# Tasks: 關鍵分表現與跨場個人技術儀表板

**Input**: Design documents from `/specs/034-clutch-points-player-dashboard/`

**Prerequisites**: plan.md、spec.md、research.md、data-model.md、contracts/（2 份）、quickstart.md（皆已存在）

**Tests**：依 `plan.md` Constitution Check（原則 II），兩個純函式模組（`group/match_stats.py` 的新增部分、`member/player_dashboard.py`）的每一個函式 MUST 有單元測試，且測試任務 MUST **先於**對應的實作任務完成並確認為失敗（紅燈）；新端點與擴充的回應 MUST 有契約測試；兩項重構（T001、T013）以**既有測試不改斷言仍全綠**為完成條件。本檔案的測試任務為強制項，非選用。

**Organization**：依 spec.md 之 5 個 User Story（US1 P1、US2 P1、US3 P2、US4 P3、US5 P3）分階段。US1（單場關鍵分）與儀表板系列（US2–US5）只共用 `match_stats.py` 的既有函式，因此 Foundational 只放兩項「保持行為不變的抽取」；儀表板自己的基礎建設（篩選集合、批次載入、端點、元件骨架）放在 US2 開頭——US3／US4／US5 依規格本來就建立在 US2 之上，不假裝它們彼此獨立。

## Format: `[ID] [P?] [Story] Description`

- **[P]**：可平行執行（不同檔案、無相依關係）
- **[Story]**：對應 spec.md 的 US1–US5；Setup／Foundational／Polish 階段任務無此標籤
- 每項任務皆附精確檔案路徑

## Path Conventions

沿用 `plan.md` Project Structure：後端 `apps/api/`，前端 `apps/web/src/`。

---

## Phase 1: Setup

*本 feature 無 Setup 任務——不新增第三方依賴、不新增 migration、不新增環境變數（plan.md Technical Context）。*

---

## Phase 2: Foundational（Blocking Prerequisites）

**Purpose**：兩項對 033 既有程式「保持對外行為不變」的抽取，讓單場詳情與儀表板日後共用同一段程式（FR-003，research.md Decision 7/8）。先做，避免後續各 Story 在同一檔案上反覆衝突。

**⚠️ CRITICAL**：兩項任務的完成條件都是「既有測試**不改任何斷言**仍全綠」。

- [ ] T001 於 `apps/api/app/domains/group/service.py` 把 `build_match_record_detail()`／`_build_derived_stats()` 內的 ORM → 純函式輸入轉換抽成模組層級函式：`_record_completeness(score_events) -> Literal["complete","partial","none"]`、`_to_raw_events(score_events, started_at) -> list[match_stats.RawEvent]`、`_to_serve_snapshots(records) -> dict[UUID, match_stats.ServeSnapshot]`、`_to_placements(placements) -> dict[UUID, match_stats.Placement]`；兩個既有函式改為呼叫它們，回應完全不變；以 `python -m pytest tests/unit/domains/group/test_match_record_detail.py tests/contract -k match_record_detail` 全綠為準
- [ ] T002 [P] 於 `apps/api/app/domains/group/match_stats.py` 自 `landing_distribution()` 抽出 `player_landings(points, placements, participants) -> dict[UUID, PlayerLandingResult]`（回傳全部參賽者的完整結果，**不套用**「沒有任何落點就回傳空」的規則），`landing_distribution()` 改為其上的薄包裝、對外行為不變；於 `apps/api/tests/unit/domains/group/test_match_stats.py` 新增測試：(a) 有球員紀錄但全場無座標時 `player_landings()` 仍回傳正確的 `scored_total`／`lost_total`，而 `landing_distribution()` 仍回傳 `[]`；(b) 既有 `landing_distribution` 測試不改斷言全綠

**Checkpoint**：無任何對外行為變化；後端既有測試全綠。

---

## Phase 3: User Story 1 - 單場關鍵分表現（Priority: P1）🎯 MVP

**Goal**：比賽詳情新增「關鍵分表現」區塊——局末階段、平分延長、賽末點（握有／兌現／化解）、依開打前比分狀態分組的得分率、逆轉摘要。

**Independent Test**：quickstart.md 情境 1–5——延長與賽末點逐分核對、封頂前雙方賽末點、7 分制顯示「此賽制不適用」、`by_state` 加總等於總比分、`comeback` 等於 `max_leads` 敗方那一筆、`-1` 修正與不完整紀錄。

- [ ] T003 [US1] 於 `apps/api/app/domains/group/match_stats.py` 新增 `frozen=True` dataclass `PhaseCounts`／`MatchPointResult`／`StateCounts`／`ClutchResult`（欄位依 data-model.md「純函式模型 (1)」）與函式簽章 `_wins(x, y, target, cap) -> bool`、`clutch_stats(points, target_score, cap_score) -> ClutchResult`（本體先 `raise NotImplementedError`）；模組仍 MUST NOT import ORM 或 `AsyncSession`
- [ ] T004 [US1] Unit test（先紅燈）於 `apps/api/tests/unit/domains/group/test_match_stats.py`：(a) `_wins` 與 `app.domains.schedule.service.match_wins` 在 `target∈{1,11,15,21}`、`cap∈{target, target+9}`、`0≤x,y≤cap` 的網格上逐格相等（research.md Decision 2）；(b) 局末階段：21 分制自任一方**開打前**達 18 起算，含其後的延長；`target < 11` → `endgame_from is None` 且 `endgame is None`；(c) 21:15 結束 → `deuce is None`；(d) quickstart 情境 1 的序列（20:20 後 A、B、A、B、B、B）→ 兩隊 `deuce.total == 6`、A `won == 2`、A `held == 2`／`converted_on is None`／`saved == 0`、B `held == 1`／`converted_on == 1`／`saved == 2`；(e) 勝方第 3 次賽末點才兌現 → `held == 3`、`converted_on == 3`，敗方 `saved == 2`；(f) 29:29、cap 30 → 該分同時計入雙方 `held`；`cap == target` 的賽制在 `target-1` 平手時亦同；(g) `by_state` 以**開打前**比分判定（第一分恆為 `tied`）；不變式：每隊三組 `total` 相加 `== len(points)`、A `leading.total` == B `trailing.total`、每組 `A.won + B.won == total`；(h) 不變式：勝方 `held ≥ 1` 且 `converted_on == held`、敗方 `converted_on is None`、`A.saved + B.saved + 1 == A.held + B.held`；(i) 輸入為含亂序撤銷後重新累計的 `EffectivePoint` 序列時，階段判定採 `score_a/score_b`（重新累計值）而非 `recorded_score_*`（depends on T003）
- [ ] T005 [US1] 實作 `_wins()` 與 `clutch_stats()`（單趟走訪：以前一個 `EffectivePoint` 的比分為開打前比分，第一分為 0:0；research.md Decision 1–3）於 `apps/api/app/domains/group/match_stats.py`，使 T004 全綠（depends on T004）
- [ ] T006 [P] [US1] 於 `apps/api/app/domains/group/schemas.py` 新增 `ClutchPhaseTotals`／`ClutchPhaseCounts`／`ClutchMatchPoints`／`ClutchStateCounts`／`ClutchComeback`／`ClutchStats`（依 data-model.md），並於 `MatchRecordDetailResponse` 新增 `clutch_stats: ClutchStats | None = None`
- [ ] T007 [US1] 於 `apps/api/app/domains/group/service.py` 的 `_build_derived_stats()` 呼叫 `match_stats.clutch_stats(points, match.target_score, match.cap_score)` 並組成 `ClutchStats`（各陣列恆為 `[A, B]` 順序）；`comeback` 取自同一次計算的 `momentum.max_leads` 中**敗方**（`match.winner_team` 的另一隊）那一筆，`margin == 0` → `None`（research.md Decision 4）；`_DerivedStats` 與 `build_match_record_detail()` 的回傳組裝同步擴充，紀錄不完整或 `effective_points()` 為 `None` 時 `clutch_stats` 維持 `None`；於 `apps/api/tests/unit/domains/group/test_match_record_detail.py` 新增經資料庫的測試：打到延長的比賽回傳正確 `clutch_stats`、`comeback` 與 `momentum_stats.max_leads` 敗方一致、勝方未曾落後 → `comeback is None`、`target_score=7` 的比賽 `endgame is None`、`partial` 紀錄 → `clutch_stats is None`（depends on T005, T006, T001）
- [ ] T008 [P] [US1] 契約測試：於 `apps/api/tests/contract/test_group_match_record_detail.py` 與 `apps/api/tests/contract/test_member_match_record_detail.py` 擴充回應形狀斷言，涵蓋 contracts/match-record-detail-api.md「保證」各條（兩筆且順序 A、B；`by_state` 加總 == `score_a + score_b`；勝方 `converted_on == held`；`comeback` 與 `max_leads` 一致；既有欄位值不變）（depends on T007）
- [ ] T009 [P] [US1] 前端型別：於 `apps/web/src/app/core/api/group-member-view.models.ts` 新增 `ClutchStats` 及子型別（與後端 JSON 一對一的 snake_case）並擴充 `MatchRecordDetailResponse.clutch_stats`；同步為既有測試 fixture 補上 `clutch_stats: null` 於 `apps/web/src/app/core/match-record-detail/match-record-detail-dialog.component.spec.ts` 與 `apps/web/src/app/core/match-record-detail/match-derived-stats/match-derived-stats.component.spec.ts`
- [ ] T010 [US1] 新增 `MatchClutchStatsComponent`（inputs：`clutchStats: ClutchStats | null`、`teamALabel`／`teamBLabel`）於 `apps/web/src/app/core/match-record-detail/match-clutch-stats/match-clutch-stats.component.{ts,html,scss}`：五個項目——局末階段（`endgame === null` 顯示「此賽制不適用」；標題帶 `endgame_from`）、平分延長（`deuce === null` 顯示「本場未進入平分延長」）、賽末點（`held === 0` 顯示「未曾握有賽末點」；否則「握有 N 次、第 k 次兌現／未兌現」＋「化解對手賽末點 M 次」）、比分狀態三組（次數＋百分比；`total === 0` 顯示「0／0」與「—」，MUST NOT 顯示 0%）、逆轉摘要（`comeback === null` 顯示「勝方全場未曾落後」；否則單一敘述同時點出兩方，FR-014）；`clutchStats === null` 顯示整塊無資料提示；所有文字以 `matchRecordDetail.clutch.*` 加入 `apps/web/src/assets/i18n/zh-TW.json` 與 `apps/web/src/assets/i18n/en.json`（depends on T009）
- [ ] T011 [US1] 於 `apps/web/src/app/core/match-record-detail/match-derived-stats/match-derived-stats.component.{ts,html}` 的「比分走勢摘要」區塊之後新增一個預設收合的原生 `<details>`，內掛 `<app-match-clutch-stats>`；於 `match-derived-stats.component.spec.ts` 新增一則斷言子元件有被渲染且位於走勢區塊之後的測試（depends on T010）
- [ ] T012 [US1] 前端測試於 `apps/web/src/app/core/match-record-detail/match-clutch-stats/match-clutch-stats.component.spec.ts`：有值的完整呈現、`endgame` 不適用、未進延長、敗方未曾握有賽末點、勝方第 k 次兌現、`total === 0` 顯示「—」而非 0%、`comeback === null`、`clutchStats === null` 的整塊提示（depends on T010）

**Checkpoint**：US1 可獨立展示——這是 MVP；四個 UI 入口自動全數套用。

---

## Phase 4: User Story 2 - 跨場個人技術儀表板（Priority: P1）

**Goal**：個人對戰紀錄頁顯示 18 項跨場指標（`all` 值），每項標示「依據 N 場／共 M 場」，並跟隨既有篩選條件。

**Independent Test**：quickstart.md 情境 6、7——指標恆 18 項、`matches_used` 依各指標納入條件、`team_serve` 的分子／分母等於各場詳情人工加總、篩選連動、翻頁不重抓、0 場空狀態。

### 儀表板基礎建設

- [ ] T013 [US2] 於 `apps/api/app/domains/member/service.py` 新增 `@dataclass(frozen=True) MemberMatchFilters`（既有 12 個篩選條件＋`group_id`，預設值同既有簽章）與 `FilteredMatch`（`match`／`summary`／`won`／`my_team`／`my_entry_id`），並把 `build_member_match_records()` 前半（查詢 → 我的隊伍與 roster entry → summaries → Python 端逐項篩選）抽成 `_filtered_member_matches(session, member_id, filters) -> list[FilteredMatch]`（排序維持 `ended_at desc, round_number desc`）；`build_member_match_records()` 的**對外簽章與回應完全不變**（內部自行組出 `MemberMatchFilters`）；以 `python -m pytest tests/unit/domains/member/test_member_match_records.py tests/unit/domains/member/test_member_group_history.py tests/contract/test_member_match_records_endpoint.py` 不改斷言全綠為準（research.md Decision 6）
- [ ] T014 [US2] 於 `apps/api/app/domains/group/service.py` 新增 `MatchStatInputs`（`completeness`、`raw_events`、`snapshots`、`placements`）與 `load_match_stat_inputs(session, matches) -> dict[UUID, MatchStatInputs]`：以 `match_id IN (...)`（每批 500 個 id）各查一次 `ScoreEvent`（`order_by(match_id, created_at, id)`）、`ScoreServeRecord`、`ShotPlacementRecord`，依 `match_id` 分組後經 T001 的轉接函式轉換；新增經資料庫的測試於 `apps/api/tests/unit/domains/group/test_match_stat_inputs.py`：多場比賽各自分組且事件順序正確、沒有事件的比賽 `completeness == "none"`、空輸入回傳 `{}`、3 場與 30 場比賽發出的查詢次數相同（research.md Decision 7）（depends on T001）

### 後端純函式（`all` 值）

- [ ] T015 [US2] 新增 `apps/api/app/domains/member/player_dashboard.py`：`frozen=True` dataclass `Ratio`／`PointLogSample`／`ServeSample`／`PlayerSample`／`MatchSample`／`MetricValue`／`MetricResult`／`TrendPoint`／`TrendSeries`／`LandingResult`／`DashboardResult`（欄位依 data-model.md「純函式模型 (2)」）、指標目錄常數（18 項的 `key`／`kind`／`better_when`，順序固定，依 data-model.md「指標目錄」）、函式簽章 `normalize_landing()`／`build_sample()`／`aggregate()`（本體先 `raise NotImplementedError`）；模組 MUST NOT import ORM 或 `AsyncSession`，只可 import `app.domains.group.match_stats` 的結果型別
- [ ] T016 [US2] Unit test（先紅燈）於 `apps/api/tests/unit/domains/member/test_player_dashboard.py`：`build_sample()`——(a) `my_team == "B"` 時挑 B 隊的階段／比分狀態／賽末點計數，`match_point_converted` 只在我方 `converted_on is not None` 時為真；(b) `clutch is None` → `point_log is None`，`serve is None` → `serve is None`；(c) 單打 → `own_serve`／`own_receive` 為 `None`，雙打取 `players[my_entry_id]`；(d) `player` 只在該場至少一位參賽者 `scored_total + lost_total > 0` 時有值（本階段 `*_landings` 先給空 list）；`aggregate()` 的 `all`——(e) 恆回傳 18 項且順序固定；(f) 比率為**總和相除**（用兩場 3/4 與 10/40 驗證結果為 13/44 而非兩個百分比的平均，FR-022）；(g) 各指標 `matches_used` 依納入條件（`endgame` 不計 `endgame is None` 的場、`deuce` 只計進過延長的場、`match_point_conversion` 只計 `held ≥ 1` 的場、`own_*` 不計單打、`avg_win_margin` 只計贏的場、`avg_loss_margin` 只計輸的場、最終比分類計全部）；(h) 有納入比賽但分母為 0 → `value is None` 且 `matches_used > 0`；(i) 沒有任何場具備資料 → `all is None`；(j) `scored_lost_ratio` 失分為 0 → `value is None`；(k) 空輸入 → `total_matches == 0`、`metrics == []`、`trends == []`、`landing is None`；(l) 本階段 `recent`／`verdict` 恆為 `None`、`has_comparison` 依 `total_matches > recent_window`（depends on T015）
- [ ] T017 [US2] 實作 `build_sample()`（落點以外的部分）與 `aggregate()` 的 `all` 值計算於 `apps/api/app/domains/member/player_dashboard.py`，使 T016 全綠（depends on T016）

### 後端 service／端點

- [ ] T018 [P] [US2] 於 `apps/api/app/domains/member/schemas.py` 新增 `DashboardMetricValue`／`DashboardMetric`／`DashboardTrendPoint`／`DashboardTrend`／`DashboardLanding`／`MemberMatchDashboardResponse`（依 data-model.md；時間欄位為 `datetime`，序列化為 ISO 8601 UTC）
- [ ] T019 [US2] 於 `apps/api/app/domains/member/service.py` 新增 `build_member_match_dashboard(session, member_id, filters) -> MemberMatchDashboardResponse`：`_filtered_member_matches()` → `load_match_stat_inputs()` → 逐場以**與單場詳情相同的純函式**（`effective_points`／`serve_stats`／`clutch_stats`／`player_landings`；儀表板用不到 `momentum_stats` 與 `tempo_stats`，不呼叫）推導 → `build_sample()` → `aggregate()` → 把 `DashboardResult` **完整**對映到 schema（含 `recent`／`verdict`／`trends`／`landing`，使 US3／US4 不需再改本函式）；`completeness != "complete"` 或 `effective_points()` 為 `None` 的比賽只提供最終比分類樣本；新增經資料庫的測試於 `apps/api/tests/unit/domains/member/test_member_match_dashboard.py`：(a) 只有一場比賽時，`team_serve`／`endgame`／`when_trailing`／`points_scored` 的分子分母等於該場 `build_match_record_detail()` 回應中我方對應欄位（FR-003）；(b) 混合詳細計分／簡易計分／單打／`partial` 紀錄的 `matches_used` 正確，`partial` 的比賽仍計入 `avg_points_for`；(c) 套用 `match_mode`／`date_from`／`partner` 篩選後 `total_matches` 等於同條件 `build_member_match_records().total_matches`（FR-019）；(d) 訪客 roster entry 依 028 綁定後的比賽被納入、未綁定者不納入；(e) 查詢次數不隨比賽場數成長（depends on T013, T014, T017, T018, T005）
- [ ] T020 [US2] 於 `apps/api/app/domains/member/router.py` 新增 dependency `match_filters_query(...) -> MemberMatchFilters`（宣告與 `get_member_match_records` 完全相同的 13 個篩選 `Query` 參數與驗證，**不含** `page`）與端點 `GET /members/me/match-dashboard`（`require_member`，`response_model=MemberMatchDashboardResponse`，docstring 列出 Errors: `MEMBER_TOKEN_INVALID`）；新增契約測試於 `apps/api/tests/contract/test_member_match_dashboard_endpoint.py`：回應形狀、18 項指標與固定順序、未登入 401、非法篩選值 422、帶 `page` 參數不影響結果、0 場比賽的空回應形狀（contracts/member-match-dashboard-api.md）（depends on T019）

### 前端

- [ ] T021 [P] [US2] 新增 `apps/web/src/app/core/api/player-dashboard.models.ts`（`DashboardMetricKey` 字串聯集＝指標目錄 18 個 key、`DashboardMetric`／`DashboardMetricValue`／`DashboardTrend`／`DashboardTrendPoint`／`DashboardLanding`／`MemberMatchDashboardResponse`），並於 `apps/web/src/app/features/auth/auth.service.ts` 新增 `getMatchDashboard(filters)`（重用 `getMatchRecords()` 既有的篩選參數組裝，不帶 `page`）
- [ ] T022 [US2] 新增 `apps/web/src/app/core/player-dashboard/dashboard-metric-card/dashboard-metric-card.component.{ts,html,scss}`（inputs：`metric: DashboardMetric`、`totalMatches`；顯示標題、依 `kind` 格式化的 `all.value`（rate → 百分比；average／ratio → 小數一位；count → 整數）、分子／分母文字、「依據 N 場／共 M 場」、`value === null` 時「0／0」與「—」、`all === null` 時該指標專屬的無資料提示；本階段不顯示對比欄）與 `apps/web/src/app/core/player-dashboard/player-dashboard.component.{ts,html,scss}`（inputs：`dashboard: MemberMatchDashboardResponse | null`、`loading`、`failed`；四個原生 `<details>` 群組——發球與接發球／關鍵分／得失分與分差／落點分布，第一組預設 `open`；指標依 `Record<DashboardMetricKey, group>` 對照表分組；發球群組固定顯示「每場第一分不列入」說明（FR-023）；`total_matches === 0` 以單一空狀態取代全部群組（FR-024）；落點群組本階段只放無資料提示）；所有文字以 `playerDashboard.*` 加入 `apps/web/src/assets/i18n/zh-TW.json` 與 `apps/web/src/assets/i18n/en.json`（depends on T021）
- [ ] T023 [US2] 於 `apps/web/src/app/features/member/match-history/match-history.component.{ts,html}` 在既有 hero 統計卡之後掛上 `<app-player-dashboard>`；新增 `dashboard`／`dashboardLoading`／`dashboardFailed` signals；儀表板請求只在初次載入與 `applyFilters()`（含清除篩選）時發出、帶目前篩選條件，`goToPage()` MUST NOT 觸發；於 `match-history.component.spec.ts` 新增測試：初次載入發一次、套用篩選再發一次且參數相同、翻頁不發、儀表板請求失敗不影響既有清單呈現（depends on T022, T020）
- [ ] T024 [US2] 前端測試於 `apps/web/src/app/core/player-dashboard/player-dashboard.component.spec.ts` 與 `apps/web/src/app/core/player-dashboard/dashboard-metric-card/dashboard-metric-card.component.spec.ts`：18 項指標各落在正確群組、`rate`／`average`／`count` 的格式、依據場數文字、「0／0 —」而非 0%、`all === null` 的專屬提示、0 場空狀態、`loading`／`failed` 狀態、第一群組預設展開（depends on T022）

**Checkpoint**：會員可在對戰紀錄頁看到跨場指標並隨篩選連動；尚無對比、趨勢、落點圖。

---

## Phase 5: User Story 3 - 最近表現對比與趨勢（Priority: P2）

**Goal**：每項指標同時顯示「最近 10 場 vs. 全部」與正確方向的進步／退步判定；可選定指標看 5 場移動趨勢。

**Independent Test**：quickstart.md 情境 8、9。

- [ ] T025 [US3] Unit test（先紅燈）於 `apps/api/tests/unit/domains/member/test_player_dashboard.py`：(a) `recent` 取輸入（新到舊）的前 10 場，再各自篩納入條件，`matches_used` 為實際場數；(b) `total_matches ≤ 10` → 所有 `recent is None`、`verdict is None`、`has_comparison is False`；(c) `recent.matches_used < 3` 或任一方 `value is None` → `verdict == "insufficient"`；(d) `better_when == "lower"`（`avg_loss_margin`、`points_lost`、`avg_points_against`）數值下降 → `"improved"`、上升 → `"declined"`；`"higher"` 反之（FR-026）；(e) 差異小於門檻（rate < 0.01；average／ratio < 0.1）→ `"unchanged"`；(f) `match_points_saved`（`better_when is None`）→ `verdict is None` 但 `recent` 仍有值；(g) 趨勢：具備資料的比賽 n ≥ 6 → 點數 `n − 4`、由舊到新、每點為連續 5 場的總和相除、`from_ended_at`／`to_ended_at` 為窗內最舊／最新；n < 6 → 該 key 不出現；`count` 類恆不出現；n = 70 → 只保留最新 60 點（research.md Decision 9/12）
- [ ] T026 [US3] 實作 `aggregate()` 的 `recent`／`verdict`／`trends` 於 `apps/api/app/domains/member/player_dashboard.py`，使 T025 全綠（depends on T025, T017）
- [ ] T027 [US3] 於 `apps/api/tests/unit/domains/member/test_member_match_dashboard.py` 與 `apps/api/tests/contract/test_member_match_dashboard_endpoint.py` 新增斷言：12 場比賽的會員回應含 `has_comparison: true`、`recent` 有值、`trends[].points[].from_ended_at` 為帶時區的 ISO 8601 字串；≤ 10 場的會員所有 `recent`／`verdict` 為 `null`（depends on T026, T020）
- [ ] T028 [US3] 前端：於 `apps/web/src/app/core/player-dashboard/dashboard-metric-card/dashboard-metric-card.component.{ts,html,scss}` 新增對比欄（`recent !== null` 時顯示「最近 10 場」數值、依據場數與差異；`verdict` 以**圖示＋文字**呈現——進步／退步／持平／樣本不足，MUST NOT 僅靠顏色；`verdict === null` 且 `recent !== null` 時只顯示數值）與「查看趨勢」按鈕（`aria-pressed`；`kind === 'count'` 不顯示）；新增 `apps/web/src/app/core/player-dashboard/dashboard-trend-chart/dashboard-trend-chart.component.{ts,html,scss}`（inputs：`series: DashboardTrend | null`、`kind`；手刻 SVG `polyline`，寫法比照 `apps/web/src/app/features/member/match-history/match-history.component.ts` 既有的 `roundTrendPolyline()`；`value === null` 的點斷線略過；每點 `<title>` 顯示日期區間與分子／分母；`aria-label` 摘要起訖值；`series === null` 顯示「比賽場數不足以呈現趨勢」）；`PlayerDashboardComponent` 新增 `selectedTrendKey` signal 並在群組下方顯示所選指標的趨勢；文字加入兩份語系檔（depends on T024）
- [ ] T029 [US3] 前端測試於 `dashboard-metric-card.component.spec.ts`、`apps/web/src/app/core/player-dashboard/dashboard-trend-chart/dashboard-trend-chart.component.spec.ts`、`player-dashboard.component.spec.ts`：`has_comparison === false` 不出現對比欄、四種 `verdict` 各有文字、越低越好的指標顯示「進步」、`count` 類無趨勢按鈕、選定指標後渲染對應折線、無 series 顯示不足提示、`null` 值點不畫（depends on T028）

---

## Phase 6: User Story 4 - 跨場落點彙總分布（Priority: P3）

**Goal**：一張「我方恆在左」的球場圖疊合跨場的得分／失分落點，可切換最近 10 場／全部。

**Independent Test**：quickstart.md 情境 10——同一物理落點以 A 隊與 B 隊身分記錄後座標相同、點數等於各場加總、界外保留、範圍切換、密集樣式。

- [ ] T030 [US4] Unit test（先紅燈）於 `apps/api/tests/unit/domains/member/test_player_dashboard.py`：(a) `normalize_landing(x, y, "A")` 原值、`"B"` → `(1 − x, 1 − y)`（旋轉而非鏡像：斷言 y 也被翻轉）；界外值 `-0.3`／`1.3` 互換後仍在範圍內；(b) 同一物理落點（我方視角的「對手右後角」）在 A、B 兩種身分下正規化後座標相等且 `x > 0.5`（SC-006）；(c) `build_sample()` 把 `player_landings()[my_entry_id]` 的 `scored`／`lost` 正規化後放入 `PlayerSample`；(d) `aggregate()` 的 `landing`：陣列為新到舊、座標四捨五入至小數 3 位、`recent_scored_count`／`recent_lost_count` 為最近 10 場的前綴長度、`*_total` 含未標落點的分數、`matches_used` 只計有 `player` 樣本的場；`total_matches ≤ 10` 時 `recent_*` 等於全體值；沒有任何落點 → `landing is None`（即使 `scored_total > 0`）
- [ ] T031 [US4] 實作 `normalize_landing()`、`build_sample()` 的落點部分與 `aggregate()` 的 `landing` 於 `apps/api/app/domains/member/player_dashboard.py`，使 T030 全綠（depends on T030, T026）
- [ ] T032 [US4] 於 `apps/api/tests/unit/domains/member/test_member_match_dashboard.py` 新增經資料庫的測試：同一會員在比賽甲屬 A 隊、比賽乙屬 B 隊，各記一筆我方視角相同位置的得分落點 → 回應 `landing.scored` 兩筆座標相等；`landing.scored` 長度等於各場 `build_match_record_detail().landing_distribution` 中該會員 `scored` 長度加總（depends on T031）
- [ ] T033 [P] [US4] 擴充 `CourtDiagramComponent`：新增選用輸入 `dense = input(false)`，為 `true` 時於宿主加上 `court--dense` class，使 `.court-marker` 縮小並降低不透明度（圓／菱形的形狀區分不變）；補測試（預設不加 class、既有測試不改斷言全綠）於 `apps/web/src/app/core/court-diagram/court-diagram.component.{ts,html,scss,spec.ts}`（research.md Decision 11）
- [ ] T034 [US4] 前端：於 `apps/web/src/app/core/player-dashboard/player-dashboard.component.{ts,html,scss}` 實作落點群組——`<app-court-diagram [isSinglesMatch]="false" [markers]="..." [dense]="markers.length > 150">`；「最近 10 場／全部」範圍切換鈕（`aria-pressed`；`has_comparison === false` 時不顯示），最近範圍以 `scored.slice(0, recent_scored_count)`／`lost.slice(0, recent_lost_count)` 取得；得分／失分各自的顯示切換；形狀＋文字圖例；圖下方文字「← 我方｜對手 →」（FR-031）；兩組「已標落點／總數」與「依據 N 場／共 M 場」隨範圍切換；`landing === null` 顯示無資料提示（說明需在詳細計分比賽中標示落點）；文字加入兩份語系檔；於 `player-dashboard.component.spec.ts` 新增測試：範圍切換取前綴、兩個顯示切換各自過濾、`dense` 門檻、我方標示存在、比例文字、`null` 提示（depends on T033, T029）

---

## Phase 7: User Story 5 - 好友檢視我的技術儀表板（Priority: P3）

**Goal**：好友戰績頁同樣呈現儀表板，可見性完全由 023 既有的設定與好友關係控管。

**Independent Test**：quickstart.md 情境 11。

- [ ] T035 [US5] 於 `apps/api/app/domains/member/service.py` 新增 `view_member_match_dashboard(session, viewer_id, member_id, filters)`（先 `await _resolve_viewable_member()`，再委派 `build_member_match_dashboard()`；MUST NOT 產生任何通知），並於 `apps/api/app/domains/member/router.py` 新增 `GET /members/{member_id}/match-dashboard`（`require_verified_member`；**宣告位置 MUST 在** `/members/me/match-dashboard` **之後**）；於 `apps/api/tests/contract/test_member_match_dashboard_endpoint.py` 新增測試：好友且對方開啟分享 → 200 且數值等於對方本人未篩選的回應；`SELF_VIEW_NOT_SUPPORTED`（400）、`MEMBER_NOT_FOUND`（404）、`FRIENDSHIP_REQUIRED`、`MATCH_RECORDS_PRIVATE` 四種拒絕的狀態碼與錯誤代碼與 `GET /members/{member_id}/match-records` 完全相同且回應不含儀表板欄位（SC-010）；對方關閉分享後再次請求即被拒絕（不快取資格）；`GET /members/me/match-dashboard` 仍命中本人端點而非被 `{member_id}` 攔截；請求前後 `notifications` 資料表筆數不變（FR-036）（depends on T020）
- [ ] T036 [P] [US5] 於 `apps/web/src/app/features/auth/auth.service.ts` 新增 `getFriendMatchDashboard(memberId)`（不帶篩選參數，寫法比照既有 `getFriendMatchRecords()`）
- [ ] T037 [US5] 於 `apps/web/src/app/features/friends/friend-match-records/friend-match-records.component.{ts,html}` 在既有彙總統計之後掛上 `<app-player-dashboard>`；儀表板請求失敗時 MUST NOT 顯示元件自己的錯誤（傳入 `dashboard = null`、`failed = false` 並整個不渲染），避免與該頁既有的「已設為不公開／非好友」提示重複；於 `friend-match-records.component.spec.ts` 新增測試：成功時渲染儀表板、`MATCH_RECORDS_PRIVATE` 時頁面只有一則既有提示且無儀表板 DOM（depends on T036, T035, T034）

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T038 [P] 語系檔一致性：確認 `zh-TW.json` 與 `en.json` 的 `matchRecordDetail.clutch.*` 與 `playerDashboard.*` 鍵集合完全相同、18 個 `playerDashboard.metric.<key>.{label,hint,empty}` 皆存在、模板中沒有寫死的中英文字串 in `apps/web/src/assets/i18n/`
- [ ] T039 後端品質關卡：`ruff check app/ tests/`、`mypy app/`、`python -m pytest tests/` 全數通過 in `apps/api/`（完整測試約 20 分鐘，於背景執行並把 `-rf` 輸出存檔；出現大量無法解釋的失敗先重跑一次再調查）
- [ ] T040 前端品質關卡：`npm run lint`、`npx tsc --noEmit -p tsconfig.app.json`、`npm test -- --watch=false` 全數通過 in `apps/web/`（`admin-page.component.spec.ts` 既有的 1 則 `NG04002` unhandled error 為本功能之前即存在）
- [ ] T041 效能驗證（SC-007，quickstart.md 情境 12）：以種子資料為一位會員建立 300 場含逐分事件的已完成比賽，量測 `GET /members/me/match-dashboard` < 3 秒、回應大小、以及 `GET /members/me/match-records` 回應時間與本功能前相當；結果記錄於 `specs/034-clutch-points-player-dashboard/quickstart.md` 情境 12 之下；未達標時回報而非自行加入快取（規格 Assumptions）
- [ ] T042 手機寬度版面檢查（FR-007、SC-009）：比賽詳情的關鍵分區塊預設收合且位於走勢摘要之後；對戰紀錄頁儀表板僅第一群組展開，既有對戰清單在 3 次捲動／點擊內可達；好友戰績頁亦同 in `apps/web/src/app/core/player-dashboard/`、`apps/web/src/app/core/match-record-detail/match-clutch-stats/`
- [ ] T043 依憲章「技術治理與品質關卡」於 PR 描述說明授權邊界：兩個新端點各自重用哪個既有 dependency、好友端點經同一個 `_resolve_viewable_member()` 且不快取資格、回應不含任何暱稱或他人識別資訊、未新增寫入路徑（plan.md Constitution Check 原則 IV）

---

## Dependencies & Execution Order

- **Foundational（T001–T002）** 兩項互不相依、可平行；T001 阻擋 T007 與 T014。
- **US1（T003–T012）** 不依賴任何儀表板任務，可最先獨立交付。
- **US2（T013–T024）** 依賴 Foundational 與 US1 的 `clutch_stats()`（T005）——儀表板的關鍵分指標直接呼叫它。T013、T014、T015 三者互不相依，可平行起步。
- **US3 → US4 依序疊在 US2 之上**：兩者都會修改 `player_dashboard.py` 的 `aggregate()` 與同一批前端元件檔，故 T031 依賴 T026、T034 依賴 T029，以避免同檔衝突；功能上 US4 並不需要 US3 的對比（僅「最近 10 場」範圍切換用到 `has_comparison`）。
- **US5（T035–T037）** 後端只依賴 US2 的端點（T020），可在 US2 完成後隨時進行；前端掛載（T037）排在 US4 之後，使好友頁一次得到完整的儀表板。
- 每個 Story 內：單元測試（紅）→ 純函式實作（綠）→ service／端點 → 前端 → 前端測試。標 [P] 的前端型別／schema 任務只依賴設計文件，可與同 Story 的後端任務平行。
- **Polish（T038–T043）** 於所有 Story 完成後進行。

## Parallel Example: User Story 1

```text
後端：T003 → T004 → T005 ─┬→ T007 → T008
      T006 [P] ───────────┘
前端：T009 [P] → T010 → T011
                     └→ T012        （與後端平行；T009 只依賴 data-model.md）
```

## Parallel Example: User Story 2

```text
基礎：T013 ║ T014 ║ T015 → T016 → T017      （三條線平行）
      T018 [P]
匯流：T019 → T020
前端：T021 [P] → T022 → T024
                     └→ T023（另需 T020）
```

## Implementation Strategy

1. **MVP**＝Foundational＋US1：所有逐分紀錄完整的比賽立刻多出關鍵分區塊，涵蓋面最廣、不需任何新端點，且 `clutch_stats()` 是儀表板關鍵分指標的前提。
2. **第二個增量**＝US2：儀表板的 `all` 值＋依據場數＋篩選連動——此時已能回答「我整體打得怎麼樣」。
3. **第三個增量**＝US3：對比與趨勢——回答「我有沒有在進步」，是使用者原始需求的核心。
4. US4（落點）與 US5（好友）依序疊加；任一未完成時，對應群組維持無資料提示／好友頁不顯示儀表板，不影響已完成者。
5. 每完成一個 Story 即執行該 Story 對應的 quickstart 情境，再進下一個。
