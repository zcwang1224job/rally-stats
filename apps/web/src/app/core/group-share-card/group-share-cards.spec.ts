import { SHARE_PALETTES } from '../share-card/share-card-palette';
import { testFooter } from '../share-card/testing/footer-ops';
import { RecordingContext } from '../share-card/testing/recording-context';
import { availableGroupCards } from './group-share-cards';
import { buildLeaderboardCardModel } from './leaderboard-card-model';
import { CREATED_AT, makeHistory, makeStandings } from './testing/history-fixtures';

const context = { createdAt: CREATED_AT };

describe('availableGroupCards — the leaderboard (041 US1, FR-001, FR-005)', () => {
  it('offers the leaderboard first, built from the standings', () => {
    const history = makeHistory();
    const [first] = availableGroupCards(history, context);
    const model = buildLeaderboardCardModel(history, context)!;

    expect(first.source).toBe('card-rank');
    expect(first.labelKey).toBe('groupShareCard.kind.leaderboard');
    expect(first.fileName).toBe(model.fileName);
    expect(first.altText).toEqual(model.altText);
  });

  it('offers nothing when nobody in the group has played', () => {
    const history = makeHistory({
      final_standings: makeStandings(3, { noMatchesAt: [0, 1, 2] }),
      my_stats: { ...makeHistory().my_stats, total_matches: 0, total_wins: 0, total_losses: 0 },
    });

    expect(availableGroupCards(history, context)).toEqual([]);
  });

  it('offers my stats second when I have played (041 US3, FR-003, FR-013)', () => {
    const options = availableGroupCards(makeHistory(), context);

    expect(options.map((o) => o.source)).toEqual(['card-rank', 'card-me']);
    expect(options[1].labelKey).toBe('groupShareCard.kind.myStats');
    expect(options[1].fileName).toBe('rally-stats-me-20260916-週三羽球團.png');
  });

  it('offers only the leaderboard when I have not played', () => {
    const history = makeHistory({
      my_stats: { ...makeHistory().my_stats, total_matches: 0, total_wins: 0, total_losses: 0, win_rate: 0 },
    });

    expect(availableGroupCards(history, context).map((o) => o.source)).toEqual(['card-rank']);
  });

  it('draws the leaderboard when asked', () => {
    const [first] = availableGroupCards(makeHistory(), context);
    const ctx = new RecordingContext();

    first.draw(ctx, {
      palette: SHARE_PALETTES.light,
      text: (key) => key,
      fonts: { base: 'sans-serif', score: 'monospace' },
      footer: testFooter(),
    });

    expect(ctx.texts()).toContain('週三羽球團');
  });
});
