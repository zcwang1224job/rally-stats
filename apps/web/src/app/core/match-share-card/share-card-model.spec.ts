import { formatDate } from '@angular/common';
import { ShareCardContext } from './share-card.models';
import { buildShareCardModel } from './share-card-model';
import { buildScoreTrendPoints } from '../match-record-detail/score-trend';
import {
  makeDetail,
  makeNone,
  makePartial,
  makeSingles,
  withClutch,
  withTempo,
} from './testing/detail-fixtures';

const neutral: ShareCardContext = { groupName: '週三羽球團', perspective: { kind: 'neutral' } };

describe('buildShareCardModel — neutral perspective (040 US1)', () => {
  it('puts the winner first and badges it WIN, whichever side won', () => {
    const aWins = buildShareCardModel(makeDetail(), neutral);
    expect(aWins.teams.map((t) => t.team)).toEqual(['A', 'B']);

    const bWins = buildShareCardModel(
      makeDetail({ score_a: 18, score_b: 21, winner_team: 'B' }),
      neutral,
    );
    expect(bWins.teams.map((t) => t.team)).toEqual(['B', 'A']);
    expect(bWins.teams[0].badge).toBe('win');
    expect(bWins.teams[0].isWinner).toBe(true);
    expect(bWins.teams[1].badge).toBeNull();
    expect(bWins.teams[1].isWinner).toBe(false);
    expect(bWins.perspective).toBe('neutral');
  });

  it('keeps each team’s score and names together after reordering (FR-019)', () => {
    const model = buildShareCardModel(
      makeDetail({ score_a: 18, score_b: 21, winner_team: 'B' }),
      neutral,
    );

    expect(model.teams[0]).toEqual({
      team: 'B',
      nicknames: ['林小美', '張阿強'],
      score: 21,
      isWinner: true,
      badge: 'win',
    });
    expect(model.teams[1].nicknames).toEqual(['王小明', '陳大華']);
    expect(model.teams[1].score).toBe(18);
  });

  it('lists one name per side for singles and two for doubles, in detail order', () => {
    expect(buildShareCardModel(makeSingles(), neutral).teams[0].nicknames).toEqual(['王小明']);
    expect(buildShareCardModel(makeDetail(), neutral).teams[0].nicknames).toEqual([
      '王小明',
      '陳大華',
    ]);
  });

  it('computes the duration from start to end, and omits it when it can’t be trusted', () => {
    expect(buildShareCardModel(makeDetail(), neutral).durationSeconds).toBe(18 * 60 + 32);
    expect(buildShareCardModel(makeDetail({ ended_at: null }), neutral).durationSeconds).toBeNull();
    expect(buildShareCardModel(makeDetail({ started_at: null }), neutral).durationSeconds).toBeNull();
    expect(
      buildShareCardModel(
        makeDetail({ started_at: '2026-09-21T11:20:00Z', ended_at: '2026-09-21T11:00:00Z' }),
        neutral,
      ).durationSeconds,
    ).toBeNull();
  });

  it('names the file after the local start date and the first-then-second score', () => {
    const detail = makeDetail({ score_a: 18, score_b: 21, winner_team: 'B' });
    const date = formatDate(detail.started_at!, 'yyyyMMdd', 'en-US');

    expect(buildShareCardModel(detail, neutral).fileName).toBe(`rally-stats-${date}-21-18.png`);
    expect(buildShareCardModel(makeDetail({ started_at: null }), neutral).fileName).toBe(
      'rally-stats-21-17.png',
    );
  });

  it('describes the card for screen readers: both teams, both scores, the winner (FR-028)', () => {
    const model = buildShareCardModel(makeDetail(), neutral);

    expect(model.altText).toEqual({
      key: 'matchShareCard.altText',
      params: {
        first: '王小明、陳大華',
        firstScore: 21,
        second: '林小美、張阿強',
        secondScore: 17,
        winner: '王小明、陳大華',
      },
    });
  });

  it('carries the group name, round and start time through unchanged', () => {
    const model = buildShareCardModel(makeDetail(), neutral);

    expect(model.groupName).toBe('週三羽球團');
    expect(model.roundNumber).toBe(3);
    expect(model.startedAt).toBe('2026-09-21T11:02:10Z');
  });

  it('draws no trend, highlights or average per point from an incomplete record', () => {
    for (const detail of [makePartial(), makeNone()]) {
      const model = buildShareCardModel(detail, neutral);
      expect(model.trend).toBeNull();
      expect(model.highlights).toEqual([]);
      expect(model.averagePointSeconds).toBeNull();
    }
  });

  it('draws the trend exactly as the detail chart does, for a complete record (FR-007)', () => {
    const detail = makeDetail();

    expect(buildShareCardModel(detail, neutral).trend).toEqual(buildScoreTrendPoints(detail));
  });

  it('shows the same average per point as the detail’s tempo block (FR-008/FR-010)', () => {
    expect(buildShareCardModel(makeDetail({ tempo_stats: withTempo(29.4) }), neutral).averagePointSeconds).toBe(29.4);
    expect(buildShareCardModel(makeDetail({ tempo_stats: null }), neutral).averagePointSeconds).toBeNull();
  });

  it('picks highlights for the winner on a neutral card', () => {
    const model = buildShareCardModel(
      makeDetail({
        score_a: 18,
        score_b: 21,
        winner_team: 'B',
        clutch_stats: withClutch({ savedB: 1, savedA: 2 }),
      }),
      neutral,
    );

    expect(model.highlights).toEqual([{ kind: 'matchPointsSaved', count: 1 }]);
  });

  it('is deterministic: the same input gives an equal model (SC-007)', () => {
    expect(buildShareCardModel(makeDetail(), neutral)).toEqual(
      buildShareCardModel(makeDetail(), neutral),
    );
  });
});
