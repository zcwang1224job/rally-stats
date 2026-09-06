# Data Model: 即時計分板與控制板

本 feature **不新增資料表、不新增欄位、不需要 Alembic migration**——所有
必要欄位已由 003（`matches` 表）與 001/002（`groups`/`courts` 表）建立
完成（見 research.md #1）。以下僅記錄本 feature 對既有實體的**讀寫邊界**
與新增的**唯讀組合視圖**（非資料表，僅為 API 回應形狀）。

## 既有實體（本 feature 讀寫，定義權屬其他 spec）

### `Match`（003 owns，`apps/api/app/domains/schedule/models.py`）

| 欄位 | 本 feature 的讀寫行為 |
|---|---|
| `status` | 讀：判斷是否可接受操作（`in_progress` 才可）。寫：`in_progress → completed`（達標）或 `in_progress → abandoned`（提前結束），兩者皆為單向終態轉換，MUST 透過 research.md #5 之原子 `UPDATE ... WHERE status = 'in_progress'` 達成，MUST NOT 由已終態逆轉回 `in_progress`。 |
| `score_a` / `score_b` | 讀：達標判定、回應組裝。寫：`+1`/`-1` 之原子遞增/遞減（`-1` 額外要求 `score > 0`，research.md #5）。 |
| `winner_team` | 寫：僅於 `status` 轉為 `completed` 時填入 `'A'`/`'B'`；轉為 `abandoned` 時 MUST 保持 `NULL`（research.md #1，此即「不產生 MatchResult」的具體實作）。 |
| `target_score` / `deuce_threshold` / `cap_score` | 唯讀——003 建立比賽當下已快照，本 feature 讀取以計算達標判定（research.md #2），MUST NOT 寫入或依即時查詢 `groups` 目前設定值取代。 |
| `ended_at` | 寫：終態轉換當下設為 `now()`（兩種終態轉換路徑皆需設定，沿用 003 `abandon_group_matches`/`abandon_court_matches` 已建立的慣例）。 |
| `court_id` | 讀：授權檢查——請求所指定的 `match_id` 對應的 `court_id` MUST 等於 token/管理員路徑解析出的場地，不符則視同 `match_id` 不存在（`MATCH_NOT_FOUND`），防止以 A 場地的 token 操作 B 場地的比賽。 |

**狀態機（本 feature 新增的轉換，003 已定義列舉本身）**：

```text
        +1/-1（達標）
in_progress ────────────→ completed（winner_team 寫入）
    │
    │ 提前結束
    ▼
abandoned（winner_team 保持 NULL）
```

兩條轉換路徑互斥且皆為終態——一旦離開 `in_progress`，MUST NOT 再被本
feature 的任何操作修改（research.md #5 之原子防呆即為此保證的實作）。

### `MatchParticipant`（003 owns，唯讀）

用於組出計分板/控制板顯示的雙方球員/隊伍名稱（`ParticipantSummary`：
`roster_entry_id`/`nickname`/`team`）。本 feature 不寫入。

### `Court`（002 owns，唯讀）

`scoreboard_token`/`control_panel_token` 用於解析請求身份（research.md
#3）；`name` 用於顯示。本 feature 不寫入。

### `Group`（001/003 owns，唯讀）

`current_round_number`（顯示用，MUST 與 003 之全域 Round 編號完全一致，
不得有本 feature 自己的一份 Round 概念）、`scheduling_mechanism`（決定
FR-011/012 之場地行為分流）、`auto_next_round`（供 research.md #6 之
`check_round_complete_and_maybe_auto_advance` 判斷）。本 feature 不寫入
`Group` 的任何欄位。

## 新增的唯讀組合視圖（API 回應形狀，非資料表）

### `CourtLiveState`（單一場地即時狀態——供 `GET .../state` 系列端點使用）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `court_id` | `str` | |
| `round_number` | `int` | 即 `Group.current_round_number` |
| `current_match` | `MatchLiveDetail \| null` | `null` 時代表場地目前無進行中比賽（見 `waiting_reason`） |
| `waiting_reason` | `"manual_assignment" \| "no_queued_match" \| null` | 沿用 003 `WaitingReason` 型別（`schedule/schemas.py`），僅在 `current_match` 為 `null` 時有值 |
| `next_up` | `NextUpPreview \| null` | 「即將登場」預告；手動安排模式下恆為 `null`（改由 `waiting_reason = "manual_assignment"` 表達，FR-018） |

### `MatchLiveDetail`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `match_id` | `str` | |
| `status` | `"in_progress"` | 此欄位出現於 `current_match` 時恆為 `in_progress`（已終態的比賽不會再是任何場地的 `current_match`） |
| `score_a` / `score_b` | `int` | |
| `participants` | `list[ParticipantSummary]`（重用 003 既有型別） | |

### `NextUpPreview`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `match_id` | `str` | 供之後 `advance_court_after_match_ends` 領取後，前端可比對是否為同一場（非必要但利於除錯） |
| `participants` | `list[ParticipantSummary]` | |

### `ScoreMutationResult`（+1/-1/提前結束端點的共同回應形狀，research.md #9）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `applied` | `bool` | 本次操作是否真正生效（`false` = no-op，見 FR-006/006a） |
| `match_id` | `str` | |
| `status` | `"in_progress" \| "completed" \| "abandoned"` | 操作後的最新狀態 |
| `score_a` / `score_b` | `int` | 操作後的最新比分 |
| `winner_team` | `"A" \| "B" \| null` | |

## Key Entities 對照 spec.md

- **Match**（spec.md 176 行）：對照上方「既有實體」段落，狀態機轉換規則
  已完整定義。
- **Match Scoring Settings**：即 `Match` 快照欄位 `target_score`/
  `deuce_threshold`/`cap_score`，本 feature 只讀不寫（001 owns 定義）。
- **Court**：本 feature 只讀 `scoreboard_token`/`control_panel_token`/
  `name`（002 owns 定義，連結本身的產生/重新產生機制不屬本 feature）。
