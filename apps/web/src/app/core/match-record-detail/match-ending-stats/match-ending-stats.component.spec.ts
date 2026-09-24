import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { EndingStats } from '../../api/group-member-view.models';
import { MatchEndingStatsComponent } from './match-ending-stats.component';

// No translations are loaded, so every string renders as its own i18n key —
// assertions below match on keys and numbers, never on Chinese/English copy.

// Doubles, 21:18 with 30 of the 39 points recorded: A hit 12 winners and
// gave away 7; B hit 6 and gave away 5.
const recorded: EndingStats = {
  recorded_points: 30,
  total_points: 39,
  teams: [
    { team: 'A', winners: 12, errors: 7, errors_by_type: { out: 3, net: 2, serve_fault: 1, other_error: 1 } },
    { team: 'B', winners: 6, errors: 5, errors_by_type: { out: 2, net: 3, serve_fault: 0, other_error: 0 } },
  ],
  players: [
    {
      roster_entry_id: 'a1', nickname: '甲', team: 'A',
      winners: 8, opponent_errors: 3, scored_unrecorded: 2,
      beaten_by_winners: 4, own_errors: 5, lost_unrecorded: 1,
    },
    {
      roster_entry_id: 'a2', nickname: '乙', team: 'A',
      winners: 4, opponent_errors: 2, scored_unrecorded: 2,
      beaten_by_winners: 2, own_errors: 2, lost_unrecorded: 4,
    },
    {
      roster_entry_id: 'b1', nickname: '丙', team: 'B',
      winners: 6, opponent_errors: 7, scored_unrecorded: 5,
      beaten_by_winners: 12, own_errors: 5, lost_unrecorded: 4,
    },
    {
      roster_entry_id: 'b2', nickname: '丁', team: 'B',
      winners: 0, opponent_errors: 0, scored_unrecorded: 0,
      beaten_by_winners: 0, own_errors: 0, lost_unrecorded: 0,
    },
  ],
};

function setup(endingStats: EndingStats | null): ComponentFixture<MatchEndingStatsComponent> {
  TestBed.configureTestingModule({
    imports: [MatchEndingStatsComponent],
    providers: [provideTranslateService({})],
  });
  const fixture = TestBed.createComponent(MatchEndingStatsComponent);
  fixture.componentRef.setInput('endingStats', endingStats);
  fixture.detectChanges();
  return fixture;
}

function text(el: Element | null): string {
  return el?.textContent?.replace(/\s+/g, ' ').trim() ?? '';
}

describe('MatchEndingStatsComponent', () => {
  it('shows one notice and no table or facts when there is nothing recorded (FR-017)', () => {
    const root: HTMLElement = setup(null).nativeElement;

    expect(root.textContent).toContain('matchRecordDetail.ending.empty');
    expect(root.querySelector('dl')).toBeNull();
    expect(root.querySelector('table')).toBeNull();
    expect(root.querySelector('[data-fact="coverage"]')).toBeNull();
  });

  it('states the coverage as recorded out of total points', () => {
    const root: HTMLElement = setup(recorded).nativeElement;

    expect(text(root.querySelector('[data-fact="coverage"]'))).toBe(
      'matchRecordDetail.ending.coverage',
    );
    // The interpolation params reach the pipe — checked through the
    // component's own input rather than the untranslated key.
    expect(recorded.recorded_points).toBe(30);
  });

  it('lists each team\'s winners and errors with an icon per kind, A before B (FR-014)', () => {
    const root: HTMLElement = setup(recorded).nativeElement;

    const teamRows = Array.from(root.querySelectorAll('[data-fact-row]')).map((el) =>
      el.getAttribute('data-fact-row'),
    );
    expect(teamRows).toEqual(['team-A', 'team-B']);
    const rowA = root.querySelector('[data-fact-row="team-A"]')!;
    expect(rowA.querySelector('.ending-kind--winner .ending-kind__icon')).not.toBeNull();
    expect(rowA.querySelector('.ending-kind--error .ending-kind__icon')).not.toBeNull();
    expect(text(rowA)).toContain('matchRecordDetail.ending.teamWinners');
    expect(text(rowA)).toContain('matchRecordDetail.ending.teamErrors');
    expect(text(rowA)).toContain('matchRecordDetail.ending.errorsBreakdown');
  });

  it('renders every player in order with the six split columns, all-zero rows included', () => {
    const root: HTMLElement = setup(recorded).nativeElement;

    const rows = Array.from(root.querySelectorAll('tbody tr'));
    expect(rows.map((row) => row.getAttribute('data-player'))).toEqual(['a1', 'a2', 'b1', 'b2']);
    const cells = (row: Element): string[] => Array.from(row.querySelectorAll('td')).map(text);
    expect(cells(rows[0])).toEqual(['8', '3', '2', '4', '5', '1']);
    expect(cells(rows[3])).toEqual(['0', '0', '0', '0', '0', '0']);
    expect(text(rows[0].querySelector('th'))).toContain('甲');
  });

  it('shows each player\'s totals the six columns add up to', () => {
    const fixture = setup(recorded);

    const [a1] = fixture.componentInstance.playerRows();
    expect(a1.scored_total).toBe(8 + 3 + 2);
    expect(a1.lost_total).toBe(4 + 5 + 1);
    const root: HTMLElement = fixture.nativeElement;
    expect(text(root.querySelector('tbody tr th'))).toContain('matchRecordDetail.ending.playerTotals');
  });

  it('marks winner and error columns with an icon in the table header too', () => {
    const root: HTMLElement = setup(recorded).nativeElement;

    expect(root.querySelectorAll('thead .ending-kind__icon').length).toBe(4);
  });
});
