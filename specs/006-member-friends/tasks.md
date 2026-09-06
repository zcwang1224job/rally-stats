# Tasks: 會員與好友系統（Member & Friend System）

**Input**: Design documents from `/specs/006-member-friends/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md（皆已存在）

**Tests**: 依 `plan.md` Constitution Check（原則 II），核心領域邏輯（密碼雜湊/JWT 簽發與 `token_version` 失效比對、Email 驗證/密碼重設 token 生命週期、使用者編號碰撞重試、`FriendRequest` 狀態機轉換、好友搜尋四狀態判斷）MUST 有單元測試，且 MUST 有至少一條涵蓋「註冊→驗證→登入→修改密碼→其他裝置 session 失效」的整合測試——本檔案的測試任務為強制項，非選用。

**Organization**：依 spec.md 之 6 個 User Story（US1–US6，依優先序 P1/P1/P1/P2/P2/P2）分階段組織，每個 Story 皆可獨立測試與交付。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行執行（不同檔案、無相依關係）
- **[Story]**: 對應 spec.md 的 US1–US6
- 每項任務皆附精確檔案路徑

## 完成狀態備註（2026-09-02）

T040–T069（US4–US6 + Polish）當初標記為未完成，但已在
`specs/010-app-wide-ui-redesign`（US7：「完成好友系統與會員團記錄復原功能」）
的實作過程中一併完成——010 的 spec.md/research.md 明確將本檔案列為權威依據
（FR-018），未重新定義任何 API 合約或資料模型，純粹是把這裡剩下的工作做完。
逐項核對後的狀態：

- **T040–T046、T048–T065（28 項）**：已完成，檔案路徑與下方描述完全一致。
- **T055**：功能已完成，但實際元件路徑為
  `apps/web/src/app/features/friends/friend-add/friend-add.component.ts`
  （原描述為 `friend-search/friend-search.component.ts`）——功能等價，僅目錄
  命名不同。
- **T047、T066、T067、T068**：010 完成主體工作時遺漏，已於本次
  （2026-09-02）補齊：T047 加上匿名建團專屬提醒文字、T066 新增
  `test_member_lifecycle.py`、T067 已手動以 curl 逐一走過本檔案
  `quickstart.md` 全部 5 個情境並確認結果相符、T068 補上
  `list_incoming_requests` 缺少的 docstring。
- **T069（安全審查）**：已於 010 的 Polish 階段執行並確認通過（見
  `specs/010-app-wide-ui-redesign/tasks.md` T057）。

## Path Conventions

沿用 `plan.md` Project Structure：`apps/api/`（FastAPI 後端）、`apps/web/`（Angular 20 前端）。monorepo 骨架已由 001 建立，本 feature 無新增 Setup 任務。

---

## Phase 1: Setup

*本 feature 無新增 Setup 任務——monorepo、CI、linting/型別檢查工具鏈已由 001 完整建立並沿用。*

---

## Phase 2: Foundational（Blocking Prerequisites）

**Purpose**：本 feature 6 個 User Story 皆需依賴的資料模型、認證基礎設施、router 骨架。`POST /auth/login`/`POST /auth/refresh` 雖然標題上屬 US2「登入與忘記密碼」，但兩者本身無專屬 FR/驗收情境（登入成功與換發新 access token 為隱含的基礎行為），且 US1 之 `POST /auth/resend-verification`（FR-011 明定「登入後才可觸發」）與後續 US3–US6 之受保護端點皆硬性依賴已存在的登入機制才能運作或測試，故比照「共用基礎設施」原則排入本階段，而非等待 US2。

**⚠️ CRITICAL**：此階段完成前不可開始任何 User Story 任務。

- [X] T001 Create Alembic migration：ALTER `members`（新增 `email`/`password_hash`/`user_number`/`verification_status`/`token_version`）+ CREATE `email_verification_tokens`/`password_reset_tokens`/`friend_requests` per `data-model.md` §1–4 in `apps/api/alembic/versions/`
- [X] T002 [P] Extend `Member` model（新增欄位）+ create `EmailVerificationToken`、`PasswordResetToken` models in `apps/api/app/domains/member/models.py`
- [X] T003 [P] Create `FriendRequest` model in `apps/api/app/domains/friend/models.py`
- [X] T004 [P] Create `apps/api/app/core/email.py`（`EmailSender` 介面 + `SesEmailSender` + `LoggingEmailSender`，per research.md #5）+ 新增 `email_backend`/SES 相關設定值於 `apps/api/app/core/config.py`
- [X] T005 [P] Create `apps/api/app/domains/member/security.py`（獨立 `CryptContext` 密碼雜湊/驗證、access+refresh JWT 簽發/解碼、`require_member`/`require_verified_member` FastAPI dependency、使用者編號產生+碰撞重試，per research.md #2/#3/#8）+ 新增 `member_access_token_ttl_minutes`/`member_refresh_token_ttl_days` 設定值於 `apps/api/app/core/config.py`
- [X] T006 [P] Define Pydantic schemas skeleton per `contracts/auth-api.md`、`contracts/member-api.md` in `apps/api/app/domains/member/schemas.py`
- [X] T007 [P] Define Pydantic schemas skeleton per `contracts/friends-api.md` in `apps/api/app/domains/friend/schemas.py`
- [X] T008 Create `apps/api/app/domains/member/service.py` + `apps/api/app/domains/member/router.py`（空 `APIRouter`）與 `apps/api/app/domains/friend/service.py` + `apps/api/app/domains/friend/router.py`（空 `APIRouter`），並註冊於 `apps/api/app/main.py`
- [X] T009 [P] Unit test：密碼雜湊/驗證 round-trip、access/refresh JWT 簽發解碼（含 `token_version` 不符時拒絕、`type` 欄位區分 access/refresh 互不可誤用）in `apps/api/tests/unit/domains/member/test_security.py`
- [X] T010 [P] Unit test：使用者編號格式（排除易混淆字元）與碰撞重試邏輯 in `apps/api/tests/unit/domains/member/test_user_number.py`
- [X] T011 [P] Contract test for `POST /auth/login`、`POST /auth/refresh` per `contracts/auth-api.md`（含未驗證帳號仍可登入、密碼錯誤、FR-002a per-IP 速率限制）in `apps/api/tests/contract/test_auth_login.py`
- [X] T012 Implement `POST /auth/login`、`POST /auth/refresh` in `apps/api/app/domains/member/service.py` + `apps/api/app/domains/member/router.py`（含 FR-002a per-IP 速率限制，重用 `app/core/rate_limit.py`）(depends on T005, T006, T008)

**Checkpoint**：Foundation ready — User Story 任務可以開始。

---

## Phase 3: User Story 1 - 會員註冊與 Email 驗證 (Priority: P1) 🎯 MVP

**Goal**：使用者填寫 Email、密碼完成註冊，帳號初始為未驗證狀態並收到驗證信；未驗證期間登入僅能看到驗證提示；完成驗證後（若尚未設定過暱稱）導向設定暱稱流程。

**Independent Test**：完整走過「填寫註冊表單 → 收到驗證信 → 點擊驗證連結 → 完成驗證」流程獨立驗證，亦可測試 Email 重複註冊、Turnstile 驗證失敗、驗證連結逾期等分支；「設定暱稱」本身之 `PATCH` 端點屬 US3 範圍，本 story 僅驗證驗證完成後 `GET /members/me` 正確回傳 `nickname: null` 供前端判斷是否導向設定流程。

### Tests for User Story 1

- [X] T013 [P] [US1] Unit test：FR-004 Email 唯一性（含大小寫正規化後視為相同）拒絕重複註冊 in `apps/api/tests/unit/domains/member/test_registration_validation.py`
- [X] T014 [P] [US1] Unit test：`email_verification_tokens` 生命週期——註冊時建立、效期判斷、`used_at` 標記、已使用/已逾期之語意化錯誤 in `apps/api/tests/unit/domains/member/test_email_verification.py`
- [X] T015 [P] [US1] Unit test：FR-011 重新發送驗證信之「同一帳號 60 秒內僅一次」速率限制（research.md #6，DB 時間戳比對）in `apps/api/tests/unit/domains/member/test_resend_verification_rate_limit.py`
- [X] T016 [P] [US1] Contract test for `POST /auth/register`（含 Turnstile 失敗、Email 重複、密碼不一致）per `contracts/auth-api.md` in `apps/api/tests/contract/test_register.py`
- [X] T017 [P] [US1] Contract test for `GET /auth/verify-email/{token}`、`POST /auth/resend-verification` per `contracts/auth-api.md` in `apps/api/tests/contract/test_verify_email.py`
- [X] T018 [US1] Integration test：註冊 → `LoggingEmailSender` 擷取驗證連結 → 呼叫驗證端點 → `verification_status` 轉為 verified → `GET /members/me` 回傳 `nickname: null`（供前端導向設定暱稱流程）in `apps/api/tests/integration/test_registration_flow.py`

### Implementation for User Story 1

- [X] T019 [US1] Implement `POST /auth/register`（Turnstile 驗證重用 `app/core/turnstile.py`、Email 正規化+唯一性、密碼雜湊、使用者編號產生、建立 `email_verification_tokens` 並透過 `EmailSender` 寄送）in `apps/api/app/domains/member/service.py` + `apps/api/app/domains/member/router.py` (depends on T012)
- [X] T020 [US1] Implement `GET /auth/verify-email/{token}` in `apps/api/app/domains/member/service.py` + `apps/api/app/domains/member/router.py`
- [X] T021 [US1] Implement `POST /auth/resend-verification`（`require_member` + 60 秒速率限制 + 新 token 核發）in `apps/api/app/domains/member/service.py` + `apps/api/app/domains/member/router.py`
- [X] T022 [US1] Implement `GET /members/me` in `apps/api/app/domains/member/service.py` + `apps/api/app/domains/member/router.py`
- [X] T023 [P] [US1] Angular 註冊頁（重用既有 Turnstile widget）in `apps/web/src/app/features/auth/register/register.component.ts`
- [X] T024 [P] [US1] Angular 「請驗證你的信箱」提示頁 + Email 驗證連結處理頁 in `apps/web/src/app/features/auth/verify-email/verify-email.component.ts`

**Checkpoint**：US1 完整可運作——可獨立展示「註冊 → 驗證信 → 完成驗證」。

---

## Phase 4: User Story 2 - 登入與忘記密碼 (Priority: P1)

**Goal**：忘記密碼可透過 Email 收信重設，重設成功後所有裝置的登入狀態皆須以新密碼重新登入；`POST /auth/login`/`POST /auth/refresh` 本身已於 Foundational 完成。

**Independent Test**：用一個已註冊帳號測試忘記密碼流程對多裝置 session 的影響，並測試速率限制、帳號不存在時的一致回應，無需依賴個人設定或好友系統。

### Tests for User Story 2

- [X] T025 [P] [US2] Unit test：`password_reset_tokens` 生命週期（1 小時效期、`used_at`、已使用/已逾期語意化錯誤）in `apps/api/tests/unit/domains/member/test_password_reset.py`
- [X] T026 [P] [US2] Unit test：FR-013 忘記密碼——Email 不存在時回應與存在時完全相同（2026-09-01 澄清，避免帳號枚舉）in `apps/api/tests/unit/domains/member/test_forgot_password_enumeration.py`
- [X] T027 [P] [US2] Unit test：重設密碼成功同時 `verification_status='verified'` 且 `token_version += 1`（FR-014/015，所有裝置失效）in `apps/api/tests/unit/domains/member/test_reset_password_invalidation.py`
- [X] T028 [P] [US2] Contract test for `POST /auth/forgot-password`、`POST /auth/reset-password/{token}` per `contracts/auth-api.md` in `apps/api/tests/contract/test_forgot_password.py`
- [X] T029 [US2] Integration test：兩裝置皆登入 → 忘記密碼重設 → 兩裝置舊 token 皆失效 → 須以新密碼重新登入 in `apps/api/tests/integration/test_forgot_password_flow.py`

### Implementation for User Story 2

- [X] T030 [US2] Implement `POST /auth/forgot-password`（per-IP 速率限制、帳號存在與否回應一致、`EmailSender` 寄送）in `apps/api/app/domains/member/service.py` + `apps/api/app/domains/member/router.py`
- [X] T031 [US2] Implement `POST /auth/reset-password/{token}` in `apps/api/app/domains/member/service.py` + `apps/api/app/domains/member/router.py`
- [X] T032 [P] [US2] Angular 忘記密碼頁 + 重設密碼頁 in `apps/web/src/app/features/auth/forgot-password/`、`apps/web/src/app/features/auth/reset-password/`

**Checkpoint**：US1–US2 皆可獨立運作。

---

## Phase 5: User Story 3 - 個人設定：編輯暱稱與修改密碼 (Priority: P1)

**Goal**：已登入會員可修改顯示暱稱（套用於未來新加入的團，不回溯影響進行中且已加入的團）與修改密碼（成功後使其他裝置登入狀態失效，保留本裝置）。

**Independent Test**：用一個已驗證會員帳號，分別測試暱稱修改對「已加入進行中的團」與「尚未加入的新團」的不同影響，以及修改密碼對多裝置 session 的影響。

### Tests for User Story 3

- [X] T033 [P] [US3] Unit test：修改 `members.nickname` MUST NOT 連動更新既有 `roster_entries.nickname`（research.md #10，FR-024；需手動 seed 一筆 `roster_entries` 列驗證其值不受影響）in `apps/api/tests/unit/domains/member/test_nickname_snapshot_isolation.py`
- [X] T034 [P] [US3] Unit test：修改密碼需正確 `current_password`、新密碼兩次需一致；成功後 `token_version += 1` 但同時為本次請求核發新 token（FR-025/026，保留本裝置）in `apps/api/tests/unit/domains/member/test_change_password.py`
- [X] T035 [P] [US3] Contract test for `PATCH /members/me/nickname`、`PATCH /members/me/password` per `contracts/member-api.md` in `apps/api/tests/contract/test_member_settings.py`
- [X] T036 [US3] Integration test：修改暱稱 → 新團顯示新暱稱、既有已加入進行中團之 `roster_entries` 快照不受影響 → 修改密碼 → 本裝置沿用新 token 持續可用、其他裝置舊 token 失效 in `apps/api/tests/integration/test_member_settings_flow.py`

### Implementation for User Story 3

- [X] T037 [US3] Implement `PATCH /members/me/nickname` in `apps/api/app/domains/member/service.py` + `apps/api/app/domains/member/router.py`
- [X] T038 [US3] Implement `PATCH /members/me/password`（含 `token_version` bump + 本裝置新 token 核發）in `apps/api/app/domains/member/service.py` + `apps/api/app/domains/member/router.py`
- [X] T039 [P] [US3] Angular 個人設定頁（暱稱/密碼編輯）+ 首次登入導向邏輯（`nickname === null` 時導向設定頁，銜接 US1 T024）in `apps/web/src/app/features/member/settings/settings.component.ts`

**Checkpoint**：US1–US3 皆可獨立運作——「會員帳號核心」完成，004（加入團）之阻塞依賴解除 🎯。

---

## Phase 6: User Story 4 - 忘記管理 PIN 碼（會員限定復原機制） (Priority: P2)

**Goal**：已登入會員可在會員頁面看到自己建立過的所有團（含已解散），並針對任一團一鍵重設管理 PIN 碼、無縫進入管理頁；此功能不適用於匿名建立的團。

**Independent Test**：用一個會員帳號建立的團，觸發「忘記管理 PIN 碼」，獨立驗證重設流程、新 Token 核發、舊 PIN 碼失效；亦可用匿名建立的團驗證此功能確實不可用。

### Tests for User Story 4

- [X] T040 [P] [US4] Unit test：`GET /members/me/groups` 僅回傳 `created_by_member_id` 為本人的團（含已解散），排除匿名建立的團 in `apps/api/tests/unit/domains/member/test_my_groups.py`
- [X] T041 [P] [US4] Unit test：忘記管理 PIN 碼拒絕非建立者/匿名建立之團（`NOT_GROUP_CREATOR`），已解散團仍可重設（FR-028/029）in `apps/api/tests/unit/domains/group/test_forgot_admin_pin.py`
- [X] T042 [P] [US4] Contract test for `GET /members/me/groups` per `contracts/member-api.md`、`POST /groups/{group_id}/forgot-admin-pin` per `contracts/forgot-admin-pin-api.md` in `apps/api/tests/contract/test_forgot_admin_pin.py`
- [X] T043 [US4] Integration test：會員建團 → 忘記 PIN 碼重設 → 新 Token 直接進入管理頁、無需重新輸入 PIN 碼 → 舊 Token 失效 → 另一開著管理頁的裝置收到 `link.regenerated`（`admin`）廣播 in `apps/api/tests/integration/test_forgot_admin_pin_flow.py`

### Implementation for User Story 4

- [X] T044 [US4] Implement `GET /members/me/groups` in `apps/api/app/domains/member/service.py` + `apps/api/app/domains/member/router.py`
- [X] T045 [US4] Implement `POST /groups/{group_id}/forgot-admin-pin`（複用既有 `regenerate-admin-pin` 核心邏輯 + `require_verified_member` + 建立者比對 + 既有 `link.regenerated` 廣播，per research.md #7）in `apps/api/app/domains/group/service.py` + `apps/api/app/domains/group/router.py` (depends on T005)
- [X] T046 [P] [US4] Angular 「我的團」列表 + 忘記管理 PIN 碼按鈕 in `apps/web/src/app/features/member/my-groups/my-groups.component.ts`
- [X] T047 [P] [US4] Angular 開團成功畫面新增匿名建團提醒文字（FR-033）in `apps/web/src/app/features/group-admin/create-group/create-group.component.html`

**Checkpoint**：US1–US4 皆可獨立運作。

---

## Phase 7: User Story 5 - 搜尋與新增好友 (Priority: P2)

**Goal**：會員可透過使用者編號搜尋其他會員並發送好友邀請；搜尋結果依雙方目前的關係狀態顯示對應的按鈕或狀態標籤。

**Independent Test**：用兩個已驗證會員帳號，互相搜尋對方的使用者編號並測試各種關係狀態（尚未有關係、已發送待處理、已是好友、搜尋自己、搜尋未驗證帳號）下按鈕/標籤的正確呈現。

### Tests for User Story 5

- [X] T048 [P] [US5] Unit test：搜尋結果四狀態判斷（`none`/`pending_outgoing`/`pending_incoming`/`friends`，FR-038）in `apps/api/tests/unit/domains/friend/test_search_friendship_status.py`
- [X] T049 [P] [US5] Unit test：搜尋排除未驗證帳號（FR-036）、拒絕搜尋自己（FR-037）in `apps/api/tests/unit/domains/friend/test_search_exclusions.py`
- [X] T050 [P] [US5] Unit test：同一組使用者任何時刻最多一筆 `pending`（唯一索引衝突轉 `FRIEND_REQUEST_ALREADY_PENDING`，FR-039）in `apps/api/tests/unit/domains/friend/test_pending_uniqueness.py`
- [X] T051 [P] [US5] Contract test for `GET /members/search`、`POST /friends/requests` per `contracts/member-api.md`、`contracts/friends-api.md` in `apps/api/tests/contract/test_friend_search.py`
- [X] T052 [US5] Integration test：A 搜尋 B → 發送邀請 → A 再次搜尋顯示「待回覆」、B 搜尋 A 顯示「待處理」in `apps/api/tests/integration/test_friend_search_flow.py`

### Implementation for User Story 5

- [X] T053 [US5] Implement `GET /members/search`（含 per-IP 速率限制，FR-020）in `apps/api/app/domains/member/service.py` + `apps/api/app/domains/member/router.py`
- [X] T054 [US5] Implement `POST /friends/requests` in `apps/api/app/domains/friend/service.py` + `apps/api/app/domains/friend/router.py`
- [X] T055 [P] [US5] Angular 好友搜尋頁 in `apps/web/src/app/features/friends/friend-search/friend-search.component.ts`

**Checkpoint**：US1–US5 皆可獨立運作。

---

## Phase 8: User Story 6 - 回覆好友邀請與解除好友 (Priority: P2)

**Goal**：會員可在好友列表依暱稱或使用者編號篩選、可接受/拒絕收到的邀請、也可隨時解除既有的好友關係（單方面動作，不需對方同意）。

**Independent Test**：用兩個已建立待處理邀請或既有好友關係的會員帳號，分別測試接受、拒絕、拒絕後重新發送、解除好友、解除後重新發送、好友列表篩選等情境。

### Tests for User Story 6

- [X] T056 [P] [US6] Unit test：接受/拒絕邀請狀態轉換，僅 `addressee` 可操作（非本人邀請回傳 `FRIEND_REQUEST_NOT_FOUND`，FR-040）in `apps/api/tests/unit/domains/friend/test_respond_friend_request.py`
- [X] T057 [P] [US6] Unit test：拒絕後可重新發送（建立新列，舊「拒絕」列保留不覆寫，FR-042）in `apps/api/tests/unit/domains/friend/test_reject_then_resend.py`
- [X] T058 [P] [US6] Unit test：解除好友（`accepted → unfriended`）、解除後可無限制重新發送邀請、不對另一方發送任何通知（FR-044/045/046）in `apps/api/tests/unit/domains/friend/test_unfriend.py`
- [X] T059 [P] [US6] Unit test：好友列表依暱稱/使用者編號篩選（子字串比對，FR-034）in `apps/api/tests/unit/domains/friend/test_friend_list_filter.py`
- [X] T060 [P] [US6] Contract test for `GET /friends`、`GET /friends/requests/incoming`、`POST /friends/requests/{id}/accept`、`POST /friends/requests/{id}/reject`、`DELETE /friends/{id}` per `contracts/friends-api.md` in `apps/api/tests/contract/test_friend_lifecycle.py`
- [X] T061 [US6] Integration test：A/B 互為好友 → 雙方好友列表可見 → A 解除好友 → 雙方列表即時反映且 B 未收到通知 → B 可無限制重新發送邀請 in `apps/api/tests/integration/test_friend_lifecycle_flow.py`

### Implementation for User Story 6

- [X] T062 [US6] Implement `GET /friends`（分頁+篩選）in `apps/api/app/domains/friend/service.py` + `apps/api/app/domains/friend/router.py`
- [X] T063 [US6] Implement `GET /friends/requests/incoming`、`POST /friends/requests/{id}/accept`、`POST /friends/requests/{id}/reject` in `apps/api/app/domains/friend/service.py` + `apps/api/app/domains/friend/router.py`
- [X] T064 [US6] Implement `DELETE /friends/{friend_request_id}` in `apps/api/app/domains/friend/service.py` + `apps/api/app/domains/friend/router.py`
- [X] T065 [P] [US6] Angular 好友列表 + 回覆好友申請頁 + 解除好友二次確認 dialog in `apps/web/src/app/features/friends/friend-list/`、`apps/web/src/app/features/friends/friend-requests/`

**Checkpoint**：US1–US6 全部皆可獨立運作。

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**：跨 User Story 的收尾與驗證。

- [X] T066 [P] Integration test：完整流程「註冊 → 驗證信 → 完成驗證 → 設定暱稱 → 登入 → 修改密碼 → 其他裝置 session 失效」in `apps/api/tests/integration/test_member_lifecycle.py`（constitution 原則 II 之強制整合測試要求）
- [X] T067 [P] 依 `quickstart.md` 全部 5 個情境手動驗證 apps/api 實際運作
- [X] T068 補齊本 feature 新增之 FastAPI router 端點（`member`、`friend`、擴充的 `group`）之 `response_model`/docstring
- [X] T069 [P] Security review：確認個人設定／忘記管理 PIN 碼／好友端點皆正確要求對應驗證層級（`require_member` vs `require_verified_member`）、回應內容不洩漏其他會員之 Email／密碼雜湊／未驗證狀態等細節、`GET /members/search` 與 `GET /members/me/groups` 不跨會員洩漏他人資料

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：無任務，略過。
- **Foundational (Phase 2)**：依賴 001 已建立之 `members`/`groups` 基礎設施與既有 `app/core/turnstile.py`/`app/core/rate_limit.py`；**封鎖**所有 User Story。
- **User Stories (Phase 3–8)**：皆依賴 Foundational 完成。
- **Polish (Phase 9)**：依賴所有欲交付的 User Story 完成。

### User Story Dependencies

- **US1（P1，MVP）**：Foundational 完成後即可開始，無其他 Story 相依。
- **US2（P1）**：核心 `login`/`refresh` 已於 Foundational 完成，本 story 僅新增忘記密碼分支；獨立於 US1 之外的邏輯（皆為 `member/service.py` 新增函式，非修改）。
- **US3（P1）**：依賴 Foundational 之 `require_verified_member`；獨立於 US1/US2 之外的邏輯。
- **US4（P2）**：依賴 Foundational 之 `require_verified_member`（T005）；獨立於 US1/US2/US3 之外的邏輯，唯一跨模組觸碰為 `group` 模組新增端點（不修改既有函式簽章）。
- **US5（P2）**：依賴 Foundational 之 `require_verified_member`；獨立於其他 Story。
- **US6（P2）**：依賴 US5 之 `FriendRequest` 建立邏輯（T054）——回覆/解除操作的對象即 US5 建立的邀請記錄。
- 建議依 P1→P1→P1→P2→P2→P2 順序（US1→US2→US3→US4→US5→US6）依序實作與驗證；US1–US3 完成即可回頭恢復 004（加入團）之規劃。

### Within Each User Story

- Tests MUST 先寫且先失敗，再進行 Implementation。
- Security/Schemas（已於 Foundational 完成）→ Service（含跨模組串接）→ Router endpoints → 前端整合。
- Story 完成（含 Checkpoint 驗證）才進入下一優先序 Story。

### Parallel Opportunities

- Phase 2 內標記 `[P]` 的任務可平行執行（惟 T008 依賴 T002/T003 完成、T011/T012 依賴 T005/T006/T008 完成）。
- 同一 User Story 內標記 `[P]` 的 Tests 可平行執行。
- 若有多位開發者：Foundational 完成後，US1、US2、US3、US4、US5 皆可平行認領（彼此僅共用 Foundational 已完成的認證基礎設施，無直接程式碼相依）；US6 需等待 US5 完成後才能開始（依賴其 `FriendRequest` 建立邏輯）。

---

## Parallel Example: User Story 1

```bash
# 平行執行 US1 的所有測試任務：
Task: "Unit test：Email 唯一性 in apps/api/tests/unit/domains/member/test_registration_validation.py"
Task: "Unit test：Email 驗證 token 生命週期 in apps/api/tests/unit/domains/member/test_email_verification.py"
Task: "Unit test：重新發送驗證信速率限制 in apps/api/tests/unit/domains/member/test_resend_verification_rate_limit.py"
Task: "Contract test for POST /auth/register in apps/api/tests/contract/test_register.py"
Task: "Contract test for GET /auth/verify-email/{token} in apps/api/tests/contract/test_verify_email.py"
```

---

## Implementation Strategy

### MVP First（Foundational + User Story 1–3：「會員帳號核心」）

1. 完成 Phase 2：Foundational（關鍵，封鎖所有 Story，含登入/換發 token 之共用基礎設施）
2. 完成 Phase 3–5：User Story 1–3（註冊/驗證、忘記密碼、個人設定）
3. **停下並驗證**：獨立測試 US1–US3（`quickstart.md` 情境 1–3）
4. 此時 004（加入團）之阻塞依賴已解除，可回頭恢復其 `/speckit-plan`
5. US4–US6（忘記管理 PIN 碼、好友系統）可視時程安排於稍後階段完成，不阻擋 004

### Incremental Delivery

1. Foundational 完成 → 認證基礎就緒（含登入/換發 token）
2. 加入 US1 → 獨立測試 → Demo（可註冊、驗證信箱）
3. 加入 US2 → 獨立測試 → Demo（忘記密碼救援完整）
4. 加入 US3 → 獨立測試 → Demo（「會員帳號核心」完成，MVP！）
5. 依序加入 US4 → US5 → US6，每個 Story 皆獨立測試後再交付
6. 每個 Story 皆為既有功能疊加價值，不破壞先前 Story

### Parallel Team Strategy

多位開發者情境：

1. 團隊共同完成 Foundational（含登入/換發 token 共用基礎設施）
2. Foundational 完成後：
   - 開發者 A：US1（註冊/驗證，MVP 核心）
   - 開發者 B：US2（忘記密碼）與 US3（個人設定）可平行進行（皆僅依賴 Foundational）
   - 開發者 C：US4（忘記管理 PIN 碼）可平行進行（僅依賴 Foundational + 既有 `group` 模組）
3. US5（好友搜尋）可與 US1–US4 平行進行（僅依賴 Foundational）
4. US6（好友回覆/解除）建議於 US5 完成後再由任一開發者認領（操作對象即 US5 建立的邀請記錄）

---

## Notes

- `[P]` 任務 = 不同檔案、無相依關係。
- `[Story]` 標籤將任務對應回 spec.md 的特定 User Story，供追溯。
- `POST /auth/login`/`POST /auth/refresh` 雖屬 US2 標題範圍，因無專屬 FR/驗收情境且為 US1/US3–US6 之硬性前置依賴，已改列 Foundational（見 Phase 2 說明）。
- 每個 User Story 皆應可獨立完成與測試。
- 實作前先確認測試會失敗（TDD，呼應 constitution 原則 II）。
- 建議每完成一項任務或一組邏輯相關任務即 commit 一次。
- 可在任一 Checkpoint 停下獨立驗證該 Story，不需等待後續 Story 完成；US1–US3 之 Checkpoint 尤其重要——完成後即可回頭處理 004。
- 避免：模糊任務描述、多任務同時修改同一檔案造成衝突、破壞 Story 獨立性的跨 Story 相依。
