import { Component, viewChild } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { ShareCardActions } from '../../share-card/share-card-actions.service';
import { ShareCardOption } from '../../share-card/share-card-option';
import { ShareCardContext } from '../share-card.models';
import { makeDetail } from '../testing/detail-fixtures';
import { ShareCardDialogComponent } from './share-card-dialog.component';

const neutral: ShareCardContext = { groupName: '週三羽球團', perspective: { kind: 'neutral' } };

function makeActions() {
  let urls = 0;
  return {
    rasterize: vi.fn(async (option: ShareCardOption) => new Blob([option.source])),
    download: vi.fn(),
    createObjectUrl: vi.fn(() => `blob:card-${++urls}`),
    revokeObjectUrl: vi.fn(),
    canShareFiles: vi.fn(() => false),
    share: vi.fn(async () => 'shared'),
    canCopyImage: vi.fn(() => false),
    copyImage: vi.fn(async () => undefined),
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

async function setup() {
  const actions = makeActions();
  TestBed.configureTestingModule({
    imports: [HostComponent],
    providers: [provideTranslateService({}), { provide: ShareCardActions, useValue: actions }],
  });
  const fixture = TestBed.createComponent(HostComponent);
  fixture.detectChanges();
  const root = fixture.nativeElement as HTMLElement;
  const open = async () => {
    (root.querySelector('.trigger') as HTMLButtonElement).focus();
    fixture.componentInstance.share().open(makeDetail(), neutral);
    await fixture.whenStable();
    fixture.detectChanges();
  };
  return { fixture, root, actions, open };
}

describe('ShareCardDialogComponent — 040’s entry into the shared preview (041)', () => {
  it('opens the preview with the match card as its only option', async () => {
    const { root, actions, open } = await setup();
    await open();

    expect(actions.rasterize).toHaveBeenCalledTimes(1);
    const option = actions.rasterize.mock.calls[0][0];
    expect(option.source).toBe('card-match');
    expect(option.fileName).toMatch(/^rally-stats-\d{8}-21-17\.png$/);
    expect(root.querySelector('.share-card__preview')?.getAttribute('alt')).toBe(
      'matchShareCard.altText',
    );
    // One option: no kind switch.
    expect(root.querySelector('.share-card__kind')).toBeNull();
  });

  it('offers no perspective switch — only the entry point decides it (040 FR-017a)', async () => {
    const { root, open } = await setup();
    await open();

    expect(root.textContent).not.toMatch(/perspective|neutral|mine/i);
  });

  it('returns to the match detail: outer dialog still open, focus back on the trigger (040 FR-003)', async () => {
    const { fixture, root, open } = await setup();
    await open();

    fixture.componentInstance.share().close();
    fixture.detectChanges();

    expect((root.querySelector('.outer') as HTMLDialogElement).open).toBe(true);
    expect(document.activeElement).toBe(root.querySelector('.trigger'));
  });
});
