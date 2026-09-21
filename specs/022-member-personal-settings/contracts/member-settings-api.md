# API Contract: 會員個人設定（四大分區）

擴充既有 `specs/006-member-friends/contracts/member-api.md`
（`GET /members/me`、`PATCH /members/me/nickname`、
`PATCH /members/me/password`、`GET /members/search` 皆有行為調整或
擴充）；新增 5 支端點。所有端點皆需登入（`Authorization: Bearer
<access_token>`），沿用既有 `require_member`／`require_verified_member`
依賴（詳見各端點）。

## `GET /members/me`（既有端點，回應擴充）

新增三個欄位，取代前端過去無從得知的「目前語言偏好/隱私設定」狀態：

```json
{
  "member_id": "...",
  "email": "...",
  "nickname": "...",
  "user_number": "...",
  "verification_status": "verified",
  "resend_verification_available_at": null,
  "language_preference": "zh-TW",
  "allow_search": true,
  "share_match_records_with_friends": true
}
```

**錯誤代碼**：不變（`MEMBER_TOKEN_INVALID`）。

## `GET /members/me/supported-languages`（新增）

回傳目前系統支援的語言代碼清單，供前端組出「基本設定」分區的語言偏好
下拉選單（research.md #4：清單本身是後端程式碼常數，前端不寫死選項）。

**Auth**：`require_member`（比照既有 `GET /members/me`，不要求已驗證
信箱——查看自己支援哪些語言不需要功能性解鎖）。

**Response**：

```json
{ "languages": ["zh-TW"] }
```

**錯誤代碼**：`MEMBER_TOKEN_INVALID`。

## `PATCH /members/me/language`（新增）

**Auth**：`require_verified_member`（比照既有 `PATCH /members/me/nickname`
——個人設定頁面整體鎖在信箱驗證之後，FR-025）。

**Request**：

```json
{ "language": "zh-TW" }
```

**Response**（回傳更新後的 `MemberPublicResponse`，比照既有
`PATCH /members/me/nickname` 的既有回應慣例）：

```json
{ "member_id": "...", "language_preference": "zh-TW", "...": "..." }
```

**錯誤代碼**：`MEMBER_TOKEN_INVALID`、`EMAIL_NOT_VERIFIED`、
`LANGUAGE_NOT_SUPPORTED`（400，`language` 不在
`GET /members/me/supported-languages` 回傳的清單中，對應 FR-004）。

## `PATCH /members/me/privacy`（新增）

**Auth**：`require_verified_member`。

**Request**（至少一個欄位非 `null`；只送出使用者這次切換的那一個欄位，
research.md #5）：

```json
{ "allow_search": false }
```

或

```json
{ "share_match_records_with_friends": false }
```

**Response**（回傳兩個隱私設定的完整目前狀態，不論這次請求只改了哪一個）：

```json
{ "allow_search": false, "share_match_records_with_friends": true }
```

**副作用（FR-020，立即生效）**：回應成功之後的下一次
`GET /members/search`、`GET /members/{member_id}/match-records*` 請求，
MUST 立即反映新設定——這兩個既有/新增端點在每次請求當下查詢
`members` 表最新值，不快取判斷結果（憲章原則 X）。

**錯誤代碼**：`MEMBER_TOKEN_INVALID`、`EMAIL_NOT_VERIFIED`、
`VALIDATION_ERROR`（兩個欄位皆為 `null`/皆未提供）。

## `GET /members/me/login-records`（新增）

**Auth**：`require_verified_member`。

**Request**：Query 參數 `page`（選填，預設 1）。

**Response**（分頁 pattern 比照既有 `MemberGroupHistoryResponse`）：

```json
{
  "records": [
    { "created_at": "2026-09-13T10:00:00Z", "device_category": "desktop" },
    { "created_at": "2026-09-12T08:30:00Z", "device_category": "mobile" }
  ],
  "page": 1,
  "total_pages": 3
}
```

依 `created_at` 由新到舊排序（FR-008）；`device_category` 為
`"desktop" | "mobile" | "unknown"`（不含 IP/地理位置，FR-007）。

**錯誤代碼**：`MEMBER_TOKEN_INVALID`、`EMAIL_NOT_VERIFIED`。

## `GET /members/{member_id}/match-records`（新增——好友檢視他人戰績）

**Auth**：`require_verified_member`。呼叫者不可為 `member_id` 本人——此
檢查在好友關係檢查**之前**執行，`member_id == 呼叫者自己` 時 MUST 立即
回應 `SELF_VIEW_NOT_SUPPORTED`（400），MUST NOT 落入下方的好友關係/
隱私檢查（避免誤判為 `FRIENDSHIP_REQUIRED`——自己與自己永遠不會有一筆
`FriendRequest`，若不特別擋在前面，`get_friendship_status()` 會回傳
`"none"`）。自己查看自己請改用既有 `GET /members/me/match-records`。

**授權檢查順序**（research.md #1/#6；spec.md Edge Cases 2026-09-13 補充）：

1. `member_id == 呼叫者自己` → `SELF_VIEW_NOT_SUPPORTED`（400）。
2. `member_id` 對應的會員不存在或未驗證 → `MEMBER_NOT_FOUND`（404，
   與既有 `search_member()` 一致的「不洩露細節」原則）。
3. 呼叫者與 `member_id` 尚未成立好友關係（`get_friendship_status()` 回傳
   非 `"friends"`） → `FRIENDSHIP_REQUIRED`（403，FR-019）。
4. 已是好友，但 `member_id` 的 `share_match_records_with_friends` 為
   `false` → `MATCH_RECORDS_PRIVATE`（403，FR-018）。
5. 皆通過 → 回應內容與既有 `GET /members/me/match-records`
   **完全相同的形狀**（`MemberMatchRecordsResponse`，含 query 參數：
   `page`、`opponent1`、`opponent2`、`partner`、`result`、`ended_from`、
   `ended_before`（Revision 2026-09-22：取代 `date_from`／`date_to`，帶 UTC
   offset 的時間點半開區間，詳見 034 合約）、`round_from`、`round_to`、
   `self_score_cmp`、`self_score`、
   `opponent_score_cmp`、`opponent_score`、`match_mode`——直接透傳給既有
   `build_member_match_records(session, member_id, ...)`）。

**錯誤代碼**：`MEMBER_TOKEN_INVALID`、`EMAIL_NOT_VERIFIED`、
`SELF_VIEW_NOT_SUPPORTED`、`MEMBER_NOT_FOUND`、`FRIENDSHIP_REQUIRED`、
`MATCH_RECORDS_PRIVATE`。

## `GET /members/{member_id}/match-records/{match_id}`（新增——好友檢視單場詳情）

**Auth**：同上，授權檢查順序（含 `member_id == 呼叫者自己` →
`SELF_VIEW_NOT_SUPPORTED` 的優先檢查）與錯誤代碼完全相同（多一個既有的
`MATCH_NOT_FOUND`／`GROUP_MEMBERSHIP_NEVER_HELD`，沿用既有
`get_member_match_record_detail()` 內部檢查）。通過後直接委派既有
`get_member_match_record_detail(session, member_id, match_id)`，回應形狀
與既有 `GET /members/me/match-records/{match_id}` 完全相同
（`MatchRecordDetailResponse`）。

## `GET /members/search`（既有端點，行為調整）

**新增檢查**：目標會員 `allow_search == false` 時（且非呼叫者本人），
回應 MUST 與目標會員不存在時完全相同——`MEMBER_NOT_FOUND`（404），不得
在錯誤訊息/回應形狀上洩露「帳號存在但已隱藏」與「帳號真的不存在」的
差異（FR-017）。呼叫者搜尋自己時，`allow_search` 狀態不影響既有
`CANNOT_SEARCH_SELF`（400）行為。

**錯誤代碼**：既有 `MEMBER_NOT_FOUND`、`CANNOT_SEARCH_SELF` 不變，僅
`MEMBER_NOT_FOUND` 觸發條件擴大（新增「目標已關閉允許被搜尋」這一種
情況）。

## `PATCH /members/me/nickname`、`PATCH /members/me/password`（既有端點，零變更）

行為與既有 `specs/006-member-friends/contracts/member-api.md` 完全相同，
本 feature 僅將其在前端重新組織進「基本設定」/「安全性」分區，不調整
請求/回應形狀或後端邏輯。
