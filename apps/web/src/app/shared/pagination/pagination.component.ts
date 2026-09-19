import { Component, computed, input, output } from '@angular/core';
import { TranslatePipe } from '@ngx-translate/core';

/** One slot in the page list: a page number, or a gap standing in for a
 * run of skipped pages. */
export type PageSlot = number | 'gap';

/** Pages shown when there are more than MAX_UNWINDOWED: first, last, and
 * the current page with one neighbor either side; everything else collapses
 * into a gap. Up to MAX_UNWINDOWED pages are simply all listed. */
const MAX_UNWINDOWED = 7;

export function pageSlots(page: number, totalPages: number): PageSlot[] {
  if (totalPages <= MAX_UNWINDOWED) {
    return Array.from({ length: totalPages }, (_, i) => i + 1);
  }
  const shown = new Set([1, totalPages, page - 1, page, page + 1]);
  const slots: PageSlot[] = [];
  for (let p = 1; p <= totalPages; p++) {
    if (shown.has(p)) {
      slots.push(p);
    } else if (slots[slots.length - 1] !== 'gap') {
      slots.push('gap');
    }
  }
  return slots;
}

/** The app's one pagination control (replaces the per-page copies). The
 * current page is marked with `aria-current="page"` and a solid style —
 * never `disabled`, which the shared `.btn` renders as a faded button that
 * reads as "unavailable" rather than "you are here". Renders nothing when
 * there is only one page. */
@Component({
  selector: 'app-pagination',
  imports: [TranslatePipe],
  templateUrl: './pagination.component.html',
  styleUrl: './pagination.component.scss',
})
export class PaginationComponent {
  readonly page = input.required<number>();
  readonly totalPages = input.required<number>();
  readonly pageChange = output<number>();

  readonly slots = computed(() => pageSlots(this.page(), this.totalPages()));

  goTo(p: number): void {
    if (p !== this.page() && p >= 1 && p <= this.totalPages()) {
      this.pageChange.emit(p);
    }
  }
}
