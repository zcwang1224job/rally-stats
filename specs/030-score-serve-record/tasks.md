# Tasks: 加分時記錄發球者與站位資訊

**Input**: Design documents from `/specs/030-score-serve-record/`

**Prerequisites**: plan.md、spec.md、research.md、data-model.md、contracts/no-new-endpoints.md、quickstart.md（皆已存在）

**Tests**: 依 `plan.md` Constitution Check（原則 II）之要求，發球權轉換規則、站位公式邊界、`-1` 排除邏輯皆 MUST 有單元測試；至少一條整合測試涵蓋「開賽 → 連續加分（含 side-out）→ 查詢紀錄」全流程——本檔案的測試任務為強制項，非選用。

**Organization**：依 spec.md 之 2 個 User Story（US1 P1、US2 P2）分階段組織。兩者共用同一份底層演算法與資料模型（`Match` 新欄位、`ScoreServeRecord`、站位公式、發球狀態初始化），這些歸類為 Foundational；US1 交付「加分即時建立正確紀錄」，US2 在 US1 之上驗證「多筆歷史紀錄彼此獨立、不被覆蓋」——US2 依賴 US1 已存在（沒有紀錄就無從驗證「紀錄不被覆蓋」），但兩者仍可分別獨立測試與驗收。

## Format: `[ID] [P?] [Story] Description`

- **[P]**：可平行執行（不同檔案、無相依關係）
- **[Story]**：對應 spec.md 的 US1/US2；Setup/Foundational/Polish 階段任務無此標籤
- 每項任務皆附精確檔案路徑

## Path Conventions

沿用 `plan.md` Project Structure：本 feature 純後端（`apps/api/`），不觸碰 `apps/web/`。

---

## Phase 1: Setup

*本 feature 無新增 Setup 任務——monorepo、CI、lint/型別檢查工具鏈已由既有專案建立並沿用；不新增任何第三方依賴。*

---

## Phase 2: Foundational（Blocking Prerequisites）

**Purpose**：兩個 User Story 共用的資料模型、發球狀態初始化與站位公式——任一 User Story 皆無法在此階段完成前開始。

**⚠️ CRITICAL**：此階段完成前，不可開始任何 User Story 的工作。

### Tests for Foundational（先寫、先失敗）

- [X] T001 [P] Unit tests：純函式 `_compute_station()`（單打/雙打、比分奇偶邊界——0、偶數、奇數，驗證單打恰有一個站位欄位非 `None`、雙打四個皆非 `None`，per data-model.md 驗證規則）與 `_initialize_serve_state()`（隨機性——多次呼叫下，發球隊伍、雙打時雙方隊伍各自的 `reference_server` 皆可能是該隊任一位球員，non-deterministic 驗證方式比照專案既有隨機性測試慣例）in `apps/api/tests/unit/domains/schedule/test_serve_state.py`

### Implementation for Foundational

- [X] T002 新增 `Match.serving_team`／`team_a_reference_server_id`／`team_b_reference_server_id` 三個 nullable 欄位，以及新的 `ScoreServeRecord` model（`score_event_id` UNIQUE FK、`match_id` FK+index、`group_id` FK+index——比照既有 `ScoreEvent` 對 `match_id`／`group_id` 雙欄皆 denormalize 的慣例，不只做一半——`server_roster_entry_id`、`server_team`、四個站位欄位、`created_at`），欄位定義與 nullable/FK/cascade 規則完全依 `data-model.md` in `apps/api/app/domains/schedule/models.py`
- [X] T003 產生並手動核對 Alembic migration（`alembic revision --autogenerate -m "score_serve_records"`）：`ALTER TABLE matches ADD COLUMN`（3 欄位）+ `CREATE TABLE score_serve_records`（`score_event_id` 唯一索引、`match_id`／`group_id` 各一般索引）in `apps/api/alembic/versions/<new_rev>_score_serve_records.py` (depends on T002)
- [X] T004 實作純函式 `_compute_station(serving_team, team_a_reference_server_id, team_b_reference_server_id, score_a, score_b)`，回傳發球者 + 四個站位，規則依 `research.md` Decision 3 的站位公式 in `apps/api/app/domains/schedule/service.py` (depends on T002；使 T001 之站位公式測試通過)
- [X] T005 實作 `_initialize_serve_state(session, match)`：查詢該場比賽的 `MatchParticipant`（A/B 兩隊），隨機指定 `serving_team`，並（雙打時）分別為兩隊隨機指定各自的 `reference_server`（單打時該隊唯一參賽者即為 `reference_server`），寫回 `match` 物件的三個新欄位，規則依 `research.md` Decision 4/5（發球隊伍與接發球隊伍皆隨機）in `apps/api/app/domains/schedule/service.py` (depends on T002；使 T001 之初始化測試通過)
- [X] T006 於 `create_match_with_participants()` 內，`status == "in_progress"` 時（`flush()` 取得 `match.id` 之後）呼叫 `_initialize_serve_state()` in `apps/api/app/domains/schedule/service.py` (depends on T005)
- [X] T007 於 `pull_queued_match_for_court()` 內，`match.status = "in_progress"` 賦值之後呼叫 `_initialize_serve_state()` in `apps/api/app/domains/schedule/service.py` (depends on T005)
- [X] T008 [P] Integration test：分別透過 T006、T007 兩個掛鉤點各自建立一場 `in_progress` 比賽（單打各一場、雙打各一場），查詢 `matches`，確認三個發球狀態欄位皆已初始化（非 `NULL`；單打的 `team_X_reference_server_id` 為該隊唯一參賽者）；並查詢 `score_serve_records`（篩選這些剛建立的 `match_id`），確認在尚未發生任何加分之前筆數為 0（FR-007：沒有加分動作就不會有紀錄）in `apps/api/tests/integration/test_score_serve_record_flow.py` (depends on T006, T007)

**Checkpoint**：Foundational 完成——比賽一轉為進行中即擁有正確初始化的發球狀態，但尚未有任何「加分即記錄」的使用者可見行為。

---

## Phase 3: User Story 1 - 加分當下自動留下發球者與站位紀錄 (Priority: P1) 🎯 MVP

**Goal**：比賽進行中每次加分（`+1`）時，系統自動建立一筆對應的 `ScoreServeRecord`；使用「`-1`」修正比分時 MUST NOT 建立。

**Independent Test**：對一場正在進行中、已知目前發球者與站位的比賽加一分，查詢這次得分事件，確認除了比分本身之外，還能查到「誰發球」與「雙方站位」；對同一場比賽呼叫 `-1`，確認沒有新增任何一筆對應紀錄。

### Tests for User Story 1（先寫、先失敗）

- [X] T009 [P] [US1] Unit test：發球權轉換規則——得分方＝目前 `serving_team` 時，`serving_team`／兩個 `reference_server` 皆不變；得分方≠目前 `serving_team`（side-out）時，`serving_team` 改為得分方，該隊（雙打）`reference_server` 換成另一位隊員，另一隊不變（`research.md` Decision 2）in `apps/api/tests/unit/domains/schedule/test_serve_state.py`
- [X] T010 [P] [US1] 既有檔案擴充：`apply_score_delta()` 的 `delta=1` 呼叫後，`score_serve_records` 新增一筆內容正確（`server_roster_entry_id`／`server_team`／四個站位欄位皆與呼叫前的發球狀態+比分一致）的紀錄；`delta=-1` 呼叫後，`score_serve_records` 筆數不變、`matches` 三個發球狀態欄位不變（FR-004）in `apps/api/tests/unit/domains/schedule/test_apply_score_delta.py`

### Implementation for User Story 1

- [X] T011 [US1] 實作 `_advance_serve_state_and_snapshot(session, match, side)`：依 T009 的轉換規則更新 `match` 的三個發球狀態欄位，呼叫 T004 之 `_compute_station()` 算出目前站位，組出（但不寫入）對應的 `ScoreServeRecord` 物件 in `apps/api/app/domains/schedule/service.py` (depends on T004, T005；使 T009 通過)
- [X] T012 [US1] 於 `apply_score_delta()` 的 `delta > 0` 分支——既有 `session.add(ScoreEvent(...))` 之後、`await session.commit()` 之前——呼叫 `_advance_serve_state_and_snapshot()`，將回傳的 `ScoreServeRecord`（`score_event_id` 指向剛建立的 `ScoreEvent`）一併 `session.add()`，於同一交易內寫入；`delta < 0` 分支維持現狀、不呼叫此函式 in `apps/api/app/domains/schedule/service.py` (depends on T011；使 T010 通過)

**Checkpoint**：US1 完整可運作——加分即時建立正確的發球者/站位紀錄，`-1` 不建立、不影響發球狀態。

---

## Phase 4: User Story 2 - 每一分的紀錄各自獨立、不被後續動作覆蓋 (Priority: P2)

**Goal**：比賽持續進行、比分不斷變動時，每一分當初留下的發球者/站位紀錄維持原樣，不會被後續的加分或修正覆蓋或改寫。

**Independent Test**：對一場比賽連續加多分（含至少一次 side-out），檢查最早那一分的發球者/站位紀錄是否仍保留當時的原始內容，而不是被之後的分數覆蓋成最新狀態；依序查詢累積的多筆紀錄，確認各自對應到當時正確的發球者與站位。

*本 Story 不需要 Foundational/US1 之外的新產品程式碼——「紀錄不被覆蓋」是 T002/T012 的資料模型設計（每次加分皆為新的 `INSERT`，程式碼中不存在任何對既有 `ScoreServeRecord` 的 `UPDATE`）的直接結果，本階段純粹是針對這個保證的驗證測試。*

### Tests for User Story 2

- [X] T013 [US2] Integration test：對一場比賽依序呼叫加分——(1) 目前發球隊繼續得一分、(2) 對方得分造成 side-out、(3) 新發球方再得一分——查詢該比賽全部 `score_serve_records`（依 `created_at` 排序），驗證三筆紀錄彼此不同、各自對應呼叫當下正確的發球者與站位，且第 (1) 筆在 (2)(3) 發生後仍保持原始內容不變 in `apps/api/tests/integration/test_score_serve_record_flow.py` (depends on T012)
- [X] T014 [P] [US2] Integration test：在 T013 的序列中途插入一次 `-1`，驗證 `score_serve_records` 筆數與插入前完全相同（沒有新增）、既有各筆內容未被改動，且 `matches` 三個發球狀態欄位維持 `-1` 之前的值 in `apps/api/tests/integration/test_score_serve_record_flow.py` (depends on T012)

**Checkpoint**：US1、US2 皆可獨立驗證——單筆記錄正確（US1）+ 多筆記錄彼此獨立、正確排序、不受 `-1` 干擾（US2）。

---

## Phase 5: Polish & Cross-Cutting Concerns

- [X] T015 [P] `ruff check app/ tests/` 與 `mypy app/` 全數通過（新增/修改的 `models.py`／`service.py`／migration 檔）——實際執行結果：兩者皆 0 錯誤（`mypy` 依專案既有慣例僅檢查 `app/`，不含 `tests/`）。
- [X] T016 對照 `quickstart.md` 的 6 個驗證情境（含 T019 新增的情境 6），逐一確認已由 T008/T013/T014/T019 等測試涵蓋，若有遺漏則補上對應測試——核對結果：情境 1→T008（Foundational）；情境 2/3→T013 + 對應單元測試；情境 4→T014 + 對應單元測試；情境 5→`test_serve_state.py` 之 `_compute_station` 單打案例 + `test_initialize_serve_state_singles_...`；情境 6→T019。六個情境皆有對應測試，無遺漏。
- [X] T017 執行完整既有 `apps/api` 測試套件（`pytest tests/`），確認本 feature 未破壞任何既有測試（`test_court_state.py`、`test_score_endpoint.py`、`test_scoring_flow.py`、`test_court_lifecycle.py` 等既有契約/整合測試）——實際執行結果：1040 passed（本 feature 新增前為 1025 passed），0 failed。
- [X] T018 [P] SC-003 驗證（人工／程式碼審查，非阻塞式量測，比照既有 016 feature 對其效能目標的驗收慣例）：審查 T012 的實作，確認新增的 `ScoreServeRecord` 寫入與既有 `ScoreEvent` 寫入共用同一次資料庫交易、沒有新增任何額外的網路往返或外部呼叫；於 PR 描述或本任務的完成註記中記錄審查結論——審查結論：`apply_score_delta()` 的 `delta > 0` 分支內，`_advance_serve_state_and_snapshot()` 只執行一次額外的 `SELECT`（查詢 `MatchParticipant`）與一次 `session.add()`（`ScoreServeRecord`，記憶體操作，不觸發即時 I/O），與既有 `ScoreEvent` 的 `session.add()` 在同一個 `await session.commit()` 之前完成，屬於同一次資料庫交易、同一次網路往返，未新增任何外部呼叫。SC-003 通過。
- [X] T019 [P] Integration test（對應 spec.md Edge Cases 第 4 點／FR-006）：對一場已經累積若干 `score_serve_records` 的比賽，呼叫既有的 `regenerate_scoreboard_link()`／`regenerate_control_panel_link()`，確認呼叫前後 `score_serve_records` 的筆數與每一筆內容完全不變（連結重新產生不影響既有發球紀錄）in `apps/api/tests/integration/test_score_serve_record_flow.py`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：無任務。
- **Foundational (Phase 2)**：依序 T001 → T002 → T003；T004、T005 皆依賴 T002，完成後才能進行 T006、T007；T008 依賴 T006、T007。**封鎖所有 User Story**。
- **User Story 1 (Phase 3)**：依賴 Foundational 完成（T004、T005）。
- **User Story 2 (Phase 4)**：依賴 User Story 1 完成（T012）——沒有 US1 建立的紀錄機制，US2 無從驗證「紀錄不被覆蓋」。
- **Polish (Phase 5)**：依賴 US1、US2 皆完成。T018 依賴 T012；T019 依賴 T012（需要先有 `score_serve_records` 可供驗證不受連結重新產生影響）。

### Within Each Phase

- 測試先寫、先確認失敗，再進行對應實作（T001 早於 T004/T005；T009/T010 早於 T011/T012）。
- 同一個檔案（`service.py`）內彼此有相依關係的實作任務依序進行，不標記 `[P]`。

### Parallel Opportunities

- T001（Foundational 測試）可與 T002（models.py，不同檔案）同時進行。
- T008（Foundational 整合測試）本身標記 `[P]`，可與 Phase 3 開始前的其他收尾工作並行。
- T009 與 T010（US1 測試，分屬不同檔案）可並行。
- T014 與 T013（US2 測試，同一檔案但驗證的是各自獨立的情境）——因同屬 `test_score_serve_record_flow.py`，建議循序撰寫避免合併衝突，`[P]` 標記僅表示邏輯上互不相依，非強制同時進行。
- T015（lint/型別檢查）可與 T016（quickstart 核對）並行。
- T018（SC-003 審查）與 T019（連結重新產生整合測試）分屬不同性質的任務（前者是審查記錄、後者是新增測試碼），可並行；T019 與既有的 T013/T014（同屬 `test_score_serve_record_flow.py`）建議循序撰寫避免合併衝突。

---

## Parallel Example: Foundational

```bash
# T001（測試）與 T002（models.py）分屬不同檔案，可同時進行：
Task: "Unit tests for _compute_station() and _initialize_serve_state() in apps/api/tests/unit/domains/schedule/test_serve_state.py"
Task: "Add Match new columns + ScoreServeRecord model in apps/api/app/domains/schedule/models.py"
```

## Parallel Example: User Story 1

```bash
# T009 與 T010 分屬不同測試檔案，可同時進行：
Task: "Unit test for serve-state transition rules in apps/api/tests/unit/domains/schedule/test_serve_state.py"
Task: "Extend apply_score_delta() tests for +1 creates / -1 does not, in apps/api/tests/unit/domains/schedule/test_apply_score_delta.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. 完成 Phase 1：Setup（無任務）
2. 完成 Phase 2：Foundational（**關鍵，封鎖所有 User Story**）
3. 完成 Phase 3：User Story 1
4. **停下並驗證**：獨立測試 User Story 1（`quickstart.md` 情境 1–4）
5. 這就是本功能的 MVP——加分即記錄，`-1` 不記錄

### Incremental Delivery

1. 完成 Setup + Foundational → 比賽開始即有正確的發球狀態
2. 加上 User Story 1 → 獨立測試 → 這是 MVP（加分即記錄）
3. 加上 User Story 2 → 獨立測試 → 補強「歷史紀錄彼此獨立、不被覆蓋」的信心，完整交付本 feature 的全部驗收標準

---

## Notes

- `[P]` 任務 = 不同檔案、無相依關係
- `[Story]` 標籤將任務對應回 spec.md 的特定 User Story，利於追蹤
- 每個 User Story 皆應可獨立完成與測試
- 實作前先確認對應測試會失敗
- 每完成一個任務或一組邏輯相關任務即可考慮 commit
- 在任一 Checkpoint 皆可停下獨立驗證該 Story
- 本 feature 全程不觸碰 `apps/web/`——若在實作過程中發現需要修改前端，先回頭確認是否偏離了 spec.md FR-005（本次範圍不含查看/顯示介面）
