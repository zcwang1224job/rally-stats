import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { MatchRecordDetailResponse } from '../api/group-member-view.models';
import {
  MatchRecordDetailDialogComponent,
  computeYTicks,
  nearestPointIndex,
  niceAxisStep,
} from './match-record-detail-dialog.component';

describe('niceAxisStep (dataviz skill, marks-and-anatomy.md)', () => {
  it('rounds to a clean 1/2/5-times-a-power-of-ten step', () => {
    expect(niceAxisStep(2)).toBe(1);
    expect(niceAxisStep(5)).toBe(2);
    expect(niceAxisStep(8)).toBe(2);
    expect(niceAxisStep(21)).toBe(10);
    expect(niceAxisStep(30)).toBe(10);
  });

  it('never returns a fractional step (scores are always whole numbers)', () => {
    expect(niceAxisStep(1)).toBe(1);
    expect(Number.isInteger(niceAxisStep(1))).toBe(true);
  });
});

describe('computeYTicks (dataviz skill, marks-and-anatomy.md)', () => {
  it('builds ticks from 0 to the max, at the nice step, top-to-bottom percent', () => {
    expect(computeYTicks(2)).toEqual([
      { value: 0, percent: 100 },
      { value: 1, percent: 50 },
      { value: 2, percent: 0 },
    ]);
  });

  it('never places a forced tick past the actual maximum', () => {
    const ticks = computeYTicks(21);
    expect(ticks.map((t) => t.value)).toEqual([0, 10, 20]);
    expect(ticks.every((t) => t.value <= 21)).toBe(true);
  });
});

describe('nearestPointIndex (dataviz skill, interaction.md)', () => {
  const points = [{ x: 0 }, { x: 33 }, { x: 67 }, { x: 100 }];

  it('snaps to the closest point by X position', () => {
    expect(nearestPointIndex(points, 0)).toBe(0);
    expect(nearestPointIndex(points, 40)).toBe(1);
    expect(nearestPointIndex(points, 60)).toBe(2);
    expect(nearestPointIndex(points, 100)).toBe(3);
  });

  it('returns index 0 for an empty-ish edge (single point)', () => {
    expect(nearestPointIndex([{ x: 50 }], 0)).toBe(0);
  });
});

const completeDetail: MatchRecordDetailResponse = {
  match_id: 'm1',
  round_number: 1,
  team_a: [{ roster_entry_id: 'p1', nickname: '小明', team: 'A' }],
  team_b: [{ roster_entry_id: 'p2', nickname: '小華', team: 'B' }],
  score_a: 2,
  score_b: 1,
  winner_team: 'A',
  started_at: '2026-01-01T10:00:00Z',
  ended_at: '2026-01-01T10:01:00Z',
  record_completeness: 'complete',
  events: [
    { side: 'A', delta: 1, score_a: 1, score_b: 0, elapsed_seconds: 10, detail: null },
    { side: 'B', delta: 1, score_a: 1, score_b: 1, elapsed_seconds: 20, detail: null },
    // a correction: A scores, then immediately gets deducted, illustrating
    // the trend chart MUST dip rather than only ever climb (FR-004).
    { side: 'A', delta: 1, score_a: 2, score_b: 1, elapsed_seconds: 25, detail: null },
    { side: 'A', delta: -1, score_a: 1, score_b: 1, elapsed_seconds: 28, detail: null },
    { side: 'A', delta: 1, score_a: 2, score_b: 1, elapsed_seconds: 30, detail: null },
  ],
  player_stats: [],
  serve_stats: null,
  momentum_stats: null,
  tempo_stats: null,
  landing_distribution: [],
  clutch_stats: null,
};

function setup(detail: MatchRecordDetailResponse | null, loading = false, loadError = false) {
  TestBed.configureTestingModule({
    imports: [MatchRecordDetailDialogComponent],
    providers: [provideTranslateService({})],
  });
  const fixture = TestBed.createComponent(MatchRecordDetailDialogComponent);
  fixture.componentRef.setInput('detail', detail);
  fixture.componentRef.setInput('loading', loading);
  fixture.componentRef.setInput('loadError', loadError);
  fixture.detectChanges();
  return fixture;
}

describe('MatchRecordDetailDialogComponent — event list (US1)', () => {
  it('renders every event, sorted by elapsed_seconds, with side/delta/score', () => {
    const fixture = setup(completeDetail);

    const rows = fixture.nativeElement.querySelectorAll('.event-row');
    expect(rows.length).toBe(completeDetail.events.length);
    const times = Array.from(rows).map((row) => (row as HTMLElement).textContent);
    // First row is the very first (elapsed 10s) event, last row the very
    // last (elapsed 30s) — i.e. already in ascending order as given.
    expect(times[0]).toContain('1 : 0');
    expect(times[times.length - 1]).toContain('2 : 1');
  });

  it('shows a deduction event (delta -1) alongside additions, not hidden', () => {
    const fixture = setup(completeDetail);

    const text = fixture.nativeElement.textContent as string;
    expect(text).toContain('matchRecordDetail.eventList.delta.minus');
    expect(text).toContain('matchRecordDetail.eventList.delta.plus');
  });

  it('marks each row with the scoring team’s color accent, matching its side', () => {
    const fixture = setup(completeDetail);

    const rows = fixture.nativeElement.querySelectorAll('.event-row');
    // completeDetail.events sides, in order: A, B, A, A, A.
    const expectedSides = completeDetail.events.map((e) => e.side);
    Array.from(rows).forEach((row, index) => {
      const el = row as HTMLElement;
      expect(el.classList.contains('event-row--a')).toBe(expectedSides[index] === 'A');
      expect(el.classList.contains('event-row--b')).toBe(expectedSides[index] === 'B');
    });
  });
});

describe('MatchRecordDetailDialogComponent — scoreboard-style header', () => {
  it('shows a team-colored dot beside each team’s names', () => {
    const fixture = setup(completeDetail);

    const dotA = fixture.nativeElement.querySelector('.basic-info__dot--a');
    const dotB = fixture.nativeElement.querySelector('.basic-info__dot--b');
    expect(dotA).not.toBeNull();
    expect(dotB).not.toBeNull();
  });

  it('gives the winning side’s score the winner modifier, not the losing side', () => {
    const fixture = setup(completeDetail); // winner_team: 'A'

    const values = fixture.nativeElement.querySelectorAll('.basic-info__score-value');
    expect(values.length).toBe(2);
    expect((values[0] as HTMLElement).classList.contains('basic-info__score-value--winner')).toBe(true);
    expect((values[1] as HTMLElement).classList.contains('basic-info__score-value--winner')).toBe(false);
    expect(values[0].textContent).toContain('2');
    expect(values[1].textContent).toContain('1');
  });

  it('shows the round label on its own line, still translated', () => {
    const fixture = setup(completeDetail);

    expect(fixture.nativeElement.querySelector('.basic-info__round')?.textContent).toContain(
      'groupMemberView.standings.roundColumnLabel',
    );
  });
});

describe('MatchRecordDetailDialogComponent — trend chart (US2)', () => {
  it("the chart's final point matches the match's real final score", () => {
    const fixture = setup(completeDetail);

    const points = fixture.componentInstance.chartPoints();
    expect(points).not.toBeNull();
    const last = points![points!.length - 1];
    // yA/yB are inverted (0 = highest score) on a 0..100 viewBox, scaled by
    // maxScore=2 here, so a final score of 2:1 means yA=0, yB=50.
    expect(last.yA).toBe(0);
    expect(last.yB).toBe(50);
  });

  it('a delta=-1 event produces an upward y-movement (score dip) on the A line', () => {
    const fixture = setup(completeDetail);

    const points = fixture.componentInstance.chartPoints()!;
    // Points order: [origin 0:0, 1:0, 1:1, 2:1, 1:1 (dip), 2:1]. The dip at
    // index 4 must have a HIGHER yA (lower score) than the point before it.
    expect(points[4].yA).toBeGreaterThan(points[3].yA);
  });

  it('prepends a synthetic 0:0 origin point when the record is complete', () => {
    const complete = setup(completeDetail);
    expect(complete.componentInstance.chartPoints()!.length).toBe(completeDetail.events.length + 1);
  });

  it('does NOT prepend a synthetic origin point when the record is partial', () => {
    const partialDetail: MatchRecordDetailResponse = {
      ...completeDetail,
      record_completeness: 'partial',
      events: completeDetail.events.slice(1), // first event no longer 1:0/0:1
    };
    const partial = setup(partialDetail);
    expect(partial.componentInstance.chartPoints()!.length).toBe(partialDetail.events.length);
  });

  // FR-008 / constitution VII: the two teams' lines MUST be distinguishable
  // by more than color alone.
  it('renders team A and B lines with different stroke-dasharray (not color-only)', () => {
    const fixture = setup(completeDetail);

    const lineA = fixture.nativeElement.querySelector('.trend-chart__line--a');
    const lineB = fixture.nativeElement.querySelector('.trend-chart__line--b');
    expect(lineA).not.toBeNull();
    expect(lineB).not.toBeNull();
    const dashA = getComputedStyle(lineA).strokeDasharray;
    const dashB = getComputedStyle(lineB).strokeDasharray;
    expect(dashA).not.toBe(dashB);
  });

  it('renders a text legend naming both teams, not just colored swatches', () => {
    const fixture = setup(completeDetail);

    const legendText = fixture.nativeElement.querySelector('.trend-legend').textContent as string;
    expect(legendText).toContain('小明');
    expect(legendText).toContain('小華');
  });
});

describe('MatchRecordDetailDialogComponent — Y-axis ticks (dataviz polish)', () => {
  it('renders clean round-number ticks scaled to the final score (maxScore=2 -> 0/1/2)', () => {
    const fixture = setup(completeDetail);

    const labels = Array.from(
      fixture.nativeElement.querySelectorAll('.trend-chart__y-axis-label'),
    ).map((el) => (el as HTMLElement).textContent);
    expect(labels).toEqual(['0', '1', '2']);
    // Same number of gridlines as ticks, one per label.
    expect(fixture.nativeElement.querySelectorAll('.trend-chart__gridline').length).toBe(3);
  });

  it('picks a coarser step for a larger score range (maxScore=21 -> 0/10/20)', () => {
    const fixture = setup({
      ...completeDetail,
      score_a: 21,
      score_b: 15,
      events: [{ side: 'A', delta: 1, score_a: 21, score_b: 15, elapsed_seconds: 600, detail: null }],
    });

    const labels = Array.from(
      fixture.nativeElement.querySelectorAll('.trend-chart__y-axis-label'),
    ).map((el) => (el as HTMLElement).textContent);
    expect(labels).toEqual(['0', '10', '20']);
  });

  it('never renders ticks/gridlines when there is no chart at all', () => {
    const fixture = setup({ ...completeDetail, record_completeness: 'none', events: [] });

    expect(fixture.nativeElement.querySelector('.trend-chart__y-axis-label')).toBeNull();
    expect(fixture.nativeElement.querySelector('.trend-chart__gridline')).toBeNull();
  });
});

describe('MatchRecordDetailDialogComponent — chart hover readout (dataviz polish)', () => {
  function stubPlotWidth(fixture: ReturnType<typeof setup>, width: number): void {
    const plot: HTMLElement = fixture.nativeElement.querySelector('.trend-chart__plot');
    vi.spyOn(plot, 'getBoundingClientRect').mockReturnValue({
      left: 0,
      width,
      top: 0,
      height: 140,
      right: width,
      bottom: 140,
      x: 0,
      y: 0,
      toJSON: () => ({}),
    });
  }

  function pointerMoveAt(fixture: ReturnType<typeof setup>, clientX: number): void {
    const plot: HTMLElement = fixture.nativeElement.querySelector('.trend-chart__plot');
    plot.dispatchEvent(new PointerEvent('pointermove', { clientX }));
    fixture.detectChanges();
  }

  it('shows a hint and no crosshair before any hover/touch', () => {
    const fixture = setup(completeDetail);

    expect(fixture.nativeElement.textContent).toContain('matchRecordDetail.chart.hoverHint');
    expect(fixture.nativeElement.querySelector('.trend-chart__crosshair')).toBeNull();
  });

  it('hovering near a point reveals its elapsed time and both scores, and a crosshair', () => {
    const fixture = setup(completeDetail);
    stubPlotWidth(fixture, 100);

    // Points (maxElapsed=30s): x = elapsed/30*100 -> [0, 33.3, 66.7, 83.3, 93.3, 100].
    // clientX=100 (with a 100-wide stubbed rect) is nearest the LAST point
    // (elapsed 30s, score 2:1).
    pointerMoveAt(fixture, 100);

    const readout = fixture.nativeElement.querySelector('.trend-chart__readout').textContent as string;
    expect(readout).not.toContain('matchRecordDetail.chart.hoverHint');
    expect(readout).toContain('2');
    expect(readout).toContain('1');
    expect(fixture.nativeElement.querySelector('.trend-chart__crosshair')).not.toBeNull();
    expect(fixture.componentInstance.hoveredIndex()).toBe(5);
  });

  it('the hovered point’s markers grow to meet the >= 8px minimum; resting points stay small', () => {
    const fixture = setup(completeDetail);
    stubPlotWidth(fixture, 100);
    pointerMoveAt(fixture, 100);

    expect(fixture.componentInstance.dotRadius(5) * 2).toBeGreaterThanOrEqual(8);
    expect(fixture.componentInstance.dotRadius(0)).toBeLessThan(fixture.componentInstance.dotRadius(5));
    const hoveredDot = fixture.nativeElement.querySelector('.trend-chart__dot--hovered');
    expect(hoveredDot).not.toBeNull();
  });

  it('leaving the chart hides the readout and crosshair again', () => {
    const fixture = setup(completeDetail);
    stubPlotWidth(fixture, 100);
    pointerMoveAt(fixture, 100);

    const plot: HTMLElement = fixture.nativeElement.querySelector('.trend-chart__plot');
    plot.dispatchEvent(new PointerEvent('pointerleave'));
    fixture.detectChanges();

    expect(fixture.componentInstance.hoveredIndex()).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('matchRecordDetail.chart.hoverHint');
    expect(fixture.nativeElement.querySelector('.trend-chart__crosshair')).toBeNull();
  });

  it('resets the hover state when the detail changes to a different match', () => {
    const fixture = setup(completeDetail);
    stubPlotWidth(fixture, 100);
    pointerMoveAt(fixture, 100);
    expect(fixture.componentInstance.hoveredIndex()).not.toBeNull();

    fixture.componentRef.setInput('detail', { ...completeDetail, match_id: 'm2' });
    fixture.detectChanges();

    expect(fixture.componentInstance.hoveredIndex()).toBeNull();
  });
});

describe('MatchRecordDetailDialogComponent — completeness states (US3)', () => {
  it('shows an empty-state message and no chart/list when record_completeness is "none"', () => {
    const noneDetail: MatchRecordDetailResponse = {
      ...completeDetail,
      record_completeness: 'none',
      events: [],
    };
    const fixture = setup(noneDetail);

    expect(fixture.nativeElement.querySelector('.completeness-note')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('.trend-chart')).toBeNull();
    expect(fixture.nativeElement.querySelector('.event-row')).toBeNull();
    // Basic info (FR-007) still shows even with no history.
    expect(fixture.nativeElement.textContent).toContain('2');
    expect(fixture.nativeElement.textContent).toContain('1');
    expect(fixture.nativeElement.querySelector('.basic-info__score')).not.toBeNull();
  });

  it('shows the existing list/chart plus an incompleteness banner when "partial"', () => {
    const partialDetail: MatchRecordDetailResponse = {
      ...completeDetail,
      record_completeness: 'partial',
      events: completeDetail.events.slice(1),
    };
    const fixture = setup(partialDetail);

    const banner = fixture.nativeElement.querySelector('.completeness-note--partial');
    expect(banner).not.toBeNull();
    expect(fixture.nativeElement.querySelector('.trend-chart')).not.toBeNull();
    expect(fixture.nativeElement.querySelectorAll('.event-row').length).toBe(
      partialDetail.events.length,
    );
  });

  it('shows a loading message while loading', () => {
    const fixture = setup(null, true, false);
    expect(fixture.nativeElement.textContent).toContain('matchRecordDetail.loading');
  });

  it('shows an error message when loading failed', () => {
    const fixture = setup(null, false, true);
    const alert = fixture.nativeElement.querySelector('[role="alert"]');
    expect(alert).not.toBeNull();
    expect(alert.textContent).toContain('matchRecordDetail.loadError');
  });

  // 032-match-record-scoring-stats US1
  it('shows both scoring and losing player badges when both are recorded', () => {
    const detail: MatchRecordDetailResponse = {
      ...completeDetail,
      events: [
        {
          side: 'A', delta: 1, score_a: 1, score_b: 0, elapsed_seconds: 10,
          detail: {
            scoring_roster_entry_id: 'p1', scoring_nickname: '小明',
            losing_roster_entry_id: 'p2', losing_nickname: '小華',
            landing_x: 0.6, landing_y: 0.2,
          },
        },
      ],
    };
    const fixture = setup(detail);

    const row = fixture.nativeElement.querySelector('.event-row');
    const badges = row.querySelectorAll('.event-row__player');
    expect(badges.length).toBe(2);
    expect(row.textContent).toContain('小明');
    expect(row.textContent).toContain('小華');
  });

  it('shows only the recorded player badge when just one side was picked', () => {
    const detail: MatchRecordDetailResponse = {
      ...completeDetail,
      events: [
        {
          side: 'A', delta: 1, score_a: 1, score_b: 0, elapsed_seconds: 10,
          detail: {
            scoring_roster_entry_id: 'p1', scoring_nickname: '小明',
            losing_roster_entry_id: null, losing_nickname: null,
            landing_x: null, landing_y: null,
          },
        },
      ],
    };
    const fixture = setup(detail);

    const row = fixture.nativeElement.querySelector('.event-row');
    const badges = row.querySelectorAll('.event-row__player');
    expect(badges.length).toBe(1);
    expect(row.textContent).toContain('小明');
  });

  it('shows no player badge when the event has no detail at all', () => {
    const fixture = setup({
      ...completeDetail,
      events: [{ side: 'A', delta: 1, score_a: 1, score_b: 0, elapsed_seconds: 10, detail: null }],
    });

    const row = fixture.nativeElement.querySelector('.event-row');
    expect(row.querySelectorAll('.event-row__player').length).toBe(0);
  });

  // 025-delete-account follow-up
  it('shows a deleted participant\'s placeholder nickname muted in the header', () => {
    const fixture = setup({
      ...completeDetail,
      team_a: [{ roster_entry_id: 'p1', nickname: 'Deleted User', team: 'A' }],
    });

    const basicInfo = fixture.nativeElement.querySelector('.basic-info') as HTMLElement;
    const deletedSpan = basicInfo.querySelector('.nickname--deleted') as HTMLElement | null;
    expect(deletedSpan).not.toBeNull();
    expect(deletedSpan?.textContent).toContain('Deleted User');
    const realSpan = Array.from<HTMLElement>(basicInfo.querySelectorAll('.nickname')).find((el) =>
      el.textContent?.includes('小華'),
    );
    expect(realSpan?.classList.contains('nickname--deleted')).toBe(false);
  });
});

describe('MatchRecordDetailDialogComponent — landing detail expand/collapse (US2)', () => {
  const withDetail: MatchRecordDetailResponse = {
    ...completeDetail,
    events: [
      {
        side: 'A', delta: 1, score_a: 1, score_b: 0, elapsed_seconds: 10,
        detail: {
          scoring_roster_entry_id: 'p1', scoring_nickname: '小明',
          losing_roster_entry_id: 'p2', losing_nickname: '小華',
          landing_x: 0.6, landing_y: 0.2,
        },
      },
      {
        side: 'A', delta: 1, score_a: 2, score_b: 0, elapsed_seconds: 20,
        detail: {
          scoring_roster_entry_id: 'p1', scoring_nickname: '小明',
          losing_roster_entry_id: null, losing_nickname: null,
          landing_x: null, landing_y: null,
        },
      },
      { side: 'B', delta: 1, score_a: 2, score_b: 1, elapsed_seconds: 30, detail: null },
    ],
  };

  it('expands a court diagram under a row with detail when clicked', () => {
    const fixture = setup(withDetail);
    const rows = fixture.nativeElement.querySelectorAll('.event-row');

    (rows[0] as HTMLElement).click();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('app-court-diagram')).not.toBeNull();
    expect(fixture.nativeElement.querySelector('.landing-not-recorded')).toBeNull();
  });

  it('collapses the row when clicked again', () => {
    const fixture = setup(withDetail);
    const rows = fixture.nativeElement.querySelectorAll('.event-row');

    (rows[0] as HTMLElement).click();
    fixture.detectChanges();
    (rows[0] as HTMLElement).click();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('app-court-diagram')).toBeNull();
  });

  it('switches the expanded row when a different one with detail is clicked, keeping at most one open', () => {
    const bothHaveLanding: MatchRecordDetailResponse = {
      ...withDetail,
      events: [
        withDetail.events[0],
        { ...withDetail.events[1], detail: { ...withDetail.events[1].detail!, landing_x: 0.3, landing_y: 0.4 } },
        withDetail.events[2],
      ],
    };
    const fixture = setup(bothHaveLanding);

    (fixture.nativeElement.querySelectorAll('.event-row')[0] as HTMLElement).click();
    fixture.detectChanges();
    (fixture.nativeElement.querySelectorAll('.event-row')[1] as HTMLElement).click();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelectorAll('app-court-diagram').length).toBe(1);
    expect(fixture.componentInstance.expandedEventIndex()).toBe(1);
  });

  it('shows "not recorded" instead of a court diagram when detail has no landing coordinates', () => {
    const fixture = setup(withDetail);
    const rows = fixture.nativeElement.querySelectorAll('.event-row');

    (rows[1] as HTMLElement).click();
    fixture.detectChanges();

    expect(fixture.nativeElement.querySelector('app-court-diagram')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('matchRecordDetail.eventList.landingNotRecorded');
  });

  it('does nothing when a row with no detail is clicked', () => {
    const fixture = setup(withDetail);
    const rows = fixture.nativeElement.querySelectorAll('.event-row');

    (rows[2] as HTMLElement).click();
    fixture.detectChanges();

    expect(fixture.componentInstance.expandedEventIndex()).toBeNull();
    expect(fixture.nativeElement.querySelector('app-court-diagram')).toBeNull();
  });

  it('resets the expanded row when a different match detail is provided', () => {
    const fixture = setup(withDetail);
    const rows = fixture.nativeElement.querySelectorAll('.event-row');
    (rows[0] as HTMLElement).click();
    fixture.detectChanges();
    expect(fixture.componentInstance.expandedEventIndex()).toBe(0);

    fixture.componentRef.setInput('detail', { ...withDetail, match_id: 'm2' });
    fixture.detectChanges();

    expect(fixture.componentInstance.expandedEventIndex()).toBeNull();
  });
});

describe('MatchRecordDetailDialogComponent — player scoring stats (US3)', () => {
  it('renders every player with their scored/fault counts when player_stats is non-empty', () => {
    const detail: MatchRecordDetailResponse = {
      ...completeDetail,
      team_a: [{ roster_entry_id: 'p1', nickname: '小明', team: 'A' }],
      team_b: [{ roster_entry_id: 'p2', nickname: '小華', team: 'B' }],
      player_stats: [
        { roster_entry_id: 'p1', nickname: '小明', team: 'A', scored_count: 3, fault_count: 1 },
        { roster_entry_id: 'p2', nickname: '小華', team: 'B', scored_count: 0, fault_count: 2 },
      ],
    };
    const fixture = setup(detail);

    const rows = fixture.nativeElement.querySelectorAll('.player-stat-row');
    expect(rows.length).toBe(2);
    expect(fixture.nativeElement.textContent).toContain('小明');
    expect(fixture.nativeElement.textContent).toContain('小華');
    expect(fixture.nativeElement.textContent).toContain('3');
    // the zero-count player MUST still be shown, not omitted.
    expect(rows[1].textContent).toContain('0');
    expect(rows[0].classList.contains('player-stat-row--a')).toBe(true);
    expect(rows[1].classList.contains('player-stat-row--b')).toBe(true);
  });

  it('shows an empty-state message instead of a stats table when player_stats is empty', () => {
    const fixture = setup({ ...completeDetail, player_stats: [] });

    expect(fixture.nativeElement.querySelectorAll('.player-stat-row').length).toBe(0);
    expect(fixture.nativeElement.textContent).toContain('matchRecordDetail.playerStats.empty');
  });
});

describe('MatchRecordDetailDialogComponent — derived stats (033)', () => {
  it('mounts the derived-stats blocks after the existing content', () => {
    const root: HTMLElement = setup(completeDetail).nativeElement;

    const derived = root.querySelector('app-match-derived-stats');
    expect(derived).not.toBeNull();
    const playerStats = root.querySelector('.player-stats-card')!;
    expect(
      playerStats.compareDocumentPosition(derived!) & Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy();
  });

  it('does not mount them when the match has no point-by-point record at all', () => {
    const root: HTMLElement = setup({
      ...completeDetail,
      record_completeness: 'none',
      events: [],
    }).nativeElement;

    expect(root.querySelector('app-match-derived-stats')).toBeNull();
  });
});

describe('MatchRecordDetailDialogComponent — collapsible sections', () => {
  it('renders the chart, event list, and player stats as native <details>, collapsed by default', () => {
    const root: HTMLElement = setup(completeDetail).nativeElement;

    const chart = root.querySelector('details.chart-card') as HTMLDetailsElement;
    const eventList = root.querySelector('details.event-list') as HTMLDetailsElement;
    const playerStats = root.querySelector('details.player-stats-card') as HTMLDetailsElement;
    expect(chart?.open).toBe(false);
    expect(eventList?.open).toBe(false);
    expect(playerStats?.open).toBe(false);
    // A <summary> replaces the old plain heading so each section has its
    // own native disclosure toggle.
    expect(chart.querySelector('summary')?.textContent).toContain('matchRecordDetail.chart.title');
    expect(eventList.querySelector('summary')?.textContent).toContain(
      'matchRecordDetail.eventList.title',
    );
    expect(playerStats.querySelector('summary')?.textContent).toContain(
      'matchRecordDetail.playerStats.title',
    );
  });

  it('expanding a section reveals its content without affecting the others', () => {
    const fixture = setup(completeDetail);
    const root: HTMLElement = fixture.nativeElement;
    const chart = root.querySelector('details.chart-card') as HTMLDetailsElement;
    const eventList = root.querySelector('details.event-list') as HTMLDetailsElement;

    eventList.open = true;
    eventList.dispatchEvent(new Event('toggle'));
    fixture.detectChanges();

    expect(chart.open).toBe(false);
    expect(eventList.open).toBe(true);
    expect(root.querySelectorAll('.event-row').length).toBe(completeDetail.events.length);
  });
});
