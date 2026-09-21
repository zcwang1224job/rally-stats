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
