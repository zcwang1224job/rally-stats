import { TestBed } from '@angular/core/testing';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { SHARE_CARD_HEIGHT, SHARE_CARD_WIDTH, ShareCardCanvas } from './share-card-canvas';
import { ShareCardActions } from './share-card-actions.service';
import { ShareCardOption, ShareCardRenderEnv } from './share-card-option';
import { SHARE_PALETTES } from './share-card-palette';
import { RecordingContext } from './testing/recording-context';

/** jsdom has none of these browser APIs; each test installs just what it
 * needs and puts things back afterwards. */
const installed: { target: object; key: string }[] = [];

function install(target: object, key: string, value: unknown): void {
  Object.defineProperty(target, key, { value, configurable: true, writable: true });
  installed.push({ target, key });
}

function setup(): ShareCardActions {
  TestBed.configureTestingModule({ providers: [provideTranslateService({})] });
  return TestBed.inject(ShareCardActions);
}

const file = () => new File(['png'], 'card.png', { type: 'image/png' });

/** jsdom has no canvas: hand `rasterize()` one that records what it draws
 * and "encodes" to a small PNG blob. */
function fakeCanvas() {
  const ctx = new RecordingContext();
  const canvas = {
    width: 0,
    height: 0,
    getContext: () => ctx,
    toBlob: (done: (blob: Blob | null) => void) => done(new Blob(['png'], { type: 'image/png' })),
  };
  const original = document.createElement.bind(document);
  vi.spyOn(document, 'createElement').mockImplementation(((tag: string) =>
    tag === 'canvas' ? canvas : original(tag)) as typeof document.createElement);
  return { canvas, ctx };
}

function option(overrides: Partial<ShareCardOption> = {}): ShareCardOption {
  return {
    source: 'card-rank',
    labelKey: 'x.kind',
    fileName: 'card.png',
    altText: { key: 'x.alt', params: {} },
    draw: vi.fn((ctx: ShareCardCanvas) => ctx.fillText('drawn', 0, 0)),
    ...overrides,
  };
}

describe('ShareCardActions — rasterize (041 contracts/share-card-core.md §3)', () => {
  afterEach(() => vi.restoreAllMocks());

  it('draws the option once on a fixed 1080×1350 canvas and encodes a PNG', async () => {
    const actions = setup();
    const { canvas, ctx } = fakeCanvas();
    const card = option();

    const blob = await actions.rasterize(card, 'light');

    expect(blob.type).toBe('image/png');
    expect([canvas.width, canvas.height]).toEqual([SHARE_CARD_WIDTH, SHARE_CARD_HEIGHT]);
    expect(card.draw).toHaveBeenCalledTimes(1);
    expect(ctx.texts()).toEqual(['drawn']);
  });

  it('hands the draw the chosen palette, the translations and the card’s footer', async () => {
    const actions = setup();
    TestBed.inject(TranslateService).setTranslation('en', { x: { hello: 'Hello' } });
    TestBed.inject(TranslateService).use('en');
    fakeCanvas();
    const card = option({ source: 'card-me' });

    await actions.rasterize(card, 'dark');

    const env = vi.mocked(card.draw).mock.calls[0][1] as ShareCardRenderEnv;
    expect(env.palette).toBe(SHARE_PALETTES.dark);
    expect(env.text('x.hello')).toBe('Hello');
    expect(env.footer.link.qrUrl).toBe(`${window.location.origin}/?ref=card-me`);
    expect(env.footer.link.displayUrl).toBe(window.location.host);
    expect(env.footer.meta).toBeNull();
  });
});

describe('ShareCardActions — system share (040 US4, FR-021/FR-023)', () => {
  afterEach(() => {
    for (const { target, key } of installed.splice(0)) {
      delete (target as Record<string, unknown>)[key];
    }
  });

  it('can share only when the browser says it can share this file', () => {
    const actions = setup();
    expect(actions.canShareFiles(file())).toBe(false);

    const canShare = vi.fn(() => true);
    install(navigator, 'canShare', canShare);
    const card = file();
    expect(actions.canShareFiles(card)).toBe(true);
    expect(canShare).toHaveBeenCalledWith({ files: [card] });

    install(navigator, 'canShare', () => false);
    expect(actions.canShareFiles(file())).toBe(false);
  });

  it('shares the image file itself', async () => {
    const actions = setup();
    const share = vi.fn(async () => undefined);
    install(navigator, 'share', share);
    const card = file();

    await expect(actions.share(card)).resolves.toBe('shared');
    expect(share).toHaveBeenCalledWith({ files: [card] });
  });

  it('shares the file alone — no title, text or url, which can make apps drop the image (041 FR-023)', async () => {
    const actions = setup();
    const share = vi.fn(async () => undefined);
    install(navigator, 'share', share);

    await actions.share(file());

    const [data] = share.mock.calls[0] as unknown as [ShareData];
    expect(Object.keys(data)).toEqual(['files']);
  });

  it('treats the user dismissing the share sheet as a cancel, not an error', async () => {
    const actions = setup();
    install(navigator, 'share', async () => {
      throw new DOMException('dismissed', 'AbortError');
    });

    await expect(actions.share(file())).resolves.toBe('cancelled');
  });

  it('passes any other failure on', async () => {
    const actions = setup();
    install(navigator, 'share', async () => {
      throw new DOMException('nope', 'NotAllowedError');
    });

    await expect(actions.share(file())).rejects.toThrow('nope');
  });
});

describe('ShareCardActions — copy image (040 US4, FR-022)', () => {
  afterEach(() => {
    for (const { target, key } of installed.splice(0)) {
      delete (target as Record<string, unknown>)[key];
    }
  });

  class FakeClipboardItem {
    constructor(readonly items: Record<string, Blob>) {}
  }

  function installClipboard(secure = true) {
    const write = vi.fn(async () => undefined);
    install(window, 'isSecureContext', secure);
    install(globalThis, 'ClipboardItem', FakeClipboardItem);
    install(navigator, 'clipboard', { write });
    return write;
  }

  it('can copy only in a secure page with image clipboard support', () => {
    const actions = setup();
    expect(actions.canCopyImage()).toBe(false);

    installClipboard(true);
    expect(actions.canCopyImage()).toBe(true);
  });

  it('cannot copy on a plain http page (the LAN test setup)', () => {
    const actions = setup();
    installClipboard(false);

    expect(actions.canCopyImage()).toBe(false);
  });

  it('cannot copy without ClipboardItem', () => {
    const actions = setup();
    installClipboard(true);
    delete (globalThis as Record<string, unknown>)['ClipboardItem'];

    expect(actions.canCopyImage()).toBe(false);
  });

  it('writes the card to the clipboard as a PNG', async () => {
    const actions = setup();
    const write = installClipboard(true);
    const blob = new Blob(['png'], { type: 'image/png' });

    await actions.copyImage(blob);

    expect(write).toHaveBeenCalledTimes(1);
    const [items] = write.mock.calls[0] as unknown as [FakeClipboardItem[]];
    expect(items[0].items).toEqual({ 'image/png': blob });
  });
});
