# Data Model: 會員首頁重新寄送驗證信

本 feature **不新增任何資料表、不需要新的 migration**（research.md 前言）。
以下記錄既有回應形狀的擴充、既有常數的調整，以及新增的共用查詢函式
（非資料表）。

## 既有實體（本 feature 讀取/沿用，定義權屬 006-member-friends）

### `Member`（既有，唯讀）

沿用既有 `verification_status`（`"unverified" | "verified"`）判斷是否
需要計算冷卻狀態（`verification_status == "verified"` 時恆回傳
`None`，不需查詢，research.md #3）。

### `EmailVerificationToken`（既有，唯讀）

沿用既有 `created_at`（`TIMESTAMPTZ`，系統自動記錄的絕對時間，UTC）
作為冷卻計算基準；同時沿用「該會員名下 Token 總筆數」作為「是否曾經
手動觸發過重新寄送」的判斷依據（筆數 ≤ 1 代表尚未手動觸發過，見下方
`_verification_token_count_and_last_created_at()`）。本 feature 不修改
此表的 schema，也不修改核發新 Token 的既有邏輯本身
（`_issue_verification_token_and_email()`）——僅將該函式改為回傳新建立
的 `EmailVerificationToken`，供呼叫端計算 `available_at`（見下方
`ResendVerificationResponse`）。

## 既有常數的調整

### `_RESEND_VERIFICATION_COOLDOWN`（`member/service.py`）

| 項目 | 既有值（006） | 本 feature 調整後 |
|---|---|---|
| 值 | `timedelta(seconds=60)` | `timedelta(minutes=5)` |

（research.md #1，spec.md FR-004）

## 新增的共用純函式（非資料表）

### `_verification_token_count_and_last_created_at(session: AsyncSession, member_id: uuid.UUID) -> tuple[int, datetime | None]`

`member/service.py` 內的模組層級私有函式，單次查詢該會員**全部**
`EmailVerificationToken` 的總筆數與最近一筆的 `created_at`（`SELECT
COUNT(id), MAX(created_at) ... WHERE member_id = :member_id`）。既有
`resend_verification()` 與新增的 `get_resend_verification_available_at()`
皆呼叫此函式（research.md #2）。

**筆數的意義**（Clarifications 2026-09-10 / `/speckit-analyze` I1
修復）：註冊當下 `register()` 必定核發過一筆 Token，且系統中新增
Token 只有兩個途徑——註冊、或手動觸發「重新寄送」。因此「筆數 ≤ 1」
即代表「這位會員從未手動觸發過『重新寄送』」，不需要額外的欄位或
migration 即可準確判斷——**筆數 ≤ 1 時，冷卻機制 MUST NOT 生效**
（FR-004、Edge Cases 第一項）；筆數 ≥ 2 時，才以「最近一筆的
`created_at`」作為 5 分鐘冷卻的計算基準（這筆一定是某次「重新寄送」
核發的，因為註冊只會核發那唯一的第一筆）。

### `get_resend_verification_available_at(session: AsyncSession, member: Member) -> datetime | None`

`member/service.py` 內新增的服務函式：

- 若 `member.verification_status == "verified"` → 回傳 `None`（不需查詢）。
- 否則查詢 `_verification_token_count_and_last_created_at()`：
  - 筆數 ≤ 1（尚未手動觸發過「重新寄送」，只有註冊當下那一封，或理論上
    查無任何紀錄的防禦性情境）→ 回傳 `None`（現在就可以觸發，不受冷卻
    限制）。
  - 筆數 ≥ 2 且「最近一筆 `created_at` + `_RESEND_VERIFICATION_COOLDOWN`」
    仍在未來 → 回傳該未來時間戳（冷卻中，尚未可再次觸發）。
  - 筆數 ≥ 2 但「最近一筆 `created_at` + `_RESEND_VERIFICATION_COOLDOWN`」
    已過去 → 回傳 `None`（現在就可以觸發）。

## 既有 API 回應形狀的擴充

### `MemberPublicResponse`（既有，新增 1 個唯讀欄位）

用於 `GET /members/me`、`POST /auth/login`（`LoginResponse.member`）、
`PATCH /members/me/nickname` 三個既有端點的共用回應形狀。

| 欄位 | 型別 | 說明 |
|---|---|---|
| `member_id`／`email`／`nickname`／`user_number`／`verification_status` | 既有 | 不變。 |
| `resend_verification_available_at` | `datetime \| None`（新增） | 呼叫 `get_resend_verification_available_at()` 算好的結果——`None` 代表現在就可以觸發重新寄送（或帳號已驗證，前端本來就用 `verification_status` 另外判斷是否顯示按鈕，不會混淆），非 `None` 則是冷卻結束的明確時間戳（research.md #3）。 |

### `ResendVerificationResponse`（既有，新增 1 個唯讀欄位）

用於 `POST /auth/resend-verification`。

| 欄位 | 型別 | 說明 |
|---|---|---|
| `sent` | `bool`（既有） | 不變，恆為 `true`（失敗時走既有 `ApiError` 拋出 `ALREADY_VERIFIED`／`RESEND_RATE_LIMITED`，不會走到這個成功回應）。 |
| `available_at` | `datetime`（新增） | 這次成功寄出後的冷卻結束時間（`= 這次核發的 Token.created_at + _RESEND_VERIFICATION_COOLDOWN`），讓前端不需要再呼叫一次 `GET /members/me` 就能立刻切換到冷卻中狀態（research.md #3）。**即使這是該會員第一次手動觸發重新寄送**（觸發當下本身不受冷卻限制，見上方 `_verification_token_count_and_last_created_at()`），`available_at` 仍 MUST 回傳「這次寄出時間 + 5 分鐘」——冷卻的是「下一次」重新寄送，不代表這次觸發本身受限。 |

## 狀態/邊界摘要

- 冷卻狀態的唯一資料來源是既有 `EmailVerificationToken.created_at`，
  本 feature 不新增、不修改任何既有資料表的 schema。
- `resend_verification_available_at`／`available_at` 皆是每次呼叫對應
  端點當下重新計算的唯讀衍生值，沒有自己的生命週期需要管理，也不會被
  快取／持久化。
- 前端 MUST NOT 自行用「現在時間 + 5 分鐘」推算冷卻結束時間，也
  MUST NOT 用 `localStorage` 等裝置本地儲存記錄/推算冷卻狀態——一律
  以伺服器回傳的時間戳為準（research.md #3，spec.md FR-009）。
