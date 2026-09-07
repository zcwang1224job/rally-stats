# Data Model: 邀請好友加入組團

本 feature 新增 **1 張資料表**（`group_invites`），需要 1 個 Alembic
migration。另修改 2 個既有回應形狀（`GroupPublicResponse` 新增欄位、
`NotificationSummary` 擴充 `type` 與新增巢狀欄位），不修改任何既有資料表
結構。

## 新增實體

### `GroupInvite`（`apps/api/app/domains/group_invite/models.py`）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `id` | `UUID` (pk) | |
| `group_id` | `UUID` (FK → `groups.id`) | 所屬團。 |
| `inviter_member_id` | `UUID` (FK → `members.id`) | 送出邀請的團長——恆等於 `group.created_by_member_id`（FR-001），獨立存欄位是為了查詢方便，不需每次都 join `groups` 表。 |
| `invitee_member_id` | `UUID` (FK → `members.id`) | 受邀好友。 |
| `status` | `String(16)` | `pending`／`accepted`／`declined`／`invalidated`（research.md #5）。 |
| `created_at` | `TIMESTAMPTZ` | |
| `updated_at` | `TIMESTAMPTZ` | 狀態轉換時更新，比照 `FriendRequest` 既有慣例。 |

**索引/約束**（research.md #6）：

- `ux_group_invites_pending_invitee`：UNIQUE (`group_id`, `invitee_member_id`) `WHERE status = 'pending'` — 同一團對同一好友，「待回覆」狀態至多一筆（FR-003）。
- `ix_group_invites_group_invitee_created`：(`group_id`, `invitee_member_id`, `created_at` DESC) — 供 research.md #8 之「取該好友在本團最新一筆邀請」查詢。

**狀態機**（research.md #5）：

```text
                 送出邀請
                    │
                    ▼
                pending ──接受成功──────────→ accepted
                    │
                    ├──拒絕────────────────→ declined
                    │
                    └──好友關係解除／團解散──→ invalidated
```

`pending` 為唯一非終態；其餘三者皆為終態，不可逆轉換。接受時因額滿而
失敗（FR-013）**不**觸發狀態轉換，`pending` 原地不動。

## 既有實體（本 feature 讀取／擴充，定義權屬其他 spec）

### `Group`（001/003 owns，`apps/api/app/domains/group/models.py`）

- 讀：`created_by_member_id`（判斷本團是否為會員建立，FR-012；等於發送
  邀請所需的 `inviter_member_id`）、`max_members`/`current_member_count`
  （由重用的 `join_group()` 內部判斷，本 feature 不重新查詢）、
  `password_ciphertext`/`password_nonce`（`skip_password=True` 時完全
  不讀取，research.md #3）。
- 寫：本 feature 不直接寫入 `Group` 的任何欄位——`disband_group()`
  既有邏輯不變，只是新增一個可選 hook 讓 `group_invite` 模組在同一交易
  內順便標記受影響的 `GroupInvite`（research.md #2）。
- **擴充**：`GroupPublicResponse`（回應形狀，非資料表）新增
  `created_by_member: bool` 欄位（research.md #9）。

### `Member`（006 owns，唯讀）

邀請人與受邀人皆為會員身分（FR-001/FR-002）。

### `FriendRequest` / 好友關係（006 owns，唯讀）

`get_friendship_status()` 判斷團長與目標會員是否為 `"friends"`——
FR-002 送出邀請前的必要條件。`unfriend()`（既有函式）新增一個可選 hook
參數，讓好友關係解除時能順便標記受影響的 `GroupInvite`
（research.md #2、FR-014），但 `FriendRequest` 本身的資料表結構、狀態機
完全不變。

### `RosterEntry`（001/003 owns，唯讀）

`GET /groups/{group_id}/invitable-friends` 用來判斷某位好友是否已是本團
`status='active'` 的現有成員（`already_member`，research.md #8、
FR-004）。接受邀請時透過重用的 `join_group()` 寫入新的 `RosterEntry`
列，寫入邏輯完全不變（research.md #3）。

### `Notification`（012 owns，擴充）

新增兩種 `type` 值（`"group_invite"`／`"group_invite_capacity_full"`），
`source_id` 皆指向 `GroupInvite.id`。**擴充**
`NotificationSummary`/`FriendRequestNotificationDetail` 所在的
schemas 模組，新增 `GroupInviteNotificationDetail` 巢狀欄位
（research.md #7）；`notifications` 資料表結構本身不變。

## 新增的唯讀組合視圖（API 回應形狀，非資料表）

### `InvitableFriendSummary`（`GET .../invitable-friends` 的陣列項目）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `member_id` | `str` | |
| `nickname` | `str \| null` | |
| `user_number` | `str` | |
| `invite_status` | `"not_invited" \| "pending" \| "accepted" \| "declined" \| "invalidated" \| "already_member"` | research.md #8 之組合判斷結果。 |
| `invite_id` | `str \| null` | 對應的 `GroupInvite.id`（`not_invited`/`already_member`——且從未被邀請過——時為 `null`）。 |

### `GroupInviteDetailResponse`（`GET /group-invites/{invite_id}`，受邀好友視角）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `invite_id` | `str` | |
| `status` | 同上 `GroupInvite.status` | 即時值，非快照。 |
| `group_id` | `str` | |
| `group_name` | `str` | |
| `inviter_nickname` | `str \| null` | |

### `AcceptGroupInviteResponse`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `group_id` | `str` | 供前端導向該團的一般成員視圖。 |
| `roster_entry_id` | `str` | |
| `nickname` | `str` | |

### `GroupInviteNotificationDetail`（見 `contracts/notification-api-additions.md`）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `invite_id` | `str` | |
| `group_id` | `str` | |
| `group_name` | `str` | |
| `status` | 同上 `GroupInvite.status` | |
| `inviter` | `FriendSummary`（重用 012/006 既有形狀） | |
| `invitee` | `FriendSummary` | |

## Key Entities 對照 spec.md

- **GroupInvite（組團邀請）**：對應上方新增實體，四態狀態機即 spec
  Key Entities 段落所述「待回覆／已接受／已拒絕／已失效」的具體實作。
- **Group（團）**：唯讀 + `GroupPublicResponse` 的一個新增旗標欄位。
- **Member（會員）**：唯讀，定義權屬 006。
- **FriendRequest / 好友關係**：唯讀 + 一個新增的可選 hook 參數，定義權
  屬 006。
- **Notification（通知）**：擴充既有回應形狀，定義權屬 012。
