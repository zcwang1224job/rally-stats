# API Contract: OAuth 登入／註冊／綁定交握

決策依據見 research.md #1/#2/#3。所有端點路徑前綴 `/auth/oauth/{provider}`，
`provider` 路徑參數 MUST 為 `google` 或 `line`，其他值一律 404。

## GET /auth/oauth/{provider}/start

啟動一次 OAuth 交握，回傳前端應整頁導向（`window.location.href =
authorize_url`）的網址。

**Query 參數**：`intent`：`"login"`（預設，訪客/既有會員快速登入或
註冊，US1/US2）或 `"link"`（既有會員在個人設定主動綁定，US3）。

**權限**：`intent=login` 時公開端點（訪客可呼叫）；`intent=link` 時 MUST
`require_verified_member`（US3 僅限已登入會員主動觸發）。

**Response 200**：`{ "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth?..." }`

**行為**：
- 產生 PKCE `code_verifier`（隨機）與 `code_challenge`（`S256`）。
- 產生簽章 `state`（`typ: "oauth_state"`，見 research.md #2）：內含
  `provider`／`intent`／（`intent=link` 時）呼叫者的 `member_id`／
  `code_verifier`／10 分鐘效期。
- 組出對應 provider 的 authorize URL：`client_id`、
  `redirect_uri={frontend_base_url}/api/auth/oauth/{provider}/callback`、
  `response_type=code`、`scope`（Google: `openid email profile`；LINE:
  `openid email profile`，LINE 端 Email 為選用授權項目，使用者可能拒絕）、
  `state`、`code_challenge`、`code_challenge_method=S256`（LINE 另加
  `nonce`，OIDC 規範要求）。

**Rate limit**：`20/minute`（比照既有 `POST /auth/login`）。

## GET /auth/oauth/{provider}/callback

Google／LINE 完成使用者授權後，瀏覽器被 redirect 回這裡。**MUST NOT**
要求 `Authorization` header（瀏覽器是被第三方導回來的全新請求）。

**Query 參數**（由 provider 附加）：成功時 `code`、`state`；使用者取消/
拒絕時 `error=access_denied`（或其他 provider 定義的錯誤碼）、`state`。

**Response**：一律是 **302 redirect**，不回傳 JSON body（回呼是瀏覽器
整頁導向的最後一站，前端要接手的是「導向去哪裡＋網址帶什麼」，不是
呼叫端能解析的 API response）：

| 情境 | 導向目標 |
|---|---|
| `state` 缺失/簽章驗證失敗/過期 | `{frontend_base_url}/auth/oauth-callback#status=error&code=OAUTH_STATE_INVALID` |
| 使用者於 provider 端取消/拒絕（FR-010） | `intent=login` 時 → `{frontend_base_url}/auth/oauth-callback#status=cancelled`；`intent=link` 時 → `{frontend_base_url}/settings?oauth_link=cancelled` |
| `code` 換 token 失敗，或 `id_token` 簽章/`iss`/`aud`/`nonce` 驗證失敗 | `.../auth/oauth-callback#status=error&code=OAUTH_PROVIDER_ERROR` |
| `intent=login`，找到既有 `member_oauth_identities` 綁定，對應會員 `deleted_at IS NOT NULL`（FR-011） | `.../auth/oauth-callback#status=error&code=ACCOUNT_DELETED` |
| `intent=login`，找到既有綁定，對應會員可正常登入（FR-003） | `.../auth/oauth-callback#status=success&access_token=...&refresh_token=...&is_new_member=false` |
| `intent=login`，查無既有綁定，取得的 Email 與**任一**既有會員 Email 相同（FR-005） | `.../auth/oauth-callback#status=error&code=OAUTH_EMAIL_ALREADY_REGISTERED` |
| `intent=login`，查無既有綁定，Email 無衝突（或 LINE 未取得 Email） | 建立新 `Member`（`verification_status="verified"`）＋新 `member_oauth_identities` 列（FR-002），核發 token → `.../auth/oauth-callback#status=success&access_token=...&refresh_token=...&is_new_member=true` |
| `intent=link`，此 `(provider, provider_user_id)` 已綁定**另一個**會員（FR-007） | `{frontend_base_url}/settings?oauth_link=error&code=OAUTH_IDENTITY_ALREADY_LINKED` |
| `intent=link`，此 `(provider, provider_user_id)` 已綁定**同一個**呼叫者自己（重複點擊） | 視為成功（冪等）→ `{frontend_base_url}/settings?oauth_link=success&provider={provider}` |
| `intent=link`，呼叫者自己在此 `provider` 已有**另一個不同**帳號的既有綁定（FR-006，/speckit-analyze 2026-09-14 remediation C1） | `{frontend_base_url}/settings?oauth_link=error&code=OAUTH_PROVIDER_ALREADY_LINKED`——MUST NOT 取代既有綁定 |
| `intent=link`，尚未被任何人綁定、呼叫者此 `provider` 尚無既有綁定，成功建立綁定（FR-006） | `{frontend_base_url}/settings?oauth_link=success&provider={provider}` |

**Rate limit**：`20/minute`（同 `start`，以 `state` 內含的資訊而非
IP 作為主要防重放依據，速率限制僅作為額外的粗粒度防護）。

**併發防護**（/speckit-analyze 2026-09-14 remediation E3，呼應
plan.md Constraints 段落）：上表每一列的判斷（FR-005 的 Email 撞號、
FR-006/FR-007 的 provider 綁定衝突）皆在應用層查詢完成後、寫入前檢查，
但兩個並發請求仍可能同時通過應用層檢查、其中一個在真正寫入時撞上
data-model.md §1/§2 的資料庫唯一索引——`complete_oauth_callback()`
MUST 捕捉該寫入交易觸發的 `IntegrityError`，依違反的是哪一條唯一索引
轉譯為上表對應的既有錯誤代碼（`OAUTH_EMAIL_ALREADY_REGISTERED`／
`OAUTH_IDENTITY_ALREADY_LINKED`／`OAUTH_PROVIDER_ALREADY_LINKED`），
MUST NOT 讓 `IntegrityError` 以未攔截例外的形式外洩為未預期的 500。

## 前端行為對照（非本 contract 強制，供 tasks.md 參考）

- `/auth/oauth-callback` 是一個新的、極簡的路由/元件：讀取
  `location.hash` 內的 `status`/`code`/`access_token`/`refresh_token`/
  `is_new_member`，`status=success` 時呼叫既有 `AuthService.setTokens()`
  並導向既有登入後的既定首頁（`is_new_member=true` 時導向既有「設定
  暱稱」既定流程，FR-012）；`status=cancelled`/`status=error` 時導向
  登入頁並依 `code` 顯示對應 i18n 訊息，讀完 hash 後 MUST 立即以
  `history.replaceState` 清除網址（token 不可停留在瀏覽紀錄/網址列）。
- 個人設定頁讀取 URL 上的 `oauth_link=success|cancelled|error`（加上
  `code`）顯示對應提示後，同樣 MUST 清除該 query 參數。
