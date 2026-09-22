# Tasks: 快速開始比賽（不開團）

**Input**: Design documents from `/specs/042-quick-match/`

**Prerequisites**: plan.md、spec.md、research.md、data-model.md、contracts/（3 份）、quickstart.md（皆已存在）

**Tests**：依 `plan.md` Constitution Check（原則 II），本功能新增一條「建立比賽」的入口（雖然走既有的 `manual_assign()`），並觸及邀請、一人一團、閒置解散等核心規則。純函式（名單驗證、換邊、位置狀態機、期限選擇）的單元測試 MUST **先於**實作完成並確認紅燈；每支新端點 MUST 有契約測試；MUST 有一條「快速開始 → 接受 → 計分 → 再打一場 → 換人再打 → 結束 → 對戰紀錄」整合測試。本檔案的測試任務為強制項。**回歸的底線**：`test_create_group.py`、`test_group_list*.py`、`test_manual_assign.py`、`test_group_invite_endpoints.py`、`test_member_match_records_endpoint.py`、`test_court_by_token.py`、`test_court_state.py` 不改斷言全數通過。

**Organization**：依 spec.md 之 5 個 User Story 分階段，順序 **US1 → US2 → US3 → US4 → US5**：
- **上線單位是 US1＋US2＋US5 一起**：US1 沒有 US2 的標籤與排除就會把「快速比賽」當成一個沒名字的團出現在對戰紀錄與開團列表；US5 的排除與閒置收尾是保護既有畫面的邊界。三者各自可獨立驗收。
- US3（再打一場）與 US4（好友接受）互不相依、可平行；US4 的「換人再打時新好友要再接受」（FR-030）是唯一交會點，放在 US4 最後。
- Foundational 階段把 `quick_match` domain 的骨架、純函式、`group_kind` 欄位一次做完，之後各 story 只加自己的端點與畫面。

## Format: `[ID] [P?] [Story] Description`

- **[P]**：可平行執行（不同檔案、無相依關係）
- **[Story]**：對應 spec.md 的 US1–US5；Setup／Foundational／Polish 階段任務無此標籤
- 每項任務皆附精確檔案路徑

## Path Conventions

沿用 `plan.md` Project Structure：後端 `apps/api/`，前端 `apps/web/src/`。後端測試於 `apps/api` 執行；從 `.claude/worktrees/` 執行時把主 checkout 的 `apps/api/.venv/bin` 放到 `PATH`、前端 `ln -s` 主 checkout 的 `node_modules`（quickstart.md）。`tests/unit/domains/quick_match/` 下的測試檔 MUST `import app.domains.member.models` 以載入全部 model（既有慣例）。

---

## Phase 1: Setup

- [ ] T001 新增 migration `apps/api/alembic/versions/<rev>_quick_match.py`（`down_revision = "b7e2d4a9c130"`）：`groups` 加 `kind VARCHAR(16) NOT NULL server_default 'normal'` 與索引 `ix_groups_kind_status (kind, status)`；新表 `quick_match_slots`（欄位、`UNIQUE (group_id, team, position)`、`CHECK (status <> 'ready' OR roster_entry_id IS NOT NULL)`、部分索引 `ix_quick_match_slots_pending (group_id) WHERE status = 'pending'`，FK 依 data-model.md §2）；`system_config` 以 `INSERT … ON CONFLICT (key) DO NOTHING` 加 `quick_match_invite_timeout_seconds='120'`、`quick_session_idle_minutes='60'`（寫法比照 `8a1f2c9d4e6b_more_system_config_defaults.py`）。`downgrade()` 完整還原（含 `DELETE` 兩列設定）。以 `alembic upgrade head && alembic downgrade -1 && alembic upgrade head` 驗證；`alembic heads` 只有一個 head
- [ ] T002 於 `apps/api/app/domains/group/models.py`：`Group` 新增 `kind: Mapped[str]`（`String(16)`、`default="normal"`、`server_default="normal"`），附註解指向 research Decision 1。新增 `apps/api/app/domains/quick_match/__init__.py` 與 `apps/api/app/domains/quick_match/models.py`：`QuickMatchSlot`（欄位同 T001；`group_id` 關聯 `Group`）。確認 model 與 migration 一致（autogenerate 空 diff）（depends on T001）
- [ ] T003 [P] 於 `apps/api/app/system_config/service.py` 新增 `get_quick_match_invite_timeout_seconds(session) -> int`（預設 120）與 `get_quick_session_idle_minutes(session) -> int`（預設 60），寫法比照 `get_match_records_page_size()`；於 `docs/tools.md` 第 3 節的共用設定表補兩列（docs/ 為本機資料夾，直接改主 checkout）

---

## Phase 2: Foundational（Blocking Prerequisites）

**Purpose**：`quick_match` domain 的骨架與純函式、所有畫面都要的 `group_kind` 欄位、語系標籤與錯誤碼。此階段完成後一般團**沒有任何行為改變**。

**⚠️ CRITICAL**：T005 的純函式是 US1／US3／US4 的前提；T007 的 `group_kind` 是所有前端分支的前提。

- [ ] T004 Unit test（**先紅燈**）：新增 `apps/api/tests/unit/domains/quick_match/test_lineup_rules.py`（無資料庫）。`validate_lineup(lineup, *, match_mode, caller_is_member)`：(a) 單打每隊 1、雙打每隊 2，否則 `QUICK_LINEUP_INVALID/size`；(b) 會員呼叫者 `self` 必須恰在 `team_a[0]`，缺少或位置錯 → `self_position`；(c) 訪客呼叫者含 `self` 或 `friend` → `guest_cannot_pick_friend`／`self_position`；(d) 暱稱去頭尾空白後重複 → `duplicate_nickname`；(e) 同一 `member_id` 兩次 → `duplicate_friend`；(f) 好友為呼叫者本人 → `self_as_friend`；(g) 訪客暱稱空白 → `NICKNAME_REQUIRED_FOR_GUEST`；(h) 合法輸入回傳正規化後的位置清單（team、position、source、nickname）。`swapped_lineup(slots)`：(i) A↔B 對調、position 不變、其餘欄位不變、回傳新物件不改輸入。`session_state(group_status, has_pending, has_in_progress)`：(j) 四種狀態的真值表（data-model.md §4），`disbanded` 永遠 `closed`。`pick_idle_cutoff(kind, now, normal_minutes, quick_minutes)`：(k) `normal` 用前者、`quick` 用後者、未知 kind 用前者。確認全部紅燈
- [ ] T005 新增 `apps/api/app/domains/quick_match/schemas.py`（`LineupSlotInput`、`LineupInput`、`QuickMatchCreateRequest`、`QuickMatchCreateResponse`、`SlotView`、`QuickSessionState`、`ReplaceLineupRequest`、`MemberQuickSessionResponse`，欄位依 contracts/quick-match-api.md；`scoring_mode`／自訂欄位重用 `group/schemas.py` 的 validator）與 `apps/api/app/domains/quick_match/service.py` 的**純函式部分**：`validate_lineup()`、`swapped_lineup()`、`session_state()`、`pick_idle_cutoff()`、常數 `QUICK_KIND = "quick"`、`NORMAL_KIND = "normal"`、`QUICK_GROUP_NAME = "快速比賽"`。使 T004 全綠（depends on T002、T004）
- [ ] T006 [P] 新增 `apps/api/tests/unit/domains/quick_match/_helpers.py`（非測試檔）：`register_member(client, db_session, email, nickname) -> (member_id, bearer_header)`（抄 `tests/contract/test_group_public_already_joined.py::_register_and_login()` 並把 `verification_status` 直接設為 verified）、`make_friends(db_session, a, b)`（直接寫 `friend_requests` 為 accepted）、`create_quick(client, *, headers=None, match_mode="singles", lineup=None, **overrides) -> dict`（POST `/quick-matches`，預設兩個訪客暱稱，帶 `valid_turnstile_token`）、`score_to_win(client, control_token, side="A")`（連按 `POST /courts/by-token/{token}/score` 到 `status == "completed"`，決勝分帶 `confirm=true`）、`ctrl(token)` 組 `/quick-matches/by-token/{token}`。不含斷言（depends on T005）
- [ ] T007 `group_kind` 欄位：於 `apps/api/app/domains/court/schemas.py` `CourtByTokenResponse` 與 `apps/api/app/domains/schedule/schemas.py` `CourtStateResponse` 新增 `group_kind: Literal["normal","quick"] = "normal"`；`apps/api/app/domains/court/router.py`（by-token）與 `apps/api/app/domains/schedule/router.py::_court_state_response()` 從 `group.kind` 填值。擴充 `apps/api/tests/contract/test_court_by_token.py` 與 `test_court_state.py`：一般團回 `"normal"`（depends on T002）
- [ ] T008 [P] 錯誤碼與語系：於 `apps/web/src/assets/i18n/zh-TW.json` 與 `en.json` 新增 `quickMatch.label`（「快速比賽」／「Quick match」）、`quickMatch.closed`、以及 `errors.QUICK_LINEUP_INVALID`、`errors.QUICK_SESSION_ONLY`、`errors.QUICK_SESSION_CLOSED`、`errors.QUICK_SESSION_NOT_IDLE`、`errors.QUICK_SESSION_NOT_WAITING`、`errors.QUICK_SLOT_NOT_PENDING`、`errors.QUICK_FRIEND_PICK_FORBIDDEN`、`errors.FRIEND_ACTIVE_ELSEWHERE`。兩檔 key 集合以既有的語系檔一致性測試（若無則加一個 `i18n-keys.spec.ts` 比對兩檔 key）驗證相同
- [ ] T009 [P] 前端模型與 API：新增 `apps/web/src/app/features/quick-match/quick-match.models.ts`（對應 T005 的 schema，`GroupKind = 'normal' | 'quick'`）與 `apps/web/src/app/features/quick-match/quick-match.service.ts`（`create()`、`getByToken()`、`rematch()`、`replaceLineup()`、`convertSlot()`、`cancel()`、`close()`、`getMyQuickSession()`，全部 `HttpClient` 呼叫 contracts/quick-match-api.md 的路徑）；於 `apps/web/src/app/core/api/court-control.service.ts` 對應的 state 型別加 `group_kind`

**Checkpoint**：純函式全綠；一般團所有既有測試零變動；前端可編譯但沒有任何新畫面。

---

## Phase 3: User Story 1 - 從首頁到開始計分只要一頁（Priority: P1）🎯 MVP 的第一塊（上線單位是 US1＋US2＋US5）

**Goal**：首頁「快速開始比賽」→ 單頁表單（訪客或會員，名單不含好友）→ 建立即開賽 → 直接落在控制板、有計分板連結與 QR、無輪次列。

**Independent Test**：quickstart.md 情境 1、2、16——訪客填兩個暱稱送出，60 秒內在 `/control/<token>` 按 +1；全程無團名／PIN／排程機制。

### 後端

- [ ] T010 [P] [US1] 服務層測試（**先紅燈**）：新增 `apps/api/tests/unit/domains/quick_match/test_quick_session.py`（用 T006 helper）。`start_quick_session(session, payload, *, member)`：(a) 訪客單打兩個暱稱 → 回傳的 group `kind="quick"`、`scheduling_mechanism="manual"`、`max_members=2`、`name == QUICK_GROUP_NAME`、`password_ciphertext is None`、`admin_pin_hash` 非空、`current_round_number == 1`、`round_history` 有 `(group_id, 1)`、一個場地名為 `default_court_name`、兩列 active 名單（A1 `is_creator=True` 且有 `guest_session_token`）、一場 `in_progress` 比賽、`match_participants` 的隊伍正確、`quick_match_slots` 兩列皆 `ready` 且 `roster_entry_id` 已填；(b) 會員雙打（self + 3 訪客）→ A1 為該會員的名單列、`created_by_member_id` 為該會員、`max_members=4`；(c) 21pt／15pt／custom 三種計分制的快照落在 `matches.target_score/deuce_threshold/cap_score`；(d) `detailed_scoring_enabled` 落在 group 與 match；(e) 會員已在別團 active → `ALREADY_ACTIVE_IN_ANOTHER_GROUP`，`detail["group_kind"] == "normal"`，且 **沒有任何** `groups`／`courts`／`roster_entries`／`matches`／`quick_match_slots` 列被留下（FR-008 rollback）；(f) 名單不合法 → `QUICK_LINEUP_INVALID` 且同樣零殘留；(g) `last_activity_at` 為現在；(h) 發布一次 `rotation.updated` 到 court 頻道（monkeypatch `publish` 計數）。確認紅燈
- [ ] T011 [US1] 於 `apps/api/app/domains/quick_match/service.py` 實作 `start_quick_session()`：依 research Decision 2 組 `Group(kind=QUICK_KIND, …)`（PIN 用 `group.security.generate_admin_pin()`／`hash_admin_pin()`；計分 preset 沿用 `group.service._SCORING_PRESETS`，自訂值沿用其驗證）→ `flush` → `RoundHistory(round_number=1)` → 場地（名稱 `get_default_court_name()`，寫法比照 `create_group()` L261–269）→ 建立者名單列（會員：`member_id`、`nickname` 為會員暱稱；訪客：A1 的暱稱、`guest_session_token=secrets.token_urlsafe(32)`）→ 其餘訪客位置各 `group.service.join_group(session, group, member=None, password=None, nickname=…, skip_password=True)`（不 commit）→ 寫 `QuickMatchSlot` 列 → `_maybe_start_match()`：全部 ready 時呼叫 `schedule.service.manual_assign(session, group, court, team_a=…, team_b=…)`。會員呼叫者先 `group.service._raise_if_active_elsewhere(session, member.id)`（T041 之後再接 hook）。整段在同一交易；任何 `ApiError` 前 `rollback`。本任務只處理 `source in (self, guest)`；`friend` 位置由 T031 接上。使 T010 (a)–(h) 全綠（depends on T010）
- [ ] T012 [US1] 於 `apps/api/app/domains/quick_match/service.py` 實作 `get_session_state(session, group, court, *, caller_member_id) -> QuickSessionState`：以 `session_state()` 推導 `state`、`current_match_id`（場地上 `in_progress`）、`last_match`（該團最近一場 `completed|abandoned` 的 id／status／winner／比分）、`slots`（含訪客位置的 `guest_binding_token`）、`can_pick_friends`、`closed_reason`（`disbanded` 時依 `quick_match_slots` 是否曾有比賽與一個記錄原因的欄位——**設計決定**：`closed_reason` 不另存欄位，以「有無任何 match 列」區分 `cancelled` 與 `manual`，`idle` 由 sweep 在 disband 前寫入 `groups.last_activity_at` 不變即可判斷不出，因此 sweep 收尾與手動結束對外都回 `manual`；註解說明）。加入 T010：(i) 建立後 `state == "playing"`、`slots` 順序為 A1、A2、B1、B2（depends on T011）
- [ ] T013 [US1] 契約測試（**先紅燈**）：新增 `apps/api/tests/contract/test_quick_match_create.py`。`POST /quick-matches`：(a) 訪客單打 201，回應含 `control_panel_token`、`scoreboard_token`、`guest_session_token`、`session.state == "playing"`；(b) 會員雙打 201、`guest_session_token is None`；(c) Turnstile 失敗 → 既有錯誤碼；(d) `QUICK_LINEUP_INVALID` 各 reason 至少一例；(e) 會員在別團 → 409；(f) 21 次／分鐘 → 429；(g) 建立後 `GET /courts/by-token/{control}/state` 的 `group_kind == "quick"`、`current_match` 非空、`round_number == 1`；(h) `GET /groups` 看不到它。確認紅燈
- [ ] T014 [US1] 新增 `apps/api/app/domains/quick_match/router.py`：`POST /quick-matches`（`optional_member`、`await verify_turnstile_token(payload.turnstile_token)`、`@limiter.limit("20/minute")` 需 `request: Request` 首參數，寫法比照 `group/router.py` 的 `POST /groups/reauth`）、`GET /quick-matches/by-token/{token}`（先 `_resolve_control_court()`：`court_service.get_court_by_token()` → `link_type != "control_panel"` 或 `group.kind != QUICK_KIND` → `ApiError("LINK_NOT_FOUND"/"QUICK_SESSION_ONLY", 404)`；`disbanded` 不擋讀取，回 `closed`）。docstring 列出錯誤碼。於 `apps/api/app/main.py` include router。使 T013 全綠（depends on T012、T013）
- [ ] T015 [US1] `GET /groups` 排除：於 `apps/api/app/domains/group/service.py::list_groups()` 的基礎 `conditions` 加 `Group.kind == NORMAL_KIND`。擴充 `apps/api/tests/contract/test_group_list_filters.py`：建一場快速比賽後列表不含它（T013 (h) 可改為引用此測試）（depends on T002）

### 前端

- [ ] T016 [P] [US1] 名單編輯元件：新增 `apps/web/src/app/features/quick-match/lineup-editor/lineup-editor.component.{ts,html,scss}`——輸入 `matchMode`、`selfNickname | null`、`friends: FriendSummary[] | null`（null＝不提供好友挑選）、`initialSlots`；輸出 `lineupChange`（`LineupInput`）與 `valid`。位置數隨模式 2↔4；A1 為本人時唯讀＋`quickMatch.self` 標籤；每個其他位置有「輸入暱稱」／「從好友挑選」切換（好友清單為 null 時只有前者，本任務先做暱稱模式，好友模式由 T036 補）；就地驗證訊息 `quickMatch.validation.*`。單元測試 `lineup-editor.component.spec.ts`：模式切換位置數、同名、空白（depends on T009）
- [ ] T017 [US1] 表單頁：新增 `apps/web/src/app/features/quick-match/quick-start/quick-start.component.{ts,html,scss,spec.ts}`，路由 `quick-match/new` 加進 `apps/web/src/app/app.routes.ts`（`loadComponent`，放在 `**` 之前）與 `apps/web/src/app/core/breadcrumb/breadcrumb.config.ts`。內容：比賽模式 segmented（預設單打）、`<app-lineup-editor>`、計分制（重用 `group-admin/shared/group-form-validators.ts` 的 `customScoringValidator`）、詳細設定 toggle、`TurnstileWidgetComponent`、送出。登入會員：`AuthService.getMe()` 取暱稱（未設暱稱導向 `/member/settings?returnTo=/quick-match/new`，比照 create-group）；訪客：先 `GroupJoinService.getActiveGuestGroupId()`／`verifyActiveGuestGroupId()` 擋「已在別團」。送出成功且 `session.state === 'playing'` → 訪客先 `setActiveGuestGroupId()`／`setGuestSessionToken()`（比照 create-group L185–192）再 `router.navigate(['/control', control_panel_token])`；`ALREADY_ACTIVE_IN_ANOTHER_GROUP` 依 `detail.group_kind` 顯示 `errors.ALREADY_ACTIVE_IN_ANOTHER_GROUP` 或 `quickMatch.error.activeQuickSession`。`waiting` 分支留待 T037。spec：表單初始值、送出後導向、錯誤顯示（depends on T009、T016）
- [ ] T018 [US1] 控制板 quick 分支（第一部分）：於 `apps/web/src/app/features/control-panel/control-panel.component.{ts,html}`：`state.group_kind === 'quick'` 時隱藏輪次列（html:25）與 `next_up` 預告（html:38），標題顯示 `quickMatch.label`；`current_match` 為空時原 `waiting_reason === 'manual_assignment'` 的等待訊息（html:177）改為佔位區塊 `<app-quick-actions>`（T027 實作，本任務先以空元件占位）。訪客建立者第一次進入時顯示一次性提示 `quickMatch.keepLinkNotice`（以 `sessionStorage` key `quickMatch.noticeShown.<token>` 控制，try/catch）。擴充 `control-panel.component.spec.ts`：quick 時輪次列不渲染、一般團不受影響（depends on T007、T009）
- [ ] T019 [P] [US1] 首頁 CTA：於 `apps/web/src/app/features/home/home.component.{ts,html}` 的 `home__actions` 新增 `quickMatch.cta` 連結至 `/quick-match/new`（登入與否皆顯示；橫幅留待 T046）。語系 key 加入兩檔（depends on T008）
- [ ] T020 [P] [US1] 計分板：於 `apps/web/src/app/features/scoreboard/` 的元件：`group_kind === 'quick'` 時隱藏輪次、標題 `quickMatch.label`。擴充其 spec（depends on T007）

**Checkpoint**：訪客與會員（不挑好友）都能從首頁一頁開賽並計分；一般團畫面零變動。

---

## Phase 4: User Story 2 - 計分、結束與戰績跟一般比賽一模一樣（Priority: P1）

**Goal**：快速比賽的自然結束計入戰績、提前結束為已捨棄；對戰紀錄、統計分析、好友對戰紀錄、分享卡都以「快速比賽」標籤呈現並可篩選。

**Independent Test**：quickstart.md 情境 3、11、12——計到 21 自動結束判勝；對戰紀錄出現、標籤為「快速比賽」、篩選只剩它們；分享卡標題為「快速比賽」；提前結束的一場不在任何人的勝負裡。

### 後端

- [ ] T021 [P] [US2] 契約測試（**先紅燈**）：新增 `apps/api/tests/contract/test_quick_match_records.py`（用 T006 helper）。會員建立單打、`score_to_win("A")`：(a) `GET /members/me/match-records` 有該場、`group_kind == "quick"`、`group_name == "快速比賽"`；(b) `?group_kind=quick` 只剩它、`?group_kind=normal` 不含它；(c) `GET /members/me/match-records/{id}` 詳情有 `group_kind`；(d) `…/dashboard` 的總場數含它；(e) 另建一場後 `POST /courts/by-token/{control}/end`（提前結束）→ 不出現在 (a) 的完成紀錄、dashboard 總場數不變；(f) 好友對戰紀錄端點（`friends/{id}/match-records`）的列有 `group_kind`；(g) `GET /members/me/groups/{group_id}/history` 回 `group_kind == "quick"`。確認紅燈
- [ ] T022 [US2] 於 `apps/api/app/domains/member/schemas.py`：`MemberMatchRecordSummary`、`MemberMatchRecordDetail`、`MemberGroupHistoryResponse`、好友對戰紀錄列、`MyGroupSummary` 各加 `group_kind: Literal["normal","quick"] = "normal"`。`apps/api/app/domains/member/service.py`：`_build_member_match_record_summaries()` 的 `select(Group.id, Group.name)` 加 `Group.kind` 並填入；詳情、團戰績、好友對戰紀錄同；`_filtered_member_matches()` 新增 `group_kind: str | None` 篩選（寫法比照 `match_mode` 的 `join(Group)`）；`apps/api/app/domains/member/router.py` 對 match-records／dashboard／comparison／好友對戰紀錄新增查詢參數 `group_kind`。使 T021 全綠；既有 `test_member_match_records_endpoint.py` 等不改斷言全綠（depends on T021）

### 前端

- [ ] T023 [P] [US2] 對戰紀錄與統計：於 `apps/web/src/app/features/member/match-history/match-history.component.{ts,html}`（比賽紀錄與統計分析兩個頁籤）、`apps/web/src/app/features/friends/*/match-records/`、`apps/web/src/app/features/member/my-groups/group-history/`：列表與詳情的活動名稱在 `group_kind === 'quick'` 時顯示 `quickMatch.label` 並加 `.tag--quick` 文字標籤（非僅顏色）；篩選列新增「活動類型」select（全部／揪團／快速比賽 → `group_kind` 參數，寫法比照既有 `match_mode` 篩選）。models 檔加 `group_kind`。擴充 `match-history.component.spec.ts`（depends on T009、T022）
- [ ] T024 [P] [US2] 分享卡：於 `apps/web/src/app/core/match-share-card/share-card.models.ts` 的 `ShareCardContext` 加 `groupKind`，`share-card-model.ts` 轉換時 `groupKind === 'quick'` → `groupName = translate.instant('quickMatch.label')`；三個呼叫端（`match-history.component.ts:438`、`group-history.component.ts:107`、`match-records.component.ts:39`）傳入 `group_kind`。擴充 `share-card-model.spec.ts`：quick 時標題為標籤、normal 時不變（depends on T009）
- [ ] T025 [US2] 控制板與計分板的 `group_disbanded` 畫面：於 `apps/web/src/app/features/control-panel/control-panel.component.html` 與 `apps/web/src/app/features/scoreboard/` 的元件，`group_kind === 'quick'` 時文字改為 `quickMatch.closed`，一般團文字不變。擴充兩個 spec（depends on T018、T020）

**Checkpoint**：快速比賽的戰績、標籤、篩選、分享卡與一般比賽一致；提前結束不計入。

---

## Phase 5: User Story 3 - 再打一場／換人再打（Priority: P2）

**Goal**：比賽結束後控制板出現「再打一場／換人再打／結束」；再打一場換邊、連結不變、計分板自動切換；換人再打可改名單（會員本人不可移除）；結束後連結失效但紀錄保留。

**Independent Test**：quickstart.md 情境 4、5、9（不含好友）——三場各自出現在對戰紀錄；結束後兩個連結顯示「這場快速比賽已結束」。

### 後端

- [ ] T026 [P] [US3] 服務層測試（**先紅燈**）：擴充 `tests/unit/domains/quick_match/test_quick_session.py`。`rematch()`：(a) idle 時新比賽 `in_progress`、參賽者 A/B 對調、`target_score` 等快照沿用 group、`quick_match_slots` 的 `team` 對調且 `roster_entry_id` 不變、`courts` 列與 token 不變；(b) playing 時 → `QUICK_SESSION_NOT_IDLE`；(c) 上一場為 `abandoned` 仍可再打；(d) 發布 `rotation.updated`。`replace_lineup()`：(e) 換掉一位訪客 → 舊名單列 `status="left"`、新列 active、新比賽含新人、`current_member_count` 正確；(f) 以 `slot_id` 引用保留者 → 其 `roster_entry_id` 不變；(g) 會員建立者的 `self` 缺少 → `QUICK_LINEUP_INVALID/self_position`；(h) 單打換雙打 → 4 個位置、`max_members` 改 4；(i) 雙打換單打 → 被移除者 left、`max_members` 改 2。`close_quick_session()`：(j) idle → `status="disbanded"`、既有完成的比賽仍 `completed`、發布 `group.disbanded`；(k) playing → 進行中比賽 `abandoned`。確認紅燈
- [ ] T027 [US3] 於 `apps/api/app/domains/quick_match/service.py` 實作 `rematch()`（`swapped_lineup()` → 更新 slots → `_maybe_start_match()`）、`replace_lineup()`（`validate_lineup()`；差集：移除者走 `schedule.service.handle_member_left(new_status="left")`；新訪客 `join_group(member=None)`；`group.max_members`／`match_mode` 更新；重寫 slots；`_maybe_start_match()`；`friend` 位置留待 T038）、`close_quick_session()`（`group.service.disband_group(session, group, abandon_unfinished_matches=schedule.service.abandon_group_matches, invalidate_pending_invites=group_invite.service.invalidate_pending_invites_for_group)`）。每個成功路徑 `_touch_activity()`。使 T026 全綠（depends on T026）
- [ ] T028 [US3] 契約測試（**先紅燈**）：新增 `apps/api/tests/contract/test_quick_match_actions.py`。(a) `POST …/rematch` 201 `state == "playing"`、`current_match_id` 變、`GET /courts/by-token/{scoreboard}/state` 顯示新的一場；(b) playing 時 rematch → 409 `QUICK_SESSION_NOT_IDLE`；(c) `POST …/lineup` 換人成功；會員建立者移除 `self` → 400；訪客呼叫者帶 `friend` → 403 `QUICK_FRIEND_PICK_FORBIDDEN`；(d) `POST …/close` → 200 `closed`；之後 `GET /courts/by-token/{control}` 與 `{scoreboard}` 皆 `group_disbanded: true`、`group_kind: "quick"`；再打 rematch → 409 `QUICK_SESSION_CLOSED`；(e) **計分板 token** 打 rematch／lineup／close／by-token → 404 `LINK_NOT_FOUND`；(f) **一般團的控制板 token** 打任何 quick 端點 → 404 `QUICK_SESSION_ONLY`；(g) `GET /members/me/match-records` 三場各自存在。確認紅燈
- [ ] T029 [US3] 於 `apps/api/app/domains/quick_match/router.py` 新增 `POST …/rematch`、`POST …/lineup`（`optional_member` 供 `can_pick_friends`）、`POST …/close`（皆經 `_resolve_control_court()`；`disbanded` → `QUICK_SESSION_CLOSED` 409）。使 T028 全綠（depends on T027、T028）

### 前端

- [ ] T030 [US3] 控制板內嵌動作元件：新增 `apps/web/src/app/features/quick-match/quick-actions/quick-actions.component.{ts,html,scss,spec.ts}`——輸入 `controlToken`；載入 `getByToken()`；`state === 'idle'`：上一場摘要（`last_match`）、「再打一場」→ `rematch()`、「換人再打」→ 展開 `<app-lineup-editor>`（`initialSlots` 帶 `slot_id`）→ `replaceLineup()`、「結束」→ `app-confirm-dialog`（`quickMatch.close.confirm`）→ `close()`；訪客位置旁「綁定戰績」連結 `guest-access/<guest_binding_token>`。`state === 'playing'` 時元件不顯示動作（控制板本身在計分）；`waiting` 分支留待 T039。於 `control-panel.component.ts` 的 `subscribeToLiveEvents()` 多訂閱 `quickMatch.lineupChanged` → `loadState()` 並通知子元件重載；`rotation.updated` 既有處理即可讓新的一場出現。playing 狀態下的「結束」放在既有 `.end-match-button` 旁，確認文字說明比賽會被捨棄。spec：idle 顯示三個按鈕、rematch 呼叫、close 需確認（depends on T009、T016、T018、T029）

**Checkpoint**：一次快速比賽可連打多場、換人、結束；連結失效畫面正確。

---

## Phase 6: User Story 4 - 戰績歸戶：好友接受（Priority: P2）

**Goal**：會員從好友清單挑人 → 等待畫面 → 好友收到通知按「接受」→ 比賽開始、雙方畫面自動切換；拒絕／逾時／「不等了」轉為訪客；好友在別團視同拒絕；換人再打的新好友要再接受。

**Independent Test**：quickstart.md 情境 6–10——兩個瀏覽器、demo 與 friend；接受 1 秒內進控制板；逾時轉訪客並開賽；已開賽後接受顯示「這場已經開始」。

### 後端

- [ ] T031 [P] [US4] 服務層測試（**先紅燈**）：擴充 `tests/unit/domains/quick_match/test_quick_session.py`（用 `make_friends`）。`start_quick_session()` 含一位好友：(a) `state == "waiting"`、**沒有** match 列、好友位置 `pending` 且 `expires_at ≈ now + timeout`、`group_invites` 一列 `pending`（`inviter_member_id` = 建立者）、`notifications` 一列 `type == "quick_match_invite"`、發布 `notification.created`；(b) 非好友 → `NOT_FRIENDS` 且零殘留；(c) 好友在別團 active → `FRIEND_ACTIVE_ELSEWHERE` 且零殘留。`on_invite_resolved(session, invite, outcome)`：(d) `accepted`（先以 `join_group(member=好友)` 建名單列模擬 accept）→ 位置 `ready`、`roster_entry_id` 填入、全部 ready → 比賽 `in_progress`、發布 `quickMatch.lineupChanged` 與 `rotation.updated`；(e) `declined` → 位置轉訪客（`source="guest"`、`member_id=None`、新名單列 `member_id IS NULL`、暱稱為好友暱稱）、invite `invalidated`、開賽；(f) `active_elsewhere` → 同 (e)。`resolve_expired_slots()`：(g) `expires_at` 過去 → 同 (e)；未過 → 不動；(h) 兩位好友一位逾時一位未回應 → 仍 waiting。`convert_slot_to_guest()`：(i) pending → 訪客並開賽；非 pending → `QUICK_SLOT_NOT_PENDING`。`cancel_session()`：(j) waiting → disbanded、零 match 列、invite `invalidated`；非 waiting → `QUICK_SESSION_NOT_WAITING`。(k) 併發：兩位好友「同時」接受只開一場（比照 `test_pull_queued_match_conflict.py` 的併發寫法）。確認紅燈
- [ ] T032 [US4] 通知型別：於 `apps/api/app/domains/notification/schemas.py` `NotificationType` 加 `"quick_match_invite"`，`NotificationSummary` 加 `quick_match_invite: QuickMatchInviteNotificationDetail | None`（`invite_id`、`inviter_nickname`、`match_mode`、`status`）；`apps/api/app/domains/notification/service.py` 新增 `create_quick_match_invite_notification(member_id, invite_id)`，`_build_notification_summaries()` 加該型別的 batch 查詢（join `group_invites` → `groups`／`members`）。擴充 `apps/api/tests/contract/test_notification_endpoints.py`：列表回該型別與 detail（depends on T002）
- [ ] T033 [US4] 邀請 domain 的擴充：於 `apps/api/app/domains/group_invite/service.py`：`send_invite()` 依 `group.kind` 選用 T032 的通知建立函式；`accept_invite()`／`decline_invite()` 新增參數 `on_resolved: InviteResolvedHook | None = None`（型別 `Callable[[AsyncSession, GroupInvite, Literal["accepted","declined","active_elsewhere"]], Awaitable[None]]`），accept 在 `join_group()` 成功後、commit 前呼叫 `on_resolved(…, "accepted")`；`join_group()` 拋 `ALREADY_ACTIVE_IN_ANOTHER_GROUP` 時先呼叫 `on_resolved(…, "active_elsewhere")` 再重新拋出；decline 呼叫 `"declined"`。`schemas.py`：`GroupInviteDetail` 加 `group_kind`、`match_mode`、`inviter_nickname`；accept 回應加 `scoreboard_token: UUID | None`。`router.py` 注入 `quick_match.service.on_invite_resolved`（late import 或在 router 模組頂端 import——router 可以 import quick_match，service 不行）。既有 `test_group_invite_endpoints.py`、`test_group_invite_flow.py` 不改斷言全綠（depends on T032）
- [ ] T034 [US4] 於 `apps/api/app/domains/quick_match/service.py` 實作 `friend` 位置：`start_quick_session()`／`replace_lineup()` 對 `friend` 位置先 `_raise_if_active_elsewhere(friend_id)`（轉成 `FRIEND_ACTIVE_ELSEWHERE`）再 `group_invite.service.send_invite()`（不 commit），slot `pending` + `expires_at`；`on_invite_resolved()`、`resolve_expired_slots()`（對 `groups` 列 `FOR UPDATE` 後處理，開賽判定同一交易）、`convert_slot_to_guest()`、`cancel_session()`；`_maybe_start_match()` 後發布 `quickMatch.lineupChanged`（court 頻道，payload 依 contracts/ably-events-additions.md）。`get_session_state()` 與所有動作入口先 `resolve_expired_slots()`。使 T031 全綠（depends on T031、T033）
- [ ] T035 [US4] 契約測試（**先紅燈**）＋端點：新增 `apps/api/tests/contract/test_quick_match_invites.py`：(a) 含好友建立 → 201 `state == "waiting"`；friend 的 `GET /notifications` 有 `quick_match_invite`；`GET /group-invites/{id}` 有 `group_kind == "quick"`、`match_mode`、`inviter_nickname`；(b) friend `POST /group-invites/{id}/accept` → 200 含 `scoreboard_token`；建立者 `GET …/by-token` 為 `playing`；(c) decline → 建立者端 slot 轉訪客並 playing；(d) `POST …/slots/{id}/convert` → playing；非 pending → 409；(e) `POST …/cancel` → closed、`GET /members/me/match-records` 無任何紀錄；非 waiting → 409；(f) 把 `system_config.quick_match_invite_timeout_seconds` 設 `'0'`（`finally` 還原）→ 下一次 `GET …/by-token` 即 playing；之後 friend accept → `GROUP_INVITE_NOT_PENDING`；(g) friend 在別團 → accept 回 409、建立者端 slot 轉訪客。於 `router.py` 新增 `POST …/slots/{slot_id}/convert`、`POST …/cancel`。使測試全綠（depends on T034）

### 前端

- [ ] T036 [P] [US4] 名單編輯的好友模式：於 `apps/web/src/app/features/quick-match/lineup-editor/lineup-editor.component.{ts,html}` 加「從好友挑選」（`friends` 非 null 時）：以 `GET /friends`（既有 `FriendService`）清單的下拉／清單挑選，已挑過的好友不可再選、不可挑本人；輸出 `{ source: 'friend', member_id }`。擴充其 spec（depends on T016）
- [ ] T037 [US4] 等待畫面：於 `apps/web/src/app/features/quick-match/quick-start/quick-start.component.{ts,html}` 加 `waiting` 分支——送出回應 `state === 'waiting'` 時不導向，改渲染名單列（暱稱、來源、`quickMatch.slot.{ready,pending,converted}`、pending 倒數以 `expires_at` 計算、「不等了，改用暱稱」→ `convertSlot()`）與「取消」（`app-confirm-dialog` → `cancel()` → 回首頁）；以既有 realtime 服務訂閱 court 頻道：`quickMatch.lineupChanged` → `getByToken()` 重載；`rotation.updated` → 導向控制板。會員在表單載入 `GET /friends` 供 T036。擴充 spec：waiting 渲染、事件導向（depends on T017、T036）
- [ ] T038 [P] [US4] 通知與邀請頁：於 `apps/web/src/app/features/notifications/notification-list/notification-list.component.ts::open()` 加 `type === 'quick_match_invite'` → `group-invites/:inviteId`；列表文字 `quickMatch.invite.notification`（`{{inviter}}`、`{{mode}}`）；`core/api/notification.models.ts` 加型別與 detail。於 `apps/web/src/app/features/group-invites/group-invite-detail/` 元件：`group_kind === 'quick'` 時標題／說明改 `quickMatch.invite.{title,description}`，接受成功且回應有 `scoreboard_token` → `router.navigate(['/scoreboard', token])`；`GROUP_INVITE_NOT_PENDING` 顯示 `quickMatch.invite.expired`。擴充兩個 spec（depends on T009）
- [ ] T039 [US4] 控制板等待狀態（換人再打挑了新好友）：`quick-actions.component` 的 `state === 'waiting'` 分支渲染與 T037 相同的名單列（抽成共用子元件 `apps/web/src/app/features/quick-match/slot-list/slot-list.component.{ts,html,scss}`，T037 改用它）。spec：waiting 時不顯示三個動作（depends on T030、T037）

**Checkpoint**：好友接受流程雙端可用；逾時與拒絕不阻擋開賽；換人再打的新好友需再接受。

---

## Phase 7: User Story 5 - 不干擾既有的揪團畫面（Priority: P3）

**Goal**：開團列表永遠看不到快速比賽（T015 已做）；「我的團」預設不列、可勾選包含；閒置 60 分鐘自動收尾；會員首頁橫幅；FR-020 的自動收尾與拒絕。

**Independent Test**：quickstart.md 情境 13–15——我的團預設無、勾選有；idle 快速比賽 2 分鐘（設定改 1）後自動收尾；有 idle 快速比賽時開團成功且它被收尾，有比賽進行中時被拒。

### 後端

- [ ] T040 [P] [US5] 「我的團」：於 `apps/api/app/domains/member/service.py::get_my_groups()` 的 `select` 加 `Group.kind`，篩選 comprehension 加 `(include_quick or row.kind != QUICK_KIND)`，`MyGroupSummary.group_kind` 填值；`router.py` 新增查詢參數 `include_quick: bool = False`。擴充 `apps/api/tests/contract/test_member_groups_history_endpoints.py`：預設不含、`include_quick=true` 含且 `group_kind == "quick"`（depends on T022）
- [ ] T041 [US5] FR-020 的自動收尾：於 `apps/api/app/domains/group/service.py::_raise_if_active_elsewhere()` 新增參數 `close_idle_quick_session: CloseQuickSessionHook | None = None`（`Callable[[AsyncSession, uuid.UUID], Awaitable[bool]]`，回傳是否已收尾）：找到的 active 團 `kind == QUICK_KIND` 且 hook 回 `True` → 放行；否則拋 `ALREADY_ACTIVE_IN_ANOTHER_GROUP`，`detail` 加 `group_kind`。`create_group()`／`join_group()` 的簽名各加同名參數往下傳；`group/router.py` 與 `group_invite/router.py`（accept 走 join_group）注入 `quick_match.service.close_idle_quick_session`（該函式：無 `in_progress` 比賽 → `close_quick_session()` 回 `True`；有 → `False`）。`quick_match.service.start_quick_session()` 也注入同一個 hook（自己的舊快速比賽 idle 時自動收尾）。單元測試擴充 `test_quick_session.py`：(a) idle 快速比賽 + 開團 → 開團成功、舊團 disbanded；(b) playing + 開團 → 409 且 `detail.group_kind == "quick"`；(c) 一般團 active + 快速開始 → 409 `group_kind == "normal"`。既有 `test_create_group.py`、`test_join_group.py` 不改斷言全綠（depends on T027）
- [ ] T042 [US5] Sweep：於 `apps/api/app/scheduler/auto_disband.py::sweep_idle_groups()`：查詢改為兩段——`kind='normal'` 用 `settings.auto_disband_idle_minutes`、`kind='quick'` 用 `await get_quick_session_idle_minutes(session)`（`pick_idle_cutoff()`）；另對 `kind='quick'`、`status='active'` 且存在 `pending` slot 的團呼叫 `quick_match.service.resolve_expired_slots()`（scheduler 可 import quick_match）。新增 `apps/api/tests/unit/scheduler/test_auto_disband_quick.py`（比照既有 sweep 測試的 `session_factory` 注入）：(a) quick idle 59 分不收、61 分收；normal 不受影響；(b) 設定改 1 分鐘生效；(c) 有逾時 pending slot 的 quick 團被轉為訪客並開賽（depends on T034）
- [ ] T043 [US5] 首頁橫幅端點：`GET /members/me/quick-session`（`require_verified_member`）於 `quick_match/router.py`／`service.py::get_member_quick_session()`：會員為建立者或有 active 名單列的 `kind='quick'` active 團 → `role`、`state`、`control_panel_token`（僅 creator）、`scoreboard_token`；否則 `null`。契約測試加進 `test_quick_match_actions.py`：creator／participant／none 三例（depends on T029）

### 前端

- [ ] T044 [P] [US5] 「我的團」篩選：於 `apps/web/src/app/features/member/my-groups/` 的篩選列加「包含快速比賽」checkbox → `include_quick` 參數；列表項 `group_kind === 'quick'` 時顯示標籤。擴充其 spec（depends on T040）
- [ ] T045 [US5] 首頁橫幅：`home.component` 登入時呼叫 `getMyQuickSession()`，非 null 顯示 `quickMatch.banner.active` 與依 `role` 的按鈕（「回到控制板」→ `/control/<token>`；「開啟計分板」→ `/scoreboard/<token>`）。擴充 `home.component.spec.ts`（depends on T019、T043）

**Checkpoint**：三個既有清單不受快速比賽干擾；閒置與一人一團規則完整。

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T046 整合測試：新增 `apps/api/tests/integration/test_quick_match_flow.py`——quickstart.md §1 的完整流程（會員建立含一位好友 → 好友接受 → 開賽 → 計到 21 → 再打一場（換邊、token 相同）→ 換人再打（換掉一位訪客）→ 結束 → 雙方 `GET /members/me/match-records` 各 2 場 `group_kind == "quick"` → 兩個舊連結 `group_disbanded: true`）（depends on T035、T041）
- [ ] T047 [P] 語系完整性：檢查 `quickMatch.*` 全部 key 在 `zh-TW.json` 與 `en.json` 都存在且無多餘；`errors.*` 新錯誤碼齊全；`docs/features.md` 第 3 節「開團與場地管理」之後新增「快速開始比賽（042）」段落與第 4 節一則常見使用流程（docs/ 直接改主 checkout）
- [ ] T048 [P] 無障礙與手機：`quick-start`、`slot-list`、`quick-actions` 三個元件在 360px 無水平捲動、按鈕 ≥ 44px、標籤含文字（非僅顏色）、倒數有 `aria-live="polite"`；以 quickstart 情境 16 的方式截圖比對
- [ ] T049 全套回歸：`apps/api` 四段 pytest（quickstart §1）、`apps/web` `ng test`／`ng lint`／`ng build`（警告數與 `origin/ut` 相同）；確認 plan.md「回歸的底線」列出的既有測試檔零 diff
- [ ] T050 實際畫面驗收：依 quickstart.md §2 的 16 個情境以 playwright 腳本跑過（`docs/042-quick-match-check/`，含兩個瀏覽器 context 的好友接受、逾時、sweep），截圖存檔；驗收後還原 `system_config` 兩個 key 並 TRUNCATE 測試庫
- [ ] T051 PR 說明：依憲章「技術治理」——說明 Constitution IV 例外（控制板動作以 `kind='quick'` 守門、一般團邊界不變）與「伺服器為唯一可信來源」（所有開賽判定在後端交易內、前端只重載）如何維持；附 quickstart 驗收摘要

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：T001 → T002；T003 平行。
- **Foundational (Phase 2)**：T004 → T005 → T006；T007、T008、T009 平行（T009 需 T005 的 schema 定案）。**阻擋所有 story**。
- **US1 (Phase 3)**：後端 T010 → T011 → T012 → T013 → T014；T015 平行。前端 T016 → T017；T018、T019、T020 平行。
- **US2 (Phase 4)**：T021 → T022；前端 T023、T024 平行、T025 需 T018／T020。可與 US1 前端平行。
- **US3 (Phase 5)**：T026 → T027 → T028 → T029 → T030。需 US1 的 T014、T018。
- **US4 (Phase 6)**：T031、T032 平行 → T033 → T034 → T035；前端 T036 → T037 → T039；T038 平行。需 US1 全部、US3 的 T027（`replace_lineup`）。
- **US5 (Phase 7)**：T040、T042、T043 平行；T041 需 T027；前端 T044、T045。需 US3 的 T027、US4 的 T034（sweep 的逾時處理）。
- **Polish (Phase 8)**：需全部 story。

### User Story Dependencies

- **US1**：只需 Foundational。**MVP 第一塊**。
- **US2**：只需 Foundational 與 US1 的建立端點（測試用）。
- **US3**：需 US1（控制板 quick 分支、建立端點）。
- **US4**：需 US1、US3 的 `replace_lineup()`。
- **US5**：需 US3 的 `close_quick_session()`、US4 的 `resolve_expired_slots()`。

### Parallel Opportunities

- Foundational：T007／T008／T009 三人平行。
- US1：後端鏈與前端鏈（T016–T020）平行；US2 的 T021–T024 可與 US1 前端同時進行。
- US3 與 US4 的後端在 T027 完成後可平行；US4 的前端（T036–T038）與 US3 的前端（T030）平行。
- US5 的 T040／T042／T043／T044 四項互不相依。

---

## Parallel Example: Foundational + US1

```bash
# Foundational 三人平行：
Task: "T007 group_kind 欄位（court/schedule schemas + routers + 兩個契約測試）"
Task: "T008 語系與錯誤碼（zh-TW.json、en.json）"
Task: "T009 前端 models 與 quick-match.service.ts"

# US1 後端鏈與前端鏈平行：
Task: "T010 → T011 → T012 → T013 → T014（quick_match service/router）"
Task: "T016 lineup-editor → T017 quick-start；T018 control-panel；T019 home；T020 scoreboard"
```

---

## Implementation Strategy

### MVP First（US1 + US2 + US5 一起上線）

1. Phase 1、2：migration、骨架、純函式、`group_kind`。
2. Phase 3（US1）：訪客與會員不挑好友即可開賽。
3. Phase 4（US2）：標籤、篩選、分享卡——沒有它，快速比賽會以「快速比賽」這個團名出現，但仍可用。
4. Phase 7（US5）的 T040、T041、T042：排除、一人一團、閒置收尾——沒有它，快速比賽會占住會員一小時且進「我的團」。
5. **STOP and VALIDATE**：quickstart §2 的 1–5、13–15。

### Incremental Delivery

1. + US3（Phase 5）→ 再打一場、換人、結束 → quickstart 4、5、9。
2. + US4（Phase 6）→ 好友接受 → quickstart 6–10。
3. Phase 8 收尾。

---

## Notes

- [P] 任務＝不同檔案、無相依；同一檔案的任務依序執行。
- 每項任務完成即 commit；到 Checkpoint 跑該 story 的測試。
- **絕不**修改 `create_group()`、`manual_assign()`、`apply_score_delta()` 的既有行為；需要的能力以新函式或注入的 hook 提供（research Decision 2）。
- `service.py` 之間的依賴方向：`quick_match` → `group`／`schedule`／`group_invite`／`court`／`notification`；反向只透過 router 注入的 hook 或 scheduler。
- 每個新錯誤碼同時出現在：raise 處、路由 docstring 的 `Errors:`、兩個語系檔的 `errors.*`。
