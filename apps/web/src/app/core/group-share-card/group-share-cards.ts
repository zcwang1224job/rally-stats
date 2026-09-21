import { MemberGroupHistoryResponse } from '../api/friend.models';
import { ShareCardOption } from '../share-card/share-card-option';
import { GroupShareCardContext } from './group-share-card.models';
import { buildLeaderboardCardModel } from './leaderboard-card-model';
import { renderLeaderboardCard } from './leaderboard-card-renderer';
import { buildMyStatsCardModel } from './my-stats-card-model';
import { renderMyStatsCard } from './my-stats-card-renderer';

/** 041-group-share-cards contracts/group-share-card.md §1: the cards a
 * group's history can make right now, in a fixed order. A card whose data
 * isn't there is simply not offered — never an empty card (FR-001). */
export function availableGroupCards(
  history: MemberGroupHistoryResponse,
  context: GroupShareCardContext,
): ShareCardOption[] {
  const options: ShareCardOption[] = [];
  const leaderboard = buildLeaderboardCardModel(history, context);
  if (leaderboard) {
    options.push({
      source: 'card-rank',
      labelKey: 'groupShareCard.kind.leaderboard',
      fileName: leaderboard.fileName,
      altText: leaderboard.altText,
      draw: (ctx, env) => renderLeaderboardCard(ctx, leaderboard, env),
    });
  }
  const myStats = buildMyStatsCardModel(history, context);
  if (myStats) {
    options.push({
      source: 'card-me',
      labelKey: 'groupShareCard.kind.myStats',
      fileName: myStats.fileName,
      altText: myStats.altText,
      draw: (ctx, env) => renderMyStatsCard(ctx, myStats, env),
    });
  }
  return options;
}
