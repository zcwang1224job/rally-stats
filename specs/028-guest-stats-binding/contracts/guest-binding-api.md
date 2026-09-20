# API Contract: 訪客名冊身份綁定帳號

決策依據見 research.md #1/#2/#4/#7。兩個新端點皆掛在既有 `group` domain
的 router 下（沿用既有 `guest_session_token` 相關端點所在的模組，不新增
`roster` domain 的 router/service，維持 research.md 決策的一致性）。

## GET /groups/guest-token/{token}/binding-status

查詢一個訪客個人查看連結目前的綁定資格，**不**要求 `RosterEntry` 現役
（active）也**不**要求所屬 `Group` 現役（active）——這是與既有
`GET /by-guest-token/{token}`（`resolve_guest_session`）最主要的差異
（research.md #1）。

**權限**：公開端點（訪客本人透過連結本身持有的 `token` 即為授權依據，
與既有訪客連結信任模型一致）。

**Response 200**：

```json
{
  "already_bound": false,
  "roster_entry_id": "uuid",
  "group_id": "uuid",
  "group_name": "string",
  "nickname": "string",
  "group_status": "active" | "disbanded",
  "roster_status": "active" | "left" | "kicked"
}
```

**Errors**：`LINK_NOT_FOUND`（404）——`token` 從未存在，或對應的
`guest_session_token` 已被管理員重新產生而失效。

## POST /groups/guest-token/{token}/bind

執行一次性綁定：把 `token` 對應的 `RosterEntry.member_id` 設為呼叫者的
帳號（新建立、既有登入、或目前已登入的 session，三者擇一，由
`optional_member` 與 request body 共同決定，research.md #2）。

**權限**：`Depends(optional_member)`——已登入時忽略 body 中帳號建立/
登入欄位；未登入時 body MUST 提供 `mode: "register"` 或 `mode: "login"`
其中一種的對應欄位。

**Request body**（三種互斥形狀之一）：

```jsonc
// 已登入（Clarifications 2026-09-15，FR-012）：Authorization header 帶
// 現有 access token，body 為空物件即可
{}

// mode: "register"（US1）
{
  "mode": "register",
  "email": "string",
  "password": "string",
  "turnstile_token": "string"
}

// mode: "login"（US2）
{
  "mode": "login",
  "email": "string",
  "password": "string"
}
```

**Response 200**（`current_member` 為 `None` 時才回傳新 token 對；已登入
一鍵綁定時 `access_token`/`refresh_token` 為 `null`，前端沿用既有
session，不需要替換 token）：

```json
{
  "bound": true,
  "group_id": "uuid",
  "access_token": "string | null",
  "refresh_token": "string | null"
}
```

**Errors**：
- `LINK_NOT_FOUND`（404）——同上。
- `ROSTER_ENTRY_ALREADY_BOUND`（409）——`token` 對應的名冊身份已被
  （任何帳號）綁定過，`UPDATE ... WHERE member_id IS NULL` 影響 0 rows
  （research.md #4）。
- `MEMBER_ALREADY_IN_GROUP`（409）——綁定者在這一團已經有一筆 `active`
  的名冊身份（最典型的是 團長 自己：他手上本來就有自己團每一條訪客連
  結）。同一個帳號在一團的輪替名單裡只能是一個人；允許之後
  `active_roster_entry_for_member()` 的 `scalar_one_or_none()` 會讓該帳
  號的所有 member-view 端點 500。名冊身份為 `left`/`kicked` 時不受此限
  （同一個人以訪客身份回鍋，spec.md Edge Cases）。
- `EMAIL_ALREADY_REGISTERED`（409，`mode: "register"` 專屬）——沿用既有
  `register()` 的既有錯誤碼；前端依 spec FR-009 引導改用
  `mode: "login"`。
- `INVALID_CREDENTIALS`（401，`mode: "login"` 專屬）——沿用既有
  `login()` 的既有錯誤碼。
- `CAPTCHA_INVALID`（400，`mode: "register"` 專屬）——沿用
  既有 `verify_turnstile_token()` 的既有錯誤碼。

**Rate limit**：`20/minute`（比照既有 `POST /auth/login`／
`GET /auth/oauth/{provider}/start`）。

---

## 對既有 OAuth 交握契約（`specs/027-google-line-oauth-login/contracts/
oauth-login-api.md`）的擴充（research.md #3）

本 feature **不修改**該檔案本身（027 已完成、已實作的既有 feature 文件
維持原樣），僅在既有端點上新增以下向下相容的擴充，實作時同步更新 027
的 contract 文件以反映這個擴充：

- `GET /auth/oauth/{provider}/start`：新增一個可選 query 參數
  `bind_guest_token`（僅在 `intent=login` 時允許帶入；`intent=link` 時
  帶入視為無效輸入，回傳 `INVALID_REQUEST`）。有帶值時，原樣寫入
  `state` JWT 的新增欄位 `bind_guest_token`。
- `GET /auth/oauth/{provider}/callback`：`state` 解出的
  `bind_guest_token` 有值時，既有登入/建帳號成功後，於同一資料庫交易內
  額外執行與 `POST /groups/guest-token/{token}/bind` 相同的綁定邏輯
  （`token` 即 `bind_guest_token` 的值）。
- 成功時的重新導向網址（`_oauth_callback_redirect_url()`）：
  `status=success` 分支的 URL fragment，於綁定成功時新增一個參數
  `bound_group_id=<group_id>`；既有 `/auth/oauth-callback` 落地頁元件
  讀到此參數時，改導向 `/groups/<bound_group_id>/member-view`，否則
  維持既有預設導向行為完全不變。
- 綁定本身失敗（例如 `ROSTER_ENTRY_ALREADY_BOUND`）MUST NOT 讓整個
  OAuth 登入流程失敗——帳號建立/登入本身仍視為成功（token 仍正常
  核發），僅綁定這一步失敗；`bound_group_id` 留空，落地頁依既有預設
  行為導向，前端 MAY 額外提示綁定失敗（沿用既有錯誤代碼顯示慣例）。
