import { Component, viewChild } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { ShareTheme } from '../share-card-canvas';
import { ShareCardActions } from '../share-card-actions.service';
import { ShareCardOption } from '../share-card-option';
import { ShareCardPreviewComponent } from './share-card-preview.component';

interface ActionsStub {
  rasterize: ReturnType<typeof vi.fn>;
  download: ReturnType<typeof vi.fn>;
  createObjectUrl: ReturnType<typeof vi.fn>;
  revokeObjectUrl: ReturnType<typeof vi.fn>;
  canShareFiles: ReturnType<typeof vi.fn>;
  share: ReturnType<typeof vi.fn>;
  canCopyImage: ReturnType<typeof vi.fn>;
  copyImage: ReturnType<typeof vi.fn>;
}

/** Blobs carry "<source>:<theme>", so a test can tell which image it got. */
function makeActions(overrides: Partial<ActionsStub> = {}): ActionsStub {
  let urls = 0;
  return {
    rasterize: vi.fn(
      async (option: ShareCardOption, theme: ShareTheme) => new Blob([`${option.source}:${theme}`]),
    ),
    download: vi.fn(),
    createObjectUrl: vi.fn(() => `blob:card-${++urls}`),
    revokeObjectUrl: vi.fn(),
    canShareFiles: vi.fn(() => false),
    share: vi.fn(async () => 'shared'),
    canCopyImage: vi.fn(() => false),
    copyImage: vi.fn(async () => undefined),
    ...overrides,
  };
}

function makeOption(overrides: Partial<ShareCardOption> = {}): ShareCardOption {
  return {
    source: 'card-rank',
    labelKey: 'x.kind.rank',
    fileName: 'rally-stats-rank-20260916-test.png',
    altText: { key: 'x.alt.rank', params: {} },
    draw: vi.fn(),
    ...overrides,
  };
}

@Component({
  imports: [ShareCardPreviewComponent],
  template: `
    <button type="button" class="trigger">share</button>
    <app-share-card-preview />
  `,
})
class HostComponent {
  readonly preview = viewChild.required(ShareCardPreviewComponent);
}

async function setup(actions = makeActions()) {
  TestBed.configureTestingModule({
    imports: [HostComponent],
    providers: [provideTranslateService({}), { provide: ShareCardActions, useValue: actions }],
  });
  const fixture = TestBed.createComponent(HostComponent);
  fixture.detectChanges();
  const root = fixture.nativeElement as HTMLElement;
  const open = async (options: ShareCardOption[] = [makeOption()]) => {
    (root.querySelector('.trigger') as HTMLButtonElement).focus();
    fixture.componentInstance.preview().open(options);
    await fixture.whenStable();
    fixture.detectChanges();
  };
  return { fixture, root, actions, open };
}

function button(root: HTMLElement, selector: string): HTMLButtonElement | null {
  return root.querySelector<HTMLButtonElement>(selector);
}

async function click(fixture: { whenStable(): Promise<unknown>; detectChanges(): void }, el: HTMLElement) {
  el.click();
  await fixture.whenStable();
  fixture.detectChanges();
}

describe('ShareCardPreviewComponent — preview and download (moved from 040)', () => {
  it('renders the card in the light theme and shows it as an image with alt text', async () => {
    const { root, actions, open } = await setup();
    const option = makeOption();
    await open([option]);

    expect(actions.rasterize).toHaveBeenCalledTimes(1);
    expect(actions.rasterize.mock.calls[0]).toEqual([option, 'light']);

    const img = root.querySelector<HTMLImageElement>('.share-card__preview')!;
    expect(img.getAttribute('src')).toBe('blob:card-1');
    expect(img.getAttribute('alt')).toBe('x.alt.rank');
  });

  it('shows a generating status until the image is ready', async () => {
    let resolve!: (blob: Blob) => void;
    const actions = makeActions({
      rasterize: vi.fn(() => new Promise<Blob>((r) => (resolve = r))),
    });
    const { fixture, root } = await setup(actions);
    fixture.componentInstance.preview().open([makeOption()]);
    fixture.detectChanges();

    expect(root.textContent).toContain('shareCard.generating');
    expect(root.querySelector('.share-card__preview')).toBeNull();

    resolve(new Blob(['x']));
    await fixture.whenStable();
    fixture.detectChanges();
    expect(root.textContent).not.toContain('shareCard.generating');
    expect(root.querySelector('.share-card__preview')).not.toBeNull();
  });

  it('always offers download, with the option’s file name (FR-032)', async () => {
    const { root, actions, open } = await setup();
    await open();

    button(root, '.share-card__download')!.click();

    expect(actions.download).toHaveBeenCalledTimes(1);
    const [blob, fileName] = actions.download.mock.calls[0];
    expect(blob).toBeInstanceOf(Blob);
    expect(fileName).toBe('rally-stats-rank-20260916-test.png');
  });

  it('shows an error and no download when the card cannot be created', async () => {
    const actions = makeActions({ rasterize: vi.fn(async () => Promise.reject(new Error('x'))) });
    const { root, open } = await setup(actions);
    await open();

    expect(root.querySelector('[role="alert"]')?.textContent).toContain('shareCard.generateError');
    expect(button(root, '.share-card__download')).toBeNull();
  });

  it('frees the image URL when closed, and hands focus back to what opened it', async () => {
    const { fixture, root, actions, open } = await setup();
    await open();

    fixture.componentInstance.preview().close();

    expect(actions.revokeObjectUrl).toHaveBeenCalledWith('blob:card-1');
    expect(document.activeElement).toBe(root.querySelector('.trigger'));
  });

  it('throws away a slow image that finishes after a newer one was asked for', async () => {
    const resolvers: ((blob: Blob) => void)[] = [];
    const actions = makeActions({
      rasterize: vi.fn(() => new Promise<Blob>((r) => resolvers.push(r))),
    });
    const { fixture, root } = await setup(actions);
    const preview = fixture.componentInstance.preview();
    preview.open([makeOption()]);
    preview.close();
    preview.open([makeOption()]);

    resolvers[1](new Blob(['new']));
    await fixture.whenStable();
    resolvers[0](new Blob(['old']));
    await fixture.whenStable();
    fixture.detectChanges();

    expect(actions.createObjectUrl).toHaveBeenCalledTimes(1);
    expect(root.querySelector('.share-card__preview')?.getAttribute('src')).toBe('blob:card-1');
  });

  it('renders again in the new language after the language is switched (040 SC-008)', async () => {
    const { fixture, root, actions, open } = await setup();
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('zh-TW', { x: { alt: { rank: '中文圖卡' } } });
    translate.setTranslation('en', { x: { alt: { rank: 'English card' } } });
    translate.use('zh-TW');
    const seenText: string[] = [];
    actions.rasterize.mockImplementation(async () => {
      seenText.push(translate.instant('x.alt.rank'));
      return new Blob(['x']);
    });

    await open();
    expect(root.querySelector('.share-card__preview')?.getAttribute('alt')).toBe('中文圖卡');
    fixture.componentInstance.preview().close();

    translate.use('en');
    await open();

    expect(seenText).toEqual(['中文圖卡', 'English card']);
    expect(root.querySelector('.share-card__preview')?.getAttribute('alt')).toBe('English card');
  });
});

describe('ShareCardPreviewComponent — light and dark (moved from 040)', () => {
  const themeButton = (root: HTMLElement, theme: string) =>
    root.querySelector<HTMLButtonElement>(`.share-card__theme-option[data-theme="${theme}"]`)!;

  it('starts light, with the choice exposed as pressed buttons', async () => {
    const { root, open } = await setup();
    await open();

    expect(themeButton(root, 'light').getAttribute('aria-pressed')).toBe('true');
    expect(themeButton(root, 'dark').getAttribute('aria-pressed')).toBe('false');
    expect(themeButton(root, 'light').textContent).toContain('shareCard.themeLight');
    expect(themeButton(root, 'dark').textContent).toContain('shareCard.themeDark');
  });

  it('redraws in dark, swaps the preview and downloads the dark image', async () => {
    const { fixture, root, actions, open } = await setup();
    await open();

    await click(fixture, themeButton(root, 'dark'));

    expect(actions.rasterize).toHaveBeenCalledTimes(2);
    expect(actions.rasterize.mock.calls[1][1]).toBe('dark');
    expect(actions.revokeObjectUrl).toHaveBeenCalledWith('blob:card-1');
    expect(root.querySelector('.share-card__preview')?.getAttribute('src')).toBe('blob:card-2');
    expect(themeButton(root, 'dark').getAttribute('aria-pressed')).toBe('true');

    button(root, '.share-card__download')!.click();
    const [blob] = actions.download.mock.calls[0] as [Blob];
    expect(await blob.text()).toBe('card-rank:dark');
  });

  it('does nothing when the current theme is picked again', async () => {
    const { fixture, root, actions, open } = await setup();
    await open();

    themeButton(root, 'light').click();
    await fixture.whenStable();

    expect(actions.rasterize).toHaveBeenCalledTimes(1);
  });

  it('opens light again next time (the choice isn’t remembered)', async () => {
    const { fixture, root, actions, open } = await setup();
    await open();
    themeButton(root, 'dark').click();
    await fixture.whenStable();
    fixture.componentInstance.preview().close();

    await open();

    expect(actions.rasterize.mock.calls.at(-1)![1]).toBe('light');
    expect(themeButton(root, 'light').getAttribute('aria-pressed')).toBe('true');
  });
});

describe('ShareCardPreviewComponent — share and copy (moved from 040)', () => {
  it('hides Share where the device can’t share images', async () => {
    const { root, open } = await setup(makeActions({ canShareFiles: vi.fn(() => false) }));
    await open();

    expect(button(root, '.share-card__share')).toBeNull();
    expect(button(root, '.share-card__download')).not.toBeNull();
  });

  it('shares the already-made image file, without drawing it again on tap', async () => {
    const actions = makeActions({ canShareFiles: vi.fn(() => true) });
    const { fixture, root, open } = await setup(actions);
    await open();

    await click(fixture, button(root, '.share-card__share')!);

    expect(actions.rasterize).toHaveBeenCalledTimes(1);
    expect(actions.share).toHaveBeenCalledTimes(1);
    const [file] = actions.share.mock.calls[0] as unknown as [File];
    expect(file).toBeInstanceOf(File);
    expect(file.type).toBe('image/png');
    expect(file.name).toBe('rally-stats-rank-20260916-test.png');
  });

  it('says nothing when the user cancels the share sheet', async () => {
    const actions = makeActions({
      canShareFiles: vi.fn(() => true),
      share: vi.fn(async () => 'cancelled'),
    });
    const { fixture, root, open } = await setup(actions);
    await open();

    await click(fixture, button(root, '.share-card__share')!);

    expect(root.querySelector('.share-card__message')).toBeNull();
  });

  it('suggests downloading when sharing fails', async () => {
    const actions = makeActions({
      canShareFiles: vi.fn(() => true),
      share: vi.fn(async () => Promise.reject(new Error('x'))),
    });
    const { fixture, root, open } = await setup(actions);
    await open();

    await click(fixture, button(root, '.share-card__share')!);

    expect(root.querySelector('.share-card__message')?.textContent).toContain('shareCard.shareError');
  });

  it('hides Copy where images can’t be copied, and copies the PNG where they can', async () => {
    const hidden = await setup(makeActions({ canCopyImage: vi.fn(() => false) }));
    await hidden.open();
    expect(button(hidden.root, '.share-card__copy')).toBeNull();
    TestBed.resetTestingModule();

    const actions = makeActions({ canCopyImage: vi.fn(() => true) });
    const { fixture, root, open } = await setup(actions);
    await open();
    await click(fixture, button(root, '.share-card__copy')!);

    expect(actions.copyImage).toHaveBeenCalledWith(expect.any(Blob));
    expect(root.querySelector('.share-card__message')?.textContent).toContain('shareCard.copied');
  });

  it('suggests downloading when copying fails', async () => {
    const actions = makeActions({
      canCopyImage: vi.fn(() => true),
      copyImage: vi.fn(async () => Promise.reject(new Error('x'))),
    });
    const { fixture, root, open } = await setup(actions);
    await open();

    await click(fixture, button(root, '.share-card__copy')!);

    expect(root.querySelector('.share-card__message')?.textContent).toContain('shareCard.copyError');
  });
});
