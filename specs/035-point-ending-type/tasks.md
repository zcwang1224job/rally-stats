# Tasks: 得分方式紀錄（主動得分 vs. 對手失誤）

**Input**: Design documents from `/specs/035-point-ending-type/`

**Prerequisites**: plan.md、spec.md、research.md、data-model.md、contracts/（3 份）、quickstart.md（皆已存在）

**Tests**：依 `plan.md` Constitution Check（原則 II），寫入驗證（`attach_shot_placement()`）、`-1` 的一併收回、兩個純函式模組的新增部分 MUST 有單元測試，且測試任務 MUST **先於**對應的實作任務完成並確認為失敗（紅燈）；三組被擴充的回應 MUST 有契約測試。本檔案的測試任務為強制項，非選用。

**Organization**：依 spec.md 之 3 個 User Story（US1 P1、US2 P2、US3 P2）分階段。三者是一條資料鏈——US1 產生資料、US2 做單場推導、US3 把單場推導彙總到儀表板——所以依序進行，不假裝彼此獨立。但**每一個都能獨立上線**：US1 上線即開始累積資料，US2／US3 晚到也不會白記。

## Format: `[ID] [P?] [Story] Description`

- **[P]**：可平行執行（不同檔案、無相依關係）
- **[Story]**：對應 spec.md 的 US1–US3；Setup／Foundational／Polish 階段任務無此標籤
- 每項任務皆附精確檔案路徑

## Path Conventions

沿用 `plan.md` Project Structure：後端 `apps/api/`，前端 `apps/web/src/`。

---

## Phase 1: Setup

*本 feature 無 Setup 任務——不新增第三方依賴、不新增環境變數。唯一的基礎設施變更（一支 migration）屬於 Foundational。*

---

## Phase 2: Foundational（Blocking Prerequisites）

**Purpose**：新欄位本身，以及讓它能被讀進純函式的那一小段——三個 Story 都建立在這上面。

**⚠️ CRITICAL**：此階段完成前，不可開始任何 User Story 的工作。

- [ ] T001 新增 Alembic migration `apps/api/alembic/versions/<rev>_shot_placement_ending_type.py`：`down_revision = 'd0c14187b0e3'`；`upgrade()` 只有 `op.add_column('shot_placement_records', sa.Column('ending_type', sa.String(length=16), nullable=True))`，`downgrade()` 只有對應的 `op.drop_column`；手寫、不用 autogenerate 的雜訊（比照 031 的 migration 註解）；不回填既有列（research.md Decision 1／8）。以 `alembic upgrade head` → `alembic downgrade -1` → `alembic upgrade head` 於測試資料庫驗證可逆
- [ ] T002 於 `apps/api/app/domains/schedule/models.py` 的 `ShotPlacementRecord` 新增 `ending_type: Mapped[str | None] = mapped_column(String(16), nullable=True)`，附註解說明五個值、NULL＝未記錄、與其他欄位互相獨立、生命週期同所在列；並於 `apps/api/app/domains/schedule/schemas.py` 新增 `EndingType = Literal["winner", "out", "net", "serve_fault", "other_error"]`（depends on T001）
- [ ] T003 [P] 於 `apps/api/app/domains/group/match_stats.py` 新增 `EndingType`（同上五值的 `Literal`；純模組 MUST NOT import `schedule.schemas`）與 `ERROR_TYPES` 常數（後四者），並為 `Placement` 新增欄位 `ending: EndingType | None = None`（具預設值，既有建構呼叫不受影響）；於 `apps/api/app/domains/group/service.py` 的 `_to_placements()` 帶出 `ending=placement.ending_type`；以 `python -m pytest tests/unit/domains/group tests/unit/domains/member -q` 不改斷言全綠為準；並於 `apps/api/tests/unit/domains/group/test_match_stats.py` 新增一條測試：`typing.get_args(app.domains.schedule.schemas.EndingType) == typing.get_args(match_stats.EndingType)`，且 `match_stats.ERROR_TYPES` 恰為前者去掉 `"winner"` 的其餘四個值（順序相同）——純模組不能 import `schedule.schemas`，兩份定義只能靠這條測試保持一致（做法與 034 的 `_wins` 網格測試相同）（depends on T002）
- [ ] T004 [P] 於 `apps/api/tests/unit/domains/_match_history.py` 的 `Shot` 新增 `ending: str | None = None`，`make_played_match()` 寫入 `ShotPlacementRecord` 時帶上 `ending_type=shot.ending`；既有使用此 helper 的測試不改斷言全綠（depends on T002）

**Checkpoint**：欄位存在、可讀進純函式；尚無任何行為變化，既有測試全綠。

---

## Phase 3: User Story 1 - 計分時記下這一分怎麼結束（Priority: P1）🎯 MVP

**Goal**：計分員在既有的落點／球員選擇畫面上以「零或一次」額外點擊記下得分方式；選填、可改、`-1` 一併收回、簡易模式不變。

**Independent Test**：quickstart.md 情境 1–6——界外與發球失誤區自動帶入、界內落在失分方半場不帶入而一次點擊、親手選擇優先但矛盾時清除、只記得分方式、簡易模式不變、`-1` 收回、後端擋矛盾。

### 後端

- [ ] T005 [US1] Unit test（先紅燈）於 `apps/api/tests/unit/domains/schedule/test_shot_placement.py`（沿用該檔既有的 `_make_group`／`_make_court`／`_make_roster_entry`／`_score_and_get_event_id`）：(a) 五種值各自寫入後可自資料庫讀回；(b) `ending_type=None` 與省略的行為與上線前相同；(c) 只帶 `ending_type`、其餘四個欄位皆 `None` → 成功（FR-010）；(d) 值域外的字串 → `ApiError("INVALID_ENDING_TYPE")`；(e) `winner`＋界外落點 → `ENDING_TYPE_CONTRADICTS_LANDING`；(f) `out`＋界內落點 → 同；(g) 以 data-model.md「界內／界外的邊界測試向量」**整張表**做參數化測試：每個「界內」點配 `winner` 成功、配 `out` 被拒；每個「界外」點相反——表格逐字照抄，並註明前端 spec（T011）用的是同一張；(h) `net`／`serve_fault`／`other_error` 配任何落點皆成功；(i) 沒有落點時 `winner`／`out` 皆成功（不檢查）；(j) 簡易計分的比賽仍回 `DETAILED_SCORING_NOT_ENABLED`；(k) 既有錯誤的判定先於新檢查——落點與得分方矛盾時回的仍是 `SCORING_PLAYER_WRONG_TEAM_FOR_LANDING`（depends on T002）
- [ ] T006 [US1] 於 `apps/api/app/domains/schedule/service.py` 的 `attach_shot_placement()` 新增 keyword-only 參數 `ending_type: str | None = None`：值域檢查（`INVALID_ENDING_TYPE`，422）；在既有的落點檢查**之後**、且只在同時提供落點時，加入兩條矛盾檢查（`ENDING_TYPE_CONTRADICTS_LANDING`，422），重用該函式已算出的 `in_bounds`；寫入 `ShotPlacementRecord(ending_type=…)`；docstring 補一段說明為何只擋這兩種組合（research.md Decision 4）。使 T005 全綠（depends on T005）
- [ ] T007 [US1] 於 `apps/api/app/domains/schedule/schemas.py` 的 `RecordShotPlacementRequest` 新增 `ending_type: EndingType | None = None`（附註解），並讓三支端點透傳：`apps/api/app/domains/schedule/router.py` 的 `record_shot_placement_by_token`、`record_shot_placement_by_admin`，以及 `apps/api/app/domains/group/router.py` 的 all-courts token 版（約第 676 行）；三者的 docstring Errors 補上 `ENDING_TYPE_CONTRADICTS_LANDING`（depends on T006）
- [ ] T008 [P] [US1] Unit test 於 `apps/api/tests/unit/domains/schedule/test_apply_score_delta.py`：記錄一分（含 `ending_type`）後對該隊 `-1` → 該 `ShotPlacementRecord` 列不存在（FR-012）；對**另一隊** `-1` → 該列仍在。此測試預期在 T006 後直接通過（收回邏輯不需修改）——若失敗代表 Decision 1 的前提不成立，須回報而非修改收回邏輯（depends on T006）
- [ ] T009 [P] [US1] 契約測試於 `apps/api/tests/contract/test_shot_placement_endpoint.py`：依 contracts/shot-placement-api.md「保證」各條——不帶 `ending_type` 的既有請求行為不變；只帶 `score_event_id`＋`ending_type` 成功；值域外 → 422；`winner`＋界外 → 422 `ENDING_TYPE_CONTRADICTS_LANDING`；同一分第二次補記仍回 `SHOT_PLACEMENT_ALREADY_RECORDED`；三支端點（token／admin／all-courts token）各至少一條帶 `ending_type` 的成功案例（depends on T007）

### 前端

- [ ] T010 [P] [US1] 於 `apps/web/src/app/core/api/court-live-state.models.ts` 新增 `export type EndingType = 'winner' | 'out' | 'net' | 'serve_fault' | 'other_error'` 與 `ENDING_TYPES` 常數陣列（固定顯示順序）；於 `apps/web/src/app/core/api/court-control.service.ts` 的 `recordShotPlacement()` 與 `recordShotPlacementAllCourts()` 各新增最後一個參數 `endingType: EndingType | null` 並送出 `ending_type`；`ENDING_TYPES` 的五個值與順序 MUST 與後端相同——T009 的契約測試逐一送出這五個值，是前後端之間的檢查
- [ ] T011 [US1] 前端測試（先紅燈）於 `apps/web/src/app/features/shot-placement/shot-placement-picker.component.spec.ts`：(a) 界外落點 → 生效值為 `out` 且「主動得分」停用；(b) 落在得分方半場的發球失誤區且 `servingTeam` 為對方 → `serve_fault`；(c) 界內落在失分方半場 → 沒有任何選項被選中、「對手出界」停用（SC-006）；(c2) 以 data-model.md 的同一張邊界測試向量表做參數化測試：「界外」點的 `landingSide()` 為 `'out'` 且 `winner` 停用，「界內」點的 `out` 停用——表格逐字照抄，並註明後端測試（T005）用的是同一張；(d) 沒有落點 → 五個選項皆可選、皆未選；(e) 親手點選後再改點另一個不矛盾的落點 → 選擇保留（FR-009）；(f) 親手選 `winner` 後把落點改到界外 → 選擇被清除並回到自動帶入的 `out`；(g) 點同一個已選的選項 → 取消（`null`），且此後不再被自動帶入覆蓋；(h) `confirm()` 發出的 `ShotPlacementConfirmed.endingType` 為生效值，未選時為 `null`；(i) `open()` 重置親手選擇；(j) 自動帶入時畫面有文字提示；(k) `useTabs()` 為真時選項位於「落點」分頁內，分頁數仍為 2（depends on T010）
- [ ] T012 [US1] 於 `apps/web/src/app/features/shot-placement/shot-placement-picker.component.{ts,html,scss}` 實作：`ShotPlacementConfirmed` 新增 `endingType`；signal `manualEndingType`（`undefined`＝未碰過）；`autoEndingType`＝`landingSide() === 'out' ? 'out' : isServeFault() ? 'serve_fault' : null`；`endingType`＝親手值優先；`disabledEndingTypes`（界外 → `winner`；界內 → `out`）；一個 `effect` 在親手值落入停用集合時把它清回 `undefined`；`open()` 重置；模板在 `.landing-section` 的球場圖正下方加一排原生按鈕 chip（`aria-pressed`、停用者 `aria-disabled`＋說明），單行、窄螢幕可橫向捲動，MUST NOT 把確認按鈕推出可視範圍（FR-013、SC-011）；文字以 `shotPlacement.ending.*` 加入 `apps/web/src/assets/i18n/zh-TW.json` 與 `apps/web/src/assets/i18n/en.json`。使 T011 全綠（depends on T011）
- [ ] T013 [US1] 三個掛載點的 `onShotPlacementConfirmed()` 把 `endingType` 透傳給 service：`apps/web/src/app/features/scoreboard/scoreboard.component.ts`、`apps/web/src/app/features/control-panel/control-panel.component.ts`、`apps/web/src/app/features/control-panel/all-courts/all-courts-court-block.component.ts`；各自的 spec（`scoreboard.component.spec.ts`、`control-panel.component.spec.ts`）補一條斷言 service 收到的最後一個參數，並修正既有呼叫斷言的參數數量（depends on T012, T007）

**Checkpoint**：US1 可獨立上線——資料開始累積；詳情與儀表板尚無新內容。

---

## Phase 4: User Story 2 - 單場比賽詳情看得出分數怎麼來的（Priority: P2）

**Goal**：逐點清單顯示每一分的得分方式；每位球員的得分拆成「主動得分／對手失誤得分／未記錄」、失分拆成「被主動得分／自己失誤／未記錄」；隊伍摘要含失誤組成。

**Independent Test**：quickstart.md 情境 7。

- [ ] T014 [US2] Unit test（先紅燈）於 `apps/api/tests/unit/domains/group/test_match_stats.py`（沿用 `_Sim`／`_play`）：`ending_stats()`——(a) `winner` 記在 `scorer_id`、失誤記在 `loser_id`（FR-003）；(b) 有得分方式、沒有對應球員 → 只進隊伍層級；(c) 每位球員 `winners + opponent_errors + scored_unrecorded == player_landings()[id].scored_total`，失分端同理（FR-015）；(d) `teams[X].errors` 是 X 隊**犯下**的失誤＝對手以失誤類得到的分；`sum(errors_by_type.values()) == errors`；(e) `recorded_points` 只計有得分方式的有效得分，`total_points == len(points)`；(f) 被 `-1` 撤銷的那一分不計入任何數字；(g) 全場沒有任何得分方式 → `None`；(h) `players` 依 `participants` 順序、含全 0 者（depends on T003）
- [ ] T015 [US2] 於 `apps/api/app/domains/group/match_stats.py` 新增 `frozen=True` dataclass `TeamEndingResult`／`PlayerEndingResult`／`EndingStatsResult`（欄位依 data-model.md）與 `ending_stats(points, placements, participants)`，使 T014 全綠（depends on T014）
- [ ] T016 [P] [US2] 於 `apps/api/app/domains/group/schemas.py`：`ShotPlacementSummary` 新增 `ending_type`；新增 `ErrorsByType`／`TeamEndingStat`／`PlayerEndingStat`／`EndingStats`；`MatchRecordDetailResponse` 新增 `ending_stats: EndingStats | None = None`（附註解：與 033／034 欄位同一條件；032 的 `player_stats` 不變）
- [ ] T017 [US2] 於 `apps/api/app/domains/group/service.py`：`_detail_for()` 帶出 `ending_type`，並把「整列皆空」的判斷由四個欄位改為五個（research.md Decision 4）；`_build_derived_stats()` 呼叫 `match_stats.ending_stats()` 並組成 `EndingStats`（`teams` 恆為 `[A, B]`、`players` 順序 `team_a + team_b`、暱稱取自 summary）；`_DerivedStats` 與回傳組裝同步擴充。於 `apps/api/tests/unit/domains/group/test_match_record_detail.py` 新增經資料庫的測試：只記了得分方式的一分 `detail` 不為 `None`；`ending_stats` 各數字正確；沒有任何得分方式 → `None`；`partial` 紀錄 → `ending_stats is None` 但 `events[].detail.ending_type` 仍回傳（depends on T015, T016, T004）
- [ ] T018 [P] [US2] 契約測試：於 `apps/api/tests/contract/test_group_match_record_detail.py` 與 `apps/api/tests/contract/test_member_match_record_detail.py` 依 contracts/match-record-detail-api.md「保證」各條——透過真實的補記端點記錄數分後查詢；斷言球員三項相加等於同一回應 `player_stats` 的得分／失分數、`recorded_points` 等式、`errors` 加總、既有欄位不變、舊式比賽 `ending_stats == null`（depends on T017, T007）
- [ ] T019 [P] [US2] 前端型別：於 `apps/web/src/app/core/api/group-member-view.models.ts` 新增 `ShotPlacementSummary.ending_type`、`ErrorsByType`／`TeamEndingStat`／`PlayerEndingStat`／`EndingStats`、`MatchRecordDetailResponse.ending_stats`；為既有 fixture 補 `ending_stats: null` 於 `match-record-detail-dialog.component.spec.ts`、`match-derived-stats.component.spec.ts`、`apps/web/src/app/features/friends/friend-match-records/friend-match-records.component.spec.ts`（depends on T010）
- [ ] T020 [US2] 新增 `apps/web/src/app/core/match-record-detail/match-ending-stats/match-ending-stats.component.{ts,html,scss,spec.ts}`（input：`endingStats: EndingStats | null`；`@use '../derived-blocks'`）：隊伍摘要（主動得分數、失誤數、四種失誤各幾次）、球員拆分表（得分三欄、失分三欄）、涵蓋範圍「已記錄 N／共 M 分」；`null` → 單一無資料提示、不渲染任何表格（FR-017）；主動得分與失誤以**圖示＋文字**區分（FR-014）；文字以 `matchRecordDetail.ending.*` 加入兩份語系檔。spec 涵蓋：完整呈現、全 0 的球員仍列出、`null` 提示、涵蓋範圍文字（depends on T019）
- [ ] T021 [US2] 於 `apps/web/src/app/core/match-record-detail/match-derived-stats/match-derived-stats.component.{ts,html}` 在關鍵分區塊之後掛上第六個預設收合的 `<details data-section="ending">`（`d.ending_stats ?? null`），並更新 `match-derived-stats.component.spec.ts` 的區塊順序斷言為 `['serve','momentum','clutch','ending','tempo','landing']`（depends on T020）
- [ ] T022 [US2] 於 `apps/web/src/app/core/match-record-detail/match-record-detail-dialog.component.{ts,html,scss}` 的逐點清單：有 `detail.ending_type` 的加分顯示一個標籤（圖示＋文字；`winner` 一種樣式、四種失誤共用另一種）；`ending_type` 為 `null` 的列外觀與上線前完全相同；只記了得分方式的列可正常顯示但不顯示「展開落點」的可點擊樣式。於 `match-record-detail-dialog.component.spec.ts` 新增對應測試（depends on T019）

**Checkpoint**：球員能在單場詳情看到「自己打下來的」與「對手送的」之分。

---

## Phase 5: User Story 3 - 儀表板上看到我的主動得分與失誤（Priority: P2）

**Goal**：034 的儀表板新增 5 項指標與失誤組成，完整沿用對比／進步判定／趨勢／依據場數。

**Independent Test**：quickstart.md 情境 8、9。

- [ ] T023 [US3] Unit test（先紅燈）於 `apps/api/tests/unit/domains/member/test_player_dashboard.py`：(a) `build_sample()` 在我該場至少一分有得分方式時產生 `EndingSample`，否則為 `None`（FR-020）——「只有隊友有紀錄、我沒有」為 `None`；(b) 指標總數 23，前 18 項 key 與順序不變，新 5 項的 `kind`／`better_when` 依 data-model.md；(c) `winner_share` 分母＝`winners + opponent_errors`，不含未記錄的分數（US3 情境 3）；(d) `winners_per_match`／`errors_per_match` 的分母為納入場數；(e) `error_share_of_lost`；(f) `winner_error_ratio` 失誤為 0 → `value None`、`matches_used > 0`；(g) 沒有任何場具備紀錄 → 5 項皆 `all None`，既有 18 項不受影響；(h) 20 場中最近 10 場 `errors_per_match` 下降 → `improved`（越低越好），`winner_share` 上升 → `improved`；(i) 新指標可出現在 `trends`；(j) `error_breakdown`：`all` 四項加總等於各場 `own_errors` 總和、`recent` 只計最近 10 場、≤ 10 場時 `recent None`、沒有任何失誤 → 整個為 `None`（depends on T015）
- [ ] T024 [US3] 於 `apps/api/app/domains/member/player_dashboard.py`：新增 `EndingSample`、`ErrorBreakdown`；`MatchSample.ending`；`build_sample()` 新增參數 `ending: EndingStatsResult | None` 並取出我那一筆；`_METRICS` 末尾新增 5 筆（以新的 `_from_ending()` 取值 helper，比照既有 `_from_serve()`）；`DashboardResult` 新增 `error_breakdown_all`／`error_breakdown_recent` 與其計算；`aggregate()` 的指標迴圈 MUST NOT 新增任何針對特定 key 的分支（research.md Decision 6）。使 T023 全綠（depends on T023）
- [ ] T025 [P] [US3] 於 `apps/api/app/domains/member/schemas.py` 新增 `DashboardErrorBreakdown`（重用 `group.schemas.ErrorsByType`）與 `MemberMatchDashboardResponse.error_breakdown`；`DashboardMetric` 註解由 18 改為 23（depends on T016）
- [ ] T026 [US3] 於 `apps/api/app/domains/member/service.py` 的 `_dashboard_sample()` 多算一次 `match_stats.ending_stats(points, inputs.placements, participants)` 傳入 `build_sample()`；`build_member_match_dashboard()` 把兩個 breakdown 對映成 `error_breakdown`（`asdict` 後的鍵名需調整，MUST 有測試）。於 `apps/api/tests/unit/domains/member/test_member_match_dashboard.py` 新增：單一比賽時 5 項指標的分子分母＝該場 `build_match_record_detail().ending_stats.players` 中我那一筆（FR-024）；混合「有得分方式／全部略過／簡易計分」的 `matches_used`；查詢次數與 034 相同、不隨場數成長（depends on T024, T025, T017）
- [ ] T027 [P] [US3] 契約測試於 `apps/api/tests/contract/test_member_match_dashboard_endpoint.py`：`METRIC_KEYS` 擴為 23 項且前 18 項不變；有比賽但無得分方式時新 5 項皆 `all: null`、`error_breakdown: null`；`EMPTY` 形狀新增 `error_breakdown: null`；好友端點的成功回應含新欄位、四種拒絕回應不含（depends on T026）
- [ ] T028 [P] [US3] 前端型別與 fixture：`apps/web/src/app/core/api/player-dashboard.models.ts` 的 `DASHBOARD_METRIC_KEYS` 加 5 個 key、新增 `DashboardErrorBreakdown` 與回應欄位；`apps/web/src/app/core/player-dashboard/dashboard-fixtures.ts` 補上新 key 的 `kind`／方向與 `error_breakdown: null` 預設（depends on T019）
- [ ] T029 [US3] 於 `apps/web/src/app/core/player-dashboard/player-dashboard.component.{ts,html,scss}`：`MetricGroup` 加 `'ending'`、`GROUP_OF` 補 5 筆（exhaustive `Record`）、`GROUPS` 順序把 `ending` 放在 `scoring` 之後；新群組內在卡片下方顯示失誤組成——四列「名稱／次數／佔比＋細長條」，單一顏色（名目類別不用漸層），把 034 既有的 `landingRange` signal 與其兩顆按鈕自落點群組內**提升為儀表板層級**（改名 `range`；放在群組清單上方、intro 文字之下；`has_comparison` 為假時不顯示），落點分布與失誤組成**共用**這一個切換，落點群組內原本的範圍按鈕移除（FR-021、research.md Decision 7）；`error_breakdown === null` 時顯示無資料提示；文字加入兩份語系檔（`playerDashboard.group.ending`、5 個 `playerDashboard.metric.<key>.{label,hint,empty}`、`playerDashboard.errorBreakdown.*`）（depends on T028）
- [ ] T030 [US3] 前端測試於 `apps/web/src/app/core/player-dashboard/player-dashboard.component.spec.ts`：23 張卡片、5 張新卡片落在 `ending` 群組且順序固定、既有三組不變、失誤組成四列與佔比、`null` 提示；034 既有的落點範圍切換測試改為操作儀表板層級的切換鈕，並新增一條「切換一次，落點標記數與失誤組成的數字**同時**改變」；整個儀表板只有一組範圍切換鈕、`details` 的預設展開狀態仍只有第一組；並確認 `match-history.component.spec.ts` 與 `friend-match-records.component.spec.ts` 中「18 張卡片」的斷言更新為 23（depends on T029）

**Checkpoint**：球員能回答「我的分數幾成是自己打下來的、我一場送幾分、最近有沒有變好」。

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T031 [P] 於 `apps/api/scripts/seed_dashboard_demo.py` 為示範資料帶入得分方式：界外落點 → `out`、界內落在失分方半場 → 依機率 `winner`／`net`、約兩成的分數刻意不記；仍只允許 `rally_stats_test`
- [ ] T032 [P] 語系檔一致性：`zh-TW.json` 與 `en.json` 的 `shotPlacement.ending.*`、`matchRecordDetail.ending.*`、`playerDashboard.errorBreakdown.*` 與 5 個新指標的鍵集合完全相同、模板無寫死的中英文字串 in `apps/web/src/assets/i18n/`
- [ ] T033 後端品質關卡：`ruff check app/ tests/`、`mypy app/`、`python -m pytest tests/` 全數通過 in `apps/api/`（完整測試約 15–25 分鐘；MUST 在同一個回合內等它跑完——worktree 會在回合結束後被清掉）
- [ ] T034 前端品質關卡：`npm run lint`、`npx tsc --noEmit -p tsconfig.app.json`、`npm test -- --watch=false` 全數通過 in `apps/web/`（`admin-page.component.spec.ts` 既有的 1 則 `NG04002` unhandled error 與本功能無關）
- [ ] T035 實際畫面與效能驗證（quickstart.md 情境 9、10；SC-002、SC-010、SC-011）：以 worktree 後端（:8001，`rally_stats_test`）＋`ng serve`（:4300）＋無頭 Chrome 走一次計分流程——390px 寬下選定得分方式前後確認按鈕皆在可視範圍內、無水平溢出；連記 10 分所需的**點擊次數**對照上線前（驗證 SC-001／SC-003：不記得分方式時次數相同；界外與發球失誤區的分數額外點擊為 0；其餘最多 1）；300 場會員的儀表板 < 3 秒且查詢次數不變。結果記錄於 `specs/035-point-ending-type/quickstart.md`；結束後 TRUNCATE 測試資料庫
- [ ] T036 撰寫 PR 說明於 `specs/035-point-ending-type/pr-description.md`（本機沒有 `gh`）：功能摘要、migration 與部署順序——**必須先跑 `alembic upgrade head` 再部署後端**，並明列順序反了的影響範圍（所有比賽詳情、整個儀表板、詳細計分的 `-1` 會一起壞，因為容器不會自動跑 migration）與回滾順序（先退後端，再 `alembic downgrade -1`）、授權邊界（不新增端點；得分方式與落點同屬補記細節、非管理員專屬操作；儀表板沿用 `require_verified_member`）、驗證結果
- [ ] T037 人工驗收（**由使用者執行**，無法自動化——無頭瀏覽器量不到人的操作時間）：依 quickstart.md 情境 10，以碼表在上線前後的版本各連記 10 分（每分都點落點＋兩位球員），確認總時間增幅 ≤ 10%（SC-002）；結果記錄於 `specs/035-point-ending-type/quickstart.md` 情境 10 之下

---

## Dependencies & Execution Order

- **Foundational（T001–T004）**：T001 → T002；T003、T004 互不相依、皆依賴 T002。
- **US1（T005–T013）** 只依賴 T002。後端線 T005 → T006 → T007 →（T008 ‖ T009）；前端線 T010 → T011 → T012 → T013（T013 另需 T007）。兩條線可平行。
- **US2（T014–T022）** 依賴 T003／T004；要用真實端點產生測試資料的 T018 另需 US1 的 T007。
- **US3（T023–T030）** 依賴 US2 的 `ending_stats()`（T015）與其 schema（T016／T017）。
- 同檔序列化：`match_stats.py`（T003 → T015）、`group/service.py`（T003 → T017）、`group/schemas.py`（T016 → T025 的重用）、`player_dashboard.py`（T024）、兩份語系檔（T012 → T020 → T029）。
- **Polish（T031–T037）** 於所有 Story 完成後進行；T031 可在 T007 之後任何時候做。T037 需要人實際操作，不擋其他任務，但 SC-002 在它完成之前不算驗證過。

## Parallel Example: User Story 1

```text
後端：T005 → T006 → T007 ─┬→ T008 [P]
                          └→ T009 [P]
前端：T010 [P] → T011 → T012 → T013（另需 T007）
```

## Implementation Strategy

1. **MVP**＝Foundational＋US1：上線當天就開始累積得分方式。這是三個 Story 裡唯一有「時間價值」的——晚一週上線就少一週的資料，而 US2／US3 晚到不會損失任何東西。
2. **US2**：資料第一次回到球員眼前，也是最容易人工核對的一層；它的 `ending_stats()` 是 US3 的單場貢獻來源。
3. **US3**：把單場推導接進 034 已有的指標機制——工作量最小，價值最高。
4. 每完成一個 Story 即執行該 Story 對應的 quickstart 情境，再進下一個。
