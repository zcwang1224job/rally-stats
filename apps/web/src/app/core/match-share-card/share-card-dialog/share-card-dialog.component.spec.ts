import { Component, viewChild } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { TranslateService, provideTranslateService } from '@ngx-translate/core';
import { ShareCardContext, ShareCardModel, ShareTheme } from '../share-card.models';
import { ShareCardActions } from '../share-card-actions.service';
import { makeDetail } from '../testing/detail-fixtures';
import { ShareCardDialogComponent } from './share-card-dialog.component';

const neutral: ShareCardContext = { groupName: '週三羽球團', perspective: { kind: 'neutral' } };

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

function makeActions(overrides: Partial<ActionsStub> = {}): ActionsStub {
  let urls = 0;
  return {
    rasterize: vi.fn(async (_model: ShareCardModel, theme: ShareTheme) => new Blob([theme])),
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

/** The share dialog sits inside an already-open outer dialog, opened from a
 * trigger button — the same arrangement as the match detail dialog. */
@Component({
  imports: [ShareCardDialogComponent],
  template: `
    <dialog open class="outer">
      <button type="button" class="trigger">share</button>
      <app-share-card-dialog />
    </dialog>
  `,
})
class HostComponent {
  readonly share = viewChild.required(ShareCardDialogComponent);
}

async function setup(actions = makeActions()) {
  TestBed.configureTestingModule({
    imports: [HostComponent],
    providers: [provideTranslateService({}), { provide: ShareCardActions, useValue: actions }],
  });
  const fixture = TestBed.createComponent(HostComponent);
  fixture.detectChanges();
  const root = fixture.nativeElement as HTMLElement;
  const open = async (detail = makeDetail(), context = neutral) => {
    (root.querySelector('.trigger') as HTMLButtonElement).focus();
    fixture.componentInstance.share().open(detail, context);
    await fixture.whenStable();
    fixture.detectChanges();
  };
  return { fixture, root, actions, open };
}

function button(root: HTMLElement, selector: string): HTMLButtonElement | null {
  return root.querySelector<HTMLButtonElement>(selector);
}

describe('ShareCardDialogComponent — preview and download (040 US1)', () => {
  it('renders the card in the light theme and shows it as an image with alt text', async () => {
    const { root, actions, open } = await setup();
    await open();

    expect(actions.rasterize).toHaveBeenCalledTimes(1);
    const [model, theme] = actions.rasterize.mock.calls[0];
    expect(theme).toBe('light');
    expect((model as ShareCardModel).groupName).toBe('週三羽球團');

    const img = root.querySelector<HTMLImageElement>('.share-card__preview')!;
    expect(img.getAttribute('src')).toBe('blob:card-1');
    expect(img.getAttribute('alt')).toBe('matchShareCard.altText');
  });

  it('shows a generating status until the image is ready', async () => {
    let resolve!: (blob: Blob) => void;
    const actions = makeActions({
      rasterize: vi.fn(() => new Promise<Blob>((r) => (resolve = r))),
    });
    const { fixture, root } = await setup(actions);
    fixture.componentInstance.share().open(makeDetail(), neutral);
    fixture.detectChanges();

    expect(root.textContent).toContain('matchShareCard.generating');
    expect(root.querySelector('.share-card__preview')).toBeNull();

    resolve(new Blob(['x']));
    await fixture.whenStable();
    fixture.detectChanges();
    expect(root.textContent).not.toContain('matchShareCard.generating');
    expect(root.querySelector('.share-card__preview')).not.toBeNull();
  });

  it('always offers download, with the model’s file name (FR-020)', async () => {
    const { root, actions, open } = await setup();
    await open();

    button(root, '.share-card__download')!.click();

    expect(actions.download).toHaveBeenCalledTimes(1);
    const [blob, fileName] = actions.download.mock.calls[0];
    expect(blob).toBeInstanceOf(Blob);
    expect(fileName).toMatch(/^rally-stats-\d{8}-21-17\.png$/);
  });

  it('shows an error and no download when the card cannot be created', async () => {
    const actions = makeActions({ rasterize: vi.fn(async () => Promise.reject(new Error('x'))) });
    const { root, open } = await setup(actions);
    await open();

    expect(root.querySelector('[role="alert"]')?.textContent).toContain(
      'matchShareCard.generateError',
    );
    expect(button(root, '.share-card__download')).toBeNull();
  });

  it('frees the image URL when closed', async () => {
    const { fixture, actions, open } = await setup();
    await open();

    fixture.componentInstance.share().close();

    expect(actions.revokeObjectUrl).toHaveBeenCalledWith('blob:card-1');
  });

  it('returns to the match detail: outer dialog still open, focus back on the trigger (FR-003)', async () => {
    const { fixture, root, open } = await setup();
    await open();

    fixture.componentInstance.share().close();
    fixture.detectChanges();

    expect((root.querySelector('.outer') as HTMLDialogElement).open).toBe(true);
    expect(document.activeElement).toBe(root.querySelector('.trigger'));
  });

  it('offers no perspective switch — only the entry point decides it (FR-017a)', async () => {
    const { root, open } = await setup();
    await open();

    expect(root.textContent).not.toMatch(/perspective|neutral|mine/i);
  });

  it('renders again in the new language after the language is switched (SC-008)', async () => {
    const { fixture, root, actions, open } = await setup();
    const translate = TestBed.inject(TranslateService);
    translate.setTranslation('zh-TW', { matchShareCard: { altText: '中文圖卡' } });
    translate.setTranslation('en', { matchShareCard: { altText: 'English card' } });
    translate.use('zh-TW');
    const seenText: string[] = [];
    actions.rasterize.mockImplementation(async () => {
      seenText.push(translate.instant('matchShareCard.altText'));
      return new Blob(['x']);
    });

    await open();
    expect(root.querySelector('.share-card__preview')?.getAttribute('alt')).toBe('中文圖卡');
    fixture.componentInstance.share().close();

    translate.use('en');
    await open();

    expect(seenText).toEqual(['中文圖卡', 'English card']);
    expect(root.querySelector('.share-card__preview')?.getAttribute('alt')).toBe('English card');
  });
});

describe('ShareCardDialogComponent — light and dark (040 US5, FR-024)', () => {
  const themeButton = (root: HTMLElement, theme: string) =>
    root.querySelector<HTMLButtonElement>(`.share-card__theme-option[data-theme="${theme}"]`)!;

  it('starts light, with the choice exposed as pressed buttons', async () => {
    const { root, open } = await setup();
    await open();

    expect(themeButton(root, 'light').getAttribute('aria-pressed')).toBe('true');
    expect(themeButton(root, 'dark').getAttribute('aria-pressed')).toBe('false');
    expect(themeButton(root, 'light').textContent).toContain('matchShareCard.themeLight');
    expect(themeButton(root, 'dark').textContent).toContain('matchShareCard.themeDark');
  });

  it('redraws in dark, swaps the preview and downloads the dark image', async () => {
    const { fixture, root, actions, open } = await setup();
    await open();

    themeButton(root, 'dark').click();
    await fixture.whenStable();
    fixture.detectChanges();

    expect(actions.rasterize).toHaveBeenCalledTimes(2);
    expect(actions.rasterize.mock.calls[1][1]).toBe('dark');
    expect(actions.revokeObjectUrl).toHaveBeenCalledWith('blob:card-1');
    expect(root.querySelector('.share-card__preview')?.getAttribute('src')).toBe('blob:card-2');
    expect(themeButton(root, 'dark').getAttribute('aria-pressed')).toBe('true');

    button(root, '.share-card__download')!.click();
    const [blob] = actions.download.mock.calls[0] as [Blob];
    expect(await blob.text()).toBe('dark');
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
    fixture.componentInstance.share().close();

    await open();

    expect(actions.rasterize.mock.calls.at(-1)![1]).toBe('light');
    expect(themeButton(root, 'light').getAttribute('aria-pressed')).toBe('true');
  });
});

describe('ShareCardDialogComponent — share and copy (040 US4)', () => {
  async function click(fixture: { whenStable(): Promise<unknown>; detectChanges(): void }, el: HTMLElement) {
    el.click();
    await fixture.whenStable();
    fixture.detectChanges();
  }

  it('hides Share where the device can’t share images (FR-021)', async () => {
    const { root, open } = await setup(makeActions({ canShareFiles: vi.fn(() => false) }));
    await open();

    expect(button(root, '.share-card__share')).toBeNull();
    expect(button(root, '.share-card__download')).not.toBeNull();
  });

  it('shares the already-made image file, without drawing it again on tap (research Decision 9)', async () => {
    const actions = makeActions({ canShareFiles: vi.fn(() => true) });
    const { fixture, root, open } = await setup(actions);
    await open();

    await click(fixture, button(root, '.share-card__share')!);

    expect(actions.rasterize).toHaveBeenCalledTimes(1);
    expect(actions.share).toHaveBeenCalledTimes(1);
    const [file] = actions.share.mock.calls[0] as unknown as [File];
    expect(file).toBeInstanceOf(File);
    expect(file.type).toBe('image/png');
    expect(file.name).toMatch(/^rally-stats-\d{8}-21-17\.png$/);
  });

  it('says nothing when the user cancels the share sheet (FR-023)', async () => {
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

    expect(root.querySelector('.share-card__message')?.textContent).toContain(
      'matchShareCard.shareError',
    );
  });

  it('hides Copy where images can’t be copied, and copies the PNG where they can (FR-022)', async () => {
    const hidden = await setup(makeActions({ canCopyImage: vi.fn(() => false) }));
    await hidden.open();
    expect(button(hidden.root, '.share-card__copy')).toBeNull();
    TestBed.resetTestingModule();

    const actions = makeActions({ canCopyImage: vi.fn(() => true) });
    const { fixture, root, open } = await setup(actions);
    await open();
    await click(fixture, button(root, '.share-card__copy')!);

    expect(actions.copyImage).toHaveBeenCalledWith(expect.any(Blob));
    expect(root.querySelector('.share-card__message')?.textContent).toContain(
      'matchShareCard.copied',
    );
  });

  it('suggests downloading when copying fails', async () => {
    const actions = makeActions({
      canCopyImage: vi.fn(() => true),
      copyImage: vi.fn(async () => Promise.reject(new Error('x'))),
    });
    const { fixture, root, open } = await setup(actions);
    await open();

    await click(fixture, button(root, '.share-card__copy')!);

    expect(root.querySelector('.share-card__message')?.textContent).toContain(
      'matchShareCard.copyError',
    );
  });
});
