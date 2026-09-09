# Data Model: 固定搭檔循環賽——手動配對後，剩餘未配對者自動隨機配對

本 feature **不新增任何資料表、不需要新的 migration**（research.md #1）。
以下記錄唯讀/唯寫查詢範圍的擴充，以及新增的 API 請求/回應形狀（非資料表）。

## 既有實體（本 feature 讀取/沿用，定義權屬其他 spec）

### `Partnership`（011 owns，唯讀，本 feature 完全不修改此實體本身）

正式搭檔配對，`(player_a_id, player_b_id)`，一位現役成員同時只能有一組
有效的正式搭檔。本 feature 讀取既有 `_get_active_partnership_teams()`
（`schedule/service.py:509`）取得目前所有正式搭檔，藉此推算「誰還沒有
正式搭檔」；本 feature MUST NOT 新增、修改、刪除任何 `Partnership` 列。

### `RosterEntry`（001/003 owns，唯讀）

沿用既有 `_get_active_roster_ordered()`（`schedule/service.py:1018`，
依 `joined_at` 排序）取得現役成員清單，用於計算「現役成員」－「已有正式
搭檔的成員」＝「目前未配對的現役成員」。

## 新增的暫時性概念（API 請求/回應形狀，非資料表——research.md #1）

### `TemporaryPairing`（暫時隨機配對，前端草稿狀態 + API 傳輸格式，不持久化）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `player_a` | `RosterSummary`（既有形狀） | 暫時配對的其中一位（`roster_entry_id`／`nickname`）。 |
| `player_b` | `RosterSummary`（既有形狀） | 暫時配對的另一位。 |

與正式 `PartnershipSummary`（`schedule/schemas.py:94`）刻意不同：**沒有
`partnership_id`**——因為它從來不是一筆被寫入資料庫、有主鍵可以指向的
資料列，只是「這一輪要用哪些配對」這個請求當下的一組資料（research.md
#1）。

### `TemporaryPairingsResponse`（新增，`POST
/groups/{group_id}/partnerships/random-preview` 的回應）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `pairings` | `list[TemporaryPairing]` | 針對呼叫當下所有「未配對現役成員」算出的隨機配對結果，每次呼叫都重新計算（FR-001，Edge Cases「多次觸發」）。 |

### `NextRoundRequest`（新增，`POST /groups/{group_id}/next-round` 既有
端點新增的**可選**請求 body——目前此端點完全無 body，此為新增，非修改
既有欄位）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `temporary_pairings` | `list[TemporaryPairingInput]`，預設 `[]` | 管理員在產生賽程前，透過 `random-preview` 預覽並可能調整過的暫時配對結果；省略或空陣列＝管理員沒有預覽過，由後端在產生賽程當下自行補齊（FR-002）。`partner_source != "manual"` 或 `scheduling_mechanism != "fixed_partner"` 時，此欄位 MUST 被忽略（FR-005，US3 回歸驗證——其餘機制的既有呼叫端不需要改動，省略此欄位即可維持既有行為）。 |

`TemporaryPairingInput`：`{ player_a_id: str, player_b_id: str }`（與既有
`PartnershipReassignRequest` 的欄位命名一致，`schedule/schemas.py:105`）。

## 賽程產生時的暫時配對驗證/補齊邏輯（`_generate_fixed_partner_matches()` 擴充）

「手動配對」模式下，產生賽程時的隊伍來源，由原本單純的「既有正式搭檔」
擴充為以下三段的聯集：

1. **正式搭檔**（既有 `_get_active_partnership_teams()`，不變）。
2. **驗證通過的 `temporary_pairings`**——請求帶進來的暫時配對中，MUST
   只保留雙方都仍然是「目前確實未配對的現役成員」的組合（Edge Cases 之
   重新驗證規則）；任一方已經有正式搭檔、已離開/被踢除、或同一人在清單
   中被使用超過一次的組合，MUST 被捨棄。
3. **自動補齊的隨機配對**（新，research.md #3 `random_pair_units()`）——
   步驟 1+2 之後，現役成員中仍然沒有被涵蓋到的人，MUST 在這裡當場隨機
   兩兩配對補齊（FR-002）。

三段聯集之後的完整隊伍清單，才交給既有的 `round_robin_pairs(teams,
start_swapped=...)` 產生賽程（既有邏輯不變）。

## 狀態/邊界摘要

- 正式搭檔資料的唯一產生方式仍然是既有三種（管理員手動指定、系統依加入
  順序自動湊對、既有一次性 fallback）——本 feature MUST NOT 新增第四種
  「正式」搭檔的產生方式（research.md #1）。
- `temporary_pairings` 只在「產生下一輪賽程」這一個請求的處理過程中有
  意義，處理完（不論賽程產生成功與否）即不再有任何殘留狀態——沒有生命
  週期需要管理，因為它從未被儲存過。
- `partner_source == "auto"` 時，`_generate_fixed_partner_matches()` 完全
  不進入「手動配對」分支，`temporary_pairings` 欄位無論傳什麼都 MUST 被
  忽略（US3）。
