# Contract: 團圖卡模組與團戰績頁的接線（`apps/web/src/app/core/group-share-card/`）

**Feature**: 041-group-share-cards | 型別定義見 [data-model.md](../data-model.md) 第 3 節；決策依據見 [research.md](../research.md) Decision 3、7、11。

本模組只依賴 `core/share-card/`、`core/api/` 的回應型別、`core/match-record-detail/ratio-format.ts`（`formatPercent`）與 `shared/line-chart/line-chart-scale.ts`；**不得** import `core/match-share-card/` 或任何 `features/`。

---

## 1. 純函式（無 DOM、無翻譯）

```ts
interface GroupShareCardContext { createdAt: string | null }

buildLeaderboardCardModel(
  history: MemberGroupHistoryResponse,
  context: GroupShareCardContext,
): LeaderboardCardModel | null

buildMyStatsCardModel(
  history: MemberGroupHistoryResponse,
  context: GroupShareCardContext,
): MyStatsCardModel | null

availableGroupCards(
  history: MemberGroupHistoryResponse,
  context: GroupShareCardContext,
): ShareCardOption[]          // 固定順序：排行榜、我的成績；模型為 null 的不出現
```

### 排行榜卡的不變式（皆列為 spec 測試項）

| # | 不變式 | 對應需求 |
|---|---|---|
| L1 | `rows` 是 `final_standings` 濾掉 `total_matches === 0` 後的**前綴**（最多 6 列），相對順序與輸入完全相同——沒有任何排序呼叫 | FR-007、FR-008 |
| L2 | 每一列的 `rank` 等於來源列的 `rank`；並列（1、1、3）原樣保留 | FR-008 |
| L3 | `podium` 只依列的位置（前 3 列為 true），不依名次 | FR-007 |
| L4 | 本人 `total_matches ≥ 1` 且不在 `rows` 內 ⇒ `selfRow` 為本人那一列；其他情況 `selfRow === null` | FR-010 |
| L5 | `rows` 與 `selfRow` 以外的球員不出現在模型的任何欄位（含 `altText`） | FR-010、SC-004 |
| L6 | 模型不含 `current_status`、`roster_entry_id` 或任何 ID | FR-011、FR-021 |
| L7 | `playerCount` ＝ `total_matches ≥ 1` 的列數 | FR-006 |
| L8 | 沒有任何出賽球員 ⇒ 回傳 `null` | FR-005 |
| L9 | 同樣的輸入 ⇒ 深度相等的輸出 | SC-010 |

### 我的成績卡的不變式

| # | 不變式 | 對應需求 |
|---|---|---|
| M1 | `my_stats.total_matches === 0` ⇒ 回傳 `null` | FR-013 |
| M2 | `winRate === formatPercent(my_stats.win_rate)` | FR-017 |
| M3 | `standing` 取自 `is_self` 列；找不到 ⇒ `standing === null` 且 `nickname === null` | FR-014 |
| M4 | `round_win_rates.length < 2` ⇒ `trend === null`；否則點數等於輪數，縱軸範圍與頁面走勢圖相同 | FR-015 |
| M5 | `opponents` 是 `opponent_records` 的前綴（最多 3 筆），順序不變；不做任何挑選或排序 | FR-016 |
| M6 | `context.createdAt === null` ⇒ `date === null` | Edge Cases |

## 2. 繪製

```ts
renderLeaderboardCard(ctx: ShareCardCanvas, model: LeaderboardCardModel, env: ShareCardRenderEnv): void
renderMyStatsCard(ctx: ShareCardCanvas, model: MyStatsCardModel, env: ShareCardRenderEnv): void
```

兩者結構相同：背景 → 標題區（團名、日期・副標）→ `stackBlocks()` 排中段 → `drawPromoFooter(env.footer)`。

| 圖卡 | 標題區副標 | 中段區塊（由上而下） | 可收縮 |
|---|---|---|---|
| 排行榜 | 「排行榜」・日期・「N 位球員」 | 頒獎台 3 列（大字名次＋獎牌圈、暱稱、勝負）→ 一般列（第 4–6 列）→ 分隔符號＋本人列（有 `selfRow` 才有） | 無（最壞情況 7 列已在中段高度內） |
| 我的成績 | 「我的成績」・日期 | 暱稱＋大字勝率＋「W 勝 L 敗・共 N 場」→ 名次膠囊「第 N 名／共 M 人」→ 各輪走勢縮圖 → 最常交手（最多 3 列） | 走勢縮圖有 `minHeight` |

繪製約定：
- 「我」以文字標籤（`groupShareCard.selfTag`）呈現，另加底色；名次以數字呈現，獎牌只是裝飾（FR-009、FR-010）。
- 獎牌以 canvas 圖形（圓＋名次數字）繪製，不使用 emoji——各平台 emoji 字型不同，會讓同一張圖卡在不同裝置上長得不一樣。
- 暱稱、團名一律經 `truncateToWidth()`；勝負場數與名次欄位寬度固定，不因暱稱長度位移（SC-005）。
- 標題用語不含「最終」（FR-012）。
- 模型中為 `null`／空陣列的區塊不進入 `stackBlocks()`，沒有空框（FR-017）。

## 3. 團戰績頁的接線（`features/member/my-groups/group-history/`）

| 項目 | 約定 |
|---|---|
| 活動日期 | 初始化時另發一次 `FriendsService.getMyGroups()`，取該團的 `created_at` 存成 signal；失敗或找不到 → `null`。**不得**影響頁面既有的 loading／error 狀態 |
| 可用選項 | `computed(() => history() ? availableGroupCards(history()!, { createdAt: createdAt() }) : [])` |
| 按鈕 | 選項為空、頁面載入中或錯誤時**不顯示**（FR-001）；放在頁面標題旁，原生 `<button>`，文字 `groupShareCard.openButton` |
| 開啟 | `preview.open(options())`；頁面放一個 `<app-share-card-preview>` |
| 與既有功能的關係 | 對戰紀錄的篩選／分頁重新載入 `history()` 時，`final_standings` 與 `my_stats` 不受篩選影響，圖卡內容因此不變（規格 Edge Cases）；比賽詳情 dialog 既有的單場圖卡入口不動 |

授權：頁面能載入就能產生圖卡，沒有額外判斷（FR-028）。

## 4. 語系 key（`groupShareCard.*`）

`openButton`、`kind.leaderboard`、`kind.myStats`、`leaderboard.title`、`leaderboard.playerCount`（參數 `count`）、`leaderboard.record`（參數 `wins`、`losses`）、`leaderboard.altText`、`selfTag`、`myStats.title`、`myStats.record`（參數 `wins`、`losses`、`matches`）、`myStats.standing`（參數 `rank`、`count`）、`myStats.trendTitle`、`myStats.opponentsTitle`、`myStats.opponentRecord`（參數 `wins`、`losses`）、`myStats.altText`。

`zh-TW` 與 `en` 的 key 集合必須完全相同（以測試斷言）。
