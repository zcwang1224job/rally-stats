# API Contract: 認證（註冊／登入／驗證／密碼重設）

沿用 `specs/architecture.md` §3.1 已定義的路徑草案。錯誤格式統一為 `{"error_code": "...", "detail": {...}}`。

## POST /auth/register

**Request**

```json
{ "email": "a@example.com", "password": "abc12345", "confirm_password": "abc12345", "turnstile_token": "..." }
```

**Response 201**

```json
{ "member_id": "uuid", "email": "a@example.com", "user_number": "aB3dEfGh" }
```

**錯誤代碼**：`CAPTCHA_INVALID`、`CAPTCHA_EXPIRED`（400，research.md #4）、`EMAIL_ALREADY_REGISTERED`（409，FR-004）、`PASSWORD_MISMATCH`、`PASSWORD_TOO_WEAK`、`VALIDATION_ERROR`（422）。

## POST /auth/login

**Request**：`{ "email": "...", "password": "..." }`

**Response 200**

```json
{
  "access_token": "...", "refresh_token": "...",
  "member": { "member_id": "uuid", "email": "a@example.com", "nickname": "小明", "user_number": "aB3dEfGh", "verification_status": "unverified" }
}
```

**錯誤代碼**：`INVALID_CREDENTIALS`（401，Email 或密碼錯誤——刻意不區分兩者以避免帳號枚舉）、`LOGIN_RATE_LIMITED`（429，FR-002a）。

**Rate limit**：per-IP，比照 `/groups/reauth` 之 slowapi 裝飾器（research.md #6）；MUST NOT 採帳號鎖定（FR-002a）。

**注意**：未驗證帳號 MUST 仍可登入成功（FR-009）——前端依 `verification_status` 顯示驗證提示畫面，後端其餘端點各自於受保護動作前檢查驗證狀態（見 member-api.md 之 `require_verified_member`）。

## POST /auth/refresh

**Request**：`{ "refresh_token": "..." }`

**Response 200**：`{ "access_token": "..." }`（不換發新 refresh token，見 research.md #2）

**錯誤代碼**：`REFRESH_TOKEN_INVALID`（401，過期／`token_version` 不符／格式錯誤皆歸此代碼）。

## GET /auth/verify-email/{token}

**Response 200**：`{ "verified": true }`

**錯誤代碼**：`VERIFICATION_TOKEN_INVALID`（404，查無此 token）、`VERIFICATION_TOKEN_EXPIRED`（410）、`VERIFICATION_TOKEN_ALREADY_USED`（409，冪等考量——已使用視為錯誤而非靜默成功，因需與「逾期」區分不同提示文案）。

## POST /auth/resend-verification

需 `Authorization: Bearer {access_token}`。

**Response 200**：`{ "sent": true }`

**錯誤代碼**：`ADMIN_TOKEN_INVALID` 等級之 `MEMBER_TOKEN_INVALID`（401）、`ALREADY_VERIFIED`（409）、`RESEND_RATE_LIMITED`（429，FR-011，research.md #6）。

## POST /auth/forgot-password

**Request**：`{ "email": "..." }`

**Response 200**：`{ "sent": true }`（**無論該 Email 是否存在對應帳號，一律回傳相同成功回應**——避免帳號枚舉；若不存在則靜默不寄信，僅記錄伺服器日誌）

**Rate limit**：per-IP，比照 `/groups/reauth` 之 slowapi 裝飾器（research.md #6）。

## POST /auth/reset-password/{token}

**Request**：`{ "new_password": "...", "confirm_new_password": "..." }`

**Response 200**：`{ "reset": true }`（成功後同時：`verification_status='verified'`、`token_version += 1`，見 data-model.md #3）

**錯誤代碼**：`RESET_TOKEN_INVALID`（404）、`RESET_TOKEN_EXPIRED`（410）、`RESET_TOKEN_ALREADY_USED`（409）、`PASSWORD_MISMATCH`、`PASSWORD_TOO_WEAK`。
