import { makeDetail, makePartial } from '../match-share-card/testing/detail-fixtures';
import { buildScoreTrendPoints } from './score-trend';

describe('buildScoreTrendPoints (016 trend chart, shared with the 040 share card)', () => {
  it('returns null when there are no events', () => {
    expect(buildScoreTrendPoints(makeDetail({ record_completeness: 'none', events: [] }))).toBeNull();
  });

  it('prepends a 0:0 origin at elapsed 0 for a complete record', () => {
    const points = buildScoreTrendPoints(
      makeDetail({
        score_a: 2,
        score_b: 1,
        events: [
          { side: 'A', delta: 1, score_a: 1, score_b: 0, elapsed_seconds: 10, detail: null },
          { side: 'B', delta: 1, score_a: 1, score_b: 1, elapsed_seconds: 20, detail: null },
          { side: 'A', delta: 1, score_a: 2, score_b: 1, elapsed_seconds: 40, detail: null },
        ],
      }),
    )!;

    expect(points.length).toBe(4);
    expect(points[0]).toEqual({ x: 0, yA: 100, yB: 100, elapsedSeconds: 0, scoreA: 0, scoreB: 0 });
    expect(points[3]).toEqual({ x: 100, yA: 0, yB: 50, elapsedSeconds: 40, scoreA: 2, scoreB: 1 });
    expect(points[1].x).toBe(25);
  });

  it('does not invent an origin for a partial record', () => {
    const points = buildScoreTrendPoints(makePartial())!;

    expect(points.length).toBe(2);
    expect(points[0].scoreA).toBe(12);
  });

  it('keeps a -1 correction as its own point, so the line dips', () => {
    const points = buildScoreTrendPoints(
      makeDetail({
        score_a: 1,
        score_b: 0,
        events: [
          { side: 'A', delta: 1, score_a: 1, score_b: 0, elapsed_seconds: 5, detail: null },
          { side: 'A', delta: 1, score_a: 2, score_b: 0, elapsed_seconds: 8, detail: null },
          { side: 'A', delta: -1, score_a: 1, score_b: 0, elapsed_seconds: 9, detail: null },
        ],
      }),
    )!;

    expect(points.map((p) => p.scoreA)).toEqual([0, 1, 2, 1]);
  });

  it('never divides by zero when every event is at elapsed 0 and the score is 0', () => {
    const points = buildScoreTrendPoints(
      makeDetail({
        record_completeness: 'partial',
        score_a: 0,
        score_b: 0,
        events: [{ side: 'A', delta: -1, score_a: 0, score_b: 0, elapsed_seconds: 0, detail: null }],
      }),
    )!;

    expect(points[0]).toEqual({ x: 0, yA: 100, yB: 100, elapsedSeconds: 0, scoreA: 0, scoreB: 0 });
  });
});
