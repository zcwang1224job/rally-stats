# Contract: 團圖卡模組與團戰績頁的接線（`apps/web/src/app/core/group-share-card/`）

**Feature**: 041-group-share-cards | 型別定義見 [data-model.md](../data-model.md) 第 3 節；決策依據見 [research.md](../research.md) Decision 3、7、11。

本模組只依賴 `core/share-card/`、`core/api/` 的回應型別與 `core/match-record-detail/ratio-format.ts`（`formatPercent`）；**不得** import `core/match-share-card/` 或任何 `features/`。

---

## 1. 純函式（無 DOM、無翻譯）

```ts
interface GroupShareCardContext { createdAt: string | null }

buildLeaderboardCardModel(
  history: MemberGroupHistoryResponse,
  context: GroupShareCardContext,
): LeaderboardCardModel | null

countPlayers(standings: readonly FinalStandingRow[]): number   // 有出賽的列數；兩張卡共用

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
| L7 | `playerCount` ＝ `countPlayers(final_standings)` | FR-006 |
| L8 | 沒有任何出賽球員 ⇒ 回傳 `null` | FR-005 |
| L9 | 同樣的輸入 ⇒ 深度相等的輸出 | SC-010 |
| L10 | `altText` 依 `rows` 列數選用 `leaderboard.altText1／2／3`，參數 `rankN` 為伺服器名次、`nameN` 為暱稱；不出現空字串參數 | FR-031、FR-008 |

### 我的成績卡的不變式

| # | 不變式 | 對應需求 |
|---|---|---|
| M1 | `my_stats.total_matches === 0` ⇒ 回傳 `null` | FR-013 |
| M2 | `winRate === formatPercent(my_stats.win_rate)` | FR-017 |
| M3 | `standing` 取自 `is_self` 列與 `countPlayers()`；找不到本人列 ⇒ `standing === null` 且 `nickname === null` | FR-014 |
| M4 | `round_win_rates.length < 2` ⇒ `trend === null`；否則點數等於輪數，`x = i / (n − 1) × 100`、`y = (1 − win_rate) × 100`——與團戰績頁 `round-trend-chart` 相同的**固定 0～100% 縱軸** | FR-015 |
| M5 | `opponents` 是 `opponent_records` 的前綴（最多 3 筆），順序不變；不做任何挑選或排序 | FR-016 |
| M6 | `context.createdAt === null` ⇒ `date === null` | Edge Cases |

## 2. 繪製

```ts
renderLeaderboardCard(ctx: ShareCardCanvas, model: LeaderboardCardModel, env: ShareCardRenderEnv): void
renderMyStatsCard(ctx: ShareCardCanvas, model: MyStatsCardModel, env: ShareCardRenderEnv): void
```

兩者結構相同：背景 → 標題區（團名 bold 44px 於 y = 72；副標 30px 於 y = 136）→ `stackBlocks()` 排中段 → `drawPromoFooter(ctx, env.footer, env)`。

**排行榜卡中段**（區塊內各列之間不另加間距）：

| 區塊 | 高度 | 內容 | 收縮 |
|---|---|---|---|
| 頒獎台 | 列數 × 120（1～3 列） | 獎牌圓（半徑 36）＋名次數字、暱稱 bold 44px、勝負 30px | 不收縮 |
| 一般列 | 列數 × 76（0～3 列，0 列時整塊省略） | 名次數字（名次 ≤ 3 時也有獎牌圓）、暱稱 36px、勝負 30px | 不收縮 |
| 本人附列 | 116（分隔符號「⋯」40＋一列 76） | 只在 `selfRow` 不為 `null` 時存在 | 不收縮 |

最壞情況 360 + 228 + 116 = 704；加兩個 48 間距為 800，超過 US2 後的可用高度 786，因此只有**間距**縮為 41，區塊高度不變。

**我的成績卡中段**：

| 區塊 | 高度 | 內容 | 收縮 |
|---|---|---|---|
| 主視覺 | 232 | 暱稱 bold 40px（行高 52，`nickname === null` 時此行省略、高度減 52）、勝率 `env.fonts.score` 140px（行高 150）、勝負總場數 30px（行高 30） | 不收縮 |
| 名次膠囊 | 56 | `myStats.standing`，`palette.panel` 底色 | 不收縮；`standing === null` 時省略 |
| 各輪走勢 | 220 | 小標 30px＋單一折線（`palette.trendA`，縱軸固定 0～100%） | `minHeight: 140`；`trend === null` 時省略 |
| 最常交手 | 40 + 列數 × 56 | 小標＋每位對手的暱稱與勝負 | 不收縮；`opponents` 為空時省略 |

最壞情況（全部區塊、3 位對手）：232 + 56 + 220 + 208 = 716，三個間距 48 時為 860；間距縮為 32 後 812，仍超過 786，走勢收縮 26 至 194。只有 1 位對手時為 604 + 96 = 700，不收縮。

繪製約定：
- 「我」以文字標籤（`groupShareCard.selfTag`）呈現：本人列以 `palette.panel` 為列底色，標籤用 `pill`（`palette.badgeBackground`）＋文字（`palette.badgeText`），兩者都沿用 040 已驗證對比的色盤欄位（FR-009、FR-010）。
- 獎牌以 canvas 圖形（圓＋名次數字）繪製，不使用 emoji——各平台 emoji 字型不同，會讓同一張圖卡在不同裝置上長得不一樣。獎牌色是排行榜專用，定義在本模組的 `group-share-card-palette.ts`：`MEDAL_COLORS = { 1: '#FCD34D', 2: '#D1D5DB', 3: '#F4B183' }`、`MEDAL_TEXT = '#111827'`，兩種配色相同，名次數字與底色的對比皆 ≥ 4.5:1（以測試斷言）。
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
| 關閉 | 不重新載入頁面資料；對戰紀錄的篩選表單與目前頁碼維持不變（FR-002） |
| 與既有功能的關係 | 對戰紀錄的篩選／分頁重新載入 `history()` 時，`final_standings` 與 `my_stats` 不受篩選影響，圖卡內容因此不變（規格 Edge Cases）；比賽詳情 dialog 既有的單場圖卡入口與 `shareContext` 不動 |

授權：頁面能載入就能產生圖卡，沒有額外判斷（FR-028）。

## 4. 語系 key（`groupShareCard.*`）

`openButton`、`kind.leaderboard`、`kind.myStats`、`leaderboard.title`、`leaderboard.playerCount`（參數 `count`）、`leaderboard.record`（參數 `wins`、`losses`）、`leaderboard.altText1`（參數 `group`、`rank1`、`name1`）、`leaderboard.altText2`（再加 `rank2`、`name2`）、`leaderboard.altText3`（再加 `rank3`、`name3`）、`selfTag`、`myStats.title`、`myStats.record`（參數 `wins`、`losses`、`matches`）、`myStats.standing`（參數 `rank`、`count`）、`myStats.trendTitle`、`myStats.opponentsTitle`、`myStats.opponentRecord`（參數 `wins`、`losses`）、`myStats.altText`（參數 `group`、`winRate`、`wins`、`losses`）。

名次一律以參數帶入，文案中不得寫死「第 1／2／3 名」。`zh-TW` 與 `en` 的 key 集合必須完全相同（以 `group-share-card-i18n.spec.ts` 斷言）。
