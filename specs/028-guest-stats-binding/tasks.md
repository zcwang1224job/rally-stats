---
description: "Task list for 028-guest-stats-binding"
---

# Tasks: 訪客即時戰況頁面建立帳號並綁定戰績

**Input**: Design documents from `/specs/028-guest-stats-binding/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/guest-binding-api.md, quickstart.md

**Tests**: Included — this repo's established convention (specs/026, specs/027) is tests alongside/before each implementation task. Constitution II's Test-First mandate applies here per plan.md's Constitution Check: binding directly affects match-history ownership and account identity, so it's held to the same coverage bar as core domain logic even though it isn't literally "開團/加入/輪替/比分".

**Organization**: Tasks are grouped by user story (US1/US2, P1/P2 per spec.md), same relationship as 027's US1→US2: US1 builds the entire binding mechanism (all four paths' shared plumbing, including OAuth's `state` extension) and US2 adds only the `mode="login"` branch on top of it.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no unmet dependency)
- **[Story]**: US1 or US2
- Paths are exact, relative to repo root

---

## Phase 1: Foundational (Blocking Prerequisites)

**Purpose**: Shared query/write primitives and shapes every story builds on. No behavior change yet — `POST /bind` doesn't exist until Phase 2.

**Note**: No separate Setup phase — this feature introduces no new dependencies, environment variables, or migrations (plan.md Technical Context).

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T001 [P] Add `BindingStatusResponse`/`BindRequest`（register/login/current-session 三種形狀的 discriminated union）/`BindResponse` schemas to `apps/api/app/domains/group/schemas.py`（contracts/guest-binding-api.md）
- [X] T002 Add `resolve_guest_binding_target(session, token)` to `apps/api/app/domains/group/service.py`——依 `guest_session_token` 查詢 `RosterEntry`，不檢查 `RosterEntry.status`／所屬 `Group.status`，查無資料才 raise `LINK_NOT_FOUND`（research.md #1；MUST NOT 修改既有 `resolve_guest_session()`）
- [X] T003 Add `bind_roster_entry_to_member(session, roster_entry_id, member_id)` to `apps/api/app/domains/group/service.py`——條件式 `UPDATE roster_entries SET member_id=:member_id WHERE id=:id AND member_id IS NULL`，受影響 0 rows 時 raise `ROSTER_ENTRY_ALREADY_BOUND`（research.md #4，depends on T002 同檔）
- [X] T004 [P] Unit tests for `resolve_guest_binding_target()`：涵蓋 `RosterEntry.status`（active/left/kicked）× `Group.status`（active/disbanded）全組合皆可查到，以及既有 `resolve_guest_session()`（active-only）完全不受影響的回歸測試——new file `apps/api/tests/unit/domains/group/test_guest_binding.py`（depends on T002）
- [X] T005 Unit tests for `bind_roster_entry_to_member()` 的並發安全（模擬兩次並發呼叫僅一次成功，第二次 raise `ROSTER_ENTRY_ALREADY_BOUND`），並斷言成功綁定後 `RosterEntry.nickname` 與綁定前完全相同（/speckit-analyze 2026-09-15 remediation, finding E1——FR-011 的不可變性此前無測試守護，僅靠 UPDATE 語句本身不觸碰該欄位）——extend `apps/api/tests/unit/domains/group/test_guest_binding.py`（depends on T003, T004 同檔）
- [X] T006 Add `GET /groups/guest-token/{token}/binding-status` to `apps/api/app/domains/group/router.py`——公開端點，呼叫 `resolve_guest_binding_target()`，回傳 `BindingStatusResponse`（depends on T001, T002）
- [X] T007 [P] Contract tests for `GET .../binding-status`：涵蓋所有 group_status × roster_status 組合與 `LINK_NOT_FOUND`——new file `apps/api/tests/contract/test_guest_binding.py`（depends on T006）
- [X] T008 [P] Add `group-guest.models.ts`（`BindingStatusResponse`/`BindRequest`/`BindResponse` TS 介面）to `apps/web/src/app/core/api/`
- [X] T009 Add `group-guest.service.ts`（`getGuestBindingStatus()`）to `apps/web/src/app/core/api/`（依賴 T008 的型別定義）

**Checkpoint**: 共用查詢與寫入邏輯就緒；`binding-status` 端到端可用；`POST /bind` 尚不存在，任何情境都還不能真的完成綁定。

---

## Phase 2: User Story 1 - 訪客在自己的即時戰況頁面建立新帳號並綁定戰績 (Priority: P1) 🎯 MVP

**Goal**: 訪客透過個人查看連結，就地建立新帳號（Email/密碼或 Google/LINE OAuth）或（若瀏覽器已是登入狀態）一鍵綁定，戰績立即歸戶；同時涵蓋進行中/已完結/已解散/已離場/已被踢出等既有狀態組合。

**Independent Test**：quickstart.md 情境 A（進行中團，Email/密碼建立新帳號）、情境 B（已解散團，OAuth 建立新帳號）、情境 D（已登入狀態一鍵綁定）三者皆可獨立驗證，不依賴 US2。

### Tests for User Story 1

- [X] T010 [P] [US1] Unit tests for `POST /bind` `mode="register"` 成功路徑（Turnstile 通過 → `register()` → 直接 `issue_access_token()`/`issue_refresh_token()` → 綁定，不重新呼叫 `login()`）——extend `apps/api/tests/unit/domains/group/test_guest_binding.py`
- [X] T011 [US1] Unit tests for `POST /bind` 已登入一鍵綁定路徑（`optional_member` 提供 `current_member` 時忽略 body 帳號欄位、不核發新 token，Clarifications 2026-09-15／FR-012）——extend 同檔（depends on T010 同檔）
- [X] T012 [US1] Unit tests for `POST /bind` `mode="register"` 邊界情境：Turnstile 失敗（`CAPTCHA_INVALID`）、Email 已註冊（`EMAIL_ALREADY_REGISTERED`，不建立帳號也不綁定）、名冊身份已被綁定過（`ROSTER_ENTRY_ALREADY_BOUND`）——extend 同檔（depends on T011 同檔）
- [X] T013 [US1] Unit tests for `POST /bind` 涵蓋 disbanded group／left／kicked roster 三種既有狀態皆可成功綁定（Acceptance Scenario 4/5）——extend 同檔（depends on T012 同檔）
- [X] T014 [P] [US1] Unit tests for `complete_oauth_callback()` 新增 `bind_guest_token` 欄位——MUST 涵蓋兩個分支皆能完成綁定並回傳 `bound_group_id`：(a) **建立新帳號**（US1 情境，該 OAuth 身份第一次登入）與 (b) **登入既有帳號**（spec.md US2 Acceptance Scenario 1 明確點名「Email/密碼或 Google/LINE」皆須支援的既有帳號登入路徑——這個分支由既有 `complete_oauth_callback()` 的既有 new-vs-returning-member 判斷邏輯原生涵蓋，不需要新程式碼，但 MUST 在測試中明確斷言，避免只驗證到 (a) 而誤以為 US2 的 OAuth 子情境未被覆蓋，/speckit-analyze 2026-09-15 remediation, finding E2）；以及「綁定失敗但 OAuth 登入本身仍成功」關鍵分支（`ROSTER_ENTRY_ALREADY_BOUND` 時 `bound_group_id` 為 `None` 但 token 仍正常核發）——extend `apps/api/tests/unit/domains/member/test_oauth_flow.py`
- [X] T015 [US1] Contract tests for `POST /groups/guest-token/{token}/bind` 的 register／current-session／OAuth 三條路徑，涵蓋 contracts/guest-binding-api.md 全部錯誤碼——extend `apps/api/tests/contract/test_guest_binding.py`（depends on T007 同檔）
- [X] T016 [P] [US1] Frontend tests for `GuestBindingCta`：未登入時顯示「建立帳號並綁定戰績」+ `mode=register` 表單（含既有 `TurnstileWidgetComponent`）；已登入時顯示「將本場戰績綁定到我的帳號」+ 一鍵送出（FR-012）；OAuth 按鈕呼叫既有 `continueWithOAuth` 模式並帶上 `bindGuestToken`——new file `apps/web/src/app/features/group-join/guest-binding-cta/guest-binding-cta.component.spec.ts`
- [X] T017 [P] [US1] Frontend tests for `GuestAccessComponent` 三分流邏輯（已綁定→導向登入頁並提示；現役未綁定→沿用既有 `resolveGuestSession()` 導向 member-view；非現役未綁定→就地渲染「個人戰績摘要」畫面）——extend `apps/web/src/app/features/group-join/guest-access/guest-access.component.spec.ts`
- [X] T018 [P] [US1] Frontend tests for `oauth-callback.component` 新增 `bound_group_id` fragment 參數：有值時導向 `/groups/<id>/member-view`；無值時維持既有預設行為（回歸測試）——extend `apps/web/src/app/features/auth/oauth-callback/oauth-callback.component.spec.ts`

### Implementation for User Story 1

- [X] T019 [US1] Implement `POST /groups/guest-token/{token}/bind` 於 `apps/api/app/domains/group/router.py`：`Depends(optional_member)`，body 為 `BindRequest`；`current_member` 存在時直接呼叫 `bind_roster_entry_to_member()`；`mode="register"` 時先 `verify_turnstile_token()` 再呼叫既有 `register()`、直接呼叫 `issue_access_token()`/`issue_refresh_token()`，再綁定，回傳新 token 對（research.md #2/#7，depends on T003, T010, T011, T012, T013）
- [X] T020 [US1] Extend `OAuthState`/`issue_oauth_state()`（`apps/api/app/domains/member/security.py`）新增 `bind_guest_token: str | None` 欄位（research.md #3，depends on T014）
- [X] T021 [US1] Extend `OAuthCallbackResult`（`apps/api/app/domains/member/service.py`）新增 `bound_group_id: str | None` 欄位；`complete_oauth_callback()` 於既有成功分支後，`oauth_state.bind_guest_token` 有值時呼叫 `group.service.bind_roster_entry_to_member()`（失敗時捕捉例外、`bound_group_id` 維持 `None`，MUST NOT 讓整個 OAuth 登入流程失敗，contracts/guest-binding-api.md）（depends on T020, T014）
- [X] T022 [US1] Extend `GET /auth/oauth/{provider}/start`（`apps/api/app/domains/member/router.py`）新增可選 query 參數 `bind_guest_token`（僅 `intent=login` 允許，`intent=link` 帶入回傳 `INVALID_REQUEST`），原樣寫入 `state`（depends on T020）
- [X] T023 [US1] Extend `_oauth_callback_redirect_url()`（`apps/api/app/domains/member/router.py`）於 `status=success` 時，`bound_group_id` 有值時於 fragment 多帶 `bound_group_id` 參數（depends on T021）
- [X] T024 [P] [US1] Create `GuestBindingCta` 元件（`.ts`/`.html`/`.scss`，`apps/web/src/app/features/group-join/guest-binding-cta/`）：依 `AuthService.loggedIn` 顯示 FR-001 兩種入口文案；封裝 `mode=register` 表單（含既有 `TurnstileWidgetComponent`）、已登入一鍵送出、OAuth 按鈕（沿用既有 `continueWithOAuth` 模式，帶上 `bindGuestToken`）（depends on T009, T016）
- [X] T025 [US1] Update `GuestAccessComponent`（`apps/web/src/app/features/group-join/guest-access/`）：初始化改為優先呼叫 `getGuestBindingStatus()`，依回應三分流導向不同畫面（已綁定/現役未綁定/非現役未綁定就地渲染摘要）（depends on T009, T017）
- [X] T026 [US1] Embed `<app-guest-binding-cta>` 於 `apps/web/src/app/features/group-member-view/group-member-view.component.html`（現役情境，FR-007 不中斷）（depends on T024）
- [X] T027 [US1] Update `oauth-callback.component.ts`：讀取 `bound_group_id` fragment 參數，導向 `/groups/<id>/member-view`，否則維持既有預設行為（depends on T018, T023）
- [X] T028 [P] [US1] Add i18n keys（綁定入口/表單/「個人戰績摘要」畫面文案，以及 `ROSTER_ENTRY_ALREADY_BOUND` 等新錯誤碼的語意化訊息）到 `apps/web/src/assets/i18n/zh-TW.json` 與 `en.json`

**Checkpoint**: User Story 1 獨立可用——quickstart.md 情境 A/B/D 皆可驗證；四條綁定路徑中除 `mode="login"` 外全數完成。

---

## Phase 3: User Story 2 - 已有會員帳號的訪客改用登入方式完成綁定 (Priority: P2)

**Goal**: 已有帳號但目前未登入的訪客，可選擇「使用現有帳號登入」而非「建立新帳號」完成綁定，避免被迫建立重複帳號；`mode="register"` 撞到既有 Email 時能順暢引導改用此路徑。

**Independent Test**：quickstart.md 情境 C——已有帳號、未登入的訪客開啟個人查看連結，選擇登入方式綁定，可獨立驗證系統沒有因此多建立一個帳號（SC-004）。

**Note**（/speckit-analyze 2026-09-15 remediation, finding E2）：spec.md 本
故事的 Acceptance Scenario 1 同時點名 Email/密碼與 Google/LINE 兩種既有
帳號登入方式。後者（既有帳號透過 OAuth 登入以完成綁定）已由 US1 的
T014/T020-T023 原生涵蓋（`complete_oauth_callback()` 既有的
new-vs-returning-member 分流邏輯不需要為此新增任何程式碼），本階段
（T029-T035）只需新增、實作 `mode="login"`（Email/密碼）這一條路徑。

### Tests for User Story 2

- [X] T029 [P] [US2] Unit tests for `POST /bind` `mode="login"`：成功綁定既有帳號、不建立新帳號（SC-004）；`INVALID_CREDENTIALS` 分支——extend `apps/api/tests/unit/domains/group/test_guest_binding.py`
- [X] T030 [US2] Unit tests 確認 `mode="register"` 時 Email 已被註冊（`EMAIL_ALREADY_REGISTERED`）不建立帳號、不綁定，回應可供前端引導改用登入（FR-009）——extend 同檔（depends on T029 同檔）
- [X] T031 [US2] Contract tests for `POST /bind` `mode="login"` 分支——extend `apps/api/tests/contract/test_guest_binding.py`
- [X] T032 [P] [US2] Frontend tests for `GuestBindingCta` 新增「使用現有帳號登入」表單切換，以及 `mode=register` 收到 `EMAIL_ALREADY_REGISTERED` 時自動引導切換到登入表單並帶入已輸入的 Email——extend `guest-binding-cta.component.spec.ts`

### Implementation for User Story 2

- [X] T033 [US2] Extend `POST /groups/guest-token/{token}/bind`（`router.py`）新增 `mode="login"` 分支：呼叫既有 `login()`，綁定，回傳既有 token 對（depends on T019, T029, T031）
- [X] T034 [US2] Extend `GuestBindingCta` 元件：新增「使用現有帳號登入」表單切換；`mode=register` 收到 `EMAIL_ALREADY_REGISTERED` 時自動引導切換（FR-009）（depends on T024, T032）
- [X] T035 [P] [US2] Add/extend i18n keys（「使用現有帳號登入」文案、`EMAIL_ALREADY_REGISTERED` 引導文字）到 `zh-TW.json`/`en.json`（depends on T028）

**Checkpoint**: User Story 2 獨立可用——quickstart.md 情境 C 可驗證；四條綁定路徑全數完成。

---

## Phase 4: Polish & Cross-Cutting Concerns

- [ ] T036 [P] 依 quickstart.md 執行全部 5 個情境（A–E）手動驗證
- [X] T037 [P] 後端：`ruff check --fix` + `mypy --strict` 於 `apps/api` 全專案通過
- [X] T038 [P] 前端：`ng lint` + `ng build --configuration development` + `ng test --watch=false` 於 `apps/web` 全部通過
- [X] T039 更新 `specs/027-google-line-oauth-login/contracts/oauth-login-api.md`，補上 `bind_guest_token`/`bound_group_id` 這個向下相容擴充（contracts/guest-binding-api.md 附錄已載明，depends on T020, T021, T022, T023）

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 1)**：無前置依賴，可立即開始——BLOCKS 所有 user story
- **User Story 1 (Phase 2)**：Depends on Foundational 完成
- **User Story 2 (Phase 3)**：Depends on Foundational 完成，且 T033/T034/T035 直接建構在 US1 的 T019/T024/T028 之上（同檔延伸，非平行）
- **Polish (Phase 4)**：Depends on 所有欲交付的 user story 完成

### User Story Dependencies

- **User Story 1 (P1)**：Foundational 完成後即可開始，不依賴 US2
- **User Story 2 (P2)**：Foundational 完成後即可開始撰寫測試（T029-T032 與 US1 無檔案衝突），但實作任務（T033-T035）修改的是 US1 已建立的同一批檔案（`router.py` 的 `bind` handler、`GuestBindingCta`、i18n 檔），因此 T033-T035 MUST 在對應的 US1 任務（T019、T024、T028）完成後才進行

### Parallel Opportunities

- Phase 1 中標 [P] 的任務（T001, T004, T007, T008）可平行
- Phase 2 中標 [P] 的任務（T010, T014, T016, T017, T018, T024, T028）可平行（T010-T013 雖標為不同 task 但同檔延伸，實際撰寫時循序累加同一份測試檔案）
- Phase 3 中標 [P] 的任務（T029, T032, T035）可平行
- US1 與 US2 的**測試撰寫**（T010-T018 vs. T029-T032）理論上可由不同人平行進行，但**實作**因同檔延伸關係 MUST 循序

---

## Parallel Example: User Story 1

```bash
# Launch US1 foundational-adjacent tests together:
Task: "Unit tests for complete_oauth_callback() bind_guest_token in apps/api/tests/unit/domains/member/test_oauth_flow.py"
Task: "Frontend tests for GuestBindingCta in apps/web/src/app/features/group-join/guest-binding-cta/guest-binding-cta.component.spec.ts"
Task: "Frontend tests for GuestAccessComponent 三分流邏輯 in guest-access.component.spec.ts"
Task: "Frontend tests for oauth-callback.component bound_group_id in oauth-callback.component.spec.ts"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Foundational
2. Complete Phase 2: User Story 1（Email/密碼 + OAuth + 已登入一鍵綁定，涵蓋進行中/已完結/已解散/已離場/已被踢出）
3. **STOP and VALIDATE**：跑 quickstart.md 情境 A/B/D
4. 此時已完整交付 spec.md 的核心價值（訪客戰績不再因訪客身份而遺失）

### Incremental Delivery

1. Foundational → binding-status 查詢可用
2. + User Story 1 → 訪客可就地建立帳號綁定（MVP）
3. + User Story 2 → 已有帳號的訪客不再被迫建立重複帳號
4. + Polish → lint/型別檢查/quickstart 全綠，補上 027 契約文件的向下相容擴充註記

---

## Notes

- [P] tasks = 不同檔案、無未完成依賴
- [Story] label 對應 spec.md 的 US1/US2，供追溯
- 本 feature 不新增 migration/依賴/環境變數（見 plan.md），因此沒有獨立的 Setup phase
- T002/T003 刻意不與既有 `resolve_guest_session()` 共用或修改同一段程式碼（research.md #1 的明確決策），實作與 code review 時 MUST 確認沒有誤觸既有函式
- 每個 task 完成後執行 commit；於各 Checkpoint 處可獨立驗證並視需要部署
