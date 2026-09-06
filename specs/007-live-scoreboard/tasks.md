# Tasks: 即時計分板與控制板（Live Scoreboard & Control Panel）

**Input**: Design documents from `/specs/007-live-scoreboard/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md（皆已存在）

**Tests**: 依 `plan.md` Constitution Check（原則 II），核心領域邏輯（+1/-1 原子防呆之真實併發測試、達標判定公式之邊界情境、提前結束之捨棄規則、`match_id`/`court_id` 授權邊界、`control_panel_token` vs `scoreboard_token` 之寫入端點拒絕）MUST 有單元測試，且 MUST 有至少一條涵蓋「+1/-1 → 自然達標 → 自動領取下一場 → 延遲請求 no-op」的整合測試——本檔案的測試任務為強制項，非選用。

**Organization**：依 spec.md 之 5 個 User Story（US1–US5，優先序 P1/P1/P1/P2/P2）分階段組織，每個 Story 皆可獨立測試與交付。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行執行（不同檔案、無相依關係）
- **[Story]**: 對應 spec.md 的 US1–US5
- 每項任務皆附精確檔案路徑

## Path Conventions

沿用 `plan.md` Project Structure：`apps/api/`（FastAPI 後端）、`apps/web/`（Angular 20 前端）。monorepo 骨架已由 001 建立，本 feature 無新增 Setup 任務，亦無需 Alembic migration（data-model.md 已確認不新增資料表/欄位）。

---

## Phase 1: Setup

*本 feature 無新增 Setup 任務——monorepo、CI、linting/型別檢查工具鏈已由 001 完整建立並沿用。*

---

## Phase 2: Foundational（Blocking Prerequisites）

**Purpose**：本 feature 5 個 User Story 共用的 Pydantic/TypeScript schema 骨架。本 feature 不需要資料表/欄位遷移（data-model.md 已確認全部欄位由 001/003 建立），故此階段極輕量。

**⚠️ CRITICAL**：此階段完成前不可開始任何 User Story 任務。

- [X] T001 [P] Define Pydantic schemas skeleton（`CourtLiveState`/`MatchLiveDetail`/`NextUpPreview`/`ScoreMutationResult`/`ScoreRequest`）per `data-model.md` in `apps/api/app/domains/schedule/schemas.py`
- [X] T002 [P] Define TypeScript models mirroring 上述 schema（供 control-panel/scoreboard/all-courts 元件共用）in `apps/web/src/app/core/api/court-live-state.models.ts`

**Checkpoint**：Foundation ready — User Story 任務可以開始。

---

## Phase 3: User Story 1 - 計分操作與自動判定勝負 (Priority: P1) 🎯 MVP

**Goal**：計分員在單一場地控制板用 +1/-1 即時調整分數；達標時系統自動判定比賽結束並自動領取下一場（演算法排程機制）；比分下限與已終態比賽皆有原子防呆。

**Independent Test**：對一場進行中的比賽獨立驗證 +1/-1 操作、達標自動結束、比分下限防呆、已結束比賽拒絕延遲請求，無需依賴提前結束或全部場地控制板。

### Tests for User Story 1

- [X] T003 [P] [US1] Unit test：`_match_wins()` 達標判定公式——21 分制（21/20/30）、15 分制（15/14/21）、自訂三組數值之邊界情境（未達標/剛好達標/deuce 需領先 2 分/觸及封頂）in `apps/api/tests/unit/domains/schedule/test_match_wins.py`
- [X] T004 [P] [US1] Unit test：`apply_score_delta()` 已終態比賽拒絕 +1（`completed`/`abandoned` 兩種情境皆測，`applied=false`、比分不變）in `apps/api/tests/unit/domains/schedule/test_apply_score_delta.py`
- [X] T005 [P] [US1] Unit test：`apply_score_delta()` 分數下限防呆——`-1` 於 `score=0` 時拒絕，`applied=false`，不出現負數 in `apps/api/tests/unit/domains/schedule/test_apply_score_delta.py`
- [X] T006 [US1] Unit test：真實併發測試——兩條獨立資料庫連線對同一 `in_progress` 比賽同時各自送出 +1，皆正確疊加（Edge Case：兩位計分員幾乎同時按 +1，比照 004 `test_join_capacity_concurrency.py` 之雙連線模式）in `apps/api/tests/unit/domains/schedule/test_score_concurrency.py`
- [X] T007 [P] [US1] Unit test：`apply_score_delta()` 達標後正確轉為 `completed` 並寫入 `winner_team`，同時呼叫既有 `advance_court_after_match_ends` 領取下一場排隊中比賽（演算法排程機制）in `apps/api/tests/unit/domains/schedule/test_apply_score_delta.py`
- [X] T008 [P] [US1] Unit test：`match_id` 對應之 `court_id` 與 token 解析出的場地不符時拒絕（`MATCH_NOT_FOUND`，research.md #4）in `apps/api/tests/unit/domains/schedule/test_score_authorization.py`
- [X] T009 [P] [US1] Unit test：以 `scoreboard_token`（而非 `control_panel_token`）呼叫寫入端點拒絕（`LINK_NOT_FOUND`，research.md #3）in `apps/api/tests/unit/domains/schedule/test_score_authorization.py`
- [X] T010 [P] [US1] Contract test for `GET /courts/by-token/{token}/state` per `contracts/scoring-api.md` in `apps/api/tests/contract/test_court_state.py`
- [X] T011 [P] [US1] Contract test for `POST /courts/by-token/{token}/matches/{match_id}/score` per `contracts/scoring-api.md` in `apps/api/tests/contract/test_score_endpoint.py`
- [X] T012 [US1] Integration test：+1/-1 → 自然達標 → 自動領取下一場（演算法模式）→ 針對已結束 `match_id` 的延遲 +1 請求 no-op、不影響新比賽 in `apps/api/tests/integration/test_scoring_flow.py`

### Implementation for User Story 1

- [X] T013 [US1] Implement `_match_wins(score_x, score_y, target_score, cap_score)` 達標判定公式 per research.md #2 in `apps/api/app/domains/schedule/service.py`
- [X] T014 [US1] Implement `apply_score_delta(session, match_id, court, side, delta)`——原子 `UPDATE ... WHERE status='in_progress' [AND score>0]`（research.md #5）、命中後套用 `_match_wins()` 判定、達標時同一交易內第二句 `UPDATE` 寫入 `completed`/`winner_team`、依序呼叫既有 `advance_court_after_match_ends`/`check_round_complete_and_maybe_auto_advance`（research.md #6）、commit、發布 `match.scoreUpdated`/`match.ended`（重用既有 `rotation.updated`/`match.nextRound`，research.md #7）in `apps/api/app/domains/schedule/service.py` (depends on T013)
- [X] T015 [US1] Implement `court_live_state(session, court)`——組出 `CourtLiveState`（`round_number`/`current_match`/`waiting_reason`，`next_up` 留待 US3 補上）in `apps/api/app/domains/schedule/service.py`
- [X] T016 [US1] Implement `GET /courts/by-token/{token}/state` router endpoint（公開，接受 `scoreboard_token` 或 `control_panel_token`）in `apps/api/app/domains/schedule/router.py` (depends on T015)
- [X] T017 [US1] Implement `POST /courts/by-token/{token}/matches/{match_id}/score` router endpoint（僅接受 `control_panel_token`，`link_type` 檢查 research.md #3）in `apps/api/app/domains/schedule/router.py` (depends on T014)
- [X] T018 [US1] Implement `POST /groups/{group_id}/courts/{court_id}/matches/{match_id}/score` router endpoint（管理員版本，比照既有 `_admin_court` dependency 模式，research.md #10）in `apps/api/app/domains/schedule/router.py` (depends on T014)
- [X] T019 [P] [US1] Angular：擴充 `control-panel.component.ts` 串接 `GET .../state` 初始載入 + +1/-1 按鈕呼叫 score 端點 + 訂閱 `match.scoreUpdated`/`match.ended` 更新畫面 in `apps/web/src/app/features/control-panel/control-panel.component.ts`
- [X] T020 [P] [US1] Angular `control-panel.component.html`：比分/Round 編號/+1-1 按鈕版面 in `apps/web/src/app/features/control-panel/control-panel.component.html`
- [X] T021 [P] [US1] Angular `court-control.service.ts`（封裝 state/score API 呼叫，供 US2/US3/US5 共用擴充）in `apps/web/src/app/core/api/court-control.service.ts`

**Checkpoint**：US1 完整可運作——可獨立展示「控制板 +1/-1 → 自動判定勝負 → 自動領取下一場」。

---

## Phase 4: User Story 2 - 提前結束比賽 (Priority: P1)

**Goal**：計分員因特殊情況按「提前結束」手動結束本場比賽；提前結束的比賽視為捨棄，不產生 `winner_team`，場地依排程機制自動或等待安排下一場。

**Independent Test**：對一場進行中的比賽觸發「提前結束」，獨立驗證確認流程、捨棄規則、以及依排程機制不同的場地後續行為，無需依賴自然結束的完整流程。

### Tests for User Story 2

- [X] T022 [P] [US2] Unit test：`end_match_early()` 正確轉為 `abandoned`、`winner_team` 保持 `NULL`（research.md #1，即「不產生 MatchResult」）in `apps/api/tests/unit/domains/schedule/test_end_match_early.py`
- [X] T023 [P] [US2] Unit test：已終態比賽（`completed` 或 `abandoned`）呼叫 `end_match_early()` 拒絕（`applied=false`，FR-006a）in `apps/api/tests/unit/domains/schedule/test_end_match_early.py`
- [X] T024 [P] [US2] Contract test for `POST /courts/by-token/{token}/matches/{match_id}/end` per `contracts/scoring-api.md` in `apps/api/tests/contract/test_end_match_endpoint.py`
- [X] T025 [US2] Integration test：提前結束 → 場地依排程機制自動領取下一場（演算法模式）；另測手動模式下顯示「等待管理員安排下一場」in `apps/api/tests/integration/test_end_match_flow.py`

### Implementation for User Story 2

- [X] T026 [US2] Implement `end_match_early(session, match_id, court)`——原子 `UPDATE ... WHERE status='in_progress'` 轉 `abandoned`（research.md #5）、依序呼叫 `advance_court_after_match_ends`/`check_round_complete_and_maybe_auto_advance`、commit、發布 `match.ended`（`waiting_reason` 邏輯，research.md #7）in `apps/api/app/domains/schedule/service.py` (依循 T014 已建立的 hook-chaining 模式)
- [X] T027 [US2] Implement `POST /courts/by-token/{token}/matches/{match_id}/end` router endpoint in `apps/api/app/domains/schedule/router.py` (depends on T026)
- [X] T028 [US2] Implement `POST /groups/{group_id}/courts/{court_id}/matches/{match_id}/end` router endpoint（管理員版本）in `apps/api/app/domains/schedule/router.py` (depends on T026)
- [X] T029 [P] [US2] Angular：`control-panel.component.ts` 新增「提前結束」按鈕邏輯 + 二次確認流程（重用既有 `confirm-dialog.component.ts`，憲章原則 V）in `apps/web/src/app/features/control-panel/control-panel.component.ts`
- [X] T030 [P] [US2] Angular `control-panel.component.html`：新增提前結束按鈕與確認彈窗 UI in `apps/web/src/app/features/control-panel/control-panel.component.html`

**Checkpoint**：US1–US2 皆可獨立運作。

---

## Phase 5: User Story 3 - 計分板公開顯示 (Priority: P1)

**Goal**：球員/旁觀者開啟計分板連結，以大字體即時看到比分、雙方名稱、Round 編號、下一組「即將登場」預告，全程不需登入或手動重新整理。

**Independent Test**：獨立開啟一個場地的計分板連結，驗證大字體比分顯示、Round 編號呈現方式、即將登場預告、以及即時同步行為（可由其他測試流程觸發比分變動後觀察此畫面反映）。

### Tests for User Story 3

- [X] T031 [P] [US3] Unit test：`peek_next_queued_match()` 唯讀查詢——回傳下一場 `queued` 比賽的參賽者，不修改 `court_id`/`status`、不影響後續 `pull_queued_match_for_court` 之領取結果（research.md #11）in `apps/api/tests/unit/domains/schedule/test_peek_next_queued_match.py`
- [X] T032 [P] [US3] Unit test：手動安排模式下 `court_live_state()` 之 `next_up` 恆為 `null`、`waiting_reason="manual_assignment"`（FR-018）in `apps/api/tests/unit/domains/schedule/test_court_live_state.py`
- [X] T033 [P] [US3] Contract test for `GET /courts/by-token/{token}/state` 之 `next_up` 欄位（含演算法模式有/無排隊中比賽、手動模式三種情境）per `contracts/scoring-api.md` in `apps/api/tests/contract/test_court_state.py`
- [X] T034 [US3] Integration test：同團兩場地同時進行同一輪，皆顯示相同 `round_number`，直到該輪賽程表消耗完畢 in `apps/api/tests/integration/test_round_number_consistency.py`

### Implementation for User Story 3

- [X] T035 [US3] Implement `peek_next_queued_match(session, group_id, round_number, court_id)`——唯讀版本，`SELECT` 不帶 `with_for_update`（research.md #11）in `apps/api/app/domains/schedule/service.py`
- [X] T036 [US3] 擴充 `court_live_state()` 加入 `next_up` 欄位（呼叫 T035）in `apps/api/app/domains/schedule/service.py` (depends on T015, T035)
- [X] T037 [P] [US3] Angular：擴充 `scoreboard.component.ts` 串接 `GET .../state` + 訂閱 `match.scoreUpdated`/`match.ended`/`rotation.updated`，大字體顯示比分/雙方名稱/Round 編號（獨立標籤區隔，FR-017）/即將登場預告 in `apps/web/src/app/features/scoreboard/scoreboard.component.ts`
- [X] T038 [P] [US3] Angular `scoreboard.component.html`：大字體比分版面、Round 編號視覺區隔、即將登場/等待管理員安排文案 in `apps/web/src/app/features/scoreboard/scoreboard.component.html`

**Checkpoint**：US1–US3 皆可獨立運作——核心「控制板操作 + 計分板顯示」閉環完整。

---

## Phase 6: User Story 4 - 斷線與重新連線處理 (Priority: P2)

**Goal**：控制板、計分板、管理頁場地控制區塊，於即時連線中斷時明確提示並限制操作；重新連線後強制以伺服器最新狀態覆蓋畫面。

**Independent Test**：模擬一個場地的控制板、計分板、以及管理頁場地控制區塊分別斷線與重連，獨立驗證斷線提示、斷線期間操作限制、重連後強制覆蓋畫面等行為。

### Tests for User Story 4

- [X] T039 [P] [US4] Vitest：共用重連刷新邏輯——`connectionState` 從非 `connected` 轉為 `connected` 時觸發一次 state 重新拉取，其餘轉換（含持續斷線中）不觸發 in `apps/web/src/app/core/realtime/reconnect-refetch.service.spec.ts`
- [X] T040 [P] [US4] Unit test：擴充後 `GET /groups/{group_id}/schedule` 之 `score_a`/`score_b`/`next_up` 欄位正確性 in `apps/api/tests/unit/domains/schedule/test_schedule_snapshot.py`
- [X] T041 [P] [US4] Contract test for 管理員版本 `POST .../score`、`POST .../end` 端點（PIN session 驗證，未驗證則 401/403）per `contracts/scoring-api.md` in `apps/api/tests/contract/test_admin_score_endpoints.py`

### Implementation for User Story 4

- [X] T042 [US4] Implement `reconnect-refetch.service.ts`（共用：觀察 `RealtimeService.connectionState` 轉換、轉為 `connected` 時觸發傳入的 refetch callback，research.md #8）in `apps/web/src/app/core/realtime/reconnect-refetch.service.ts`
- [X] T043 [P] [US4] Angular：`scoreboard.component.ts`/`control-panel.component.ts` 串接 `reconnect-refetch.service`（斷線提示 UI + 操作停用/警示 + 重連強制覆蓋，FR-022~024）in `apps/web/src/app/features/scoreboard/scoreboard.component.ts`, `apps/web/src/app/features/control-panel/control-panel.component.ts` (depends on T042)
- [X] T044 [US4] 擴充 `MatchSummary`/`CourtScheduleStatus` schema 加入 `score_a`/`score_b`/`next_up` in `apps/api/app/domains/schedule/schemas.py` (depends on T035)
- [X] T045 [US4] 擴充 `build_schedule_snapshot()` 組入上述新欄位 in `apps/api/app/domains/schedule/service.py` (depends on T044, T035)
- [X] T046 [US4] Implement 管理頁「場地控制」區塊元件——顯示比分/Round/即將登場 + +1/-1/提前結束操作（呼叫 T018/T028 之管理員端點）+ 串接 `reconnect-refetch.service` in `apps/web/src/app/features/group-admin/schedule-management/court-control.component.ts` (depends on T018, T028, T042)
- [X] T047 [P] [US4] `court-control.component.html` 版面 in `apps/web/src/app/features/group-admin/schedule-management/court-control.component.html`
- [X] T048 [US4] 將 `court-control` 元件嵌入既有 `admin-page.component` in `apps/web/src/app/features/group-admin/admin-page/admin-page.component.ts` (depends on T046)

**Checkpoint**：US1–US4 皆可獨立運作。

---

## Phase 7: User Story 5 - 全部場地控制板與控制板的權限邊界 (Priority: P2)

**Goal**：現場人手不足時可打開「全部場地控制板」在同一畫面操作團內所有場地；不論哪種控制板，皆不提供 Next Round 操作入口。

**Independent Test**：開啟一個團的全部場地控制板，獨立驗證同一畫面可操作所有場地、與單一場地控制板的即時同步一致性、以及畫面上確實找不到任何 Next Round 相關操作。

### Tests for User Story 5

- [X] T049 [P] [US5] Unit test：全部場地 token 之 score/end 端點——`match_id` 與 `court_id` 路徑參數不符時拒絕（同 research.md #4 之授權邊界）in `apps/api/tests/unit/domains/schedule/test_all_courts_score_authorization.py`
- [X] T050 [P] [US5] Contract test for `GET /groups/by-all-courts-token/{token}/state` per `contracts/scoring-api.md` in `apps/api/tests/contract/test_all_courts_state.py`
- [X] T051 [P] [US5] Contract test for `POST /groups/by-all-courts-token/{token}/courts/{court_id}/matches/{match_id}/score`｜`/end` per `contracts/scoring-api.md` in `apps/api/tests/contract/test_all_courts_score_endpoint.py`
- [X] T052 [US5] Integration test：全部場地控制板對某場地按 +1 → 該場地自己的 `control_panel_token` 控制板與對應計分板皆同步更新一致 in `apps/api/tests/integration/test_all_courts_score_flow.py`
- [X] T053 [P] [US5] Angular test：`control-panel`/`all-courts-control-panel` 元件模板斷言——無任何 Next Round 觸發入口（SC-004）in `apps/web/src/app/features/control-panel/control-panel.component.spec.ts`

### Implementation for User Story 5

- [X] T054 [US5] Implement `GET /groups/by-all-courts-token/{token}/state` router endpoint（組合團內所有場地之 `court_live_state()`）in `apps/api/app/domains/group/router.py` (depends on T015, T036)
- [X] T055 [US5] Implement `POST /groups/by-all-courts-token/{token}/courts/{court_id}/matches/{match_id}/score` router endpoint in `apps/api/app/domains/group/router.py` (depends on T014)
- [X] T056 [US5] Implement `POST /groups/by-all-courts-token/{token}/courts/{court_id}/matches/{match_id}/end` router endpoint in `apps/api/app/domains/group/router.py` (depends on T026)
- [X] T057 [P] [US5] Angular：擴充 `all-courts-control-panel.component.ts` 串接 `GET .../state` + 逐場地區塊之 +1/-1/提前結束操作 in `apps/web/src/app/features/control-panel/all-courts/all-courts-control-panel.component.ts`
- [X] T058 [P] [US5] `all-courts-control-panel.component.html`：多場地區塊化版面，清楚區隔避免誤按（FR-001）in `apps/web/src/app/features/control-panel/all-courts/all-courts-control-panel.component.html`
- [X] T059 [US5] 擴充 `all-courts-control-panel.component.ts` 串接 `reconnect-refetch.service`（沿用 US4 已建立之共用邏輯）in `apps/web/src/app/features/control-panel/all-courts/all-courts-control-panel.component.ts` (depends on T042, T057)

**Checkpoint**：US1–US5 全部皆可獨立運作。

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**：跨 User Story 的收尾與驗證。

- [X] T060 [P] Integration test：完整生命週期「+1/-1 → 自然達標 → 自動領取下一場 → 針對舊 `match_id` 的延遲請求 no-op → 提前結束下一場 → Round 消耗完畢觸發 Auto Next Round」in `apps/api/tests/integration/test_scoring_lifecycle.py`（constitution 原則 II 之強制整合測試要求）
- [X] T061 [P] 依 `quickstart.md` 全部 6 個情境手動驗證 apps/api 實際運作（含情境 1 之 1 秒內同步人工抽測、情境 5 之斷線重連模擬）
- [X] T062 補齊本 feature 新增之 FastAPI router 端點之 `response_model`/docstring
- [X] T063 [P] Security review：確認 `scoreboard_token` 無法呼叫任何寫入端點（research.md #3）；`match_id`/`court_id` 授權邊界無法被猜測繞過（research.md #4）；管理員端點與公開 token 端點之驗證路徑完全獨立、不共用同一段驗證程式碼（research.md #10）
- [X] T064 [P] Accessibility review：Round 編號與比分之視覺區隔不僅靠字體大小差異，MUST 搭配文字標籤（FR-017，憲章原則 VII）；斷線提示不僅靠顏色變化

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：無任務，略過。
- **Foundational (Phase 2)**：僅 schema 骨架，無外部依賴；**封鎖**所有 User Story。
- **User Stories (Phase 3–7)**：皆依賴 Foundational 完成。
- **Polish (Phase 8)**：依賴所有欲交付的 User Story 完成。

### User Story Dependencies

- **US1（P1，MVP）**：Foundational 完成後即可開始，無其他 Story 相依；建立 `apply_score_delta()`（T014）與 `court_live_state()`（T015）核心邏輯供其餘 Story 共用擴充。
- **US2（P1）**：依循 US1 之 `apply_score_delta()`（T014）已建立的原子防呆/hook-chaining/事件發布模式，新增 `end_match_early()`（T026）——邏輯獨立（不同的狀態轉換路徑），僅重用同一套設計模式，非直接程式碼相依。
- **US3（P1）**：依賴 US1 之 `court_live_state()`（T015）——本 story 為其擴充 `next_up` 欄位（T036），非重新實作。
- **US4（P2）**：依賴 US1 之管理員端點路由基礎（T018、T028 分別建立於 US1/US2）與 US3 之 `peek_next_queued_match()`（T035，供 `build_schedule_snapshot()` 擴充重用）；新增 `reconnect-refetch.service.ts`（T042）供 US5 之全部場地控制板重用。
- **US5（P2）**：依賴 US1 之 `apply_score_delta()`（T014）、`court_live_state()`（T015）、US2 之 `end_match_early()`（T026）、US3 之 `court_live_state()` 擴充版（T036，含 `next_up`）——本 story 僅新增「全部場地」這一層路由聚合與前端多場地版面，核心業務邏輯完全重用；亦依賴 US4 之 `reconnect-refetch.service`（T042）供其元件重用（T059）。
- 建議依 P1→P1→P1→P2→P2 順序（US1→US2→US3→US4→US5）依序實作與驗證。

### Within Each User Story

- Tests MUST 先寫且先失敗，再進行 Implementation。
- Service（含跨模組串接、既有 hook 呼叫）→ Router endpoints（公開 + 管理員版本）→ 前端整合。
- Story 完成（含 Checkpoint 驗證）才進入下一優先序 Story。

### Parallel Opportunities

- Phase 2 之 T001（後端 schema）與 T002（前端 models）可平行執行。
- 同一 User Story 內標記 `[P]` 的 Tests 可平行執行。
- 若有多位開發者：US1 完成後，US2、US3 可平行認領（皆僅依賴 US1 的核心 `apply_score_delta()`/`court_live_state()`，彼此無直接程式碼相依）；US4、US5 建議在 US1–US3 皆完成後再認領（US5 直接依賴 US2/US3 之產出，US4 依賴 US1/US2/US3 之路由與服務函式）。

---

## Parallel Example: User Story 1

```bash
# 平行執行 US1 的所有測試任務：
Task: "Unit test：_match_wins() 達標判定公式 in apps/api/tests/unit/domains/schedule/test_match_wins.py"
Task: "Unit test：apply_score_delta() 已終態拒絕 in apps/api/tests/unit/domains/schedule/test_apply_score_delta.py"
Task: "Unit test：分數下限防呆 in apps/api/tests/unit/domains/schedule/test_apply_score_delta.py"
Task: "Unit test：match_id/court_id 授權邊界 in apps/api/tests/unit/domains/schedule/test_score_authorization.py"
Task: "Unit test：scoreboard_token 拒絕寫入 in apps/api/tests/unit/domains/schedule/test_score_authorization.py"
Task: "Contract test for GET /courts/by-token/{token}/state in apps/api/tests/contract/test_court_state.py"
Task: "Contract test for POST /courts/by-token/{token}/matches/{match_id}/score in apps/api/tests/contract/test_score_endpoint.py"
```

---

## Implementation Strategy

### MVP First（僅 User Story 1）

1. 完成 Phase 2：Foundational（schema 骨架）
2. 完成 Phase 3：User Story 1
3. **停下並驗證**：獨立測試 US1（`quickstart.md` 情境 1、2）
4. 若已可展示，即可部署/demo（「開團 → 加入 → 排點 → 計分」MVP 閉環至此完整）

### Incremental Delivery

1. Foundational 完成 → schema 就緒
2. 加入 US1 → 獨立測試 → Demo（MVP：控制板 +1/-1 + 自動判定勝負完整閉環！）
3. 加入 US2 → 獨立測試 → Demo（提前結束完整）
4. 加入 US3 → 獨立測試 → Demo（計分板公開顯示完整，核心對外呈現價值到位）
5. 加入 US4 → 獨立測試 → Demo（斷線重連保護到位）
6. 加入 US5 → 獨立測試 → Demo（全部場地控制板 + 權限邊界驗證完整）
7. 每個 Story 皆為既有功能疊加價值，不破壞先前 Story

### Parallel Team Strategy

多位開發者情境：

1. 團隊共同完成 Foundational（極輕量，兩項任務）
2. Foundational 完成後：
   - 開發者 A：US1（控制板核心操作，MVP）
   - 開發者 B：待 US1 的 `apply_score_delta()` 就緒後，平行進行 US2（提前結束，重用同一套原子防呆設計模式）
   - 開發者 C：待 US1 的 `court_live_state()` 就緒後，平行進行 US3（計分板顯示）
3. US4（斷線重連）與 US5（全部場地控制板）建議在 US1–US3 皆完成後認領——US5 直接重用 US2/US3 之函式，US4 之 `reconnect-refetch.service` 則被 US5 進一步重用，先後順序有實質相依性

---

## Notes

- `[P]` 任務 = 不同檔案、無相依關係。
- `[Story]` 標籤將任務對應回 spec.md 的特定 User Story，供追溯。
- US2/US3 之核心邏輯與 US1 各自獨立（不同狀態轉換路徑/唯讀查詢），僅重用同一套「原子防呆 + hook-chaining + 事件發布」設計模式，避免誤判為需要重新設計。
- 實作前先確認測試會失敗（TDD，呼應 constitution 原則 II）。
- 建議每完成一項任務或一組邏輯相關任務即 commit 一次。
- 可在任一 Checkpoint 停下獨立驗證該 Story，不需等待後續 Story 完成。
- 避免：模糊任務描述、多任務同時修改同一檔案造成衝突、破壞 Story 獨立性的跨 Story 相依。
