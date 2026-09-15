# Tasks: 計分板發球站位顯示

**Input**: Design documents from `/specs/029-serve-rotation-display/`

**Prerequisites**: plan.md、spec.md、research.md、data-model.md、contracts/court-state-serve-fields.md、quickstart.md（皆已存在）；`030-score-serve-record` 已實作完成（`Match.serving_team`/`team_a_reference_server_id`/`team_b_reference_server_id` 三個欄位與 `_compute_station()`/`_advance_serve_state_and_snapshot()` 共用函式皆已存在於 `apps/api/app/domains/schedule/service.py`）。

**Tests**: 依 `plan.md` Constitution Check（原則 II／VII）之要求，後端新欄位形狀、前端四站位渲染與非色彩發球者標記皆 MUST 有測試；本檔案的測試任務為強制項，非選用。

**Organization**：依 spec.md 之 3 個 User Story（US1 P1、US2 P2、US3 P3）分階段組織。US2（開賽自動指派發球方）的底層機制已由 `030-score-serve-record` 的 Foundational 工作完成並測試過，US3（多裝置一致且即時）的底層機制已由本 feature 的 Foundational 階段（`serve` 搭 `match.scoreUpdated` 單一事件送出）自然滿足——這兩個 Story 因此只需要「確認既有機制透過本次新增的介面依然成立」的驗證測試，不需要新的產品邏輯；US1（畫面呈現）才是本 feature 真正新增程式碼的地方，也是 MVP。

## Format: `[ID] [P?] [Story] Description`

- **[P]**：可平行執行（不同檔案、無相依關係）
- **[Story]**：對應 spec.md 的 US1/US2/US3；Setup/Foundational/Polish 階段任務無此標籤
- 每項任務皆附精確檔案路徑

## Path Conventions

沿用 `plan.md` Project Structure：後端 `apps/api/`、前端 `apps/web/`，本 feature 同時涉及兩者。

---

## Phase 1: Setup

*本 feature 無新增 Setup 任務——不新增任何第三方依賴，monorepo/CI/lint 工具鏈沿用既有設定。*

---

## Phase 2: Foundational（Blocking Prerequisites）

**Purpose**：後端把既有發球狀態透過 `GET .../state` 與 `match.scoreUpdated` 事件暴露成結構化的 `serve` 欄位；前端補上對應型別。三個 User Story 皆依賴這一層才能開始。

**⚠️ CRITICAL**：此階段完成前，不可開始任何 User Story 的工作。

### Tests for Foundational（先寫、先失敗）

- [X] T001 [P] Contract test 擴充：`GET /courts/by-token/{token}/state` 回應之 `current_match.serve`——雙打比賽時四個站位欄位皆非 `null`、`server_roster_entry_id`/`server_team` 存在且與 `matches.serving_team`/對應 `reference_server` 一致；單打比賽時每隊四個站位欄位中恰有一個非 `null`；沒有進行中比賽時 `current_match` 本身為 `null`（不特別斷言 `serve`）in `apps/api/tests/contract/test_court_state.py`
- [X] T002 [P] Integration test 擴充：`monkeypatch.setattr("app.domains.schedule.service.publish", AsyncMock())`（比照既有 `tests/integration/test_standings_realtime_flow.py` 慣例）。(a) 對一場比賽加分（`+1`）後，斷言 `match.scoreUpdated` 這次呼叫的 payload（`call.args[2]`）含有 `serve` 欄位，且其值與同一次呼叫後查詢 `score_serve_records` 最新一筆的對應欄位完全一致；(b) 緊接著對同一場比賽呼叫 `-1`，斷言該次呼叫**不拋出例外、回應 200**，`match.scoreUpdated` 仍正常發布且 payload 含有 `serve`，其 `server_team`/`server_roster_entry_id` 與 `-1` 之前相同（`-1` 不改變發球方，030 Decision 5），但四個站位欄位依修正後的比分重新反映正確的奇偶（FR-010）in `apps/api/tests/integration/test_scoring_flow.py`

### Implementation for Foundational

- [X] T003 新增 `ServeStationInfo` Pydantic schema（`server_roster_entry_id: str`、`server_team: Team`、`team_a_right_roster_entry_id: str | None`、`team_a_left_roster_entry_id: str | None`、`team_b_right_roster_entry_id: str | None`、`team_b_left_roster_entry_id: str | None`），並在 `MatchLiveDetail` 新增 `serve: ServeStationInfo | None` 欄位 in `apps/api/app/domains/schedule/schemas.py`
- [X] T004 擴充 `court_live_state()`：查詢 `Match` 時一併取得 `serving_team`/`team_a_reference_server_id`/`team_b_reference_server_id`；若 `serving_team` 非 `None`，呼叫 `_match_participants_by_team()` 取得雙方參賽者、呼叫 `_compute_station()` 算出站位，組成 `ServeStationInfo` 填入 `MatchLiveDetail.serve`；若 `serving_team` 為 `None`（research.md Decision 4，030 尚未部署前的舊比賽），`serve` 設為 `None` in `apps/api/app/domains/schedule/service.py` (depends on T003；使 T001 通過)
- [X] T005 擴充 `apply_score_delta()` 既有的 `match.scoreUpdated` `publish()` 呼叫，於組出該次 payload 時加上 `serve` 欄位。**注意**：`serve_record`（`_advance_serve_state_and_snapshot()` 的回傳值）只在 `delta > 0` 分支內有定義，但 `publish("match.scoreUpdated", ...)` 所在的 `else` 分支（`match_wins(...)` 為否時）在 `delta < 0` 也會執行——直接引用 `serve_record` 會在每次「-1」修正比分時因變數未定義而丟出例外。因此依 `delta` 分兩種情況組出 `serve`：
  - `delta > 0`：重用同一次呼叫中 `serve_record` 的欄位（`server_roster_entry_id`／`server_team`／四個站位）組成 `serve` 字典——**不重新呼叫 `_compute_station()`**，避免同一份站位算兩次。
  - `delta < 0`（`-1` 修正比分，FR-010）：現場呼叫 `_match_participants_by_team()` 取得雙方參賽者，並以（此時已 `refresh()` 過的）`match.serving_team`／`team_a_reference_server_id`／`team_b_reference_server_id`（`-1` 不會改動這三個欄位，030 Decision 5）與 `match.score_a`／`match.score_b`（修正後的比分）呼叫 `_compute_station()` 現算，做法比照 T004。

  兩種情況皆須處理 `match.serving_team is None`（030 尚未部署前的舊比賽）時 `serve` 設為 `None`，與 T004 一致 in `apps/api/app/domains/schedule/service.py` (depends on T003, T004；使 T002 通過)
- [X] T006 [P] 新增 `ServeStationInfo` TypeScript interface，並在 `MatchLiveDetail` 新增 `serve: ServeStationInfo | null` 欄位 in `apps/web/src/app/core/api/court-live-state.models.ts`

**Checkpoint**：Foundational 完成——`GET .../state` 與 `match.scoreUpdated` 皆已攜帶 `serve`，但畫面尚未呈現任何內容。

---

## Phase 3: User Story 1 - 觀看計分板即可看出目前發球者與站位 (Priority: P1) 🎯 MVP

**Goal**：計分板畫面四個角落分別顯示雙方球員（單打 2 位、雙打 4 位）暱稱，目前發球者有非純色彩的視覺標記；比分變動時不需重新整理即自動更新。

**Independent Test**：開啟一場已在進行中、比分不為 0:0 的比賽的計分板連結，確認四個角落是否各自顯示正確球員暱稱、能否一眼看出誰在發球；為該比賽加一分後，畫面不重新整理即正確更新。

### Tests for User Story 1（先寫、先失敗）

- [X] T007 [P] [US1] Vitest：給定雙打 `liveState`（`serve` 四個站位皆非 `null`），元件渲染出四個站位各自的暱稱文字，且僅發球者所在站位存在一個非純色彩的標記元素（例如帶有文字/`aria-label` 的圖示，而非只是一個 CSS class）in `apps/web/src/app/features/scoreboard/scoreboard.component.spec.ts`
- [X] T008 [P] [US1] Vitest：(a) 給定單打 `liveState`（`serve` 每隊四個站位中恰有一個非 `null`），元件每隊只渲染一個站位暱稱，另一個站位不渲染任何佔位元素或空白框；(b) 給定 `liveState().current_match` 為 `null`（呼應 FR-007，比照既有「等待中」測試情境），元件不渲染任何站位或發球者標記元素——沿用既有 `@if (state.current_match; ...)` 版面守門，非本次新增邏輯，此處純粹是防止日後改動不小心破壞這個既有保證 in `apps/web/src/app/features/scoreboard/scoreboard.component.spec.ts`
- [X] T009 [US1] Vitest：初始 `liveState` 顯示 A 隊發球，模擬收到含新 `serve`（B 隊發球，side-out 後）的 `match.scoreUpdated` 事件，元件畫面上的發球者標記在不呼叫 `getState()`/不重新整理的情況下移動到新的站位 in `apps/web/src/app/features/scoreboard/scoreboard.component.spec.ts`

### Implementation for User Story 1

- [X] T010 [US1] 新增元件方法／computed，輸入 `serve: ServeStationInfo | null` 與 `match.participants`、輸出四個站位各自的 `{ nickname, isServer } | null`（站位欄位為 `null` 或 `serve` 本身為 `null` 時回傳 `null`，對應站位留白）in `apps/web/src/app/features/scoreboard/scoreboard.component.ts`
- [X] T011 [US1] 改寫 `scoreboard.component.html`：把每隊原本「`.names` 內用 `@for` 疊出所有隊員」的區塊，改成呼叫 T010 的方法分別渲染「右側站位」「左側站位」兩個獨立元素；發球者所在站位加上非純色彩標記（圖示＋i18n文字，比照既有 `.status-badge` 慣例）in `apps/web/src/app/features/scoreboard/scoreboard.component.html`
- [X] T012 [P] [US1] 新增發球者標記的 i18n 字串（例如 `scoreboard.serving`）至 `apps/web/src/assets/i18n/zh-TW.json` 與 `apps/web/src/assets/i18n/en.json`
- [X] T013 [US1] 新增站位版面與發球者標記樣式（沿用既有 `.team`/`.names` 版面兩欄式結構內部拆分，不更動既有比分字體大小/雙打隊伍區塊配色）in `apps/web/src/app/features/scoreboard/scoreboard.component.scss`
- [X] T014 [US1] 擴充既有 `match.scoreUpdated` 訂閱 handler，比照既有 `score_a`/`score_b` 的淺層合併方式，一併把事件負載的 `serve` 合併進本地 `liveState` 的 `current_match` in `apps/web/src/app/features/scoreboard/scoreboard.component.ts` (depends on T006；使 T009 通過)

**Checkpoint**：US1 完整可運作——四站位正確顯示、單打留白、發球者非色彩標記、比分變動即時更新。此為本 feature 的 MVP。

---

## Phase 4: User Story 2 - 比賽開始時系統自動決定首位發球方 (Priority: P2)

**Goal**：比賽一轉為進行中即已有發球方（機制由 `030-score-serve-record` 提供），本 feature 新增的 `GET .../state` 介面正確暴露這個既成事實。

**Independent Test**：讓一場比賽轉為進行中，立即查詢 `GET .../state`，確認 `current_match.serve` 已非 `null`，不需要任何加分動作。

*本 Story 不需要新的產品邏輯——隨機指派機制由 030 的 `_initialize_serve_state()` 已完整實作與測試；本階段只驗證 Foundational 階段新增的 API 曝光層，從比賽一開始就正確反映這個既有機制的結果。*

### Tests for User Story 2

- [X] T015 [US2] Contract test：建立一場比賽並直接轉為 `in_progress`（不呼叫任何加分端點），立即呼叫 `GET .../state`，斷言 `current_match.serve` 非 `null` 且 `server_roster_entry_id` 屬於該場比賽的參賽者之一 in `apps/api/tests/contract/test_court_state.py` (depends on T004)

**Checkpoint**：US2 確認完成——開賽當下、加分之前，`serve` 已經正確可查。

---

## Phase 5: User Story 3 - 多人同時查看時資訊一致且即時 (Priority: P3)

**Goal**：同一場比賽的發球者/站位資訊，在多個同時開啟計分板連結的裝置之間一致且即時同步；中途才開啟的裝置也能直接看到正確結果。

**Independent Test**：模擬兩個裝置（兩次獨立呼叫 `GET .../state`）在同一次得分後看到相同的 `serve`；模擬一個裝置在比賽進行到一半才第一次載入，直接取得正確站位。

*本 Story 的一致性保證來自 research.md Decision 1（站位由後端算好、單一份計算結果）與 Decision 2（搭同一個 `match.scoreUpdated` 事件送給所有訂閱端）——這兩者已在 Foundational 階段完成，本階段只需驗證這個既有架構的多端一致性，不需要新的產品邏輯。*

### Tests for User Story 3

- [X] T016 [US3] Integration test：對一場比賽加分後，各自獨立呼叫兩次 `GET .../state`（模擬兩個裝置），斷言兩次回應的 `current_match.serve` 完全相同 in `apps/api/tests/integration/test_scoring_flow.py` (depends on T004)
- [X] T017 [P] [US3] Vitest：既有 `ReconnectRefetchService` 觸發的 `loadState()` 重新拉取整份 `CourtStateResponse` 後，畫面上的發球者標記與站位正確反映新拉取到的 `serve`（呼應 spec Edge Case「中途才開啟連結」與 quickstart.md 情境 6）in `apps/web/src/app/features/scoreboard/scoreboard.component.spec.ts`

**Checkpoint**：US1、US2、US3 皆可獨立驗證，三者合併即完整交付 spec.md 全部驗收標準。

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T018 [P] 後端 `ruff check app/ tests/` 與 `mypy app/` 全數通過；前端 `ng lint` 與 `tsc --noEmit`（或等效嚴格型別檢查）全數通過——實際執行結果：四者皆 0 錯誤。
- [X] T019 對照 `quickstart.md` 的 6 個驗證情境，逐一確認已由 T001/T002/T007–T009/T015–T017 等測試涵蓋，若有遺漏則補上對應測試——核對結果：情境 1→T007；情境 2/3→T009；情境 4→T008；情境 5→T008(b)；情境 6→T017、T016。六個情境皆有對應測試，無遺漏。
- [X] T020 分別執行完整既有後端測試套件（`pytest tests/`）與前端測試套件（`ng test`），確認本 feature 未破壞任何既有測試（尤其 `test_court_state.py`、`test_scoring_flow.py`、`scoreboard.component.spec.ts` 既有案例）——實際執行結果：前端 350 passed（本 feature 新增前為 346 passed）、0 failed；後端 1044 passed、1 failed（`test_oauth_state.py::test_tampered_state_is_rejected`，與本 feature 完全無關的既有 OAuth 測試，獨立重跑 5 次可重現 4 通過/1 失敗的既有間歇性失敗，非本次改動造成的迴歸）。

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：無任務。
- **Foundational (Phase 2)**：T003 → T004 → T005（T005 的 `delta < 0` 分支比照 T004 現算 `serve`，因此依賴 T004 已存在的同一套邏輯/慣例，非僅依賴 schema）；T006（前端型別）可與後端任務平行。**封鎖所有 User Story**。
- **User Story 1 (Phase 3)**：依賴 Foundational 完成（T004 提供 `GET .../state` 的 `serve`；T006 提供前端型別）。
- **User Story 2 (Phase 4)**：依賴 T004。與 User Story 1 相互獨立（不共用實作任務），可平行進行。
- **User Story 3 (Phase 5)**：依賴 T004、T005。與 User Story 1/2 相互獨立，可平行進行。
- **Polish (Phase 6)**：依賴 US1、US2、US3 皆完成。

### Within Each Phase

- 測試先寫、先確認失敗，再進行對應實作。
- 同一檔案（`service.py`、`scoreboard.component.ts`／`.html`）內彼此有相依關係的任務依序進行，不標記 `[P]`。

### Parallel Opportunities

- T001 與 T002（Foundational 測試，不同檔案）可並行；T006（前端型別，不同檔案）可與 T003–T005（後端）並行。
- Foundational 完成後，US1（T007–T014）、US2（T015）、US3（T016–T017）三個 Story 之間可由不同人平行開發——US2/US3 只讀取 Foundational 已提供的欄位，不修改 US1 的前端檔案。
- T007/T008（US1 前端測試，同檔案但不同案例）與 T012（i18n 檔案，不同檔案）可並行。
- T018 的前後端檢查可並行。

---

## Parallel Example: Foundational

```bash
# T001（後端契約測試）與 T006（前端型別）分屬不同專案/檔案，可同時進行：
Task: "Contract test for GET .../state serve field in apps/api/tests/contract/test_court_state.py"
Task: "Add ServeStationInfo TypeScript interface in apps/web/src/app/core/api/court-live-state.models.ts"
```

## Parallel Example: Post-Foundational Stories

```bash
# Foundational 完成後，US2 與 US3 的測試可與 US1 的前端工作同時進行：
Task: "Contract test: serve populated immediately at match start (US2) in apps/api/tests/contract/test_court_state.py"
Task: "Integration test: two GET .../state calls return identical serve (US3) in apps/api/tests/integration/test_scoring_flow.py"
Task: "Add station-resolving helper in scoreboard.component.ts (US1)"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. 完成 Phase 1：Setup（無任務）
2. 完成 Phase 2：Foundational（**關鍵，封鎖所有 User Story**）
3. 完成 Phase 3：User Story 1
4. **停下並驗證**：獨立測試 User Story 1（`quickstart.md` 情境 1–4）
5. 這就是本功能的 MVP——計分板正確顯示發球站位與即時更新

### Incremental Delivery

1. 完成 Setup + Foundational → 後端/型別就緒，尚無畫面
2. 加上 User Story 1 → 獨立測試 → 這是 MVP（畫面正確顯示且即時更新）
3. 加上 User Story 2 → 獨立測試 → 確認開賽當下即有資料可顯示（多半已自動成立，此步驟主要是補上驗證測試）
4. 加上 User Story 3 → 獨立測試 → 確認多裝置一致性（多半已自動成立，此步驟主要是補上驗證測試）

---

## Notes

- `[P]` 任務 = 不同檔案、無相依關係
- `[Story]` 標籤將任務對應回 spec.md 的特定 User Story，利於追蹤
- US2、US3 刻意只有測試任務、沒有「Implementation」小節——因為底層機制已由 Foundational（本 feature）與 030（前一個 feature）完成，這是刻意的設計結果，不是遺漏
- 實作前先確認對應測試會失敗
- 每完成一個任務或一組邏輯相關任務即可考慮 commit
- 在任一 Checkpoint 皆可停下獨立驗證該 Story
- 本 feature MUST NOT 修改 control-panel/all-courts 的樣板——它們共用同一個 `court_live_state()`，`serve` 欄位對它們而言只是多出來、不使用的資料（spec Assumptions）
