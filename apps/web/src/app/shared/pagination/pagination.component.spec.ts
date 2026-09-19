import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { PaginationComponent, pageSlots } from './pagination.component';

function setup(page: number, totalPages: number) {
  TestBed.configureTestingModule({
    imports: [PaginationComponent],
    providers: [provideTranslateService({})],
  });
  const fixture = TestBed.createComponent(PaginationComponent);
  fixture.componentRef.setInput('page', page);
  fixture.componentRef.setInput('totalPages', totalPages);
  const emitted: number[] = [];
  fixture.componentInstance.pageChange.subscribe((p) => emitted.push(p));
  fixture.detectChanges();
  const buttons = (): HTMLButtonElement[] =>
    Array.from(fixture.nativeElement.querySelectorAll('.pagination button'));
  return { fixture, emitted, buttons };
}

describe('pageSlots', () => {
  it('lists every page when there are 7 or fewer', () => {
    expect(pageSlots(1, 1)).toEqual([1]);
    expect(pageSlots(4, 7)).toEqual([1, 2, 3, 4, 5, 6, 7]);
  });

  it('keeps first, last and the current page with its neighbors, collapsing the rest', () => {
    expect(pageSlots(1, 20)).toEqual([1, 2, 'gap', 20]);
    expect(pageSlots(10, 20)).toEqual([1, 'gap', 9, 10, 11, 'gap', 20]);
    expect(pageSlots(20, 20)).toEqual([1, 'gap', 19, 20]);
    expect(pageSlots(3, 20)).toEqual([1, 2, 3, 4, 'gap', 20]);
  });
});

describe('PaginationComponent', () => {
  it('renders nothing for a single page', () => {
    const { fixture } = setup(1, 1);
    expect(fixture.nativeElement.querySelector('.pagination')).toBeNull();
  });

  it('renders previous, every page, and next', () => {
    const { buttons } = setup(1, 3);
    expect(buttons().map((b) => b.textContent?.trim())).toEqual([
      'common.previousPage',
      '1',
      '2',
      '3',
      'common.nextPage',
    ]);
  });

  it('marks the current page with aria-current instead of disabling it', () => {
    const { buttons } = setup(2, 3);
    const current = buttons().find((b) => b.getAttribute('aria-current') === 'page');
    expect(current?.textContent?.trim()).toBe('2');
    expect(current?.disabled).toBe(false);
    expect(buttons().filter((b) => b.hasAttribute('aria-current')).length).toBe(1);
  });

  it('disables previous on the first page and next on the last', () => {
    const first = setup(1, 3).buttons();
    expect(first[0].disabled).toBe(true);
    expect(first[first.length - 1].disabled).toBe(false);

    TestBed.resetTestingModule();
    const last = setup(3, 3).buttons();
    expect(last[0].disabled).toBe(false);
    expect(last[last.length - 1].disabled).toBe(true);
  });

  it('emits the chosen page, and nothing when the current page is clicked', () => {
    const { buttons, emitted } = setup(2, 3);
    const byText = (t: string) => buttons().find((b) => b.textContent?.trim() === t)!;
    byText('3').click();
    byText('2').click();
    byText('common.previousPage').click();
    byText('common.nextPage').click();
    expect(emitted).toEqual([3, 1, 3]);
  });
});
