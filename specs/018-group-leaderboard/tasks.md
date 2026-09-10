# Tasks: 團內即時排行榜（強化既有戰績頁）

**Input**: Design documents from `/specs/018-group-leaderboard/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md（皆已存在）

**Tests**: 依 `plan.md` Constitution Check（原則 II）之要求，排序/並列名次跳號演算法與離團成員排除邏輯屬於使用者可觀察的核心呈現邏輯，MUST 有單元/契約/整合測試覆蓋；本檔案的測試任務為強制項，非選用。

**Organization**：依 spec.md 之 3 個 User Story（US1–US3，優先序 P1/P2/P3）分階段組織。US1（排序清單呈現）與 US3（並列名次/穩定排序）共用**同一支**後端排序演算法（`build_group_standings()` 擴充後的排序＋並列跳號邏輯），演算法本身無法乾淨拆成兩個各自獨立的程式碼變更，因此歸類為 Foundational；US1 階段只需要在既有前端元件上疊加渲染邏輯即可獨立驗證，US3 階段則是針對 Foundational 已經實作好的並列邏輯做端到端驗證，不需要額外新程式碼。US2（即時更新）是獨立疊加的一層，依賴 Foundational 但不依賴 US1 的前端渲染細節，可平行開發。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行執行（不同檔案、無相依關係）
- **[Story]**: 對應 spec.md 的 US1–US3
- 每項任務皆附精確檔案路徑

## Path Conventions

沿用 `plan.md` Project Structure：`apps/api/`（FastAPI 後端）、`apps/web/`（Angular 20 前端）。monorepo 骨架已由 001 建立，本 feature 無新增 Setup 任務。

---

## Phase 1: Setup

*本 feature 無新增 Setup 任務——monorepo、CI、linting/型別檢查工具鏈已由 001 完整建立並沿用；不新增資料表，不需要新的 migration（research.md 前言）。*

---

## Phase 2: Foundational（Blocking Prerequisites）

**Purpose**：US1（排序呈現）與 US3（並列名次）共用的核心排序演算法，以及 US2（即時更新）需要的擴充後回應形狀——任一 User Story 皆無法在此階段完成前開始獨立驗證。

### Tests for Foundational（先寫、先失敗）

- [X] T001 [P] Unit test：`build_group_standings()` 擴充後的排序/並列/離團排除邏輯——(a) 依 `total_wins` 由高到低排序；(b) 並列時 `rank` 顯示同一數字，且緊接其後的名次依人數跳號（standard competition ranking，research.md #6）；(c) 並列時的內部排序依 `joined_at`（早加入者排前面，research.md #2）；(d) 已離開/被踢除的成員 MUST NOT 出現在 `members` 清單中，但其對戰貢獻 MUST 仍正確累計進現役對手的 `total_wins`/`total_losses`（research.md #3）；(e) 尚未有任何已完成比賽的現役成員 MUST 仍出現在清單中，`total_wins`/`total_losses` 皆為 `0`；(f) `scheduling_mechanism == "fixed_partner"` 的團，同一場比賽的兩位搭檔 MUST 各自獨立累計自己的 `total_wins`/`total_losses`，MUST NOT 以搭檔組合合併計算（FR-009）in `apps/api/tests/unit/domains/group/test_group_standings_ranking.py`
- [X] T002 [P] Contract test for `GET /groups/{group_id}/standings` 擴充後的回應形狀——`members` 每個項目皆含 `rank`/`total_wins`/`total_losses`（型別正確）；既有 `rounds`/`current_round_number` 欄位與既有回應行為完全一致（回歸測試）per `contracts/standings-api.md` in `apps/api/tests/contract/test_group_standings_ranking_endpoint.py`

### Implementation for Foundational

- [X] T003 [P] 擴充 `MemberStandingRow` schema，新增 `rank: int`／`total_wins: int`／`total_losses: int` 欄位 in `apps/api/app/domains/group/schemas.py`
- [X] T004 擴充 `build_group_standings()`——查詢條件新增 `RosterEntry.status == "active"` 過濾（data-model.md）；組裝回應前新增「加總 `total_wins`/`total_losses` → 依 `total_wins` 排序 → 算出並列名次（次要依 `joined_at`）」的後處理步驟 in `apps/api/app/domains/group/service.py` (depends on T001, T002, T003)
- [X] T005 [P] 前端 `MemberStandingRow` TypeScript 介面同步新增 `rank`／`total_wins`／`total_losses` in `apps/web/src/app/core/api/group-member-view.models.ts`

**Checkpoint**：Foundational 完成——排序、並列名次、離團排除、擴充後的回應形狀皆已在後端就緒，User Story 的獨立驗證與前端工作可以開始。

---

## Phase 3: User Story 1 - 檢視團內排行榜 (Priority: P1) 🎯 MVP

**Goal**：團內任一現役成員打開既有的「戰績」頁面，能看到依名次排序的完整清單，看得到自己排第幾名、贏了幾場、輸了幾場。

**Independent Test**：依 `quickstart.md` 情境 1、4——(a) 一般排序＋並列/尚無紀錄的呈現；(b) 離團成員被排除但對手戰績不受影響。兩者皆不需要即時更新即可獨立驗證。

### Implementation for User Story 1

- [X] T006 [US1] Integration test：(a) 一般排序情境——多位成員不同勝場數，驗證回應 `members` 依 `rank` 排序且離團成員不出現（quickstart.md 情境 1）；(b) 離團成員被排除，但過去對戰貢獻仍正確累計進現役對手的戰績（quickstart.md 情境 4）in `apps/api/tests/integration/test_standings_realtime_flow.py` (depends on T004)
- [X] T007 [US1] `standings.component.ts`：新增「判斷目前使用者是否為某一列的本人」邏輯（比對登入會員/訪客的 `roster_entry_id`）；新增「該成員本輪是否有任何已完成比賽」判斷（`total_wins + total_losses === 0` 時視為「尚無比賽紀錄」，FR-007）in `apps/web/src/app/features/group-member-view/standings/standings.component.ts` (depends on T005)
- [X] T008 [US1] `standings.component.html`：新增 `rank` 欄位渲染（例如「第 N 名」，並列時顯示相同數字）；自己所在列 MUST 以圖示/文字＋視覺樣式標示（非純顏色，FR-011）；`total_wins`/`total_losses` 皆為 0 的成員顯示「尚無比賽紀錄」文字而非「0 勝 0 敗」in `apps/web/src/app/features/group-member-view/standings/standings.component.html` (depends on T007)
- [X] T009 [P] [US1] `standings.component.scss`：新增 `rank` 欄位樣式、自己所在列的視覺標示樣式 in `apps/web/src/app/features/group-member-view/standings/standings.component.scss`
- [X] T010 [P] [US1] 新增「尚無比賽紀錄」、自己所在列標示文字之 zh-TW i18n 字串 in `apps/web/src/assets/i18n/zh-TW.json`
- [X] T011 [US1] Vitest：`members` 依 `rank` 排序渲染於畫面；自己所在列有圖示/文字＋樣式標示（非僅靠顏色可區分，人工/程式判斷皆可驗證）；`total_wins`/`total_losses` 皆為 0 的列正確顯示「尚無比賽紀錄」而非「0 勝 0 敗」in `apps/web/src/app/features/group-member-view/standings/standings.component.spec.ts` (depends on T008, T009, T010)

**Checkpoint**：US1 完整可運作——戰績頁顯示正確排序名次，管理員與一般成員皆可獨立驗證，MVP。

---

## Phase 4: User Story 2 - 比賽進行中即時更新排名 (Priority: P2)

**Goal**：比賽被判定完成後，正在檢視戰績頁的使用者在數秒內自動看到更新後的名次，不需要手動重新整理；離線期間錯過更新的使用者，重新連線/回到畫面時也能自動拿到正確狀態。

**Independent Test**：依 `quickstart.md` 情境 2、5——(a) 比賽完成後另一分頁在 2 秒內自動更新；(b) 斷線重連後自動拿到正確名次，且畫面上沒有任何「連線中斷」提示元件。

### Implementation for User Story 2

- [X] T012 [P] [US2] Integration test：`apply_score_delta()` 使比賽狀態轉為 `completed` 時，`_publish_match_ended()` MUST 額外對 `group_notifications_channel(group_id)` 發布 `standings.updated` 事件（payload 僅含 `group_id`，contracts/ably-events.md）；`end_match_early()`（捨棄路徑）MUST NOT 觸發此事件；一般 `apply_score_delta()`（+1/-1）但比分尚未達到致勝條件、比賽仍為 `in_progress` 時，MUST NOT 觸發此事件（FR-003 後半——比分變動中不重算排名）in `apps/api/tests/integration/test_standings_realtime_flow.py` (depends on T004)
- [X] T013 [US2] 擴充 `_publish_match_ended()`，新增對 `group_notifications_channel(group_id)` 發布 `standings.updated` 事件 in `apps/api/app/domains/schedule/service.py` (depends on T012)
- [X] T014 [US2] `standings.component.ts`：注入既有 `RealtimeService`，訂閱 `group_notifications_channel(groupId)` 頻道的 `standings.updated` 事件，收到後重新呼叫 `getStandings()`；注入既有 `ReconnectRefetchService`，訂閱 `onReconnect()`，比照相同重新拉取邏輯；元件銷毀時取消訂閱（沿用 `RealtimeService.subscribe()` 既有 teardown 行為）；MUST NOT 新增任何「連線中斷」提示元件（FR-012）in `apps/web/src/app/features/group-member-view/standings/standings.component.ts` (depends on T007, T013)
- [X] T015 [US2] Vitest：收到 `standings.updated` 事件後正確重新呼叫 `getStandings()`；`onReconnect()` 觸發後同樣重新呼叫；元件銷毀時訂閱被正確取消 in `apps/web/src/app/features/group-member-view/standings/standings.component.spec.ts` (depends on T014)

**Checkpoint**：US1+US2 皆可獨立運作——「看得到排名」與「排名一定是最新的」兩層價值逐步疊加。

---

## Phase 5: User Story 3 - 並列名次與穩定排序 (Priority: P3)

**Goal**：確認兩位以上成員戰績完全相同時，戰績頁以並列＋跳號的方式呈現名次，且多次重新整理或即時更新後，這些人彼此的顯示順序保持穩定。

**Independent Test**：依 `quickstart.md` 情境 3——建構戰績完全相同的測試資料，驗證 `rank` 並列且跳號、多次呼叫結果順序一致。

### Implementation for User Story 3

- [X] T016 [US3] Integration test：兩位以上現役成員 `total_wins` 完全相同時，`rank` MUST 顯示同一數字，且緊接其後的名次 MUST 依人數跳號（例如兩人並列第 2 名，下一位是第 4 名）；同一份資料連續呼叫 `GET /groups/{group_id}/standings` 三次，`members` 陣列順序與 `rank` 100% 一致（quickstart.md 情境 3）in `apps/api/tests/integration/test_standings_realtime_flow.py` (depends on T004) — 本階段不需要額外的後端/前端實作，純粹驗證 Foundational（T004）的排序演算法已經正確涵蓋此情境（US1 的前端渲染已經直接顯示 `rank` 欄位，無需為並列情況另寫渲染邏輯）。

**Checkpoint**：US1–US3 全部皆可獨立運作——排序呈現、即時更新、並列穩定性彼此互不干擾。

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**：跨 User Story 的收尾與驗證。

- [X] T017 [P] 依 `quickstart.md` 全部 6 個情境人工驗證實際運作
- [X] T018 [P] Security review：確認 `GET /groups/{group_id}/standings` 沿用既有 `resolve_active_roster_membership`，存取層級未因本次擴充而改變（FR-010）；確認新增的 `rank`/`total_wins`/`total_losses` 欄位未洩漏任何非現役成員或團外成員的資訊
- [X] T019 [P] Accessibility review：確認 T008/T009 的自己所在列標示符合憲章原則 VII（非純顏色，圖示/文字並用）
- [X] T020 補齊 `GET /groups/{group_id}/standings` 之 `response_model`/docstring 完整性——既有 docstring 只引用 005-member-view 的 FR-005~010，補上對 018 新增 FR（FR-001~FR-012）的引用（憲章原則 II 之強制項）in `apps/api/app/domains/group/router.py`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：無任務，略過。
- **Foundational (Phase 2)**：無其他依賴，但 BLOCKS 所有 User Story——US1 的渲染依賴擴充後的回應形狀，US2 的即時更新依賴同一支 `build_group_standings()` 產生的最新結果，US3 的並列驗證直接針對 Foundational 的排序演算法。
- **User Stories (Phase 3–5)**：皆依賴 Foundational 完成；US1 依賴 Foundational 提供的排序/欄位；US2 依賴 Foundational（確保「重新拉取」拿到的資料已經是排序好的）但不依賴 US1 的前端渲染細節，可平行開發；US3 依賴 Foundational，可在 Foundational 完成後立即開始，不需要等 US1/US2。
- **Polish (Phase 6)**：依賴所有欲交付的 User Story 完成。

### User Story Dependencies

- **US1（P1，MVP）**：依賴 Foundational（T001–T005）。
- **US2（P2）**：依賴 Foundational 提供的擴充後端點；前端訂閱邏輯需要 T007（本人列判斷）已存在的元件基礎，故排在 US1 的 T007 之後，但不依賴 T008–T011 的渲染細節。
- **US3（P3）**：依賴 Foundational（T004）之排序演算法；不依賴 US1/US2 的任何實作。

### Within Each Phase

- Tests（Foundational 的 T001–T002；US1 的 T006；US2 的 T012；US3 的 T016）MUST 先寫且先失敗，再進行對應 Implementation。
- schema → service 函式 → 前端型別 → 前端元件 → 前端測試。
- 每個 Checkpoint 皆可停下獨立驗證，不需等待後續 Story 完成。

### Parallel Opportunities

- Foundational 的兩個測試任務（T001–T002）可平行執行；T003（schema）與 T001/T002 互不相依，可平行。
- US1 的 T009（樣式）、T010（i18n）可與 T007/T008（元件邏輯/樣板）平行進行。
- US2 的 T012（後端測試）可與 US1 的前端任務平行開發（皆依賴 Foundational，彼此不相依）。

---

## Parallel Example: Foundational

```bash
# 平行執行 Foundational 的測試與 schema 任務：
Task: "Unit test：build_group_standings() 排序/並列/離團排除邏輯 in apps/api/tests/unit/domains/group/test_group_standings_ranking.py"
Task: "Contract test for GET /groups/{group_id}/standings 擴充欄位 in apps/api/tests/contract/test_group_standings_ranking_endpoint.py"
Task: "擴充 MemberStandingRow schema in apps/api/app/domains/group/schemas.py"
```

## Parallel Example: User Story 1

```bash
# US1 的樣式與 i18n 任務可平行執行：
Task: "standings.component.scss：rank 欄位與自己所在列樣式 in apps/web/src/app/features/group-member-view/standings/standings.component.scss"
Task: "新增戰績頁相關 zh-TW i18n 字串 in apps/web/src/assets/i18n/zh-TW.json"
```

---

## Implementation Strategy

### MVP First（僅 User Story 1）

1. 完成 Phase 2：Foundational（後端排序/並列/離團排除邏輯就緒）
2. 完成 Phase 3：User Story 1
3. **停下並驗證**：獨立測試 US1（`quickstart.md` 情境 1、4）
4. 若已可展示，即可部署/demo（管理員與一般成員打開戰績頁就能看到排序後的名次）

### Incremental Delivery

1. 完成 Foundational → 後端就緒
2. 加入 US1 → 獨立測試 → Demo（看得到排名，MVP！）
3. 加入 US2 → 獨立測試 → Demo（排名一定是最新的，即時更新）
4. 加入 US3 → 獨立測試 → Demo（確認並列/穩定排序皆正確，通常不需要額外程式碼）
5. 每個 Story 皆為既有功能疊加價值，不破壞先前 Story

### Parallel Team Strategy

多位開發者情境：

1. 開發者 A：Foundational（T001–T005）與 US3（T016，同一支排序邏輯的延伸驗證）
2. 開發者 B：待 Foundational 完成後接手 US1 前端（T006–T011）
3. 開發者 C：待 Foundational 完成後接手 US2（T012–T015），後端/前端皆可獨立於 US1 的渲染細節進行

## Notes

- `[P]` 任務 = 不同檔案、無相依關係。
- `[Story]` 標籤將任務對應回 spec.md 的特定 User Story，供追溯；Foundational 任務無 Story 標籤，因 US1/US3 共用同一支後端排序函式。
- 排序/並列名次計算 MUST 只在後端 `build_group_standings()` 完成一次，前端 MUST NOT 自行重新排序或重新計算名次（憲章原則 X，research.md #2）——實作與 code review 時請特別留意。
- 實作前先確認測試會失敗（TDD，呼應憲章原則 II）。
- 建議每完成一項任務或一組邏輯相關任務即 commit 一次。
- 可在任一 Checkpoint 停下獨立驗證該 Story，不需等待後續 Story 完成。
- 避免：模糊任務描述、多任務同時修改同一檔案造成衝突、在前端重新實作並列名次跳號演算法（那會產生與後端不一致的風險，違反 research.md #2/#6 的決策）。
