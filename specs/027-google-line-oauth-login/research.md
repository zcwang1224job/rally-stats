# Research: 使用 Google／LINE 帳號註冊與登入

本文件記錄 Phase 0 的技術決策，解決 plan.md Technical Context 中列出的
未知項目。決策依據：既有程式碼慣例（`app/domains/member/`）、既有前端
token 儲存機制（`AuthService`，`localStorage`）、本專案 constitution。

## #1：OAuth 交握流程的整體形狀（Authorization Code + PKCE，後端全權代理）

**Decision**：採用標準 OAuth 2.0 Authorization Code Flow，並加上 PKCE
（S256）作為額外防護；**整個交握完全由後端代理**，前端只做兩件事：
(a) 呼叫 `GET /auth/oauth/{provider}/start` 取得 `authorize_url` 後整頁導向
（`window.location.href`），(b) 在固定的回呼落地頁 `/auth/oauth-callback`
讀取網址 `#fragment` 中的 token 或錯誤代碼，寫入既有 `AuthService`
（`setTokens()`）。Google／LINE 的 `redirect_uri` 一律指向後端（透過既有
`frontend_base_url` + 既有 `/api` Nginx proxy 前綴組成，例如
`{frontend_base_url}/api/auth/oauth/google/callback`），不指向前端路由——
`code`/`state` 這類敏感參數只在後端之間（伺服器對 Google/LINE 的 token
endpoint）傳遞，不經過瀏覽器可見的網址列，符合既有「伺服器為唯一可信
來源」（原則 X 精神延伸）與「不信任前端判斷結果」的一貫作法。

**Rationale**：本系統既有登入（`POST /auth/login`）回傳 JSON body 內的
`access_token`/`refresh_token`，由前端 `AuthService` 寫入 `localStorage`
（不是 Cookie-based session）。要讓 OAuth 登入的最終結果一樣落在前端
`AuthService` 手上，最小改動的做法就是：後端完成整個 OAuth 交握、核發
與既有登入完全相同的 token pair，再用一次 302 redirect 把 token 帶回
前端一個新的、專門的回呼落地頁（透過 URL fragment `#`，不是 query
string——fragment 不會被瀏覽器送進 Referer header 或伺服器存取日誌，是
業界對「用網址傳遞一次性敏感資料」的標準做法）；落地頁做的事情跟既有
`login()` 呼叫成功後的 `.pipe(tap(...))` 完全一樣，只是觸發來源不同。

**Alternatives considered**：
- 前端直接持有 Google/LINE 的 `client_id` 並自行組出 authorize URL、
  自行處理 callback、自行呼叫後端一支「用 provider access_token 換我們
  自己 token」的端點（SPA-only 模式，Google Identity Services 的
  `One Tap`/`Sign In With Google` JS SDK 走的是這條路）——放棄，因為 LINE
  官方 SDK 對這種「前端直接拿 provider token 換後端 session」模式的
  官方支援與安全建議不如 Google 成熟一致，且此模式需要後端額外驗證一顆
  「前端聲稱是這個 provider token」的信任鏈，二選一時選擇「後端全權代理」
  可以讓兩個 provider 共用完全相同的一套後端邏輯與安全模型，不必為兩個
  provider 各自維護一套前端 SDK 整合與對應的信任驗證程式碼。
- Cookie-based session（後端直接在 callback 的 302 回應中設定
  httpOnly Cookie）——放棄，因為既有系統的認證模型全面是「JSON body
  token + Authorization header」，改用 Cookie 只為了 OAuth 這一條路徑，
  會讓 `AuthService`/HTTP interceptor 出現兩套並存的認證機制，增加維護
  負擔，且不符合「新增選項、不取代既有機制」的 spec.md Assumption。

## #2：`state` 參數的實作方式（簽章 JWT，不落地 DB）

**Decision**：`state` 參數本身就是一顆**簽章 JWT**（重用既有
`settings.jwt_secret`，`issue_access_token()`/`issue_refresh_token()`
所在的同一支 `app/domains/member/security.py` 新增第三種
`typ: "oauth_state"`，避免與既有 access/refresh token 混淆——
`_decode_token()` 既有的 `expected_type` 參數機制天然支援這種擴充），
內容包含 `provider`、`intent`（`"login"` | `"link"`）、`intent == "link"`
時的 `member_id`、PKCE 的 `code_verifier`、與短效期（10 分鐘）。後端在
callback 收到 `state` 後驗證簽章與效期即可還原整個交握上下文，**不需要
任何新的資料表或背景清除工作**。

**Rationale**：PKCE 的 `code_verifier` 理論上只需要「產生它的同一個
client（此處即後端本身）在交換 code 時能拿得出來」，既然整個交握都在
後端進行、`state` 本來就會在 `authorize` 請求與 `callback` 回應之間
原樣往返，把 `code_verifier` 直接放進簽章過的 `state` 裡是最省事、也最
安全（簽章防止竄改，短效期防止重放）的做法，完全不需要引入一張新的
資料表與對應的過期清除排程——呼應 constitution「未來規劃事項」段落對
新增背景維運負擔的謹慎態度。

**Alternatives considered**：新增一張 `oauth_login_states` 資料表（state
→ 交握上下文的映射，短 TTL）——放棄，多一張表、多一個「誰來清除過期列」
的維運問題，換不到任何簽章 JWT 方案沒有的安全性。

## #3：id_token 簽章驗證與 provider 差異封裝（新增依賴：Authlib）

**Decision**：新增 `authlib` 作為後端依賴（`pyproject.toml`），用其
`authlib.jose` 模組驗證 Google／LINE 回傳的 `id_token`（OIDC JWT，需要
向 provider 的 JWKS endpoint 抓公鑰驗簽——Google 用
`https://www.googleapis.com/oauth2/v3/certs`，LINE 用
`https://api.line.me/oauth2/v2.1/certs`），並用既有 `httpx.AsyncClient`
（已用於 `app/core/turnstile.py`）呼叫兩個 provider 的
`token` endpoint 交換 `code`。新增
`app/domains/member/oauth_providers.py`，定義一個極簡的
`OAuthProviderConfig`（dataclass：`authorize_url`／`token_url`／
`jwks_url`／`client_id`／`client_secret`／`scopes`）並列出 `GOOGLE`／
`LINE` 兩個常數設定；router/service 層只透過 `provider: Literal["google",
"line"]` 字串與這個小型設定表打交道，不出現任何 provider 專屬的
if/else 分支散落在核心邏輯中（呼應原則 VI 模組化）。

**Rationale**：手動驗證 JWT 簽章（下載並快取 JWKS、處理金鑰輪替、驗證
`iss`/`aud`/`exp`/`nonce` 等一整套 OIDC 規範細節）是資安敏感區域，重新
發明容易出錯（例如忘記驗證 `aud` 會讓別的 client_id 核發的 token 也被
接受）。本專案先前的「不新增套件」是描述過去每個 feature 剛好都不需要，
不是專案級硬性限制；這是本專案第一次需要處理第三方簽章驗證，`authlib`
是 Python 生態圈中最成熟、star 數與維護活躍度最高的 OAuth/OIDC client
函式庫之一，用一個經過廣泛審查的函式庫換取正確性，優於手刻。

**Alternatives considered**：手動用 `httpx` 抓 JWKS + `PyJWT` 驗簽——
放棄，`PyJWT` 本身不處理 JWKS 抓取/快取/輪替，等於還是要自己刻這一層，
`authlib` 已經內建。`google-auth`（Google 官方 SDK）——只涵蓋 Google，
LINE 仍需另一套機制，兩個 provider 會分別維護不對稱的驗證程式碼，故
選擇 provider-agnostic 的 `authlib`。

## #4：`members.email`／`members.password_hash` 改為可為空

**Decision**：兩個欄位皆從 `NOT NULL` 改為 `nullable=True`；
`members.email` 既有的唯一索引 `ux_members_email`（純 unique index）
改為**部分唯一索引**（partial unique index）`WHERE email IS NOT NULL`
——允許多筆 `email IS NULL`（LINE 未提供 Email 的帳號）並存，但任何一個
非 NULL 的 Email 值仍在全系統唯一（FR-005 在應用層的檢查之外，資料庫層
再提供一層防線）。

**Rationale**：這是本 feature 唯一觸及既有核心 schema 的變更，也是
Summary 中點名的核心技術挑戰——`member.email`／`member.password_hash`
目前被大量既有程式碼假設「一定存在」直接讀取或傳入
`verify_password()`：`login()`（Email／密碼登入，OAuth-only 會員本來就
不會走這條路，不受影響）、`change_password()`／`delete_account()`
（兩者皆呼叫 `verify_password(current_password, member.password_hash)`，
OAuth-only 會員的 `password_hash` 為 `None` 時 MUST 改走略過密碼驗證的
分支，見 data-model.md／contracts/account-recovery-api.md）、既有寄信
流程（驗證信、忘記密碼信、好友通知信——凡是 `member.email` 可能為
`None` 的地方，寄信前 MUST 檢查並略過，不可對 `None` 呼叫寄信函式）。

**Alternatives considered**：
- 讓 LINE 帳號也「一定要有 Email」（若 LINE 未提供，前端手動要求使用者
  輸入一個）——已在 spec.md FR-004（Clarifications）明確否決，維持
  spec 決策不重新展開。
- 對 OAuth-only 會員的 `password_hash` 寫入一個「不可能被驗證通過」的
  隨機雜湊值（維持欄位 `NOT NULL`），而非真正允許 `NULL`——放棄，這種
  「假密碼」的做法會讓 `change_password()`／`delete_account()` 誤判為
  「這個會員原本就有密碼」，導致 FR-008（唯一登入方式不可解除）與
  FR-013（提示補設密碼）的邏輯必須另外發明一套「這個雜湊值是不是假的」
  的判斷依據，比直接允許 `NULL` 更複雜、更容易出錯。

## #5：`member_oauth_identities` 是本 feature 唯一新增的資料表

**Decision**：新增一張 `member_oauth_identities` 表（member_id, provider,
provider_user_id, email_at_link, created_at），`UNIQUE(provider,
provider_user_id)` 實作 FR-007（同一個外部帳號不可重複綁定到另一個
會員），`UNIQUE(member_id, provider)` 實作 FR-006（每個 provider 每個
會員最多一個綁定）。詳見 data-model.md。

**Rationale**：`Member` 既有實體不適合直接長出
`google_sub`/`line_sub`/`google_email`/`line_email` 這種「每加一個
provider 就加兩個欄位」的橫向擴充欄位——未來若要支援 Apple 登入等其他
provider，需要改 schema 加欄位；獨立成一張「多對一」的關聯表則是
provider 數量增加時只需要多一種 `provider` 列舉值，不需要 migration。

## #6：新帳號的 `verification_status`／既有既有驗證信流程的互動

**Decision**：`_complete_oauth_login()`（新函式，
`app/domains/member/service.py`，`complete_oauth_callback()` 的
`intent=login` 分支內部呼叫）建立的新 `Member` 直接以
`verification_status="verified"` 寫入，**不**呼叫既有
`_issue_verification_token_and_email()`（既有 `register()` 會呼叫的
既有輔助函式）——即使該次 OAuth 授權有取得 Email 也一樣不寄驗證信，
因為這個 Email 已經不需要再被「驗證」一次。

**Rationale**：直接對應 spec.md Clarifications 2026-09-14 第一題的
決策（Google／LINE 官方 OAuth 授權本身即等同或高於既有 Email 驗證信的
可信度）。技術上這只是「建立 Member 時 `verification_status` 欄位填
哪個值、要不要呼叫寄信輔助函式」的差異，不需要新增任何 schema 或修改
`require_verified_member` 既有的判斷邏輯（它只檢查
`verification_status == "verified"`，不關心是怎麼變成這個值的）。

## #7：`delete_account()`／`change_password()` 對「無密碼會員」的相容

**Decision**：
- `DeleteAccountRequest.current_password` 改為 `str | None = None`；
  `delete_account()` 內：若 `member.password_hash is not None`，維持
  既有「驗證 `current_password` 正確」的既有行為；若為 `None`（純
  OAuth 會員從未設過密碼），MUST 略過密碼驗證這一步，直接執行既有的
  匿名化流程——已通過 `require_verified_member` 的有效 session 本身
  即是身分證明，與既有「已登入 = 可以做這個會員自己的事」的信任等級
  一致，不因為多了一種帳號類型就臨時提高門檻。
- `ChangePasswordRequest.current_password` 同樣改為 `str | None = None`；
  `change_password()`：若 `member.password_hash is None`，改名為概念上
  的「設定密碼」而非「變更密碼」——略過舊密碼驗證，直接雜湊並寫入
  `new_password`；若已有密碼則維持既有「必須驗證舊密碼」行為不變。此
  端點因此同時服務 FR-013「補設密碼」與既有「變更既有密碼」兩種情境，
  不需要新增一支獨立端點。

**Rationale**：兩個既有端點的既有安全模型（`require_verified_member`
+ 密碼再次確認）在「本來就沒有密碼可以再次確認」的帳號類型下，最小
改動且邏輯自洽的做法就是把「有沒有密碼」當成既有兩個函式內部的一個
分支條件，而非發明兩支平行的新端點——沿用既有 API 合約（路徑、
response shape 不變），只放寬其中一個 request 欄位的必要性。

## #8：FR-013「補上 Email」——新增一支小端點，重用既有驗證信機制

**Decision**：新增 `POST /members/me/email`（`require_verified_member`，
request `{email: str}`）——僅適用於目前 `member.email IS NULL` 的會員
（`email` 已存在時回傳既有的 `EMAIL_ALREADY_SET` 之類錯誤，導向既有
「聯絡客服」或維持現狀，不在本 feature 開放「更換」既有 Email，避免
擴大範圍）；成功時比照既有 `register()` 尾端呼叫
`_issue_verification_token_and_email()`，直接重用既有驗證信 token 模型
與寄信樣板（`member.email` 先寫入這個未驗證的新值，`verification_status`
維持原本已經是 `verified` 不變——這裡验证的是「這個新加入的 Email 真的
是這位會員本人能收到信的信箱」，跟既有「帳號是否可信」是兩件獨立的事，
不倒退成未驗證帳號）。

**Rationale**：完整重用既有 Email 驗證 token/寄信基礎設施（既有
`EmailVerificationToken` 表、既有 `GET /auth/verify-email/{token}`
端點、既有 `resend-verification` 機制），只是新增一個「觸發點」（原本
只有註冊會觸發，現在「幫已存在帳號後補 Email」也能觸發），不重新發明
一套驗證流程。

## #9：Google／LINE 對 Email 可用性的既有差異（確認 spec 假設成立）

**Decision**：維持 spec.md Assumptions 既有判斷——Google 的
`openid email profile` scope 只要使用者同意登入，幾乎必定連帶取得
`email`／`email_verified: true`（Google 帳號的本質就是一個 Email
位址，沒有「Google 帳號但沒有 Email」這種東西）；LINE 的 `email` scope
需要開發者於 LINE Developers Console 額外申請（Email 權限）且使用者
授權當下可自行取消勾選，故只有 LINE 這條路徑需要處理「取得 profile 但
沒有 Email」的分支，Google 路徑不需要。

**Rationale**：純粹確認技術事實，不影響已定案的 FR-004 範圍，記錄於此
供 tasks.md 撰寫測試案例時參考（Google 的單元測試不需要涵蓋「沒有
Email」分支；LINE 的需要）。
