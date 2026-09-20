---

description: "Task list for 038-admin-detailed-scoring"
---

# Tasks: 管理頁分數控制板支援比賽詳細設定

**Input**: Design documents from `/specs/038-admin-detailed-scoring/`

**Prerequisites**: [plan.md](./plan.md)、[spec.md](./spec.md)、[research.md](./research.md)、[data-model.md](./data-model.md)、[contracts/schedule-api-additions.md](./contracts/schedule-api-additions.md)、[quickstart.md](./quickstart.md)

**Tests**: **本功能的測試是必要的，不是選配。** 憲章原則 II 明定「比分計算」屬核心領域邏輯，修改時未附測試的 PR 視為未完成。research.md Decision 8 已定下測試策略：後端補契約測試（快照值、不回溯），前端補元件測試（凍結與 pending-point 狀態機）。

**Organization**: 依 user story 分組，每個 story 可獨立實作與驗收。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行執行（不同檔案、無未完成的相依）
- **[Story]**: 對應 spec.md 的 user story（US1／US2／US3）

## Path Conventions

本專案為 web application 雙專案結構：後端 `apps/api/`、前端 `apps/web/`。以下路徑皆自 repo 根目錄起算。

---

## Phase 1: Setup（環境準備）

**Purpose**: 讓測試跑得起來，並取得改動前的基準。本功能沒有專案初始化工作——沒有新套件、沒有新目錄、沒有 migration。

- [X] T001 [P] 建立前端測試環境：`ln -s /Users/zcwang/projects/rally-stats/apps/web/node_modules apps/web/node_modules`（worktree 沒有自己的 `node_modules`，此 symlink 已被 gitignore）
- [X] T002 [P] 建立後端測試環境：把主 checkout 的 `apps/api/.venv/bin` 加入 `PATH`（`apps/api/tests/conftest.py` 會 shell out 到 `alembic`，僅用絕對路徑呼叫 python 不夠）
- [X] T003 取得基準：於 `apps/web` 執行 `npx ng test --watch=false`，確認 `apps/web/src/app/features/group-admin/schedule-management/court-control.component.spec.ts` 現有 3 條測試通過（註：整體 `ng test` 一律會報 1 個來自 `admin-page.component.spec.ts` 的 `NG04002` unhandled error，是既有現象，非本功能造成）

---

## Phase 2: Foundational（阻塞性前置作業）

**Purpose**: 把「這場比賽是否啟用詳細設定」送到管理頁，補齊前端型別與服務層，並鋪好凍結機制。**本階段完成後畫面行為應完全不變**——簡易模式與詳細模式都還是一鍵加分，這是刻意的：凍結機制先就位，US1 才能安全地掛上詳細視窗。

**⚠️ CRITICAL**: 三個 user story 都依賴本階段，必須先完成。

### 後端：排程快照補上欄位

- [X] T004 [P] 在 `apps/api/app/domains/schedule/schemas.py` 的 `MatchSummary` 新增 `detailed_scoring_enabled: bool = False`，並比照同檔 `MatchLiveDetail` 既有欄位的註解風格說明「這是比賽自己的快照、不是團的當下設定」
- [X] T005 在 `apps/api/app/domains/schedule/service.py` 的 `build_schedule_snapshot()`（約 L2064，全檔唯一的 `MatchSummary(...)` 建構點）加入 `detailed_scoring_enabled=entry[0].detailed_scoring_enabled`（`entry[0]` 為 `Match` ORM 物件，欄位定義於 `apps/api/app/domains/schedule/models.py:49`）（depends on T004）
- [X] T006 [P] 在 `apps/api/tests/contract/test_detailed_scoring_toggle.py` 新增契約測試：沿用該檔既有的 `_create_group_with_active_match()`，驗證 `GET /groups/{group_id}/schedule` 的 `courts[].current_match.detailed_scoring_enabled` 在團開啟時建立的比賽為 `true`、關閉時為 `false`（depends on T005）
- [X] T007 [P] 在 `apps/api/tests/contract/test_detailed_scoring_toggle.py` 新增快照不回溯測試：比賽開打後把團開關切到相反值，同一場比賽的 `detailed_scoring_enabled` 維持原值（憲章原則 III，FR-015）（depends on T005；與 T006 同檔，兩者請依序提交而非同時編輯）
- [X] T008 於 `apps/api` 執行 `python -m pytest tests/contract/test_detailed_scoring_toggle.py` 與 `ruff check app/ tests/ && mypy app/`，確認後端這一層完成且可獨立合併

### 前端：型別與服務層

- [X] T009 [P] 在 `apps/web/src/app/features/group-admin/schedule-management/schedule.models.ts` 為 `MatchSummary` 新增 `detailed_scoring_enabled: boolean`，並為 `ScoreMutationResult` 補上後端早已回傳、前端漏宣告的 `score_event_id: string | null`（同一檔案的兩處改動，合併為一個任務以免衝突）
- [X] T010 在 `apps/web/src/app/features/group-admin/schedule-management/schedule.service.ts` 新增 `recordShotPlacement()` 與 `undoMatchCompletion()`，簽章與參數順序比照 `apps/web/src/app/core/api/court-control.service.ts` 的同名方法，差別僅在路徑改為 `/groups/${groupId}/courts/${courtId}/matches/${matchId}/…` 並帶上 `this.authHeader(groupId)`；`EndingType` 與 `ShotPlacementAttachResponse` 自 `apps/web/src/app/core/api/court-live-state.models.ts` 匯入（depends on T009）

### 前端：凍結機制就位（此時尚無任何行為變化）

- [X] T011 在 `apps/web/src/app/features/group-admin/schedule-management/court-control.component.ts` 新增 `private readonly frozenCourt = signal<CourtScheduleStatus | null>(null)` 與 `readonly displayCourt = computed(() => this.frozenCourt() ?? this.court())`，並加註解說明「此元件沒有自己的 live state，賽末點會讓父元件重抓後 `current_match` 變 null」這個凍結存在的理由
- [X] T012 把 `court-control.component.ts` 中**所有讀 `current_match` 的地方**改走 `displayCourt()`：比分跳動 effect（L81）、`score()` 取 `match_id`（L194）、`confirmEndMatch()` 取 `match_id`（L212）。**`court_id` 的三處讀取（L103 realtime 頻道、L123/L129 左右交換偏好）維持讀 `court()` 不改**——`court_id` 在元件生命週期內恆定，改了只會在凍結期間多餘地重新求值（research.md 風險註 1 的對照表）（depends on T011）
- [X] T013 把 `apps/web/src/app/features/group-admin/schedule-management/court-control.component.html` 第 6 行的 `@if (court().current_match; as match)` 改為 `@if (displayCourt()?.current_match; as match)`；模板其餘部分全部使用 `match` 別名，**不需要逐行改**（depends on T011）
- [X] T014 在 `court-control.component.spec.ts` 新增回歸測試：`frozenCourt` 為 null 時 `displayCourt() === court()`，且簡易模式（`detailed_scoring_enabled: false`）按「+1」仍只呼叫 `scoreMatch()`、不開任何視窗——保護 SC-004「操作流程與實作前逐步相同」（depends on T012、T013）

**Checkpoint**: 後端送得出快照值、前端型別與服務層齊備、凍結機制就位；畫面行為零變化，可安全合併。

---

## Phase 3: User Story 1 - 管理員在管理頁加分後記錄這一分的詳細資料 (Priority: P1) 🎯 MVP

**Goal**: 詳細設定開啟時，管理頁按「+1」立即加分並在同一次按壓開啟詳細記錄視窗，確認後資料與公開控制頁面記的分完全等價。

**Independent Test**: 開一個已啟用「比賽詳細設定」的團，排一場比賽，全程只從開團管理頁面計分，打完後到比賽紀錄頁檢查——每一分都有落點與球員資料，與從控制頁面計分的對照組無法區分。

**參考實作**: `apps/web/src/app/features/control-panel/all-courts/all-courts-court-block.component.ts` 是架構上最接近的姊妹元件（同為 per-court 子元件、無自身 live state、靠 `changed` output 請父元件重抓），本階段基本上是把它的詳細計分流程移植過來並替換資料來源。

### Tests for User Story 1

- [X] T015 [P] [US1] 在 `apps/web/src/app/features/group-admin/schedule-management/court-control.component.spec.ts` 擴充 `setup()` 的 `ScheduleService` stub，讓 `scoreMatch` 可回傳完整的 `ScoreMutationResult`（含 `applied`、`score_event_id`、`serve`），並加入 `recordShotPlacement`／`undoMatchCompletion` 的 stub；範本見 `apps/web/src/app/features/scoreboard/scoreboard.component.spec.ts` 的 `detailedMatchState`（約 L394）
- [X] T016 [P] [US1] 在 `court-control.component.spec.ts` 新增測試：詳細模式下點「+1」會呼叫 `scoreMatch(…, side, 1)`、呼叫 picker 的 `open()` 一次，且 `pendingScoringSide()` 等於被加分的那一隊（FR-001、FR-002、FR-003）（depends on T015）
- [X] T017 [P] [US1] 在 `court-control.component.spec.ts` 新增測試：picker 的 `confirmed` 事件會把落點、得分／失分球員與 `endingType` 原樣傳給 `recordShotPlacement()`，且 `score_event_id` 取自加分回應（FR-004、FR-014）（depends on T015）
- [X] T018 [P] [US1] 在 `court-control.component.spec.ts` 新增測試：加分回應 `applied: false`（或無 `score_event_id`）時視窗自行關閉，不留下 pending point（FR-017）（depends on T015）

### Implementation for User Story 1

- [X] T019 [US1] 在 `court-control.component.ts` 匯入 `ShotPlacementPickerComponent`、`ShotPlacementConfirmed`（`apps/web/src/app/features/shot-placement/shot-placement-picker.component`）與 `PendingPoint`、`PendingPointAction`（`…/shot-placement/pending-point`），並把 picker 加入元件的 `imports` 陣列、新增 `readonly shotPlacementPicker = viewChild<ShotPlacementPickerComponent>('shotPlacementPicker')`
- [X] T020 [US1] 在 `court-control.component.ts` 新增 pending 狀態欄位：`pendingScoringSide`、`pendingServingTeam`、`pendingServingScore`、`pendingServingRosterEntryId`、`pendingPoint`、`pickerOpen`，欄位語意與註解比照 `all-courts-court-block.component.ts` 同名欄位（尤其「發球方必須在加分**前**擷取」的理由）（depends on T019）
- [X] T021 [US1] 在 `court-control.component.ts` 實作 `scoreThenOpenPicker(side: Team)`：擷取加分前的發球狀態 → `frozenCourt.set(current)` → `shotPlacementPicker()?.open()` → 送出 `scoreMatch(…, side, 1)`；回應成功時以 `result.score_a/score_b/serve` patch `frozenCourt`、呼叫 `changed.emit()`、再 `point.resolve(result.score_event_id, result.status !== 'in_progress')`；回應未 applied 或出錯則 `abandonPoint(point)`（depends on T020）
- [X] T022 [US1] 在 `court-control.component.ts` 實作 `abandonPoint()`、`onShotPlacementClosed()`（解除凍結）與 `clearPendingPoint()`，行為比照 `all-courts-court-block.component.ts` 同名方法（depends on T021）
- [X] T023 [US1] 在 `court-control.component.ts` 實作 `onShotPlacementConfirmed()` → `requestPickerAction({ kind: 'confirm', detail })` → `runPickerAction()` 的確認分支，呼叫 T010 新增的 `recordShotPlacement()`，成功後 `clearPendingPoint()` 與 `changed.emit()`（depends on T022）
- [X] T024 [US1] 在 `court-control.component.html` 把左右兩側的「+1」改為 `(click)="match.detailed_scoring_enabled ? scoreThenOpenPicker(leftTeam()) : score(leftTeam(), 1)"`（右側同理用 `rightTeam()`）；**「-1」兩顆按鈕維持呼叫 `score(…, -1)` 不變**（FR-010）（depends on T021）
- [X] T025 [US1] 在 `court-control.component.html` 的 `@if (…; as match)` 區塊內、`.scoring-controls` 之後掛上 `<app-shot-placement-picker #shotPlacementPicker …/>`，input／output 繫結比照 `all-courts-court-block.component.html`（約 L75）：`[participants]="match.participants"`、`[scoringTeam]="pendingScoringSide()"`、`[servingTeam]`、`[servingScore]`、`[servingRosterEntryId]`、`[leftTeam]="leftTeam()"`、`(confirmed)`、`(scoreCancelled)`、`(closed)`（depends on T024）
- [X] T026 [US1] 執行 `npx ng test --watch=false` 與 `npm run lint && npx tsc --noEmit -p tsconfig.app.json`，確認 T015～T018 的測試轉綠

**Checkpoint**: US1 完成——詳細設定開啟時管理頁可記錄詳細資料，關閉時行為不變。此時即為可交付的 MVP（quickstart.md 情境 1、2、3）。

---

## Phase 4: User Story 2 - 記錯了可以當場略過或收回這一分 (Priority: P2)

**Goal**: 詳細視窗的三個出口在管理頁都能用——略過保留分數、取消收回分數、賽末點的取消一併撤銷比賽結束判定；取消失敗時顯示可讀原因。

**Independent Test**: 在管理頁對一場詳細設定開啟的比賽按「+1」，分別以「略過」與「取消這一分」結束視窗，驗證前者比分保留且無詳細資料、後者比分回到按下前。

**註**: 「略過」在 US1 完成後**已自動可用**——picker 的 `skip()` 只關閉視窗、不觸發任何 output，`onShotPlacementClosed()` 會解除凍結。本階段只需為它補測試（T027），實作工作集中在「取消這一分」。

### Tests for User Story 2

- [X] T027 [P] [US2] 在 `court-control.component.spec.ts` 新增測試：按「略過」後視窗關閉、凍結解除、`recordShotPlacement()` 未被呼叫、且未送出任何 `-1`（FR-006）
- [X] T028 [P] [US2] 在 `court-control.component.spec.ts` 新增測試：比賽仍進行中時的「取消這一分」會送出 `scoreMatch(…, side, -1)`（FR-007）
- [X] T029 [P] [US2] 在 `court-control.component.spec.ts` 新增測試：該分已讓比賽結束（加分回應的 `status !== 'in_progress'`）時，「取消這一分」改呼叫 `undoMatchCompletion(…, side)` 而非 `-1`（FR-008）
- [X] T030 [P] [US2] 在 `court-control.component.spec.ts` 新增測試：`undoMatchCompletion()` 回 `ApiError` 時，`cancelScoreErrorKey()` 被設為該錯誤的 `i18nKey`，且比分狀態不被污染（FR-009）

### Implementation for User Story 2

- [X] T031 [US2] 在 `court-control.component.ts` 新增 `readonly cancelScoreErrorKey = signal<string | null>(null)`，並在每次 `scoreThenOpenPicker()` 開始時重設為 `null`
- [X] T032 [US2] 在 `court-control.component.ts` 實作 `onShotPlacementCancelled()` 與 `runPickerAction()` 的取消分支：`point.matchCompleted` 為真時呼叫 `undoMatchCompletion()`、錯誤時 `cancelScoreErrorKey.set(error.i18nKey)`；為假時送出 `scoreMatch(…, point.side, -1)`。兩者成功後都 `clearPendingPoint()` + `changed.emit()`。行為比照 `all-courts-court-block.component.ts` 的同名方法（depends on T031）
- [X] T033 [US2] 在 `court-control.component.html` 中 T013 改好的 `@if (displayCourt()?.current_match; as match)` **之前**加入 `@if (cancelScoreErrorKey(); as key) { <p role="alert">{{ key | translate }}</p> }`，比照 `all-courts-court-block.component.html` L4-6 的既有做法（**不新增語系 key**——`ROUND_ALREADY_ADVANCED`、`NEXT_MATCH_ALREADY_STARTED`、`MATCH_NOT_COMPLETED`、`SIDE_DID_NOT_WIN_THIS_MATCH`、`ADMIN_TOKEN_INVALID` 在 `zh-TW.json` 與 `en.json` 均已存在）（depends on T031）
- [X] T034 [US2] 執行 `npx ng test --watch=false` 與 lint／型別檢查，確認 T027～T030 轉綠

**Checkpoint**: US1 + US2 皆可獨立運作（quickstart.md 情境 4）。

---

## Phase 5: User Story 3 - 詳細視窗開著的時候不會被即時更新抽掉 (Priority: P3)

**Goal**: 賽末點與他人同時操作都不會讓視窗消失；視窗關閉後畫面回到最新真實狀態；連按兩次只記一分。

**Independent Test**: 把一場比賽打到賽末點前一分，從管理頁按下決勝那一分，在視窗開啟期間讓比賽結束通知抵達，驗證視窗仍在、仍可完成記錄，且關閉後畫面顯示正確的賽後狀態。

**註**: 凍結機制本身已在 Phase 2（T011～T013）就位、US1 已在使用它，本階段補的是**邊界情況的驗證**與 `ScoreTapGuard`。實作量小、驗證量大，這是刻意的。

### Tests for User Story 3

- [X] T035 [P] [US3] 在 `court-control.component.spec.ts` 新增測試：視窗開啟期間把 `court` input 換成 `current_match: null`（模擬賽末點後父元件重抓），驗證 `displayCourt()` 仍回傳凍結狀態、模板中的 picker 未被銷毀（FR-011）
- [X] T036 [P] [US3] 在 `court-control.component.spec.ts` 新增測試：凍結期間 `displayCourt()` 的比分等於加分回應帶回的新比分，而非按下前的舊值（FR-012）
- [X] T037 [P] [US3] 在 `court-control.component.spec.ts` 新增測試：視窗以 `closed` 關閉後 `frozenCourt()` 回到 `null`，`displayCourt()` 立即等於最新的 `court()` input（FR-011 後半）
- [X] T038 [P] [US3] 在 `court-control.component.spec.ts` 新增測試：快速連按兩次「+1」時 `scoreMatch` 只被呼叫一次、picker 的 `open()` 只被呼叫一次（FR-013）

### Implementation for User Story 3

- [X] T039 [US3] 在 `court-control.component.ts` 引入 `ScoreTapGuard`（`apps/web/src/app/features/shot-placement/score-tap-guard`）：新增 `private readonly scoreGuard = new ScoreTapGuard()`，讓 `score()`、`scoreThenOpenPicker()` 與取消分支的 `-1` 都先 `tryAcquire()`、完成或失敗後 `release()`，取消分支的 `-1` 前先 `hold()`。**此改動同時修正管理頁簡易模式本來就缺少的防連點**（research.md Decision 5），是本功能唯一會觸及簡易模式的地方
- [X] T040 [US3] 檢查比分跳動動畫：確認 T012 已把 effect 改綁 `displayCourt()`，使「畫面上的數字變一次就跳一次」——凍結期間播一次（frozenCourt 被 patch 時）、解凍時不重播（research.md Decision 6）（depends on T012、T039）
- [X] T041 [US3] 執行 `npx ng test --watch=false` 與 lint／型別檢查，確認 T035～T038 轉綠

**Checkpoint**: 三個 user story 全部獨立可運作（quickstart.md 情境 5、6）。

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T042 [P] **留給使用者在自己的 checkout 上驗收**（本專案流程：使用者 pull feature 分支後自行測試）。自動化測試已涵蓋情境 1～6、8、9 的行為判定；情境 7（離線）與「A 場視窗開著時 B 場仍即時更新」需要真實瀏覽器與 Ably 連線。註：`seed_dashboard_demo` 不會建立場地與進行中的比賽，無法直接用它開出管理頁場地控制板，需自行開團→加場地→加人→排點。依 `specs/038-admin-detailed-scoring/quickstart.md` 逐一驗證情境 1～9，特別確認情境 5 的「A 場視窗開著時 B 場仍即時更新」（凍結只影響單一場地，不是整頁停更）
- [X] T043 [P] 確認**零新增語系 key**：`git diff origin/ut -- apps/web/src/assets/i18n/` 應為空（FR-020、憲章原則 VIII）
- [X] T044 [P] 確認**零 migration**：`git diff origin/ut --stat -- apps/api/alembic/` 應為空（data-model.md）
- [X] T045 比照 `court-control.component.ts` 既有的中文註解風格，補齊新增方法的註解，並在提及凍結與 `PendingPoint` 之處指向 `all-courts-court-block.component.ts` 的對應說明，避免同一套理由在四個元件各寫一次
- [X] T046 於 `apps/api` 執行完整後端測試套件（約 1,700+ 測試、20 分鐘，背景執行並把 `-rf` 輸出導到檔案），確認無迴歸
- [X] T047 撰寫 PR 說明 `specs/038-admin-detailed-scoring/pr-description.md`，依憲章「技術治理與品質關卡」說明本變更如何維持「伺服器為唯一可信來源」與「設定快照不回溯」邊界，並註明管理員權限路徑未變動

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup（Phase 1）**：無相依，可立即開始
- **Foundational（Phase 2）**：相依 Setup——**阻塞所有 user story**
- **User Stories（Phase 3–5）**：全部相依 Phase 2 完成
- **Polish（Phase 6）**：相依所有欲交付的 story

### 後端與前端可平行

Phase 2 的後端（T004～T008）與前端（T009～T014）兩條線**彼此獨立**，可由兩人同時進行。後端那條線甚至可以單獨先合併——新欄位是純新增、對現行前端零影響（contracts/schedule-api-additions.md「非變更」一節）。

### User Story Dependencies

- **US1（P1）**：Phase 2 完成後即可開始，不相依其他 story
- **US2（P2）**：**相依 US1**——取消／略過都作用在 US1 建立的 `PendingPoint` 與 picker 之上，這不是可有可無的耦合，而是同一個視窗的三個出口
- **US3（P3）**：凍結的驗證相依 US1（需要有視窗可開）；`ScoreTapGuard`（T039）則與 US1／US2 無關，可提前單獨進行

### Within Each User Story

- 測試先寫、先看它失敗，再寫實作
- 元件狀態欄位 → 方法 → 模板繫結
- `court-control.component.ts` 與 `.html` 常需成對修改，同一組任務請一起提交

### Parallel Opportunities

- T001、T002 可平行
- T004 與 T009 可平行（不同專案、不同檔案）
- T006、T007 同檔，**不可**同時編輯——標 [P] 是相對於前端那條線而言
- 各 story 的測試任務（T015～T018、T027～T030、T035～T038）在 `setup()` stub（T015）就位後彼此獨立，但**都在同一個 spec 檔**，實務上請依序寫入
- T042、T043、T044 可平行

---

## Parallel Example: Foundational Phase

```bash
# 兩條線同時開工：
Task: "T004 apps/api/app/domains/schedule/schemas.py — MatchSummary 新增 detailed_scoring_enabled"
Task: "T009 apps/web/.../schedule.models.ts — MatchSummary 與 ScoreMutationResult 補欄位"
```

---

## Implementation Strategy

### MVP First（只做 User Story 1）

1. Phase 1: Setup
2. Phase 2: Foundational（**關鍵——阻塞所有 story**）
3. Phase 3: User Story 1
4. **STOP and VALIDATE**：跑 quickstart.md 情境 1、2、3
5. 此時使用者描述的核心需求「加分的時候可以進行詳細設定」已經達成，可交付

### Incremental Delivery

1. Setup + Foundational → 後端欄位可先單獨合併
2. + US1 → 驗證 → 交付（MVP，解決統計資料缺口）
3. + US2 → 驗證 → 交付（補上按錯邊的修正路徑）
4. + US3 → 驗證 → 交付（賽末點與防連點的邊界）

### 建議的單人執行順序

本功能規模不大（後端 2 行、前端 3 個檔案實質改動），單人一輪做完即可。若要分批提交，建議切成三個 commit：**後端欄位**（T004～T008）、**前端基礎 + US1**（T009～T026）、**US2 + US3 + Polish**（T027～T047）。

---

## Notes

- [P] = 不同檔案、無相依
- 本功能**無 migration、無新端點、無新錯誤碼、無新語系 key**——若實作過程中發現需要其中任何一項，代表偏離了設計，請回頭檢查 research.md
- 判斷是否進入詳細模式一律讀 `match.detailed_scoring_enabled`（比賽快照），**絕不**讀管理頁已持有的團設定 `view.detailed_scoring_enabled`（憲章原則 III）
- `apps/web/src/app/features/shot-placement/` 下的三個檔案（picker、`PendingPoint`、`ScoreTapGuard`）只引用、不修改
- 每完成一個任務或一組邏輯相關的任務就提交一次
