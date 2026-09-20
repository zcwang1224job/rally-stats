---

description: "Task list for 039-match-point-confirm"
---

# Tasks: 決勝分二次確認

**Input**: Design documents from `/specs/039-match-point-confirm/`

**Prerequisites**: [plan.md](./plan.md)、[spec.md](./spec.md)、[research.md](./research.md)、[data-model.md](./data-model.md)、[contracts/live-state-additions.md](./contracts/live-state-additions.md)、[quickstart.md](./quickstart.md)

**Tests**: **必要，不是選配。** 憲章原則 II 明定「比分計算」屬核心領域邏輯。本功能的風險高度集中在一支純函式的邊界判斷（deuce 與 cap），所以 `core/match-point.spec.ts` 是整份清單裡最重要的一項測試。

**Organization**: 依 user story 分組。US1 在**一個**畫面走通流程即為 MVP，US3 才擴散到其餘三個畫面。

> **2026-09-20 依 `/speckit-analyze` 修訂**：補上 FR-012／FR-013／FR-014 的自動化覆蓋（T035～T037）、在 `plusPressed()` 加入重入防護（T025）、讓確認後的送分不會被防連點冷卻靜默丟棄（T026）；並移除同檔測試任務上誤標的 `[P]`、補齊相依宣告與完整路徑。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行執行（**不同檔案**、無未完成的相依）
- **[Story]**: 對應 spec.md 的 user story（US1／US2／US3）

## Path Conventions

後端 `apps/api/`、前端 `apps/web/`，路徑自 repo 根目錄起算。

## ⚠️ 實作前必讀

research.md 記錄了兩個**會造成靜默卡死、且單元測試驗不出來**的坑。動手前請先讀 Decision 1 與 Decision 3：

1. **`ConfirmDialogComponent` 沒有任何取消／關閉的 output**，而且 `<dialog>` 按 **Esc** 關閉**不會**經過元件的 `cancel()`。狀態清除必須掛在原生 `close` 事件上（T013），否則使用者按一次 Esc，那個場地的決勝分就再也按不動。
2. **絕對不要在開啟確認框前取得 `ScoreTapGuard`。** `tryAcquire()` 只有 `release()` 能解，而取消沒有 release 的時機——取消一次就永久鎖死該場地所有計分按鈕。確認流程不得在開框時取得 guard；送分時才由 `score()` 處理（見 T026 的 `force` 語意）。

---

## Phase 1: Setup（環境準備）

**Purpose**: 讓測試跑得起來並取得基準。本功能沒有專案初始化工作。

- [X] T001 [P] 建立前端測試環境：`ln -s /Users/zcwang/projects/rally-stats/apps/web/node_modules apps/web/node_modules`（worktree 沒有自己的 `node_modules`，此 symlink 已被 gitignore）
- [X] T002 [P] 建立後端測試環境：把主 checkout 的 `apps/api/.venv/bin` 加入 `PATH`（`apps/api/tests/conftest.py` 會 shell out 到 `alembic`）；並確認本機 docker 的 `infra-db-1` 容器是啟動狀態，否則 `alembic downgrade base` 會失敗
- [X] T003 取得基準：於 `apps/web` 執行 `npx ng test --watch=false` 並記下通過數（預期 798 左右）。整體 `ng test` 一律會報 1 個來自 `admin-page.component.spec.ts` 的 `NG04002` unhandled error，是既有現象

---

## Phase 2: Foundational（阻塞性前置作業）

**Purpose**: 後端送出判定所需的兩個欄位、建立共用的判定函式、替共用確認框補上關閉訊號。**本階段完成後畫面行為完全不變**——沒有任何一個「+」的行為改變，這是刻意的。

**⚠️ CRITICAL**: 三個 user story 都依賴本階段。

### 後端：兩個 schema 各加兩個欄位

- [X] T004 在 `apps/api/app/domains/schedule/schemas.py` 為 `MatchSummary` 與 `MatchLiveDetail` **各**新增 `target_score: int` 與 `cap_score: int`（**必填、不給預設值**——見 data-model.md「預設值的選擇」：給 0 會讓每一分都被算成決勝分）。**MUST NOT 加入 `deuce_threshold`**，它不參與獲勝判定（contracts 第 4 節）
- [X] T005 在 `apps/api/app/domains/schedule/service.py` 的 `build_schedule_snapshot()`（L2031，`MatchSummary(...)` 建構點約 L2064）填入 `target_score=entry[0].target_score, cap_score=entry[0].cap_score`（depends on T004）
- [X] T006 在 `apps/api/app/domains/schedule/service.py` 的 `court_live_state()`（L3890，`MatchLiveDetail(...)` 建構點約 L3907）填入 `target_score=match.target_score, cap_score=match.cap_score`（depends on T004；與 T005 同檔不同函式，請依序修改）
- [X] T007 [P] 在 `apps/api/tests/contract/test_detailed_scoring_toggle.py` 新增契約測試：`GET /groups/{group_id}/schedule` 的 `current_match` 帶出比賽快照的 `target_score` / `cap_score`（沿用該檔既有的 `_create_group_with_active_match()`）（depends on T005）
- [X] T008 [P] 在 `apps/api/tests/contract/test_court_state.py` 新增契約測試：`GET /courts/by-token/{token}/state` 的 `current_match` 同樣帶出這兩個欄位（depends on T006）
- [X] T009 在 `apps/api/tests/contract/test_detailed_scoring_toggle.py` 新增快照不回溯測試：比賽開打後調整團的比賽設定，進行中比賽的 `target_score` / `cap_score` 維持原值（憲章原則 III，FR-008）（depends on T005、T007；與 T007 同檔，請依序寫入）
- [X] T010 於 `apps/api` 執行 `python -m pytest tests/contract -k "schedule or court_state or detailed_scoring"` 與 `ruff check app/ tests/ && mypy app/`，確認後端這一層可獨立合併

### 前端：共用判定函式（本功能最關鍵的測試）

- [X] T011 [P] 新增 `apps/web/src/app/core/match-point.ts`，匯出 `isMatchPoint(scoringSideScore, opponentScore, targetScore, capScore): boolean`，語意對應後端 `service.py:3072` 的 `match_wins()`：`加分後 >= capScore || (加分後 >= targetScore && 加分後 - opponentScore >= 2)`。`targetScore` 或 `capScore` 為 `undefined` 時 MUST 回傳 `false`（舊後端相容）。**MUST NOT 使用 `deuce_threshold`**，並在檔案註解寫明原因
- [X] T012 新增 `apps/web/src/app/core/match-point.spec.ts`，把 data-model.md「邊界對照表」的 8 列逐列寫成測試：一般賽末點 20:15 ✅、還差兩分 19:15 ❌、**deuce 20:20 ❌**、deuce 後領先 21:20 ✅、**上限 29:29 ✅**、上限前一分 28:29 ❌、雙方同時（deuce）兩邊皆 ❌、雙方同時（上限）兩邊皆 ✅；另加 `undefined` 參數回傳 `false`（depends on T011）

### 前端：共用確認框補上關閉訊號

- [X] T013 在 `apps/web/src/app/features/group-admin/shared/confirm-dialog.component.ts` 新增 `readonly closed = output<void>()`，**繫結在 `<dialog>` 的原生 `(close)` 事件上**（`<dialog #dialog ... (close)="closed.emit()">`），而**不是**從 `cancel()` 方法發出——原生 close 才涵蓋確認鈕、取消鈕與 **Esc** 三條路徑（research.md Decision 1）。純新增，全專案 14 處既有使用不受影響
- [X] T014 在 `apps/web/src/app/features/group-admin/shared/confirm-dialog.component.spec.ts` 補測試：`confirm()` 會先 emit `confirmed` 再 emit `closed`（順序很重要，送分的處理函式要讀得到尚未清除的隊伍）；`cancel()` 只 emit `closed`（depends on T013）

### 前端：型別與文案

- [X] T015 [P] 在 `apps/web/src/app/features/group-admin/schedule-management/schedule.models.ts` 為 `MatchSummary` 新增 `target_score?: number` 與 `cap_score?: number`（可選，舊後端讀成 `undefined`）
- [X] T016 [P] 在 `apps/web/src/app/core/api/court-live-state.models.ts` 為 `MatchLiveDetail`（L52）新增同樣兩個可選欄位
- [X] T017 [P] 在 `apps/web/src/assets/i18n/zh-TW.json` 的 `controlPanel` 下新增 `matchPointConfirmTitle`（「確認這一分結束比賽？」）與 `matchPointConfirmBody`（「此操作無法復原，本場比賽將結束並計入戰績。」）——刻意與同區塊既有的 `endMatchConfirmBody` 同句型、相反結論
- [X] T018 [P] 在 `apps/web/src/assets/i18n/en.json` 的 `controlPanel` 下新增對應英文：`"Confirm the point that ends this match?"` 與 `"This cannot be undone. The match will end and the result will count toward records."`
- [X] T019 於 `apps/web` 執行 `npx ng test --watch=false` 與 `npm run lint && npx tsc --noEmit -p tsconfig.app.json`，確認 T012、T014 轉綠且沒有既有測試被影響

**Checkpoint**: 後端送得出判定所需欄位、判定函式已驗證、確認框有了關閉訊號；**四個畫面的「+」行為完全沒變**，可安全合併。

---

## Phase 3: User Story 1 - 簡易模式按下決勝分時先確認 (Priority: P1) 🎯 MVP

**Goal**: 未啟用詳細設定的比賽，按下會結束比賽的「+」時先跳確認框，確認後才送分、取消則什麼都不做。

**Independent Test**: 開一個未啟用詳細設定的團，把一場比賽打到 20:15，按下領先方的「+」，驗證確認框出現、內容說明後果、確認後比賽才結束；重來一次按取消，驗證比分維持 20:15 且能繼續計分。

**試點畫面**: 本階段只做**開團管理頁場地控制**（`court-control.component`）——它的 spec 檔最小最乾淨（355 行）、038 剛改過最熟悉。其餘三個畫面在 US3 複製同一套。

> Phase 3 與 Phase 4 的測試任務都寫在同一個 spec 檔，因此**一律不標 `[P]`**，請依序寫入以免互相覆蓋。

### Tests for User Story 1

- [X] T020 [US1] 在 `apps/web/src/app/features/group-admin/schedule-management/court-control.component.spec.ts` 擴充測試資料：加入一個未啟用詳細設定、比分 20:15、`target_score: 21`、`cap_score: 30` 的 court fixture（沿用該檔既有的 `setup()` 與 `plusButtons()` 輔助函式）
- [X] T021 [US1] 在 `apps/web/src/app/features/group-admin/schedule-management/court-control.component.spec.ts` 新增測試：按下領先方「+」時**不呼叫** `scoreMatch`，而是呼叫確認框的 `open()`，且 `pendingMatchPointSide()` 等於該隊（FR-001）（depends on T020）
- [X] T022 [US1] 在 `apps/web/src/app/features/group-admin/schedule-management/court-control.component.spec.ts` 新增測試：確認框 emit `confirmed` 後才呼叫 `scoreMatch(…, side, 1)`（FR-003）（depends on T020）
- [X] T023 [US1] 在 `apps/web/src/app/features/group-admin/schedule-management/court-control.component.spec.ts` 新增測試：確認框 emit `closed`（未確認）後 `pendingMatchPointSide()` 回到 `null`、`scoreMatch` 未被呼叫，且可再次按「+」重新開啟確認框（FR-004，涵蓋 Esc 的程式碼路徑）（depends on T020）

### Implementation for User Story 1

- [X] T024 [US1] 在 `apps/web/src/app/features/group-admin/schedule-management/court-control.component.ts` 新增 `readonly pendingMatchPointSide = signal<Team | null>(null)` 與 `readonly matchPointDialog = viewChild<ConfirmDialogComponent>('matchPointDialog')`（與既有的 `endMatchDialog` 並存）
- [X] T025 [US1] 在 `apps/web/src/app/features/group-admin/schedule-management/court-control.component.ts` 新增 `plusPressed(side: Team)`，三路分支（research.md Decision 6）：詳細模式 → `scoreThenOpenPicker(side)`；簡易模式且 `isMatchPoint(...)` → 設定 `pendingMatchPointSide` 並開啟確認框；其他 → `score(side, 1)`。比分與 `target_score` / `cap_score` 取自 `displayCourt().current_match`。**兩項硬性要求**：(a) 方法開頭加重入防護 `if (this.pendingMatchPointSide() !== null) { return; }`——讓 FR-014 由結構保證，而非依賴「dialog 是模態」這個 jsdom 驗不到的假設；(b) **MUST NOT 呼叫 `scoreGuard.tryAcquire()`**（research.md Decision 3），並在此處加註解說明原因（depends on T024）
- [X] T026 [US1] 在 `apps/web/src/app/features/group-admin/schedule-management/court-control.component.ts` 為既有的 `score()` 加上第三個參數 `force = false`：`force` 為真時改用 `this.scoreGuard.hold()` 取代 `tryAcquire()`（`hold()` 無條件上鎖、不會被冷卻擋下）。然後新增 `onMatchPointConfirmed()`（讀 `pendingMatchPointSide()`，非 null 則呼叫 `score(side, 1, true)`）與 `onMatchPointDialogClosed()`（`pendingMatchPointSide.set(null)`）。**`force` 的理由**：確認框是使用者刻意的第二次動作，不是誤觸；若走一般的 `tryAcquire()`，剛好落在前一次請求的 400ms 冷卻內就會被**靜默丟棄**——使用者以為結束了比賽，實際上沒送出任何分（depends on T025）
- [X] T027 [US1] 在 `apps/web/src/app/features/group-admin/schedule-management/court-control.component.html` 把兩顆「+1」的 `(click)`（L76 與 L94）改為 `plusPressed(leftTeam())` / `plusPressed(rightTeam())`；**「-1」兩顆維持不變**（FR-006）（depends on T025）
- [X] T028 [US1] 在 `apps/web/src/app/features/group-admin/schedule-management/court-control.component.html` 的 match 區塊內新增第二個確認框：`<app-confirm-dialog #matchPointDialog variant="primary" [title]="'controlPanel.matchPointConfirmTitle' | translate" [body]="'controlPanel.matchPointConfirmBody' | translate" (confirmed)="onMatchPointConfirmed()" (closed)="onMatchPointDialogClosed()" />`（depends on T026）
- [X] T029 [US1] 於 `apps/web` 執行 `npx ng test --watch=false` 與 lint／型別檢查，確認 T021～T023 轉綠

**Checkpoint**: US1 完成——管理頁的決勝分已有二次確認。此時使用者描述的核心需求在一個畫面上已達成（quickstart 情境 1）。

---

## Phase 4: User Story 2 - 只在真正該出現的時候出現 (Priority: P2)

**Goal**: 確認框不浮濫——deuce 不跳、非決勝分不跳、「-1」不跳、詳細模式不跳；只有真正會結束比賽的那一分才問。同時鎖住三條容易被忽略的 MUST：防重複、離線、伺服器判定優先。

**Independent Test**: 在一場未啟用詳細設定的比賽中從 0:0 連續計分到結束，記錄每一次「+」是否跳確認，驗證只有最後那一分跳。

**註**: 判定本身已由 T012 的純函式測試涵蓋大半；本階段補的是**元件層真的接對了**的驗證。仍在試點畫面（`court-control`）上進行，所有測試同檔，依序寫入。

### Tests for User Story 2

- [X] T030 [US2] 在 `apps/web/src/app/features/group-admin/schedule-management/court-control.component.spec.ts` 新增測試：**20:20（deuce）**按「+」**直接呼叫 `scoreMatch`、不開確認框**——21:20 只領先 1 分還沒贏（FR-009，本功能最容易寫錯的一條）（depends on T020）
- [X] T031 [US2] 在 `apps/web/src/app/features/group-admin/schedule-management/court-control.component.spec.ts` 新增測試：**29:29（上限 30）**按任一方「+」**都會開確認框**（FR-009、FR-010）（depends on T020）
- [X] T032 [US2] 在 `apps/web/src/app/features/group-admin/schedule-management/court-control.component.spec.ts` 新增測試：19:15 等非決勝分按「+」直接送分、不開確認框（FR-007）（depends on T020）
- [X] T033 [US2] 在 `apps/web/src/app/features/group-admin/schedule-management/court-control.component.spec.ts` 新增測試：任何比分下按「-1」都直接送分、不開確認框（FR-006）（depends on T020）
- [X] T034 [US2] 在 `apps/web/src/app/features/group-admin/schedule-management/court-control.component.spec.ts` 新增測試：**詳細設定開啟**且處於決勝分時，按「+」走 `scoreThenOpenPicker`（038 的詳細記錄視窗），**不**開本功能的確認框（FR-005、SC-006）（depends on T020）
- [X] T035 [US2] 在 `apps/web/src/app/features/group-admin/schedule-management/court-control.component.spec.ts` 新增測試：決勝分時**連按兩次「+」只開一個確認框**（`open()` 恰被呼叫一次），確認後 `scoreMatch` 也只被呼叫一次（**FR-014**，驗證 T025 的重入防護；jsdom 沒有真正的模態行為，所以這條必須靠程式碼層防護才過得了）（depends on T025、T020）
- [X] T036 [US2] 在 `apps/web/src/app/features/group-admin/schedule-management/court-control.component.spec.ts` 新增測試：確認框開啟中把 `connectionState` 轉為非 `connected`，按確認**不得送分**（**FR-012**——「+」本身已由既有 `[disabled]` 涵蓋，這條補的是「框開著時斷線」那段空窗）（depends on T020）
- [X] T037 [US2] 在 `apps/web/src/app/features/group-admin/schedule-management/court-control.component.spec.ts` 新增測試：確認後伺服器回傳 `status: 'in_progress'`（該分結果上沒有結束比賽）時，元件**不得**自行把比賽標記為結束，一切以回應為準（**FR-013**）（depends on T020）
- [X] T038 [US2] 執行 `npx ng test --watch=false` 與 lint／型別檢查，確認 T030～T037 轉綠

**Checkpoint**: 試點畫面的正負向行為與三條容易漏掉的 MUST 都已鎖住，可安全複製到其餘畫面。

---

## Phase 5: User Story 3 - 四個計分畫面行為一致 (Priority: P3)

**Goal**: 把 US1 + US2 的同一套搬到其餘三個計分畫面，文案與行為完全一致。

**Independent Test**: 同一場未啟用詳細設定、來到決勝分的比賽，分別從四個畫面按「+」，驗證四者都跳確認框且行為相同。

**注意各畫面的差異**：
- `control-panel` 與 `all-courts-court-block` 用 `leftTeam()` / `rightTeam()`（可左右交換）
- `scoreboard` 的「+」直接寫死 `'A'` / `'B'`（不交換），所以是 `plusPressed('A')` / `plusPressed('B')`
- 比分來源各不相同：control-panel 讀 `frozenState() ?? liveState()`、all-courts 讀 `displayState()`、scoreboard 讀自己的 live state——請比照各元件既有 `score()` 取比分的方式
- **每個畫面都要一併帶上 T025 的重入防護與 T026 的 `force` 語意**，不要只複製快樂路徑

### 單一場地控制頁面

- [X] T039 [US3] 在 `apps/web/src/app/features/control-panel/control-panel.component.ts` 依 T024～T026 的同一套加入 `pendingMatchPointSide`、`matchPointDialog`、含重入防護的 `plusPressed()`、`score()` 的 `force` 參數與兩個處理函式
- [X] T040 [US3] 在 `apps/web/src/app/features/control-panel/control-panel.component.html` 把 L117 與 L131 的「+」改為 `plusPressed(leftTeam())` / `plusPressed(rightTeam())`，並加入 `#matchPointDialog` 確認框（depends on T039）
- [X] T041 [US3] 在 `apps/web/src/app/features/control-panel/control-panel.component.spec.ts` 補測試：決勝分開確認框、確認後送分、deuce 不跳、詳細模式走 picker、連按兩次只開一個（depends on T040）

### 全場地控制板

- [X] T042 [US3] 在 `apps/web/src/app/features/control-panel/all-courts/all-courts-court-block.component.ts` 加入同一套（比分讀 `displayState()`）
- [X] T043 [US3] 在 `apps/web/src/app/features/control-panel/all-courts/all-courts-court-block.component.html` 把 L20 與 L60 的「+」改為 `plusPressed(...)`，並加入 `#matchPointDialog` 確認框（depends on T042）
- [X] T044 [US3] **新增** `apps/web/src/app/features/control-panel/all-courts/all-courts-court-block.component.spec.ts`——**這個元件目前完全沒有 spec 檔**（整個 all-courts 資料夾都沒有）。以 `court-control.component.spec.ts` 為範本建立最小測試骨架，涵蓋決勝分開確認框、確認後送分、deuce 不跳三條（depends on T043）

### 記分板

- [X] T045 [US3] 在 `apps/web/src/app/features/scoreboard/scoreboard.component.ts` 加入同一套（注意：此畫面不交換左右，`plusPressed` 收 `'A'` / `'B'`）
- [X] T046 [US3] 在 `apps/web/src/app/features/scoreboard/scoreboard.component.html` 把 L117 與 L126 的「+」改為 `plusPressed('A')` / `plusPressed('B')`，並加入 `#matchPointDialog` 確認框（depends on T045）
- [X] T047 [US3] 在 `apps/web/src/app/features/scoreboard/scoreboard.component.spec.ts` 補測試：決勝分開確認框、確認後送分、deuce 不跳（depends on T046）
- [X] T048 [US3] 執行 `npx ng test --watch=false` 與 lint／型別檢查，確認四個畫面的測試全綠

**Checkpoint**: 四個畫面行為一致（quickstart 情境 6）。

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T049 [P] 確認語系檔**只新增 4 個 key**：`git diff origin/ut -- apps/web/src/assets/i18n/` 應只看到 `matchPointConfirmTitle` 與 `matchPointConfirmBody` 各兩個語言（FR-015）
- [X] T050 [P] 確認**零 migration**：`git diff origin/ut --stat -- apps/api/alembic/` 應為空
- [ ] T051 **真實瀏覽器手動驗證（單元測試驗不出來）**：依 quickstart.md 情境 7 與 8——用**鍵盤 Esc** 關掉確認框後再按一次「+」必須能正常開啟；Esc 取消後「-1」與「+」都必須仍然有反應。jsdom 沒有實作 `<dialog>`，這兩條只能在真的瀏覽器上看（research.md 風險註 1、2）
- [ ] T052 依 `specs/039-match-point-confirm/quickstart.md` 逐一手動驗證情境 1～11，特別是情境 2（deuce 不跳）、情境 3（上限跳）與情境 10（確認期間比分被改）
- [X] T053 於 `apps/api` 執行完整後端測試套件（約 1,750 測試、20 分鐘，背景執行並把 `-rf` 輸出導到檔案），確認無迴歸
- [X] T054 撰寫 PR 說明 `specs/039-match-point-confirm/pr-description.md`，依憲章「技術治理與品質關卡」說明本變更如何維持「伺服器為唯一可信來源」（前端判定只決定要不要問，不參與實際判定）與「設定快照不回溯」邊界，並說明這是憲章原則 V 在既有缺口上的落實

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup（Phase 1）**：無相依
- **Foundational（Phase 2）**：相依 Setup——**阻塞所有 user story**
- **US1（Phase 3）**：相依 Phase 2
- **US2（Phase 4）**：相依 US1（在同一個試點畫面上補負向與 MUST 驗證）
- **US3（Phase 5）**：相依 US1 + US2（複製的是已驗證過的那一套）
- **Polish（Phase 6）**：相依所有 story

### 後端與前端可平行

Phase 2 的後端（T004～T010）與前端（T011～T019）兩條線彼此獨立，可同時進行。後端那條線可以單獨先合併——新欄位純新增、對現行前端零影響。

### User Story Dependencies

- **US1（P1）**：Phase 2 完成後即可開始
- **US2（P2）**：**相依 US1**——它驗證的是 US1 那段三路分支的負向行為，不是獨立功能
- **US3（P3）**：**相依 US1 + US2**——刻意如此。先在一個畫面把流程與邊界都驗證過，再複製三份；反過來做會把同一個錯誤複製四次

### Within Each User Story

- 測試先寫、先看它失敗，再寫實作
- 元件狀態 → 方法 → 模板繫結
- 每個元件的 `.ts` 與 `.html` 常需成對修改，請一起提交

### Parallel Opportunities

- T001、T002 可平行
- T004（後端 schema）與 T011（前端純函式）可平行——不同專案
- T007 與 T008 分屬兩個測試檔，可平行；T009 與 T007 同檔，須依序
- T015～T018 四個任務分屬四個不同檔案，可平行
- **Phase 3 與 Phase 4 的測試任務全部落在同一個 spec 檔，皆不可平行**
- Phase 5 的三個畫面（control-panel / all-courts / scoreboard）彼此獨立，三人可同時進行
- T049、T050 可平行

---

## Parallel Example: Foundational Phase

```bash
# 兩條線同時開工：
Task: "T004 apps/api/.../schemas.py — MatchSummary 與 MatchLiveDetail 各加 target_score / cap_score"
Task: "T011 apps/web/src/app/core/match-point.ts — isMatchPoint() 純函式"
```

## Parallel Example: User Story 3

```bash
# 三個畫面互不相干：
Task: "T039-T041 control-panel"
Task: "T042-T044 all-courts-court-block（含新建 spec 檔）"
Task: "T045-T047 scoreboard"
```

---

## Implementation Strategy

### MVP First（Phase 1–3）

1. Setup
2. Foundational（**關鍵——阻塞所有 story**）
3. US1 在管理頁場地控制走通
4. **STOP and VALIDATE**：跑 quickstart 情境 1，並**務必**做 T051 的 Esc 手動檢查
5. 此時「決勝分會先確認」在一個畫面上已成立，可交付

### Incremental Delivery

1. Setup + Foundational → 後端欄位可先單獨合併
2. + US1 → 驗證 → 交付（MVP）
3. + US2 → 負向行為與三條 MUST 鎖住 → 交付
4. + US3 → 四個畫面一致 → 交付

### 建議的提交切分

四個 commit：**後端欄位**（T004～T010）、**共用基礎**（T011～T019：純函式 + 確認框 output + 型別 + 文案）、**試點畫面 US1+US2**（T020～T038）、**其餘三畫面 + Polish**（T039～T054）。

---

## Notes

- [P] = 不同檔案、無相依
- 本功能**無 migration、無新端點、無新錯誤碼**；語系檔**只加 4 個 key**
- 判定一律用 `match.target_score` / `match.cap_score`（比賽快照），**絕不**讀團的當下設定
- `isMatchPoint()` **絕不**使用 `deuce_threshold`——後端根本不會送它過來
- `plusPressed()` **絕不**在開啟確認框時取得 `ScoreTapGuard`；送分才由 `score()` 處理
- 每完成一個任務或一組邏輯相關的任務就提交一次
