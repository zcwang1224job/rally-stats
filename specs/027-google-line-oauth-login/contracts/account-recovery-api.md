# API Contract: 帳號綁定管理與救援路徑

決策依據見 research.md #7/#8。所有端點皆需
`Authorization: Bearer {access_token}` 且 `require_verified_member`。

## GET /members/me（既有端點，回應擴充）

`MemberPublicResponse` 新增：

```json
{
  "email": null,
  "linked_oauth_providers": ["line"],
  "has_password": false
}
```

- `email`：既有欄位，型別由 `str` 改為 `str | null`（data-model.md §4）。
- `linked_oauth_providers`：新增欄位，目前已綁定的 provider 清單（依
  `member_oauth_identities` 查詢），供「個人設定」渲染「已綁定」狀態
  （US3 驗收情境 1）。
- `has_password`：新增欄位（實作階段補充，data-model.md §4 說明）—
  `member.password_hash is not None`，供前端決定
  `PATCH /members/me/password`／`DELETE /members/me` 表單是否顯示
  「目前密碼」欄位，以及與 `email` 一併判斷 FR-013 提醒的顯示條件
  （`!has_password && !email`）。

## DELETE /members/me/oauth-identities/{provider}

解除一個既有綁定（US3 隱含的一般解除綁定能力；FR-008 的限制在此把關）。

**權限**：`require_verified_member`。

**Response 204**：成功解除。

**錯誤代碼**：

- `OAUTH_IDENTITY_NOT_LINKED`（404）——該 provider 目前未綁定至此會員。
- `LAST_LOGIN_METHOD`（409，FR-008）——解除後該會員將沒有任何登入方式
  （`password_hash IS NULL` 且解除後不再有任何 `member_oauth_identities`
  列）；系統 MUST 拒絕此次解除，不執行任何寫入。

## POST /members/me/password（既有端點 `PATCH /members/me/password` 的
request 語意擴充，路徑/方法不變）

`ChangePasswordRequest.current_password` 由必填改為可選
（data-model.md §4）。

**行為分支**（research.md #7）：

- `member.password_hash IS NOT NULL`：`current_password` MUST 提供且
  MUST 通過驗證，否則 `CURRENT_PASSWORD_INCORRECT`（既有行為不變）。
- `member.password_hash IS NULL`（FR-013「補設密碼」情境）：
  `current_password` MUST 被忽略（即使提供也不驗證），直接以
  `new_password` 雜湊寫入；回應與既有 `ChangePasswordResponse`
  （新 token pair）完全相同形狀。

## POST /members/me/email

補上一個先前為 `NULL` 的 Email（FR-013 的「補上 Email」分支）；**僅**
適用於目前沒有 Email 的帳號，不提供「更換既有 Email」能力（範圍外）。

**Request**：`{ "email": "user@example.com" }`

**Response 202**：`{ "verification_email_sent": true }`——比照既有
`register()` 尾端行為，寫入 `member.email`（此時尚未驗證）並寄出既有
驗證信（重用既有 `EmailVerificationToken`／`GET
/auth/verify-email/{token}`／`resend-verification` 全套既有機制，
research.md #8）。

**錯誤代碼**：

- `EMAIL_ALREADY_SET`（409）——`member.email` 已非 `NULL`，本端點僅服務
  「從無到有」，MUST 拒絕（不在本 feature 範圍內提供更換既有 Email 的
  能力）。
- `EMAIL_ALREADY_REGISTERED`（409）——欲補上的 Email 已被另一個既有
  帳號使用（與既有 `register()` 完全相同的判斷，含大小寫正規化）。

## DELETE /members/me（既有端點，request 語意擴充）

`DeleteAccountRequest.current_password` 由必填改為可選
（data-model.md §4，research.md #7）。

**行為分支**：

- `member.password_hash IS NOT NULL`：`current_password` MUST 提供且
  MUST 通過驗證，否則 `CURRENT_PASSWORD_INCORRECT`（既有行為不變）。
- `member.password_hash IS NULL`（純 OAuth 會員刪除自己的帳號）：
  `current_password` MUST 被忽略，略過密碼驗證步驟，直接執行既有的
  匿名化流程——已通過 `require_verified_member` 的有效 session 本身即
  是身分證明；前端既有的二次確認對話框（憲章原則 V）維持顯示，僅隱藏
  「輸入目前密碼」欄位。
