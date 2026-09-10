# Data Model: 團內即時排行榜（強化既有戰績頁）

本 feature **不新增任何資料表、不需要新的 migration**（research.md 前言）。
以下記錄既有回應形狀的擴充、既有查詢條件的變更，以及新增的即時事件形狀
（非資料表）。

## 既有實體（本 feature 讀取/沿用，定義權屬其他 spec）

### `Match` / `MatchParticipant`（既有，唯讀，本 feature 完全不修改）

戰績頁排名的統計基礎——沿用既有 `status == "completed"` 的比賽與其
`winner_team`/`team` 欄位推算每位現役成員的勝敗場次，邏輯與既有
`build_group_standings()` 的逐輪累計完全相同，只是額外做一次總計與排序
（research.md #2）。

### `RosterEntry`（既有，唯讀，查詢條件有變更）

沿用既有 `joined_at` 作為並列名次的次要排序依據（research.md #2/#6）。
**查詢條件變更**：既有 `roster_result` 查詢新增 `RosterEntry.status ==
"active"` 過濾（research.md #3）——只有目前現役的成員會出現在戰績頁的
`members` 清單中；已離開/被踢除者的過去對戰貢獻仍正確反映在其現役對手
的統計上，因為這部分計算來源是 `MatchParticipant`，不受這個過濾影響。

## 既有 API 回應形狀的擴充（`GET /groups/{group_id}/standings`）

### `MemberStandingRow`（既有，新增 3 個唯讀欄位）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `roster_entry_id` | `str`（既有） | 不變。 |
| `nickname` | `str`（既有） | 不變。 |
| `current_status` | `Literal["active", "left", "kicked"]`（既有） | 不變——過濾後這個欄位在戰績頁的回應中恆為 `"active"`（research.md #3），保留欄位本身是因為既有 schema 不拆分成兩個不同形狀。 |
| `rounds` | `dict[int, RoundRecord]`（既有） | 不變，逐輪細目予以保留（spec.md Assumptions）。 |
| `rank` | `int`（新增） | 依 `total_wins` 排序後的名次，並列時同一數字，之後的名次依人數跳號（standard competition ranking，research.md #6）。 |
| `total_wins` | `int`（新增） | 該成員 `rounds` 內所有輪次 `wins` 的加總——即既有前端 `totalRecord().wins`，改為後端直接算好回傳，維持單一計算來源（憲章原則 X，research.md #2）。 |
| `total_losses` | `int`（新增） | 同上，`losses` 的加總。 |

`members` 陣列本身的排列順序 MUST 直接依 `rank` 由小到大排序（前端不需要
也不應該再自行排序——research.md #2）。

### `GroupStandingsResponse`（既有，欄位不變）

`current_round_number`、`rounds`（已產生過的輪次清單）維持既有定義，
`members` 如上所述新增 3 個欄位並依 `rank` 排序。

## 新增的即時事件（Ably，非資料表）

### `standings.updated`（新增，發布於既有 `group_notifications_channel(group_id)`）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `group_id` | `str` | 純粹作為觸發訊號，前端收到後直接整包重新呼叫 `GET /groups/{group_id}/standings`，不使用 payload 內容做任何增量計算（research.md #1，維持憲章原則 X 之單一計算來源）。 |

發布時機：`_publish_match_ended()`（`schedule/service.py`）——全系統唯一
會把 `Match.status` 設為 `"completed"` 的呼叫路徑之後（research.md #1）。
`abandoned`（提前結束/捨棄）路徑 MUST NOT 觸發本事件——捨棄的比賽本來就
不計入任何人的戰績（spec.md FR-005），排名不會因此改變，沒有必要重新
整理畫面。

## 狀態/邊界摘要

- 戰績頁排名的唯一資料來源是既有 `Match`/`MatchParticipant`/`RosterEntry`
  資料，本 feature 不新增、不修改任何既有資料表的 schema。
- `rank`/`total_wins`/`total_losses` 三個新欄位是每次呼叫
  `GET /groups/{group_id}/standings` 當下重新計算的唯讀衍生值，沒有
  自己的生命週期需要管理，也不會被快取／持久化。
- `standings.updated` 事件本身不攜帶任何排名結果，純粹是「請重新拉取」
  的訊號——即使事件遺失（例如短暫斷線），FR-012／research.md #4 的
  reconnect-refetch 機制也保證使用者重新連線/回到畫面時會拿到正確狀態，
  不依賴每一則事件都必須送達。
