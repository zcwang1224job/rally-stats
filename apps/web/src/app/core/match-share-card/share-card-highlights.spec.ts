import { MatchRecordDetailResponse } from '../api/group-member-view.models';
import { formatPercent } from '../match-record-detail/ratio-format';
import { highlightThreshold, pickHighlights } from './share-card-highlights';
import {
  makeDetail,
  makeNone,
  makePartial,
  withClutch,
  withEnding,
  withMomentum,
} from './testing/detail-fixtures';

/** A wins 21:17 by default (21-point match). */
function kinds(detail: MatchRecordDetailResponse, protagonist: 'A' | 'B' = 'A'): string[] {
  return pickHighlights(detail, protagonist).map((h) => h.kind);
}

describe('highlightThreshold (040 FR-012: max(3, floor(T × ratio)))', () => {
  it('scales comeback / run / margin by the points to win', () => {
    const at = (t: number) => [0.15, 0.25, 0.5].map((r) => highlightThreshold(t, r));

    expect(at(21)).toEqual([3, 5, 10]);
    expect(at(15)).toEqual([3, 3, 7]);
    expect(at(11)).toEqual([3, 3, 5]);
  });

  it('never goes below 3, so a short game doesn’t make every match a highlight', () => {
    expect(highlightThreshold(5, 0.15)).toBe(3);
    expect(highlightThreshold(5, 0.25)).toBe(3);
    expect(highlightThreshold(5, 0.5)).toBe(3);
  });
});

describe('pickHighlights — each candidate at its threshold (21-point)', () => {
  it('#1 comeback: from 3 down, not from 2', () => {
    expect(
      pickHighlights(makeDetail({ clutch_stats: withClutch({ comeback: { winner: 'A', maxDeficit: 3 } }) }), 'A'),
    ).toEqual([{ kind: 'comeback', deficit: 3 }]);
    expect(kinds(makeDetail({ clutch_stats: withClutch({ comeback: { winner: 'A', maxDeficit: 2 } }) }))).toEqual([]);
  });

  it('#2 match points saved: one or more of the opponent’s', () => {
    expect(pickHighlights(makeDetail({ clutch_stats: withClutch({ savedA: 1 }) }), 'A')).toEqual([
      { kind: 'matchPointsSaved', count: 1 },
    ]);
    expect(kinds(makeDetail({ clutch_stats: withClutch({ savedA: 0 }) }))).toEqual([]);
    // B's saves are B's, not A's.
    expect(kinds(makeDetail({ clutch_stats: withClutch({ savedB: 2 }) }))).toEqual([]);
  });

  it('#3 deuce win: reached deuce and the protagonist won, protagonist’s score first', () => {
    const deuce = makeDetail({ score_a: 22, score_b: 20, clutch_stats: withClutch({ deuce: true }) });

    expect(pickHighlights(deuce, 'A')).toEqual([{ kind: 'deuceWin', scoreFor: 22, scoreAgainst: 20 }]);
    expect(kinds(makeDetail({ clutch_stats: withClutch({ deuce: false }) }))).toEqual([]);
  });

  it('#4 run: 5 in a row, not 4', () => {
    expect(pickHighlights(makeDetail({ momentum_stats: withMomentum(5, 0) }), 'A')).toEqual([
      { kind: 'run', length: 5 },
    ]);
    expect(kinds(makeDetail({ momentum_stats: withMomentum(4, 0) }))).toEqual([]);
  });

  it('#5 winner rate: 50% of the protagonist’s points, with 80% of endings recorded', () => {
    // A scored 21: 11 winners = 52%, 10 = 48%.
    expect(pickHighlights(makeDetail({ ending_stats: withEnding(11, 0, 80, 100) }), 'A')).toEqual([
      { kind: 'winnerRate', percent: formatPercent(11 / 21) },
    ]);
    expect(kinds(makeDetail({ ending_stats: withEnding(10, 0, 80, 100) }))).toEqual([]);
    // 79% coverage is too thin to state a rate.
    expect(kinds(makeDetail({ ending_stats: withEnding(11, 0, 79, 100) }))).toEqual([]);
  });

  it('#5 winner rate: skipped when a side scored nothing, or no ending was recorded', () => {
    expect(kinds(makeDetail({ score_b: 0, ending_stats: withEnding(0, 0, 21, 21) }), 'B')).toEqual([]);
    expect(kinds(makeDetail({ ending_stats: null }))).toEqual([]);
  });

  it('#6 lead changes: 3, not 2', () => {
    expect(pickHighlights(makeDetail({ momentum_stats: withMomentum(0, 0, 3) }), 'A')).toEqual([
      { kind: 'leadChanges', count: 3 },
    ]);
    expect(kinds(makeDetail({ momentum_stats: withMomentum(0, 0, 2) }))).toEqual([]);
  });

  it('#7 big margin: by 10, not 9', () => {
    expect(pickHighlights(makeDetail({ score_a: 21, score_b: 11 }), 'A')).toEqual([
      { kind: 'bigMargin', margin: 10 },
    ]);
    expect(kinds(makeDetail({ score_a: 21, score_b: 12 }))).toEqual([]);
  });
});

describe('pickHighlights — scaled to shorter games', () => {
  it('in an 11-point match, a run of 3 counts and a run of 2 does not', () => {
    const eleven = (run: number) =>
      makeDetail({ target_score: 11, score_a: 11, score_b: 8, momentum_stats: withMomentum(run, 0) });

    expect(kinds(eleven(3))).toEqual(['run']);
    expect(kinds(eleven(2))).toEqual([]);
  });

  it('in an 11-point match, winning by 5 is a big margin', () => {
    expect(kinds(makeDetail({ target_score: 11, score_a: 11, score_b: 6 }))).toEqual(['bigMargin']);
    expect(kinds(makeDetail({ target_score: 11, score_a: 11, score_b: 7 }))).toEqual([]);
  });
});

describe('pickHighlights — choosing and ordering', () => {
  it('keeps the first three by priority when everything qualifies', () => {
    const everything = makeDetail({
      score_a: 22,
      score_b: 11,
      clutch_stats: withClutch({ comeback: { winner: 'A', maxDeficit: 5 }, savedA: 2, deuce: true }),
      momentum_stats: withMomentum(8, 0, 4),
      ending_stats: withEnding(20, 0, 33, 33),
    });

    expect(kinds(everything)).toEqual(['comeback', 'matchPointsSaved', 'deuceWin']);
  });

  it('keeps priority order among whatever qualifies', () => {
    const detail = makeDetail({ score_a: 21, score_b: 10, momentum_stats: withMomentum(6, 0, 3) });

    expect(kinds(detail)).toEqual(['run', 'leadChanges', 'bigMargin']);
  });

  it('only praises the protagonist even when it lost (FR-013)', () => {
    // A won 21:17; B is "my" side here.
    const detail = makeDetail({
      score_a: 21,
      score_b: 10,
      clutch_stats: withClutch({ comeback: { winner: 'A', maxDeficit: 5 }, savedB: 1, deuce: true }),
      momentum_stats: withMomentum(0, 6, 3),
      ending_stats: withEnding(0, 6, 31, 31),
    });

    const picked = kinds(detail, 'B');
    expect(picked).toEqual(['matchPointsSaved', 'run', 'winnerRate']);
    expect(picked).not.toContain('comeback');
    expect(picked).not.toContain('deuceWin');
    expect(picked).not.toContain('bigMargin');
  });

  it('lets the neutral lead-change highlight through for a losing protagonist', () => {
    expect(kinds(makeDetail({ momentum_stats: withMomentum(0, 0, 3) }), 'B')).toEqual(['leadChanges']);
  });

  it('gives nothing for an incomplete record, whatever the stats say (FR-011)', () => {
    const stats = {
      clutch_stats: withClutch({ savedA: 1 }),
      momentum_stats: withMomentum(8, 0, 5),
    };

    expect(pickHighlights(makePartial(stats), 'A')).toEqual([]);
    expect(pickHighlights(makeNone(stats), 'A')).toEqual([]);
  });

  it('is deterministic (FR-015)', () => {
    const detail = makeDetail({ momentum_stats: withMomentum(6, 0, 3), score_b: 10 });

    expect(pickHighlights(detail, 'A')).toEqual(pickHighlights(detail, 'A'));
  });
});
