# Tasks: 對戰紀錄洞察（優缺點摘要、搭檔與對手戰績、比較基準）

**Input**: Design documents from `/specs/036-match-insights-benchmarks/`

**Prerequisites**: plan.md、spec.md、research.md、data-model.md、contracts/（4 份）、quickstart.md（皆已存在）

**Tests**：依 `plan.md` Constitution Check（原則 II），三個規則模組（`insights`、`matchups`、`group_benchmark`）與身分鍵的單元測試 MUST **先於**對應的實作任務完成並確認為失敗（紅燈）；`verify_ever_group_member()` 的修正 MUST 先有失敗的迴歸測試；兩支擴充端點與三支新端點 MUST 有契約測試。本檔案的測試任務為強制項，非選用。

**Organization**：依 spec.md 之 4 個 User Story（US1 P1、US2 P1、US3 P2、US4 P3）分階段。US1 與 US2 的**核心互不相依**，可平行——只有 US2 的兩項整合任務（T024 的對戰組合規則、T027 中摘要的點擊跳轉）需要 US1 先完成；US3 依賴 US1 的 `insights.derive()`（要把團內來源併進去）與 US2 的 `matchups.build()`（合併版摘要含對戰組合）；US4 依賴 US2 的 `matchups` 模組（交手紀錄）與 US3 的一個小函式 `overall_values()`（T030，可單獨提前）。每一個 Story 完成後皆可獨立上線。

## Format: `[ID] [P?] [Story] Description`

- **[P]**：可平行執行（不同檔案、無相依關係）
- **[Story]**：對應 spec.md 的 US1–US4；Setup／Foundational／Polish 階段任務無此標籤
- 每項任務皆附精確檔案路徑

## Path Conventions

沿用 `plan.md` Project Structure：後端 `apps/api/`，前端 `apps/web/src/`。

---

## Phase 1: Setup

*本 feature 無 Setup 任務——不新增第三方依賴、不新增環境變數、無 migration。*

---

## Phase 2: Foundational（Blocking Prerequisites）

**Purpose**：一個既有缺陷的修正（US3 重用的授權檢查），以及 US2／US3／US4 共用的身分鍵。

**⚠️ CRITICAL**：此階段完成前，不可開始 US2／US3／US4；US1 只依賴 T004。

- [X] T001 迴歸測試（**先紅燈**）：新增 `apps/api/tests/unit/domains/group/test_verify_ever_group_member.py`——(a) 同一會員在同一團有**兩列** `RosterEntry`（第一列 `status="left"`、第二列 `status="active"`，模擬離開後重新加入）→ `verify_ever_group_member()` MUST 不拋例外；(b) 只有一列 `left`／`kicked` → 通過；(c) 沒有任何列 → `ApiError("GROUP_MEMBERSHIP_NEVER_HELD")` 403；(d) 只有 `member_id IS NULL` 的訪客列 → 403。另於 `apps/api/tests/contract/test_member_groups_history_endpoints.py` 新增一條：兩段參與期間的會員 `GET /members/me/groups/{id}/history` → 200。確認 (a) 與契約案例在修正前失敗（預期 `MultipleResultsFound` → 500）；**若 (a) 沒有失敗，代表 research.md Decision 7 的前提不成立，須停下回報，不要修改程式**
- [X] T002 於 `apps/api/app/domains/group/service.py` 的 `verify_ever_group_member()`（約 L1019–1025）把查詢改為 `.limit(1)` 並以 `.first()` 取值，docstring 補一句說明為何不能用 `scalar_one_or_none()`（重新加入會新增名單列）。使 T001 全綠；`tests/contract/test_member_groups_history_endpoints.py` 與 `tests/contract/test_member_match_record_detail.py` 既有案例不改斷言全綠（depends on T001）
- [X] T003 [P] 身分鍵模組（同一任務內先測試後實作）：新增 `apps/api/tests/unit/domains/member/test_player_identity.py` 與 `apps/api/app/domains/member/player_identity.py`（無 ORM、不 import 任何 `service`）——`player_key(member_id: uuid.UUID | None, roster_entry_id: uuid.UUID) -> str`（有 `member_id` → `m:<uuid>`，否則 `r:<uuid>`）、`parse_player_key(value: str) -> tuple[Literal["m","r"], uuid.UUID]`（不符 `^(m|r):<uuid>$` → `ValueError`）、`@dataclass(frozen=True) PlayerRef(key, nickname, member_id: str | None)`。測試涵蓋：兩種鍵、往返一致、大小寫與多餘空白被拒、空字串被拒（data-model.md「身分鍵」）
- [X] T004 [P] 於 `apps/api/tests/unit/domains/_match_history.py` 的 `make_entry()` 新增 keyword 參數 `status: str = "active"` 與 `joined_at: datetime | None = None`（皆具預設值）；既有使用此 helper 的測試不改斷言全綠（`python -m pytest tests/unit/domains/group tests/unit/domains/member -q`）
- [X] T057 [P] 擴充 `apps/api/scripts/seed_dashboard_demo.py` 的**基本示範資料**（仍只允許 `rally_stats_test`），讓每個 Story 完成後即可跑對應的 quickstart 情境：依 quickstart.md「前置準備」除效能用的團以外的全部項目——`demo` 的比賽分布在兩個團、一位球友兩團不同暱稱、兩位不同球員同暱稱、一位高勝率搭檔（≥ 5 場）、一位低勝率對手（≥ 5 場）、一位只打 2 場的搭檔、`demo` 在其中一團離開後重新加入、好友 `friend@example.com`（開啟分享、與 `demo` 既當過對手也當過搭檔）。*編號 T057 是 `/speckit-analyze` 後追加（analyze F3），刻意不重編既有的 T005–T056 以免打亂任務間的交叉引用；執行順序以所在階段為準。*

**Checkpoint**：重新加入過的會員能開啟團歷史（quickstart 情境 0）；身分鍵可用；尚無任何畫面變化。

---

## Phase 3: User Story 1 - 優缺點自動摘要（Priority: P1）🎯 MVP

**Goal**：個人對戰紀錄頁前段以幾句話指出強項、待加強、最近變化，每句附依據的數字、可跳到對應指標；跟隨篩選；好友頁同樣呈現。

**Independent Test**：quickstart.md 情境 1–3——數字與儀表板逐位相等、重新整理與切換語言後項目與順序不變、發球／接發球只出現一句、不因「落後時得分率偏低」產生敘述、樣本不足與表現均衡各有明確說明。

### 後端

- [X] T005 [US1] Unit test（**先紅燈**）：新增 `apps/api/tests/unit/domains/member/test_insights.py`（無資料庫；以 `player_dashboard.build_sample()`／`aggregate()` 建輸入，比照 `test_player_dashboard.py` 既有的建構 helper）。依 data-model.md 規則表逐條：(a) `rate_vs_overall` 五個指標各自在偏離 0.0499／0.05／0.0999／0.10 的輕微／明顯邊界，高於基準 → strength、低於 → weakness；(b) **基準**（FR-011，實作時以模擬實測定案）：發球類為逐場的條件期望 `(得分−1)÷(總分−1)`、接發球類為 `得分÷(總分−1)`，以該場的指標分母加權——以兩場強弱懸殊的比賽手算一組數字斷言，並斷言它既不等於合併相除、也不等於逐場加權全場得分率；局末為涵蓋比賽的合併全場得分率；沒有該指標資料的比賽不影響基準；完封（對手 0 分）不拋例外；(c) 分母 29 分不產生候選、30 分產生；`matches_used` 2 不產生、3 產生；(d) `deuce_vs_even` 基準固定 0.50；(e) `when_leading`／`when_tied`／`when_trailing`／`match_point_conversion` 即使大幅偏離也**永不**以 `source="self"` 出現（FR-012、SC-003）；`match_points_saved` 不進任何規則；(f) 成對指標 `(team_serve, team_receive)`、`(own_serve, own_receive)` 每組只留偏離絕對值較大者，相同時留 weakness（FR-016）；(g) `error_share_high` 0.60／0.70 與分母 20 分門檻、`dominant_error` 只在該種類佔本人失誤 > 50% 時帶出；`winner_share_high` 0.50／0.60；(h) `recent_change`：只取 `verdict ∈ {improved, declined}`，`rate` 差 0.05／0.10、`average`／`ratio` 相對變化 15%／30%，「全部」的值為 0 時不產生候選、不拋例外；`has_comparison` 為假時 `recent` 為空；候選同時有進步與退步而前兩名皆退步時第二名換成排名最高的進步（FR-014）；(i) 排序：level → source → 樣本數 → `_METRICS` 順序（FR-015）；各清單上限 3／3／2；(j) `status`：無任何規則達最低樣本 → `insufficient_data`；有達樣本但無一達門檻 → `balanced`；否則 `ok`；零場比賽 → `insufficient_data`；(k) **同一輸入呼叫兩次結果完全相等**；(l) 每個 `params` 數字與輸入的 `MetricValue` 逐位相等；(m) `matchups=None`、`benchmark=None` 時 `matchups` 清單為空、`benchmark_group_name` 為 `None`；(n) **零偏差測試**——以固定亂數種子合成弱／中／強三種球員各 1,500 場，單場內每一分勝率固定、每場第一分不計入發球與接發球（同 033 FR-012）；三種球員的 `rate_vs_overall` 敘述皆為 0 句，且指標與 `expected_rate()` 的差距小於 1 個百分點；另一條對照測試斷言合併相除與逐場加權兩種直覺基準在發球上各偏離超過 0.8 個百分點、方向相反（SC-003；analyze F1）（FR-009、FR-010、FR-011、FR-013、FR-017、FR-018）
- [X] T006 [US1] 新增 `apps/api/app/domains/member/insights.py`（無 ORM／session；只 import `player_dashboard` 與 `player_identity`）：`InsightRule`／`InsightList`／`InsightLevel`／`InsightSource` 的 `Literal`、`Insight`、`InsightsResult`、模組頂端的具名門檻常數（research.md「門檻常數的位置」）、`derive(samples, dashboard, matchups=None, benchmark=None) -> InsightsResult`。本任務實作 `rate_vs_overall`、`deuce_vs_even`、`error_share_high`、`winner_share_high`、`recent_change` 與去重、排序、上限、`status`；`matchups`／`benchmark` 參數先接受但不使用（由 T024、T038 補上）。基準的算法見 research.md Decision 1——需要逐指標的 contribution，因此於 `apps/api/app/domains/member/player_dashboard.py` 新增一個公開的唯讀存取 `metric_specs() -> tuple[_MetricSpec, ...]`（只回傳既有的 `_METRICS`），**`aggregate()` 與 `_METRICS` 本體不動**。使 T005 全綠；`test_player_dashboard.py` 既有測試不改斷言全綠（depends on T005）
- [X] T007 [P] [US1] 於 `apps/api/app/domains/member/schemas.py` 新增 `DashboardInsightPlayer(key, nickname, member_id)`、`DashboardInsight(list, rule, level, source, metric_key, player, params)`、`DashboardInsights(status, benchmark_group_name, strengths, weaknesses, recent, matchups)`，並於 `MemberMatchDashboardResponse` 新增 `insights: DashboardInsights`（**具預設值**：`status="insufficient_data"`、四個空清單）；`rule`／`list`／`level`／`source` 的 `Literal` 值 MUST 與 `insights.py` 相同——於 `test_insights.py` 加一條以 `typing.get_args()` 比對兩邊的測試（contracts/member-match-dashboard-api.md）
- [X] T008 [US1] 於 `apps/api/app/domains/member/service.py` 的 `build_member_match_dashboard()`：保留已建好的 `samples` 清單，於 `aggregate()` 之後呼叫 `insights.derive(samples, result)` 並對映進回應。於 `apps/api/tests/unit/domains/member/test_member_match_dashboard.py` 新增：`insights` 隨篩選條件改變（只看雙打 vs. 全部）；每句的 `params.value`／`numerator`／`denominator`／`matches_used` 與同一回應 `metrics[]` 中同 key 的 `all` 逐位相等（FR-002）；**查詢次數與上線前相同**（沿用該檔既有的查詢計數斷言）（FR-019）（depends on T006、T007）
- [X] T009 [P] [US1] 契約測試於 `apps/api/tests/contract/test_member_match_dashboard_endpoint.py`：`insights` 的完整形狀；`EMPTY` 形狀新增預設的 `insights`；同一請求連打兩次 `insights` 的 JSON 完全相同（SC-002）；好友端點成功回應含 `insights` 且任何一句的 `source` 皆不為 `benchmark`；好友端點四種拒絕回應不含 `insights`；23 項 `metrics` 的 key、順序、數值與上線前相同；`typing.get_args(insights.InsightRule)` 等於 data-model.md 規則表的八個代碼（清單逐字抄入測試，與 T012 互為對照）；未驗證信箱的會員被拒（FR-004、FR-036、FR-037）（depends on T008）

### 前端

- [X] T010 [P] [US1] 型別與 fixture：於 `apps/web/src/app/core/api/player-dashboard.models.ts` 新增 `INSIGHT_RULES`（常數陣列，值與順序同 data-model.md 規則表）、`InsightRule`、`InsightList`、`InsightLevel`、`InsightSource`、`DashboardInsightPlayer`、`DashboardInsight`、`DashboardInsights`，並為 `MemberMatchDashboardResponse` 加上 `insights`；於 `apps/web/src/app/core/player-dashboard/dashboard-fixtures.ts` 補上預設的空 `insights` 與一個建構 helper `insight(overrides)`
- [X] T011 [US1] 新增 `apps/web/src/app/core/player-insights/player-insights.component.{ts,html,scss}`（`app-player-insights`；inputs：`insights: DashboardInsights | null`、`loading`、`pendingBenchmark: boolean = false`、`benchmarkOmittedByFilters: boolean = false`；outputs：`metricPicked: DashboardMetricKey`、`playerPicked: string`）。四個清單各一個小節（`matchups` 清單為空且 `status="ok"` 時整節不顯示——US2 上線前它恆為空）；每句是原生 `<button>`，內容＝圖示＋`playerInsights.rule.<rule>.<variant>` 組出的句子＋一行 `playerInsights.evidence`（分子／分母、百分比、依據場數）；強項／待加強、進步／退步以**圖示與文字**區分，不只靠顏色（FR-006）；規則 → 語系 key 的對應是 exhaustive `Record<InsightRule, …>`；`status` 為 `insufficient_data`／`balanced` 時以單一說明取代四個清單；個別清單為空時顯示該清單的說明行（FR-018）；暱稱一律經 `<app-nickname>` 或插值帶入，**不使用 `innerHTML`**（FR-008）。同時於 `apps/web/src/assets/i18n/zh-TW.json` 與 `en.json` 新增 `playerInsights.*`（data-model.md「語系 key」；待加強的句型為描述事實的建設性語氣，FR-020）（FR-003、FR-005、FR-010）（depends on T010）
- [X] T012 [US1] 前端測試：新增 `apps/web/src/app/core/player-insights/player-insights.component.spec.ts`——四個清單與上限、三種 `status`、空清單說明行、每句有非顏色的區分標記、點擊發出正確的 `metricPicked`／`playerPicked`、`pendingBenchmark` 與 `benchmarkOmittedByFilters` 各自的說明行；另以實際讀入兩份語系檔的方式斷言 `INSIGHT_RULES` 每條規則的每個變體在 `zh-TW.json` 與 `en.json` **都存在**；`INSIGHT_RULES` 等於 data-model.md 規則表的同一份八個代碼（逐字抄入，與 T009 互為對照）（depends on T011）
- [X] T013 [P] [US1] 指標卡錨點與聚焦：於 `apps/web/src/app/core/player-dashboard/dashboard-metric-card.component.html` 的 `<article>` 加上 `[attr.id]="'metric-' + m.key"` 與 `tabindex="-1"`；於 `apps/web/src/app/core/player-dashboard/player-dashboard.component.ts` 新增公開方法 `focusMetric(key: DashboardMetricKey): void`——以既有的 `GROUP_OF` 找出群組、把該群組的 `<details>` 設為 `open`、`scrollIntoView({ block: 'center' })`、`focus()`；於 `player-dashboard.component.spec.ts` 新增：收合中的群組被展開、焦點落在正確的卡片、未知 key 不拋例外（research.md Decision 11；FR-010）
- [X] T014 [US1] 於 `apps/web/src/app/features/member/match-history/match-history.component.{ts,html}`：在 hero 卡片與 `<app-player-dashboard>` **之間**放入 `<app-player-insights [insights]="dashboard()?.insights ?? null" [loading]="dashboardLoading()" (metricPicked)="…" />`；以 `viewChild(PlayerDashboardComponent)` 呼叫 `focusMetric()`；儀表板請求失敗時摘要區塊不顯示（沿用 `dashboardFailed()`），不影響其他內容（FR-007）。於 `match-history.component.spec.ts` 新增對應測試（depends on T011、T013）
- [X] T015 [US1] 於 `apps/web/src/app/features/friends/friend-match-records/friend-match-records.component.{ts,html}`：在好友的儀表板上方放入 `<app-player-insights>`（資料來自既有的 `getFriendMatchDashboard()` 回應），點擊同樣呼叫 `focusMetric()`；於 `friend-match-records.component.spec.ts` 新增：摘要有呈現、好友關閉分享時不殘留（沿用既有的拒絕流程）（depends on T011、T013）

**Checkpoint**：會員不需任何點擊即可讀到自己的強項與待加強；US1 可獨立上線。

---

## Phase 4: User Story 2 - 搭檔與對手戰績（Priority: P1）

**Goal**：搭檔戰績＋擴充後的對手戰績（平均分差、依身分彙總、重點摘要、排序）；點某個人 → 整頁縮小到與他有關的比賽；摘要新增「對戰組合」清單。

**Independent Test**：quickstart.md 情境 4–6——與對戰清單人工核對一致、同人不同暱稱合併、不同人同暱稱分開、「場數少」標示、點擊後整頁同步縮小且不帶進暱稱相近的人、只打單打時顯示說明。

### 後端

- [X] T016 [US2] Unit test（**先紅燈**）：新增 `apps/api/tests/unit/domains/member/test_matchups.py`（無資料庫）——`build()`：(a) 同一 `m:` 鍵在不同暱稱下合併為一列、顯示暱稱取 `ended_at` 最大的那一場；(b) 不同鍵同暱稱（含兩位 `"Deleted User"`）分為兩列；(c) 雙打的兩位對手各計一次、`margin` 各計一次；(d) 單打不進 `partner_records`、`doubles_matches` 正確；(e) 同一人既當搭檔也當對手 → 兩個列表各一列；(f) `avg_margin` 可為負、四捨五入到 0.1；(g) `low_sample` 在 2 場為真、3 場為假；(h) 排序：`matches` 由多到少、同場數依 `player_key`；(i) 四個重點摘要的門檻（最常 ≥ 3、最佳／最難纏 ≥ 5）、勝率相同取場數多者、再相同取 `player_key` 較小者、無人達門檻 → `None`；(j) `overall_win_rate`／`doubles_win_rate`，零場 → `None`；(k) 空輸入不拋例外（FR-021、FR-022、FR-024）
- [X] T017 [US2] 新增 `apps/api/app/domains/member/matchups.py`（無 ORM；只 import `player_identity`）：`MatchupInput`、`MatchupRecord`、`MatchupHighlights`、`MatchupResult`、常數 `LOW_SAMPLE_BELOW = 3`／`HIGHLIGHT_MIN_MATCHES = 5`、`build(inputs) -> MatchupResult`（data-model.md「純函式模型 (1)」）。使 T016 全綠（depends on T003、T016）
- [X] T018 [P] [US2] 於 `apps/api/app/domains/group/schemas.py` 新增 `MatchupRecord`（`OpponentRecord` 既有五個欄位＋`player_key`、`member_id`、`avg_margin`、`low_sample`）與 `MatchupHighlights`；`MemberMatchRecordsResponse.opponent_records` 型別改為 `list[MatchupRecord]`，新增 `partner_records: list[MatchupRecord] = []`、`matchup_highlights`（具預設值）、`doubles_matches: int = 0`。**`OpponentRecord` 與 `GroupMatchRecordsResponse.player_records` 不動**（contracts/member-match-records-api.md）
- [X] T019 [US2] 於 `apps/api/app/domains/member/service.py`：新增 `_matchup_inputs(filtered: list[FilteredMatch]) -> list[matchups.MatchupInput]`（由 `item.summary.team_a/team_b` 與 `item.my_team`／`item.my_entry_id` 轉出；自己以 `roster_entry_id` 排除；`margin` 取自 `match.score_a/score_b`），並以 `matchups.build()` **取代** `build_member_match_records()` 中的 `opponent_tallies`（約 L1366–1399）。於 `apps/api/tests/unit/domains/member/test_member_match_records.py`：新增搭檔列表、分差、`doubles_matches`、跨團合併（同一會員兩個團、兩個暱稱）；**把既有以暱稱斷言合併的案例改為以 `player_key` 斷言**，並在改寫處留註解指向 research.md Decision 3；確認不新增查詢、不寫入任何資料（FR-001、FR-021、FR-022）（depends on T017、T018）
- [X] T020 [US2] Unit test（**先紅燈**）於 `apps/api/tests/unit/domains/member/test_member_match_records.py`：`partner_key` 只留該球員與我同隊的比賽、`opponent_key` 只留他在對方的比賽；與既有 `partner`／`opponent1`（暱稱子字串）同時生效（AND）；暱稱相近但不同人的比賽**不被帶入**；同一會員在別團的不同暱稱**會被帶入**；`r:` 鍵可篩訪客；格式正確但無符合 → 空結果而非錯誤；並於 `test_member_match_dashboard.py` 新增一條：同一組 `partner_key` 下儀表板的 `total_matches` 等於對戰紀錄的 `total_matches`
- [X] T021 [US2] 兩個精確篩選參數（research.md Decision 4——**要加在四個地方**）：`apps/api/app/domains/member/service.py` 的 `MemberMatchFilters`＋`partner_key`／`opponent_key`、`_filtered_member_matches()` 的後置篩選（以 `player_identity.player_key()` 比對該場搭檔／對手）、`build_member_match_records()` 與 `view_member_match_records()` 各新增兩個 keyword 參數；`apps/api/app/domains/member/router.py` 的 `match_filters_query`、`get_member_match_records`、`get_viewed_member_match_records` 各新增兩個 `Query(max_length=40)` 參數，路由層以 `parse_player_key()` 驗證，`ValueError` → `ApiError("INVALID_PLAYER_KEY", status_code=422)`；三支路由的 docstring 補上新參數與錯誤代碼。另於 `apps/api/tests/unit/domains/member/test_member_match_records.py` 新增**守門測試**：以 FastAPI 路由內省取出四支路由（`/members/me/match-records`、`/members/{member_id}/match-records`、`/members/me/match-dashboard`、`/members/{member_id}/match-dashboard`）的 query 參數名稱，斷言去掉 `page` 後四者集合完全相同。使 T020 全綠（FR-023）（depends on T019、T020）
- [X] T022 [P] [US2] 契約與整合測試：`apps/api/tests/contract/test_member_match_records_endpoint.py`——新欄位的形狀、既有五個欄位仍在、`partner_key` 格式不合 → 422 `INVALID_PLAYER_KEY`、好友端點回傳相同欄位且四種拒絕回應不含；`apps/api/tests/contract/test_member_groups_history_endpoints.py`——團歷史的既有斷言不變（其個人統計維持原本五個欄位，見契約）；`apps/api/tests/integration/test_member_match_records_flow.py`——以 `opponent_key` 請求對戰紀錄與儀表板，兩者 `total_matches` 一致（depends on T021）
- [X] T023 [US2] Unit test（**先紅燈**）擴充 `apps/api/tests/unit/domains/member/test_insights.py`：`partner_above_overall`（基準為 `doubles_win_rate`；一起出賽 4 場不產生、5 場產生；差 0.15／0.30 的輕微／明顯）、`opponent_below_overall`（基準為 `overall_win_rate`）；搭檔、對手各至多一句、各取差距最大者；`low_sample` 的列永不被選；`player` 欄位帶出 `key`／`nickname`／`member_id`；`params` 與 `MatchupRecord` 逐位相等（FR-025、US2-11）
- [X] T024 [US2] 於 `apps/api/app/domains/member/insights.py` 實作上述兩條規則；於 `apps/api/app/domains/member/service.py` 的 `build_member_match_dashboard()` 以 `_matchup_inputs()`＋`matchups.build()` 產生 `MatchupResult` 傳入 `derive()`（不新增查詢——`FilteredMatch` 已在手上）。使 T023 全綠；於 `test_member_match_dashboard.py` 新增一條：`insights.matchups[].params` 與同一組篩選下對戰紀錄回應的 `partner_records`／`opponent_records` 中同一 `player_key` 的數字相等（depends on T008、T019、T023）

### 前端

- [X] T025 [P] [US2] 於 `apps/web/src/app/core/api/group-member-view.models.ts` 新增 `MatchupRecord extends OpponentRecord`（＋`player_key`、`member_id`、`avg_margin`、`low_sample`）、`MatchupHighlights`；`MemberMatchRecordsResponse` 加上 `partner_records`、`matchup_highlights`、`doubles_matches` 並把 `opponent_records` 型別改為 `MatchupRecord[]`；`MemberMatchRecordFilters` 加上 `partner_key?`／`opponent_key?`（`auth.service.ts` 的 `withMatchFilters()` 會原樣送出，不需修改——於該服務的 spec 加一條確認）
- [X] T026 [US2] 新增 `apps/web/src/app/core/matchup-records/matchup-records.component.{ts,html,scss,spec.ts}`（`app-matchup-records`；inputs：`titleKey`、`records: MatchupRecord[]`、`highlights: { mostKey: string | null; bestKey: string | null }`、`highlightLabels`、`emptyKey`、`clickable: boolean = true`；output：`picked: MatchupRecord`）。每列：暱稱（`<app-nickname>`）、場數、勝敗、勝率長條（沿用既有 `.ranking-row` 的樣式）、平均分差（帶正負號）、「場數少」標記；列帶 `[attr.id]="'matchup-' + r.player_key"`；`clickable` 為真時整列是 `<button>`，為假時是一般列；三顆排序按鈕（場數／勝率／平均分差，預設場數，`aria-sort`）——**純呈現排序**，不改變重點摘要；列表上方顯示重點摘要；整個區塊包在 `<details>` 內，**預設展開**（既有的對手排行原本恆可見；SC-005 的 2 次點擊以展開狀態為準）。語系 key `member.matchHistory.matchups.*` 與 `INVALID_PLAYER_KEY` 的錯誤訊息加入兩份語系檔。spec：三種排序、`low_sample` 標示、重點摘要、`clickable=false` 時列不是按鈕、空狀態、預設為展開（FR-003、FR-024）（depends on T025）
- [X] T027 [US2] 於 `apps/web/src/app/features/member/match-history/match-history.component.{ts,html,scss}`：以兩個 `<app-matchup-records>`（搭檔在前、對手在後；搭檔列表的 `highlights` 取 `most_played_partner`／`best_partner`，對手列表取 `most_faced_opponent`／`toughest_opponent`）**取代**既有的 `.opponent-ranking` 區塊（html 約 L172–190）與已無用途的 `rankBadge()`；`doubles_matches === 0` 時搭檔區塊顯示 `noDoubles` 說明（FR-026）；新增 signal `pickedPlayer: { role: 'partner' | 'opponent'; record: MatchupRecord } | null`，`load()` 組篩選時把它併入 `partner_key`／`opponent_key`；`hasActiveFilters` 納入它；篩選面板上方顯示作用中對象的 chip（「只看與 X 搭檔的比賽」／「只看對上 X 的比賽」）與一顆清除鈕——chip 的清除鈕**只**移除這個對象、不動表單上的其他條件；表單既有的「清除篩選」則連同這個對象一併清掉（兩種條件同時生效、各自可清除，規格 Edge Cases）；摘要的 `playerPicked` → 展開對應的 `<details>` 並捲動到 `#matchup-<key>`。於 `match-history.component.spec.ts`：兩個新參數進入**兩支**請求、chip 與清除、點擊後回到第 1 頁、既有的對手排行斷言改為新元件（FR-023）（depends on T014、T026）
- [X] T028 [US2] 於 `apps/web/src/app/features/friends/friend-match-records/friend-match-records.component.html`：儀表板下方放入兩個 `<app-matchup-records [clickable]="false">`（資料已在既有的 `getFriendMatchRecords()` 回應中）；摘要的 `playerPicked` → 展開對應的 `<details>` 並捲動到 `#matchup-<key>`（FR-010）；於 `friend-match-records.component.spec.ts`：有呈現、列不可點擊、點擊對戰組合敘述會捲動到該列、頁面仍沒有篩選表單（FR-037）（depends on T026）

**Checkpoint**：會員能回答「我跟誰搭最順、老是輸給誰」，並一鍵縮小到與某人有關的比賽；US2 可獨立上線。

---

## Phase 5: User Story 3 - 團內比較（Priority: P2）

**Goal**：選定一個自己曾加入的團，看到每項指標的團內平均、我的名次與比較人數；匿名由回應結構保證；名列前後四分之一的指標併入摘要。

**Independent Test**：quickstart.md 情境 7–9——平均／人數／名次與人工計算一致、回應全文不含他人資料、從未加入的團 403 而已離團／已解散 200、團內來源在有篩選時退場。

### 後端

- [X] T029 [US3] 重構 `apps/api/app/domains/member/service.py::_dashboard_sample()`（約 L1420–1466）為兩步：`_match_derivations(match, summary, inputs) -> _MatchDerivations`（每場一次：`participants`、`points`、`clutch`、`serve`、`landings`、`ending`、`is_doubles`）與 `_sample_from(d: _MatchDerivations, *, match, my_team, my_entry_id, won) -> MatchSample`（只呼叫 `player_dashboard.build_sample()`）；`_dashboard_sample()` 保留為兩者的組合，`build_member_match_dashboard()` 行為不變。**先**跑 `tests/unit/domains/member/test_member_match_dashboard.py` 與 `tests/contract/test_member_match_dashboard_endpoint.py` 確認全綠、重構後**不改任何斷言**仍全綠（research.md Decision 5）（depends on T024）
- [X] T030 [P] [US3] 於 `apps/api/app/domains/member/player_dashboard.py` 新增 `overall_values(samples) -> dict[str, MetricValue]`——對 `_METRICS` 逐項呼叫既有的 `_metric_value()`，不算對比、趨勢、落點；於 `apps/api/tests/unit/domains/member/test_player_dashboard.py` 先寫測試：對同一批 sample，`overall_values()[key]` 與 `aggregate().metrics` 中同 key 的 `all` **逐項相等**（含 `None`）；空清單不拋例外
- [X] T031 [US3] Unit test（**先紅燈**）：新增 `apps/api/tests/unit/domains/member/test_group_benchmark.py`（無資料庫）——(a) `matches_used` 4 不納入、5 納入；`value is None` 不納入；(b) 達門檻者 2 人 → `pool_too_small`（平均與名次皆 `None`）、3 人 → `ok`；(c) `status` 判定順序：`pool_too_small` → `no_direction` → `self_below_minimum` → `ok`；(d) 我未達門檻時 `pool_size` 不含我、有平均、無名次；(e) `better_when="higher"` 最大者第 1、`"lower"` 最小者第 1；(f) 並列跳號（1224）；另以同一組整數輸入呼叫 `group.service._assign_standard_competition_ranks()`，斷言兩者名次相同；(g) `group_average` 為每人等權的算術平均（**不是**分子分母加總相除），四捨五入規則同 034；(h) 我在此團沒有該指標資料 → `mine is None`；(i) 回傳 23 項、順序同 `_METRICS`；(j) **`BenchmarkResult` 的任何欄位都不含其他球員的鍵或數值**（以 `dataclasses.asdict()` 後的全文搜尋斷言）；(k) `rank_from_bottom`：以相反方向、同一規則排出；最後一名並列兩人時兩人皆為 1；全員數值相同時 `rank` 與 `rank_from_bottom` 皆為 1；非 `ok` 的指標為 `None`（FR-030、FR-031）
- [X] T032 [US3] 新增 `apps/api/app/domains/member/group_benchmark.py`（無 ORM）：`PlayerValues`、`BenchmarkMetric`、`BenchmarkResult`、常數 `MIN_MATCHES_PER_PLAYER = 5`／`MIN_POOL = 3`／`QUARTILE_MIN_POOL = 4`、`build(me_key, players) -> BenchmarkResult`；`BenchmarkMetric` 含 `rank_from_bottom`（只供 `insights` 使用）。使 T031 全綠（depends on T030、T031）
- [X] T033 [P] [US3] 於 `apps/api/app/domains/group/service.py` 新增公開的 `load_group_completed_matches(session, group_id) -> list[tuple[Match, MatchRecordSummary]]`——包住既有的 `_completed_matches_query()`＋`_build_match_record_summaries()`，不帶篩選與分頁、參賽者一次查詢載入；於 `apps/api/tests/unit/domains/group/` 對應的測試檔新增：只回傳 `completed`、已捨棄的比賽不在其中、查詢次數與比賽數無關
- [X] T034 [P] [US3] 於 `apps/api/app/domains/member/schemas.py` 新增 `BenchmarkGroupOption`、`BenchmarkGroupsResponse`、`GroupBenchmarkGroup`、`GroupBenchmarkMetric`、`GroupBenchmarkResponse`（contracts/group-benchmark-api.md）。**`GroupBenchmarkMetric` MUST NOT 有任何可放他人資料的欄位**——只有 `key`、`kind`、`better_when`、`mine`、`status`、`group_average`、`pool_size`、`rank`；純函式的 `rank_from_bottom` **不進回應**（research.md Decision 6）
- [X] T035 [US3] Unit test（**先紅燈**，經資料庫）：新增 `apps/api/tests/unit/domains/member/test_member_group_benchmark.py`——`list_benchmark_groups()`：回傳的每一個團都能通過 `verify_ever_group_member()`（同一個條件）；含已離開／已被踢除／已解散的團、不含以訪客身分參加的團、依 `my_completed_matches` 由多到少；`build_group_benchmark()`：(a) 訪客名單球員（`member_id IS NULL`）被納入比較人數；(b) 會員多段參與期間（兩列名單）合併為一人；(c) 已離團球員被納入；(d) `mine` 等於 `build_member_match_dashboard(session, me, MemberMatchFilters(group_id=…))` 同 key 的 `all`（FR-029）；(e) 只計該團的比賽——我在別團的比賽不影響 `mine`；(f) 從未加入 → `GROUP_MEMBERSHIP_NEVER_HELD`；(g) 查詢次數在 5 場與 50 場時相同；(h) 只用簡易計分的團只有 `avg_*` 四項可能為 `ok`
- [X] T036 [US3] 於 `apps/api/app/domains/member/service.py` 新增 `list_benchmark_groups(session, member_id)`（團的範圍＝我曾有 `member_id` 名單列的團，與 `verify_ever_group_member()` 同一個條件；場數以一個 group-by 查詢取得）與 `build_group_benchmark(session, member_id, group_id)`：`verify_ever_group_member()` → `load_group_completed_matches()` → `load_match_stat_inputs()` → 每場 `_match_derivations()` **一次** → 對每位參賽者 `_sample_from()` → 依 `player_key` 分組 → `overall_values()` → `group_benchmark.build()`。查詢全部完成後，純運算（每場推導之後的所有步驟）以 `asyncio.to_thread()` 執行（比照 `app/core/email.py`）；傳入執行緒的 MUST 是已脫離 session 的純資料，不得在執行緒內碰 ORM 物件的延遲載入屬性。使 T035 全綠（FR-027、FR-028）（depends on T002、T029、T032、T033、T034、T035）
- [X] T037 [US3] Unit test（**先紅燈**）擴充 `apps/api/tests/unit/domains/member/test_insights.py`：`benchmark_quartile`——`pool_size` 3 不產生、4 產生；`q = pool_size // 4`（無條件捨去）：5 人時只有第 1 名與倒數第 1 名、8 人與 9 人時前 2 名與倒數 2 名；並列佔用名額——4 人中 2 人並列最後、7 人中 5 人並列第一皆不產生，8 人中 2 人並列第一則兩人皆為 strength；全員數值相同 → 不產生；「明顯」需第 1 名或倒數第 1 名**且** `pool_size ≥ 8`，4 人的團一律為輕微；排序的樣本數取 `mine.matches_used`；只取 `status="ok"` 的指標；**同一 `metric_key` 同時有 benchmark 與 self 候選時只留 benchmark**；排序中 benchmark 先於 self；`recent` 清單不受去重影響；`benchmark_group_name` 被帶出；`params.mine`／`group_average`／`rank`／`pool_size` 與 `BenchmarkMetric` 逐位相等；`when_trailing` **可以**經由此來源出現（FR-012 只排除自我對比）
- [X] T038 [US3] 於 `apps/api/app/domains/member/insights.py` 實作 `benchmark_quartile` 與跨來源去重；於 `build_group_benchmark()` 末段另算一次本人**未篩選**的跨團儀表板（`_filtered_member_matches()`＋`aggregate()`＋`matchups.build()`），以 `derive(samples, dashboard, matchups, benchmark=…)` 產生已合併的 `insights` 放進回應（research.md Decision 2）。使 T037 全綠；於 `test_member_group_benchmark.py` 新增：`insights` 中 `benchmark_quartile` 的參數與 `metrics[]` 同 key 相等（FR-033）（depends on T036、T037）
- [X] T039 [US3] 於 `apps/api/app/domains/member/router.py` 新增 `GET /members/me/benchmark-groups` 與 `GET /members/me/group-benchmark`（`group_id: uuid.UUID` 為必填 query；皆 `require_verified_member`；宣告在 `/members/{member_id}/…` 系列**之前**），docstring 列出 Errors。新增 `apps/api/tests/contract/test_member_group_benchmark_endpoint.py`：兩支端點的形狀；未驗證信箱被拒；從未加入 → 403；已離開、已被踢除、已解散、兩段參與期間各 → 200；多送的篩選參數被忽略；不存在的 `group_id` → 403 `GROUP_MEMBERSHIP_NEVER_HELD`；**匿名掃描**——建立暱稱各異的其他球員（含一位會員、一位訪客），斷言回應 JSON 全文不含其中任何一個暱稱、`member_id`、`roster_entry_id`（SC-007；FR-028、FR-036、FR-038）（depends on T038）

### 前端

- [X] T040 [P] [US3] 新增 `apps/web/src/app/core/api/group-benchmark.models.ts`（`BenchmarkGroupOption`、`BenchmarkStatus`、`GroupBenchmarkMetric`、`GroupBenchmarkResponse`）；於 `apps/web/src/app/features/auth/auth.service.ts` 新增 `getBenchmarkGroups()` 與 `getGroupBenchmark(groupId)`；新增 `apps/web/src/app/core/benchmark-group-preference.ts`（`getBenchmarkGroup(memberId)`／`setBenchmarkGroup(memberId, groupId)`，key `rally-stats:benchmark-group:<memberId>`，比照 `core/score-swap-preference.ts`，存取一律包 try/catch）與其 spec（`localStorage` 拋例外時回傳 `null`／不拋）（FR-027）
- [X] T041 [US3] 新增 `apps/web/src/app/features/member/match-history/group-benchmark/group-benchmark.component.{ts,html,scss,spec.ts}`（`app-group-benchmark`；inputs：`groups`、`selectedGroupId`、`benchmark`、`loading`、`failed`；outputs：`opened`、`groupChanged`）。預設收合的 `<details>`，展開時發出 `opened`；原生 `<select>` 選團（選項顯示團名與狀態）；一行 `scopeNote`「固定以此團的全部比賽計算」（FR-032）；依儀表板既有的群組順序列出指標，每列：我的值（沿用 `dashboard-format.ts` 的格式化）、團內平均、`第 r 名／共 n 人`；四種 `status` 各自的呈現（`poolTooSmall`／`selfBelowMinimum`／`noDirection` 以文字說明，不留空白格）；`groups` 為空 → `noGroups` 說明（US3-10）。語系 key `groupBenchmark.*` 加入兩份語系檔。spec：四種 `status`、無團說明、選團發出事件、窄螢幕下表格不產生水平溢出的結構斷言、預設為收合（FR-003、FR-031）（depends on T040）
- [X] T042 [US3] 於 `apps/web/src/app/features/member/match-history/match-history.component.{ts,html}` 接線（research.md Decision 9）：(a) 沒有記住的團 → 直到 `opened` 才載入 `getBenchmarkGroups()`，並以第一筆為預設發出請求；(b) 有記住的團 → 儀表板回應到達後於背景載入；(c) 選團 → 寫入偏好並重新請求；(d) 記住的團回 403／404 → 改用預設並覆寫偏好；(e) **摘要來源的單一規則**：已載入團內比較**且** `hasActiveFilters()` 為假 → `<app-player-insights>` 顯示團內比較回應的 `insights`，否則顯示儀表板回應的；載入中傳 `pendingBenchmark`；已選定團但有篩選 → 傳 `benchmarkOmittedByFilters`（FR-034）；(f) 團內比較失敗不影響其他內容。前端**不做**任何合併、排序或門檻判斷。於 `match-history.component.spec.ts` 新增上述六點各一條（FR-027）（depends on T027、T041）

**Checkpoint**：會員知道自己的每項指標在團裡排第幾；US3 可獨立上線。

---

## Phase 6: User Story 4 - 與好友並排比較（Priority: P3）

**Goal**：在好友戰績頁把自己的數字放在旁邊，並看到兩人互為對手／搭檔的紀錄。

**Independent Test**：quickstart.md 情境 10——並排數值各自等於雙方未篩選的儀表板、雙方皆達 3 場才標示較佳、交手紀錄與對戰清單核對一致、關閉分享後全部被拒。

- [X] T043 [US4] Unit test（**先紅燈**）擴充 `apps/api/tests/unit/domains/member/test_matchups.py`：`head_to_head(inputs, friend_key)`——互為對手與互為搭檔各自的場數／勝敗／勝率／平均分差，皆從檢視者角度；從未互為對手 → `as_opponents is None`；從未同隊 → `as_partners is None`；兩者皆無 → 兩個 `None`；單打只會計入 `as_opponents`
- [X] T044 [US4] 於 `apps/api/app/domains/member/matchups.py` 新增 `MatchupTally`、`HeadToHead`、`head_to_head()`。使 T043 全綠（depends on T017、T043）
- [X] T045 [P] [US4] 於 `apps/api/app/domains/member/schemas.py` 新增 `ComparisonMetric(key, kind, better_when, friend, me, better)`、`HeadToHeadTally`、`HeadToHead`、`MatchComparisonResponse`（contracts/match-comparison-api.md）
- [X] T046 [US4] 於 `apps/api/app/domains/member/service.py` 新增 `view_member_match_comparison(session, viewer_id, member_id)`：`_resolve_viewable_member()` → 雙方各自未篩選的 `_filtered_member_matches()`＋`load_match_stat_inputs()`＋`overall_values()` → 逐項算 `better`（常數 `COMPARISON_MIN_MATCHES = 3`；任一方 `value is None` 或 `matches_used < 3`、或 `better_when is None` → `None`；相等 → `"tie"`）→ 以檢視者的 `_matchup_inputs()` 與 `player_key(friend_id, …)` 呼叫 `head_to_head()`。新增 `apps/api/tests/unit/domains/member/test_member_match_comparison.py`（先寫）：`friend`／`me` 各自等於雙方 `build_member_match_dashboard()` 未篩選的 `all`；`better` 的四種值；`lower` 方向的指標判定正確；`head_to_head` 的角度；**函式不寫入任何資料**（以 session 的 flush／commit 計數或前後資料列數斷言）（FR-001、FR-035、FR-039）（depends on T030、T044、T045）
- [X] T047 [US4] 於 `apps/api/app/domains/member/router.py` 新增 `GET /members/{member_id}/match-comparison`（`require_verified_member`；宣告在所有 `/members/me/…` 路由之後）。新增 `apps/api/tests/contract/test_member_match_comparison_endpoint.py`：成功形狀；`SELF_VIEW_NOT_SUPPORTED`／`MEMBER_NOT_FOUND`／`FRIENDSHIP_REQUIRED`／`MATCH_RECORDS_PRIVATE` 四種拒絕且回應不含任何數值；對方關閉分享後**再次**請求即被拒（請求當下判定）；檢視者自己關閉分享不影響結果；未驗證信箱被拒；`/members/me/match-comparison` 不會被誤判為 `member_id="me"` 的成功回應（FR-004、FR-036）（depends on T046）
- [X] T048 [P] [US4] 新增 `apps/web/src/app/core/api/match-comparison.models.ts`；於 `apps/web/src/app/features/auth/auth.service.ts` 新增 `getFriendMatchComparison(memberId)`
- [X] T049 [US4] 新增 `apps/web/src/app/features/friends/friend-match-records/friend-comparison/friend-comparison.component.{ts,html,scss,spec.ts}`（`app-friend-comparison`；inputs：`comparison`、`friendNickname`、`loading`、`failed`）：依儀表板群組順序，每項指標並排「好友｜我」兩個值，各附依據場數；`better` 以**圖示＋文字**標示（FR-006），`null` 不標示、缺資料的一方顯示「—」；下方「我們的交手紀錄」兩組，`null` 顯示 `neverPlayed` 的明確文字。語系 key `friendComparison.*` 加入兩份語系檔。spec：四種 `better`、缺資料、兩組交手紀錄與 `null`（FR-035）（depends on T048）
- [X] T050 [US4] 於 `apps/web/src/app/features/friends/friend-match-records/friend-match-records.component.{ts,html}`：新增「與我比較」切換鈕（`aria-pressed`）；**開啟時才**請求 `getFriendMatchComparison()`，每次造訪至多一次；被拒時沿用該頁既有的原因提示並清掉已顯示的比較內容；頁面上**不出現**任何團內比較（FR-037）。於 `friend-match-records.component.spec.ts` 新增對應測試（FR-035）（depends on T028、T049）

**Checkpoint**：四個 Story 全部完成。

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T051 [P] 擴充 `apps/api/scripts/seed_dashboard_demo.py`（仍只允許 `rally_stats_test`）：新增效能用的團（40 位球員、1,000 場逐分紀錄完整的比賽，`heavy` 為其中一員）；基本示範資料已由 T057 提前完成
- [X] T052 [P] 語系檔一致性：`apps/web/src/assets/i18n/zh-TW.json` 與 `en.json` 的 `playerInsights.*`、`member.matchHistory.matchups.*`、`groupBenchmark.*`、`friendComparison.*` 鍵集合完全相同；本功能觸及的模板無寫死的中英文字串；`member.matchHistory.opponentRanking.*` 舊鍵經全文搜尋確認**仍被 014 的團歷史頁引用，保留不刪**（FR-005、SC-009）
- [X] T053 後端品質關卡：`ruff check app/ tests/`、`mypy app/`、`python -m pytest tests/` 全數通過 in `apps/api/`（完整測試約 20–25 分鐘；MUST 在同一個回合內等它跑完——worktree 會在回合結束後被清掉；出現大量無法解釋的失敗時先重跑一次再調查）
- [X] T054 前端品質關卡：`npm run lint`、`npx tsc --noEmit -p tsconfig.app.json`、`npm test -- --watch=false` 全數通過 in `apps/web/`（`admin-page.component.spec.ts` 既有的 1 則 `NG04002` unhandled error 與本功能無關）
- [X] T055 實際畫面與效能驗證（quickstart.md 情境 1–11；SC-001、SC-005、SC-008～SC-010）：以 worktree 後端（:8001，`rally_stats_test`）＋`ng serve`（:4300）＋無頭 Chrome，1100px 與 390px 兩種寬度各走一次——摘要的數字與指標卡相等、點擊跳轉與焦點、點搭檔後整頁縮小（≤ 2 次點擊）、團內比較的匿名（檢視回應全文）、來源切換、好友頁；兩種寬度皆無水平溢出、無 `pageerror`；**先**在 `origin/ut` 的程式碼上以同一份 `heavy` 資料量測對戰紀錄與儀表板兩支請求作為基準，再量測本分支的同兩支請求與 1,000 場團的 `group-benchmark`（各 5 次取中位數；增幅門檻見 SC-008），以及 `group-benchmark` 執行期間另一個請求的回應時間。結果回填於 `specs/036-match-insights-benchmarks/quickstart.md` 情境 11；**不得**在 pytest 使用測試資料庫期間進行；結束後 TRUNCATE 測試資料庫（SC-004、SC-006）
- [X] T056 撰寫 PR 說明於 `specs/036-match-insights-benchmarks/pr-description.md`（本機沒有 `gh`）：功能摘要；**無 migration、部署順序無限制**；刻意的行為變更（對手戰績由暱稱改為依身分彙總，列數可能改變）；順帶修正的既有缺陷（`verify_ever_group_member()`，影響 014 的兩支端點）；授權邊界（三支新端點皆 `require_verified_member`；團內比較沿用 014 的「曾為正式成員」、匿名由回應結構保證；比較端點沿用 023 的四段檢查；不新增隱私設定）；驗證結果

---

## Dependencies & Execution Order

- **Foundational（T001–T004、T057）**：T001 → T002；T003、T004、T057 獨立。US1 只需要 T004；US2／US4 需要 T003；US3 需要 T002、T003。T057 不擋任何實作任務，但每個 Story 的 quickstart 驗證需要它。
- **US1（T005–T015）**：後端線 T005 → T006 → T008 → T009，T007 可與 T006 平行；前端線 T010 → T011 → T012，T013 獨立，T014／T015 需 T011＋T013。兩條線可平行（前端以 fixture 開發）。
- **US2（T016–T028）**：後端線 T016 → T017 → T019 → T020 → T021 → T022；T018 可與 T017 平行；T023 → T024（另需 US1 的 T008）。前端線 T025 → T026 →（T027 ‖ T028）；T027 另需 US1 的 T014。**若 US2 先於 US1 進行**：T023／T024 與 T027 中「摘要的 `playerPicked`」順延到 US1 完成後。
- **US3（T029–T042）**：T029 需 US2 的 T024 完成後再動 `service.py`（同檔序列化）；T030、T033、T034 互相獨立；T031 → T032；T035 → T036 → T037 → T038 → T039。前端線 T040 → T041 → T042（T042 另需 T027）。
- **US4（T043–T050）**：T043 → T044；T046 需 T030（`overall_values()`，屬 US3）——**若要在 US3 之前做 US4，先把 T030 單獨提前**，它沒有其他相依。前端 T048 → T049 → T050（另需 T028）。
- 同檔序列化：`member/service.py`（T008 → T019 → T021 → T024 → T029 → T036 → T038 → T046）、`member/insights.py`（T006 → T024 → T038）、`member/schemas.py`（T007 → T034 → T045）、`member/router.py`（T021 → T039 → T047）、`test_insights.py`（T005 → T023 → T037）、`match-history.component.*`（T014 → T027 → T042）、`friend-match-records.component.*`（T015 → T028 → T050）、兩份語系檔（T011 → T026 → T041 → T049）。
- **Polish（T051–T056）**：T051（效能用的團）可在 T039 之後任何時候做，需先有 T057；其餘於所有 Story 完成後進行。

## Parallel Example: User Story 1

```text
後端：T005 → T006 ─┬→ T008 → T009 [P]
        T007 [P] ──┘
前端：T010 [P] → T011 → T012
      T013 [P] ────────┬→ T014
                       └→ T015
```

## Parallel Example: User Story 3

```text
T029（重構）
T030 [P] ─┐
T031 → T032 ─┼→ T035 → T036 → T037 → T038 → T039
T033 [P] ─┤
T034 [P] ─┘
前端：T040 [P] → T041 → T042
```

## Implementation Strategy

1. **MVP**＝Foundational＋US1：只依賴 034／035 已經算好的指標，改動面最小，卻最直接回答「我的優缺點是什麼」。
2. **US2**：對**所有**歷史比賽立即生效（不需詳細計分），同時修正既有排行以暱稱彙總造成的錯併——包括所有已刪除帳號被併成一列的問題。與 US1 同為 P1、互不相依；有兩條人力時平行進行，只有一條時先做哪個都可以。
3. **US3**：工作量最大、也是唯一有效能風險的一段。先做 T029 的重構並以既有測試鎖住行為，再往上疊；T055 的實測若超過 5 秒，回報並另案評估快取，不在本功能內擴充範圍。
4. **US4**：最小的一段，幾乎全是重用。
5. 每完成一個 Story 即執行該 Story 對應的 quickstart 情境，再進下一個。
