# Tasks: 落點詳細計分模式

**Input**: Design documents from `/specs/031-shot-placement-scoring/`

**Prerequisites**: plan.md、spec.md、research.md、data-model.md、contracts/（皆已存在）、quickstart.md

**Tests**：依 `plan.md` Constitution Check（原則 II）之要求，`roster_entry_id` 驗證、`detailed_scoring_enabled` 守門、座標範圍驗證、`delta<0` 收回邏輯，以及團設定切換，皆 MUST 有對應測試；至少一條整合測試涵蓋「開啟詳細模式 → 開賽 → 標落點加分 → 修正比分收回」全流程——本檔案的測試任務為強制項，非選用。

**Organization**：依 spec.md 之 3 個 User Story（US1 P1、US2 P2、US3 P3）分階段組織。三者共用同一份 Foundational 資料模型（`Group`/`Match` 新欄位、`ShotPlacementRecord`、`MatchLiveDetail` 新欄位）；US1 交付「標落點＋選球員即可加分」核心互動（含三處既有計分畫面的前端整合）；US2 交付「團管理員可切換模式」的設定介面；US3 交付「修正比分同時收回落點紀錄」。US1 可獨立測試（可用 fixture 直接在資料庫層級把某場比賽設為詳細模式，不需要先有 US2 的 HTTP 開關）；US2、US3 亦可各自獨立驗證。

## Format: `[ID] [P?] [Story] Description`

- **[P]**：可平行執行（不同檔案、無相依關係）
- **[Story]**：對應 spec.md 的 US1/US2/US3；Setup/Foundational/Polish 階段任務無此標籤
- 每項任務皆附精確檔案路徑

## Path Conventions

沿用 `plan.md` Project Structure：後端 `apps/api/`，前端 `apps/web/src/app/`。

---

## Phase 1: Setup

*本 feature 無新增 Setup 任務——monorepo、CI、lint/型別檢查工具鏈已由既有專案建立並沿用；不新增任何第三方依賴（plan.md Technical Context）。*

---

## Phase 2: Foundational（Blocking Prerequisites）

**Purpose**：三個 User Story 共用的資料模型與快照機制——任一 User Story 皆無法在此階段完成前開始。

**⚠️ CRITICAL**：此階段完成前，不可開始任何 User Story 的工作。

- [ ] T001 新增 `Group.detailed_scoring_enabled`（`Boolean NOT NULL DEFAULT false`）於 `apps/api/app/domains/group/models.py`（緊鄰既有 `scoreboard_scoring_enabled` 欄位）
- [ ] T002 新增 `Match.detailed_scoring_enabled`（`Boolean NOT NULL`，無 Python 端 default，比照既有 `target_score`/`deuce_threshold`/`cap_score` 三個快照欄位的既有寫法）以及新的 `ShotPlacementRecord` model（`score_event_id` UNIQUE FK `score_events.id` CASCADE、`match_id` FK+index、`group_id` FK+index——比照 `ScoreServeRecord` 對 `match_id`/`group_id` 雙欄皆 denormalize 的既有慣例、`roster_entry_id` FK `roster_entries.id`、`team` `String(1)`、`landing_x`/`landing_y` `Float NOT NULL`、`created_at`），欄位定義依 `data-model.md` in `apps/api/app/domains/schedule/models.py` (depends on T001)
- [ ] T003 產生並手動核對 Alembic migration：`ALTER TABLE groups ADD COLUMN detailed_scoring_enabled`、`ALTER TABLE matches ADD COLUMN detailed_scoring_enabled`（`server_default=false` 回填既有資料列，比照既有 migration 對「新增 NOT NULL 欄位到既有表」的慣用寫法）、`CREATE TABLE shot_placement_records`（`score_event_id` 唯一索引、`match_id`/`group_id` 各一般索引）in `apps/api/alembic/versions/<new_rev>_shot_placement_records.py` (depends on T001, T002)
- [ ] T004 於 `create_match_with_participants()` 內，`Match(...)` 建構時新增 `detailed_scoring_enabled=group.detailed_scoring_enabled`，比照既有 `target_score=group.target_score` 等三行的既有寫法 in `apps/api/app/domains/schedule/service.py` (depends on T002, T003)
- [ ] T005 [P] Unit test：`create_match_with_participants()` 在 `group.detailed_scoring_enabled=True`／`False` 兩種情況下，新建立的 `Match.detailed_scoring_enabled` 分別正確反映當下的團設定值（快照，非之後即時查詢）——直接以 fixture 在資料庫層級設定 `group.detailed_scoring_enabled`，不透過 HTTP 端點 in `apps/api/tests/unit/domains/schedule/test_apply_score_delta.py`（新增測試函式，沿用既有檔案）(depends on T004)
- [ ] T006 新增 `MatchLiveDetail.detailed_scoring_enabled: bool` 於 `apps/api/app/domains/schedule/schemas.py`，並於 `court_live_state()` 建構 `MatchLiveDetail` 時填入 `match.detailed_scoring_enabled` in `apps/api/app/domains/schedule/service.py` (depends on T002)
- [ ] T007 [P] Contract test：`GET .../state` 回應的 `current_match.detailed_scoring_enabled` 正確反映該場比賽的快照值（簡易模式比賽為 `false`，即使該團當下團設定已改為 `true`）in `apps/api/tests/contract/test_court_state.py`（新增測試函式，沿用既有檔案）(depends on T006)
- [ ] T008 [P] 新增 `MatchLiveDetail.detailedScoringEnabled: boolean` 於 `apps/web/src/app/core/api/court-live-state.models.ts`（沿用既有 `serve`/`participants` 等欄位的既有命名慣例，camelCase）

**Checkpoint**：Foundational 完成——資料庫具備完整的模式旗標與快照機制，`GET .../state` 已能反映每場比賽該用哪種計分介面，但尚未有任何實際寫入落點紀錄或切換設定的使用者可見行為。

---

## Phase 3: User Story 1 - 加分時標記落點與得分球員 (Priority: P1) 🎯 MVP

**Goal**：詳細計分模式下，計分員在球場示意圖點落點、選球員、確認後，系統把該球員所屬隊伍的比分加一，並建立一筆對應的 `ShotPlacementRecord`；三個既有計分畫面（計分板、控制板、全場地控制板）皆改用同一個共用互動元件。

**Independent Test**：對一場已啟用詳細計分模式（直接於 fixture 設定 `match.detailed_scoring_enabled=True`，不依賴 US2 的 HTTP 開關）、正在進行中的比賽，呼叫新的 `/score-detailed` 端點，查詢該次得分事件，確認能同時查到落點座標與所選球員，且比分確實加一；前端則開啟計分板頁面確認球場圖點選＋選球員的互動流程可以完整走完並成功呼叫該端點。

### Tests for User Story 1（先寫、先失敗）⚠️

- [ ] T009 [P] [US1] Unit test：`apply_score_delta()` 在 `delta=1` 且提供 `shot_placement` 參數時，於同一交易內寫入一筆 `ShotPlacementRecord`（`score_event_id` 與剛建立的 `ScoreEvent` 一致、`roster_entry_id`/`team`/`landing_x`/`landing_y` 皆與傳入值一致）；不提供 `shot_placement` 時（既有簡易模式呼叫方式）不寫入任何 `ShotPlacementRecord`，行為與擴充前完全相同（回歸保護）in `apps/api/tests/unit/domains/schedule/test_apply_score_delta.py`
- [ ] T010 [P] [US1] Unit test：新函式 `apply_detailed_score()` 的三項驗證——`roster_entry_id` 不屬於該場比賽時拒絕（`PARTICIPANT_NOT_IN_MATCH`）、`match.detailed_scoring_enabled=False` 時拒絕（`DETAILED_SCORING_NOT_ENABLED`）、`landing_x`/`landing_y` 超出 `[-0.3, 1.3]` 時拒絕（`INVALID_LANDING_COORDINATES`）；三種情況皆不改動比分、不寫入任何紀錄 in `apps/api/tests/unit/domains/schedule/test_shot_placement.py`（新檔案）
- [ ] T011 [P] [US1] Unit test：`apply_detailed_score()` 成功路徑——`roster_entry_id` 屬於 A 隊時，換算出的 `side` 為 `"A"`，比分正確加一（B 隊比照）in `apps/api/tests/unit/domains/schedule/test_shot_placement.py`
- [ ] T012 [P] [US1] Contract test：`POST /courts/by-token/{token}/matches/{match_id}/score-detailed`（token 版）與 `POST /groups/{group_id}/courts/{court_id}/matches/{match_id}/score-detailed`（admin 版）的成功回應形狀（`ScoreMutationResult`，比照既有 `/score` 端點）與三種錯誤代碼的 HTTP 422；token 版並驗證權限比照既有 `/score`（`control_panel_token` 可用，`scoreboard_token` 需該團 `scoreboard_scoring_enabled=True` 才可用）in `apps/api/tests/contract/test_score_detailed_endpoint.py`（新檔案）

### Implementation for User Story 1

- [ ] T013 [US1] 新增 `ScoreDetailedRequest`（`roster_entry_id: str`、`landing_x: float`、`landing_y: float`，`Field` 加上 `ge=-0.3, le=1.3` 範圍驗證）於 `apps/api/app/domains/schedule/schemas.py`
- [ ] T014 [US1] 擴充 `apply_score_delta()`：新增可選參數 `shot_placement: ShotPlacementInput | None = None`（`ShotPlacementInput` 為新的內部 dataclass/NamedTuple，欄位 `roster_entry_id`/`landing_x`/`landing_y`）；`delta > 0` 分支內，`shot_placement` 非 `None` 時，與既有 `ScoreEvent`/`ScoreServeRecord` 同一交易寫入 `ShotPlacementRecord`（`score_event_id` 指向同一個 `score_event_id`、`team` 取 `side` 參數值）in `apps/api/app/domains/schedule/service.py` (depends on T002；使 T009 通過)
- [ ] T015 [US1] 實作 `apply_detailed_score(session, court, match_id, roster_entry_id, landing_x, landing_y, source)`：依序驗證 `match.detailed_scoring_enabled`、`landing_x`/`landing_y` 範圍、`roster_entry_id` 屬於該場比賽（查詢 `MatchParticipant`，取得其 `team` 作為 `side`），驗證通過後呼叫 `apply_score_delta(session, court, match_id, side, 1, source=source, shot_placement=ShotPlacementInput(roster_entry_id, landing_x, landing_y))` in `apps/api/app/domains/schedule/service.py` (depends on T013, T014；使 T010、T011 通過)
- [ ] T016 [US1] 新增兩個路由：`POST /courts/by-token/{token}/matches/{match_id}/score-detailed`（比照 `score_by_token` 的 `_can_score_by_token` 權限判斷）與 `POST /groups/{group_id}/courts/{court_id}/matches/{match_id}/score-detailed`（比照 `score_by_admin` 的 `require_admin`/`_admin_court` 依賴），皆呼叫 `service.apply_detailed_score()` in `apps/api/app/domains/schedule/router.py` (depends on T015；使 T012 通過)
- [ ] T017 [P] [US1] 新增 `CourtControlService.scoreDetailed(token, matchId, rosterEntryId, landingX, landingY): Observable<ScoreMutationResult>`（比照既有 `.score()` 方法的既有寫法）in `apps/web/src/app/core/api/court-control.service.ts`
- [ ] T018 [US1] 新增共用元件 `ShotPlacementPickerComponent`（standalone）：以彈出形式呈現「球場示意圖（純 CSS 繪製，比照計分板既有球場線條/球網手法）點落點 → 從輸入的參賽者清單選一位 → 確認」三步驟；`@Input` 接收該場比賽的 `participants: ParticipantSummary[]`，確認前可重新點選/重新選擇（FR-003），確認時 emit 一個 `(rosterEntryId, landingX, landingY)` 的輸出事件，不自行呼叫任何 API in `apps/web/src/app/features/shot-placement/shot-placement-picker.component.ts` + `.html` + `.scss` (depends on T008)
- [ ] T019 [P] [US1] Component test：`ShotPlacementPickerComponent` 的互動狀態機——初始未選取時確認按鈕停用、點落點後可重新點選另一個位置、選球員後可重新選擇另一位、確認前的暫時選擇不會提早 emit、只有明確按下確認才 emit 一次帶有最終選擇的事件 in `apps/web/src/app/features/shot-placement/shot-placement-picker.component.spec.ts`
- [ ] T020 [P] [US1] 計分板整合：`match.detailedScoringEnabled` 為真時，原本的「+1」按鈕改為開啟 `ShotPlacementPickerComponent`；訂閱其確認事件後呼叫 `CourtControlService.scoreDetailed()`，成功後合併回傳的比分（比照既有 `.score()` 呼叫成功後的既有合併寫法）in `apps/web/src/app/features/scoreboard/scoreboard.component.ts` + `.html`（既有測試需同步更新，比照本次會話稍早 UI 重構時的既有模式）
- [ ] T021 [P] [US1] 控制板整合：同 T020，套用於控制板 in `apps/web/src/app/features/control-panel/control-panel.component.ts` + `.html`
- [ ] T022 [P] [US1] 全場地控制板整合：同 T020，套用於全場地控制板的單一場地方塊 in `apps/web/src/app/features/control-panel/all-courts/all-courts-court-block.component.ts` + `.html`
- [ ] T023 [P] [US1] 新增本功能相關顯示文字（球場圖操作提示、選球員清單標題、確認按鈕文字等）至既有語系檔 in `apps/web/src/assets/i18n/zh-TW.json` + `en.json`
- [ ] T024 [US1] Integration test：透過 fixture 建立一場 `detailed_scoring_enabled=True` 的雙打比賽，依序呼叫 `/score-detailed` 兩次（不同球員、不同落點），查詢 `shot_placement_records`，確認兩筆各自獨立、內容正確、`score_event_id` 分別對應各自的 `ScoreEvent` in `apps/api/tests/integration/test_shot_placement_flow.py`（新檔案）(depends on T016)

**Checkpoint**：US1 完整可運作——三個既有計分畫面在詳細模式下皆改用新的點落點/選球員互動，後端正確驗證並記錄。

---

## Phase 4: User Story 2 - 依團選擇要用簡易計分或詳細計分模式 (Priority: P2)

**Goal**：團管理員可以在管理頁開啟/關閉詳細計分模式；變更只影響之後新建立的比賽，不回溯影響進行中比賽。

**Independent Test**：呼叫團設定切換端點開啟詳細計分模式後，之後新建立的比賽 `detailed_scoring_enabled` 為 `true`；呼叫前已經在進行中的比賽維持 `false` 不變（此驗證依賴 Foundational 的 T004 快照機制，不依賴 US1 的計分互動本身）。

### Tests for User Story 2（先寫、先失敗）⚠️

- [ ] T025 [P] [US2] Contract test（比照既有 `tests/contract/test_scoreboard_scoring.py` 的既有結構與案例分佈）：新團預設 `detailed_scoring_enabled=false`；管理員呼叫 `PATCH /{group_id}/detailed-scoring` 開啟後，`GET /{group_id}/admin` 回傳的 `detailed_scoring_enabled=true`；非管理員（無/錯誤 token）呼叫遭拒絕；切換時對該團每個場地廣播 `match.nextRound`（比照既有廣播測試的 `monkeypatch.setattr(group_service, "publish", fake_publish)` 手法）in `apps/api/tests/contract/test_detailed_scoring_toggle.py`（新檔案）
- [ ] T026 [P] [US2] Integration test：對應 spec.md User Story 2 Acceptance Scenario——開啟團設定前已存在且進行中的比賽，開啟後其 `detailed_scoring_enabled` 維持 `false`；開啟後才建立的新比賽為 `true` in `apps/api/tests/integration/test_shot_placement_flow.py`

### Implementation for User Story 2

- [ ] T027 [US2] 實作 `set_detailed_scoring(session, group, enabled)`：更新 `group.detailed_scoring_enabled`、`commit`/`refresh`，並對該團每個未刪除場地廣播既有 `match.nextRound` 事件（完整比照既有 `set_scoreboard_scoring()` 的既有寫法）in `apps/api/app/domains/group/service.py`
- [ ] T028 [P] [US2] 新增 `DetailedScoringRequest`（`enabled: bool`）、`DetailedScoringResponse`（`detailed_scoring_enabled: bool`），並於 `AdminGroupResponse` 新增 `detailed_scoring_enabled: bool` 欄位（比照既有 `scoreboard_scoring_enabled` 欄位的既有註解與放置位置——僅管理頁可見，不進 `GroupPublicResponse`）in `apps/api/app/domains/group/schemas.py`
- [ ] T029 [US2] 新增路由 `PATCH /{group_id}/detailed-scoring`（比照既有 `set_scoreboard_scoring` 路由的既有寫法，含既有的 `GET /{group_id}` 系列端點回傳新欄位所需的建構呼叫更新）in `apps/api/app/domains/group/router.py` (depends on T027, T028；使 T025、T026 通過)
- [ ] T030 [P] [US2] 管理頁新增「詳細計分模式」開關 UI（比照既有 `scoreboard_scoring_enabled` 開關的既有版面與互動模式），呼叫對應的 group API 方法 in `apps/web/src/app/features/group-admin/admin-page/admin-page.component.ts` + `.html`（既有測試需同步更新）
- [ ] T031 [P] [US2] 新增本開關相關顯示文字（開關標籤、說明文字）至既有語系檔 in `apps/web/src/assets/i18n/zh-TW.json` + `en.json`

**Checkpoint**：US1、US2 皆可獨立驗證——US1 的計分互動 + US2 的設定入口皆已完整。

---

## Phase 5: User Story 3 - 修正錯誤的一分時，連同落點紀錄一起處理 (Priority: P3)

**Goal**：詳細計分模式下執行既有「修正比分（-1）」時，一併移除最後一筆落點/球員紀錄；對簡易模式比賽無影響（no-op）。

**Independent Test**：在詳細計分模式下記錄一分後，執行既有的修正比分（-1），查詢該場比賽的落點紀錄，確認該筆已消失、比分正確減一，且更早的其他紀錄不受影響；對簡易模式比賽執行 -1，確認行為與擴充前完全相同。

### Tests for User Story 3（先寫、先失敗）⚠️

- [ ] T032 [P] [US3] Unit test：`apply_score_delta()` 的 `delta=-1` 分支——詳細模式比賽已有至少一筆 `ShotPlacementRecord` 時，執行後該隊最新一筆消失、更早的其他筆不受影響；簡易模式比賽（從未有任何 `ShotPlacementRecord`）執行後行為不變（no-op，不因為新增這段邏輯而報錯或產生副作用）；0:0 時執行 `-1` 的既有下限保護行為（不產生負分）不受本次擴充影響 in `apps/api/tests/unit/domains/schedule/test_apply_score_delta.py`

### Implementation for User Story 3

- [ ] T033 [US3] 實作 `_remove_last_shot_placement_record(session, match_id, side)`：查詢並刪除該 `match_id`+`team` 最新一筆 `ShotPlacementRecord`（`ORDER BY created_at DESC LIMIT 1`），不存在時不做任何事 in `apps/api/app/domains/schedule/service.py`
- [ ] T034 [US3] 於 `apply_score_delta()` 的 `delta < 0` 分支，比分成功遞減後呼叫 `_remove_last_shot_placement_record()`（同一交易內）in `apps/api/app/domains/schedule/service.py` (depends on T033, T014；使 T032 通過)
- [ ] T035 [US3] Integration test：對應 quickstart.md 驗證情境 3——完整走一遍「標落點加分 → 修正比分收回」流程，驗證比分與紀錄筆數皆正確 in `apps/api/tests/integration/test_shot_placement_flow.py` (depends on T034)

**Checkpoint**：三個 User Story 皆可獨立驗證，spec.md 全部 Acceptance Scenario 皆有對應測試覆蓋。

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T036 [P] `ruff check app/ tests/` 與 `mypy app/` 全數通過（新增/修改的 `models.py`／`service.py`／`schemas.py`／`router.py`／migration 檔）
- [ ] T037 [P] `ng lint` 與 `tsc --noEmit`（`tsconfig.app.json`、`tsconfig.spec.json`）全數通過（新增/修改的前端檔案）
- [ ] T038 執行完整既有 `apps/api` 測試套件（`pytest tests/`），確認本 feature 未破壞任何既有測試
- [ ] T039 執行完整既有 `apps/web` 測試套件（`ng test --watch=false`），確認本 feature 未破壞任何既有測試（尤其 `scoreboard.component.spec.ts`／`control-panel.component.spec.ts`／`all-courts-court-block.component.spec.ts`／`admin-page.component.spec.ts` 四個受本次改動影響的既有檔案）
- [ ] T040 對照 `quickstart.md` 的 8 個驗證情境，逐一確認已由 T005/T007/T009–T012/T024–T026/T032/T035 等測試涵蓋，若有遺漏則補上對應測試
- [ ] T041 [P] SC-001 驗證（人工／實機操作計時，非自動化效能量測基礎設施，比照 030 SC-003 既有驗收慣例）：在手機瀏覽器實際操作 T018 共用元件完成一次加分，記錄操作時間，確認中位數落在 10 秒以內；於本任務完成註記中記錄量測結果

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：無任務。
- **Foundational (Phase 2)**：T001 → T002 → T003 依序；T004 依賴 T002/T003；T005 依賴 T004；T006 依賴 T002；T007 依賴 T006；T008 可與後端任務平行。**封鎖所有 User Story**。
- **User Story 1 (Phase 3)**：依賴 Foundational 全部完成。
- **User Story 2 (Phase 4)**：依賴 Foundational 完成（T004 快照機制）；不依賴 US1（US2 的獨立測試只驗證快照行為，不需要 `/score-detailed` 端點存在）。
- **User Story 3 (Phase 5)**：依賴 US1 完成（T014，`apply_score_delta()` 的 `shot_placement` 參數與寫入邏輯必須先存在，US3 才有「最後一筆紀錄」可供收回）。
- **Polish (Phase 6)**：依賴 US1、US2、US3 皆完成。

### Within Each Phase

- 測試先寫、先確認失敗，再進行對應實作。
- 同一個檔案（`service.py`／`router.py`／`schemas.py`）內彼此有相依關係的實作任務依序進行，不標記 `[P]`。
- 前端三個既有畫面的整合任務（T020/T021/T022）分屬不同檔案，可平行進行，但三者皆依賴 T018（共用元件）先完成。

### Parallel Opportunities

- T005（Foundational 單元測試）與 T006（schemas.py + service.py）可平行（不同檔案）。
- T007 與 T008 可平行（分屬前後端不同檔案）。
- US1 的四項測試 T009–T012 分屬不同檔案（`test_apply_score_delta.py`／`test_shot_placement.py`（新）／`test_score_detailed_endpoint.py`（新）），可平行撰寫。
- US1 前端任務 T017（service）、T018（共用元件）完成後，T020/T021/T022（三個既有畫面整合）可平行進行；T019（共用元件測試）與 T023（i18n）亦可平行。
- US2 的 T025/T026（測試）、T028（schemas）可與 T027（service）平行撰寫（測試先寫失敗）；T030/T031（前端）可與後端任務平行。
- US3 只有一條主要程式碼路徑（`service.py` 同一函式），T032（測試）與 T033（新函式）可平行起筆，但 T034 需等待兩者完成。
- Polish 階段 T036/T037（lint/型別）、T038/T039（既有測試套件）、T041（SC-001 量測）彼此分屬不同性質，可平行；T040 建議在其餘任務完成後再核對。

---

## Parallel Example: User Story 1

```bash
# T009、T010、T011、T012 分屬不同測試檔案，可同時進行：
Task: "Unit test for apply_score_delta() shot_placement write behavior in apps/api/tests/unit/domains/schedule/test_apply_score_delta.py"
Task: "Unit test for apply_detailed_score() validation errors in apps/api/tests/unit/domains/schedule/test_shot_placement.py"
Task: "Unit test for apply_detailed_score() success path in apps/api/tests/unit/domains/schedule/test_shot_placement.py"
Task: "Contract test for /score-detailed endpoint in apps/api/tests/contract/test_score_detailed_endpoint.py"

# T018 完成後，三個既有畫面整合可同時進行：
Task: "Wire ShotPlacementPickerComponent into scoreboard.component"
Task: "Wire ShotPlacementPickerComponent into control-panel.component"
Task: "Wire ShotPlacementPickerComponent into all-courts-court-block.component"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. 完成 Phase 1：Setup（無任務）
2. 完成 Phase 2：Foundational（**關鍵，封鎖所有 User Story**）
3. 完成 Phase 3：User Story 1
4. **停下並驗證**：獨立測試 User Story 1（`quickstart.md` 情境 2、4、5、7）——此時詳細模式只能透過直接操作資料庫（或未來的 US2 端點）啟用，但核心的「標落點加分」互動已完整可用
5. 這就是本功能的 MVP

### Incremental Delivery

1. 完成 Setup + Foundational → 資料模型與快照機制就緒
2. 加上 User Story 1 → 獨立測試 → 這是 MVP（標落點加分的核心互動）
3. 加上 User Story 2 → 獨立測試 → 團管理員終於能自行開關，不再需要直接操作資料庫
4. 加上 User Story 3 → 獨立測試 → 補上「修正比分同時收回紀錄」的資料正確性保護，完整交付本 feature 的全部驗收標準

### Parallel Team Strategy

Foundational 完成後：
- Developer A：User Story 1（後端 `/score-detailed` + 前端共用元件 + 三處整合）
- Developer B：User Story 2（團設定開關，前後端）
- User Story 3 建議留到 US1 完成後由同一位負責 US1 的開發者接續（同一段 `apply_score_delta()` 程式碼，避免合併衝突）

---

## Notes

- `[P]` 任務 = 不同檔案、無相依關係
- `[Story]` 標籤將任務對應回 spec.md 的特定 User Story，利於追蹤
- 每個 User Story 皆應可獨立完成與測試
- 實作前先確認對應測試會失敗
- 每完成一個任務或一組邏輯相關任務即可考慮 commit
- 在任一 Checkpoint 皆可停下獨立驗證該 Story
- 前端三個既有計分畫面（計分板、控制板、全場地控制板）的既有測試在 T020/T021/T022 完成後 MUST 同步檢查是否需要更新選擇器或新增案例，比照本次會話稍早計分板 UI 重構時的既有處理模式
