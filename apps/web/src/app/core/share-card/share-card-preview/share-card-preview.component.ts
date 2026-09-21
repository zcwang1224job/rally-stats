import { Component, ElementRef, OnDestroy, inject, signal, viewChild } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';
import { ShareTheme } from '../share-card-canvas';
import { ShareCardActions } from '../share-card-actions.service';
import { ShareCardOption } from '../share-card-option';

type Status = 'idle' | 'generating' | 'ready' | 'error';

let nextId = 0;

/** 040-match-share-card's preview, shared by every card since 041
 * (contracts/share-card-core.md §2). It knows nothing about any card's
 * data: each option draws itself. Opens as its own modal; closing it hands
 * focus back to whatever opened it. The preview is the generated PNG
 * itself, so what you see is the file you get. */
@Component({
  selector: 'app-share-card-preview',
  imports: [TranslatePipe],
  templateUrl: './share-card-preview.component.html',
  styleUrl: './share-card-preview.component.scss',
})
export class ShareCardPreviewComponent implements OnDestroy {
  private readonly actions = inject(ShareCardActions);
  private readonly dialog = viewChild.required<ElementRef<HTMLDialogElement>>('dialog');

  /** A page can hold more than one preview (a group page plus the match
   * detail it opens), so the heading id must be unique. */
  readonly titleId = `share-card-title-${++nextId}`;

  readonly options = signal<readonly ShareCardOption[]>([]);
  readonly selected = signal<ShareCardOption | null>(null);
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
   * starts after awaiting anything (040 research.md Decision 9). */
  private file: File | null = null;
  private returnFocus: HTMLElement | null = null;
  /** Bumped on every render request and on close, so a slow render that
   * finishes after a newer one (or after closing) is thrown away. */
  private generation = 0;

  /** Opens on the first option, in light colors — neither choice is
   * remembered from last time. */
  open(options: readonly ShareCardOption[]): void {
    this.returnFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    this.options.set(options);
    this.selected.set(options[0] ?? null);
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
    const option = this.selected();
    if (this.blob && option) {
      this.actions.download(this.blob, option.fileName);
    }
  }

  readonly themes: readonly ShareTheme[] = ['light', 'dark'];

  /** Redraws in the chosen colors; download/share/copy then use the new
   * image. */
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
      // A dismissed share sheet is the user's choice, not a failure.
      () => undefined,
      () => this.message.set('shareCard.shareError'),
    );
  }

  copy(): void {
    if (!this.blob) {
      return;
    }
    this.message.set(null);
    this.actions.copyImage(this.blob).then(
      () => this.message.set('shareCard.copied'),
      () => this.message.set('shareCard.copyError'),
    );
  }

  ngOnDestroy(): void {
    this.generation++;
    this.releaseImage();
  }

  private async generate(): Promise<void> {
    const option = this.selected();
    if (!option) {
      return;
    }
    const run = ++this.generation;
    this.status.set('generating');
    this.message.set(null);
    try {
      const blob = await this.actions.rasterize(option, this.theme());
      if (run !== this.generation) {
        return;
      }
      this.releaseImage();
      this.blob = blob;
      this.file = new File([blob], option.fileName, { type: 'image/png' });
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
