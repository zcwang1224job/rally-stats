# Data Model: 加分時記錄發球者與站位資訊

## 新增／修改欄位

### `matches` 新增欄位（比賽等級的持久化「發球狀態」，research.md Decision 1）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `serving_team` | `VARCHAR(1)` 列舉：`'A'` \| `'B'`，**nullable** | 目前發球隊伍。比賽尚未轉為 `in_progress` 前為 `NULL`；轉為 `in_progress` 當下由 `_initialize_serve_state()` 隨機寫入（research.md Decision 4），之後隨每次加分（`delta > 0`）依 side-out 規則遞移（research.md Decision 2）。`-1` MUST NOT 修改此欄位。 |
| `team_a_reference_server_id` | `UUID` FK → `roster_entries.id`，**nullable** | A 隊目前的 reference server（單打時恆為 A 隊唯一參賽者；雙打時是「目前輪到站在跟 A 隊比分奇偶對應的正確發球區」的那一位球員）。初始化與遞移規則同上。 |
| `team_b_reference_server_id` | `UUID` FK → `roster_entries.id`，**nullable** | B 隊對應欄位，語意同上。 |

三個欄位皆為現有比賽的**新增**欄位，既有（已完成/已捨棄）比賽的資料列
維持 `NULL`，不回填、不重新計算——本功能不影響既有比賽紀錄。

新增 Alembic migration：`ALTER TABLE matches ADD COLUMN serving_team
VARCHAR(1) NULL, ADD COLUMN team_a_reference_server_id UUID NULL
REFERENCES roster_entries(id), ADD COLUMN team_b_reference_server_id
UUID NULL REFERENCES roster_entries(id)`。

## 新增實體

### `ScoreServeRecord`（新表 `score_serve_records`）

每一次「加分」（`ScoreEvent` 之 `delta > 0`）對應 0 或 1 筆本表資料列
（`delta < 0` 的修正動作不會有對應資料列，research.md Decision 5）。
寫入後即不可變（immutable）——沒有任何程式路徑會 `UPDATE` 已存在的
`ScoreServeRecord`（FR-003）。

| 欄位 | 型別 | 說明 |
|---|---|---|
| `id` | `UUID`，PK，`default=uuid4` | |
| `score_event_id` | `UUID` FK → `score_events.id`，`UNIQUE NOT NULL`，`ON DELETE CASCADE` | 與觸發這筆紀錄的加分事件一對一對應。 |
| `match_id` | `UUID` FK → `matches.id`，`NOT NULL`，`ON DELETE CASCADE`，索引 | 從 `score_event_id` 可推得，此處比照既有 `ScoreEvent` 的 denormalize 慣例額外存一份，讓「查某場比賽全部發球紀錄」不需要 join `score_events`。 |
| `group_id` | `UUID` FK → `groups.id`，`NOT NULL`，索引 | 從 `match_id` 可推得，比照既有 `ScoreEvent.group_id` 同一套 denormalize 慣例額外存一份（`ScoreEvent` 對 `match_id`／`group_id` 兩者皆denormalize，本表沿用同一模式，而非只做一半）——FR-005「未來可被取得」預期的存取路徑（既有比賽紀錄查詢權限）多以 `group_id` 為查詢範圍界線，沒有這欄會強迫未來的查詢多一次 join `matches` 才能套用既有的團級授權過濾。 |
| `server_roster_entry_id` | `UUID` FK → `roster_entries.id`，`NOT NULL` | 這一分的發球者。等於下方 4 個站位欄位中，`server_team` 那一隊、比分奇偶對應的那一格。 |
| `server_team` | `VARCHAR(1)` 列舉：`'A'` \| `'B'`，`NOT NULL` | 這一分寫入當下的 `serving_team` 快照。 |
| `team_a_right_roster_entry_id` | `UUID` FK → `roster_entries.id`，nullable | A 隊「右側站位」球員；單打且 A 隊球員這一刻站左側時為 `NULL`。 |
| `team_a_left_roster_entry_id` | `UUID` FK → `roster_entries.id`，nullable | A 隊「左側站位」球員；單打且 A 隊球員這一刻站右側時為 `NULL`。 |
| `team_b_right_roster_entry_id` | `UUID` FK → `roster_entries.id`，nullable | B 隊「右側站位」球員，語意同上。 |
| `team_b_left_roster_entry_id` | `UUID` FK → `roster_entries.id`，nullable | B 隊「左側站位」球員，語意同上。 |
| `created_at` | `TIMESTAMPTZ`，`NOT NULL`，`server_default=now()` | 沿用既有時間戳慣例（Constitution VIII）。 |

**應用層不變量**（不以 DB CHECK 約束表達，比照本專案既有慣例——例如
`member.language_preference` 的允許值只在程式碼中檢查，見
`app/domains/member/schemas.py` 的 `SUPPORTED_LANGUAGES` 註解——保留
彈性、避免日後規則調整需要資料庫遷移）：

- `server_roster_entry_id` MUST 等於 `team_{server_team}_right_roster_entry_id`
  或 `team_{server_team}_left_roster_entry_id` 兩者之一（依當下比分奇偶
  決定是哪一個，見 research.md Decision 3 的站位公式）。
- 單打比賽（`match_mode = 'singles'`）：`team_a_left_roster_entry_id`
  與 `team_a_right_roster_entry_id` 恰有一個非 `NULL`；B 隊比照。
- 雙打比賽（`match_mode = 'doubles'`）：四個站位欄位皆非 `NULL`。

新增 Alembic migration（與 `matches` 新欄位同一份 migration 檔）：
`CREATE TABLE score_serve_records (...)`，並在 `score_event_id` 建立
`UNIQUE` 索引、在 `match_id`／`group_id` 各建立一般索引。

## 既有實體（本 feature 讀寫規則變更，schema 不變）

### `ScoreEvent`（007-live-scoreboard owns，schema 不變）

- `apply_score_delta()` 寫入 `ScoreEvent` 的既有邏輯完全不變；本功能
  只在 `delta > 0` 且該筆 `ScoreEvent` 成功寫入、取得其 `id` 之後，
  於**同一個資料庫交易**內額外寫入一筆對應的 `ScoreServeRecord`
  （`score_event_id` 指向剛寫入的這筆 `ScoreEvent`；`group_id` 直接
  複用 `match.group_id`，與既有 `ScoreEvent.group_id` 的取值來源相同，
  不重新查詢）。

### `Match`（003-schedule-rotation owns，本次新增其發球狀態欄位）

- 既有欄位（`status`、`score_a`、`score_b`、`winner_team` 等）與既有
  讀寫邏輯完全不變。
- `apply_score_delta()` 的 `delta > 0` 分支，在既有的「比分遞增」
  `UPDATE` 之後，新增一步「發球狀態轉換」判定（research.md Decision
  2）：若得分方＝目前 `serving_team`，三個發球狀態欄位不變；若得分方
  ≠目前 `serving_team`（side-out），`serving_team` 改為得分方，且
  （雙打時）得分方的 `reference_server` 換成該隊另一位球員；未得分
  那一隊的 `reference_server` 不變。

### `MatchParticipant`（003-schedule-rotation owns，schema 不變，唯讀）

- 本功能讀取某場比賽 A/B 兩隊各自的參賽者（`roster_entry_id`、
  `team`），用於：(a) 初始化 `reference_server` 時決定該隊有哪些人可
  抽籤；(b) side-out 時找出「該隊另一位球員」（雙打）。不新增、不修改
  任何 `MatchParticipant` 資料列。

## 站位計算公式（純函式，不落地為欄位，僅用於寫入 `ScoreServeRecord` 快照當下）

給定 `serving_team`、`team_a_reference_server_id`、
`team_b_reference_server_id`、目前 `score_a`、`score_b`：

對每一隊 X（A 或 B）：

- 若 `score_X` 為偶數：`reference_server_X` → `team_X_right`；該隊另一
  位球員（雙打，若有）→ `team_X_left`。
- 若 `score_X` 為奇數：`reference_server_X` → `team_X_left`；該隊另一
  位球員 → `team_X_right`。
- 單打：只有 `reference_server_X` 一位球員，依上述規則佔用其中一個
  站位，另一個維持 `NULL`。

`server_roster_entry_id` = `serving_team` 所屬隊伍當下的
`reference_server`；`server_team` = `serving_team`。

## 驗證規則（新增）

| 規則 | 涉及欄位 | 依據 |
|---|---|---|
| `-1`（`delta < 0`）MUST NOT 建立 `ScoreServeRecord`、MUST NOT 修改 `matches` 的三個發球狀態欄位 | `score_serve_records`、`matches.serving_team`/`team_a_reference_server_id`/`team_b_reference_server_id` | FR-004 |
| 每一筆 `ScoreServeRecord` 寫入後 MUST NOT 再被任何程式路徑 `UPDATE` | `score_serve_records` | FR-003 |
| 比賽沒有轉為 `in_progress` 之前（`serving_team IS NULL`）MUST NOT 產生任何 `ScoreServeRecord` | `matches.serving_team`、`score_serve_records` | FR-007 |
