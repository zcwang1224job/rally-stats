# Phase 1 Data Model: 會員與好友系統

沿用 `specs/architecture.md` §2.2 既有 DDL（`members`、`email_verification_tokens`、`password_reset_tokens`、`friend_requests`）。`members` 表已由 001 之初始 migration 建立最小 stub（`id`/`nickname`/`created_at`），本 feature 以 **ALTER TABLE** 補齊其餘欄位，其餘三張表為全新建立。

## 1. `members`（ALTER 既有表）

| 欄位 | 型別 | 約束 | 說明 |
|---|---|---|---|
| `id` | UUID | PK（既有） | |
| `email` | VARCHAR(255) | **新增**，NOT NULL，唯一索引 `ux_members_email` | 已正規化小寫；ALTER 時對既有 stub 資料無影響（目前無真實會員資料） |
| `password_hash` | VARCHAR(255) | **新增**，NOT NULL | bcrypt |
| `nickname` | VARCHAR(20) | 既有，改為可為 NULL 的語意確認（NULL = 尚未完成首次暱稱設定，FR-012） | |
| `user_number` | VARCHAR(8) | **新增**，NOT NULL，唯一索引（大小寫不敏感）`ux_members_user_number_ci` | 原始大小寫保留顯示 |
| `verification_status` | VARCHAR(16) | **新增**，NOT NULL，預設 `'unverified'` | `unverified \| verified` |
| `token_version` | INT | **新增**，NOT NULL，預設 `0` | JWT 失效機制（research.md #2） |
| `created_at` | TIMESTAMPTZ | 既有 | |

**狀態轉換**：`verification_status`：`unverified → verified`（單向，透過 Email 驗證連結點擊、或忘記密碼重設成功，FR-008/FR-014）。

## 2. `email_verification_tokens`（新建）

| 欄位 | 型別 | 約束 |
|---|---|---|
| `id` | UUID | PK |
| `member_id` | UUID | FK → `members(id)` ON DELETE CASCADE |
| `token` | UUID | 唯一索引 `ux_evt_token`，`gen_random_uuid()` |
| `expires_at` | TIMESTAMPTZ | NOT NULL（建立時間 + 24 小時） |
| `used_at` | TIMESTAMPTZ | nullable；非 NULL 代表已使用過 |
| `created_at` | TIMESTAMPTZ | NOT NULL |

**生命週期**：註冊成功時建立一筆 → 使用者點擊連結時：`expires_at` 未過期且 `used_at IS NULL` → 標記 `used_at = now()` + `members.verification_status = 'verified'`；同一會員的舊未使用 token（例如觸發過「重新發送」）在新 token 建立時不主動失效——比對邏輯僅檢查該筆 token 本身是否過期/已使用，允許多組同時有效的驗證連結並存（使用者點擊任一封信中的連結皆可完成驗證），簡化實作且不影響安全性（驗證動作本身冪等）。

## 3. `password_reset_tokens`（新建）

| 欄位 | 型別 | 約束 |
|---|---|---|
| `id` | UUID | PK |
| `member_id` | UUID | FK → `members(id)` ON DELETE CASCADE |
| `token` | UUID | 唯一索引 `ux_prt_token` |
| `expires_at` | TIMESTAMPTZ | NOT NULL（建立時間 + 1 小時，重設密碼風險較高，效期短於驗證信） |
| `used_at` | TIMESTAMPTZ | nullable |
| `created_at` | TIMESTAMPTZ | NOT NULL |

**生命週期**：`POST /auth/forgot-password` 建立一筆 → `POST /auth/reset-password/{token}` 驗證未過期/未使用 → 標記 `used_at`、更新 `password_hash`、`verification_status='verified'`、`token_version += 1`（FR-014/FR-015）。

## 4. `friend_requests`（新建）

| 欄位 | 型別 | 約束 |
|---|---|---|
| `id` | UUID | PK |
| `requester_id` | UUID | FK → `members(id)` |
| `addressee_id` | UUID | FK → `members(id)`；CHECK `requester_id <> addressee_id` |
| `status` | VARCHAR(16) | NOT NULL，預設 `'pending'`：`pending \| accepted \| rejected \| unfriended` |
| `created_at` | TIMESTAMPTZ | NOT NULL |
| `updated_at` | TIMESTAMPTZ | NOT NULL，狀態轉換時更新 |

**唯一性約束**：`ux_friend_requests_pending_pair`——`(LEAST(requester_id, addressee_id), GREATEST(requester_id, addressee_id))` 部分唯一索引（`WHERE status = 'pending'`），確保同一組使用者任何時刻最多一筆待處理邀請，不分發起方向（FR-039）。

**狀態機**：
```
pending --accept--> accepted --unfriend--> unfriended
pending --reject--> rejected
```
`rejected`/`unfriended` 皆為終態，但 MUST NOT 阻擋重新發送邀請——重新發送建立**新的一列**（FR-042/FR-046），不修改舊列狀態；因唯一索引僅約束 `pending` 狀態，舊的 `rejected`/`unfriended` 列與新的 `pending` 列可同時存在。

## 5. `roster_entries`（既有欄位語意確認，無 schema 變更）

`nickname` 欄位（001 既有）為獨立欄位，本 feature 不新增/修改任何欄位；`PATCH /members/me/nickname` 僅更新 `members.nickname`，見 research.md #10。

## Pydantic Schema 對應（`app/domains/member/schemas.py`、`app/domains/friend/schemas.py`）

- `RegisterRequest`：`email`、`password`、`confirm_password`、`turnstile_token`
- `LoginRequest`：`email`、`password`
- `LoginResponse` / `RefreshResponse`：`access_token`、`refresh_token`（僅 login 回傳）、`member` 摘要
- `MemberPublicResponse`：`member_id`、`email`、`nickname`、`user_number`、`verification_status`
- `SetNicknameRequest`：`nickname`
- `ChangePasswordRequest`：`current_password`、`new_password`、`confirm_new_password`
- `ForgotPasswordRequest`：`email`
- `ResetPasswordRequest`：`new_password`、`confirm_new_password`
- `SearchMemberResponse`：`member_id`、`nickname`、`user_number`、`friendship_status`（`none \| pending_outgoing \| pending_incoming \| friends`）
- `FriendRequestCreate`：`addressee_user_number`
- `FriendListResponse`：分頁好友列表（`member_id`、`nickname`、`user_number`）
- `IncomingFriendRequestResponse`：待回覆邀請列表
