# Data Model: 開團流程優化——合理預設值與自動預設場地

本 feature **不新增任何資料表、不需要新的 migration**（research.md 前言）。
以下記錄既有請求形狀的調整、既有服務函式內部行為的擴充，以及兩個新增的
模組層級常數（非資料表）。

## 既有實體（本 feature 讀取/沿用，定義權屬其他 spec）

### `Group`（既有，001-create-manage-group，本 feature 不改變 schema）

沿用既有 `name` 欄位（`String`，既有 1–30 字長度限制不變）。本 feature
只改變「請求中 `name` 留空時，`Group.name` 最終寫入什麼值」這一段
服務層邏輯（research.md #1），不改變欄位本身的型別或長度限制。

### `RosterEntry`（既有，001-create-manage-group，唯讀，計算時機調整）

沿用既有「建立者暱稱」欄位。本 feature 唯一的調整是把
`create_group()` 內原本用來組出 `RosterEntry.nickname` 的暱稱計算
時機提前，讓同一個已算出的值也能拿來組預設團名（research.md #1）——
`RosterEntry` 本身的欄位與既有語意完全不變。

### `Court`（既有，002-court-management，本 feature 不改變 schema）

沿用既有 `name`（`String(20)`）、既有 `ux_courts_group_name_active`
部分唯一索引（同團內現役球場名稱不可重複）、既有
`scoreboard_token`/`control_panel_token`（更名 MUST NOT 影響這兩者，
`rename_court()` 本來就只更新 `name` 欄位，research.md #3）。本
feature 新增的是「團建立時自動插入一筆 `Court` 記錄」這個新的資料
產生路徑，schema 本身不變。

## 新增的模組層級常數（非資料表）

### `group/service.py`

| 常數 | 值 | 說明 |
|---|---|---|
| `_DEFAULT_GROUP_NAME_SUFFIX` | `"的羽球團"` | 團名留空時，與建立者暱稱組合成預設團名（research.md #1，spec.md FR-001）。 |
| `_DEFAULT_COURT_NAME` | `"球場一"` | 團建立時自動建立的球場名稱（research.md #2，spec.md FR-006）。 |

## 既有請求形狀的調整

### `CreateGroupRequest`（既有，`group/schemas.py`，`name` 欄位型別調整）

| 欄位 | 既有型別 | 調整後型別 | 說明 |
|---|---|---|---|
| `name` | `str`（必填） | `str \| None = None` | `field_validator` 改為：`None` 或去除頭尾空白後為空字串時，正規化為 `None`（視同未提供）；非空時維持既有 1–30 字長度檢查不變（research.md #1，spec.md FR-001、Edge Cases）。 |

其餘欄位（`max_members`／`match_mode`／`scheduling_mechanism`／
`creator_nickname` 等）**維持既有型別與必填語意不變**
（research.md #4）。

## 既有服務函式行為的擴充

### `create_group(session, payload, *, member) -> tuple[Group, RosterEntry, str, str | None]`（既有，`group/service.py`，回傳型別不變）

- 既有暱稱計算時機提前（research.md #1）：`resolved_nickname =
  member.nickname if member else stripped_creator_nickname`，緊接在
  既有暱稱驗證檢查（`MEMBER_NICKNAME_NOT_SET`／
  `NICKNAME_REQUIRED_FOR_GUEST`）之後計算，供「組出 `Group.name`」與
  「組出 `RosterEntry.nickname`」共用同一個值。
- `Group.name` 的寫入值：`payload.name if payload.name else
  f"{resolved_nickname}{_DEFAULT_GROUP_NAME_SUFFIX}"`。
- 新增：在既有 `session.add(roster_entry)` 之後、既有唯一一次
  `await session.commit()` 之前，`session.add(Court(group_id=group.id,
  name=_DEFAULT_COURT_NAME))`（research.md #2）。
- commit 後新增：`await session.refresh(court)`，並對
  `group_notifications_channel(str(group.id))` 發布既有
  `court.added` 事件（payload 形狀與既有 `create_court()` 完全相同：
  `{"court_id": str(court.id), "name": court.name}`）。
- 回傳型別**不變**（`tuple[Group, RosterEntry, str, str | None]`）——
  自動建立的 `Court` 不需要回傳給呼叫端，既有
  `GET /groups/{group_id}/courts` 端點會在前端載入管理頁時自然查到它
  （沿用既有查詢邏輯，不需額外處理）。

### `rename_court(session, court, payload) -> Court`（既有，`court/service.py`，行為完全不變）

本 feature **不修改**此函式的任何邏輯——research.md #3 已確認其既有
行為（`COURT_DELETED` 檢查、`IntegrityError` → `COURT_NAME_ALREADY_
EXISTS`、只更新 `name` 不動 token 欄位）已經完全符合 spec.md
FR-009~FR-011 的要求，只是先前從未被任何畫面呼叫、也從未被測試覆蓋。

## 狀態/邊界摘要

- 預設團名與自動建立的球場皆是 `create_group()` 這單一次呼叫、單一個
  資料庫交易內的產物——沒有獨立的生命週期，也不會有「團建立成功但
  預設球場沒建立成功」的中間態（research.md #2，spec.md FR-007）。
- 自動建立的「球場一」建立完成後即為一筆普通的現役 `Court` 記錄，與
  手動新增的球場在資料上完全無法區分（沒有任何「這是自動建立」的
  標記欄位），因此天生就滿足 FR-008「不得有任何特殊限制」的要求——
  不是靠額外程式碼刻意放行，而是資料模型本身沒有機制可以區分兩者。
- 球場更名這條路徑的資料流完全沿用既有 `rename_court()`，本 feature
  在資料層面沒有任何新增或變更。
