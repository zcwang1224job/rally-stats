# Tasks: 加入團（嘎團）（Join Group）

**Input**: Design documents from `/specs/004-join-group/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md（皆已存在）

**Tests**: 依 `plan.md` Constitution Check（原則 II），核心領域邏輯（人數上限原子性保證之真實併發測試、密碼驗證無鎖定機制、Guest Session Token 生命週期、FR-020a 短路邏輯、場地名稱/時間區間篩選查詢）MUST 有單元測試，且 MUST 有至少一條涵蓋「瀏覽列表→驗證密碼→輸入暱稱→加入成功→取得 Guest Session Token→還原狀態」的整合測試——本檔案的測試任務為強制項，非選用。

**Organization**：依 spec.md 之 6 個 User Story（US1–US6，依優先序 P1/P1/P1/P2/P2/P3）分階段組織，每個 Story 皆可獨立測試與交付。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行執行（不同檔案、無相依關係）
- **[Story]**: 對應 spec.md 的 US1–US6
- 每項任務皆附精確檔案路徑

## Path Conventions

沿用 `plan.md` Project Structure：`apps/api/`（FastAPI 後端）、`apps/web/`（Angular 20 前端）。monorepo 骨架已由 001 建立，本 feature 無新增 Setup 任務，亦無需 Alembic migration（data-model.md 已確認不新增資料表/欄位）。

---

## Phase 1: Setup

*本 feature 無新增 Setup 任務——monorepo、CI、linting/型別檢查工具鏈已由 001 完整建立並沿用。*

---

## Phase 2: Foundational（Blocking Prerequisites）

**Purpose**：本 feature 6 個 User Story 共用的 Pydantic schema 骨架。本 feature 不需要資料表/欄位遷移（data-model.md 已確認全部欄位由 001/002 建立），故此階段極輕量。

**⚠️ CRITICAL**：此階段完成前不可開始任何 User Story 任務。

- [X] T001 [P] Define Pydantic schemas skeleton（`GroupListItem`/`GroupListResponse`/`VerifyPasswordRequest`/`VerifyPasswordResponse`/`JoinLinkPreviewResponse`/`JoinGroupRequest`/`JoinGroupResponse`/`GuestSessionResponse`）per `data-model.md` §3 in `apps/api/app/domains/group/schemas.py`

**Checkpoint**：Foundation ready — User Story 任務可以開始。

---

## Phase 3: User Story 1 - 從開團列表瀏覽並加入公開場次 (Priority: P1) 🎯 MVP

**Goal**：使用者在開團列表瀏覽場次，點擊「加入」後（若有密碼則先驗證），依 Guest 身分輸入暱稱完成加入。本 story 建立 `join_group()` 核心寫入路徑，供 US2–US6 共用擴充。

**Independent Test**：在一個已存在、無密碼保護的團上，以未登入身分完整走過「開團列表 → 點擊加入 → 輸入暱稱 → 加入成功」流程；另對一個有密碼保護的團測試密碼驗證步驟（含錯誤重試），皆可獨立驗證。

### Tests for User Story 1

- [X] T002 [P] [US1] Unit test：密碼比對正確/錯誤（`verify_password()`）in `apps/api/tests/unit/domains/group/test_verify_password.py`
- [X] T003 [P] [US1] Unit test：Guest 加入之暱稱格式驗證——空白（去除頭尾空白後為空字串）或超過 20 字皆拒絕（FR-004）in `apps/api/tests/unit/domains/group/test_join_validation.py`
- [X] T004 [P] [US1] Unit test：重複暱稱（與既有 active 成員相同）允許加入成功、不阻擋（FR-020，底層暱稱資料不受影響，顯示層區分序號屬前端/後續顯示規則不在本測試範圍）in `apps/api/tests/unit/domains/group/test_join_validation.py`
- [X] T005 [P] [US1] Contract test for `GET /groups`（基本列表，無篩選/無個人化）per `contracts/group-list-api.md` in `apps/api/tests/contract/test_group_list.py`
- [X] T006 [P] [US1] Contract test for `POST /groups/{group_id}/verify-password` per `contracts/join-api.md`（含連續 10+ 次錯誤仍可重試，FR-016）in `apps/api/tests/contract/test_verify_password.py`
- [X] T007 [P] [US1] Contract test for `POST /groups/{group_id}/join`（Guest 路徑）per `contracts/join-api.md` in `apps/api/tests/contract/test_join_group.py`
- [X] T008 [US1] Integration test：瀏覽列表 → 密碼驗證（含一次錯誤重試）→ 輸入暱稱 → 加入成功 → `current_member_count` 正確 +1、`RosterEntry` 正確建立 in `apps/api/tests/integration/test_join_flow.py`

### Implementation for User Story 1

- [X] T009 [US1] Implement `list_groups()`（基本查詢：`status='active'`、分頁，無篩選/無個人化）in `apps/api/app/domains/group/service.py`
- [X] T010 [US1] Implement `verify_password()`（重用既有 `decrypt_group_password`）in `apps/api/app/domains/group/service.py`
- [X] T011 [US1] Implement `join_group()`（Guest 路徑：暱稱格式驗證、密碼比對、原子性人數保證 `UPDATE ... WHERE current_member_count < max_members`、建立 `RosterEntry`、產生 Guest Session Token、呼叫 003 之 `handle_member_joined`）in `apps/api/app/domains/group/service.py` (depends on T010)
- [X] T012 [US1] Implement `GET /groups` router endpoint in `apps/api/app/domains/group/router.py` (depends on T009)
- [X] T013 [US1] Implement `POST /groups/{group_id}/verify-password` router endpoint in `apps/api/app/domains/group/router.py` (depends on T010)
- [X] T014 [US1] Implement `POST /groups/{group_id}/join` router endpoint in `apps/api/app/domains/group/router.py` (depends on T011)
- [X] T015 [P] [US1] Angular 開團列表元件（取代既有 placeholder）in `apps/web/src/app/features/group-join/group-list/group-list.component.ts`
- [X] T016 [P] [US1] Angular 加入流程元件（密碼頁 → 暱稱頁 → 完成畫面，單一多步驟元件）in `apps/web/src/app/features/group-join/join-flow/join-flow.component.ts`
- [X] T017 [P] [US1] Angular `group-join.service.ts`（list/verifyPassword/join API 呼叫 + Guest Session Token 儲存骨架）in `apps/web/src/app/features/group-join/group-join.service.ts`

**Checkpoint**：US1 完整可運作——可獨立展示「瀏覽列表 → 加入成功」。

---

## Phase 4: User Story 2 - 透過加入連結／QR Code 直接加入 (Priority: P1)

**Goal**：使用者掃描 QR Code 或點擊加入連結，直接進入加入流程（略過列表搜尋），若團已解散/已滿/連結已失效則看到明確錯誤畫面。

**Independent Test**：用一個團的加入連結分別測試「團正常可加入」「團已解散」「團已滿」三種情境，獨立驗證導向流程與錯誤畫面，無需依賴開團列表的搜尋/篩選功能。

### Tests for User Story 2

- [X] T018 [P] [US2] Unit test：`resolve_join_link()` 查無對應 token 拋出 `LINK_NOT_FOUND` in `apps/api/tests/unit/domains/group/test_resolve_join_link.py`
- [X] T019 [P] [US2] Contract test for `GET /join/{join_link_token}` per `contracts/join-api.md`（含已解散團、已滿團之欄位值——皆為 200 回應，非錯誤代碼）in `apps/api/tests/contract/test_join_link.py`
- [X] T020 [US2] Integration test：透過連結進入 → 略過列表搜尋 → 密碼驗證 → 加入成功；另測已解散團與已滿團之連結進入行為 in `apps/api/tests/integration/test_join_link_flow.py`

### Implementation for User Story 2

- [X] T021 [US2] Implement `resolve_join_link()`（依 `join_link_token` 查詢團，回傳含 `court_names` 之預覽資訊）in `apps/api/app/domains/group/service.py`
- [X] T022 [US2] Implement `GET /join/{join_link_token}` router endpoint in `apps/api/app/domains/group/router.py` (depends on T021)
- [X] T023 [P] [US2] Angular 加入連結進入頁（解析 token → 導向 US1 之 join-flow 元件；已解散/已滿/連結無效之明確錯誤畫面）in `apps/web/src/app/features/group-join/group-join.component.ts`

**Checkpoint**：US1–US2 皆可獨立運作。

---

## Phase 5: User Story 3 - 人數上限的兩層檢查與併發控制 (Priority: P1)

**Goal**：驗證 US1 已建立的 `join_group()` 之原子性人數保證在真實併發情境下正確運作，並補上前置檢查的前端提早攔截。

**Independent Test**：對一個僅剩 1 個名額的團，模擬兩個幾乎同時送出的最終加入請求，獨立驗證僅一方成功、`current_member_count` 正確不超過上限；亦可獨立測試已滿的團在前置檢查階段就被擋下。

### Tests for User Story 3

- [X] T024 [P] [US3] Unit test：已滿團呼叫 `join_group()` 拋出 `GROUP_FULL`（單一請求情境，非併發）in `apps/api/tests/unit/domains/group/test_join_capacity.py`
- [X] T025 [US3] Unit test：真實併發測試——兩條獨立資料庫連線對僅剩 1 名額的團同時呼叫 `join_group()`，僅一方成功、`current_member_count` 正確等於 `max_members`（比照 003 `test_next_round_locking.py` 之雙連線模式）in `apps/api/tests/unit/domains/group/test_join_capacity_concurrency.py`
- [X] T026 [P] [US3] Contract test for `POST /groups/{group_id}/join` 之 `GROUP_FULL` 情境（含前置檢查通過但送出前被搶先佔用之情境）per `contracts/join-api.md` in `apps/api/tests/contract/test_join_group.py`

### Implementation for User Story 3

*本 story 之原子性保證機制已於 US1 之 `join_group()`（T011）內建（research.md #5），此處無新增後端邏輯，僅新增測試驗證與前端前置提示。*

- [X] T027 [P] [US3] Angular 前端人數已滿前置提示（點擊「加入」前先比對已取得的 `current_member_count`/`max_members`，已滿則提早提示「此團人數已滿」、不進入密碼/暱稱頁，FR-011）in `apps/web/src/app/features/group-join/group-list/group-list.component.ts`

**Checkpoint**：US1–US3 皆可獨立運作，人數上限之原子性保證已通過真實併發測試驗證。

---

## Phase 6: User Story 4 - Guest 身分延續性 (Priority: P2)

**Goal**：Guest 使用者重新整理頁面或斷線重連時，系統正確識別同一人並還原狀態；團解散或 Guest 退出/被踢除時，Token 立即失效。

**Independent Test**：讓一個 Guest 使用者加入某團後模擬重新整理頁面，獨立驗證狀態被正確還原；亦可分別對「團已解散」與「該 Guest 已退出/被踢除」兩種情境測試 Token 失效行為。

### Tests for User Story 4

- [X] T028 [P] [US4] Unit test：`resolve_guest_session()` 有效 token 回傳正確 `roster_entry`；查無 token 回傳 `LINK_NOT_FOUND` in `apps/api/tests/unit/domains/group/test_guest_session.py`
- [X] T029 [P] [US4] Contract test for `GET /groups/by-guest-token/{token}` per `contracts/join-api.md` in `apps/api/tests/contract/test_guest_session.py`
- [X] T030 [US4] Integration test：Guest 加入 → 模擬重新整理（重新呼叫 `by-guest-token`）→ 正確還原；團解散後同一 token 失效；Guest 被踢除（直接呼叫 003 之 `kick_member`）後同一 token 失效 in `apps/api/tests/integration/test_guest_session_flow.py`

### Implementation for User Story 4

- [X] T031 [US4] Implement `resolve_guest_session()`（JOIN `groups` 確認團仍為 active 且 `RosterEntry` 仍為 active）in `apps/api/app/domains/group/service.py`
- [X] T032 [US4] Implement `GET /groups/by-guest-token/{token}` router endpoint in `apps/api/app/domains/group/router.py` (depends on T031)
- [X] T033 [P] [US4] Angular Guest Session Token 本地儲存與還原邏輯（加入成功後存入 localStorage，頁面載入時檢查並呼叫 `by-guest-token` 還原；無效時導向全新加入流程）in `apps/web/src/app/features/group-join/group-join.service.ts`

**Checkpoint**：US1–US4 皆可獨立運作。

---

## Phase 7: User Story 5 - 開團列表篩選與可訪問性顯示 (Priority: P2)

**Goal**：使用者可依場地名稱、場地 ID、活動時間區間搜尋/篩選開團列表；密碼狀態顯示同時滿足圖示形狀與文字標籤兩種區分方式。

**Independent Test**：在一個有多筆場次資料的開團列表上，分別測試場地名稱搜尋、時間區間篩選、以及色盲/灰階模式下的密碼狀態辨識。

### Tests for User Story 5

- [X] T034 [P] [US5] Unit test：場地名稱/場地 ID 篩選查詢邏輯——一團多場地時任一場地命中即算命中（research.md #7）in `apps/api/tests/unit/domains/group/test_group_list_filters.py`
- [X] T035 [P] [US5] Unit test：活動時間區間篩選（區間重疊判斷；未套用篩選時不受影響地正常顯示；套用篩選時未設定活動時間之團自動排除）in `apps/api/tests/unit/domains/group/test_group_list_filters.py`
- [X] T036 [P] [US5] Contract test for `GET /groups` 篩選 query 參數 per `contracts/group-list-api.md` in `apps/api/tests/contract/test_group_list.py`

### Implementation for User Story 5

- [X] T037 [US5] 擴充 `list_groups()` 加入 `court_name`/`court_id`/`time_start`/`time_end` 篩選查詢 in `apps/api/app/domains/group/service.py` (depends on T009)
- [X] T038 [US5] 擴充 `GET /groups` router endpoint 加入對應 query 參數 in `apps/api/app/domains/group/router.py` (depends on T037)
- [X] T039 [P] [US5] Angular 開團列表搜尋/篩選 UI（場地名稱/ID 輸入、時間區間選擇）in `apps/web/src/app/features/group-join/group-list/group-list.component.ts`
- [X] T040 [P] [US5] Angular 密碼狀態鎖頭圖示（開/闔形狀 + 文字標籤雙重區分，MUST NOT 僅靠顏色，FR-005）in `apps/web/src/app/features/group-join/group-list/group-list.component.html`

**Checkpoint**：US1–US5 皆可獨立運作。

---

## Phase 8: User Story 6 - 已登入會員的加入差異化與個人化列表 (Priority: P3)

**Goal**：已登入會員加入時不需輸入暱稱（直接使用會員暱稱）；已在此團有 active 記錄之會員直接導向現有狀態；開團列表呈現「已加入的團」個人化資訊。

**Independent Test**：分別用「已設定暱稱的會員」與「尚未設定暱稱的會員」兩種帳號測試加入流程的差異，並檢視開團列表是否正確呈現個人化資訊。

### Tests for User Story 6

- [X] T041 [P] [US6] Unit test：已登入且已設定暱稱之會員加入——直接使用會員暱稱，不需 `nickname` 輸入（FR-018）in `apps/api/tests/unit/domains/group/test_join_as_member.py`
- [X] T042 [P] [US6] Unit test：已登入但尚未設定暱稱之會員加入——拒絕並回傳 `NICKNAME_REQUIRED_FOR_MEMBER`（FR-019）in `apps/api/tests/unit/domains/group/test_join_as_member.py`
- [X] T043 [P] [US6] Unit test：FR-020a 短路——已登入會員在此團已有 active `RosterEntry` 時直接回傳既有記錄（`created_new: false`）、MUST NOT 重新驗證密碼或人數上限 in `apps/api/tests/unit/domains/group/test_join_as_member.py`
- [X] T044 [P] [US6] Unit test：`GET /groups` 之 `joined_by_me` 欄位——未帶 Bearer token 為 `null`、已登入未加入為 `false`、已登入已加入為 `true` in `apps/api/tests/unit/domains/group/test_group_list_personalization.py`
- [X] T045 [P] [US6] Contract test for `POST /groups/{group_id}/join`（已登入會員路徑）per `contracts/join-api.md` in `apps/api/tests/contract/test_join_group.py`
- [X] T046 [US6] Integration test：已登入會員透過加入連結再次進入已加入的團 → 直接導向現有狀態、不重新驗證密碼或人數上限 in `apps/api/tests/integration/test_member_join_flow.py`

### Implementation for User Story 6

- [X] T047 [US6] Implement `optional_member` FastAPI dependency（有 `Authorization` header 則解碼驗證，格式錯誤/已失效/缺少皆回傳 `None`，不拋出例外，research.md #2）in `apps/api/app/domains/member/security.py`
- [X] T048 [US6] 擴充 `join_group()` 加入已登入會員路徑（暱稱來源分流、FR-020a 短路檢查置於最前）in `apps/api/app/domains/group/service.py` (depends on T011, T047)
- [X] T049 [US6] 擴充 `list_groups()`／`resolve_join_link()` 加入 `joined_by_me`／`already_joined` 個人化欄位 in `apps/api/app/domains/group/service.py` (depends on T009, T021, T047)
- [X] T050 [US6] 擴充 `GET /groups`、`GET /join/{token}`、`POST /{group_id}/join` router endpoints 支援可選 `Authorization` header in `apps/api/app/domains/group/router.py` (depends on T047, T048, T049)
- [X] T051 [P] [US6] Angular 已登入會員加入流程（略過暱稱頁；未設定暱稱者導向 006 之個人設定頁完成後自動接續加入）in `apps/web/src/app/features/group-join/join-flow/join-flow.component.ts`
- [X] T052 [P] [US6] Angular 開團列表「已加入的團」個人化標示 in `apps/web/src/app/features/group-join/group-list/group-list.component.html`

**Checkpoint**：US1–US6 全部皆可獨立運作。

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**：跨 User Story 的收尾與驗證。

- [X] T053 [P] Integration test：完整流程「瀏覽列表 → 驗證密碼 → 輸入暱稱 → 加入成功 → 取得 Guest Session Token → 重新整理還原」in `apps/api/tests/integration/test_join_lifecycle.py`（constitution 原則 II 之強制整合測試要求）
- [X] T054 [P] 依 `quickstart.md` 全部 5 個情境手動驗證 apps/api 實際運作（含情境 4 之真實併發 curl 測試）
- [X] T055 補齊本 feature 新增之 FastAPI router 端點（`group` 模組擴充部分）之 `response_model`/docstring
- [X] T056 [P] Security review：確認 Guest Session Token 不具會員權限、不可跨團使用；密碼驗證回應（`verify-password`、`join` 之 `GROUP_PASSWORD_INCORRECT`）不洩漏密碼明文；`GET /groups`／`GET /join/{token}` 之公開回應不洩漏其他會員之 Email 或內部識別資訊

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：無任務，略過。
- **Foundational (Phase 2)**：僅 schema 骨架，無外部依賴；**封鎖**所有 User Story。
- **User Stories (Phase 3–8)**：皆依賴 Foundational 完成。
- **Polish (Phase 9)**：依賴所有欲交付的 User Story 完成。

### User Story Dependencies

- **US1（P1，MVP）**：Foundational 完成後即可開始，無其他 Story 相依；建立 `join_group()`（T011）核心寫入路徑供其餘 Story 共用擴充。
- **US2（P1）**：依賴 US1 之 `join_group()`/`verify_password()`（T010/T011）——本 story 僅新增「連結解析」這個新入口，加入本身的邏輯完全重用，不重新實作（FR-010）。
- **US3（P1）**：依賴 US1 之 `join_group()`（T011）——其原子性保證機制已內建，本 story 為其新增真實併發測試驗證，非重新實作。
- **US4（P2）**：依賴 US1 之 `join_group()`（T011，Guest Session Token 於此產生）；獨立於 US2/US3 之外的新增邏輯。
- **US5（P2）**：依賴 US1 之 `list_groups()`（T009）——本 story 為其擴充篩選參數，非重新實作。
- **US6（P3）**：依賴 US1 之 `join_group()`（T011）、`list_groups()`（T009）與 US2 之 `resolve_join_link()`（T021）——皆為新增分支/欄位，非修改既有行為；亦依賴 006 已完成之會員 JWT 認證基礎設施（`require_member` 模式）。
- 建議依 P1→P1→P1→P2→P2→P3 順序（US1→US2→US3→US4→US5→US6）依序實作與驗證。

### Within Each User Story

- Tests MUST 先寫且先失敗，再進行 Implementation。
- Service（含跨模組串接）→ Router endpoints → 前端整合。
- Story 完成（含 Checkpoint 驗證）才進入下一優先序 Story。

### Parallel Opportunities

- Phase 2 僅一項任務，無平行機會。
- 同一 User Story 內標記 `[P]` 的 Tests 可平行執行。
- 若有多位開發者：US1 完成後，US2、US3、US4、US5 可平行認領（皆僅依賴 US1 的核心 `join_group()`/`list_groups()`，彼此無直接程式碼相依）；US6 建議最後認領（依賴前述多個 story 的既有函式，且額外依賴 006 之會員認證基礎設施）。

---

## Parallel Example: User Story 1

```bash
# 平行執行 US1 的所有測試任務：
Task: "Unit test：密碼比對 in apps/api/tests/unit/domains/group/test_verify_password.py"
Task: "Unit test：Guest 暱稱格式驗證 in apps/api/tests/unit/domains/group/test_join_validation.py"
Task: "Unit test：重複暱稱允許加入 in apps/api/tests/unit/domains/group/test_join_validation.py"
Task: "Contract test for GET /groups in apps/api/tests/contract/test_group_list.py"
Task: "Contract test for POST /groups/{group_id}/verify-password in apps/api/tests/contract/test_verify_password.py"
Task: "Contract test for POST /groups/{group_id}/join in apps/api/tests/contract/test_join_group.py"
```

---

## Implementation Strategy

### MVP First（僅 User Story 1）

1. 完成 Phase 2：Foundational（schema 骨架）
2. 完成 Phase 3：User Story 1
3. **停下並驗證**：獨立測試 US1（`quickstart.md` 情境 1、3）
4. 若已可展示，即可部署/demo

### Incremental Delivery

1. Foundational 完成 → schema 就緒
2. 加入 US1 → 獨立測試 → Demo（MVP：列表瀏覽 + Guest 加入完整閉環！）
3. 加入 US2 → 獨立測試 → Demo（QR Code/連結入口完整）
4. 加入 US3 → 獨立測試 → Demo（併發正確性通過真實測試驗證）
5. 依序加入 US4 → US5 → US6，每個 Story 皆獨立測試後再交付
6. 每個 Story 皆為既有功能疊加價值，不破壞先前 Story

### Parallel Team Strategy

多位開發者情境：

1. 團隊共同完成 Foundational（極輕量，單一任務）
2. Foundational 完成後：
   - 開發者 A：US1（列表瀏覽 + Guest 加入，MVP 核心）
   - 開發者 B：待 US1 的 `join_group()`/`verify_password()` 就緒後，平行進行 US2（連結入口）與 US4（Guest 延續性）
   - 開發者 C：待 US1 的 `list_groups()` 就緒後，平行進行 US5（篩選/可訪問性）；US3（併發測試）可與其他 Story 平行進行，僅需 US1 完成
3. US6（會員差異化）建議最後認領，同時依賴 US1/US2 之既有函式與 006 之會員認證基礎設施

---

## Notes

- `[P]` 任務 = 不同檔案、無相依關係。
- `[Story]` 標籤將任務對應回 spec.md 的特定 User Story，供追溯。
- 每個 User Story 皆應可獨立完成與測試；US3 之實作階段刻意留白（核心邏輯已於 US1 內建），僅新增測試與前端提示，避免誤判為需要重新設計原子性機制。
- 實作前先確認測試會失敗（TDD，呼應 constitution 原則 II）。
- 建議每完成一項任務或一組邏輯相關任務即 commit 一次。
- 可在任一 Checkpoint 停下獨立驗證該 Story，不需等待後續 Story 完成。
- 避免：模糊任務描述、多任務同時修改同一檔案造成衝突、破壞 Story 獨立性的跨 Story 相依。
