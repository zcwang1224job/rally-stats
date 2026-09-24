import { ChangeDetectorRef, ElementRef, inject, signal } from '@angular/core';

/** A records page's big sections run as an accordion: all folded on
 * arrival, and opening one folds whichever was open — so the page is a short
 * list of titles above the matches rather than a long scroll through every
 * section. Shared by the member's own 對戰紀錄 and a friend's records page.
 *
 * Create it in a component field initializer (it injects the host element
 * and its change detector). Each panel is a `<details>` — or a component
 * rendering one — that carries `data-section="<key>"`, binds
 * `[open]="sections.isOpen('<key>')"` and reports the reader's own toggles
 * to `toggled()`. */
export class SectionAccordion<S extends string> {
  private readonly host = inject<ElementRef<HTMLElement>>(ElementRef);
  private readonly cdr = inject(ChangeDetectorRef);

  /** The one open section — none on arrival. */
  readonly openSection = signal<S | null>(null);

  isOpen(section: S): boolean {
    return this.openSection() === section;
  }

  /** A panel was opened or closed (its `toggle`). The previously open one
   * folds NOW, not on the next change detection: if it sat above this one,
   * the page shifts up by its height and the title just tapped would be
   * left off screen. Measured after the shift, it is scrolled back. */
  toggled(section: S, open: boolean): void {
    if (!open) {
      if (this.isOpen(section)) {
        this.openSection.set(null);
      }
      return;
    }
    if (this.isOpen(section)) {
      return; // our own [open] binding echoing back
    }
    this.openNow(section);
    const panel = this.host.nativeElement.querySelector<HTMLElement>(`[data-section="${section}"]`);
    // "Off screen" includes tucked under the sticky nav, which is what the
    // panel's scroll-margin-top clears.
    const clearance = panel ? parseFloat(getComputedStyle(panel).scrollMarginTop) || 0 : 0;
    if (panel && panel.getBoundingClientRect().top < clearance) {
      panel.scrollIntoView?.({ block: 'start' });
    }
  }

  /** Opens a section for a jump into it (an insight sentence), folding the
   * rest before anything inside it is measured or scrolled to. */
  openNow(section: S): void {
    this.openSection.set(section);
    this.cdr.detectChanges();
  }

  closeAll(): void {
    this.openSection.set(null);
  }
}
