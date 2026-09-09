# Tasks: 比賽加減分紀錄與趨勢圖（Match Score Timeline & Trend Chart）

**Input**: Design documents from `/specs/016-match-score-timeline/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md（皆已存在）

**Tests**: 依 `plan.md` Constitution Check（原則 II）之要求，`get_completed_match_or_404()`/`build_match_record_detail()` 的完整／部分／無三態判斷、兩個新端點各自的授權邊界，皆 MUST 有單元/契約測試；至少一條整合測試涵蓋「打完比賽 → 查看詳情」全流程——本檔案的測試任務為強制項，非選用。

**Organization**：依 spec.md 之 3 個 User Story（US1–US3，優先序 P1/P2/P3）分階段組織。三個 User Story 消費的是**同一個**後端回應形狀（`MatchRecordDetailResponse`）——差別只在前端如何呈現它（US1：逐筆清單；US2：趨勢圖；US3：無/部分紀錄的特殊狀態畫面），因此後端唯讀查詢邏輯與兩個新端點本身歸類為 Foundational（所有 User Story 皆直接依賴、不可再拆分給單一 Story），User Story 階段皆為純前端交付。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行執行（不同檔案、無相依關係）
- **[Story]**: 對應 spec.md 的 US1–US3
- 每項任務皆附精確檔案路徑

## Path Conventions

沿用 `plan.md` Project Structure：`apps/api/`（FastAPI 後端）、`apps/web/`（Angular 20 前端）。monorepo 骨架已由 001 建立，本 feature 無新增 Setup 任務。

---

## Phase 1: Setup

*本 feature 無新增 Setup 任務——monorepo、CI、linting/型別檢查工具鏈已由 001 完整建立並沿用；`score_events` 資料表已於前一階段建立完成（`apps/api/alembic/versions/f3a1c9d4e7b2_score_events_table.py`），本 feature 不需要新的 migration。*

---

## Phase 2: Foundational（Blocking Prerequisites）

**Purpose**：三個 User Story 共用的唯讀查詢邏輯與兩個新 API 端點——任一 User Story 皆無法在此階段完成前開始前端工作。

### Tests for Foundational（先寫、先失敗）

- [X] T001 [P] Unit test：`get_completed_match_or_404()` 對不存在/非 `completed` 狀態的 `match_id` 拋出 `MATCH_NOT_FOUND`；`build_match_record_detail()` 之三態判斷（`events` 為空 → `"none"`；第一筆 `score_a+score_b==1` → `"complete"`；否則 → `"partial"`）與 `elapsed_seconds` 換算正確性（research.md #3）；含兩個邊界案例：(a) 大量 `ScoreEvent`（例如 40+ 筆、含多次來回扣分修正）時 `events` 完整回傳、不截斷（spec.md Edge Case）；(b) 兩筆 `ScoreEvent` 的 `created_at` 刻意設為相同時，排序結果以 `id` 為次要鍵，重複查詢結果一致（research.md #3 排序 tie-breaker）in `apps/api/tests/unit/domains/group/test_match_record_detail.py`
- [X] T002 [P] Contract test for `GET /groups/{group_id}/match-records/{match_id}`（成功回應形狀、`MEMBERSHIP_REQUIRED`、比賽存在但屬於別的團時回傳 `MATCH_NOT_FOUND` 而非 403）per `contracts/match-record-detail-api.md` in `apps/api/tests/contract/test_group_match_record_detail.py`
- [X] T003 [P] Contract test for `GET /members/me/match-records/{match_id}`（成功回應形狀、`MEMBER_TOKEN_INVALID`、`GROUP_MEMBERSHIP_NEVER_HELD`、已退出該團的會員仍可成功查看）per `contracts/match-record-detail-api.md` in `apps/api/tests/contract/test_member_match_record_detail.py`
- [X] T003a [P] Integration test：完整走完一場比賽（透過 `apply_score_delta()` 依序呼叫多次 +1/-1 直到自然達標結束，比照既有 `test_apply_score_delta.py` 的建構方式）後，分別呼叫 `GET /groups/{group_id}/match-records/{match_id}` 與 `GET /members/me/match-records/{match_id}`，驗證兩者皆回傳 `record_completeness == "complete"`，且 `events` 逐筆內容（`side`/`delta`/`score_a`/`score_b`/`elapsed_seconds`）與實際呼叫順序完全一致（plan.md Testing 小節承諾之全流程整合測試）in `apps/api/tests/integration/test_match_score_timeline_flow.py`

### Implementation for Foundational

- [X] T004 [P] 新增 `ScoreEventSummary`／`MatchRecordDetailResponse(MatchRecordSummary)` schemas in `apps/api/app/domains/group/schemas.py`
- [X] T005 實作 `get_completed_match_or_404(session, match_id)`——重用既有 `_completed_matches_query()` 加上 `WHERE id = match_id` in `apps/api/app/domains/group/service.py` (depends on T004)
- [X] T006 實作 `build_match_record_detail(session, match)`——重用既有 `_build_match_record_summaries()` 取得基本資訊，查詢該場比賽的 `ScoreEvent`（依 `created_at` 升冪）換算 `elapsed_seconds` 並判斷 `record_completeness`（research.md #3）in `apps/api/app/domains/group/service.py` (depends on T004, T005)
- [X] T007 實作 `GET /groups/{group_id}/match-records/{match_id}` router 端點——重用既有 `resolve_active_roster_membership()`，比賽存在但 `group_id` 不符時回傳 `MATCH_NOT_FOUND` in `apps/api/app/domains/group/router.py` (depends on T006)
- [X] T008 實作 `GET /members/me/match-records/{match_id}` router 端點——`require_member` 之後重用既有 `verify_ever_group_member(session, match.group_id, member.id)` in `apps/api/app/domains/member/router.py` (depends on T006)
- [X] T009 [P] **實作時修訂（比原規劃更能從根本消除 I1 這類錯誤，見下方説明）**：不新建 `match-record-detail.service.ts`，改為在「團內對戰紀錄分頁」「跨團對戰紀錄」「我的團→歷史」各自現有的三個父層元件已經在用的既有 service 上，各自新增一支對應正確端點的方法——(a) `GroupMemberViewService.getMatchRecordDetail(groupId, matchId)`（重用既有 `guestTokenQuery()`/`authHeader()`，呼叫 `GET /groups/{group_id}/match-records/{match_id}`）in `apps/web/src/app/features/group-member-view/group-member-view.service.ts`；(b) `AuthService.getMatchRecordDetail(matchId)`（呼叫 `GET /members/me/match-records/{match_id}`，供「跨團對戰紀錄」與「我的團→歷史」兩個頁面共用）in `apps/web/src/app/features/auth/auth.service.ts`。`ScoreEventSummary`／`MatchRecordDetailResponse` TypeScript 介面新增於既有 `apps/web/src/app/core/api/group-member-view.models.ts`（`MatchRecordSummary` 所在檔案）。**設計理由**：原規劃是一支「依有無 `groupId` 參數決定呼叫哪個端點」的共用 service（見下方刪除線說明），這種「靠呼叫端傳對參數」的設計正是 I1 那個 bug 的根源——呼叫端必須記得「這個入口不能傳 `groupId`」才不會出錯。現在改成每個入口各自呼叫自己頁面「本來就已經在用」的既有 service（跟該頁清單本身呼叫的是同一個 service），沒有任何分支判斷、沒有可能傳錯的參數，從結構上就不存在誤用的空間，不必再靠警語或迴歸測試補救。~~新增 `match-record-detail.service.ts`——`getMatchRecordDetail({ matchId, groupId? })` 依有無 `groupId` 呼叫對應端點~~（已放棄此設計）in `apps/web/src/app/features/group-member-view/group-member-view.service.ts`、`apps/web/src/app/features/auth/auth.service.ts`、`apps/web/src/app/core/api/group-member-view.models.ts` (depends on T007, T008)

**Checkpoint**：Foundational 完成——兩個新端點皆能正確回傳完整／部分／無三態的 `MatchRecordDetailResponse`，User Story 的前端工作可以開始。

---

## Phase 3: User Story 1 - 點進比賽查看加減分紀錄 (Priority: P1) 🎯 MVP

**Goal**：使用者從任一「對戰紀錄」清單點進一場比賽，看到依時間排序的完整逐筆加減分紀錄（方、加/扣、比分、開賽後經過時間）與基本比賽資訊。

**Independent Test**：任選一場有完整紀錄的已完成比賽，從三個既有清單之一點擊，畫面出現的每一筆加減分紀錄皆與實際發生的操作一致且依時間先後排列。

### Implementation for User Story 1

- [X] T010 [US1] 建立共用元件 `MatchRecordDetailDialogComponent`——**純呈現元件，不注入任何 service、不知道任何端點**：`@Input() detail: MatchRecordDetailResponse | null`、`@Input() loading: boolean`、`@Input() error: boolean`、`@Output() closed`。顯示基本資訊（FR-007：參賽者/輪次/最終比分）與依 `elapsed_seconds` 排序的逐筆紀錄清單 in `apps/web/src/app/core/match-record-detail/match-record-detail-dialog.component.ts` + `.html`（不依賴 T009，可與 T009 平行開發）
- [X] T011 [US1] 團內對戰紀錄分頁：每列新增點擊，呼叫**本頁本來就已經在用**的 `GroupMemberViewService.getMatchRecordDetail(groupId, matchId)`（T009a），將結果餵給 `MatchRecordDetailDialogComponent` 顯示 in `apps/web/src/app/features/group-member-view/match-records/match-records.component.ts` + `.html` (depends on T009, T010)
- [X] T012 [US1] 會員跨團對戰紀錄：每列新增點擊，呼叫**本頁本來就已經在用**的 `AuthService.getMatchRecordDetail(matchId)`（T009b），將結果餵給同一元件 in `apps/web/src/app/features/member/match-history/match-history.component.ts` + `.html` (depends on T009, T010)
- [X] T013 [US1] 我的團歷史頁：每列新增點擊，呼叫**同一支** `AuthService.getMatchRecordDetail(matchId)`（與 T012 完全相同的呼叫——此頁本來就是讓已離開/被踢除的成員也能查看歷史，其清單端點 `GET /members/me/groups/{group_id}/history` 本身用的就是「曾經」語意的 `verify_ever_group_member`；因為 T009 已將「該呼叫哪個端點」的決定收斂成「這個頁面本來在用哪支 service」，這裡不存在誤用團內對戰紀錄分頁專用端點的可能，見 T009 設計理由）in `apps/web/src/app/features/member/my-groups/group-history/group-history.component.ts` + `.html` (depends on T009, T010)
- [X] T014 [P] [US1] 新增逐筆紀錄畫面的 zh-TW i18n 字串（得/失分方標籤、加/扣分文字、「開賽後 {{m}} 分 {{s}} 秒」時間模板)in `apps/web/src/assets/i18n/zh-TW.json`
- [X] T015 [US1] Vitest：給定 `detail` input 為 `record_completeness: "complete"` 的模擬資料，元件依 `elapsed_seconds` 升冪呈現正確筆數與欄位 in `apps/web/src/app/core/match-record-detail/match-record-detail-dialog.component.spec.ts` (depends on T010)
- [X] T015a [P] [US1] Vitest（迴歸防呆，對應 I1 修正後的新設計）：分別驗證三個入口各自呼叫的 service 方法——`match-records.component`（團內對戰紀錄）呼叫 `GroupMemberViewService.getMatchRecordDetail`；`match-history.component`（跨團）與 `group-history.component`（我的團歷史）皆呼叫 `AuthService.getMatchRecordDetail`（而非 `GroupMemberViewService`），即使該列資料本身帶有 `group_id` 欄位 in `apps/web/src/app/features/group-member-view/match-records/match-records.component.spec.ts`、`apps/web/src/app/features/member/match-history/match-history.component.spec.ts`、`apps/web/src/app/features/member/my-groups/group-history/group-history.component.spec.ts` (depends on T011, T012, T013)

**Checkpoint**：US1 完整可運作——三個入口皆可點進去看到完整逐筆加減分紀錄。

---

## Phase 4: User Story 2 - 以趨勢圖檢視比分變化 (Priority: P2)

**Goal**：在同一詳情畫面新增趨勢圖，橫軸為開賽後經過時間，呈現雙方比分變化，扣分時對應曲線下降，兩條曲線不僅靠顏色區分。

**Independent Test**：開啟一場含扣分事件的比賽詳情，圖表終點比分與正式最終比分一致；扣分發生的時間點，對應那一方的曲線呈現下降；兩條曲線可用非顏色的方式（線條樣式/圖例文字）分辨。

### Implementation for User Story 2

- [X] T016 [US2] 新增 computed signal，將 `events` 映射為 A/B 兩隊隨 `elapsed_seconds` 變化的 SVG 座標點 in `apps/web/src/app/core/match-record-detail/match-record-detail-dialog.component.ts` (depends on T010)
- [X] T017 [US2] 新增趨勢圖 SVG 標記——兩條 `<polyline>`（A 實線／B 虛線 `stroke-dasharray`）+ 文字圖例（非純色彩區分，FR-008，憲章原則 VII）in `apps/web/src/app/core/match-record-detail/match-record-detail-dialog.component.html` + `.scss` (depends on T016)
- [X] T018 [P] [US2] Vitest：圖表 computed signal 之終點數值與 `score_a`/`score_b` 一致；`delta = -1` 事件在對應曲線產生下降點 in `apps/web/src/app/core/match-record-detail/match-record-detail-dialog.component.spec.ts` (depends on T016)
- [X] T019 [P] [US2] Vitest + 人工核對：兩條曲線的 `stroke-dasharray`/圖例文字皆存在且不同，確認非僅靠顏色區分（FR-008）in `apps/web/src/app/core/match-record-detail/match-record-detail-dialog.component.spec.ts` (depends on T017)
- [ ] T019a [P] [US2] 人工驗收（對應 SC-005，quickstart.md 情境 2 步驟 3）：找一位未參與開發的人，只給看趨勢圖（不看逐筆文字紀錄），請其回答「哪一方獲勝」與「過程中是否出現扣分修正」，記錄兩題皆答對即通過 (depends on T017)

**Checkpoint**：US1+US2 皆可獨立運作——逐筆紀錄與趨勢圖皆到位。

---

## Phase 5: User Story 3 - 沒有加減分紀錄時的清楚提示 (Priority: P3)

**Goal**：`record_completeness = "none"` 時顯示明確的「無加減分紀錄」提示（不顯示錯誤或空圖表）；`"partial"` 時顯示現有紀錄與圖表，並附上「部分紀錄」提示。

**Independent Test**：開啟一場 `"none"` 的比賽，看到「無加減分紀錄」提示、無圖表、無清單；開啟一場 `"partial"` 的比賽，看到現有逐筆紀錄與圖表，並附上不完整提示。

### Implementation for User Story 3

- [X] T020 [US3] 依 `record_completeness` 分支呈現——`"none"`：顯示空狀態提示，不渲染清單與圖表；`"partial"`：正常渲染清單與圖表，額外顯示不完整提示 banner in `apps/web/src/app/core/match-record-detail/match-record-detail-dialog.component.ts` + `.html` (depends on T010, T017)
- [X] T021 [P] [US3] 新增「無加減分紀錄」／「此為部分紀錄，比賽前段未被記錄」之 zh-TW i18n 字串 in `apps/web/src/assets/i18n/zh-TW.json`
- [X] T022 [P] [US3] Vitest：`"none"` 時不渲染圖表/清單、只顯示提示；`"partial"` 時清單/圖表正常渲染且顯示不完整 banner in `apps/web/src/app/core/match-record-detail/match-record-detail-dialog.component.spec.ts` (depends on T020)
- [X] T023 [US3] Integration test：(a) 完全沒有 `score_events` 的已完成比賽 → 詳情端點回傳 `"none"`；(b) 只保留部分 `score_events`（第一筆非 1:0/0:1）的已完成比賽 → 回傳 `"partial"` in `apps/api/tests/integration/test_match_score_timeline_flow.py` (depends on T006)

**Checkpoint**：US1–US3 全部皆可獨立運作——完整、部分、無紀錄三種狀態皆有對應的清楚呈現。

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**：跨 User Story 的收尾與驗證。

- [ ] T024 [P] 依 `quickstart.md` 全部 5 個情境人工驗證實際運作
- [X] T025 [P] Security review：確認兩個新端點皆重用既有授權判斷式、未新增或放寬任何權限語意；確認 `MATCH_NOT_FOUND` 的統一回傳（比賽不存在/未完成/屬於別團三種情況皆同一錯誤碼）未洩漏額外資訊——已於程式碼審查中確認：`get_completed_match_or_404()`/`resolve_active_roster_membership()`/`verify_ever_group_member()` 皆為既有函式、零修改；`test_group_match_record_detail.py::test_match_from_different_group_returns_match_not_found` 與 `test_incomplete_match_returns_match_not_found` 皆驗證回傳統一的 `MATCH_NOT_FOUND`
- [X] T026 [P] Accessibility review 總結：確認 T019 的雙曲線非色彩區分、`record_completeness` 提示皆圖示/文字並用（憲章原則 VII）——已於程式碼審查中確認：`.trend-chart__line--a`/`--b` 分別為實線/虛線（`stroke-dasharray`）+ 不同 marker 形狀（圓形/方形）+ 文字圖例；`matchRecordDetail.completeness.none`/`.partial` 皆有前綴圖示（🚫/⚠️）而非純色彩背景
- [ ] T027 Performance 抽測：SC-001（一次點擊、SHOULD 3 秒內載入詳情畫面）人工抽測——**尚待人工執行**，需在實際瀏覽器環境中操作

**⚠️ 尚待人工執行的項目**（無法由自動化測試/程式碼審查取代，需要真人操作或判斷）：
- T019a：找一位未參與開發的人只看趨勢圖判斷勝負與扣分修正
- T024：依 `quickstart.md` 全部 5 個情境，在實際啟動的前後端環境中人工操作驗證（本次實作已用等價的自動化契約/整合測試涵蓋相同情境的資料正確性，但情境本身要求「前端畫面呈現」的人工檢視尚未執行）
- T027：SC-001 的 3 秒載入時間人工抽測

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：無任務，略過。
- **Foundational (Phase 2)**：無其他依賴，但 BLOCKS 所有 User Story——三個 Story 消費的是同一個後端回應形狀，未完成 Foundational 前端無資料可呈現。
- **User Stories (Phase 3–5)**：皆依賴 Foundational 完成；US1/US2/US3 在同一元件（`MatchRecordDetailDialogComponent`）上疊加功能，故實務上依優先序循序開發（US1 建立元件骨架 → US2 疊加圖表 → US3 疊加特殊狀態分支），但三者各自的驗收準則彼此獨立，可分別驗證與交付。
- **Polish (Phase 6)**：依賴所有欲交付的 User Story 完成。

### User Story Dependencies

- **US1（P1，MVP）**：依賴 Foundational；建立 `MatchRecordDetailDialogComponent` 骨架與三個入口的點擊事件，是 US2/US3 疊加功能的基礎。
- **US2（P2）**：依賴 Foundational 提供的 `elapsed_seconds`/`score_a`/`score_b` 欄位；在 US1 建立的元件上新增圖表區塊，不修改 US1 已完成的清單呈現邏輯。
- **US3（P3）**：依賴 Foundational 提供的 `record_completeness` 欄位；在 US1（清單）與 US2（圖表）之上新增條件分支，決定何時完全不渲染清單/圖表。

### Within Each Phase

- Tests（Foundational 的 T001–T003、T003a）MUST 先寫且先失敗，再進行 Implementation。
- Schemas → Service → Router endpoints → 前端 service/型別 → 前端元件 → 前端測試。
- 每個 Checkpoint 皆可停下獨立驗證，不需等待後續 Story 完成。

### Parallel Opportunities

- Foundational 的測試任務（T001–T003）可平行執行；T003a 需等 T006（`build_match_record_detail()`）與兩個端點（T007/T008）皆完成才能跑。
- T004（schemas）與後續 T005/T006 之間有相依，但 T009（前端 service）需等 T007/T008 兩個端點皆完成。
- US1 的 T011/T012/T013（三個入口的點擊事件）修改的是三個不同檔案，可平行進行；T015a 需等三者皆完成。
- US2 的 T018/T019/T019a、US3 的 T021/T022 皆可分別平行執行。

---

## Parallel Example: Foundational

```bash
# 平行執行 Foundational 的所有測試任務：
Task: "Unit test：get_completed_match_or_404()/build_match_record_detail() 三態判斷 in apps/api/tests/unit/domains/group/test_match_record_detail.py"
Task: "Contract test for GET /groups/{group_id}/match-records/{match_id} in apps/api/tests/contract/test_group_match_record_detail.py"
Task: "Contract test for GET /members/me/match-records/{match_id} in apps/api/tests/contract/test_member_match_record_detail.py"
```

## Parallel Example: User Story 1

```bash
# 三個入口的點擊事件可平行進行（不同檔案）：
Task: "團內對戰紀錄分頁點擊事件 in apps/web/src/app/features/group-member-view/match-records/"
Task: "會員跨團對戰紀錄點擊事件 in apps/web/src/app/features/member/match-history/"
Task: "我的團歷史頁點擊事件 in apps/web/src/app/features/member/my-groups/group-history/"
```

---

## Implementation Strategy

### MVP First（僅 User Story 1）

1. 完成 Phase 2：Foundational（兩個新端點就緒）
2. 完成 Phase 3：User Story 1
3. **停下並驗證**：獨立測試 US1（`quickstart.md` 情境 1、5）
4. 若已可展示，即可部署/demo（使用者已能點進比賽看到完整逐筆紀錄，即使還沒有圖表）

### Incremental Delivery

1. 完成 Foundational → 後端就緒
2. 加入 US1 → 獨立測試 → Demo（逐筆紀錄清單，MVP！）
3. 加入 US2 → 獨立測試 → Demo（趨勢圖，核心使用者價值閉環到位——「一眼看出趨勢」）
4. 加入 US3 → 獨立測試 → Demo（無/部分紀錄的邊界情境妥善處理）
5. 每個 Story 皆為既有功能疊加價值，不破壞先前 Story

### Parallel Team Strategy

多位開發者情境：

1. 開發者 A：Foundational 後端部分（T001–T008、T003a）
2. 開發者 B：待 T009 就緒後接手 `MatchRecordDetailDialogComponent`（US1 骨架）
3. US2（圖表）與 US3（特殊狀態分支）皆需在 US1 元件骨架（T010）就緒後才能疊加，建議由同一人接續完成，避免同一元件檔案的合併衝突

## Notes

- `[P]` 任務 = 不同檔案、無相依關係。
- `[Story]` 標籤將任務對應回 spec.md 的特定 User Story，供追溯；Foundational 任務無 Story 標籤，因三個 Story 共用同一份後端回應。
- 兩個新端點皆重用既有 `resolve_active_roster_membership()`/`verify_ever_group_member()`，實作時 MUST NOT 修改這兩支既有函式本身。
- **`/speckit-analyze` 修正記錄（I1）**：「會員跨團對戰紀錄」與「我的團→歷史」這兩個入口 MUST 呼叫會員範圍端點（不傳 `groupId`），只有「團內對戰紀錄分頁」該傳 `groupId`——T009/T013/T015a 已加上明確警語與迴歸測試，實作與 code review 時請特別留意，避免重蹈覆轍。
- 實作前先確認測試會失敗（TDD，呼應憲章原則 II）。
- 建議每完成一項任務或一組邏輯相關任務即 commit 一次。
- 可在任一 Checkpoint 停下獨立驗證該 Story，不需等待後續 Story 完成。
- 避免：模糊任務描述、多任務同時修改同一檔案造成衝突、引入圖表第三方套件（research.md #5 已定案沿用手刻 SVG）。
