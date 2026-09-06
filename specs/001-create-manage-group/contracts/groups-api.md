# API Contract: 開團與管理

沿用 `specs/architecture.md` §3.1 已定義的路徑；本文件補完本 feature 擁有端點的請求/回應 schema 與錯誤代碼。所有錯誤回應格式統一為 `{"error_code": "...", "detail": {...}}`（constitution 原則 VIII，語意化錯誤代碼，非寫死文字）。

## POST /groups

建立團。

**Request** (`multipart/form-data` 或 JSON，含 Turnstile token)

```json
{
  "name": "string, 1-30 chars",
  "password": "string, 1-20 chars, optional",
  "max_members": "integer",
  "match_mode": "singles | doubles",
  "scheduling_mechanism": "fair_rotation | fixed_partner | individual_mixed | manual",
  "scoring_mode": "21pt | 15pt | custom",
  "custom_scoring": {
    "target_score": "integer, optional (required if scoring_mode=custom)",
    "deuce_threshold": "integer, optional",
    "cap_score": "integer, optional"
  },
  "activity_time_start": "HH:MM, optional",
  "activity_time_end": "HH:MM, optional",
  "creator_nickname": "string, ≤20 chars, required only if not authenticated",
  "turnstile_token": "string"
}
```

**Response 201**

```json
{
  "group_id": "uuid",
  "group_number": 100042,
  "admin_pin": "384726",
  "admin_token": "jwt...",
  "current_member_count": 1,
  "roster_entry_id": "uuid",
  "guest_session_token": "string, present only if anonymous"
}
```

**錯誤代碼**：`VALIDATION_ERROR`（欄位不合法，含 detail 逐欄說明）、`CAPTCHA_INVALID`、`CAPTCHA_EXPIRED`、`GROUP_MEMBER_CAP_EXCEEDED`、`NICKNAME_REQUIRED_FOR_GUEST`、`MEMBER_NICKNAME_NOT_SET`（已登入但尚未完成首次暱稱設定）。

## GET /groups/{group_id}

團的公開資訊（供加入前預覽、開團列表項目）。不需驗證。

**Response 200**

```json
{
  "group_id": "uuid",
  "group_number": 100042,
  "name": "string",
  "has_password": true,
  "current_member_count": 4,
  "max_members": 8,
  "match_mode": "doubles",
  "activity_time_start": "19:00",
  "activity_time_end": "21:00",
  "status": "active | disbanded"
}
```

`activity_time_start/end` 為 `null` 時前端 MUST 顯示「未提供時間」（FR-006，前端呈現規則，非 API 契約本身）。

## POST /groups/reauth

組團編號 + PIN 碼 → 管理 Token。

**Request**

```json
{ "group_number": 100042, "admin_pin": "384726" }
```

**Response 200**

```json
{ "admin_token": "jwt...", "group_id": "uuid" }
```

**錯誤代碼**：`GROUP_NOT_FOUND`、`GROUP_ADMIN_PIN_INCORRECT`、`GROUP_ADMIN_LOCKED`（含 `detail.retry_after_seconds`）。

## GET /groups/{group_id}/admin

管理頁資料（Header: `Authorization: Bearer {admin_token}`）。

**Response 200**（`disbanded` 團回傳 `read_only: true`，前端據此停用所有寫入操作）

```json
{
  "group": { "...同 Group 完整欄位，含 password 明文（解密後）..." },
  "read_only": false,
  "base_settings_version": 3,
  "admin_token_version": 1
}
```

**錯誤代碼**：`ADMIN_TOKEN_INVALID`（簽章/效期失敗，或 `admin_token_version` 不符 → 前端導向重新驗證頁）。

## PATCH /groups/{group_id}

編輯團設定（一般欄位）。

**Request**

```json
{
  "expected_version": 3,
  "name": "string, optional",
  "password": "string | null, optional",
  "match_mode": "singles | doubles, optional",
  "max_members": "integer, optional",
  "activity_time_start": "HH:MM | null, optional",
  "activity_time_end": "HH:MM | null, optional"
}
```

**Response 200**：更新後的 Group 完整資料 + 新 `base_settings_version`。

**錯誤代碼**：`VERSION_CONFLICT`（HTTP 409，`expected_version` 與目前值不符）、`MATCH_MODE_MEMBER_CAP_CONFLICT`（切換雙打但人數上限未達 4，FR-020）、`GROUP_MEMBER_CAP_EXCEEDED`、`GROUP_DISBANDED`（唯讀團嘗試寫入）。

## PATCH /groups/{group_id}/scoring-settings

**Request**

```json
{
  "expected_version": 3,
  "scoring_mode": "21pt | 15pt | custom",
  "target_score": "integer, optional",
  "deuce_threshold": "integer, optional",
  "cap_score": "integer, optional"
}
```

**錯誤代碼**：同上 + `INVALID_CUSTOM_SCORING`（FR-014 邏輯不一致）。

## POST /groups/{group_id}/disband

**Request**：無 body（僅 Header 帶 admin_token）。

**Response 200**：`{ "status": "disbanded" }`

同一筆交易內：更新 `groups.status`、將該團所有 `queued`/`in_progress` 比賽轉為 `abandoned`（呼叫 003 spec 擁有的內部 service，非跨 HTTP）、逐一對每個場地頻道 + 團通知頻道發布 `group.disbanded`（見 `ably-events.md`）。

## POST /groups/{group_id}/regenerate-admin-pin

**Request**：無 body。

**Response 200**

```json
{ "admin_pin": "新 6 碼", "admin_token": "新 jwt（供觸發者無縫繼續使用）" }
```

同一筆交易內：`admin_pin_hash` 更新、`admin_token_version += 1`、發布 `link.regenerated`（`link_type: admin`）至 `group:{group_id}:notifications`。

**錯誤代碼**：`VERSION_CONFLICT`（HTTP 409，`admin_token_version` 於請求送達前已被搶先變更）。
