# Tasks: 休息／準備切換

**Input**: Design documents from `/specs/037-rest-ready-toggle/`

**Prerequisites**: plan.md、spec.md、research.md、data-model.md、contracts/（3 份）、quickstart.md（皆已存在）

**Tests**：依 `plan.md` Constitution Check（原則 II），本功能**直接修改輪替（排點）演算法**——憲章點名的核心邏輯。兩個純函式的單元測試 MUST **先於**實作完成並確認為失敗（紅燈）；叫場、替補、`wait_count` 凍結、自動換輪各 MUST 有正常路徑與邊界測試；兩支新端點 MUST 有契約測試；MUST 有一條含休息的「開團 → 加入 → 排點 → 計分」整合測試。本檔案的測試任務為強制項，非選用。**回歸的底線**：沒有人休息時，所有既有排程測試 MUST 不改斷言全數通過。

**Organization**：依 spec.md 之 4 個 User Story 分階段。US1、US2、US3 同為 P1；階段順序採 **US1 → US3 → US2 → US4**，理由：
- **US3 MUST 與 US1 同一次上線**——少了它，休息就是插隊的捷徑（plan.md「建議實作順序」）。US1＋US3 是第一個可以安全上線的組合。
- US2 與 US3 的後端互不相依，可由兩人平行；US2 的工作量最大，放在後面不會擋住 US1＋US3 的交付。
- US4（P2）只是同一個動作的另一個入口，依賴 US1 的服務函式與切換按鈕元件。

## Format: `[ID] [P?] [Story] Description`

- **[P]**：可平行執行（不同檔案、無相依關係）
- **[Story]**：對應 spec.md 的 US1–US4；Setup／Foundational／Polish 階段任務無此標籤
- 每項任務皆附精確檔案路徑

## Path Conventions

沿用 `plan.md` Project Structure：後端 `apps/api/`，前端 `apps/web/src/`。後端測試指令一律於 `apps/api` 執行；從 `.claude/worktrees/` 執行時把主 checkout 的 `apps/api/.venv/bin` 放到 `PATH`（quickstart.md）。

---

## Phase 1: Setup

- [ ] T001 新增 migration `apps/api/alembic/versions/<rev>_rest_state.py`（`down_revision = "b5c8e2f41a07"`）：`roster_entries` 加 `resting_since TIMESTAMP WITH TIME ZONE NULL` 與 `played_credit INTEGER NOT NULL`（`server_default="0"`）；新表 `roster_rest_periods`（`id UUID PK`、`roster_entry_id UUID NOT NULL FK → roster_entries.id` 含索引、`group_id UUID NOT NULL FK → groups.id` 含索引、`started_at`／`ended_at TIMESTAMP WITH TIME ZONE NOT NULL`、`CHECK (ended_at >= started_at)`）。`downgrade()` 完整還原。以 `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` 驗證可往返；`alembic heads` 只有一個 head（data-model.md「儲存變更」）
- [ ] T002 於 `apps/api/app/domains/roster/models.py`：`RosterEntry` 新增 `resting_since: Mapped[datetime | None]` 與 `played_credit: Mapped[int]`（`default=0`、`server_default="0"`），各附一行註解指向 research.md Decision 1／4；同檔新增 `class RosterRestPeriod(Base)`（欄位同 T001）。確認 `alembic check`（或 autogenerate 的空 diff）顯示 model 與 migration 一致（depends on T001）

---

## Phase 2: Foundational（Blocking Prerequisites）

**Purpose**：兩個純函式（公平性規則的全部數學）與新測試共用的 helper。此階段完成後**沒有任何行為改變**。

**⚠️ CRITICAL**：T004 是 US3 的前提；T005 是所有經資料庫的新測試的前提。

- [ ] T003 Unit test（**先紅燈**）：新增 `apps/api/tests/unit/domains/schedule/test_rest_histories.py`（無資料庫）。`player_histories(matches, rest_periods)`：(a) 不傳 `rest_periods`（或傳空 dict）時，對一組含多場比賽的輸入，結果與現有實作**逐位相同**（把現有 `test_schedule_fairness.py` 中任一組輸入抄來對照）；(b) 球員上一場結束後有 5 場比賽上場，其中 3 場的 `started_at` 落在他的休息區間 `[start, end)` 內 → `rest == 2`；(c) 區間之前與之後上場的比賽照計；(d) 同一位球員兩段不重疊的區間都被扣除；(e) 進行中的區間 `(start, None)` 扣除 `start` 之後的全部；(f) 區間開始於他還在場上時（`start < last_end`）→ 只扣 `last_end` 之後、區間內的比賽，不為負；(g) 邊界：`started_at == start` 算在區間內、`started_at == end` 不算；(h) `played` 與 `run` 完全不受 `rest_periods` 影響；(i) 別人的區間不影響他。`returning_played_credit(own_effective: int, others_effective: Sequence[int]) -> int`：(j) 下中位數——`others=[2,4,6,8]`、`own=1` → `3`（目標 4）；`others=[2,4,6]`、`own=1` → `3`；(k) `others=[]` → `0`；(l) `own` 已 ≥ 目標 → `0`；(m) 0 場的新人不把目標拉到 0：`others=[0,5,6,7]`、`own=1` → `4`；(n) 回傳值恆為非負整數。確認全部紅燈
- [ ] T004 於 `apps/api/app/domains/schedule/algorithms.py`：`player_histories()` 新增選填參數 `rest_periods: Mapping[uuid.UUID, Sequence[tuple[datetime, datetime | None]]] | None = None`，只改 `rest` 的計算（data-model.md「坐著等的場數」）；`started_between()` 維持原樣，另寫一個只在有區間時才走的計數分支，讓沒有區間的球員走原本的 `bisect` 路徑。新增純函式 `returning_played_credit()`（data-model.md「有效場數」）。更新 `PlayerHistory` 的 docstring：`played` 可能含 `played_credit`、`rest` 不含休息期間。使 T003 全綠；`tests/unit/domains/schedule/test_schedule_fairness.py`、`test_fair_rotation_stage1.py`、`test_peek_next_queued_match.py` 不改斷言全綠（depends on T003）
- [ ] T005 [P] 新增 `apps/api/tests/unit/domains/schedule/_rest_helpers.py`（非測試檔，供本功能的新測試共用；比照 `test_pull_queued_match_conflict.py` 既有的 `_make_group`／`_make_court` 寫法）：`make_group(session, *, match_mode, scheduling_mechanism, partner_source="auto", continuous_rotation=False, auto_next_round=False)`、`make_courts(session, group, n)`、`make_players(session, group, n, *, guest=True) -> list[RosterEntry]`、`set_resting(session, entry, since=None)`（直接寫欄位，不經服務層——讓排程測試不依賴 `set_rest_state()`）、`finish_match(session, match)`（把一場 `in_progress` 設為 `completed` 並呼叫既有的 `_advance_after_terminal()`）。不含任何斷言（depends on T002）

**Checkpoint**：純函式全綠；既有測試零變動；尚無任何行為或畫面變化。

---

## Phase 3: User Story 1 - 球員自己切換休息／準備（Priority: P1）🎯 MVP（須與 US3 一起上線）

**Goal**：球員在自己的畫面上一鍵切換；休息中的人不進任何新產生的場次；所有人即時看到；狀態跨重新整理與換輪保留。

**Independent Test**：quickstart.md 情境 1–3、10——公平輪替雙打 8 人 1 面場地，一人按休息後連續數輪都不在新場次裡；按準備好了之後重新成為候選；他人無法切換他的狀態。

### 後端

- [ ] T006 [P] [US1] 服務層測試（**先紅燈**）：新增 `apps/api/tests/unit/domains/schedule/test_rest_round_generation.py`（用 T005 的 helper）。對四種自動排程方式各一組：(a) 公平輪替雙打 9 人 2 面場地、1 人休息 → `plan_next_round()` 產生的場次不含他；(b) 單打循環 5 人、1 人休息 → 場次數為 4 人的循環賽（6 場），不含他；(c) 個人全混搭 6 人、1 人休息 → 不含他；(d) 固定搭檔＋`partner_source="auto"` 8 人、1 人休息 → 不含他，其餘 7 人照既有規則組隊（一人輪空）；(e) 固定搭檔＋`partner_source="manual"`：有 `Partnership(A,B)`，A 休息 → A 與 **B 都**沒有場次，且 B **沒有**被自動補位臨時配給別的落單者（research Decision 2）；(f) 準備中的人不足一場（雙打剩 3 人）→ 不產生任何場次、不拋例外；(g) 換輪前後休息者的 `resting_since` 不變（FR-006）；(h) `build_round_matches_list()` 的 `sitting_out` 不含休息者；(i) **沒有人休息時**，對同一亂數種子，(a)–(d) 產生的場次與移除本功能前相同（以 `random.seed` 固定後比對參賽者集合）。確認 (a)–(h) 紅燈
- [ ] T007 [P] [US1] 服務層測試（**先紅燈**）：新增 `apps/api/tests/unit/domains/schedule/test_rest_state.py`。`set_rest_state(session, group, entry, resting=…)`：(a) 準備中 → 休息：`resting_since` 為現在、回傳 `changed=True`；(b) 已休息再設休息 → `changed=False`、`resting_since` **不變**、不寫入 `roster_rest_periods`、不發布事件（以 monkeypatch 過的 `publish` 計數）；(c) 休息 → 準備中：`resting_since` 為 `None`、`roster_rest_periods` 多一列且 `started_at` 等於先前的 `resting_since`、`ended_at >= started_at`；(d) `status` 為 `left`／`kicked` 的列 → `ApiError("ROSTER_ENTRY_NOT_FOUND")` 404；(e) 別的團的列 → 同一個錯誤；(f) `group.status != "active"` → `GROUP_DISBANDED` 409；(g) 正在場上時設休息 → 該場 `status` 仍為 `in_progress`、參賽者不變，回傳 `currently_playing=True`（FR-014）；(h) 設休息的當下，他在當前這一輪的 `queued` 場次的參賽者與 `status` **完全不變**（FR-013）；(i) 成功且 `changed=True` 時發布一次 `roster.restChanged` 到 `group_notifications_channel`，payload 為 `{roster_entry_id, nickname, resting}`；(j) 休息中的人離開（`handle_member_left()`）後重新加入 → 新列 `resting_since is None`（FR-001、FR-030）。確認紅燈
- [ ] T008 [US1] 於 `apps/api/app/domains/schedule/service.py`：新增模組層級常數 `_IS_READY = RosterEntry.resting_since.is_(None)`（附註解指向 research Decision 2），加進 `_get_active_roster_for_selection()`、`_get_active_roster_ids()`、`_get_active_roster_ordered()` 的 `where`；`apply_wait_count_updates()` 的第二句 UPDATE（未被挑中者 +1）加上 `_IS_READY`。**先 grep 這三個函式的所有呼叫端**（約 15 處），逐一確認「只看準備中的人」是該處要的語意；`build_schedule_snapshot()` 的名單查詢與 `manual_assign()`／`change_match_player()` 的驗證 MUST 不受影響（它們不經過這三個函式——若有經過，改為直接查詢）。`_resolve_manual_fixed_partner_teams()`：任一人休息的 `Partnership` 整隊略過，且其中準備中的那一位 MUST NOT 進入自動補位的候選。`build_round_matches_list()` 的 `sitting_out` 排除休息者。使 T006 全綠；`tests/unit/domains/schedule/` 既有測試不改斷言全綠（depends on T006）
- [ ] T009 [P] [US1] 於 `apps/api/app/domains/schedule/schemas.py`：新增 `RestStateRequest(resting: bool, guest_session_token: str | None = None)`、`RestStateResponse(roster_entry_id: str, resting: bool, resting_since: datetime | None, currently_playing: bool, changed: bool)`；`RosterScheduleStatus` 新增 `resting: bool = False`、`resting_since: datetime | None = None`、`partner_roster_entry_id: str | None = None`（後者由 T026 填值，本任務只加欄位）（contracts/rest-state-api.md、schedule-api-additions.md）
- [ ] T010 [US1] 新增 `apps/api/app/domains/schedule/rest.py`（import `service`；`service` MUST NOT import 本模組）：`async def set_rest_state(session, group, entry, *, resting: bool) -> RestStateResponse`。本任務實作 research Decision 7 的步驟 1、2 的狀態寫入（含寫入 `RosterRestPeriod`）、3（commit）、4（`service.refresh_courts_after_roster_change()`）、6（`publish` 到 `group_notifications_channel`，事件名 `roster.restChanged`）；步驟 1 取團列鎖的寫法比照 `_seat_waiting_players_on_court()`（`select(Group.id)…with_for_update()`）。`played_credit` 調整留待 T017、中途加入者流程留待 T026、自動換輪檢查留待 T027——各留一行 `# 037 T0xx` 的位置註解。`build_schedule_snapshot()` 填入 `resting`／`resting_since`。使 T007 全綠（depends on T007、T008、T009）
- [ ] T011 [US1] 本人端點：於 `apps/api/app/domains/group/service.py` 新增 `set_own_rest_state(session, group, roster_entry_id, *, resting, guest_session_token, member_id)`——擁有權檢查與 `leave_group()`（約 L2029–2057）**逐行相同**（把該段抽成模組內的 `_require_owned_active_entry()` 並讓 `leave_group()` 也改用它，避免兩份實作漂移），通過後委派 `schedule.rest.set_rest_state()`。於 `apps/api/app/domains/group/router.py` 緊接 `POST …/leave` 之後新增 `PUT /{group_id}/roster/{roster_entry_id}/rest-state`（`Depends(optional_member)`、`response_model=RestStateResponse`），docstring 列出錯誤代碼。`tests/` 中 `leave_group` 的既有測試不改斷言全綠（depends on T010）
- [ ] T012 [P] [US1] 契約測試：新增 `apps/api/tests/contract/test_rest_state_endpoints.py` 的本人端點部分——200 的回應形狀；會員本人、訪客本人（token 在 body）成功；**他人會員、他人的訪客 token、完全不帶身分、已離開的列、別的團的列、不存在的 uuid——六種拒絕的 status code 與 response body MUST 逐位相同**（404 `ROSTER_ENTRY_NOT_FOUND`，FR-004）；同時帶會員身分與訪客 token 時以 token 為準；連送兩次 `{"resting": true}` → 第二次 200 且 `changed: false`；團已解散 → 409。另擴充 `apps/api/tests/contract/test_member_schedule.py`，並於本檔對管理員的 `GET /groups/{id}/schedule` 加同樣的斷言（該端點目前沒有專屬的契約測試檔）：`roster[]` 每列含 `resting`／`resting_since`／`partner_roster_entry_id`，休息中的人**仍在** `roster[]` 裡（depends on T011）

### 前端

- [ ] T013 [P] [US1] 型別與 service：於 `apps/web/src/app/features/group-admin/schedule-management/schedule.models.ts` 的 `RosterScheduleStatus`（約 L64）新增 `resting: boolean`、`resting_since: string | null`、`partner_roster_entry_id: string | null`，並新增 `RestStateResponse`；於 `apps/web/src/app/features/group-member-view/group-member-view.service.ts` 新增 `setOwnRestState(groupId, resting): Observable<RestStateResponse>`——以既有的 `resolveRosterEntryId()`（約 L86）取得自己的列，身分帶法與同檔的 `leaveGroup()`（約 L98–108）相同（會員優先、否則訪客 token 放 body）。更新該 service 既有 spec 的 fixture 補上新欄位的預設值
- [ ] T014 [US1] 新增 `apps/web/src/app/core/rest-toggle-button/rest-toggle-button.component.{ts,html,scss,spec.ts}`（`app-rest-toggle-button`；inputs：`resting: boolean`、`currentlyPlaying: boolean = false`、`pending: boolean = false`、`compact: boolean = false`（管理頁名單列用）；output：`toggled: boolean`——發出**目標狀態**）。原生 `<button type="button">`、`[attr.aria-pressed]="resting"`、`pending` 時 `disabled`；文字為 `restToggle.rest`（「我要休息」）／`restToggle.ready`（「準備好了」），圖示＋文字；`resting && currentlyPlaying` 時在按鈕下方顯示 `restToggle.afterThisMatch`（「打完這一場後開始休息」，FR-014）。不含確認框（FR-002）。同時於 `apps/web/src/assets/i18n/zh-TW.json` 與 `en.json` 新增 `restToggle.*` 與 `scheduleManagement.restingBadge`（「休息中」）。spec：兩種狀態的文字與 `aria-pressed`、`pending` 停用、`afterThisMatch` 的出現條件、點擊發出目標狀態；另比照 `player-insights.component.spec.ts` 讀入兩份語系檔，斷言本功能**目前已新增**的 key 在兩邊都存在（後續任務新增 key 時同步加進這條測試的清單）
- [ ] T015 [US1] 於 `apps/web/src/app/features/group-member-view/member-schedule/member-schedule.component.{ts,html}`：名單區（html 約 L68–78）每一列在既有的 `currently_playing`／`wait_count` 標記旁，`resting` 時顯示「休息中」標記（圖示＋文字，FR-008）；**只有自己的那一列**（以 `resolveRosterEntryId()` 的結果比對）顯示 `<app-rest-toggle-button>`，另在名單上方放一個同樣的按鈕讓球員不必找自己的列；`toggled` → `setOwnRestState()`，成功後以回應更新自己的列並 `load()`，失敗時還原並顯示 `error.i18nKey | translate`；`pending` 期間停用。把 `roster.restChanged` 加入 group 頻道的訂閱事件清單（ts 約 L19–20），處理方式同既有事件＝`load()`。擴充 `member-schedule.component.spec.ts`：標記的出現、按鈕只在自己的列、成功／失敗流程、收到 `roster.restChanged` 會重抓（depends on T013、T014）

**Checkpoint**：休息者不進新的一輪，所有人即時看到（quickstart 情境 1–3、10）。**尚不可上線**——回來的人目前會因為 `rest` 與 `played` 而得到優先權，由 Phase 4 處理。

---

## Phase 4: User Story 3 - 休息不能變成插隊的捷徑（Priority: P1）

**Goal**：休息期間等待場數凍結；回來時順位等同「去休息之前」，不因久未上場或總場數少而優先。

**Independent Test**：quickstart.md 情境 8——公平輪替雙打 9 人 1 面場地連續輪轉，A 在等待場數為 1 時休息、其餘人連打 6 場後回來：等待場數仍為 1、順位不優於等待場數更高者、之後的上場次數與其他人相當。

- [ ] T016 [P] [US3] 服務層測試（**先紅燈**）：新增 `apps/api/tests/unit/domains/schedule/test_rest_fairness.py`。(a) `apply_wait_count_updates()`：休息者未被挑中 → `wait_count` 不變（含 `NULL` 維持 `NULL`）；(b) 連續輪轉 `_seat_waiting_players_on_court()`：休息者不被挑中、也不在 `passed_over` 裡被 +1（US3 情境 4）——*T008 已使 (a)(b) 成立，此處把它們釘住*；(c) `_get_player_histories()`：A 上一場結束後休息、期間 4 場比賽上場、回來後又 1 場上場 → `rest == 1`（紅燈）；進行中的休息同樣扣除；(d) 回來時的 `played_credit`：其他準備中球員的實際場數為 `[4,5,6,7]`、A 為 1 → `set_rest_state(resting=False)` 後 A 的 `played_credit == 4`、`_get_player_histories()[A].played == 5`（紅燈）；(e) A 第二次休息回來，其他人有效場數中位數為 9、A 有效場數為 8 → credit 只加 1（累加而非覆蓋）；(f) 計算目標時**排除**休息中的人與 `left`／`kicked` 的人，**包含**其他人各自的 credit；(g) 從未上場的人休息後回來 → `wait_count` 仍為 `NULL`、不在 `_get_player_histories()` 結果裡（他確實是新人，FR-026 不適用）；(h) 已上場過的人回來 → `wait_count` 等於休息前的值，MUST NOT 變成 `NULL`（FR-024、FR-026）；(i) 排行榜 `build_group_standings()` 對同一批比賽的結果不因任何人的 `played_credit` 而改變（FR-028）
- [ ] T017 [US3] 於 `apps/api/app/domains/schedule/service.py` 的 `_get_player_histories()`：多一個查詢載入該團的 `RosterRestPeriod`（`WHERE group_id = …`）與 `resting_since IS NOT NULL` 的進行中區間，組成 `rest_periods` 傳給 `player_histories()`；再載入該團 `played_credit > 0` 的列，把回傳的 `PlayerHistory.played` 加上 credit（`_replace`）；從未上場的人維持不在結果裡。docstring 說明這是 credit 進入排程的**唯一入口**。於 `apps/api/app/domains/schedule/rest.py` 的 T010 預留位置實作切回準備中時的調整：以 `_get_player_histories()` 取得所有人的有效場數、以 `_get_active_roster_ordered()`（已只含準備中）扣掉本人得到 `others`、呼叫 `returning_played_credit()`、`UPDATE … SET played_credit = played_credit + :delta`。**順序**：MUST 在清除本人的 `resting_since` **之前**計算 `others`，或明確排除本人。使 T016 全綠（depends on T004、T010、T016）
- [ ] T018 [US3] 模擬測試（SC-004）：擴充 `apps/api/tests/integration/test_schedule_fairness_simulation.py`——於既有的 `Scenario` 增加選填欄位 `rest_probability: float = 0.0` 與 `return_probability: float = 0.0`；`_run()` 在每場比賽結束後，以該次 run 的亂數種子決定是否讓某位閒置且準備中的球員休息（經 `set_rest_state()`）、是否讓某位休息中的球員回來，並在 `Report` 記錄每位球員每次休息前後的 `wait_count`、回來後第一次挑人時的候選排序、回來後的上場次數。新增一個情境（公平輪替雙打、10 人、2 面場地、連續輪轉、`rest_probability=0.15`、`return_probability=0.3`、3 個種子）與斷言：(a) 每一次休息前後 `wait_count` 差值為 0；(b) 回來後第一次 `stage1_select_players()` 的排序中，沒有任何「`wait_count` 嚴格大於他、且整段期間一直準備中」的球員排在他之後；(c) 回來後到模擬結束，他的上場率（上場數 ÷ 期間內的比賽數）不高於「整段期間一直準備中」球員的上場率中位數 + 0.10——**先在 T017 完成前執行一次，確認 (c) 會失敗**（證明這條斷言確實抓得到 research Decision 4 的問題），把失敗時的數字寫進測試的 docstring。既有情境（兩個機率皆為 0）的結果 MUST 逐位不變（depends on T017）

**Checkpoint**：US1＋US3 可一起上線——休息者不進新場次，且回來不插隊。已排好的場次此時的行為：照原樣被叫到（與上線前相同），由 Phase 5 改善。

---

## Phase 5: User Story 2 - 已排好的場次在有人休息時的處理（Priority: P1）

**Goal**：按休息的當下不改場次；叫場先叫沒有休息者的；輪到時替補模式找「現在就能上場」的替補、保留模式等他回來；回來立即叫場；被休息卡住的輪次能自動換輪；畫面說得清楚每一場的狀況。

**Independent Test**：quickstart.md 情境 4–7——個人全混搭、單打循環、固定搭檔各一團，驗證場次原封不動、預告與實際一致、替補三條件、保留與立即叫場、自動換輪與兩個守門條件。

### 後端——叫場與替補

- [ ] T019 [P] [US2] 服務層測試（**先紅燈**）：新增 `apps/api/tests/unit/domains/schedule/test_rest_call_up.py`。(a) 排隊中有「含休息者」與「不含」兩種場次，前者叫場順序在前 → `pull_queued_match_for_court()` 叫的是後者（FR-015）；(b) 單打循環，只剩含休息者的場次 → 回 `None`、場次 `status`／參賽者不變（FR-018）；(c) 固定搭檔，隊伍中一人休息 → 同 (b)；(d) 個人全混搭，只剩含休息者 A 的場次，有一位準備中、不在該場、不在場上的 S → 該場上場，`MatchParticipant` 中 A 的列變成 S（**同一個 `team`**），其餘三人不變（FR-016）；(e) 替補三條件各一個反例：候選人休息中／已在該場／正在別的場地 `in_progress` → 不被選；三種人都排除後沒有候選 → 回 `None`、場次原封不動（FR-017）；(f) 一場有兩位休息者 → 兩位都換，且兩位替補不同人；只找得到一位 → 整場不動；(g) 替補的挑選順序：本輪出賽最少 → 與留下者交手最少 → 最早加入（各用一組只差該鍵的候選）；(h) 公平輪替雙打：替補者 `wait_count` 歸零、休息者 `wait_count` 不變；個人全混搭：兩者 `wait_count` 皆不變（FR-027）；(i) `PairHistory` 記在替補者與留下的三人之間，不含休息者；(j) `peek_next_queued_match()` 與隨後的 `pull_queued_match_for_court()` 對同一狀態選到同一場、同一組替補，且 `peek` 之後資料庫中該場的參賽者**仍是原本的四人**（FR-015）；(k) A 在 `peek` 之後、`pull` 之前回來 → `pull` 叫的是原陣容；(l) A 的其他排隊場次不因其中一場被替補而改變（逐場處理）；(m) `start_planned_round()` 走同一套規則；(n) **併發**：兩面場地同時空出、排隊中兩場各含一位休息者、只有一位可用替補 → 以兩個 session 並行呼叫（比照 `test_pull_queued_match_conflict.py`／`test_next_round_locking.py` 的寫法），結果 MUST 是一場上場、另一場回 `None`，該替補不會同時出現在兩場 `in_progress` 裡
- [ ] T020 [US2] 於 `apps/api/app/domains/schedule/service.py`：新增 `@dataclass(frozen=True) class NextMatchChoice`（`match: Match`、`substitutions: tuple[tuple[uuid.UUID, uuid.UUID], ...]`——（休息者, 替補）。`_choose_next_queued_match()` 回傳型別改為 `NextMatchChoice | None`：(1) 既有候選查詢加上「場次內沒有 `resting_since IS NOT NULL` 的參賽者」的 `NOT EXISTS`，有候選就照既有的 `pick_next_match()`；(2) 沒有候選且 `_substitutes_for_rest(group)`（公平輪替雙打或個人全混搭）→ 依 `_QUEUE_ORDER` 逐一檢視「含休息者、無人在場上」的場次，對每位休息者呼叫 `_pick_substitute(…, must_be_free=True, exclude=已選的替補)`，第一個全部找得到的場次即為結果；(3) 其餘回 `None`。函式需要 `Group`（取排程方式）——把簽章的 `group_id` 改為 `group` 或在函式內載入，**更新全部呼叫端**（`mypy --strict` 會列出）。`_pick_substitute()` 新增 `must_be_free: bool = False` 與 `exclude: Collection[uuid.UUID] = ()`：為真時候選另須不在 `_busy_participants_subquery()` 裡（準備中已由 T008 的 `_get_active_roster_ordered()` 保證）；`remove_roster_entry_from_schedule()` 的既有呼叫不傳新參數、行為不變。`pull_queued_match_for_court()`：`choice.substitutions` 非空時，**先** `select(Group.id)…with_for_update()` 取團列鎖、**重新呼叫** `_choose_next_queued_match()`（鎖內重讀誰在場上）、再寫入 `MatchParticipant` 與替補者的 `wait_count`（公平輪替才歸零），最後 `_start_match()`；沒有替補的一般路徑 MUST 不多任何查詢或鎖。`peek_next_queued_match()` 改為回傳 `NextMatchChoice | None`。使 T019 (a)–(n) 全綠；`test_pull_queued_match_conflict.py`、`test_peek_next_queued_match.py`、`test_advance_court.py`、`test_advance_other_idle_courts.py`、`test_member_removal.py` 不改斷言全綠（depends on T008、T019）

### 後端——回來之後、被卡住的輪次

- [ ] T021 [P] [US2] 服務層測試（**先紅燈**）：新增 `apps/api/tests/unit/domains/schedule/test_rest_round_stall.py`。`round_is_stalled_by_rest()`：(a) 四個條件全成立 → 真；各缺一（有 `in_progress`／沒有 `queued`／有一場 `queued` 不含休息者／替補模式下找得到替補）→ 假。`_can_generate_any_match()`：(b) 單打 2 人準備中 → 真、1 人 → 假；雙打 4／3；固定搭檔兩隊／一隊。`check_round_complete_and_maybe_auto_advance()`：(c) 開啟自動換輪、被卡住、下一輪排得出 → 換輪，被保留的場次成為 `abandoned`（不產生 `MatchResult`，Constitution III）、新的一輪不含休息者；(d) 被卡住但下一輪排不出任何一場（單打只剩 A、B，A 休息）→ **不換輪**、`current_round_number` 不變、A 的場次仍 `queued`；(e) 未開啟自動換輪 → 不換輪；(f) 由 `set_rest_state()` 觸發：所有場地閒置、只剩一場含 A 的 `queued`、A 設休息 → 立即換輪（research Decision 6「誤觸的後果」）；(g) 空的輪次（沒有任何場次）、開啟自動換輪，某人回來使準備中人數足夠 → 換輪並產生場次；人數仍不足 → 不換輪；(h) **反覆切換同一人 10 次**，`current_round_number` 的增加次數 ≤ 實際產生了場次的輪數（不空轉）；(i) 既有路徑：沒有人休息時，比賽結束觸發的自動換輪行為與 `test_round_completion.py` 既有斷言一致
- [ ] T022 [P] [US2] 服務層測試（**先紅燈**）：新增 `apps/api/tests/unit/domains/schedule/test_rest_return.py`。(a) 單打循環：整輪產生時 A 在休息、輪中回來 → `_schedule_late_joiner_matches()` 為 A 補上對每位準備中球員的場次，A 的 `wait_count` 不變；(b) 個人全混搭：同上；(c) 固定搭檔＋手動搭檔：`Partnership(A,B)` 兩人都因 A 休息而沒有場次；A 回來（B 一直準備中）→ 以 **A、B 原隊伍**補入對每一隊的場次；(d) 同 (c) 但 B 也在休息、只有 A 回來 → A **不被**臨時配給其他落單者，沒有新場次；B 也回來後才以原隊伍補入（research Decision 8 的風險一）；(e) 別人中途加入（`handle_member_joined()`）時，休息中的人不被當成 newcomer、也不被排成新人的對手；(f) 輪次為 `awaiting_plan` 時回來 → 不補場次；(g) 公平輪替雙打 → 不補場次（下一次挑人自然納入）；(h) 回來時有閒置場地、且他被保留的場次因此可叫 → `set_rest_state()` 返回前該場已 `in_progress`（FR-019），**不必等別場結束**；(i) 連續輪轉、閒置且準備中 3 人、場地空著，第 4 人回來 → 立即排出一場（US3 情境 5）；(j) 輪次為 `awaiting_start`（已規劃未開始）時回來 → 不會替管理員開始這一輪（`refresh_courts_after_roster_change()` 既有的守門）
- [ ] T023 [US2] 於 `apps/api/app/domains/schedule/service.py`：新增 `round_is_stalled_by_rest(session, group) -> bool` 與 `_can_generate_any_match(session, group) -> bool`（data-model.md「這一輪是否被休息卡住」；research Decision 6）；`check_round_complete_and_maybe_auto_advance()` 改為 `(round_is_complete or round_is_stalled_by_rest) and _can_generate_any_match`——**注意**：由比賽結束觸發、且 `round_is_complete` 為真的既有路徑，`_can_generate_any_match` 為假時的行為要與現在一致；先以 `test_round_completion.py` 確認現況（現況若會產生空的輪次，就只對「被卡住」與「由狀態變更觸發」兩種情況套用守門，並在 docstring 寫明）。於 `apps/api/app/domains/schedule/rest.py` 的預留位置接上步驟 5（呼叫 `check_round_complete_and_maybe_auto_advance()`，傳入一個 `triggered_by_rest_change=True` 之類的旗標供上述區分）。使 T021 全綠（depends on T020、T021）
- [ ] T024 [US2] 於 `apps/api/app/domains/schedule/service.py` 的 `_schedule_late_joiner_matches()` 與 `_teams_for_newcomers()`：確認經 T008 後 `active` 只含準備中的人；固定搭檔＋手動搭檔時，有正式 `Partnership` 而搭檔不在 `active` 裡的 newcomer MUST 略過（不進臨時配對）。於 `apps/api/app/domains/schedule/rest.py` 的預留位置，切回準備中時呼叫 `service._schedule_late_joiner_matches()`（於 commit 之前，與 `handle_member_joined()` 的用法一致；若需跨模組呼叫私有函式，於 `service.py` 以公開名稱 `schedule_matches_for_unscheduled_members()` 包一層）。使 T022 全綠；`test_member_joined.py` 不改斷言全綠（depends on T020、T022）

### 後端——畫面需要的資訊

- [ ] T025 [P] [US2] 於 `apps/api/app/domains/schedule/schemas.py`：`WaitingReason` 加入 `"held_for_rest"`、`"not_enough_ready"`；新增 `SubstitutionPreview(resting: RosterSummary, substitute: RosterSummary)`、`WaitingOnRest(match_count: int, players: list[RosterSummary], stalled: bool)`；`NextUpPreview` 新增 `substitutions: list[SubstitutionPreview] = []`；`RoundMatchSummary` 新增 `rest_effect: Literal["held", "substitute"] | None = None`；`RoundMatchesResponse` 新增 `waiting_on_rest: WaitingOnRest | None = None`。`RosterSummary` 若定義在 `NextUpPreview` 之後，調整宣告順序（contracts/schedule-api-additions.md）
- [ ] T026 [US2] 於 `apps/api/app/domains/schedule/service.py`：`build_schedule_snapshot()`——`next_up` 改用 `NextMatchChoice`：`participants` 呈現替補後的陣容（替補者沿用被替補者的 `team`）、填入 `substitutions`；`waiting_reason` 依 data-model.md 的表判斷兩個新值（`held_for_rest`：有 `queued` 但 `choice is None` 且全部含休息者；`not_enough_ready`：沒有 `queued`、`_continuous_rotation_applies()`、閒置且準備中 < 4、名單上有人休息）；固定搭檔時填 `partner_roster_entry_id`（取自當前這一輪 `_COUNTS_TOWARD_ROUND` 的場次裡與他同 `team` 的人）。`build_round_matches_list()`——對 `queued` 且含休息者的場次填 `rest_effect`（依 `_substitutes_for_rest(group)`）；組出 `waiting_on_rest`（`players` 不重複、依 `joined_at`；`stalled` 取 `round_is_stalled_by_rest()`）。同一個請求內避免 N+1：休息者集合一次查出後在記憶體比對。其他同樣建構 `next_up`／`waiting_reason` 的地方（schemas.py 約 L351、L380 的兩個 court 狀態型別——控制面板與全場地面板）一併處理，`waiting_reason` 共用同一個判斷函式（depends on T020、T023、T025）
- [ ] T027 [P] [US2] 契約測試：擴充 `apps/api/tests/contract/test_member_schedule.py`、`test_round_matches.py`、`test_member_round_matches.py`，管理員的 `GET /groups/{id}/schedule` 則寫在 `test_rest_state_endpoints.py`——`next_up.substitutions` 的形狀與空陣列預設；兩個新 `waiting_reason` 各一個情境；`rest_effect` 三種值；`waiting_on_rest` 為 `null` 與非 `null`、`stalled` 真假；固定搭檔時 `partner_roster_entry_id` 有值、其他排程方式為 `null`；排行榜與對戰紀錄端點的回應 schema **沒有**任何新欄位（FR-028）（depends on T026）

### 前端

- [ ] T028 [P] [US2] 於 `apps/web/src/app/features/group-admin/schedule-management/schedule.models.ts`：`NextUpPreview`（約 L23）新增 `substitutions`；`RoundMatchSummary` 新增 `rest_effect`；`RoundMatchesResponse` 新增 `waiting_on_rest`；`WaitingReason` 聯集加入兩個新值；新增 `SubstitutionPreview`、`WaitingOnRest`。所有既有 spec 的 fixture 補上預設值（`substitutions: []`、`rest_effect: null`、`waiting_on_rest: null`）
- [ ] T029 [US2] 成員頁：於 `apps/web/src/app/features/group-member-view/member-schedule/member-schedule.component.{ts,html}`——場地的等待原因（html 約 L12–33）以 exhaustive `Record<WaitingReason, string>` 對應語系 key，**不認得的值退回 `waitingNoQueuedMatch`**（舊前端搭新後端／未來新值）；`next_up.substitutions` 非空時在預告下方顯示 `restToggle.substitutionNote`（「{{substitute}} 代替 {{resting}}（休息中）」），暱稱經 `<app-nickname>` 或插值，不使用 `innerHTML`；固定搭檔時，自己的 `partner_roster_entry_id` 指到的那一列為 `resting` → 在自己的切換按鈕附近顯示 `restToggle.partnerResting`（「搭檔休息中，你們的場次暫緩」，FR-022）；成員頁的本輪賽程清單對 `rest_effect` 顯示 `restToggle.effectHeld`（「保留，等他回來」）／`restToggle.effectSubstitute`（「輪到時由替補上場」）。新增語系 key 到兩份語系檔並加進 T014 的語系測試清單。擴充 `member-schedule.component.spec.ts`：兩個新等待原因、未知值的退回、替補註記、搭檔說明的出現與不出現、`rest_effect` 標示（depends on T015、T028）
- [ ] T030 [US2] 管理頁：於 `apps/web/src/app/features/group-admin/schedule-management/round-matches-list.component.{ts,html}` 顯示 `rest_effect` 標示（與 T029 同一組語系 key）；於 `apps/web/src/app/features/group-admin/admin-page/admin-page.component.{ts,html}` 的賽程區塊，`waiting_on_rest` 非 `null` 時顯示提示 `scheduleManagement.waitingOnRest`（「剩下 {{count}} 場在等休息中的球員：{{names}}」），`stalled` 為真時改用醒目樣式（圖示＋文字，不只顏色）並在**未開啟自動進入下一輪**時附上 `scheduleManagement.waitingOnRestHint`（「可以幫他按『準備好了』，或結束這一輪」，FR-021）；場地區塊的等待原因與 T029 共用同一個對應（抽到 `apps/web/src/app/core/` 下的小工具 `waiting-reason-label.ts`，成員頁同步改用）。把 `roster.restChanged` 加入管理頁 group 頻道的訂閱（ts 約 L312–324）→ 重抓名單、賽程、本輪賽程清單。擴充 `round-matches-list.component.spec.ts` 與 `admin-page.component.spec.ts`（depends on T028、T029）

**Checkpoint**：US1＋US2＋US3——規格定義的完整最小版本（quickstart 情境 1–8、10）。

---

## Phase 6: User Story 4 - 管理員幫球員切換（Priority: P2）

**Goal**：管理員在管理頁名單上替任何一位在團球員切換；手動操作的選單標示休息中的人但不禁止選擇。

**Independent Test**：quickstart.md 情境 9——對沒有登入裝置的訪客球員按休息，該球員的頁面即時反映，排程行為與本人切換完全相同。

- [ ] T031 [US4] 管理員端點：於 `apps/api/app/domains/schedule/router.py` 緊接踢人路由（約 L369）之後新增 `PUT /groups/{group_id}/members/{roster_entry_id}/rest-state`（`Depends(require_admin)`、`response_model=RestStateResponse`）——載入該列，不存在／不屬於此團／非 `active` → `ROSTER_ENTRY_NOT_FOUND` 404；忽略 body 的 `guest_session_token`；委派 `rest.set_rest_state()`。建立者的列**可以**切換（與踢人的 `CANNOT_KICK_CREATOR` 不同）。於 `apps/api/tests/contract/test_rest_state_endpoints.py` 新增管理員部分：成功（含訪客列、會員列、建立者列）；沒有管理員 token／別團的管理員 token → 沿用 `require_admin` 既有的錯誤；`left` 的列 → 404；成功後該球員以**自己的身分**讀 `member-schedule` 看到 `resting: true`；發布一次 `roster.restChanged`。另加一條：免驗證的畫面（計分板、單一場地控制面板、全場地控制面板的 token）**無法**呼叫任何一支 rest-state 端點（Constitution IV）（depends on T010）
- [ ] T032 [P] [US4] 於 `apps/web/src/app/features/group-admin/schedule-management/schedule.service.ts` 緊接 `kickMember()`（約 L236）新增 `setMemberRestState(groupId, rosterEntryId, resting): Observable<RestStateResponse>`；補 service spec
- [ ] T033 [US4] 於 `apps/web/src/app/features/group-admin/admin-page/admin-page.component.{ts,html}` 的名單分頁（html 約 L255–300）：每一列在既有標記（約 L261–267）旁顯示「休息中」標記；在踢人按鈕（約 L296–300）之前放 `<app-rest-toggle-button [compact]="true" …>`，**包含建立者的列**（踢人按鈕在該列隱藏，切換按鈕不隱藏）；`toggled` → `setMemberRestState()`，逐列的 `pending` 狀態（`Set<roster_entry_id>` signal）；失敗時顯示錯誤並還原；不加確認框。compact 模式的按鈕文字用 `restToggle.adminRest`（「休息」）／`restToggle.adminReady`（「準備好了」），`aria-label` 帶上暱稱（`restToggle.adminAriaLabel`：「將 {{nickname}} 設為休息中」）。擴充 `admin-page.component.spec.ts`：每列都有按鈕（含建立者）、標記、成功／失敗、逐列 pending 互不影響（depends on T014、T030、T032）
- [ ] T034 [P] [US4] 手動操作的選單：於 `apps/web/src/app/features/group-admin/schedule-management/manual-assign.component.{ts,html}`（`availableRoster()` 約 L30）與 `round-matches-list.component.ts` 的 `changeCandidates()`（約 L198）及交換選單——休息中的候選人在選項文字後加上「（休息中）」（`scheduleManagement.restingSuffix`），**仍可選**（FR-029）；排序不變。新增 `manual-assign.component.spec.ts`（該元件目前沒有測試檔）：標示出現、休息中的人可被選取並送出；擴充 `round-matches-list.component.spec.ts` 同樣兩點。後端不需改動——於 `apps/api/tests/unit/domains/schedule/test_manual_assign_validation.py` 加一條：把休息中的人手動排上場 → 成功，且他的 `resting_since` **不變**（FR-029）

**Checkpoint**：四個 User Story 全部完成。

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T035 整合測試（Constitution II 的端到端要求；SC-008）：新增 `apps/api/tests/integration/test_rest_toggle_flow.py`——經 HTTP 走完：開團（個人全混搭、2 面場地）→ 6 人加入 → 規劃並開始一輪 → A 以自己的身分設休息 → 逐場計分到只剩含 A 的場次 → 確認上場的是替補後的陣容且與前一次 `member-schedule` 的 `next_up` 相同 → A 設準備中 → 把這一輪打完 → 讀排行榜、團內對戰紀錄、A 與替補者各自的個人對戰紀錄：被替補的那一場記在替補者名下、A 沒有那一場、其餘數字與以同一批比分手算的結果一致。另一條：單打循環＋自動換輪，A 休息到這一輪被卡住 → 自動換輪 → A 回來被補進新的一輪
- [ ] T036 [P] 既有測試的回歸確認：於 `apps/api` 執行 `python -m pytest tests/unit/domains/schedule tests/unit/domains/group tests/contract tests/integration -q`，**任何既有測試的斷言都不應需要修改**；若有需要修改的，逐一列在本任務的備註並說明為什麼不是回歸。再跑一次全套件（約 20 分鐘，背景執行並把 `-rf` 輸出導到檔案；跑完之前不要結束回合）
- [ ] T037 [P] 靜態檢查：`apps/api`：`ruff check app/ tests/ && mypy app/`；`apps/web`：`npm run lint && npx tsc --noEmit -p tsconfig.app.json && npm test -- --watch=false`。`_choose_next_queued_match()` 回傳型別改變後，`mypy --strict` MUST 沒有任何 `# type: ignore` 新增
- [ ] T038 實機驗證 quickstart.md 情境 1–12（依記憶中的 worktree 實機流程：後端 uvicorn :8001、前端 `ng serve --port 4300`、Playwright 三個 context 分別為管理員、會員 A、訪客 B；**先做實機、再跑會清空資料庫的 pytest**）。情境 1 量測切換到其他視窗更新的時間（SC-001：< 2 秒）；情境 12 以 375px 寬截圖確認名單列沒有水平溢出。把截圖與發現的問題記在 PR 描述
- [ ] T039 [P] 文件：更新本機的 `docs/features.md`（gitignored，直接寫進主 checkout，不 commit）的排程章節，加入休息／準備切換的行為摘要與三個容易被問到的問題（按休息後已排好的場次怎麼辦、回來會不會插隊、自動換輪何時會因休息而觸發）；新增 `specs/037-rest-ready-toggle/pr-description.md`（比照 036 的格式），依憲章「技術治理」要求寫明本變更如何維持「伺服器為唯一可信來源」（`roster.restChanged` 只由後端發布、替補與保留的判斷全在後端）與「管理員操作僅限管理頁」（管理員端點 `require_admin`、免驗證畫面無切換）

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 Setup**（T001–T002）：無相依，最先做。
- **Phase 2 Foundational**（T003–T005）：依賴 Phase 1。T003→T004 為序列；T005 可與 T003／T004 平行。
- **Phase 3 US1**：依賴 Phase 2（T005；不依賴 T004）。
- **Phase 4 US3**：依賴 T004 與 US1 的 T010。
- **Phase 5 US2**：依賴 US1 的 T008、T010。**與 Phase 4 互不相依**，可平行。
- **Phase 6 US4**：後端 T031 只依賴 T010，可在 US1 完成後任何時間做；前端 T033 依賴 T014 與 T030（同一個檔案 `admin-page.component.*`，避免衝突所以排在 T030 之後）。
- **Phase 7 Polish**：依賴所有要上線的 Story。

### 同一檔案、不可平行的任務

- `apps/api/app/domains/schedule/service.py`：T008 → T017 → T020 → T023 → T024 → T026（US3 的 T017 與 US2 的 T020 若由兩人平行，改動的函式不重疊——`_get_player_histories()` vs. `_choose_next_queued_match()`／`_pick_substitute()`——但仍須在合併時留意）。
- `apps/api/app/domains/schedule/rest.py`：T010 → T017 → T023 → T024（三個預留位置各自獨立）。
- `apps/api/app/domains/schedule/schemas.py`：T009 → T025。
- `apps/web/…/member-schedule.component.*`：T015 → T029。
- `apps/web/…/admin-page.component.*`：T030 → T033。
- `apps/web/…/schedule.models.ts`：T013 → T028。
- 兩份語系檔：T014、T029、T030、T033、T034 都會加 key——各自只加自己的區塊，合併衝突以「兩邊都保留」解決。

### User Story 獨立性

| Story | 可獨立示範 | 可獨立上線 | 說明 |
|---|---|---|---|
| US1 | ✅ | ❌ | 少了 US3，回來的人會因 `rest` 與 `played` 而優先——不可單獨上線。 |
| US1＋US3 | ✅ | ✅ | 第一個可上線的組合。已排好的場次仍照原樣被叫到（與現況相同，不是退步）。 |
| US2 | ✅（需 US1） | ✅（需 US1＋US3） | 補上「當前這一輪」的處理。 |
| US4 | ✅（需 US1） | ✅ | 另一個入口。 |

## Parallel Example

```text
# Phase 2：純函式測試與 helper 平行
T003 test_rest_histories.py        ║  T005 _rest_helpers.py

# Phase 3：兩份先紅燈的測試與 schema 平行起跑
T006 test_rest_round_generation.py ║  T007 test_rest_state.py  ║  T009 schemas.py  ║  T013 前端型別與 service

# US1 後端完成後：兩條線平行
線 A（US3）：T016 → T017 → T018
線 B（US2）：T019 ║ T021 ║ T022（三份測試平行）→ T020 → T023 → T024 → T025 ║ → T026 → T027
線 C（US4 後端）：T031
```

## Implementation Strategy

1. **先把數學做對**（Phase 1–2）：migration 與兩個純函式。沒有行為改變，可以先合併。
2. **第一次上線＝US1＋US3**：球員能休息、不進新場次、回來不插隊。這已經解決「下一輪還是排到不在場邊的人」，而且不碰叫場邏輯——風險最低的一段。
3. **第二次上線＝US2**：改動 `_choose_next_queued_match()`（所有叫場的唯一入口）與自動換輪，是本功能風險最高的部分；T019 的併發測試與 T021 的空轉測試是這一段的安全網，MUST 先紅後綠。
4. **US4 隨時可加**：後端一支路由、前端一個按鈕。若現場「沒帶手機的人」很多，可提前到第一次上線。
5. **每個階段結束都跑一次 T036 的既有測試**——「沒有人休息時行為逐位相同」是整個功能最重要的不變量。

## Notes

- 任務總數 39。Setup 2、Foundational 3、US1 10、US3 3、US2 12、US4 4、Polish 5。
- 與 plan.md 的一處差異：SC-004 的模擬測試擴充的是 `tests/integration/test_schedule_fairness_simulation.py`（既有的情境驅動模擬在這裡，有 `Scenario`／`_run()`／`Report`），不是 plan.md 寫的 `tests/unit/…/test_fairness_simulation.py`（那支只有單一的固定情境）。
- FR 追溯：FR-001（T007、T010）、FR-002（T011、T014、T015）、FR-003（T031、T033）、FR-004（T011、T012、T031）、FR-005（T007、T012）、FR-006（T006）、FR-007（T010、T015、T030）、FR-008（T014、T015、T033）、FR-009（T006、T008）、FR-010（T008、T016）、FR-011（T006、T026、T029）、FR-012（T022、T024）、FR-013（T007）、FR-014（T007、T014）、FR-015（T019、T020、T026）、FR-016／FR-017（T019、T020）、FR-018（T019、T020）、FR-019（T022、T010）、FR-020（T021、T023）、FR-021（T026、T030）、FR-022（T026、T029）、FR-023（T016、T019）、FR-024（T008、T016）、FR-025（T003、T004、T017）、FR-026（T016、T022）、FR-027（T019、T020）、FR-028（T016、T027、T035）、FR-029（T034）、FR-030（T007）。
