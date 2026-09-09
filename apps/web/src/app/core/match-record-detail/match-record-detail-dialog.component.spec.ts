import { TestBed } from '@angular/core/testing';
import { provideTranslateService } from '@ngx-translate/core';
import { MatchRecordDetailResponse } from '../api/group-member-view.models';
import { MatchRecordDetailDialogComponent } from './match-record-detail-dialog.component';

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
    { side: 'A', delta: 1, score_a: 1, score_b: 0, elapsed_seconds: 10 },
    { side: 'B', delta: 1, score_a: 1, score_b: 1, elapsed_seconds: 20 },
    // a correction: A scores, then immediately gets deducted, illustrating
    // the trend chart MUST dip rather than only ever climb (FR-004).
    { side: 'A', delta: 1, score_a: 2, score_b: 1, elapsed_seconds: 25 },
    { side: 'A', delta: -1, score_a: 1, score_b: 1, elapsed_seconds: 28 },
    { side: 'A', delta: 1, score_a: 2, score_b: 1, elapsed_seconds: 30 },
  ],
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
    expect(fixture.nativeElement.textContent).toContain('2 : 1');
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
});
