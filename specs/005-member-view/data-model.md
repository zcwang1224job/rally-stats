# Data Model: 團內成員視圖

## 新增資料表

### `round_history`（新表，research.md #1）

供 FR-008「已離開」狀態判定所需的「該輪開始時間點」查詢；由 003 既有的
`generate_next_round()` 寫入，本 feature 只讀。

| 欄位 | 型別 | 說明 |
|---|---|---|
| `group_id` | `UUID`（FK → `groups.id`，複合主鍵之一） | |
| `round_number` | `INTEGER`（複合主鍵之一） | 對應該次呼叫後 `groups.current_round_number` 的值；MUST 從 `1` 起——該團第一次呼叫 `generate_next_round()` 時就寫入第 1 輪（research.md #1、#2） |
| `started_at` | `TIMESTAMPTZ NOT NULL` | `generate_next_round()` 遞增 `current_round_number` 當下的 `now()` |

複合主鍵 `(group_id, round_number)`；無需額外索引（查詢皆以主鍵命中）。

### `roster_entries.left_at`（既有表新增欄位，research.md #3）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `left_at` | `TIMESTAMPTZ NULL` | `status` 轉為 `left`/`kicked` 當下由 003 既有 `handle_member_left()` 一併寫入；`status == 'active'` 時恆為 `NULL` |

## 既有實體（本 feature 讀取，定義權屬其他 spec）

### `Match` / `MatchParticipant`（003 owns）

戰績/對戰紀錄之底層資料來源：
- `Match.status == 'completed'` 且 `Match.winner_team` 非 NULL → 產生
  「比賽結果」（沿用 architecture.md 之 Match/MatchResult 合併決策，
  見 007 research.md #1，本 feature 延伸至戰績/對戰紀錄查詢）。
- `Match.round_number` → 戰績表格的輪次欄位對應依據。
- `MatchParticipant.roster_entry_id`/`team` → 判定某成員該場之隊伍、
  用於比對 `winner_team` 決定勝敗。

### `RosterEntry`（001 owns，003/004/006 擴充）

- `status`（`active`/`left`/`kicked`）+ 新增 `left_at` → FR-008 判定
  基準。
- `joined_at` → FR-007b 判定基準。
- `member_id`（nullable）→ 區分 Guest（NULL）與會員（非 NULL）、
  作為會員跨團查詢的 JOIN 鍵。
- `guest_session_token` → 退出組團後之失效判斷（research.md #7，
  `status` 轉為非 `active` 後查找條件自然失效，不需清空欄位本身）。

### `Group`（001 owns，003 擴充）

- `current_round_number` → 賽程頁顯示之目前輪次；戰績頁欄位範圍改以
  `round_history` 實際紀錄為準（research.md #2），不直接依賴此欄位。
- `status`（`active`/`disbanded`）→ **不**作為本 feature 讀取端點的
  存取條件（research.md #5，唯讀存取不受解散影響）。
- `scheduling_mechanism` → 賽程頁 waiting_reason 顯示邏輯沿用既有
  `build_schedule_snapshot()`。

### `Member`（006 owns）

- `id` → 會員跨團對戰紀錄查詢之 JOIN 鍵（`re.member_id = member.id`）。

## 新增的唯讀組合視圖（API 回應形狀，非資料表）

### `RoundStatus`

單一成員在單一輪次的狀態列舉：

```text
"won" | "lost" | "did_not_play" | "left"
```

### `MemberStandingRow`（戰績表格的一列，一位成員）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `roster_entry_id` | `str` | |
| `nickname` | `str` | |
| `current_status` | `"active" \| "left" \| "kicked"` | |
| `rounds` | `dict[int, RoundStatus]`（JSON 物件，key 為輪次編號字串） | 涵蓋該團 `round_history` 已記錄的全部輪次（從第 1 輪起），每輪恆有值（研究 #4 之四狀態公式保證） |

### `GroupStandingsResponse`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `current_round_number` | `int` | |
| `rounds` | `list[int]` | 表格欄位對應之輪次編號清單（該團 `round_history` 已記錄的輪次，從第 1 輪起，依序排列），供前端固定欄位順序，避免各列 `rounds` 物件 key 順序不一致 |
| `members` | `list[MemberStandingRow]` | 依 `joined_at` 排序 |

### `MatchRecordSummary`（對戰紀錄的一列，一場已完成比賽）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `match_id` | `str` | |
| `round_number` | `int` | |
| `team_a` | `list[ParticipantSummary]`（重用 003/007 既有型別） | |
| `team_b` | `list[ParticipantSummary]` | |
| `score_a` / `score_b` | `int` | |
| `winner_team` | `"A" \| "B"` | 恆非 NULL（僅 `completed` 比賽才會出現於此列表） |

### `GroupMatchRecordsResponse`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `matches` | `list[MatchRecordSummary]` | 依 `round_number` 由新到舊排序 |
| `page` / `total_pages` | `int` | 沿用 004 既有分頁慣例 |

### `MemberMatchRecordSummary`（會員跨團版本，多一個團名欄位）

`MatchRecordSummary` 之欄位 + `group_id: str` + `group_name: str`。

### `MemberMatchRecordsResponse`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `matches` | `list[MemberMatchRecordSummary]` | |
| `total_matches` / `total_wins` / `total_losses` | `int` | 跨團彙總統計（FR-018），僅計入 `completed` 比賽 |
| `win_rate` | `float` | `total_wins / total_matches`（`total_matches == 0` 時為 `0.0`，MUST NOT 除以零） |
| `page` / `total_pages` | `int` | |

### `LeaveGroupRequest`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `guest_session_token` | `str \| None` | Guest 身分退出時提供；與 `Authorization` header（Member 身分）擇一，皆缺時 MUST 回傳錯誤 |

### `LeaveGroupResponse`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `roster_entry_id` | `str` | |
| `status` | `"left"` | |

## Key Entities 對照 spec.md

- **MatchResult**：延用 `Match.status == 'completed'` + `winner_team`
  作為底層資料來源（見上），不新建資料表。
- **RosterEntry / Player**：`status` + 新增 `left_at` 欄位（見上），
  狀態轉換邏輯本身仍屬 003/004 範圍，本 feature 只新增 `left_at`
  這一個純粹供「時間點比對」使用的欄位。
- **Member**：僅讀取 `id` 作為跨團查詢 JOIN 鍵。
- **Guest Session Token**：退出後之失效透過既有「查找條件失效」機制
  達成（見上），不需要新增欄位或狀態。
