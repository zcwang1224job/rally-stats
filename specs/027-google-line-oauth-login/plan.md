# Implementation Plan: 使用 Google／LINE 帳號註冊與登入

**Branch**: `main`（本專案未使用 per-feature git branch，延續既有慣例）| **Date**: 2026-09-14 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/027-google-line-oauth-login/spec.md`，
交叉比對 `/specs/006-member-friends`（既有 `Member` 實體、`login()`／
`register()`／`issue_access_token()`／`issue_refresh_token()`／
`require_verified_member` 既有認證核心）、`/specs/022-member-personal-settings`
（既有 `PrivacySettingsRequest`/`MemberPublicResponse` 擴充模式）、
`/specs/025-delete-account`（既有 `delete_account()`／匿名化就地保留列
的既有作法）。

## Summary

本 feature 在既有 Email／密碼註冊/登入之外，新增「使用 Google 繼續」／
「使用 LINE 繼續」兩個入口：訪客可直接以 Google／LINE 帳號一鍵建立帳號
並登入（US1/US2），既有 Email／密碼會員則可在個人設定主動把自己的帳號
與 Google／LINE 帳號綁定，之後任一方式皆可登入回同一個帳號（US3）。

核心技術挑戰有兩個：

1. **既有 `members.email`／`members.password_hash` 兩個欄位目前皆為
   `NOT NULL`，被為數不少的既有程式碼（`login()`、
   `change_password()`、`delete_account()`、既有寄信流程）直接假設
   「一定存在」**——本 feature 因 FR-004（LINE 的 Email 為選用授權
   項目）與「純 OAuth 帳號沒有密碼」的本質，MUST 讓兩個欄位改為可為
   空，並逐一排查、修正每一個既有假設其非空的呼叫點（research.md
   #4/#7，完整清單見 data-model.md §1）。
2. **OAuth 交握必須把最終結果安全地帶回既有前端 `AuthService`
   （`localStorage` token 模型，不是 Cookie-based session）**——本
   feature 採用「後端全權代理整個 Authorization Code + PKCE 交握，
   透過一次 302 redirect 把 token 用 URL fragment 帶回前端一個新的
   回呼落地頁」的設計（research.md #1/#2），讓 OAuth 登入的最終行為
   與既有 Email／密碼登入殊途同歸、共用同一套 `AuthService`/HTTP
   interceptor 邏輯，不引入第二套並存的認證機制。

其餘技術決策（見 research.md）：新增 `authlib` 依賴以正確驗證
Google／LINE 回傳的 `id_token`（JWKS 簽章驗證，資安敏感區域不手刻，
research.md #3）；新增一張 `member_oauth_identities` 關聯表（而非在
`Member` 上橫向新增每個 provider 各一組的欄位，research.md #5）；
`state` 參數本身是一顆簽章 JWT（重用既有 `jwt_secret`），不新增資料表
與對應清除排程（research.md #2）；`change_password()`／
`delete_account()` 兩個既有端點改為在「該會員目前沒有密碼」時略過密碼
再次驗證，而非新增平行的端點（research.md #7）。

## Technical Context

**Language/Version**：延續既有（後端 Python 3.12 + FastAPI；前端
TypeScript / Angular 20+）。

**Primary Dependencies**：沿用既有堆疊（SQLAlchemy 2.x async ORM、
Alembic migration、Pydantic v2、httpx；前端 RxJS、ngx-translate）。
**新增一個後端依賴：`authlib`**（OAuth2/OIDC client，含 JWKS 簽章驗證），
理由見 research.md #3——這是本專案第一次需要處理第三方身分提供者的
JWT 簽章驗證，屬於資安敏感區域，不手刻。

**Storage**：PostgreSQL（既有）。新增一個 migration：新增
`member_oauth_identities` 表（data-model.md §2）；`members.email`／
`members.password_hash` 改為 `nullable`；`ux_members_email` 改為部分
唯一索引（`WHERE email IS NOT NULL`，data-model.md §1）。

**Testing**：pytest（後端）：新 migration 的欄位可為空性/索引正確性、
`member_oauth_identities` 的兩條 UNIQUE 約束（FR-006/FR-007）、OAuth
callback 服務函式（`intent=login`／`intent=link` 各自的成功/衝突/取消
分支，涵蓋 Google 一定有 Email、LINE 可能沒有 Email 兩種 provider 回應）、
`state` JWT 的簽章/效期驗證、`change_password()`／`delete_account()`
在「有密碼」/「無密碼」兩種會員下的分支行為、`_complete_oauth_login()`
建立的新帳號 `verification_status` 直接為 `verified`（Clarifications
2026-09-14 第一題）、FR-005 的 Email 撞號檢查涵蓋既有 Email／密碼會員與
既有 OAuth-only 會員兩種既有帳號類型。Vitest（前端）：新的
`/auth/oauth-callback` 落地頁元件（讀取 `#fragment`、呼叫既有
`AuthService.setTokens()`、依 `status`/`code` 導向不同結果）、登入頁
新增的兩顆「使用 Google／LINE 繼續」入口（整頁導向 `authorize_url`）、
個人設定頁的綁定狀態顯示與 FR-013 提醒的顯示條件。

**Target Platform**：延續既有（Docker on AWS ECS，本地
`docker-compose`）；本 feature 需在容器環境設定四個新環境變數
（`google_oauth_client_id`/`_secret`、`line_oauth_channel_id`/
`_secret`），沿用既有 `Settings`（`app/core/config.py`）機制，不新增
基礎設施元件。

**Project Type**：Web application（monorepo）；本 feature 同時觸及
`apps/api` 與 `apps/web`。

**Performance Goals**：SC-001（外部授權畫面操作完成後，本系統這一側
3 秒內完成帳號建立/登入並回到已登入狀態）——OAuth callback 一次處理
（換 token、驗簽、DB 查詢/寫入、核發 token）預期落在既有 `login()`/
`register()` 同等的資料庫往返數量級，額外的網路成本僅是對
Google/LINE token endpoint 與 JWKS endpoint 各一次 HTTPS 請求（JWKS
可考慮短期記憶體快取，降低重複請求，非本 feature 的強制要求）。

**Constraints**：FR-005/FR-007——Email／provider 身分撞號的檢查 MUST
在寫入新 `Member`/`member_oauth_identities` 列**之前**於同一個資料庫
交易內完成，避免併發請求造成的 race condition 繞過唯一性檢查（資料庫
唯一索引本身是最終防線，見 data-model.md §1/§2，應用層檢查 MUST 搭配
索引違反時轉譯為對應的既有/新增錯誤代碼，而不是讓 `IntegrityError`
直接外洩為 500）。FR-010——OAuth 取消/失敗流程 MUST NOT 建立任何部分
寫入的帳號或綁定紀錄（單一資料庫交易，失敗即 rollback）。

**Scale/Scope**：與既有 Email／密碼註冊/登入同等規模（單次請求，無
批次語意），不需要額外的分頁或速率限制設計；JWKS 金鑰快取（若實作）
規模為個位數公鑰，不需要額外的快取基礎設施。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | 新增/擴充的 Pydantic schema（`member_oauth_identities` 對應的 request/response、`MemberPublicResponse.email: str \| None`、`linked_oauth_providers`）與對應 TS 介面皆完整定型；`state` JWT 的 payload 以型別化的 dataclass/TypedDict 建構，不使用 `dict[str, Any]` 直接讀寫；mypy --strict／`tsc --strict`／ESLint 皆為既有 blocking check，不新增例外。 | PASS |
| II. 測試優先 | OAuth callback 的每個分支（成功/撞號/取消/已刪除帳號/重複綁定）屬於核心認證邏輯，MUST 有對應單元/contract 測試；`state` 簽章驗證、`member_oauth_identities` 的兩條 UNIQUE 約束在併發下的行為 MUST 有測試覆蓋（見 tasks.md）。 | PASS |
| III. 即時性與資料一致性 | 本 feature 不觸及計分板/控制板/賽程即時同步，不適用。 | 不適用 |
| IV. 權限與安全 | 新端點 `intent=login` 時公開（比照既有 `register()`/`login()` 的公開端點定位），`intent=link` 與帳號綁定管理端點皆掛在既有 `require_verified_member` 之上，不新增獨立權限判斷邏輯。**對「會員帳號 MUST 完成 Email 驗證後才能使用任何功能」一條的解釋延伸**：OAuth 建立的新帳號不會經過既有 Email 驗證信這個*機制*，但 Clarifications 2026-09-14 第一題已明確決策——Google／LINE 官方 OAuth 授權本身是一種與既有 Email 驗證同等或更高可信度的身分佐證，`verification_status` 因此直接為 `verified`，滿足的是本原則「未經身分確認不得使用功能」的精神，而非繞過它；`require_verified_member` 的既有判斷邏輯（檢查 `verification_status` 欄位值）完全不需修改。**對「Email MUST 在系統內保持唯一」一條**：`members.email` 允許 `NULL`（LINE 未提供時），但任何非 `NULL` 值仍透過部分唯一索引保證全系統唯一（data-model.md §1）；FR-005/FR-007 的撞號防護則進一步防止「同一個真實 Email 被不同帳號各自持有」的資安風險（避免帳號劫持），比字面上的「Email 必填」更貼近本原則「防止身分混淆」的核心目的。密碼欄位（`password_hash`）允許 `NULL` 屬於本 feature 引入的新帳號類型（純 OAuth）本身沒有密碼這一既有事實的如實反映，「密碼 MUST 單向雜湊儲存」在密碼存在時依然成立、不受影響。 | PASS（延伸解釋，已明確記錄） |
| V. UX 一致性（破壞性操作二次確認） | 解除 OAuth 綁定（`DELETE /members/me/oauth-identities/{provider}`）、刪除帳號（`DELETE /members/me`，含無密碼分支）皆為既有/新增的可能造成帳號存取能力喪失的操作，前端 MUST 提供二次確認對話框（無密碼會員的刪除帳號僅省略「輸入密碼」欄位，確認對話框本身不省略）。 | PASS |
| VI. 可維護性 | Provider 專屬設定（`authorize_url`/`token_url`/`jwks_url`/`client_id`/`client_secret`/`scopes`）集中於新增的 `app/domains/member/oauth_providers.py` 一個小型設定表，router/service 層只以 `provider` 字串與這張表打交道，不出現 provider 專屬的 if/else 散落在核心邏輯（research.md #3）；新增邏輯集中於既有 `member` domain，不建立新 domain。 | PASS |
| VII. 無障礙與行動裝置優先 | 「使用 Google／LINE 繼續」兩顆新按鈕沿用既有 `.btn`/`.btn--secondary` 版面慣例，圖示（Google/LINE 官方品牌圖示）搭配文字標籤，不僅靠圖示或顏色區分兩個入口。 | PASS |
| VIII. i18n 與時區 | 新增顯示文字（兩顆入口按鈕文字、回呼落地頁的各種狀態訊息、FR-013 提醒文字、個人設定綁定狀態文字）集中於 `zh-TW.json`/`en.json`；新增錯誤碼（`OAUTH_STATE_INVALID`/`OAUTH_PROVIDER_ERROR`/`ACCOUNT_DELETED`/`OAUTH_EMAIL_ALREADY_REGISTERED`/`OAUTH_IDENTITY_ALREADY_LINKED`/`OAUTH_PROVIDER_ALREADY_LINKED`/`OAUTH_IDENTITY_NOT_LINKED`/`LAST_LOGIN_METHOD`/`EMAIL_ALREADY_SET`，`OAUTH_PROVIDER_ALREADY_LINKED` 為 /speckit-analyze 2026-09-14 remediation 新增，對應 FR-006 的 C1 補充）比照既有慣例加入 `errors` 物件，由既有 `error-interceptor`/`ApiError` 機制轉譯，不回傳寫死中文句子。本 feature 新增的唯一時間欄位（`member_oauth_identities.created_at`）沿用既有「系統自動記錄的絕對時間戳」規則（`TIMESTAMPTZ`/UTC/ISO 8601）。 | PASS |
| IX. 可攜性與可部署性 | 新增 `authlib` 依賴寫入 `requirements.txt`（本專案的依賴實際由 requirements.txt/requirements-dev.txt 管理，非 pyproject.toml——實作階段修正）；四個新環境變數（`google_oauth_client_id`/`_secret`、`line_oauth_channel_id`/`_secret`）透過既有 `Settings`/`.env` 機制注入，不寫死在程式碼中；Docker 建置流程不需改動（純 Python 依賴，既有 `pip install`/建置步驟已涵蓋）。 | PASS |
| X. 即時同步的可信來源 | 本 feature 不觸及比分/賽程狀態，不適用；但精神上延伸適用於 OAuth 交握本身——`code`/`state` 的驗證與 token 核發全程在後端完成，前端僅接收最終結果，不參與任何需要信任判斷的步驟（research.md #1）。 | 不適用（精神延伸已落實） |
| XI. 防機器人/防濫用 | 沿用 spec.md Assumptions 既有決策——OAuth 授權流程本身已具備等同 Turnstile 的防自動化機器人保護，新帳號建立不重複要求 Turnstile；`/auth/oauth/{provider}/start`／`/callback` 兩端點仍沿用既有 `20/minute` 速率限制（比照 `POST /auth/login`）作為額外的粗粒度防護。 | PASS（不適用 Turnstile，已於 spec.md 明確記錄） |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking（原則 IV 的
兩處延伸解釋已在上表明確記錄理由，非未說明的偏離）。

## Project Structure

### Documentation (this feature)

```text
specs/027-google-line-oauth-login/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/
│   ├── oauth-login-api.md
│   └── account-recovery-api.md
└── tasks.md             # Phase 2 output (/speckit-tasks command — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
apps/api/
├── requirements.txt      # + authlib 依賴（research.md #3；實際依賴檔，非 pyproject.toml）
├── alembic/versions/
│   └── <rev>_member_oauth_identities.py
│                         # 新增 member_oauth_identities 表；
│                         #   members.email/password_hash 改為 nullable；
│                         #   ux_members_email 改為部分唯一索引
├── app/core/config.py   # + google_oauth_client_id/_secret、
│                         #   line_oauth_channel_id/_secret 四個新設定
├── app/domains/member/
│   ├── models.py         # + Member.email/password_hash 改 nullable；
│   │                         #   + MemberOAuthIdentity 新 ORM model
│   ├── oauth_providers.py # 新增：GOOGLE/LINE 的 OAuthProviderConfig
│   │                         #   設定表（research.md #3）
│   ├── schemas.py         # + MemberPublicResponse.email: str | None、
│   │                         #   + linked_oauth_providers；
│   │                         #   ChangePasswordRequest/DeleteAccountRequest
│   │                         #   的 current_password 改為 Optional
│   ├── security.py        # + issue_oauth_state()/decode_oauth_state()
│   │                         #   （typ: "oauth_state"，重用既有
│   │                         #   _issue_token()/_decode_token() 機制）
│   ├── service.py         # + start_oauth_flow()、
│   │                         #   + complete_oauth_callback()（intent
│   │                         #   分流：login 建新帳號或既有登入、link
│   │                         #   綁定既有帳號）、
│   │                         #   + unlink_oauth_identity()、
│   │                         #   + add_email()（FR-013）；
│   │                         #   change_password()/delete_account() 新增
│   │                         #   「密碼可能不存在」分支（research.md #7）
│   └── router.py          # + GET /auth/oauth/{provider}/start
│                         #   + GET /auth/oauth/{provider}/callback
│                         #   + DELETE /members/me/oauth-identities/{provider}
│                         #   + POST /members/me/email
└── app/core/errors.py    # 不需改動（既有 ApiError 機制沿用）

apps/web/src/app/
├── features/auth/
│   ├── auth.service.ts   # 不需改動核心邏輯（既有 setTokens() 重用）
│   ├── login/login.component.html/.ts
│   │                         # + 「使用 Google 繼續」/「使用 LINE 繼續」
│   │                         #   兩顆按鈕，呼叫 GET .../start 後整頁導向
│   └── oauth-callback/       # 新增：/auth/oauth-callback 落地頁元件
│       ├── oauth-callback.component.ts
│       │                     # 讀取 location.hash，呼叫既有
│       │                     #   AuthService.setTokens()，依 status 導向
│       ├── oauth-callback.component.html
│       └── oauth-callback.component.spec.ts
├── core/api/member-auth.models.ts
│                         # email?: string | null；
│                         #   + linkedOauthProviders；
│                         #   currentPassword 改為可選
└── features/member/settings/
    ├── settings.component.html/.ts
    │                         # + Google/LINE 綁定狀態與「綁定」/「解除」
    │                         #   按鈕；+ FR-013 非強制提醒區塊；
    │                         #   + 補上 Email 的表單（POST .../email）
    └── settings.component.spec.ts
```

**Structure Decision**：後端變更集中於既有 `member` domain（新增
`oauth_providers.py` 一個小檔案封裝 provider 差異，其餘皆是既有
`models.py`/`schemas.py`/`security.py`/`service.py`/`router.py` 的
擴充），不新增 domain；前端新增一個獨立的 `features/auth/oauth-callback/`
路由元件，既有 `login.component`/`settings.component` 僅做局部擴充，
不新增新的 feature 目錄。

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

無違反項目，本表格從缺。
