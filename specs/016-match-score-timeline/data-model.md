# Data Model: 比賽加減分紀錄與趨勢圖

本 feature **不新增任何資料表**（`score_events` 已於上一階段建立，
schema 定義見 `apps/api/app/domains/schedule/models.py` 的 `ScoreEvent`，
migration 見 `apps/api/alembic/versions/f3a1c9d4e7b2_score_events_table.py`）。
以下記錄唯讀查詢範圍與新增的 API 回應形狀（非資料表）。

## 既有實體（本 feature 讀取，定義權屬其他 spec）

### `Match`（003 owns，唯讀）

讀：`id`／`group_id`／`round_number`／`status`／`score_a`／`score_b`／
`winner_team`／`started_at`／`ended_at`。只查詢 `status == "completed"`
的列（`_completed_matches_query()`，`group/service.py:941`）——已捨棄
（`abandoned`）的比賽依既有規則本就不出現在任何對戰紀錄清單中，本
feature 沿用此既有邊界，不另外處理。

### `MatchParticipant` / `RosterEntry`（003 owns，唯讀）

讀：透過既有 `_build_match_record_summaries()`（`group/service.py:949`）
組出 `team_a`/`team_b`（`ParticipantSummary`：`roster_entry_id`／
`nickname`／`team`），供 FR-007 之基本資訊呈現。

### `ScoreEvent`（016 上一階段建立，schedule domain owns，唯讀）

讀：`match_id`／`side`／`delta`／`score_a`／`score_b`／`created_at`，依
`created_at, id` 升冪排序（`id` 作為 `created_at` 剛好相同時的次要排序鍵
——`test_score_concurrency.py` 顯示同一場比賽的並發加減分是系統實際支援
的情境，兩筆事件的 `created_at` 理論上可能落在同一個時間戳，僅靠
`created_at` 排序不足以保證穩定順序；`id` 雖是隨機 UUID、不具寫入順序
意義，但至少讓排序結果具「確定性」——同一份資料重複查詢一定得到同一個
順序，不會忽前忽後，滿足 spec.md Edge Case「不可因時間顯示精度不足而
順序錯亂」的字面要求），換算「開賽後經過秒數」（`created_at -
Match.started_at`，取整數秒）。`source` 欄位（`control_panel`/`admin`/
`all_courts`）為系統內部資訊，本 feature 不對外曝露（見 spec.md
Assumptions）。

## 新增的唯讀組合視圖（API 回應形狀，非資料表）

### `ScoreEventSummary`（新增，`group/schemas.py`）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `side` | `"A" \| "B"` | 得／失分方。 |
| `delta` | `1 \| -1` | 本次為加分或扣分。 |
| `score_a` | `int` | 本次操作後 A 隊比分。 |
| `score_b` | `int` | 本次操作後 B 隊比分。 |
| `elapsed_seconds` | `int` | 距離比賽開始（`Match.started_at`）經過的秒數，`>= 0`（research.md #3 判斷「完整」時，第一筆事件的 `score_a + score_b` 恆為 `1`，但 `elapsed_seconds` 不受此限——單純是時間差）。 |

### `MatchRecordDetailResponse`（新增，繼承既有 `MatchRecordSummary`）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `match_id` | `str` | 既有欄位（繼承自 `MatchRecordSummary`）。 |
| `round_number` | `int` | 既有欄位。 |
| `team_a` | `list[ParticipantSummary]` | 既有欄位。 |
| `team_b` | `list[ParticipantSummary]` | 既有欄位。 |
| `score_a` | `int` | 既有欄位——最終比分。 |
| `score_b` | `int` | 既有欄位——最終比分。 |
| `winner_team` | `"A" \| "B"` | 既有欄位。 |
| `started_at` | `datetime` | 既有欄位——完整比賽必為非 `None`（見既有欄位註解）。 |
| `ended_at` | `datetime` | 既有欄位。 |
| `record_completeness` | `"complete" \| "partial" \| "none"` | **新增**（FR-006/006a，research.md #3）。 |
| `events` | `list[ScoreEventSummary]` | **新增**，依 `elapsed_seconds` 升冪排序（FR-002/003）；`record_completeness == "none"` 時為空陣列。 |

`MatchRecordSummary` 本身（`group/schemas.py:373`）不修改，既有呼叫端
（`GET /groups/{group_id}/match-records` 等清單端點）零行為變動。

## 狀態/邊界摘要

- `record_completeness` 三態判斷邏輯見 research.md #3——純粹由
  `events` 本身的第一筆資料推導，不依賴任何額外欄位或部署時間戳。
- 存取邊界：`GET /groups/{group_id}/match-records/{match_id}` 沿用既有
  `resolve_active_roster_membership()`（現役 Guest/Member）；`GET
  /members/me/match-records/{match_id}` 沿用既有
  `verify_ever_group_member()`（曾經是成員即可，`require_member`
  把關登入狀態）——皆為既有函式，零修改（research.md #1）。
- 兩個端點皆對「比賽存在但不符合授權範圍」統一回傳 `MATCH_NOT_FOUND`
  （群組範圍端點：比賽存在但屬於別的團；兩者皆適用：比賽存在但未
  完成），不透露額外資訊（見 contracts/）。
