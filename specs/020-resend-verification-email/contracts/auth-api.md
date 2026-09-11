# API Contract: 會員首頁重新寄送驗證信

擴充既有 `specs/006-member-friends/contracts/auth-api.md` 之
`POST /auth/resend-verification`、`GET /members/me`、
`POST /auth/login`、`PATCH /members/me/nickname` 四個既有端點的**回應
形狀**（新增欄位、調整既有冷卻門檻，不新增端點、不修改請求參數、不
修改既有錯誤碼）。

## `POST /auth/resend-verification`（既有端點，回應新增 1 個欄位，冷卻門檻調整）

**Auth**：`Authorization: Bearer {access_token}`（不變，`require_member`，
不要求信箱已驗證——這正是本端點存在的目的）。

**變更**：冷卻門檻由既有 60 秒改為 **5 分鐘**（data-model.md，取代
006-member-friends FR-011 之既有設定）；冷卻基準改為「該會員上一次
**手動觸發**重新寄送的時間」，MUST NOT 把註冊當下系統自動寄出的第一封
驗證信算作一次「重新寄送」——會員從未手動觸發過重新寄送時（該會員
名下僅有註冊時核發的那一筆 Token），這次觸發 MUST 直接成功，不受冷卻
限制（Clarifications 2026-09-10，research.md #5，修復 `/speckit-analyze`
finding I1）。

**Response 200**：

```json
{ "sent": true, "available_at": "2026-09-10T10:05:00Z" }
```

`available_at` 為本次成功寄出後的冷卻結束時間（新增，data-model.md）——
即使這次是該會員第一次手動觸發（觸發本身不受冷卻限制），`available_at`
仍 MUST 正確回傳「這次寄出時間 + 5 分鐘」，代表**下一次**觸發的最早
可行時間。

**錯誤代碼**：`MEMBER_TOKEN_INVALID`（401）、`ALREADY_VERIFIED`
（409）、`RESEND_RATE_LIMITED`（429，門檻改為 5 分鐘，其餘語意不變）。

## `GET /members/me`（既有端點，回應新增 1 個欄位）

**Auth**：`Authorization: Bearer {access_token}`（不變）。

**Response 200**：

```json
{
  "member_id": "uuid",
  "email": "a@example.com",
  "nickname": "小明",
  "user_number": "12345678",
  "verification_status": "unverified",
  "resend_verification_available_at": "2026-09-10T10:05:00Z"
}
```

`resend_verification_available_at`（新增，data-model.md）：`null` 代表
現在就可以觸發重新寄送（或帳號已驗證——前端仍以 `verification_status`
判斷是否顯示按鈕，兩者不會混淆），否則為冷卻結束的明確時間戳。

## `POST /auth/login`（既有端點，`member` 欄位隨 `MemberPublicResponse` 同步擴充）

**Response 200** 之 `member` 物件欄位形狀與上述 `GET /members/me`
完全相同（兩者共用同一個 `MemberPublicResponse`）——登入當下即可讓前端
立即知道是否仍在冷卻中，不需要額外呼叫 `GET /members/me`。

## `PATCH /members/me/nickname`（既有端點，`resend_verification_available_at` 恆為 `null`）

**權限不變**：`require_verified_member`——呼叫此端點時會員必定已驗證，
`resend_verification_available_at` 因此恆為 `null`（`get_resend_
verification_available_at()` 對已驗證會員直接回傳 `None`，不觸發查詢，
data-model.md）。

---

## 前端使用方式摘要

- 頁面載入（`GET /members/me`）與登入當下（`POST /auth/login`）即可
  取得目前冷卻狀態，不需要額外請求。
- 成功呼叫 `POST /auth/resend-verification` 後，直接使用回應中的
  `available_at` 切換到冷卻中狀態，不需要再呼叫一次 `GET /members/me`。
- 前端 MUST 只依伺服器回傳的時間戳排程一次性到期事件，MUST NOT 自行
  推算冷卻結束時間（research.md #3）。
