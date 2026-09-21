# Data Model: 單場比賽分享圖卡（040-match-share-card）

**Date**: 2026-09-21 | **Plan**: [plan.md](./plan.md) | **Research**: [research.md](./research.md)

本功能**不新增、不修改任何資料表**，也沒有 migration。以下分成兩部分：(A) 既有持久化資料在本功能中的角色；(B) 只存在於前端記憶體、查看當下產生的呈現模型。

---

## A. 既有持久化資料（唯讀）

| 資料 | 來源 | 本功能用途 |
|---|---|---|
| `matches.target_score` | `apps/api/app/domains/schedule/models.py`，比賽建立時由團設定快照寫入，`NOT NULL` | **新投影**到 `MatchRecordDetailResponse.target_score`，作為亮點門檻換算的 T（FR-012a） |
| `matches.score_a／score_b／winner_team／round_number／started_at／ended_at` | 同上，已由 `MatchRecordSummary` 投影 | 比分、勝方、輪次、日期、時長 |
| 參賽者（`team_a`／`team_b` 的 `ParticipantSummary`） | 已投影 | 暱稱（FR-006a：全部照常顯示） |
| `record_completeness`、`events` | 016 | 降級判斷、走勢點 |
| `momentum_stats`、`tempo_stats` | 033 | 亮點 #4、#6；平均每分耗時 |
| `clutch_stats` | 034 | 亮點 #1、#2、#3 |
| `ending_stats` | 035 | 亮點 #5 |

### 回應欄位變更

`MatchRecordDetailResponse`（後端 `group/schemas.py`，前端 `core/api/group-member-view.models.ts`）：

| 欄位 | 型別 | 必填 | 說明 |
|---|---|---|---|
| `target_score` | `int` | 是 | 該場比賽建立時的獲勝分數快照。**MUST NOT** 讀取團目前的設定。 |

其餘欄位不變。詳見 [contracts/match-record-detail-api.md](./contracts/match-record-detail-api.md)。

---

## B. 前端呈現模型（不儲存）

### ShareCardContext（由呼叫端提供）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `groupName` | `string` | 團名，四個呼叫端手上都已有（research Decision 5） |
| `perspective` | `{ kind: 'neutral' }` \| `{ kind: 'mine'; myTeam: 'A' \| 'B' }` | 只有會員個人跨團對戰紀錄會給 `mine`（FR-016、FR-017a） |

**驗證規則**：`mine` 的 `myTeam` 由列資料推導：`won ? winner_team : 另一隊`。若呼叫端拿不到可靠的列資料，MUST 給 `neutral`（FR-018）。

### ShareCardModel（`buildShareCardModel(detail, context)` 的輸出）

| 欄位 | 型別 | 規則 |
|---|---|---|
| `groupName` | `string` | 來自 context |
| `startedAt` | `string \| null` | ISO 時間戳；由 renderer 依裝置時區格式化成日期，格式字串取自語系 key `matchShareCard.dateFormat`，locale 固定為 `en-US`（research Decision 8）；null 時不畫日期 |
| `roundNumber` | `number` | |
| `perspective` | `'neutral' \| 'mine'` | |
| `teams` | `[CardTeam, CardTeam]` | **第一隊為主角隊**：中立視角為勝方，我方視角為我方（FR-016、FR-017） |
| `trend` | `ScoreTrendPoint[] \| null` | 僅 `record_completeness === 'complete'` 時有值（FR-007），否則為 null |
| `highlights` | `Highlight[]` | 0～3 個；不完整紀錄時一律為 `[]`（FR-011） |
| `durationSeconds` | `number \| null` | `ended_at − started_at`；任一為 null 或結果 < 0 時為 null |
| `averagePointSeconds` | `number \| null` | `tempo_stats?.average_seconds ?? null` |
| `fileName` | `string` | `rally-stats-YYYYMMDD-{第一隊分數}-{第二隊分數}.png`，日期同樣依裝置時區 |
| `altText` | `{ key: string; params: Record<string, string \| number> }` | 預覽 `<img>` 的替代文字（FR-028） |

### CardTeam

| 欄位 | 型別 | 規則 |
|---|---|---|
| `team` | `'A' \| 'B'` | 原始隊伍代號，用於選擇隊伍配色，也保證排序後比分與暱稱的對應正確（FR-019） |
| `nicknames` | `string[]` | 單打 1 個、雙打 2 個，順序同詳情 |
| `score` | `number` | 該隊的最終分數 |
| `isWinner` | `boolean` | |
| `badge` | `'win' \| 'victory' \| 'defeat' \| null` | 中立：勝方為 `win`，敗方為 null；我方：我方為 `victory` 或 `defeat`，對手為 null |

### Highlight（可辨識聯集，`kind` 即 research Decision 7 的候選）

| `kind` | 參數 | 語系 key（`matchShareCard.highlight.*`） |
|---|---|---|
| `comeback` | `deficit: number` | `comeback`：「最大落後 {deficit} 分逆轉勝」 |
| `matchPointsSaved` | `count: number` | `matchPointsSaved`：「化解 {count} 個賽末點」 |
| `deuceWin` | `scoreFor: number; scoreAgainst: number` | `deuceWin`：「延長賽 {scoreFor}:{scoreAgainst} 勝出」 |
| `run` | `length: number` | `run`：「最長連得 {length} 分」 |
| `winnerRate` | `percent: string`（已格式化，如 `"58%"`） | `winnerRate`：「主動得分 {percent}」 |
| `leadChanges` | `count: number` | `leadChanges`：「領先易手 {count} 次」 |
| `bigMargin` | `margin: number` | `bigMargin`：「以 {margin} 分差勝出」 |

**狀態轉換**：無。模型是 `(detail, context)` 的純函式輸出；配色（`'light' | 'dark'`）與語言不屬於模型，而是繪製時的參數，所以切換配色不需要重建模型（FR-024）。

### SharePalette

`'light' | 'dark'` 各一組固定色值：背景、主要文字、次要文字、分隔線、A 隊色、B 隊色、徽章底色與文字色、走勢線 A 與 B。所有文字與背景的組合對比度 ≥ 4.5:1（research Decision 10）。

### 圖卡圖片（Blob）

由 `ShareCardActions.rasterize(model, palette)` 產生 1080×1350 的 `image/png`。只存在於預覽生命週期內：以 object URL 顯示，預覽關閉時 revoke。系統不保存、不上傳。
