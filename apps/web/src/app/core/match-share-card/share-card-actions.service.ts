import { Injectable, inject } from '@angular/core';
import { TranslateService } from '@ngx-translate/core';
import { ShareCardModel, ShareTheme } from './share-card.models';
import { SHARE_PALETTES } from './share-card-palette';
import { SHARE_CARD_HEIGHT, SHARE_CARD_WIDTH, renderShareCard } from './share-card-renderer';

/** 040-match-share-card: everything that touches the browser — canvas,
 * files, object URLs — kept behind one injectable so the preview dialog can
 * be tested without any of it (research.md Decision 9). */
@Injectable({ providedIn: 'root' })
export class ShareCardActions {
  private readonly translate = inject(TranslateService);

  /** Draws the card on a fixed 1080×1350 canvas — never scaled by the
   * device pixel ratio, so every phone produces the same file (FR-004). */
  async rasterize(model: ShareCardModel, theme: ShareTheme): Promise<Blob> {
    await document.fonts?.ready;
    const style = getComputedStyle(document.documentElement);
    const fonts = {
      base: style.getPropertyValue('--font-family-base').trim() || 'sans-serif',
      score: style.getPropertyValue('--font-family-score').trim() || 'sans-serif',
    };
    const canvas = document.createElement('canvas');
    canvas.width = SHARE_CARD_WIDTH;
    canvas.height = SHARE_CARD_HEIGHT;
    const ctx = canvas.getContext('2d');
    if (!ctx) {
      throw new Error('Canvas 2D is not available');
    }
    // Read at draw time, so a card opened after a language switch is drawn
    // in the new language (SC-008).
    renderShareCard(
      ctx,
      model,
      SHARE_PALETTES[theme],
      (key, params) => String(this.translate.instant(key, params)),
      fonts,
    );
    return new Promise<Blob>((resolve, reject) =>
      canvas.toBlob(
        (blob) => (blob ? resolve(blob) : reject(new Error('Could not encode the card'))),
        'image/png',
      ),
    );
  }

  createObjectUrl(blob: Blob): string {
    return URL.createObjectURL(blob);
  }

  revokeObjectUrl(url: string): void {
    URL.revokeObjectURL(url);
  }

  /** Sharing the image FILE is the one web route into LINE/IG with a
   * picture attached (Web Share Level 2). `core/line-share.ts` deliberately
   * avoids `navigator.share` — but that is for sharing a link, which the
   * LINE it! endpoint handles on desktop too; it cannot carry an image, so
   * the two choices don't conflict (research.md Decision 9). */
  canShareFiles(file: File): boolean {
    try {
      return typeof navigator.canShare === 'function' && navigator.canShare({ files: [file] });
    } catch {
      return false;
    }
  }

  /** Resolves `'cancelled'` when the user dismisses the share sheet — not
   * an error (FR-023); anything else is passed on to the caller. */
  async share(file: File): Promise<'shared' | 'cancelled'> {
    try {
      await navigator.share({ files: [file] });
      return 'shared';
    } catch (error) {
      if ((error as { name?: string } | null)?.name === 'AbortError') {
        return 'cancelled';
      }
      throw error;
    }
  }

  /** Unlike `core/clipboard.ts` (text, with an execCommand fallback), an
   * image has no fallback: it needs a secure context and ClipboardItem, so
   * over plain-http LAN testing the Copy button simply isn't offered. */
  canCopyImage(): boolean {
    return (
      window.isSecureContext === true &&
      typeof ClipboardItem !== 'undefined' &&
      typeof navigator.clipboard?.write === 'function'
    );
  }

  async copyImage(blob: Blob): Promise<void> {
    await navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })]);
  }

  download(blob: Blob, fileName: string): void {
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = fileName;
    document.body.appendChild(link);
    link.click();
    link.remove();
    // Revoking in the same tick can cancel the download in Safari; a short
    // delay lets it start first.
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
}
