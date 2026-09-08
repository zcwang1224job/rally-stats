# Data Model: 團長手動新增訪客入團

本 feature **不新增任何資料表，也不修改任何既有資料表結構**（research.md
#1）——手動新增的訪客與自行加入的訪客，在資料層完全是同一種
`RosterEntry`，唯一差別是「由誰觸發建立動作」，這個差異不需要、也不應該
反映在資料模型裡。

## 既有實體（本 feature 讀取/寫入，定義權屬其他 spec）

### `RosterEntry`（001/003/004 owns，本 feature 透過既有 `join_group()` 寫入，不直接操作）

沿用 004-join-group 既有欄位語意，重點提醒：

| 欄位 | 說明（與本 feature 相關部分） |
|---|---|
| `member_id` | 本 feature 建立的項目一律為 `NULL`（訪客），與自行加入的訪客完全相同 |
| `nickname` | 由團長輸入，驗證規則沿用既有（1–20 字，去除頭尾空白），MUST NOT 額外要求唯一性 |
| `status` | 建立時為 `"active"`，後續可被既有踢人功能改為 `"kicked"`，無新狀態值 |
| `wait_count` | 建立時為 `NULL`（「尚未上場」既有 sentinel 值），行為與自行加入的訪客一致 |
| `guest_session_token` | 建立時產生（`secrets.token_urlsafe(32)`），本 feature US2 的分享連結即以此 token 為核心 |
| `is_creator` | 恆為 `False`（團長本人的項目在開團當下就已建立，不會透過本 feature 重複建立） |

### `Group`（001 owns，唯讀 + 既有的 atomic 人數計數更新）

- 讀：`id`／`status`／`current_member_count`／`max_members`——沿用
  `join_group()` 既有的人數上限檢查與已解散團擋下邏輯，本 feature 不新增
  查詢。

## 新增的 API 請求/回應形狀（非資料表）

### `AddGuestRequest`（新增）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `nickname` | `str` | 必填，1–20 字（去除頭尾空白後驗證），驗證規則與訊息沿用既有 `NICKNAME_REQUIRED_FOR_GUEST` |

刻意不包含 `password` 欄位——管理員身份本身已是授權來源
（research.md #1），與公開的 `JoinGroupRequest` 語意不同，不應該讓 API
使用者誤以為需要提供密碼。

### 回應：沿用既有 `JoinGroupResponse`（不新增欄位）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `roster_entry_id` | `str` | 新建立的花名冊項目 ID |
| `nickname` | `str` | 建立後的暱稱（去除頭尾空白後的版本） |
| `guest_session_token` | `str \| None` | 本 feature 一律非 `None`（訪客一定會有 token）；US2 的分享連結即由此組成 |
| `created_new` | `bool` | 本 feature 一律為 `True`（訪客沒有既有身份可供短路判斷，每次呼叫都是全新項目） |

## 狀態/邊界摘要

- 手動新增的訪客與自行加入的訪客，在「是誰的資料」這個問題上沒有分別
  ——查詢輪替名單、比賽紀錄、戰績統計的既有邏輯，MUST NOT 需要因應本
  feature 做任何修改（若需要修改，代表本 feature 的重用設計出了問題）。
- 分享連結（US2）的有效期與既有 `guest_session_token` 完全一致，沒有
  獨立的過期時間或使用次數限制——這是既有 004-join-group 的既有屬性，
  本 feature 不改變它。
