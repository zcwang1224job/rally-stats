import { Component, ElementRef, OnDestroy, inject, signal, viewChild } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import { MatchRecordDetailResponse } from '../../api/group-member-view.models';
import { ShareCardContext, ShareCardModel, ShareTheme } from '../share-card.models';
import { ShareCardActions } from '../share-card-actions.service';
import { buildShareCardModel } from '../share-card-model';

type Status = 'idle' | 'generating' | 'ready' | 'error';

/** 040-match-share-card: the preview opened from the match detail dialog
 * (research.md Decision 11). Stacks on top of the detail as its own modal;
 * closing it hands focus back to the button that opened it and leaves the
 * detail exactly as it was (FR-003). The preview is the generated PNG
 * itself, so what you see is the file you get (SC-006). */
@Component({
  selector: 'app-share-card-dialog',
  imports: [TranslatePipe],
  templateUrl: './share-card-dialog.component.html',
  styleUrl: './share-card-dialog.component.scss',
})
export class ShareCardDialogComponent implements OnDestroy {
  private readonly actions = inject(ShareCardActions);
  private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');

  readonly model = signal<ShareCardModel | null>(null);
  readonly theme = signal<ShareTheme>('light');
  readonly status = signal<Status>('idle');
  readonly imageUrl = signal<string | null>(null);
  /** Language key of a short notice (copied, share failed, …). */
  readonly message = signal<string | null>(null);

  readonly canShare = signal(false);
  readonly canCopy = signal(false);

  private blob: Blob | null = null;
  /** Made as soon as the image is ready, so Share can hand it to the
   * system sheet straight from the tap — iOS Safari refuses a share that
   * starts after awaiting anything (research.md Decision 9). */
  private file: File | null = null;
  private returnFocus: HTMLElement | null = null;
  /** Bumped on every render request and on close, so a slow render that
   * finishes after a newer one (or after closing) is thrown away. */
  private generation = 0;

  open(detail: MatchRecordDetailResponse, context: ShareCardContext): void {
    this.returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    this.model.set(buildShareCardModel(detail, context));
    this.theme.set('light');
    this.message.set(null);
    const nativeDialog = this.dialog().nativeElement;
    if (typeof nativeDialog.showModal === 'function') {
      nativeDialog.showModal();
    } else {
      nativeDialog.setAttribute('open', '');
    }
    void this.generate();
  }

  close(): void {
    const nativeDialog = this.dialog().nativeElement;
    if (typeof nativeDialog.close === 'function') {
      nativeDialog.close();
    } else {
      nativeDialog.removeAttribute('open');
    }
    this.reset();
  }

  /** Esc closes the native dialog without going through close(). */
  onNativeClose(): void {
    this.reset();
  }

  download(): void {
    const model = this.model();
    if (this.blob && model) {
      this.actions.download(this.blob, model.fileName);
    }
  }

  readonly themes: readonly ShareTheme[] = ['light', 'dark'];

  /** FR-024: redraws in the chosen colors; download/share/copy then use
   * the new image. Not remembered — every preview opens light. */
  selectTheme(theme: ShareTheme): void {
    if (theme === this.theme() || this.status() === 'idle') {
      return;
    }
    this.theme.set(theme);
    void this.generate();
  }

  /** Called straight from the tap, with the file made in advance. */
  share(): void {
    if (!this.file) {
      return;
    }
    this.message.set(null);
    this.actions.share(this.file).then(
      // A dismissed share sheet is the user's choice, not a failure (FR-023).
      () => undefined,
      () => this.message.set('matchShareCard.shareError'),
    );
  }

  copy(): void {
    if (!this.blob) {
      return;
    }
    this.message.set(null);
    this.actions.copyImage(this.blob).then(
      () => this.message.set('matchShareCard.copied'),
      () => this.message.set('matchShareCard.copyError'),
    );
  }

  ngOnDestroy(): void {
    this.generation++;
    this.releaseImage();
  }

  private async generate(): Promise<void> {
    const model = this.model();
    if (!model) {
      return;
    }
    const run = ++this.generation;
    this.status.set('generating');
    this.message.set(null);
    try {
      const blob = await this.actions.rasterize(model, this.theme());
      if (run !== this.generation) {
        return;
      }
      this.releaseImage();
      this.blob = blob;
      this.file = new File([blob], model.fileName, { type: 'image/png' });
      this.canShare.set(this.actions.canShareFiles(this.file));
      this.canCopy.set(this.actions.canCopyImage());
      this.imageUrl.set(this.actions.createObjectUrl(blob));
      this.status.set('ready');
    } catch {
      if (run !== this.generation) {
        return;
      }
      this.releaseImage();
      this.status.set('error');
    }
  }

  private reset(): void {
    this.generation++;
    this.releaseImage();
    this.status.set('idle');
    this.message.set(null);
    const target = this.returnFocus;
    this.returnFocus = null;
    target?.focus();
  }

  private releaseImage(): void {
    const url = this.imageUrl();
    if (url) {
      this.actions.revokeObjectUrl(url);
    }
    this.imageUrl.set(null);
    this.blob = null;
    this.file = null;
    this.canShare.set(false);
    this.canCopy.set(false);
  }
}
