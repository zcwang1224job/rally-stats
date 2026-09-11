# Data Model: 我的團最終團隊排名

本 feature **不新增任何資料表、不需要新的 migration**（research.md 前言）。
以下記錄新增的衍生回應形狀、既有實體的唯讀查詢方式，以及重構抽出的共用
純函式（非資料表）。

## 既有實體（本 feature 讀取/沿用，定義權屬其他 spec）

### `Match` / `MatchParticipant`（既有，唯讀，本 feature 完全不修改）

最終團隊排名的統計基礎——沿用既有 `_completed_matches_query()`
（`status == "completed"`）疊加 `group_id` 過濾，join `MatchParticipant`
取得每位參與者在每場比賽的 `team`，與 `Match.winner_team` 比對判定
勝負（research.md #1）。已捨棄（`abandoned`）的比賽 MUST NOT 計入——
`_completed_matches_query()` 本來就排除這個狀態，沿用即可，無需額外
處理（spec.md FR-003）。

### `RosterEntry`（既有，唯讀，查詢條件與 018 相反，且依 `member_id` 分組合併）

沿用既有 `joined_at`。**查詢條件**：**不**加 `RosterEntry.status ==
"active"` 過濾（018 為了排除離團成員才加的過濾，本 feature 刻意不套用），
也**不**加 `member_id IS NOT NULL` 過濾（訪客亦涵蓋在內，research.md #3，
spec.md FR-002）——查詢範圍是「該 `group_id` 底下所有曾經存在過的
`RosterEntry`」。

**分組規則**（research.md #1，落實 spec.md Edge Cases「同一位會員多筆
歷史紀錄只列一次」）：`member_id` 不為 `NULL` 的列依 `member_id` 分組
（同一位會員的所有歷史 `RosterEntry` 合併成一組，統計彙總其全部參與
期間的比賽）；`member_id` 為 `NULL`（訪客）的列每一筆各自獨立成一組。
每組的顯示屬性（`nickname`／`current_status`／代表用
`roster_entry_id`）取該組內 `joined_at` 最新的一筆；排序用的 `joined_at`
取該組內最早的一筆。

## 新增的衍生回應形狀

### `FinalStandingRow`（新增，位於 `group/schemas.py`，與既有 `MemberStandingRow` 同層）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `roster_entry_id` | `str` | 該組（可能對應多筆 `RosterEntry`）代表列的 `RosterEntry.id`（`joined_at` 最新的一筆），僅作為前端渲染時的 `track by` 鍵值，不用於自己與否的判斷（見 `is_self`）。 |
| `nickname` | `str` | 該組代表列的 `nickname`；訪客與會員一視同仁（research.md #3）。 |
| `current_status` | `Literal["active", "left", "kicked"]` | 該組代表列的 `RosterEntry.status`；MUST 用於前端標示「已離開」／「已被踢除」（spec.md FR-006）。 |
| `is_self` | `bool` | 這一組是否為目前查看此頁面的會員自己（依 `member_id == viewer_member_id` 比對，伺服器端算好，research.md #4）；訪客組恆為 `false`（本頁面僅會員可存取）。前端 MUST 直接渲染此欄位，MUST NOT 自行比對任何 ID（spec.md FR-011）。 |
| `rank` | `int` | 依該組彙總 `total_wins` 排序後的名次，並列時同一數字，之後的名次依人數跳號（standard competition ranking，`_assign_standard_competition_ranks()`，research.md #2）。 |
| `total_matches` | `int` | 該組在本團「已完成」比賽的總場次（`total_wins + total_losses`），彙總自組內**所有**歷史 `RosterEntry` 的參與紀錄——`0` 代表「尚無比賽紀錄」，前端據此判斷是否顯示對應文字（spec.md FR-007），而非誤判為並列最後一名。 |
| `total_wins` | `int` | 累計勝場數，本團自成立以來的所有已完成比賽（不分輪次，spec.md FR-004），彙總自組內所有歷史 `RosterEntry`。 |
| `total_losses` | `int` | 累計敗場數，定義同上。 |

`final_standings: list[FinalStandingRow]` 陣列本身的排列順序 MUST 直接
依 `rank` 由小到大排序（前端不需要也不應該再自行排序，比照 018 的既有
規則，憲章原則 X）。

### `MemberGroupHistoryResponse`（既有，`member/schemas.py`，新增 1 個欄位）

在既有 `group_id`／`group_name`／`my_stats`／`matches`／`page`／
`total_pages` 之外，新增：

| 欄位 | 型別 | 說明 |
|---|---|---|
| `final_standings` | `list[FinalStandingRow]` | 該團所有曾參與者（依 `member_id` 合併同一位會員的多筆歷史紀錄後）的最終排名，涵蓋範圍見 FR-002；MUST NOT 受既有 `nickname` 查詢參數（FR-004/FR-009 之比賽清單篩選）影響——與 `matches`/`my_stats` 是三個互相獨立的區塊（spec.md FR-001）。 |

## 新增的共用純函式（非資料表）

### `_assign_standard_competition_ranks(total_wins_in_order: list[int]) -> list[int]`

`group/service.py` 內的模組層級私有函式，輸入為「已依 `total_wins`
降冪排序」的勝場數列表，輸出為對應的 `rank` 列表（1-based，並列同號、
之後跳號）。`build_group_standings()`（018）與新增的
`build_group_final_standings()`（本 feature）皆呼叫此函式，取代原本各自
內嵌一份排序迴圈（research.md #2）——純函式、無副作用、不涉及資料庫。

### `build_group_final_standings(session: AsyncSession, group_id: uuid.UUID, *, viewer_member_id: uuid.UUID) -> list[FinalStandingRow]`

`group/service.py` 內新增的服務函式，實作 research.md #1 之查詢、依
`member_id` 分組合併、與彙總邏輯，`viewer_member_id` 用於計算每組的
`is_self`（research.md #4），回傳已依 `rank` 排序的 `FinalStandingRow`
列表。由 `member/service.py` 的 `get_member_group_history()` 呼叫（傳入
既有 `require_member` 解析出的 `member.id` 作為 `viewer_member_id`），
組進 `MemberGroupHistoryResponse.final_standings`。

## 狀態/邊界摘要

- 最終團隊排名的唯一資料來源是既有 `Match`/`MatchParticipant`/
  `RosterEntry` 資料，本 feature 不新增、不修改任何既有資料表的 schema。
- `final_standings` 是每次呼叫 `GET /members/me/groups/{group_id}/history`
  當下重新計算的唯讀衍生值，沒有自己的生命週期需要管理，也不會被快取／
  持久化——與 018 的 `rank`/`total_wins`/`total_losses` 同一設計原則。
- 不涉及任何即時廣播事件——本功能是快照式呈現（spec.md FR-012），重新
  載入頁面即可看到最新資料，不需要新的 Ably 事件（research.md 前言）。
- 同一位會員在同一團有多筆歷史 `RosterEntry`（先退出後又重新加入）——
  MUST 合併為 `final_standings` 中的同一列，統計彙總其全部參與期間的
  所有已完成比賽（research.md #1，落實 spec.md Edge Cases）；訪客則
  無法合併（沒有跨場次的穩定身份），每筆歷史 `RosterEntry` 各自成列。
