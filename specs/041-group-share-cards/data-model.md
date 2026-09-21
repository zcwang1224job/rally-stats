# Data Model: 團分享圖卡與導流頁尾（041-group-share-cards）

**Plan**: [plan.md](./plan.md) | **Research**: [research.md](./research.md)

本功能**不新增、不修改任何已儲存的資料**，也不改任何 API 回應。以下全部是前端的呈現模型：由既有回應轉換而來，只存在於產生圖卡的當下。

## 1. 輸入（既有，唯讀）

| 來源 | 欄位 | 用途 |
|---|---|---|
| `MemberGroupHistoryResponse`（`GET /members/me/groups/{id}/history`，團戰績頁已載入） | `group_name` | 兩張圖卡的標題 |
| 同上 `.final_standings[]`：`FinalStandingRow` | `nickname`、`rank`、`total_matches`、`total_wins`、`total_losses`、`is_self` | 排行榜列；我的成績卡的名次與暱稱。**`current_status` 刻意不讀**（FR-011）。`roster_entry_id` 不進入模型（FR-021） |
| 同上 `.my_stats`：`MemberGroupStatsResponse` | `total_matches`、`total_wins`、`total_losses`、`win_rate`、`round_win_rates[]`、`opponent_records[]` | 我的成績卡 |
| `MyGroupsResponse`（`GET /members/me/groups`，本功能在團戰績頁新增一次呼叫） | 該團的 `created_at` | 活動日期；取不到時為 `null` |
| `window.location.origin`／`host` | — | QR 網址與可讀網址 |

伺服器端既有的排序保證（本功能依賴、但不重做）：

- `final_standings`：依標準競賽名次（並列同名次、下一名跳號）排序，次要排序為最早的加入時間；涵蓋所有曾參與者，含 0 場者、訪客、已離團者。
- `my_stats.opponent_records`：依交手場數由多到少，次要排序為球員鍵值。

## 2. 共用層模型（`core/share-card/`）

### ShareCardSource

`'card-rank' | 'card-me' | 'card-match'`——`ref` 參數的值，也是圖卡種類的識別。

本節的 `ShareCardSource`、`ShareCardLink`、`QrMatrix`、`PromoFooter`、`ShareCardRenderEnv`、`ShareCardOption` 全部定義在 `share-card-option.ts`（只放型別、不 import 任何實作檔，避免循環），並在 Phase 2 就定案為以下形狀；之後各 phase 只改實作、不改欄位。

### ShareCardLink

| 欄位 | 型別 | 說明 |
|---|---|---|
| `qrUrl` | `string` | `<origin>/?ref=<source>`；不含任何 ID（FR-021） |
| `displayUrl` | `string` | `host`（不含通訊協定、路徑、參數），給人眼讀與手動輸入（FR-019） |

### QrMatrix

| 欄位 | 型別 | 說明 |
|---|---|---|
| `size` | `number` | 每邊模組數（version 1–40 → 21–177）。一般網址為 33；頁尾可畫的上限為 53（`qrLayout()` 仍可得到 4px） |
| `isDark(row, col)` | `boolean` | 該模組是否為深色 |

`QrMatrix | null`：`null` 表示 QR 產生失敗或網址過長（每模組會低於 4px），頁尾省略 QR 碼、保留可讀網址。

### QrLayout（`qrLayout(size)` 的輸出）

| 欄位 | 說明 |
|---|---|
| `modulePx` | 滿足 `(size + 4) × modulePx ≤ 240` 的最大**偶數**，且 ≥ 4；否則整個結果為 `null` |
| `offset` | QR 在 240×240 底板內置中的起點 |

驗證規則：`modulePx` 必為偶數（縮圖 50% 後每模組仍為整數像素，research Decision 5）。

### PromoFooter

| 欄位 | 型別 | 說明 |
|---|---|---|
| `link` | `ShareCardLink` | 由 `rasterize()` 以 `buildShareCardLink(window.location, option.source)` 產生；Phase 2 起就是必填 |
| `qr` | `QrMatrix \| null` | US2 之前固定為 `null`；US2 起由 `rasterize()` 動態載入 `qrcode` 產生，失敗時為 `null` |
| `meta` | `string \| null` | 頁尾左上方的一行輔助資訊。`rasterize()` 一律給 `null`；040 單場圖卡的 renderer 以 `{ ...env.footer, meta }` 覆寫為「比賽時長 · 平均每分耗時」；團圖卡維持 `null` |

品牌字樣、標語、掃碼提示由 renderer 依語系取得，不放在模型裡。

### Block 與排版

| 欄位 | 型別 | 說明 |
|---|---|---|
| `height` | `number` | 理想高度 |
| `minHeight` | `number`（選填） | 可收縮到的下限；未提供表示不可收縮 |
| `draw(y, height)` | 函式 | 以實際分到的高度繪製 |

`stackBlocks(blocks, { top, bottom, gap, minGap })`：

1. 區塊總高＋`gap`(48) × 間距數 ≤ 可用高度 → 不收縮，起點為 `top + Math.floor(剩餘 / 2)`，整組垂直置中（與 040 現行行為相同）。
2. 否則間距改為 `max(minGap, Math.floor((可用 − 區塊總高) / 間距數))`（最低 32）；若因此放得下，區塊高度不變，剩餘像素同樣置中。
3. 間距 32 仍不足 → 由上而下，把有 `minHeight` 的區塊依序收縮到「剛好放下」或其 `minHeight` 為止；起點為 `top`。
4. 仍不足 → 由 `top` 開始往下排；renderer 測試保證各圖卡的最壞情況不會走到這一步。

全部以整數像素計算；同樣輸入必得同樣輸出（SC-010）。各圖卡的區塊尺寸見 contracts/share-card-core.md §7 與 contracts/group-share-card.md §2。

### ShareCardOption（預覽外殼的輸入）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `source` | `ShareCardSource` | 圖卡種類；決定 `ref` 值 |
| `labelKey` | `string` | 種類切換按鈕的語系 key |
| `fileName` | `string` | 下載檔名（FR-032） |
| `altText` | `TranslatedText` | 預覽的替代文字（FR-031） |
| `draw(ctx, env)` | 函式 | 把圖卡畫到 1080×1350 的 canvas 上 |

`ShareCardRenderEnv`：`{ palette, text, fonts, footer: PromoFooter }`，由 `ShareCardActions.rasterize()` 組好後交給 `draw`。

## 3. 團圖卡模型（`core/group-share-card/`）

### GroupShareCardContext（頁面提供）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `createdAt` | `string \| null` | 團的建立時間（ISO）；`getMyGroups()` 失敗或找不到該團時為 `null` |

### LeaderboardRow

| 欄位 | 型別 | 來源／規則 |
|---|---|---|
| `rank` | `number` | `FinalStandingRow.rank`，**原樣**（FR-008） |
| `nickname` | `string` | 原樣 |
| `wins`／`losses` | `number` | `total_wins`／`total_losses` |
| `isSelf` | `boolean` | `is_self` |
| `podium` | `boolean` | 是否為前 3 **列**（依列的位置，不依名次） |

### LeaderboardCardModel

| 欄位 | 型別 | 規則 |
|---|---|---|
| `groupName` | `string` | |
| `date` | `string \| null` | `context.createdAt` |
| `playerCount` | `number` | `countPlayers(final_standings)`＝`total_matches ≥ 1` 的列數（FR-006、FR-011）；我的成績卡共用同一個函式 |
| `rows` | `LeaderboardRow[]` | 先濾掉 `total_matches = 0`，**保持伺服器順序**，取前 6 列（FR-007） |
| `selfRow` | `LeaderboardRow \| null` | 本人有出賽且不在 `rows` 內時，另附本人那一列與真實名次（FR-010）；否則 `null` |
| `fileName` | `string` | `rally-stats-rank-<YYYYMMDD 或 nodate>-<團名安全字元>.png` |
| `altText` | `TranslatedText` | 依 `rows` 列數選用 `groupShareCard.leaderboard.altText1／2／3`；參數 `group`、`rankN`（伺服器名次，並列時原樣）、`nameN`，不出現空字串參數（FR-031） |

`buildLeaderboardCardModel(history, context)` 在沒有任何出賽球員時回傳 `null`（FR-005 的可用條件）。

### MyStatsCardModel

| 欄位 | 型別 | 規則 |
|---|---|---|
| `groupName`、`date` | | 同上 |
| `nickname` | `string \| null` | `is_self` 那一列的暱稱；找不到則 `null`（整行省略） |
| `winRate` | `string` | `formatPercent(my_stats.win_rate)`——與頁面字面相同（FR-017） |
| `wins`、`losses`、`matches` | `number` | `my_stats` 原樣 |
| `standing` | `{ rank: number; playerCount: number } \| null` | 來自 `is_self` 列與排行榜卡相同定義的 `playerCount`；找不到本人列則 `null`（FR-014） |
| `trend` | `{ x: number; y: number }[] \| null` | `round_win_rates.length ≥ 2` 時，第 i 輪為 `x = i / (n − 1) × 100`、`y = (1 − win_rate) × 100`——與團戰績頁 `round-trend-chart` 相同的固定 0～100% 縱軸（FR-015）；否則 `null` |
| `opponents` | `{ nickname; wins; losses }[]` | `opponent_records` 前 3 筆，順序不變（FR-016）；可為空陣列（整塊省略） |
| `fileName` | `string` | `rally-stats-me-<YYYYMMDD 或 nodate>-<團名安全字元>.png` |
| `altText` | `TranslatedText` | `groupShareCard.myStats.altText`，參數 `group`、`winRate`、`wins`、`losses` |

`buildMyStatsCardModel(history, context)` 在 `my_stats.total_matches = 0` 時回傳 `null`（FR-013）。

### availableGroupCards(history, context) → ShareCardOption[]

固定順序：排行榜、我的成績；模型為 `null` 的種類不出現。回傳空陣列時頁面不顯示「分享圖卡」按鈕（FR-001）。

## 4. 040 模型的變動

`ShareCardModel`（單場比賽）**欄位不變**。`durationSeconds`／`averagePointSeconds` 仍在模型上，只是 renderer 把它們組成 `PromoFooter.meta` 交給共用頁尾繪製，而不是自己畫頁尾。`ShareCardContext`、`Highlight`、`CardTeam` 不變。共用型別（`ShareCardCanvas`、`SharePalette`、`ShareTheme`、`ShareCardText`、`ShareCardFonts`、`TranslatedText`）搬到 `core/share-card/`，`share-card.models.ts` 以 re-export 維持既有匯入路徑。

## 5. 狀態

沒有持久狀態。預覽外殼的暫時狀態沿用 040（`idle → generating → ready | error`），多一個「目前選取的圖卡種類」；切換種類或配色都會重新進入 `generating`，並以世代編號丟棄過期的產圖結果。配色與種類都不記憶：每次開啟為亮色＋第一個可用種類。
