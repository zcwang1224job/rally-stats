# Data Model: 使用 Google／LINE 帳號註冊與登入

決策依據見 research.md。

## 1. `Member`（既有實體，`app/domains/member/models.py`）— 兩個既有欄位改為可為空

| 欄位 | 舊型別 | 新型別 | 說明 |
|---|---|---|---|
| `email` | `String(255) NOT NULL` | `String(255) NULL` | research.md #4。`None` 代表「透過 LINE 首次授權建立、當次未取得 Email 的帳號」（FR-004）。 |
| `password_hash` | `String(255) NOT NULL` | `String(255) NULL` | research.md #4。`None` 代表「純 OAuth 帳號，從未設定過密碼」。 |

既有唯一索引 `ux_members_email`（`ux_members_email ON members(email)`）
改為部分唯一索引：

```python
op.drop_index("ux_members_email", table_name="members")
op.create_index(
    "ux_members_email",
    "members",
    ["email"],
    unique=True,
    postgresql_where=sa.text("email IS NOT NULL"),
)
```

其餘既有欄位（`id`／`nickname`／`user_number`／`verification_status`／
`token_version`／`created_at`／`language_preference`／`allow_search`／
`share_match_records_with_friends`／
`allow_friend_invite_from_match_pages`／`deleted_at`）語意不變。

**受影響的既有讀取點**（皆須新增 `is None` 分支，見 research.md #7/#9）：

- `app/domains/member/service.py` `delete_account()`／`change_password()`
  — `password_hash is None` 時略過舊密碼驗證。
- 任何寄信路徑（既有驗證信／忘記密碼信／好友邀請等既有通知信）— 寄信前
  MUST 檢查 `member.email is not None`，`None` 時略過寄信（不可對
  `None` 呼叫既有 `send_email()`）。本 feature 範圍內受影響的既有函式：
  `_issue_verification_token_and_email()`（僅在呼叫端已知 email 非空
  時才呼叫，OAuth 建立帳號的新路徑本就不呼叫它，見 research.md #6）。
  忘記密碼流程（`forgot_password()`）本就以「輸入 Email 找帳號」為
  入口，`email IS NULL` 的帳號天然不會被這支既有函式查到，無需額外
  改動。
- 前端顯示 Email 的既有畫面（個人設定／`MemberPublicResponse.email`
  若前端有直接顯示）— `email` 若為 `null`，MUST 顯示「尚未設定」而非
  空字串或崩潰；後端 `MemberPublicResponse.email` 型別同步改為
  `str | None`。

## 2. `member_oauth_identities`（新增資料表）

一個會員帳號與一個外部身分提供者帳號之間的關聯（research.md #5）：

| 欄位 | 型別 | 說明 |
|---|---|---|
| `id` | `UUID PRIMARY KEY` | `default=uuid.uuid4`，比照既有慣例。 |
| `member_id` | `UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE` | 索引（既有 migration 慣例：FK 一律建索引，見 `3912de8ceb6c_index_foreign_keys.py` 先例）。 |
| `provider` | `String(16) NOT NULL` | `"google"` \| `"line"`。 |
| `provider_user_id` | `String(255) NOT NULL` | 該 provider 回傳 `id_token` 的 `sub` claim。 |
| `email_at_link` | `String(255) NULL` | 綁定當下 provider 回傳的 Email（僅供「個人設定」顯示「已綁定 xxx@gmail.com」使用，非登入判斷依據——判斷依據永遠是 `provider_user_id`）。 |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |

**約束**：

```python
op.create_unique_constraint(
    "ux_member_oauth_identities_provider_user",
    "member_oauth_identities",
    ["provider", "provider_user_id"],
)  # FR-007：同一個外部帳號不可重複綁定到另一個會員
op.create_unique_constraint(
    "ux_member_oauth_identities_member_provider",
    "member_oauth_identities",
    ["member_id", "provider"],
)  # FR-006：每個 provider 每個會員最多一個綁定
```

**應用層行為**（/speckit-analyze 2026-09-14 remediation C1）：`intent=link`
時，若呼叫者自己在該 `provider` 已有一筆不同的既有綁定，服務層 MUST
在寫入前查出這個情況並直接拒絕（`OAUTH_PROVIDER_ALREADY_LINKED`），
MUST NOT 嘗試刪除舊綁定後插入新綁定（即不做「取代」語意）——上面的
`ux_member_oauth_identities_member_provider` 唯一索引因此永遠只是
最終防線（防併發 race condition，見 contracts/oauth-login-api.md
「併發防護」段落），不是應用層唯一依賴的判斷依據。

`ON DELETE CASCADE`：`Member` 列本身從不被硬刪除（025-delete-account
的匿名化就地保留列），此設定僅為referential-integrity 完整性慣例，
實務上不會觸發。

## 3. `member_oauth_identities` 與既有 `Member.verification_status`／
`Member.deleted_at` 的互動

- 新建立的 OAuth-only 帳號：`verification_status = "verified"`
  （research.md #6）。
- `deleted_at IS NOT NULL` 的帳號（025-delete-account）透過其原本
  綁定的 `member_oauth_identities` 列再次登入時，MUST 依既有規則拒絕
  （FR-011）——`delete_account()` 既有行為已將 `email`/`password_hash`
  改寫為不可用值，**但不會刪除 `member_oauth_identities` 列**（沒有
  理由這麼做，判斷依據是查到 `Member` 後檢查 `deleted_at`，不是判斷
  綁定列存不存在）；OAuth 登入服務函式 MUST 在找到既有綁定後，比照
  既有 Email／密碼 `login()`（若既有 `login()` 尚未檢查 `deleted_at`，
  本 feature 的新 OAuth 登入路徑仍 MUST 自行檢查並拒絕——見
  contracts/oauth-login-api.md）。

## 4. Schema／型別擴充（既有檔案）

`app/domains/member/schemas.py`：

```python
class MemberPublicResponse(BaseModel):
    ...
    email: str | None  # 舊：str（FR-004 連動變更）
    linked_oauth_providers: list[Literal["google", "line"]]  # 新增，US3
    has_password: bool  # 新增（實作階段補充，見下方說明）
```

**`has_password`**（實作階段補充，非原始規劃文件涵蓋，於此記錄）：
`member.password_hash is not None` 的布林值。前端需要它才能決定
`PATCH /members/me/password`／`DELETE /members/me` 表單是否顯示「目前
密碼」欄位（research.md #7），以及 FR-013 的提醒是否顯示（`!has_password
&& !email`）——這兩者若只看 `linked_oauth_providers` 無法判斷（一個
`password_hash` 為 `None` 但零個 OAuth 綁定的帳號理論上不該存在，但
`has_password` 讓前端不需要間接推導）。

`ChangePasswordRequest`／`DeleteAccountRequest`：

```python
class ChangePasswordRequest(BaseModel):
    current_password: str | None = None  # 舊：str（research.md #7）
    new_password: str
    confirm_new_password: str

class DeleteAccountRequest(BaseModel):
    current_password: str | None = None  # 舊：str（research.md #7）
```

`apps/web/src/app/core/api/member-auth.models.ts` 對應同步調整
（`email?: string | null`、新增 `linkedOauthProviders: ('google' |
'line')[]`、`currentPassword` 改為可選）。

## 5. 實體關係圖（僅示意本 feature 新增/擴充的部分）

```text
Member (既有)
├── email                    NULL 代表 LINE 未取得 Email 的帳號（改動）
├── password_hash            NULL 代表純 OAuth 帳號（改動）
├── verification_status      OAuth 建立時直接為 "verified"（不變動欄位本身）
└── deleted_at                既有規則不變，OAuth 登入路徑同樣檢查

member_oauth_identities (新增)
├── member_id      ───────────→ Member.id
├── provider                  "google" | "line"
├── provider_user_id          UNIQUE(provider, provider_user_id) — FR-007
│                              UNIQUE(member_id, provider)        — FR-006
└── email_at_link              僅供顯示，非登入判斷依據
```
