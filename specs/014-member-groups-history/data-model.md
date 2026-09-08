# Data Model: 我的團完整參與紀錄與戰績

本 feature **不新增任何資料表**，也不修改任何既有資料表結構（research.md
#6）。以下記錄唯讀查詢範圍的擴充，以及新增的 API 回應形狀（非資料表）。

## 既有實體（本 feature 讀取，定義權屬其他 spec）

### `Group`（001/003 owns，唯讀）

- 讀：`id`／`group_number`／`name`／`status`／`created_by_member_id`
  ——用於判斷「我建立過的團」與清單顯示。查詢範圍**不**依 `status` 篩選
  （已解散的團仍需列出，FR-001）。

### `RosterEntry`（001/003/006 owns，唯讀）

- 讀：`group_id`／`member_id`／`status`／`joined_at`——用於判斷「我曾經
  加入過的團」（`member_id` 為本人、任何 `status`）。同一位會員可能在同一
  團有多筆歷史紀錄（加入→離開→重新加入），取 `joined_at` 最新一筆的
  `status` 作為顯示用的「目前狀態」（research.md #4）。`member_id IS
  NULL`（訪客加入）天生被排除，不需額外判斷式（FR-003）。
- 也用於本 feature 新增的授權判斷式 `verify_ever_group_member()`
  ——只要求「存在任一筆」，不限狀態、不限最新一筆（research.md #3）。

### `Match` / `MatchParticipant`（003 owns，唯讀）

- 讀：透過擴充後的 `build_group_match_records(group_id, nickname=...)`
  （該團所有已完成比賽，供 FR-004/FR-009 之比賽清單與暱稱篩選）與
  `build_member_match_records(group_id=...)`（會員自己的個人統計，供
  FR-005，不接受暱稱篩選）間接查詢，本 feature 不直接寫新的 SQL 查詢這
  兩張表（Revision 2026-09-07b：改回以 `build_group_match_records()` 為
  比賽清單的主要查詢——Revision 2026-09-07a 曾誤將其整個換成
  `build_member_match_records()`，導致清單被錯誤窄化為僅自己的比賽）。

## 新增的唯讀組合視圖（API 回應形狀，非資料表）

### `MyGroupSummary`（既有 schema，擴充 2 個欄位）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `group_id` | `str` | 既有欄位。 |
| `group_number` | `int` | 既有欄位。 |
| `name` | `str` | 既有欄位。 |
| `status` | `"active" \| "disbanded"` | 既有欄位——團本身的狀態。 |
| `is_creator` | `bool` | **新增**。是否為此團的建立者。 |
| `member_status` | `"active" \| "left" \| "kicked"` | **新增**。自己在此團「最新一筆」`RosterEntry` 的狀態（research.md #4）。 |

`MyGroupsResponse`（既有，`{ groups: MyGroupSummary[] }`）形狀不變。

### `MemberGroupStatsResponse`（新增，Revision 2026-09-07b）

會員自己在此團的個人表現——恆常反映完整參與紀錄，不受
`MemberGroupHistoryResponse.matches` 自己的暱稱篩選影響（FR-005）。

| 欄位 | 型別 | 說明 |
|---|---|---|
| `total_matches` | `int` | 我在此團的已完成比賽總場次。 |
| `total_wins` | `int` | |
| `total_losses` | `int` | |
| `win_rate` | `float` | `total_wins / total_matches`，無比賽時為 `0.0`。 |
| `round_win_rates` | `list[RoundWinRatePoint]` | 各輪勝率趨勢，供圖表呈現（既有形狀重用）。 |
| `opponent_records` | `list[OpponentRecord]` | 對戰對象戰績排行（既有形狀重用）。 |

### `MemberGroupHistoryResponse`（新增，`GET
/members/me/groups/{group_id}/history` 的回應——Revision 2026-09-07b：
`matches` 改回該團完整已完成比賽清單，`my_stats` 獨立巢狀個人統計）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `group_id` | `str` | |
| `group_name` | `str` | |
| `my_stats` | `MemberGroupStatsResponse` | 會員自己的個人統計/圖表資料（FR-005）。 |
| `matches` | `list[MatchRecordSummary]` | 該團**所有**已完成比賽（不限自己是否參與，既有形狀重用；FR-004，可依 `nickname` 篩選）。 |
| `page` | `int` | |
| `total_pages` | `int` | |

`MatchRecordSummary`／`RoundWinRatePoint`／`OpponentRecord` 皆為既有
形狀（`group/schemas.py`），不修改、不重複定義。

### 篩選參數（Revision 2026-09-07b 修正，FR-009）

`GET /members/me/groups/{group_id}/history` 新增單一 query 參數
`nickname`（選填）——搜尋**該團全部已完成比賽**中，任一位參與者（不分
哪一隊）的暱稱是否包含此字串（大小寫不分），只影響 `matches` 欄位，
MUST NOT 影響 `my_stats`（research.md #2 修正版：`build_group_match_
records()` 新增 `nickname` 篩選參數，而非重用
`build_member_match_records()` 的一整組個人化篩選欄位——後者的
`opponent1`/`opponent2`/`partner`/`self_score_cmp`/`opponent_score_cmp`
等欄位皆隱含「以某個人視角」的語意，不適用於「該團全部比賽」這種無
特定視角的清單）。

## 狀態/邊界摘要

- 「我的團」清單的涵蓋範圍 = 「曾經有 `RosterEntry`」∪「曾經是
  `created_by_member_id`」，以 `group_id` 去重（FR-001）。
- 查看某團歷史的存取邊界 = 與上述清單涵蓋範圍完全一致（Clarifications
  2026-09-07、FR-006）——未曾參與過的團一律拒絕（`GROUP_MEMBERSHIP_NEVER_HELD`，
  403）。
