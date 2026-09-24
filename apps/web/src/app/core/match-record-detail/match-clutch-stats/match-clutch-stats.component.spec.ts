import { ComponentFixture, TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { ClutchStats } from '../../api/group-member-view.models';
import { MatchClutchStatsComponent } from './match-clutch-stats.component';

// No translations are loaded, so every string renders as its own i18n key —
// assertions below match on keys, never on Chinese/English copy.

// 22:24 after 20:20 — see test_match_stats.py's long-tiebreak case.
const wentToDeuce: ClutchStats = {
  endgame_from: 18,
  endgame: [
    { team: 'A', won: 5, total: 11 },
    { team: 'B', won: 6, total: 11 },
  ],
  deuce: [
    { team: 'A', won: 2, total: 6 },
    { team: 'B', won: 4, total: 6 },
  ],
  match_points: [
    { team: 'A', held: 3, converted_on: null, saved: 0 },
    { team: 'B', held: 1, converted_on: 1, saved: 3 },
  ],
  by_state: [
    { team: 'A', leading: { won: 10, total: 23 }, tied: { won: 12, total: 23 }, trailing: { won: 0, total: 0 } },
    { team: 'B', leading: { won: 0, total: 0 }, tied: { won: 11, total: 23 }, trailing: { won: 13, total: 23 } },
  ],
  comeback: { winner: 'B', max_deficit: 1, score_a: 1, score_b: 0 },
};

function setup(clutchStats: ClutchStats | null): ComponentFixture<MatchClutchStatsComponent> {
  TestBed.configureTestingModule({
    imports: [MatchClutchStatsComponent],
    providers: [provideTranslateService({})],
  });
  const fixture = TestBed.createComponent(MatchClutchStatsComponent);
  fixture.componentRef.setInput('clutchStats', clutchStats);
  fixture.detectChanges();
  return fixture;
}

function rows(root: HTMLElement, fact: string): string[] {
  return Array.from(root.querySelectorAll(`[data-fact-row="${fact}"]`)).map(
    (el) => el.textContent?.replace(/\s+/g, ' ').trim() ?? '',
  );
}

describe('MatchClutchStatsComponent', () => {
  it('shows one notice and no numbers when the record is incomplete (FR-016)', () => {
    const root: HTMLElement = setup(null).nativeElement;

    expect(root.textContent).toContain('matchRecordDetail.clutch.empty');
    expect(root.querySelector('dl')).toBeNull();
    expect(root.querySelector('table')).toBeNull();
    expect(root.textContent).not.toContain('%');
  });

  it('shows endgame and deuce as won/total with a percentage, A before B', () => {
    const root: HTMLElement = setup(wentToDeuce).nativeElement;

    expect(rows(root, 'endgame')).toEqual([
      'matchRecordDetail.derived.teamA 5/11 45%',
      'matchRecordDetail.derived.teamB 6/11 55%',
    ]);
    expect(rows(root, 'deuce')).toEqual([
      'matchRecordDetail.derived.teamA 2/6 33%',
      'matchRecordDetail.derived.teamB 4/6 67%',
    ]);
    expect(root.querySelector('[data-fact="endgame"]')?.textContent).toContain(
      'matchRecordDetail.clutch.endgame',
    );
  });

  it('says the endgame does not apply instead of showing numbers (FR-010)', () => {
    const root: HTMLElement = setup({ ...wentToDeuce, endgame_from: null, endgame: null }).nativeElement;

    expect(rows(root, 'endgame')).toEqual(['matchRecordDetail.clutch.endgameNotApplicable']);
    expect(root.querySelector('[data-fact="endgame"]')?.textContent).toContain(
      'matchRecordDetail.clutch.endgameTitle',
    );
  });

  it('says the match never went to deuce instead of "0/0" (US1 scenario 3)', () => {
    const root: HTMLElement = setup({ ...wentToDeuce, deuce: null }).nativeElement;

    expect(rows(root, 'deuce')).toEqual(['matchRecordDetail.clutch.deuceNone']);
  });

  it('tells held-and-converted, held-but-not, and never-held apart', () => {
    const converted = rows(setup(wentToDeuce).nativeElement, 'match-points');
    expect(converted[0]).toContain('matchRecordDetail.clutch.matchPointsNotConverted');
    expect(converted[0]).not.toContain('matchPointsSaved'); // saved 0 is not worth a line
    expect(converted[1]).toContain('matchRecordDetail.clutch.matchPointsConverted');
    expect(converted[1]).toContain('matchRecordDetail.clutch.matchPointsSaved');

    TestBed.resetTestingModule();
    const neverHeld = rows(
      setup({
        ...wentToDeuce,
        match_points: [
          { team: 'A', held: 1, converted_on: 1, saved: 0 },
          { team: 'B', held: 0, converted_on: null, saved: 0 },
        ],
      }).nativeElement,
      'match-points',
    );
    expect(neverHeld[1]).toContain('matchRecordDetail.clutch.matchPointsNeverHeld');
    expect(neverHeld[1]).not.toContain('matchPointsNotConverted');
  });

  it('shows a never-occurred score state as "0/0 —", never 0% (FR-015)', () => {
    const table: HTMLElement = setup(wentToDeuce).nativeElement.querySelector('[data-table="by-state"]');
    const teamA = Array.from(table.querySelectorAll('tbody tr')[0].querySelectorAll('td')).map(
      (td) => td.textContent?.replace(/\s+/g, ' ').trim(),
    );

    expect(teamA).toEqual(['10/23 43%', '12/23 52%', '0/0 —']);
    expect(table.textContent).not.toContain('0%');
  });

  it('names the winner in the comeback line, or says they never trailed (FR-014)', () => {
    expect(rows(setup(wentToDeuce).nativeElement, 'comeback')).toEqual([
      'matchRecordDetail.clutch.comebackByB',
    ]);

    TestBed.resetTestingModule();
    expect(rows(setup({ ...wentToDeuce, comeback: null }).nativeElement, 'comeback')).toEqual([
      'matchRecordDetail.clutch.comebackNone',
    ]);
  });
});
