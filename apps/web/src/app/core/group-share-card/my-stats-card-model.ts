import { MemberGroupHistoryResponse } from '../api/friend.models';
import { formatPercent } from '../match-record-detail/ratio-format';
import { GroupShareCardContext, MyStatsCardModel } from './group-share-card.models';
import { countPlayers, groupCardFileName } from './leaderboard-card-model';

const TOP_OPPONENTS = 3;

/** 041-group-share-cards contracts/group-share-card.md §1 (M1–M6). Every
 * number is the page's own: the win rate goes through the page's percent
 * rule, the rank is the server's, the opponents keep the server's order
 * (most played first) — nothing is re-derived or re-picked (FR-016,
 * constitution X). Null when I haven't played here, so the card isn't
 * offered (FR-013). */
export function buildMyStatsCardModel(
  history: MemberGroupHistoryResponse,
  context: GroupShareCardContext,
): MyStatsCardModel | null {
  const stats = history.my_stats;
  if (stats.total_matches === 0) {
    return null;
  }
  const me = history.final_standings.find((row) => row.is_self) ?? null;
  const rounds = stats.round_win_rates;
  return {
    groupName: history.group_name,
    date: context.createdAt,
    activity: context.activity ?? null,
    nickname: me?.nickname ?? null,
    winRate: formatPercent(stats.win_rate),
    wins: stats.total_wins,
    losses: stats.total_losses,
    matches: stats.total_matches,
    standing: me ? { rank: me.rank, playerCount: countPlayers(history.final_standings) } : null,
    // The page draws this on a fixed 0–100% axis (round-trend-chart's
    // bounds), so the card does too: same data, same shape.
    trend:
      rounds.length >= 2
        ? rounds.map((round, index) => ({
            x: (index / (rounds.length - 1)) * 100,
            // 100 − rate × 100 rather than (1 − rate) × 100, which leaves
            // float dust (0.4 × 100 = 40.000…01).
            y: 100 - round.win_rate * 100,
          }))
        : null,
    opponents: stats.opponent_records
      .slice(0, TOP_OPPONENTS)
      .map(({ nickname, wins, losses }) => ({ nickname, wins, losses })),
    fileName: groupCardFileName('me', history.group_name, context.createdAt),
    altText: {
      key: 'groupShareCard.myStats.altText',
      params: {
        group: history.group_name,
        winRate: formatPercent(stats.win_rate),
        wins: stats.total_wins,
        losses: stats.total_losses,
      },
    },
  };
}
