# Tasks: 賽程與輪替名單（Schedule & Roster Rotation）

**Input**: Design documents from `/specs/003-schedule-rotation/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md（皆已存在）

**Tests**: 依 `plan.md` Constitution Check（原則 II），核心領域邏輯（兩階段排點演算法、Round 終態判定、零場地防呆、成員異動賽程收斂、悲觀鎖衝突偵測）MUST 有單元測試，且 MUST 有至少一條涵蓋「產生 Round→完成/捨棄比賽→自動領取→Next Round」的整合測試——本檔案的測試任務為強制項，非選用。

**Organization**: 依 spec.md 之 6 個 User Story（US1–US6，依優先序 P1/P1/P1/P2/P2/P2）分階段組織，每個 Story 皆可獨立測試與交付。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行執行（不同檔案、無相依關係）
- **[Story]**: 對應 spec.md 的 US1–US6
- 每項任務皆附精確檔案路徑

## Path Conventions

沿用 `plan.md` Project Structure：`apps/api/`（FastAPI 後端）、`apps/web/`（Angular 20 前端）。monorepo 骨架已由 001 建立，本 feature 無新增 Setup 任務。

---

## Phase 1: Setup

*本 feature 無新增 Setup 任務——monorepo、CI、linting/型別檢查工具鏈已由 001 完整建立並沿用。*

---

## Phase 2: Foundational（Blocking Prerequisites）

**Purpose**：本 feature 6 個 User Story 皆需依賴的資料模型、router 骨架、以及與 001/002 既有模組的整合串接。

**⚠️ CRITICAL**：此階段完成前不可開始任何 User Story 任務。

- [X] T001 Create Alembic migration creating `matches`, `match_participants`, `pair_history`, `partnerships` tables per `data-model.md` §1–4 in `apps/api/alembic/versions/`
- [X] T002 [P] Create `Match` SQLAlchemy model in `apps/api/app/domains/schedule/models.py`
- [X] T003 [P] Create `MatchParticipant` SQLAlchemy model in `apps/api/app/domains/schedule/models.py`
- [X] T004 [P] Create `PairHistory` SQLAlchemy model in `apps/api/app/domains/schedule/models.py`
- [X] T005 [P] Create `Partnership` SQLAlchemy model in `apps/api/app/domains/schedule/models.py`
- [X] T006 [P] Define base Pydantic schemas skeleton per `contracts/schedule-api.md` in `apps/api/app/domains/schedule/schemas.py`
- [X] T007 Create `apps/api/app/domains/schedule/service.py` + `apps/api/app/domains/schedule/router.py`（空 `APIRouter`）並註冊於 `apps/api/app/main.py`
- [X] T008 [P] Unit test：FR-042 驗證擋下「單打 + 固定搭檔循環賽/個人全混搭循環賽」組合（建立團與編輯團兩條路徑）in `apps/api/tests/unit/domains/group/test_scheduling_match_mode_validation.py`
- [X] T009 Add FR-042 validation to `CreateGroupRequest`/`EditGroupRequest` schemas and `create_group`/`edit_group` service functions in `apps/api/app/domains/group/schemas.py` and `apps/api/app/domains/group/service.py` (depends on T008)
- [X] T010 Implement `abandon_group_matches(session, group_id)` in `apps/api/app/domains/schedule/service.py`, wire into `disband_group`'s call site in `apps/api/app/domains/group/router.py`（串接 001 之 `AbandonMatchesHook`，per research.md #2）(depends on T002–T004)
- [X] T011 Implement `abandon_court_matches(session, court_id) -> bool` in `apps/api/app/domains/schedule/service.py`, wire into `delete_court`'s call site in `apps/api/app/domains/court/router.py`（串接 002 之 `AbandonCourtMatchesHook`，per research.md #2）(depends on T002–T004)

**Checkpoint**：Foundation ready — User Story 任務可以開始。

---

## Phase 3: User Story 1 - 公平輪替：兩階段自動排點 (Priority: P1) 🎯 MVP

**Goal**：系統依「等待輪數」選出上場名單（階段一），再依「配對次數」決定分組（階段二），產生完整賽程表供各場地依序消化。

**Independent Test**：在已有多個場地與輪替名單成員的團上，將排程機制設為公平輪替並觸發 Round 產生，驗證上場名單排序、配對分組、wait_count 更新、人數不足時的空場處理。

### Tests for User Story 1

- [X] T012 [P] [US1] Unit test：階段一排序（`wait_count` DESC + `joined_at` ASC 次要排序、NULL 視為無限大、人數不足時部分場地空置）in `apps/api/tests/unit/domains/schedule/test_fair_rotation_stage1.py`
- [X] T013 [P] [US1] Unit test：階段二貪婪配對（依 `pair_history` 最小化，不影響階段一已決定的上場名單）in `apps/api/tests/unit/domains/schedule/test_fair_rotation_stage2.py`
- [X] T014 [P] [US1] Unit test：`wait_count` 整批更新（上場者歸零、未上場者 +1，含原本 `NULL` 者正確轉為 1）in `apps/api/tests/unit/domains/schedule/test_wait_count_update.py`
- [X] T015 [P] [US1] Unit test：比賽被捨棄仍歸零 `wait_count` 且仍計入 `pair_history`（FR-009）in `apps/api/tests/unit/domains/schedule/test_abandoned_match_counting.py`
- [X] T016 [P] [US1] Contract test for `POST /groups/{group_id}/next-round`（公平輪替情境）per `contracts/schedule-api.md` in `apps/api/tests/contract/test_next_round_fair_rotation.py`
- [X] T017 [US1] Integration test：3 場地、12 人雙打輪替名單 → 產生 Round → 3 場皆進行中、比賽設定快照正確 → `wait_count` 正確更新 in `apps/api/tests/integration/test_fair_rotation_flow.py`

### Implementation for User Story 1

- [X] T018 [US1] Implement `stage1_select_players()` in `apps/api/app/domains/schedule/algorithms.py`
- [X] T019 [US1] Implement `stage2_pair_players()`（貪婪配對）in `apps/api/app/domains/schedule/algorithms.py`
- [X] T020 [US1] Implement `pair_history` 累加 helper（`player_lo_id`/`player_hi_id` 排序 upsert，per research.md #5）in `apps/api/app/domains/schedule/service.py`
- [X] T021 [US1] Implement `wait_count` 整批更新 helper（per research.md #9）in `apps/api/app/domains/schedule/service.py`
- [X] T022 [US1] Implement `create_match_with_participants()`（寫入 `matches`+`match_participants`+`pair_history`、套用比賽設定快照）in `apps/api/app/domains/schedule/service.py` (depends on T020)
- [X] T023 [US1] Implement `generate_next_round()` 公平輪替分支（階段一+階段二+建立比賽+初次領取，per research.md #7）in `apps/api/app/domains/schedule/service.py` (depends on T018, T019, T021, T022)
- [X] T024 [US1] Implement `GET /groups/{group_id}/schedule` router endpoint per `contracts/schedule-api.md` in `apps/api/app/domains/schedule/router.py`
- [X] T025 [US1] Implement `POST /groups/{group_id}/next-round` router endpoint（本 story 僅涵蓋公平輪替路徑）in `apps/api/app/domains/schedule/router.py` (depends on T023)
- [X] T026 [P] [US1] Angular 管理頁「場地控制」區塊改接真實排程資料（取代 002 US4 骨架）in `apps/web/src/app/features/group-admin/admin-page/admin-page.component.ts`
- [X] T027 [P] [US1] Angular「Next Round」按鈕 in `apps/web/src/app/features/group-admin/admin-page/admin-page.component.ts`

**Checkpoint**：US1 完整可運作——可獨立展示「產生 Round → 各場地立即開始計分」。

---

## Phase 4: User Story 2 - 手動安排：逐場指定上場球員 (Priority: P1)

**Goal**：管理員在場地空閒時親自選人建立比賽，不預先產生賽程表。

**Independent Test**：將排程機制設為手動安排，驗證場地空閒時顯示等待安排提示、選人建立比賽的流程與防呆規則、`wait_count` 同步更新。

### Tests for User Story 2

- [X] T028 [P] [US2] Unit test：FR-013 三項防呆（已在其他場地進行中／已離開／同場重複選擇）in `apps/api/tests/unit/domains/schedule/test_manual_assign_validation.py`
- [X] T029 [P] [US2] Unit test：手動安排比賽不經過 `queued`、建立當下參與者 `wait_count` 歸零（FR-014/015）in `apps/api/tests/unit/domains/schedule/test_manual_assign_wait_count.py`
- [X] T030 [P] [US2] Contract test for `POST /courts/{court_id}/manual-assign` per `contracts/schedule-api.md` in `apps/api/tests/contract/test_manual_assign.py`
- [X] T031 [US2] Integration test：手動安排模式場地顯示「等待管理員安排」→ 選人建立比賽 → 直接進行中，全程無 `queued` 狀態 in `apps/api/tests/integration/test_manual_assign_flow.py`

### Implementation for User Story 2

- [X] T032 [US2] Implement `manual_assign()` service in `apps/api/app/domains/schedule/service.py` (depends on T022)
- [X] T033 [US2] Implement `POST /courts/{court_id}/manual-assign` router endpoint in `apps/api/app/domains/schedule/router.py` (depends on T032)
- [X] T034 [P] [US2] Angular 手動安排選人介面 in `apps/web/src/app/features/group-admin/schedule-management/manual-assign.component.ts`

**Checkpoint**：US1–US2 皆可獨立運作。

---

## Phase 5: User Story 3 - Round 生命週期：賽程表消耗、Next Round 與 Auto Next Round (Priority: P1)

**Goal**：賽程表消耗完畢後可自動（Auto Next Round）或手動（Next Round）進入下一輪；零場地時防呆攔截。

**Independent Test**：讓賽程表自然消耗完畢驗證 Auto Next Round 觸發、隨時手動按下 Next Round 驗證強制重排、零場地狀態下觸發兩種操作驗證防呆提示。

### Tests for User Story 3

- [X] T035 [P] [US3] Unit test：Round 終態判定（`completed`/`abandoned` 皆算終態，FR-028）in `apps/api/tests/unit/domains/schedule/test_round_completion.py`
- [X] T036 [P] [US3] Unit test：零場地防呆（`Next Round` 與 `Auto Next Round` 皆拒絕、場地數為 0 且已開啟自動機制時不嘗試產生，FR-029/030）in `apps/api/tests/unit/domains/schedule/test_zero_court_guard.py`
- [X] T037 [P] [US3] Unit test：`advance_court_after_match_ends` 領取下一場排隊中比賽，或無排隊中比賽時維持「等待下一輪」（FR-027）in `apps/api/tests/unit/domains/schedule/test_advance_court.py`
- [X] T038 [P] [US3] Unit test：`Next Round` 強制捨棄目前排隊中/進行中比賽後立即重新產生下一輪（FR-032/033，含手動安排模式的捨棄+等待安排路徑）in `apps/api/tests/unit/domains/schedule/test_next_round_force.py`
- [X] T039 [P] [US3] Unit test：悲觀鎖取得失敗回傳 `ROUND_GENERATION_IN_PROGRESS`（research.md #8）in `apps/api/tests/unit/domains/schedule/test_next_round_locking.py`
- [X] T040 [P] [US3] Contract test for `PATCH /groups/{group_id}/auto-next-round` per `contracts/schedule-api.md` in `apps/api/tests/contract/test_auto_next_round.py`
- [X] T041 [US3] Integration test：比賽達終態 → 自動領取下一場 → 賽程表消耗完畢 → 已開啟 Auto Next Round 時自動產生下一輪 in `apps/api/tests/integration/test_round_lifecycle_flow.py`

### Implementation for User Story 3

- [X] T042 [US3] Implement `advance_court_after_match_ends(session, match)` in `apps/api/app/domains/schedule/service.py`（手動安排模式 no-op，per research.md #10）(depends on T023)
- [X] T043 [US3] Implement `check_round_complete_and_maybe_auto_advance(session, group)` in `apps/api/app/domains/schedule/service.py` (depends on T042)
- [X] T044 [US3] 擴充 `generate_next_round()`：加入悲觀鎖（`SELECT ... FOR UPDATE NOWAIT`）、零場地防呆、`Next Round` 強制捨棄路徑（演算法模式與手動安排模式分支，FR-029～033）in `apps/api/app/domains/schedule/service.py` (depends on T023)
- [X] T045 [US3] Implement `PATCH /groups/{group_id}/auto-next-round` router endpoint（含 FR-016 反向防呆：手動安排模式下拒絕啟用）in `apps/api/app/domains/schedule/router.py`
- [X] T046 [P] [US3] Angular「Auto Next Round」開關 + 賽程狀態顯示（等待下一輪／等待管理員安排）in `apps/web/src/app/features/group-admin/admin-page/admin-page.component.ts`

**Checkpoint**：US1–US3 皆可獨立運作，已具備可展示的完整輪替閉環。

---

## Phase 6: User Story 4 - 固定搭檔循環賽 (Priority: P2)

**Goal**：搭檔固定，依隊伍層級排序決定誰上場、依跨隊配對次數決定對戰組合；管理頁提供搭檔設定區塊。

**Independent Test**：切換為固定搭檔循環賽，驗證初始自動配對、搭檔設定區塊手動調整、新成員加入配對、搭檔離開後落單、切換離開/切回時的配對重置。

### Tests for User Story 4

- [X] T047 [P] [US4] Unit test：切換進入時依加入順序自動配對，人數為奇數時最後一人落單（FR-020）in `apps/api/tests/unit/domains/schedule/test_partnership_auto_pairing.py`
- [X] T048 [P] [US4] Unit test：隊伍層級階段一選人（優先度 = 兩隊員 `wait_count` 較高者 MAX，落單者不列入上場名單）in `apps/api/tests/unit/domains/schedule/test_fixed_partner_stage1.py`
- [X] T049 [P] [US4] Unit test：跨隊個人配對次數加總最小決定隊伍對戰組合（FR-019，貪婪法依序處理多場地）in `apps/api/tests/unit/domains/schedule/test_fixed_partner_stage2.py`
- [X] T050 [P] [US4] Unit test：搭檔設定手動重新配對，原搭檔各自變回落單，不影響既有排隊中/進行中比賽（FR-021）in `apps/api/tests/unit/domains/schedule/test_partnership_manual_reassign.py`
- [X] T051 [P] [US4] Unit test：新成員加入時與落單者自動配對，或成為新落單者；搭檔一方離開/被踢除時另一方變回落單（FR-022/023）in `apps/api/tests/unit/domains/schedule/test_partnership_membership_changes.py`
- [X] T052 [P] [US4] Unit test：切換離開時 Partnership 全數清空，切回時視為全新配對流程，`PairHistory` 不受影響（FR-024）in `apps/api/tests/unit/domains/schedule/test_partnership_mechanism_switch.py`
- [X] T053 [P] [US4] Contract test for `GET /groups/{group_id}/partnerships` and `PATCH /groups/{group_id}/partnerships` per `contracts/schedule-api.md` in `apps/api/tests/contract/test_partnerships.py`
- [X] T054 [US4] Integration test：切換為固定搭檔循環賽 → 自動配對 → 產生 Round → 驗證隊伍層級選人與跨隊配對結果 in `apps/api/tests/integration/test_fixed_partner_flow.py`

### Implementation for User Story 4

- [X] T055 [US4] Implement `team_stage1_select()`（`Partnership` 為單位，MAX `wait_count` 優先度）in `apps/api/app/domains/schedule/algorithms.py`
- [X] T056 [US4] Implement `team_matchup_stage2()`（跨隊配對次數加總最小，貪婪法）in `apps/api/app/domains/schedule/algorithms.py`
- [X] T057 [US4] Implement `auto_pair_on_enter_fixed_partner()`、`clear_partnerships_on_exit()` in `apps/api/app/domains/schedule/service.py`
- [X] T058 [US4] Implement `manual_partnership_reassign()`、成員加入/離開之 Partnership 連動 handler in `apps/api/app/domains/schedule/service.py`
- [X] T059 [US4] 擴充 `generate_next_round()` 加入固定搭檔循環賽分支（使用 T055/T056）in `apps/api/app/domains/schedule/service.py` (depends on T055, T056)
- [X] T060 [US4] 串接 001 之 `PATCH /groups/{group_id}`（`edit_group`）：於 `scheduling_mechanism` 變動時呼叫 Partnership 副作用函式，per research.md #4 in `apps/api/app/domains/group/router.py` (depends on T057)
- [X] T061 [US4] Implement `GET /groups/{group_id}/partnerships` and `PATCH /groups/{group_id}/partnerships` router endpoints in `apps/api/app/domains/schedule/router.py`
- [X] T062 [P] [US4] Angular 搭檔設定區塊 in `apps/web/src/app/features/group-admin/schedule-management/partnership-settings.component.ts`

**Checkpoint**：US1–US4 皆可獨立運作。

---

## Phase 7: User Story 5 - 個人全混搭循環賽 (Priority: P2)

**Goal**：每輪重新配對，複用公平輪替與固定搭檔循環賽已定案的演算法邏輯，不另建新演算法。

**Independent Test**：切換為個人全混搭循環賽並觸發 Round 產生，驗證兩步驟貪婪法（先分搭檔、再分隊伍對戰）的執行順序與結果。

### Tests for User Story 5

- [X] T063 [P] [US5] Unit test：兩步驟貪婪法——第一步沿用 FR-008 配對邏輯決定搭檔，第二步沿用 FR-019 跨隊配對邏輯決定隊伍對戰，不新增或另行驗證新演算法 in `apps/api/tests/unit/domains/schedule/test_individual_mixed.py`
- [X] T064 [US5] Integration test：切換為個人全混搭循環賽 → 產生 Round → 驗證兩步驟分派結果 in `apps/api/tests/integration/test_individual_mixed_flow.py`

### Implementation for User Story 5

- [X] T065 [US5] 於 `generate_next_round()` 加入個人全混搭循環賽分支，重用 `stage2_pair_players()`（T019）+ `team_matchup_stage2()`（T056）in `apps/api/app/domains/schedule/service.py` (depends on T019, T056)

**Checkpoint**：US1–US5 皆可獨立運作。

---

## Phase 8: User Story 6 - 成員加入/退出/踢除對賽程表的影響 (Priority: P2)

**Goal**：管理員可踢除成員；成員中途加入/退出時正確調整賽程表，不多不少、不誤觸發整輪重排。

**Independent Test**：在賽程表運作中的團上，分別測試中途加入新成員、成員主動退出（透過直接呼叫 service 函式模擬，見 plan.md Assumptions）、管理員踢除成員三種情境。

### Tests for User Story 6

- [X] T066 [P] [US6] Unit test：移除成員自排隊中比賽移除該人，人數不足則整場移除，進行中比賽不受影響，且不觸發整輪重新排點（FR-039/040/041）in `apps/api/tests/unit/domains/schedule/test_member_removal.py`
- [X] T067 [P] [US6] Unit test：中途加入者不影響目前 Round 已產生的賽程表、不觸發任何重排（FR-038）in `apps/api/tests/unit/domains/schedule/test_member_joined.py`
- [X] T068 [P] [US6] Contract test for `DELETE /groups/{group_id}/members/{roster_entry_id}` per `contracts/schedule-api.md` in `apps/api/tests/contract/test_kick_member.py`
- [X] T069 [US6] Integration test：Round 進行中踢除成員（同時涉及排隊中與進行中比賽）→ 正確收斂、不觸發整輪重排 in `apps/api/tests/integration/test_kick_member_flow.py`

### Implementation for User Story 6

- [X] T070 [US6] Implement `remove_roster_entry_from_schedule()` 共用邏輯（排隊中移除該成員、人數不足時整場移除、固定搭檔模式下 Partnership 清理）in `apps/api/app/domains/schedule/service.py` (depends on T057)
- [X] T071 [US6] Implement `handle_member_joined()`、`handle_member_left()`、`kick_member()`（皆使用 T070）in `apps/api/app/domains/schedule/service.py` (depends on T070)
- [X] T072 [US6] Implement `DELETE /groups/{group_id}/members/{roster_entry_id}` router endpoint + 發布 `member.left` in `apps/api/app/domains/schedule/router.py` (depends on T071)
- [X] T073 [P] [US6] Angular 踢除成員按鈕 + 二次確認 dialog in `apps/web/src/app/features/group-admin/admin-page/admin-page.component.ts`

**Checkpoint**：US1–US6 全部皆可獨立運作。

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**：跨 User Story 的收尾與驗證。

- [X] T074 [P] Integration test：完整流程「新增輪替名單成員 → 產生 Round → 完成/捨棄比賽 → 自動領取下一場 → Next Round」in `apps/api/tests/integration/test_schedule_lifecycle.py`（constitution 原則 II 之強制整合測試要求）
- [X] T075 [P] SC-002 多輪模擬驗證（人數可被場地容量整除時，任兩位 active 參與者累計上場次數差距 100% 不超過 1 次）in `apps/api/tests/unit/domains/schedule/test_fairness_simulation.py`
- [X] T076 [P] 依 `quickstart.md` 全部 5 個情境手動驗證 apps/api 實際運作
- [X] T077 補齊本 feature 新增之 FastAPI router 端點（`schedule`、擴充的 `group`/`court`）之 `response_model`/docstring
- [X] T078 [P] Security review：確認 `manual-assign`／踢除／搭檔設定端點皆正確要求 `require_admin`，且回應內容不洩漏其他團的輪替名單或比賽資料

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：無任務，略過。
- **Foundational (Phase 2)**：依賴 001/002 已建立之基礎設施；**封鎖**所有 User Story。
- **User Stories (Phase 3–8)**：皆依賴 Foundational 完成。
- **Polish (Phase 9)**：依賴所有欲交付的 User Story 完成。

### User Story Dependencies

- **US1（P1，MVP）**：Foundational 完成後即可開始，無其他 Story 相依。
- **US2（P1）**：依賴 US1 之 `create_match_with_participants()`（T022）共用寫入邏輯，程式碼上為新增分支而非修改。
- **US3（P1）**：依賴 US1 之 `generate_next_round()`（T023）——本 story 為其擴充悲觀鎖/防呆/強制捨棄路徑，非重新實作。
- **US4（P2）**：依賴 US1 之演算法框架（`generate_next_round()` 分派結構）與 Foundational 之 `Partnership` model；獨立於 US2/US3 之外的邏輯。
- **US5（P2）**：依賴 US1 之 `stage2_pair_players()`（T019）與 US4 之 `team_matchup_stage2()`（T056）——純粹複用，無新演算法。
- **US6（P2）**：依賴 US4 之 Partnership 清理邏輯（T057，若當下為固定搭檔模式）；獨立於 US2/US3/US5。
- 建議依 P1→P1→P1→P2→P2→P2 順序（US1→US2→US3→US4→US5→US6）依序實作與驗證；US5 必須晚於 US4（程式碼直接複用其函式）。

### Within Each User Story

- Tests MUST 先寫且先失敗，再進行 Implementation。
- Algorithms → Service（含跨模組串接）→ Router endpoints → 前端整合。
- Story 完成（含 Checkpoint 驗證）才進入下一優先序 Story。

### Parallel Opportunities

- Phase 2 內標記 `[P]` 的任務可平行執行（惟 T008/T009 為序列相依、T010/T011 皆依賴 T002–T004 完成）。
- 同一 User Story 內標記 `[P]` 的 Tests 可平行執行。
- 若有多位開發者：US1 完成後，US2、US3 可平行認領（皆僅依賴 US1 的核心寫入/分派邏輯，彼此無直接程式碼相依）；US4 可與 US2/US3 平行進行；US5、US6 需等待 US4 完成後才能平行認領。

---

## Parallel Example: User Story 1

```bash
# 平行執行 US1 的所有測試任務：
Task: "Unit test：階段一排序 in apps/api/tests/unit/domains/schedule/test_fair_rotation_stage1.py"
Task: "Unit test：階段二貪婪配對 in apps/api/tests/unit/domains/schedule/test_fair_rotation_stage2.py"
Task: "Unit test：wait_count 整批更新 in apps/api/tests/unit/domains/schedule/test_wait_count_update.py"
Task: "Unit test：捨棄比賽計數 in apps/api/tests/unit/domains/schedule/test_abandoned_match_counting.py"
Task: "Contract test for POST /groups/{group_id}/next-round in apps/api/tests/contract/test_next_round_fair_rotation.py"
```

---

## Implementation Strategy

### MVP First（僅 User Story 1）

1. 完成 Phase 2：Foundational（關鍵，封鎖所有 Story）
2. 完成 Phase 3：User Story 1
3. **停下並驗證**：獨立測試 US1（`quickstart.md` 情境 1）
4. 若已可展示，即可部署/demo

### Incremental Delivery

1. Foundational 完成 → 基礎就緒
2. 加入 US1 → 獨立測試 → Demo（MVP！）
3. 加入 US2 → 獨立測試 → Demo（排程機制選擇完整）
4. 加入 US3 → 獨立測試 → Demo（完整輪替閉環：Round 接續運作）
5. 依序加入 US4 → US5 → US6，每個 Story 皆獨立測試後再交付
6. 每個 Story 皆為既有功能疊加價值，不破壞先前 Story

### Parallel Team Strategy

多位開發者情境：

1. 團隊共同完成 Foundational
2. Foundational 完成後：
   - 開發者 A：US1（公平輪替，MVP 核心）
   - 開發者 B：待 US1 的 `create_match_with_participants()` 就緒後，平行進行 US2（手動安排）
   - 開發者 C：待 US1 的 `generate_next_round()` 框架就緒後，平行進行 US3（Round 生命週期）
3. US4（固定搭檔循環賽）可與 US2/US3 平行進行（僅依賴 Foundational 的 `Partnership` model）
4. US5、US6 建議於 US4 完成後再由任一開發者認領（程式碼直接複用 US4 的函式）

---

## Notes

- `[P]` 任務 = 不同檔案、無相依關係。
- `[Story]` 標籤將任務對應回 spec.md 的特定 User Story，供追溯。
- 每個 User Story 皆應可獨立完成與測試；US6 之「成員主動退出」情境透過直接呼叫 `handle_member_left()` service 函式模擬驗證（實際 HTTP 端點屬 005 spec 範圍，見 plan.md Assumptions）。
- 實作前先確認測試會失敗（TDD，呼應 constitution 原則 II）。
- 建議每完成一項任務或一組邏輯相關任務即 commit 一次。
- 可在任一 Checkpoint 停下獨立驗證該 Story，不需等待後續 Story 完成。
- 避免：模糊任務描述、多任務同時修改同一檔案造成衝突、破壞 Story 獨立性的跨 Story 相依。
