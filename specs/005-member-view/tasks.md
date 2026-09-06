# Tasks: 團內成員視圖（Member View）

**Input**: Design documents from `/specs/005-member-view/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md（皆已存在）

**Tests**: 依 `plan.md` Constitution Check（原則 II），四狀態判定公式（含全部四種狀態與其各自成因）、`round_history` 寫入時機、`left_at` 一旦成立即不可逆之單向鎖定特性、`resolve_active_roster_membership()` 之 Guest/Member 雙軌身分驗證與 disbanded 團仍可讀取、跨團查詢天然排除 Guest 紀錄，皆 MUST 有單元測試；至少一條整合測試涵蓋「多輪比賽（含候補/捨棄/中途退出/中途加入）→ 戰績頁四狀態皆正確」全流程——本檔案的測試任務為強制項，非選用。

**Organization**：依 spec.md 之 5 個 User Story（US1–US5，優先序 P1/P1/P1/P2/P3）分階段組織，每個 Story 皆可獨立測試與交付。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行執行（不同檔案、無相依關係）
- **[Story]**: 對應 spec.md 的 US1–US5
- 每項任務皆附精確檔案路徑

## Path Conventions

沿用 `plan.md` Project Structure：`apps/api/`（FastAPI 後端，擴充既有 `app/domains/group`、`app/domains/schedule`、`app/domains/roster`；US5 之 `GET /members/me/match-records` 例外置於既有 `app/domains/member/`，見 plan.md Structure Decision）、`apps/web/`（Angular 20 前端，新增 `features/group-member-view/`、擴充 `features/member/`）。monorepo 骨架已由 001 建立，本 feature 無新增 Setup 任務。

---

## Phase 1: Setup

*本 feature 無新增 Setup 任務——monorepo、CI、linting/型別檢查工具鏈已由 001 完整建立並沿用。*

---

## Phase 2: Foundational（Blocking Prerequisites）

**Purpose**：本 feature 唯一的 schema 變更（`round_history` 表 + `roster_entries.left_at` 欄位）、對應的 Pydantic 回應骨架，以及貫穿 US1–US4 全部讀取端點的共用身分驗證函式 `resolve_active_roster_membership()`。這三者皆為多個 User Story 共同依賴的基礎設施。

**⚠️ CRITICAL**：此階段完成前不可開始任何 User Story 任務。

- [X] T001 Alembic migration：新增 `round_history` 表（`group_id`/`round_number` 複合主鍵、`started_at`）+ `roster_entries` 新增 `left_at TIMESTAMPTZ NULL` 欄位 per data-model.md in `apps/api/alembic/versions/`
- [X] T002 [P] 擴充 `RosterEntry` model 新增 `left_at` 欄位 in `apps/api/app/domains/roster/models.py` (depends on T001)
- [X] T003 [P] 新增 `RoundHistory` model in `apps/api/app/domains/group/models.py` (depends on T001)
- [X] T004 [P] 定義 Pydantic schemas 骨架（`RoundStatus`/`MemberStandingRow`/`GroupStandingsResponse`/`MatchRecordSummary`/`GroupMatchRecordsResponse`/`MemberMatchRecordSummary`/`MemberMatchRecordsResponse`/`LeaveGroupRequest`/`LeaveGroupResponse`）per data-model.md in `apps/api/app/domains/group/schemas.py`（`member/service.py`、`member/router.py` 匯入 `MemberMatchRecordSummary`/`MemberMatchRecordsResponse` 重用，見 US5）
- [X] T005 [P] Unit test：`generate_next_round()` 於遞增 `current_round_number` 之同一交易內寫入對應 `round_history` 列，第 1 輪不寫入紀錄（research.md #1、#2）in `apps/api/tests/unit/domains/schedule/test_round_history.py`
- [X] T006 擴充 `generate_next_round()` 寫入 `round_history` 列 per research.md #1、#2 in `apps/api/app/domains/schedule/service.py` (depends on T003, T005)
- [X] T007 [P] Unit test：`handle_member_left()` 於轉為 `left`/`kicked` 當下寫入 `left_at`，`status == 'active'` 時 `left_at` 恆為 `NULL`（research.md #3）in `apps/api/tests/unit/domains/schedule/test_handle_member_left_left_at.py`
- [X] T008 擴充 `handle_member_left()` 寫入 `entry.left_at = datetime.now(UTC)` per research.md #3 in `apps/api/app/domains/schedule/service.py` (depends on T002, T007)
- [X] T009 [P] Unit test：`resolve_active_roster_membership()`——Guest token 對應 `active` RosterEntry 通過、非 `active` 或查無對應 → `MEMBERSHIP_REQUIRED`(403)；Member 於此團有 `active` RosterEntry 通過、無則 403；guest token 與 member 皆缺 → 403；disbanded 團（`Group.status != 'active'`）仍通過（research.md #5）in `apps/api/tests/unit/domains/group/test_active_roster_membership.py`
- [X] T010 Implement `resolve_active_roster_membership(session, group_id, guest_session_token, member_id)` per research.md #5 in `apps/api/app/domains/group/service.py` (depends on T009)

**Checkpoint**：Foundation ready — User Story 任務可以開始。

---

## Phase 3: User Story 1 - 一般成員導覽與唯讀賽程檢視 (Priority: P1) 🎯 MVP

**Goal**：一般成員（非管理員）進入已加入的團，看到「賽程/戰績/退出組團/對戰紀錄」導覽而非管理員功能；賽程頁唯讀即時同步比分與排點狀態。

**Independent Test**：可用一個一般成員帳號（或 Guest 身分）進入已加入的團，獨立驗證導覽項目、賽程頁的即時同步與唯讀性，無需依賴戰績、對戰紀錄或退出組團等其他功能。

### Tests for User Story 1

- [X] T011 [P] [US1] Contract test for `GET /groups/{group_id}/member-schedule` per `contracts/member-view-api.md`（Guest token 成功回傳 `ScheduleResponse`、無 token 回傳 `403 MEMBERSHIP_REQUIRED`）in `apps/api/tests/contract/test_member_schedule.py`
- [X] T012 [P] [US1] Angular test：一般成員導覽元件模板斷言——僅顯示「賽程/戰績/退出組團/對戰紀錄」，不存在「場地設定」「賽程設定」「輪替名單管理」「解散」等管理員專屬項目（SC-001）in `apps/web/src/app/features/group-member-view/group-member-view.component.spec.ts`

### Implementation for User Story 1

- [X] T013 [US1] Implement `GET /groups/{group_id}/member-schedule` router endpoint——透過 `resolve_active_roster_membership()` 驗證後直接呼叫既有 `build_schedule_snapshot()`（research.md #6，完整重用 `ScheduleResponse`）in `apps/api/app/domains/group/router.py` (depends on T010)
- [X] T014 [P] [US1] Angular：`group-member-view.component.ts` 外殼元件——一般成員導覽（賽程/戰績/退出組團/對戰紀錄），Guest token/Member 身分路由解析 in `apps/web/src/app/features/group-member-view/group-member-view.component.ts`
- [X] T015 [P] [US1] Angular：`member-schedule.component.ts`——呼叫 `GET .../member-schedule`，訂閱既有 Ably 頻道（`match.scoreUpdated`/`match.ended`/`rotation.updated`/`match.nextRound`/`member.joined`/`member.left`），純唯讀呈現（無加減分/排程控制元件，FR-004）in `apps/web/src/app/features/group-member-view/member-schedule/member-schedule.component.ts`
- [X] T016 [P] [US1] `member-schedule.component.html`：目前 Round 編號、各場地進行中比賽、排隊中預告版面 in `apps/web/src/app/features/group-member-view/member-schedule/member-schedule.component.html`

**Checkpoint**：US1 完整可運作——一般成員可獨立進入團、看到專屬導覽與唯讀賽程頁。

---

## Phase 4: User Story 2 - 團內戰績：逐輪勝負狀態 (Priority: P1)

**Goal**：一般成員查看「戰績」頁，能看到團內每位曾經參與過的成員在每一輪的勝負狀態（勝/敗/未上場/已離開），範圍僅限本團。

**Independent Test**：可在一個已完成多輪比賽、且有成員候補未上場、有成員中途退出的團上，獨立驗證戰績頁對四種狀態的正確標示，無需依賴對戰紀錄或退出組團功能。

### Tests for User Story 2

- [X] T017 [P] [US2] Unit test：四狀態公式——「勝」/「敗」判定（`Match.status == 'completed'`，依 `MatchParticipant.team` 是否等於 `winner_team`）in `apps/api/tests/unit/domains/group/test_standings_formula.py`
- [X] T018 [P] [US2] Unit test：四狀態公式——「未上場」候補中情境（該輪無 `MatchParticipant` 紀錄，FR-007a）in `apps/api/tests/unit/domains/group/test_standings_formula.py`
- [X] T019 [P] [US2] Unit test：四狀態公式——「未上場」已捨棄比賽情境（`Match.status == 'abandoned'`，永久不再更新為勝/敗，FR-007c、FR-010）in `apps/api/tests/unit/domains/group/test_standings_formula.py`
- [X] T020 [P] [US2] Unit test：四狀態公式——「未上場」比賽仍為 `queued`/`in_progress` 之暫時性標示（目前輪次尚未完賽），待比賽完成後更新為「勝」或「敗」，不誤判為捨棄或候補中（FR-010）in `apps/api/tests/unit/domains/group/test_standings_formula.py`
- [X] T021 [P] [US2] Unit test：四狀態公式——「未上場」加入之前所有更早輪次情境（`joined_at > round_history.started_at`，FR-007b，不新增第五種狀態）in `apps/api/tests/unit/domains/group/test_standings_formula.py`
- [X] T022 [P] [US2] Unit test：四狀態公式——「已離開」狀態於退出/被踢輪次之後所有輪次恆定顯示，不會變回「未上場」（FR-008、SC-004 之不可逆特性）in `apps/api/tests/unit/domains/group/test_standings_formula.py`
- [X] T023 [P] [US2] Unit test：四狀態公式——手動安排排程機制下「已離開」判定同樣採「該輪開始時間點」基準，與演算法排程機制一致（spec Scenario US2-6）in `apps/api/tests/unit/domains/group/test_standings_formula.py`
- [X] T024 [P] [US2] Unit test：`build_group_standings()` 範圍隔離——另一團已完成之比賽/成員 MUST NOT 出現於本團戰績回應中（FR-009）in `apps/api/tests/unit/domains/group/test_standings_formula.py`
- [X] T025 [P] [US2] Contract test for `GET /groups/{group_id}/standings` per `contracts/member-view-api.md`（`rounds` 範圍 `2..current_round_number`、無 token 回傳 `403 MEMBERSHIP_REQUIRED`）in `apps/api/tests/contract/test_group_standings.py`
- [X] T026 [US2] Integration test：多輪比賽（含候補、捨棄、中途退出、中途加入四種成因皆涵蓋）→ 戰績頁四狀態皆正確 全流程 in `apps/api/tests/integration/test_standings_flow.py`

### Implementation for User Story 2

- [X] T027 [US2] Implement `build_group_standings(session, group)`——四狀態判定公式 per research.md #4，`rounds` 範圍 `2..current_round_number`（research.md #2），範圍僅限本團（FR-009）in `apps/api/app/domains/group/service.py` (depends on T017-T024, T006, T008)
- [X] T028 [US2] Implement `GET /groups/{group_id}/standings` router endpoint in `apps/api/app/domains/group/router.py` (depends on T027, T010)
- [X] T029 [P] [US2] Angular：`standings.component.ts`——戰績表格（成員 × 輪次），四狀態視覺標示 in `apps/web/src/app/features/group-member-view/standings/standings.component.ts`
- [X] T030 [P] [US2] `standings.component.html`：表格版面，「已離開」狀態 MUST 同時有文字標籤與非純色彩之視覺區分（圖示或底線，憲章原則 VII）in `apps/web/src/app/features/group-member-view/standings/standings.component.html`

**Checkpoint**：US1–US2 皆可獨立運作。

---

## Phase 5: User Story 3 - 團內對戰紀錄：逐場列表 (Priority: P1)

**Goal**：一般成員查看「對戰紀錄」，以列表方式看到本團每一場已完成比賽的 Round 編號、對戰雙方、比分與勝負結果，僅限本團範圍。

**Independent Test**：可在一個已完成若干場比賽的團上，獨立驗證對戰紀錄列表的欄位完整性與範圍限制（僅本團），無需依賴戰績頁或其他功能。

### Tests for User Story 3

- [X] T031 [P] [US3] Unit test：`build_group_match_records()`——僅包含 `status == 'completed'` 之比賽（`abandoned`/`queued`/`in_progress` 皆排除），依 `round_number` 由新到舊排序 in `apps/api/tests/unit/domains/group/test_group_match_records.py`
- [X] T032 [P] [US3] Unit test：`build_group_match_records()` 範圍隔離——另一團已完成之比賽 MUST NOT 出現於本團對戰紀錄回應中（FR-012）in `apps/api/tests/unit/domains/group/test_group_match_records.py`
- [X] T033 [P] [US3] Contract test for `GET /groups/{group_id}/match-records` per `contracts/member-view-api.md`（分頁參數、無 token 回傳 `403 MEMBERSHIP_REQUIRED`）in `apps/api/tests/contract/test_group_match_records.py`

### Implementation for User Story 3

- [X] T034 [US3] Implement `_completed_matches_query()` 共用查詢建構子（`WHERE status = 'completed'`，JOIN `match_participants`，research.md #8；供本 Story 與 US5 `member.service.build_member_match_records()` 跨模組匯入重用）in `apps/api/app/domains/group/service.py`
- [X] T035 [US3] Implement `build_group_match_records(session, group_id, page)`——套用 `_completed_matches_query()` + `Match.group_id == group_id` 過濾 in `apps/api/app/domains/group/service.py` (depends on T034, T031, T032)
- [X] T036 [US3] Implement `GET /groups/{group_id}/match-records` router endpoint in `apps/api/app/domains/group/router.py` (depends on T035, T010)
- [X] T037 [P] [US3] Angular：`match-records.component.ts`——對戰紀錄列表（Round/對戰雙方/比分/勝負）+ 分頁 in `apps/web/src/app/features/group-member-view/match-records/match-records.component.ts`
- [X] T038 [P] [US3] `match-records.component.html`

**Checkpoint**：US1–US3 皆可獨立運作。

---

## Phase 6: User Story 4 - 退出組團 (Priority: P2)

**Goal**：一般成員可隨時點擊「退出組團」並二次確認後離開，賽程表與控制板依既有成員異動規則自動調整。

**Independent Test**：可讓一位一般成員對一個有排隊中比賽的團觸發退出，獨立驗證確認彈窗、賽程表調整、控制板通知、以及退出後無法直接還原狀態的行為，無需依賴戰績或對戰紀錄頁面。

### Tests for User Story 4

- [X] T039 [P] [US4] Unit test：`leave_group()` 授權——Guest token 不符或 `member_id` 不符呼叫者 → `ROSTER_ENTRY_NOT_FOUND`(404)，不可代替他人退出 in `apps/api/tests/unit/domains/group/test_leave_group_authorization.py`
- [X] T040 [P] [US4] Unit test：`leave_group()` 呼叫既有 `handle_member_left(..., new_status="left")`；成功後 Guest 之 `guest_session_token` 立即失效（`status` 已非 `active`，`resolve_active_roster_membership()` 查找條件不再成立，FR-016）in `apps/api/tests/unit/domains/group/test_leave_group.py`
- [X] T041 [P] [US4] Contract test for `POST /groups/{group_id}/roster/{roster_entry_id}/leave` per `contracts/member-view-api.md`（成功回傳 `201`、非本人回傳 `404 ROSTER_ENTRY_NOT_FOUND`）in `apps/api/tests/contract/test_leave_group_endpoint.py`
- [X] T042 [US4] Integration test：Guest 退出 → `guest_session_token` 立即失效 → 該團所有場地控制板收到既有 `member.left` 事件 → 排隊中相關比賽自動調整、進行中比賽不受影響、未觸發 Round 重新排點（`current_round_number` 不變）in `apps/api/tests/integration/test_leave_group_flow.py`

### Implementation for User Story 4

- [X] T043 [US4] Implement `leave_group(session, group, roster_entry_id, guest_session_token, member)`——驗證呼叫者身分後呼叫既有 `handle_member_left(session, group, entry, new_status="left")` per research.md #7 in `apps/api/app/domains/group/service.py` (depends on T039, T040, T008)
- [X] T044 [US4] Implement `POST /groups/{group_id}/roster/{roster_entry_id}/leave` router endpoint in `apps/api/app/domains/group/router.py` (depends on T043)
- [X] T045 [P] [US4] Angular：`leave-group.component.ts`——退出按鈕 + 二次確認流程（重用既有 `confirm-dialog.component.ts`，憲章原則 V）in `apps/web/src/app/features/group-member-view/leave-group/leave-group.component.ts`
- [X] T046 [P] [US4] `leave-group.component.html`

**Checkpoint**：US1–US4 皆可獨立運作。

---

## Phase 7: User Story 5 - 會員跨團對戰紀錄 (Priority: P3)

**Goal**：已登入會員可在「會員」頁面查看自己過去參與過的所有團、所有已完成比賽的紀錄與跨團彙總勝負統計；Guest 身分的紀錄永遠不會被任何會員帳號收錄。

**Independent Test**：可用一個曾加入多個團並完成比賽的會員帳號，獨立驗證跨團對戰紀錄的彙總正確性；亦可用一個曾以 Guest 身分打過比賽、之後才註冊成為會員的帳號，驗證其會員對戰紀錄不會出現任何 Guest 時期的紀錄，均可獨立驗證。

### Tests for User Story 5

- [X] T047 [P] [US5] Unit test：`build_member_match_records()`——依 `roster_entries.member_id` JOIN 彙總跨團已完成比賽，`member_id IS NULL`（Guest）紀錄天然排除、即使該 Guest 日後註冊亦不回溯合併（research.md #9）in `apps/api/tests/unit/domains/member/test_member_match_records.py`
- [X] T048 [P] [US5] Unit test：`build_member_match_records()` 跨團彙總——`total_matches`/`total_wins`/`total_losses` 於該會員參與 ≥2 個團之已完成比賽時，累加結果正確（spec US5 Acceptance Scenario 1）in `apps/api/tests/unit/domains/member/test_member_match_records.py`
- [X] T049 [P] [US5] Unit test：跨團彙總 `win_rate`——`total_matches == 0` 時回傳 `0.0`，MUST NOT 除以零 in `apps/api/tests/unit/domains/member/test_member_match_records.py`
- [X] T050 [P] [US5] Contract test for `GET /members/me/match-records` per `contracts/member-view-api.md`（`require_member` 驗證，未登入回傳 `MEMBER_TOKEN_INVALID`）in `apps/api/tests/contract/test_member_match_records_endpoint.py`
- [X] T051 [US5] Integration test：某使用者先以 Guest 身分打過比賽、之後註冊為會員並登入 → 該會員之對戰紀錄與彙總統計皆不包含任何 Guest 時期紀錄 in `apps/api/tests/integration/test_member_match_records_flow.py`

### Implementation for User Story 5

- [X] T052 [US5] Implement `build_member_match_records(session, member_id, page)`——跨模組匯入重用 `group.service._completed_matches_query()`（research.md #8）+ `EXISTS` 條件過濾 `roster_entries.member_id == member_id`，應用層累加 `total_matches`/`total_wins`/`total_losses`/`win_rate` in `apps/api/app/domains/member/service.py` (depends on T034, T047, T048, T049)
- [X] T053 [US5] Implement `GET /members/me/match-records` router endpoint（`require_member` dependency，006 既有）in `apps/api/app/domains/member/router.py` (depends on T052)
- [X] T054 [P] [US5] Angular：`match-history.component.ts`——跨團對戰紀錄列表（含團名）+ 彙總統計（總場次/總勝/總敗/勝率）in `apps/web/src/app/features/member/match-history/match-history.component.ts`
- [X] T055 [P] [US5] `match-history.component.html`
- [X] T056 [US5] 將 `match-history` 元件納入既有 `member.component` 導覽 in `apps/web/src/app/features/member/member.component.ts` (depends on T054)

**Checkpoint**：US1–US5 全部皆可獨立運作。

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**：跨 User Story 的收尾與驗證。

- [X] T057 [P] Integration test：一般成員視角完整生命週期（導覽 → 唯讀賽程即時同步 → 多輪戰績四狀態 → 對戰紀錄 → 退出 → 退出後 token 立即失效）per quickstart.md 全部 5 個情境 in `apps/api/tests/integration/test_member_view_lifecycle.py`（constitution 原則 II 之強制整合測試要求）
- [X] T058 [P] 依 `quickstart.md` 全部 5 個情境手動驗證 apps/api 實際運作
- [X] T059 補齊本 feature 新增之 FastAPI router 端點之 `response_model`/docstring
- [X] T060 [P] Security review：確認一般成員視圖端點皆無法觸發任何管理員專屬寫入操作（FR-002）；`resolve_active_roster_membership()` 之 `MEMBERSHIP_REQUIRED` 不區分「從未加入/已退出/token 打錯」（research.md #5）；退出組團授權無法代替他人退出（FR-014）
- [X] T061 [P] Accessibility review：戰績表格「已離開」狀態不僅靠顏色區分（憲章原則 VII，FR-008 視覺呈現落實）

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：無任務，略過。
- **Foundational (Phase 2)**：schema migration + models + schemas + `resolve_active_roster_membership()`；**封鎖**所有 User Story（US1–US4 直接依賴 `resolve_active_roster_membership()`；US2 額外依賴 `round_history`/`left_at` 之寫入擴充）。
- **User Stories (Phase 3–7)**：皆依賴 Foundational 完成。
- **Polish (Phase 8)**：依賴所有欲交付的 User Story 完成。

### User Story Dependencies

- **US1（P1，MVP）**：Foundational 完成後即可開始，無其他 Story 相依；重用既有 `build_schedule_snapshot()`（007），不新增後端邏輯。
- **US2（P1）**：依賴 Foundational 之 `round_history`（T006）與 `left_at`（T008）寫入擴充，無其他 User Story 相依。
- **US3（P1）**：Foundational 完成後即可開始；新建 `_completed_matches_query()`（T034）供 US5 重用。
- **US4（P2）**：依賴 Foundational 之 `left_at` 寫入擴充（T008）與既有 003 `handle_member_left()`；無其他 User Story 相依。
- **US5（P3）**：依賴 US3 之 `_completed_matches_query()`（T034，research.md #8 明確設計為共用）——此為跨模組匯入（`app/domains/member/service.py` 匯入 `app/domains/group/service.py` 之函式，plan.md Structure Decision 已說明例外理由），也是本 feature 唯一之直接跨 Story 程式碼相依，其餘皆獨立。
- 建議依 P1→P1→P1→P2→P3 順序（US1→US2→US3→US4→US5）依序實作與驗證；US5 需等 US3 之 T034 完成才能開始其 T052。

### Within Each User Story

- Tests MUST 先寫且先失敗，再進行 Implementation。
- Service（含跨模組共用函式）→ Router endpoints → 前端整合。
- Story 完成（含 Checkpoint 驗證）才進入下一優先序 Story。

### Parallel Opportunities

- Phase 2 之 T002/T003/T004 可平行執行（不同檔案）；T005/T007/T009 三組單元測試可平行撰寫。
- 同一 User Story 內標記 `[P]` 的 Tests 可平行執行。
- 若有多位開發者：Foundational 完成後，US1、US2、US3、US4 可平行認領（彼此無直接程式碼相依）；US5 建議在 US3 完成後再認領（直接依賴其 `_completed_matches_query()`）。

---

## Parallel Example: User Story 2

```bash
# 平行執行 US2 的所有測試任務：
Task: "Unit test：四狀態公式——勝/敗判定 in apps/api/tests/unit/domains/group/test_standings_formula.py"
Task: "Unit test：四狀態公式——未上場（候補中）in apps/api/tests/unit/domains/group/test_standings_formula.py"
Task: "Unit test：四狀態公式——未上場（已捨棄）in apps/api/tests/unit/domains/group/test_standings_formula.py"
Task: "Unit test：四狀態公式——未上場（進行中/排隊中暫時性標示）in apps/api/tests/unit/domains/group/test_standings_formula.py"
Task: "Unit test：四狀態公式——未上場（加入前）in apps/api/tests/unit/domains/group/test_standings_formula.py"
Task: "Unit test：四狀態公式——已離開之不可逆特性 in apps/api/tests/unit/domains/group/test_standings_formula.py"
Task: "Unit test：四狀態公式——手動安排模式判定基準一致 in apps/api/tests/unit/domains/group/test_standings_formula.py"
Task: "Unit test：build_group_standings() 範圍隔離（不含其他團資料）in apps/api/tests/unit/domains/group/test_standings_formula.py"
Task: "Contract test for GET /groups/{group_id}/standings in apps/api/tests/contract/test_group_standings.py"
```

---

## Implementation Strategy

### MVP First（僅 User Story 1）

1. 完成 Phase 2：Foundational（schema migration + 共用身分驗證）
2. 完成 Phase 3：User Story 1
3. **停下並驗證**：獨立測試 US1（`quickstart.md` 情境 1）
4. 若已可展示，即可部署/demo（一般成員導覽 + 唯讀賽程頁 MVP 閉環至此完整）

### Incremental Delivery

1. Foundational 完成 → schema 與共用驗證就緒
2. 加入 US1 → 獨立測試 → Demo（MVP：一般成員導覽 + 唯讀賽程頁完整）
3. 加入 US2 → 獨立測試 → Demo（戰績四狀態完整）
4. 加入 US3 → 獨立測試 → Demo（對戰紀錄列表完整）
5. 加入 US4 → 獨立測試 → Demo（退出組團完整）
6. 加入 US5 → 獨立測試 → Demo（會員跨團對戰紀錄完整，功能全數交付）
7. 每個 Story 皆為既有功能疊加價值，不破壞先前 Story

### Parallel Team Strategy

多位開發者情境：

1. 團隊共同完成 Foundational（schema migration 建議由單一開發者完成，避免 migration 版本衝突）
2. Foundational 完成後：
   - 開發者 A：US1（導覽 + 唯讀賽程頁，MVP）
   - 開發者 B：US2（戰績四狀態，僅依賴 Foundational）
   - 開發者 C：US3（對戰紀錄，建立 `_completed_matches_query()` 供 US5 重用）
   - 開發者 D：US4（退出組團，僅依賴 Foundational + 既有 003 `handle_member_left`）
3. US5 建議在 US3 完成後再認領（直接依賴其 `_completed_matches_query()`）

---

## Notes

- `[P]` 任務 = 不同檔案、無相依關係（同一測試檔案內的多個測試案例任務例外標記為 `[P]`，因彼此測試函式獨立、僅共用檔案，實際撰寫時可平行處理不同函式）。
- `[Story]` 標籤將任務對應回 spec.md 的特定 User Story，供追溯。
- US2 之 Foundational 依賴（`round_history`/`left_at` 寫入擴充）刻意置於 Phase 2，因兩者皆是修改既有 003 函式（`generate_next_round`/`handle_member_left`）之最小擴充，與具體 User Story 邏輯無關，屬純粹的資料模型就緒工作。
- US5 對 US3（`_completed_matches_query()`）之相依為 research.md #8 明確設計決策（FR-021 要求共用底層查詢），非無意間產生的耦合；其 `service.py`/`router.py` 置於 `app/domains/member/` 而非 `group/`，因該端點無 `group_id` 且驗證方式為 006 既有 `require_member`（見 plan.md Structure Decision 之例外說明）。
- 實作前先確認測試會失敗（TDD，呼應 constitution 原則 II）。
- 建議每完成一項任務或一組邏輯相關任務即 commit 一次。
- 可在任一 Checkpoint 停下獨立驗證該 Story，不需等待後續 Story 完成。
- 避免：模糊任務描述、多任務同時修改同一檔案造成衝突、破壞 Story 獨立性的跨 Story 相依（US5→US3 之單一例外已於上方明確說明其正當性）。
