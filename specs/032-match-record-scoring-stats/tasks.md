# Tasks: 對戰紀錄逐點得失分球員與落點資訊、球員得失分統計

**Input**: Design documents from `/specs/032-match-record-scoring-stats/`

**Prerequisites**: plan.md、spec.md、research.md、data-model.md、contracts/、quickstart.md（皆已存在）

**Tests**：依 `plan.md` Constitution Check（原則 II）之要求，`build_match_record_detail()` 的落點附掛邏輯、球員得失分統計加總邏輯，皆 MUST 有對應單元測試；既有的四個回應形狀契約測試 MUST 至少各更新/擴充一處涵蓋新欄位。本檔案的測試任務為強制項，非選用。

**Organization**：依 spec.md 之 3 個 User Story（US1 P1、US2 P1、US3 P2）分階段組織。US1/US2 共用同一份 Foundational 後端擴充（`ScoreEventSummary.detail`，兩者都需要同一個巢狀物件裡的不同欄位，無法在後端層級拆開，見 research.md Decision 1/2）；US3（球員得失分統計）是完全獨立的第二個回應欄位（`player_stats`），可在 Foundational 完成後獨立於 US1/US2 開發與驗證。三者皆不涉及新端點、新資料表。

## Format: `[ID] [P?] [Story] Description`

- **[P]**：可平行執行（不同檔案、無相依關係）
- **[Story]**：對應 spec.md 的 US1/US2/US3；Setup/Foundational/Polish 階段任務無此標籤
- 每項任務皆附精確檔案路徑

## Path Conventions

沿用 `plan.md` Project Structure：後端 `apps/api/`，前端 `apps/web/src/app/`。

---

## Phase 1: Setup

*本 feature 無新增 Setup 任務——不新增任何第三方依賴、不新增資料庫 migration（plan.md Technical Context）。*

---

## Phase 2: Foundational（Blocking Prerequisites）

**Purpose**：US1 與 US2 共用的後端「落點/球員資訊附掛」與其前端型別定義——任一 User Story 皆無法在此階段完成前開始（US3 的 `player_stats` 雖不直接依賴這裡新增的 `detail` 欄位，但依賴同一段查詢邏輯與同一個測試檔案的 fixture helper，故一併納入 Foundational 以避免重工）。

**⚠️ CRITICAL**：此階段完成前，不可開始任何 User Story 的工作。

- [X] T001 [P] 新增 `ShotPlacementSummary` schema（`scoring_roster_entry_id`/`scoring_nickname`/`losing_roster_entry_id`/`losing_nickname`/`landing_x`/`landing_y`，皆為 `xxx | None`）於 `apps/api/app/domains/group/schemas.py`（緊鄰既有 `ScoreEventSummary`）
- [X] T002 新增 `ScoreEventSummary.detail: ShotPlacementSummary | None = None` 欄位於 `apps/api/app/domains/group/schemas.py`（depends on T001）
- [X] T003 新增測試 fixture helper `_add_shot_placement(session, event, *, roster_entry_id=None, losing_roster_entry_id=None, landing_x=None, landing_y=None, team)`（比照既有 `_add_event()` 的既有寫法，`team` 對應 `ShotPlacementRecord.team`，永遠有值）於 `apps/api/tests/unit/domains/group/test_match_record_detail.py`
- [X] T004 [P] Unit test：擴充後的 `build_match_record_detail()`，針對一筆有完整記錄（`roster_entry_id`+`losing_roster_entry_id`+`landing_x`/`landing_y` 皆有值）的加分事件，回傳的 `ScoreEventSummary.detail` 四個子欄位皆正確對應（暱稱正確查出）in `apps/api/tests/unit/domains/group/test_match_record_detail.py`（depends on T002, T003）
- [X] T005 [P] Unit test：`build_match_record_detail()` 對「完全沒有對應 `ShotPlacementRecord`」與「對應資料列存在但四個欄位全部是 `NULL`」兩種情況，回傳的 `detail` 皆為 `None`（research.md Decision 2）；對 `delta=-1` 的扣分事件，`detail` 恆為 `None` in `apps/api/tests/unit/domains/group/test_match_record_detail.py`（depends on T002, T003）
- [X] T006 [P] Unit test：`build_match_record_detail()` 對「只記錄得分球員、未記錄落點」與「只記錄落點、未記錄任一球員」兩種部分記錄情況，`detail` 非 `None`，但個別未記錄的子欄位各自為 `None` in `apps/api/tests/unit/domains/group/test_match_record_detail.py`（depends on T002, T003）
- [X] T007 擴充 `build_match_record_detail()`：在既有查詢 `ScoreEvent` 之後，新增一次查詢該場比賽全部 `ShotPlacementRecord`（`WHERE match_id = :match_id`），依 `roster_entry_id`/`losing_roster_entry_id` 收集需要查詢暱稱的 id 集合並一次查出（比照 `_build_match_record_summaries()` 既有「先查 id 集合、再一次查暱稱」模式），依 `score_event_id` 建立索引；組裝每筆 `ScoreEventSummary` 時，依 research.md Decision 2 規則決定 `detail`（四個欄位全空或無對應資料列 → `None`）in `apps/api/app/domains/group/service.py`（depends on T001, T002；使 T004、T005、T006 通過）
- [X] T008 [P] 新增 `ShotPlacementDetail` interface（camelCase 欄位，見 data-model.md）於 `apps/web/src/app/core/api/group-member-view.models.ts`，並新增 `ScoreEventSummary.detail: ShotPlacementDetail | null` 欄位
- [X] T009 [P] Contract test：`GET /groups/{group_id}/match-records/{match_id}` 回應中，有記錄落點/球員的加分事件其 `detail` 欄位正確回傳，沒有記錄的事件 `detail` 為 `null` in `apps/api/tests/contract/test_group_match_record_detail.py`（depends on T007）
- [X] T010 [P] Contract test：同 T009，改用 `GET /members/me/match-records/{match_id}` 驗證（確認擴充自動套用到會員視角端點，不需個別修改）in `apps/api/tests/contract/test_member_match_record_detail.py`（depends on T007）

**Checkpoint**：Foundational 完成——`MatchRecordDetailResponse.events[].detail` 已能正確反映每一筆加分事件當時記錄的球員/落點資訊，四個既有端點皆已受惠；前端已有對應的 TypeScript 型別可用，但畫面尚未呈現任何新資訊。

---

## Phase 3: User Story 1 - 逐點紀錄顯示得失分球員 (Priority: P1) 🎯 MVP

**Goal**：比賽詳情彈窗的逐點紀錄清單中，已記錄得分/失分球員的加分事件旁顯示對應暱稱徽章；沒有記錄的維持原樣。

**Independent Test**：以 Foundational 完成的後端回應為輸入（不需要真的操作計分畫面，直接以 fixture 資料驅動元件測試），開啟比賽詳情彈窗，確認有 `detail.scoring_nickname`/`detail.losing_nickname` 的事件旁顯示對應暱稱，沒有的事件維持原本樣式。

### Tests for User Story 1（先寫、先失敗）⚠️

- [X] T011 [P] [US1] Component test：`MatchRecordDetailDialogComponent` 對一筆 `detail` 同時有 `scoring_nickname`/`losing_nickname` 的事件，顯示兩個球員暱稱徽章；對一筆只有 `scoring_nickname`（`losing_nickname` 為 `null`）的事件，只顯示一個徽章；對一筆 `detail` 為 `null` 的事件，不顯示任何徽章 in `apps/web/src/app/core/match-record-detail/match-record-detail-dialog.component.spec.ts`

### Implementation for User Story 1

- [X] T012 [US1] 在逐點紀錄的每一列（`.event-row`）新增條件式球員暱稱徽章：`detail?.scoring_nickname`/`detail?.losing_nickname` 個別存在時才顯示對應徽章（沿用既有 `<app-nickname>` 元件呈現暱稱，比照本檔案頂部 `team_a`/`team_b` 名單的既有寫法）in `apps/web/src/app/core/match-record-detail/match-record-detail-dialog.component.html`（depends on T008；使 T011 通過）
- [X] T013 [P] [US1] 新增本階段顯示文字（得分球員/失分球員徽章的標籤或 `aria-label`）至 `matchRecordDetail.eventList` 既有命名空間 in `apps/web/src/assets/i18n/zh-TW.json` + `en.json`

**Checkpoint**：US1 完整可運作——四個既有對戰紀錄入口皆能在逐點紀錄旁看到已記錄的得分/失分球員。

---

## Phase 4: User Story 2 - 點擊查看該分的羽球落點 (Priority: P1)

**Goal**：點擊已顯示球員資訊的加分紀錄，在同一個比賽詳情對話框內、該筆紀錄下方原地展開球場示意圖與落點標記（或「未記錄落點」提示）；同時間至多一筆展開（Clarifications 2026-09-16）。

**Independent Test**：對一筆 `detail` 非 `null` 的事件點擊，確認原地展開球場示意圖並正確標示 `landing_x`/`landing_y`（或當兩者為 `null` 時顯示「未記錄落點」）；再點擊同一筆確認收合；點擊另一筆確認切換展開對象且同時間只有一筆展開；對 `detail` 為 `null` 的事件點擊確認沒有任何反應。

### Tests for User Story 2（先寫、先失敗）⚠️

- [X] T014 [P] [US2] Unit test：新元件 `CourtDiagramComponent` 在傳入 `landingX`/`landingY` 皆非 `null` 時，於正確的相對位置渲染落點標記；傳入皆為 `null` 時不渲染任何標記；`isSinglesMatch=true` 時渲染兩條 `.out-of-play-band`，`false` 時不渲染 in `apps/web/src/app/core/court-diagram/court-diagram.component.spec.ts`（新檔案）
- [X] T015 [P] [US2] Component test：`MatchRecordDetailDialogComponent` 的展開/收合行為——點擊有 `detail` 的事件列原地展開球場示意圖；再次點擊同一列收合；點擊另一筆有 `detail` 的事件列時，原本展開的列收合、新點擊的列展開（同時間至多一筆）；點擊 `detail` 為 `null` 的事件列沒有任何展開效果 in `apps/web/src/app/core/match-record-detail/match-record-detail-dialog.component.spec.ts`
- [X] T016 [P] [US2] Component test：展開一筆 `detail` 非 `null`、但 `landing_x`/`landing_y` 皆為 `null` 的事件，展開區塊顯示「未記錄落點」而非球場示意圖上的標記 in `apps/web/src/app/core/match-record-detail/match-record-detail-dialog.component.spec.ts`

### Implementation for User Story 2

- [X] T017 [US2] 新增共用唯讀元件 `CourtDiagramComponent`（standalone）：從 `shot-placement-picker.component.html`/`.scss` 抽出純視覺的 `.court`/`.out-of-play-band`/`.landing-marker` 區塊（research.md Decision 5），`input` 為 `isSinglesMatch: boolean`、`landingX: number | null`、`landingY: number | null`，純渲染、無任何 pointer 事件 in `apps/web/src/app/core/court-diagram/court-diagram.component.ts` + `.html` + `.scss`（使 T014 通過）
- [X] T018 [US2] 重構 `ShotPlacementPickerComponent`：`.court` 內容改用新的 `<app-court-diagram>`（傳入既有的 `isSinglesMatch()`/`selectedPoint()` 對應值），`.court-area` 外層的 pointer 事件處理邏輯不變；`@Component({ imports: [...] })` 新增 `CourtDiagramComponent`；確認既有 `shot-placement-picker.component.spec.ts` 測試全數維持通過（回歸保護，不新增測試案例）in `apps/web/src/app/features/shot-placement/shot-placement-picker.component.ts` + `.html` + `.scss`（depends on T017）
- [X] T019 [US2] 在 `MatchRecordDetailDialogComponent` 新增 `expandedEventIndex = signal<number | null>(null)` 與 `toggleExpand(index: number)` 方法（點擊已展開的索引則設回 `null`，否則設為新索引，天然達成「同時間至多一筆」與「切換」行為）；`detail()` input 變更時（開啟不同比賽）重置為 `null` in `apps/web/src/app/core/match-record-detail/match-record-detail-dialog.component.ts`（使 T015 通過）
- [X] T020 [US2] 在逐點紀錄的每一列新增點擊行為（僅當 `event.detail` 非 `null` 時可點擊，比照既有 `role="button"`/`tabindex`/`keydown.enter` 無障礙慣例），並在該列下方原地展開一個區塊：`landing_x`/`landing_y` 皆非 `null` 時顯示 `<app-court-diagram>` 並標示落點，皆為 `null` 時顯示「未記錄落點」提示；`@Component({ imports: [...] })` 新增 `CourtDiagramComponent` in `apps/web/src/app/core/match-record-detail/match-record-detail-dialog.component.ts` + `.html`（depends on T017, T019；使 T016 通過）
- [X] T021 [P] [US2] 新增本階段顯示文字（「未記錄落點」提示、展開/收合的 `aria-label`）至 `matchRecordDetail.eventList` 既有命名空間 in `apps/web/src/assets/i18n/zh-TW.json` + `en.json`

**Checkpoint**：US1 與 US2 皆完整可運作——逐點紀錄可展開查看落點，球場示意圖邏輯與計分當下畫面共用同一元件。

---

## Phase 5: User Story 3 - 整場比賽的球員得失分統計 (Priority: P2)

**Goal**：比賽詳情畫面新增「球員得失分統計」，列出雙方全部參賽者的得分/造成失分次數；完全沒有資料時顯示明確提示。

**Independent Test**：對一場有多筆記錄球員的比賽，確認回應的 `player_stats` 正確加總且包含全部參賽者（含 0 次的球員）；對完全沒有記錄的比賽，確認 `player_stats` 為空陣列且畫面顯示無資料提示而非全零統計表。

### Tests for User Story 3（先寫、先失敗）⚠️

- [X] T022 [P] [US3] Unit test：`build_match_record_detail()` 對多筆各自記錄不同球員組合的加分事件（含只記錄得分球員、只記錄失分球員、兩者皆記錄三種情況混合），`player_stats` 中每位球員的 `scored_count`/`fault_count` 分別正確加總，且完全沒有被記錄過的參賽者也出現在陣列中並為 `0`（不得省略）in `apps/api/tests/unit/domains/group/test_match_record_detail.py`（depends on T007）
- [X] T023 [P] [US3] Unit test：`build_match_record_detail()` 對完全沒有任何一筆 `ShotPlacementRecord`（或有資料列但全部欄位皆 `NULL`）的比賽，`player_stats` 回傳空陣列 in `apps/api/tests/unit/domains/group/test_match_record_detail.py`（depends on T007）
- [X] T024 [P] [US3] Component test：`MatchRecordDetailDialogComponent` 的球員得失分統計區塊——`player_stats` 非空時，依序渲染每位球員的暱稱、`scored_count`、`fault_count`；`player_stats` 為空陣列時，顯示「此比賽沒有球員得失分紀錄」提示，不渲染任何統計列 in `apps/web/src/app/core/match-record-detail/match-record-detail-dialog.component.spec.ts`

### Implementation for User Story 3

- [X] T025 [US3] 新增 `PlayerScoringStat` schema（`roster_entry_id`/`nickname`/`team`/`scored_count`/`fault_count`）於 `apps/api/app/domains/group/schemas.py`，並新增 `MatchRecordDetailResponse.player_stats: list[PlayerScoringStat] = []` 欄位
- [X] T026 [US3] 擴充 `build_match_record_detail()`：對 T007 已查出的同一批 `ShotPlacementRecord`，依 `roster_entry_id`（非 `NULL`）與 `losing_roster_entry_id`（非 `NULL`）分別分組計數；若兩者合計為空則 `player_stats = []`，否則依這場比賽既有 `team_a + team_b` 名單組出每位球員的 `PlayerScoringStat`（缺項預設 0，research.md Decision 3/4）in `apps/api/app/domains/group/service.py`（depends on T025；使 T022、T023 通過）
- [X] T027 [P] [US3] 新增 `PlayerScoringStat` interface（camelCase 欄位）於 `apps/web/src/app/core/api/group-member-view.models.ts`，並新增 `MatchRecordDetailResponse.player_stats: PlayerScoringStat[]` 欄位
- [X] T028 [US3] 在 `MatchRecordDetailDialogComponent` 模板新增「球員得失分統計」區塊：`player_stats` 非空時渲染統計表（依隊伍分組，`team_a` 全部球員在前、`team_b` 在後，比照既有 `team_a`/`team_b` 排序慣例），空陣列時顯示無資料提示 in `apps/web/src/app/core/match-record-detail/match-record-detail-dialog.component.html`（depends on T027；使 T024 通過）
- [X] T029 [P] [US3] 新增本階段顯示文字（統計區塊標題、欄位標籤、無資料提示）至新的 `matchRecordDetail.playerStats` 命名空間 in `apps/web/src/assets/i18n/zh-TW.json` + `en.json`
- [X] T030 [P] [US3] Contract test：`GET /groups/{group_id}/match-records/{match_id}` 回應中 `player_stats` 欄位正確反映（非空/空陣列兩種情況各一）in `apps/api/tests/contract/test_group_match_record_detail.py`（depends on T026）

**Checkpoint**：三個 User Story 皆完整可運作——對戰紀錄詳情同時具備逐點球員資訊、可展開的落點檢視、整場球員得失分統計。

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**：涵蓋四個既有入口一致性、既有回歸測試、與 quickstart.md 驗證。

- [X] T031 [P] Integration test：對應 quickstart.md 情境 6/9——依序寫入多筆不同記錄組合的加分事件後，分別以團對戰紀錄、會員個人跨團對戰紀錄兩個既有入口查詢同一場比賽，確認 `events[].detail` 與 `player_stats` 內容完全一致 in `apps/api/tests/integration/test_match_score_timeline_flow.py`
- [X] T032 執行 `uv run ruff check app tests`、`uv run mypy app`（後端）與 `npx ng lint`、`npx tsc -p tsconfig.app.json --noEmit`（前端），確認全數通過（Constitution I）
- [X] T033 執行完整後端測試套件（`uv run pytest -q`，確認無其他 pytest 行程同時執行）與完整前端測試套件（`npx ng test --watch=false`），確認全數通過且無既有測試回歸（尤其 `shot-placement-picker.component.spec.ts`，因 T018 重構了其內部 DOM 結構）
- [X] T034 依 quickstart.md 全部 9 個情境手動或以自動化腳本逐一驗證

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：無任務，略過。
- **Foundational (Phase 2)**：無前置依賴，可立即開始——BLOCKS 全部三個 User Story。
- **User Story 1 (Phase 3)**：依賴 Foundational 完成（需要 `detail` 欄位）。
- **User Story 2 (Phase 4)**：依賴 Foundational 完成（需要 `detail.landing_x`/`landing_y`）；與 US1 共用同一個模板檔案（`match-record-detail-dialog.component.html`），實務上建議 US1 先完成、US2 接續在同一批修改上疊加，但兩者的驗收條件彼此獨立，US2 不依賴 US1 的球員徽章是否已經顯示。
- **User Story 3 (Phase 5)**：依賴 Foundational 完成（重用同一批已查出的 `ShotPlacementRecord`），完全獨立於 US1/US2（不同的回應欄位 `player_stats`、模板中不同的獨立區塊），可與 US1/US2 平行開發。
- **Polish (Phase 6)**：依賴全部三個 User Story 完成。

### Within Each User Story

- 測試先寫、先確認失敗，再進行對應實作。
- Schema/型別定義先於服務層邏輯，服務層邏輯先於前端模板改動。

### Parallel Opportunities

- Foundational 中 T001、T008 可平行；T004/T005/T006 三個測試函式可平行寫（皆在同一檔案但互不相依，落地時個別確認各自失敗即可）；T009/T010 兩個既有契約測試檔案可平行擴充。
- US1（Phase 3）與 US3（Phase 5）可完全平行進行（不同回應欄位、模板中不同區塊）。
- US2（Phase 4）的 T014（`CourtDiagramComponent` 測試）可與 US1/US3 的任務平行，但 T017～T020 需依序完成（元件抽出 → 既有元件重構 → 對話框狀態 → 對話框模板）。

---

## Parallel Example: Foundational

```bash
Task: "新增 ShotPlacementSummary schema in apps/api/app/domains/group/schemas.py"
Task: "新增 ShotPlacementDetail interface in apps/web/src/app/core/api/group-member-view.models.ts"
```

## Parallel Example: User Story 1 與 User Story 3 同時進行

```bash
# 開發者 A：US1
Task: "Component test：球員暱稱徽章顯示條件"
Task: "逐點紀錄列新增球員暱稱徽章"

# 開發者 B：US3（不衝突，不同回應欄位與模板區塊）
Task: "Unit test：player_stats 加總邏輯"
Task: "擴充 build_match_record_detail() 計算 player_stats"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. 完成 Phase 2：Foundational
2. 完成 Phase 3：User Story 1（逐點球員徽章）
3. **停下並驗證**：獨立測試 US1
4. 視需要部署/展示

### Incremental Delivery

1. Foundational 完成 → 基礎就緒（後端已能附掛 detail，前端已有型別）
2. 加入 US1（球員徽章）→ 獨立測試 → 部署/展示（MVP）
3. 加入 US2（展開看落點，含共用球場元件抽出）→ 獨立測試 → 部署/展示
4. 加入 US3（球員得失分統計）→ 獨立測試 → 部署/展示
5. 每個 User Story 皆在不破壞前一個的前提下獨立增加價值

---

## Notes

- [P] 任務 = 不同檔案、無相依關係
- [Story] 標籤對應 spec.md 的特定 User Story，便於追溯
- 每個 User Story 皆應可獨立完成與獨立測試
- 實作前先確認測試會失敗
- 依使用者慣例，僅在使用者明確要求時才建立 git commit
- 在任一 Checkpoint 皆可停下獨立驗證該 User Story
- 避免：模糊的任務描述、同檔案衝突、破壞 User Story 獨立性的跨故事相依
