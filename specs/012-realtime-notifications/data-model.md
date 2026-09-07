# Data Model: 即時通知功能

本 feature 新增 **1 張資料表**（`notifications`），需要 1 個 Alembic
migration。不修改任何既有資料表。

## 新增實體

### `Notification`（`apps/api/app/domains/notification/models.py`）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `id` | `UUID` (pk) | |
| `member_id` | `UUID` (FK → `members.id`, `ondelete='CASCADE'`) | 通知的接收者（FR-009）。會員被刪除時（未來帳號刪除功能，見憲章「未來規劃事項」）通知一併清除，不留孤兒列。 |
| `type` | `String(32)` | 本次僅有合法值 `"friend_request"`；決定如何解讀 `source_id`（research.md #5）。未來新增類型（例如 `"group_invite"`）時只需擴充服務層與 schema，本欄位型別/資料表結構不變（FR-011）。 |
| `source_id` | `UUID` | 依 `type` 指向對應的來源事件列——`type="friend_request"` 時指向 `friend_requests.id`。**無 DB 層 FK 約束**（多型參照，research.md #5）。 |
| `read_at` | `TIMESTAMPTZ`，nullable | `NULL` = 未讀；非 `NULL` = 已讀時間戳（FR-005）。 |
| `created_at` | `TIMESTAMPTZ`，`server_default=now()` | 建立時間，即該則通知在列表中的排序依據（FR-004）。 |

**索引/約束**（research.md #8）：

- `ix_notifications_member_created`：(`member_id`, `created_at` DESC) — 列表分頁查詢。
- `ix_notifications_member_unread`：(`member_id`) `WHERE read_at IS NULL`（partial）— 未讀計數查詢（FR-006）。
- `uq_notifications_type_source_member`：UNIQUE (`type`, `source_id`, `member_id`) — 同一來源事件對同一會員 MUST NOT 重複建立通知。

**不變量**：

- 一旦建立即永久保留，MUST NOT 被應用邏輯刪除（FR-012；`member_id` 上的
  `ondelete='CASCADE'` 僅在會員帳號本身被刪除時才連帶清除，非本 feature
  範圍內會發生的路徑）。
- `read_at` 只能從 `NULL` 轉為一個時間戳，MUST NOT 被改回 `NULL`（沒有
  「標記未讀」的操作，FR-005/FR-007/FR-008 皆只描述單向的已讀轉換）。

**狀態機**：

```text
        會員點擊/開啟該則（FR-007）
        或「全部標示已讀」（FR-008）
unread ──────────────────────────→ read
（read_at = NULL）              （read_at = 建立當下的 now()）
```

單向、終態轉換；無其他狀態。

## 既有實體（本 feature 讀取，定義權屬 006-member-friends）

### `FriendRequest`（`apps/api/app/domains/friend/models.py`，唯讀）

`GET /notifications` 依通知的 `source_id` 批次查詢對應的
`FriendRequest` 列，取其 `status`（`pending`/`accepted`/`rejected`/
`unfriended`）供前端呈現「此申請目前的最新狀態」（Assumptions：即使已在
其他管道處理完畢，通知仍呈現最新狀態而非假裝待處理）。本 feature 不
寫入 `FriendRequest` 的任何欄位——`friend/service.py` 的
`create_friend_request()` 仍是唯一寫入者，僅額外呼叫
`notification.service.create_friend_request_notification()`（見
research.md #4）。

### `Member`（`apps/api/app/domains/member/models.py`，唯讀）

用於組出通知列表中申請人的顯示資訊（`nickname`/`user_number`），與
`friend/service.py` 既有的 `list_incoming_requests()` 完全相同的查詢
慣例——即時查詢，不快照（research.md #5）。

## 新增的唯讀組合視圖（API 回應形狀，非資料表）

### `NotificationSummary`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `notification_id` | `str` | |
| `type` | `"friend_request"` | 目前唯一合法值；未來新增類型時擴充此聯合型別。 |
| `read` | `bool` | `read_at IS NOT NULL`（FR-005，前端不需自行判斷時間戳）。 |
| `created_at` | `str`（ISO 8601, UTC） | |
| `friend_request` | `FriendRequestNotificationDetail \| null` | `type = "friend_request"` 時必定非 null；未來新增類型時比照新增一個對應的 nullable 欄位（例如 `group_invite`），不改變既有欄位形狀（FR-011）。 |

### `FriendRequestNotificationDetail`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `friend_request_id` | `str` | |
| `status` | `"pending" \| "accepted" \| "rejected" \| "unfriended"` | 該筆好友申請目前的最新狀態（即時查詢，見上）。 |
| `requester` | `FriendSummary`（重用 `app.domains.friend.schemas.FriendSummary`） | 送出申請的會員（`member_id`/`nickname`/`user_number`）。 |

### `NotificationListResponse`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `notifications` | `list[NotificationSummary]` | 依 `created_at` 新到舊排序（FR-004）。 |
| `unread_count` | `int` | 與 `GET /notifications/unread-count` 相同定義，一併回傳供列表頁頁首顯示。 |
| `page` | `int` | |
| `total_pages` | `int` | |

### `UnreadCountResponse`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `unread_count` | `int` | 精確值；封頂顯示（「99+」）為前端呈現邏輯，後端一律回傳精確數字（FR-006）。 |

### `MarkAllReadResponse`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `marked_count` | `int` | 本次操作實際轉為已讀的筆數（原本已讀的不計入）。 |

## Key Entities 對照 spec.md

- **Notification（通知）**（spec.md `## Key Entities`）：對應上方
  `Notification` 實體，`type`/`source_id` 的多型設計即 spec 所述「資料
  結構須可擴充其他類型」的具體實作（FR-011）。
- **Member（會員）**：唯讀，定義權屬 006。
- **FriendRequest（好友申請）**：唯讀，定義權屬 006；本次唯一會觸發
  `Notification` 建立的來源事件類型。
