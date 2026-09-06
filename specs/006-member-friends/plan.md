# Implementation Plan: 會員與好友系統（Member & Friend System）

**Branch**: `N/A (no git repository initialized)` | **Date**: 2026-09-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/006-member-friends/spec.md`，交叉比對 `/specs/architecture.md`（`members`/`email_verification_tokens`/`password_reset_tokens`/`friend_requests` DDL 與完整 API 端點清單已定案）、`/specs/001-create-manage-group/`（`Member` 最小 stub、`groups.created_by_member_id`、`roster_entries.member_id`/`nickname` 皆已建立但未賦予完整語意）。

**觸發背景**：`/speckit-plan 004-join-group` 執行前發現 004 spec 之 FR-018/019/020a、FR-006、US6 皆依賴「已登入會員」判斷（暱稱是否已設定、會員帳號與 Player 記錄配對），但目前 `Member` 僅有 001 建立的最小 stub，無任何認證機制。`architecture.md` §7.1 原始建議之實作順序本將「會員帳號核心」排在最前（甚至先於 001），但實際專案進度先完成了 001→002→003，尚未回頭補上此依賴。使用者已確認：暫停 004，先規劃並實作本 feature（006）之會員帳號核心，待完成後再回頭規劃 004。

## Summary

會員可註冊（Email + 密碼，需 Turnstile）、需完成 Email 信箱驗證後才能使用完整功能、可透過忘記密碼流程復原帳號、可在個人設定頁編輯暱稱與修改密碼；已登入會員可透過「忘記管理 PIN 碼」復原自己建立過的團的管理權限；會員可搜尋使用者編號、發送/接受/拒絕好友邀請、解除好友關係。本 feature 將既有 `members` 表最小 stub 擴充為完整帳號實體（ALTER TABLE 新增 email/password_hash/user_number/verification_status/token_version），新建 `email_verification_tokens`/`password_reset_tokens`/`friend_requests` 三張表，新增 `app/domains/member/`（認證、個人設定、使用者編號搜尋）與 `app/domains/friend/`（好友邀請/列表/解除）兩個模組，並於既有 `group/router.py` 新增一個跨模組串接端點（忘記管理 PIN 碼）。會員 JWT（access + refresh）沿用 001 之 `admin_token` 無狀態版本號失效模式；Turnstile 驗證直接重用 `app/core/turnstile.py`；Email 寄送透過新增的 `app/core/email.py`（SES／本地日誌雙後端）完成。

## Technical Context

**Language/Version**：延續 001-003（後端 Python 3.12+；前端 TypeScript / Angular 20+）。

**Primary Dependencies**：新增 `boto3`（Amazon SES 寄信，research.md #5）；其餘沿用既有 FastAPI/SQLAlchemy/Alembic/pyjwt/passlib/slowapi 堆疊，不新增其他套件。

**Storage**：PostgreSQL，ALTER 既有 `members` 表 + 新建 `email_verification_tokens`/`password_reset_tokens`/`friend_requests` 三張表（DDL 見 data-model.md，`architecture.md` 已定案）。

**Testing**：pytest + pytest-asyncio。核心領域邏輯（密碼雜湊/驗證、JWT 簽發與 `token_version` 失效比對、Email 驗證/密碼重設 token 生命週期、使用者編號碰撞重試、`FriendRequest` 狀態機轉換、好友搜尋四狀態判斷）MUST 有單元測試；至少一條整合測試涵蓋「註冊 → 驗證信 → 完成驗證 → 設定暱稱 → 登入 → 修改密碼 → 其他裝置 session 失效」全流程。`EmailSender` 之 `LoggingEmailSender` 實作使測試可直接斷言信件內容包含正確的 token 連結，不需真實外部服務。

**Target Platform**：延續 001-003；`boto3`/SES 呼叫透過既有 AWS 帳號（正式環境）或 `LoggingEmailSender`（本地/CI，見 research.md #5）。

**Project Type**：Web application（monorepo，延續既有結構）。

**Performance Goals**：延續既有標準，本 feature 無新增高頻端點（好友邀請通知明確定案為非即時，FR-041）。

**Constraints**：會員 JWT 採無狀態版本號比對（research.md #2），MUST NOT 新增 session/token 黑名單資料表；Email 寄送失敗 MUST NOT 使呼叫端請求失敗（research.md #5，比照 Ably `publish()` 之容錯哲學）；`PATCH /members/me/nickname` MUST NOT 連動更新既有 `roster_entries` 列（research.md #10，FR-024）。

**Scale/Scope**：會員規模與好友關係數量預期為中小型社群規模（數千會員等級），`friend_requests` 之部分唯一索引與既有 `pair_history` 等表之查詢模式相近，無特殊效能疑慮。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | Pydantic v2 schema 對應所有請求/回應；SQLAlchemy 2.0 型別化 `Member`（擴充既有 model）、`EmailVerificationToken`、`PasswordResetToken`、`FriendRequest`；`ruff`/`mypy --strict` blocking check。 | PASS |
| II. 測試優先 | 密碼雜湊/JWT/token 生命週期/使用者編號碰撞/好友狀態機皆屬核心領域邏輯，MUST 有單元測試；至少一條整合測試涵蓋「註冊→驗證→登入→修改密碼」全流程。 | PASS（列入 tasks.md 強制項） |
| III. 即時性與一致性 | 本 feature 無計分板/控制板相關狀態，「設定變更時間一致性」不適用；好友邀請明確定案為非即時（FR-041），不透過 Ably。 | PASS（不適用之處已說明） |
| IV. 權限與安全 | 會員密碼 MUST 單向雜湊（bcrypt，同管理 PIN 碼演算法但獨立 `CryptContext` 實例，research.md #3）；Email MUST 格式驗證且系統內唯一（FR-004/006）；未驗證帳號 MUST 全面鎖定除驗證提示外的所有功能（FR-009，`require_verified_member` dependency 落實）；註冊端點 MUST 整合 Turnstile（FR-001，重用 `app/core/turnstile.py`）；登入端點 MUST 具備 per-IP 速率限制、MUST NOT 採帳號鎖定（FR-002a，2026-09-01 澄清，research.md #6）；忘記密碼 MUST NOT 洩漏帳號是否存在（FR-013，同日澄清）。 | PASS |
| V. UX 一致性 | 解除好友 MUST 提供二次確認（FR-043，前端落實，於 tasks.md 展開）。 | PASS |
| VI. 可維護性 | `member`/`friend` 兩個獨立模組（research.md #1）；對 `group/router.py` 的唯一觸碰（忘記管理 PIN 碼）已於 research.md #7 明確界定為新增端點、複用既有 PIN 重設核心邏輯，不變更既有函式簽章。 | PASS |
| VII. 無障礙 | 本 feature 無新增視覺分類元素（沿用既有表單元件慣例），不適用。 | PASS（不適用） |
| VIII. i18n 與時區 | 錯誤回應一律語意化代碼（`EMAIL_ALREADY_REGISTERED`、`VERIFICATION_TOKEN_EXPIRED` 等）；`email_verification_tokens`/`password_reset_tokens`/`friend_requests` 之時間欄位皆用 `TIMESTAMPTZ`。 | PASS |
| IX. 可攜性 | `boto3`/SES 金鑰透過環境變數注入（沿用既有 Secrets Manager 模式）；本地開發預設 `LoggingEmailSender`，不強制要求 AWS 憑證即可開發。 | PASS |
| X. 伺服器為單一事實來源 | 好友系統無即時廣播需求（FR-041 明確排除）；忘記管理 PIN 碼複用既有 `link.regenerated` 廣播（DB 交易提交後才發布）。 | PASS |
| XI. 防機器人 | 註冊端點 MUST 整合 Turnstile（FR-001，重用既有機制）；登入/忘記密碼/修改密碼明確排除（FR-002），改以速率限制防護（research.md #6）。 | PASS |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/006-member-friends/
├── plan.md                        # 本檔案
├── research.md                    # Phase 0 產出
├── data-model.md                  # Phase 1 產出
├── quickstart.md                  # Phase 1 產出
├── contracts/                     # Phase 1 產出
│   ├── auth-api.md
│   ├── member-api.md
│   ├── friends-api.md
│   └── forgot-admin-pin-api.md
└── tasks.md                       # /speckit-tasks 產出（本指令不建立）
```

### Source Code (repository root)

```text
apps/api/
├── app/
│   ├── core/
│   │   └── email.py             # 新增：EmailSender 介面 + SesEmailSender/LoggingEmailSender
│   ├── domains/
│   │   ├── member/
│   │   │   ├── models.py        # 擴充既有 Member：email/password_hash/user_number/verification_status/token_version
│   │   │   ├── schemas.py       # 新增：註冊/登入/個人設定/搜尋 請求回應
│   │   │   ├── security.py      # 新增：密碼雜湊、access/refresh JWT 簽發驗證、使用者編號產生
│   │   │   ├── service.py       # 新增：註冊/登入/驗證/忘記密碼/個人設定 業務邏輯
│   │   │   └── router.py        # 新增：/auth/*、/members/* 端點
│   │   ├── friend/
│   │   │   ├── models.py        # 新增：FriendRequest
│   │   │   ├── schemas.py
│   │   │   ├── service.py
│   │   │   └── router.py        # 新增：/friends/* 端點
│   │   └── group/
│   │       └── router.py        # 擴充：POST /groups/{group_id}/forgot-admin-pin
│   └── ...                      # core/db、core/rate_limit、core/turnstile 皆重用既有，不變動
└── tests/
    ├── unit/domains/member/
    ├── unit/domains/friend/
    ├── contract/
    └── integration/

apps/web/
└── src/app/features/
    ├── auth/
    │   ├── register/
    │   ├── login/
    │   ├── verify-email/
    │   ├── forgot-password/
    │   └── reset-password/
    ├── member/
    │   ├── member-info/           # 會員資訊頁（FR-021）
    │   ├── settings/              # 個人設定頁（暱稱/密碼）
    │   └── my-groups/             # 忘記管理 PIN 碼列表
    └── friends/
        ├── friend-list/
        ├── friend-search/
        └── friend-requests/
```

**Structure Decision**：`app/domains/member` 由 001 之最小 stub 擴充為完整帳號模組；新增 `app/domains/friend` 獨立模組（research.md #1）；`app/core/email.py` 為新的共用基礎設施模組（比照 `app/core/turnstile.py`/`app/core/realtime.py` 之既有慣例：單一外部 I/O 出口）；對 `group` 模組唯一的擴充（忘記管理 PIN 碼端點）維持「新增，不變更既有行為」原則。前端新增三個對等的 feature 目錄（`auth`/`member`/`friends`），對應本 feature 三個關注點各自的畫面群。

## Complexity Tracking

*本 feature 無 Constitution Check 違反項目，此表格從略。*

## Post-Design Constitution Check

*Re-evaluated after Phase 1（`data-model.md`、`contracts/`、`quickstart.md`）產出。*

設計階段的關鍵決策——(1) 會員 JWT 沿用 001 之無狀態版本號失效模式而非新建 session 表（research.md #2）、(2) Email 寄送以獨立 `EmailSender` 介面隔離外部依賴且失敗不阻斷主要業務流程（research.md #5，呼應 constitution X 之既有容錯哲學）、(3) 忘記管理 PIN 碼複用 `group` 模組既有 PIN 重設核心邏輯與既有 Ably 事件、不新建平行邏輯（research.md #7）——皆為在不違反任何 FR 的前提下確保正確性與模組邊界的實作細節，未引入新的 Constitution 違反項目。**Gate 結果維持 PASS，無需新增 Complexity Tracking 項目。**

## Assumptions

- 本 feature 之實作範圍涵蓋 spec.md 全部 6 個 User Story；但依 `architecture.md` §7.1 原始建議順序與本次觸發背景（解除 004 之阻塞依賴），**建議優先完成 P1（US1 註冊/驗證、US2 登入/忘記密碼、US3 個人設定）作為「會員帳號核心」checkpoint**，即可回頭恢復 004 之規劃與實作；US4（忘記管理 PIN 碼）、US5/US6（好友系統）為 P2，可視時程安排於稍後的階段完成，不阻擋 004。此優先順序將於 `/speckit-tasks` 產出的 tasks.md 之 Implementation Strategy 段落具體化。
- Email 寄送內容（HTML 樣板、寄件人顯示名稱等視覺細節）留待 tasks.md 實作階段決定基本純文字/簡易 HTML 內容即可，本 plan 不預先設計樣板。
- 前端各頁面之路由結構（`/auth/register` 等路徑）延續既有 Angular routing 慣例，具體路由設定留待 tasks.md 展開。
