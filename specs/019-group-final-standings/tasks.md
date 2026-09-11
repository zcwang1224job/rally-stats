# Tasks: 我的團最終團隊排名

**Input**: Design documents from `/specs/019-group-final-standings/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md（皆已存在）

**Tests**: 依 `plan.md` Constitution Check（原則 II）之要求，排序/並列名次跳號演算法、涵蓋範圍（含離團/訪客/同會員合併）、`is_self` 計算屬於使用者可觀察的核心呈現邏輯，MUST 有單元/契約/整合測試覆蓋；本檔案的測試任務為強制項，非選用。

**Organization**：依 spec.md 之 3 個 User Story（US1–US3，優先序 P1/P2/P3）分階段組織。三者共用**同一支**後端排名函式 `build_group_final_standings()`（涵蓋範圍、排序、`is_self`、空狀態皆是同一份查詢/彙總邏輯的不同面向，無法乾淨拆成互不相干的程式碼變更），因此核心實作歸類為 Foundational；US1（MVP，已解散團的完整呈現）在此之上疊加前端渲染；US2（尚未解散團也顯示同一份快照）與 US3（尚無比賽紀錄的清楚提示）皆是 Foundational＋US1 已經涵蓋的行為，只需要端到端驗證，不需要額外程式碼。

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

**Purpose**：US1（完整呈現）、US2（任一團狀態皆顯示）、US3（空狀態提示）共用的核心排名函式與擴充後的回應形狀——任一 User Story 皆無法在此階段完成前開始獨立驗證。

### Tests for Foundational（先寫、先失敗）

- [X] T001 [P] Unit test：新函式 `build_group_final_standings()` 的涵蓋範圍與排序邏輯——(a) 涵蓋現役／已離開／已被踢除的所有參與者（不限現役，FR-002）；(b) 涵蓋訪客參與者（`member_id IS NULL`），且不額外標示與一般參與者不同（FR-002，research.md #3）；(c) 同一位會員在同一團有多筆歷史 `RosterEntry`（先退出後又重新加入）MUST 合併為一列，`total_matches`/`total_wins`/`total_losses` 為其全部參與期間的加總（research.md #1，spec.md Edge Cases）；(d) 依 `total_wins` 由高到低排序，並列時 `rank` 顯示同一數字且緊接其後的名次依人數跳號（standard competition ranking），並列時的內部順序依（合併後最早的）`joined_at`（research.md #1/#2）；(e) 已捨棄（abandoned）的比賽 MUST NOT 計入任何人的 `total_matches`/`total_wins`/`total_losses`（FR-003）；(f) `scheduling_mechanism == "fixed_partner"` 的團，同一場比賽的兩位搭檔 MUST 各自獨立累計自己的勝敗，MUST NOT 以搭檔組合合併計算（FR-009）；(g) 尚未有任何已完成比賽的參與者 MUST 仍出現在清單中，`total_matches` 為 `0`；(h) 傳入 `viewer_member_id` 對應的那一組（含合併後任一筆 `RosterEntry`）`is_self` MUST 為 `true`，其餘為 `false`（research.md #4）in `apps/api/tests/unit/domains/group/test_group_final_standings.py`
- [X] T002 [P] Contract test：`GET /members/me/groups/{group_id}/history` 擴充後的回應形狀——新增 `final_standings` 陣列，每個項目皆含 `roster_entry_id`/`nickname`/`current_status`/`is_self`/`rank`/`total_matches`/`total_wins`/`total_losses`（型別正確）；既有 `group_id`/`group_name`/`my_stats`/`matches`/`page`/`total_pages` 欄位與既有回應行為完全一致（回歸測試，比照 `specs/014-member-groups-history/contracts/member-groups-history-api.md`）per `contracts/final-standings-api.md` in `apps/api/tests/contract/test_member_groups_history_endpoints.py`

### Implementation for Foundational

- [X] T003 [P] 抽出共用純函式 `_assign_standard_competition_ranks(total_wins_in_order: list[int]) -> list[int]`（data-model.md），並將既有 `build_group_standings()` 內嵌的排序/並列名次迴圈改為呼叫此函式——純重構，MUST NOT 改變既有回應行為（既有 `test_group_standings_ranking.py` 需維持全數通過）in `apps/api/app/domains/group/service.py`
- [X] T004 [P] 新增 `FinalStandingRow` schema（`roster_entry_id: str`／`nickname: str`／`current_status: Literal["active","left","kicked"]`／`is_self: bool`／`rank: int`／`total_matches: int`／`total_wins: int`／`total_losses: int`，data-model.md）in `apps/api/app/domains/group/schemas.py`
- [X] T005 實作 `build_group_final_standings(session, group_id, *, viewer_member_id) -> list[FinalStandingRow]`——查詢該團所有 `RosterEntry`（不過濾 `status`、不過濾 `member_id`）；依 `member_id` 分組合併（`member_id` 為 `NULL` 的訪客各自獨立成組）；每組彙總 `_completed_matches_query()` join `MatchParticipant` 得出的 `total_matches`/`total_wins`/`total_losses`；依 `total_wins` 排序後呼叫 T003 的共用函式取得 `rank`；計算 `is_self`（research.md #1/#4）in `apps/api/app/domains/group/service.py` (depends on T001, T002, T003, T004)
- [X] T006 [P] `MemberGroupHistoryResponse` 新增 `final_standings: list[FinalStandingRow]` 欄位（data-model.md）in `apps/api/app/domains/member/schemas.py`
- [X] T007 `get_member_group_history()` 呼叫 `build_group_final_standings(session, group_id, viewer_member_id=member_id)`，組進回應的 `final_standings`——MUST NOT 受既有 `nickname` 查詢參數影響（FR-001）in `apps/api/app/domains/member/service.py` (depends on T005, T006)
- [X] T008 [P] 新增 `FinalStandingRow` TypeScript 介面（與後端欄位一致）in `apps/web/src/app/core/api/group-member-view.models.ts`
- [X] T009 `MemberGroupHistoryResponse` TypeScript 介面新增 `final_standings: FinalStandingRow[]` 欄位並 import `FinalStandingRow` in `apps/web/src/app/core/api/friend.models.ts` (depends on T008)

**Checkpoint**：Foundational 完成——涵蓋範圍、排序、並列名次、合併同一會員多筆紀錄、`is_self`、擴充後的回應形狀皆已在後端就緒，前端型別同步完成，User Story 的獨立驗證與前端渲染工作可以開始。

---

## Phase 3: User Story 1 - 在「我的團」查看已解散團的最終團隊排名 (Priority: P1) 🎯 MVP

**Goal**：會員從「我的團」點進一個已解散的團，能看到全團所有曾參與者（含已離開/被踢除）依戰績排序的最終名次，包含自己排在第幾名。

**Independent Test**：依 `quickstart.md` 情境 1、3、4——(a) 已解散團的完整涵蓋範圍與排序、自己標示；(b) 訪客與同一會員多次加入的合併呈現；(c) 已捨棄比賽不計入、固定搭檔以個人為單位。

### Implementation for User Story 1

- [X] T010 [US1] Integration test：已解散的團，`final_standings` 依序列出現役/已離開/已被踢除的參與者並正確排序、跳號，查看者自己那一列 `is_self` 為 `true`（quickstart.md 情境 1）；訪客參與者正常出現且無特殊標記，同一位會員先退出又重新加入只出現一列且戰績為兩次加入期間的加總（quickstart.md 情境 3）；一場比賽被標記為 `abandoned` MUST NOT 計入任何人的戰績，且 `scheduling_mechanism == "fixed_partner"` 的團中同場搭檔各自獨立累計勝敗、不合併為搭檔組合（quickstart.md 情境 4，整合層級驗證 T001(e)/(f) 之單元邏輯，FR-003/FR-009）；對同一份不變的資料連續呼叫端點三次，`final_standings` 的 `rank`／排列順序 100% 一致，不隨機跳動（quickstart.md 情境 1 步驟 5，FR-005/SC-005）in `apps/api/tests/integration/test_member_groups_history_flow.py` (depends on T007)
- [X] T011 [US1] 新增 i18n 字串：`groupMemberView.standings.status.kicked`（比照既有 `status.left` 圖示＋文字慣例）、最終團隊排名區塊標題與整體空狀態提示（`member.matchHistory.finalStandingsTitle`／`member.matchHistory.finalStandings.empty`，research.md #6）in `apps/web/src/assets/i18n/zh-TW.json`
- [X] T012 [US1] `group-history.component.ts`：新增「該列是否尚無比賽紀錄」判斷（`total_matches === 0`，FR-007）與「整個團是否完全沒有已完成比賽」判斷（`final_standings` 每一列皆 `total_matches === 0`，FR-008）——自己所在列直接渲染後端算好的 `is_self`，MUST NOT 自行比對任何 ID（research.md #4）in `apps/web/src/app/features/member/my-groups/group-history/group-history.component.ts` (depends on T009)
- [X] T013 [US1] `group-history.component.html`：新增「最終團隊排名」區塊（表格：名次／暱稱／已離開或已被踢除標籤／總戰績或「尚無比賽紀錄」），自己所在列 MUST 以圖示/文字＋視覺樣式標示（非純顏色，FR-011）；完全無比賽時顯示整體「尚無比賽紀錄」提示（FR-008）——與既有「我的戰績」「對戰紀錄」兩區塊並存，不取代既有內容（FR-001）in `apps/web/src/app/features/member/my-groups/group-history/group-history.component.html` (depends on T012, T011)
- [X] T014 [P] [US1] `group-history.component.scss`：新增最終團隊排名表格、自己所在列、已離開/已被踢除標籤之樣式 in `apps/web/src/app/features/member/my-groups/group-history/group-history.component.scss`
- [X] T015 [US1] Vitest：`final_standings` 依 `rank` 排序渲染；自己所在列（`is_self`）有圖示/文字＋樣式標示；已離開/已被踢除標籤正確顯示；`total_matches === 0` 的列顯示「尚無比賽紀錄」而非「0 勝 0 敗」in `apps/web/src/app/features/member/my-groups/group-history/group-history.component.spec.ts` (depends on T013, T014)

**Checkpoint**：US1 完整可運作——已解散團的最終團隊排名正確呈現，MVP。

---

## Phase 4: User Story 2 - 尚在進行中的團也能在「我的團」預覽同一份排名 (Priority: P2)

**Goal**：尚未解散的團，同樣能在「我的團」歷史頁面看到同一份最終團隊排名區塊，反映點擊當下的累計快照。

**Independent Test**：依 `quickstart.md` 情境 2——尚未解散、已有部分比賽完成的團，點進去驗證同樣能看到最終團隊排名區塊。

### Implementation for User Story 2

- [X] T016 [US2] Integration test：尚未解散、已有部分比賽完成的團，`final_standings` 同樣正確回傳並反映呼叫當下的累計排名（quickstart.md 情境 2）——本階段不需要額外的後端/前端實作，純粹驗證 Foundational（T005/T007）與 US1（T012/T013）已經對任一團狀態（`active`/`disbanded`）一視同仁地呈現（FR-012），不需要為「團是否已解散」寫任何條件分支 in `apps/api/tests/integration/test_member_groups_history_flow.py` (depends on T007)

**Checkpoint**：US1+US2 皆可獨立運作——「已解散團看得到最終結果」與「任一團狀態都在同一個地方看得到」兩層價值疊加。

---

## Phase 5: User Story 3 - 尚無比賽紀錄時的清楚提示 (Priority: P3)

**Goal**：確認完全沒有已完成比賽的團、或部分參與者尚無比賽紀錄時，最終團隊排名區塊以清楚文字呈現，不會誤判或顯示錯誤/空白畫面。

**Independent Test**：依 `quickstart.md` 情境 5——完全沒有已完成比賽的團，驗證整體顯示「尚無比賽紀錄」提示；混合情境驗證部分參與者個別顯示同樣文字而不被排除或誤判為並列最後一名。

### Implementation for User Story 3

- [X] T017 [US3] Integration test：完全沒有已完成比賽的團，`final_standings` 陣列 MUST 包含所有曾參與者、每列 `total_matches`/`total_wins`/`total_losses` 皆為 `0`（quickstart.md 情境 5）；一個團部分成員已打過比賽、部分完全沒打過，尚無記錄者 MUST 仍出現在清單中且不被誤判為並列最後一名（spec.md Edge Cases）in `apps/api/tests/integration/test_member_groups_history_flow.py` (depends on T007) — 本階段不需要額外的後端實作，純粹驗證 Foundational（T005）的彙總邏輯已正確涵蓋零場次情境。
- [X] T018 [US3] Vitest：驗證 T013 已實作的「尚無比賽紀錄」文字（單列）與整體空狀態提示（全團皆零場次）正確渲染，不顯示錯誤或空白畫面 in `apps/web/src/app/features/member/my-groups/group-history/group-history.component.spec.ts` (depends on T013) — 本階段不需要額外的前端實作。

**Checkpoint**：US1–US3 全部皆可獨立運作——完整呈現、任一團狀態、空狀態提示彼此互不干擾。

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**：跨 User Story 的收尾與驗證。

- [X] T019 [P] 依 `quickstart.md` 全部 5 個情境人工驗證實際運作
- [X] T020 [P] Security review：確認 `GET /members/me/groups/{group_id}/history` 沿用既有 `verify_ever_group_member`，存取層級未因本次擴充而改變（FR-010）；確認 `final_standings` 未洩漏任何 `member_id` 或其他非既有必要的內部識別碼（`is_self` 由伺服器算好，回應本身不附帶原始 `member_id`，research.md #4）
- [X] T021 [P] Accessibility review：確認 T013 的自己所在列與已離開/已被踢除標籤符合憲章原則 VII（非純顏色，圖示/文字並用）
- [X] T022 補齊 `GET /members/me/groups/{group_id}/history` 之 `response_model`/docstring 完整性——既有 docstring 只引用 014-member-groups-history 的 FR，補上對 019 新增 FR（FR-001~FR-012）的引用（憲章原則 II 之強制項）in `apps/api/app/domains/member/router.py`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：無任務，略過。
- **Foundational (Phase 2)**：無其他依賴，但 BLOCKS 所有 User Story——US1 的渲染依賴擴充後的回應形狀與前端型別，US2/US3 的驗證直接針對 Foundational（T005）的彙總邏輯。
- **User Stories (Phase 3–5)**：皆依賴 Foundational 完成；US1 依賴 Foundational 提供的 `final_standings` 欄位與前端型別；US2、US3 依賴 Foundational 與 US1 的渲染邏輯（因為兩者驗證的是「同一份呈現在不同情境下的正確性」，不需要額外程式碼），可在 US1 完成後立即開始。
- **Polish (Phase 6)**：依賴所有欲交付的 User Story 完成。

### User Story Dependencies

- **US1（P1，MVP）**：依賴 Foundational（T001–T009）。
- **US2（P2）**：依賴 Foundational 與 US1（T012/T013 的渲染邏輯本身就是「任一團狀態皆顯示」，US2 只是驗證這一點，不新增程式碼）。
- **US3（P3）**：依賴 Foundational（T005 的零場次彙總邏輯）與 US1（T013 的空狀態文字渲染），同樣只需要驗證。

### Within Each Phase

- Tests（Foundational 的 T001–T002；US1 的 T010；US2 的 T016；US3 的 T017–T018）MUST 先寫且先失敗，再進行對應 Implementation（US2/US3 本身無新增 Implementation，測試即驗證既有邏輯）。
- schema → service 函式 → 前端型別 → 前端元件 → 前端測試。
- 每個 Checkpoint 皆可停下獨立驗證，不需等待後續 Story 完成。

### Parallel Opportunities

- Foundational 的兩個測試任務（T001–T002）可平行執行；T003（共用排名函式重構）、T004（schema）彼此無相依，可與測試任務平行進行；T008（前端型別）可與後端任務平行進行。
- US1 的 T014（樣式）、T011（i18n）可與 T012/T013（元件邏輯/樣板）平行進行。

---

## Parallel Example: Foundational

```bash
# 平行執行 Foundational 的測試與 schema/重構任務：
Task: "Unit test：build_group_final_standings() 涵蓋範圍/排序/合併/is_self 邏輯 in apps/api/tests/unit/domains/group/test_group_final_standings.py"
Task: "Contract test for GET /members/me/groups/{group_id}/history 擴充欄位 in apps/api/tests/contract/test_member_groups_history_endpoints.py"
Task: "抽出共用 _assign_standard_competition_ranks() 並重構 build_group_standings() in apps/api/app/domains/group/service.py"
Task: "新增 FinalStandingRow schema in apps/api/app/domains/group/schemas.py"
```

## Parallel Example: User Story 1

```bash
# US1 的樣式與 i18n 任務可平行執行：
Task: "group-history.component.scss：最終團隊排名表格與自己所在列樣式 in apps/web/src/app/features/member/my-groups/group-history/group-history.component.scss"
Task: "新增最終團隊排名相關 zh-TW i18n 字串 in apps/web/src/assets/i18n/zh-TW.json"
```

---

## Implementation Strategy

### MVP First（僅 User Story 1）

1. 完成 Phase 2：Foundational（後端涵蓋範圍/排序/合併/`is_self` 邏輯就緒，前端型別同步）
2. 完成 Phase 3：User Story 1
3. **停下並驗證**：獨立測試 US1（`quickstart.md` 情境 1、3、4）
4. 若已可展示，即可部署/demo（會員從「我的團」點進已解散的團就能看到最終團隊排名）

### Incremental Delivery

1. 完成 Foundational → 後端與前端型別就緒
2. 加入 US1 → 獨立測試 → Demo（已解散團看得到最終排名，MVP！）
3. 加入 US2 → 獨立測試 → Demo（任一團狀態都在同一個地方看得到）
4. 加入 US3 → 獨立測試 → Demo（空狀態提示正確，通常不需要額外程式碼）
5. 每個 Story 皆為既有功能疊加價值，不破壞先前 Story

### Parallel Team Strategy

多位開發者情境：

1. 開發者 A：Foundational 後端部分（T001–T007）
2. 開發者 B：待 T005/T008 完成後接手 Foundational 前端型別（T009）與 US1 前端（T011–T015）
3. 開發者 C：待 Foundational 完成後接手 US2（T016）、US3（T017–T018）之驗證測試，與開發者 B 的 US1 前端工作平行進行

## Notes

- `[P]` 任務 = 不同檔案、無相依關係。
- `[Story]` 標籤將任務對應回 spec.md 的特定 User Story，供追溯；Foundational 任務無 Story 標籤，因 US1–US3 共用同一支後端排名函式。
- 排序/並列名次/涵蓋範圍/`is_self` 計算 MUST 只在後端 `build_group_final_standings()` 完成一次，前端 MUST NOT 自行重新排序、重新計算名次，或自行比對任何 ID 判斷「是不是我自己」（憲章原則 X，research.md #2/#4）——實作與 code review 時請特別留意。
- 實作前先確認測試會失敗（TDD，呼應憲章原則 II）。
- 建議每完成一項任務或一組邏輯相關任務即 commit 一次。
- 可在任一 Checkpoint 停下獨立驗證該 Story，不需等待後續 Story 完成。
- 避免：模糊任務描述、多任務同時修改同一檔案造成衝突、在前端重新實作排序或並列名次演算法（那會產生與後端不一致的風險，違反 research.md #2 的決策）、在回應中額外暴露 `member_id` 等非必要的內部識別碼。
