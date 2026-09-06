# API Contract: 會員個人資訊與設定

所有端點皆需 `Authorization: Bearer {access_token}`（`require_member`）。標示「需已驗證」者額外要求 `verification_status == 'verified'`（`require_verified_member`，未驗證回傳 `EMAIL_NOT_VERIFIED` 403），比照 FR-009。

## GET /members/me

**Response 200**

```json
{ "member_id": "uuid", "email": "a@example.com", "nickname": "小明", "user_number": "aB3dEfGh", "verification_status": "verified" }
```

## PATCH /members/me/nickname（需已驗證）

**Request**：`{ "nickname": "新暱稱" }`

**Response 200**：更新後的 `GET /members/me` 內容。

**錯誤代碼**：`VALIDATION_ERROR`（422，空白或超過 20 字，FR-022）。

**注意**：僅更新 `members.nickname`；MUST NOT 連動更新任何既有 `roster_entries.nickname`（見 data-model.md #5, research.md #10, FR-024）。

## PATCH /members/me/password（需已驗證）

**Request**：`{ "current_password": "...", "new_password": "...", "confirm_new_password": "..." }`

**Response 200**：`{ "changed": true, "access_token": "...", "refresh_token": "..." }`（同時核發本裝置適用的新 token 對，見 research.md #2）

**錯誤代碼**：`CURRENT_PASSWORD_INCORRECT`（400）、`PASSWORD_MISMATCH`、`PASSWORD_TOO_WEAK`（422）。

## GET /members/me/groups（需已驗證）

供「忘記管理 PIN 碼」列表使用（FR-028/029）。

**Response 200**

```json
{
  "groups": [
    { "group_id": "uuid", "group_number": 100234, "name": "週三夜羽", "status": "active" },
    { "group_id": "uuid", "group_number": 100178, "name": "上週場次", "status": "disbanded" }
  ]
}
```

僅回傳 `created_by_member_id == 本人` 的團（不論 `status`，見 FR-028）。

## GET /members/search?user_number=（需已驗證）

**Response 200**

```json
{ "member_id": "uuid", "nickname": "小美", "user_number": "aB3dEfGh", "friendship_status": "none" }
```

`friendship_status` ∈ `none | pending_outgoing | pending_incoming | friends`（FR-038 之四狀態，供前端決定按鈕/標籤文案）。

**錯誤代碼**：`MEMBER_NOT_FOUND`（404——查無此編號、或對應帳號未驗證〔FR-036〕、或搜尋自己〔FR-037，回傳 `CANNOT_SEARCH_SELF` 更精確〕皆歸此類語意；`CANNOT_SEARCH_SELF` 獨立代碼供前端顯示不同提示）。

**Rate limit**：per-IP，比照 `/groups/reauth`（research.md #6，FR-020）。
