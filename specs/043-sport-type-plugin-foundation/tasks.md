---

description: "Task list for 043-sport-type-plugin-foundation"
---

# Tasks: 多活動支援與比賽類型外掛基礎（Sport Type Plugin Foundation）

**Input**: Design documents from `/specs/043-sport-type-plugin-foundation/`

**Prerequisites**: plan.md、spec.md、research.md、data-model.md、contracts/（`sports-api.md`、`match-events-api.md`、`sections-manifest.md`、`plugin-boundary.md`）、quickstart.md、憲章 1.1.0（原則 III 完賽定義、原則 XII 外掛邊界）

**Tests**: **必做**。憲章原則 II 與 plan.md 的 Constitution Check 要求核心規則（達標判定、脊椎過濾、平手彙總、事件狀態機、區塊退路）的測試先於實作；每個 story 的測試任務 MUST 先寫、先確認失敗，再做該 story 的實作。唯一例外是 Phase 3（US1）的「搬移」任務：行為不變的重構，保證來自既有 278＋97 個測試在「允許變更清單」之外不改動而維持全綠。

**允許變更清單（既有測試檔）**：匯入路徑、TestBed providers／mock 物件補新方法、`web/test-setup.ts`。`expect`／`assert` 斷言 MUST NOT 改動（spec US1 情境 3、FR-031）。

**Organization**: 依 spec.md 的 user story 分 phase。Phase 1–2 建立外掛基礎但不碰羽球行為；Phase 3（US1）把羽球搬進 `net_rally` 外掛並以既有測試全綠驗收；之後每個 story 都是「加法」。story 順序依 spec 優先序：US1、US2、US3（P1）→ US5、US4、US6、US7（P2）。US5（通用類型）排在 US4（自訂活動）之前，因為訪客的「其他」活動就是通用類型。

## Format: `[ID] [P?] [Story] Description`

- **[P]**：可平行執行（不同檔案、不依賴尚未完成的任務）
- **[Story]**：對應 spec.md 的 user story（US1～US7）
- 路徑縮寫：`api/` = `apps/api/`；`web/` = `apps/web/src/app/`；`i18n/` = `apps/web/src/assets/i18n/`
- 任務描述結尾的（FR-…／SC-…／Decision N）標出它實作或驗證的需求與研究決策

## 環境備註（worktree）

- 後端：`export PATH=/Users/zcwang/projects/rally-stats/apps/api/.venv/bin:$PATH`，在 `api/` 執行 `ruff check app tests && mypy app && lint-imports && python -m pytest -q`。T001 新增 dev 依賴 `import-linter`：worktree 共用主 checkout 的 venv，所以要在**主 checkout 的 `apps/api`** 執行一次 `uv sync`（或 `pip install import-linter`）。
- 前端：`ln -s /Users/zcwang/projects/rally-stats/apps/web/node_modules apps/web/node_modules`，在 `apps/web` 執行 `npx ng test --watch=false`、`npx ng lint`、`npx ng build`。不新增前端套件。
- 全套後端測試約 20 分鐘，在背景執行並把 `-rf` 輸出存檔；一次大量失敗可能是既知的間歇問題（重跑失敗檔再判斷）。
- 測試 DB 每次 session 會 `alembic downgrade base` → `upgrade head`，T010 的 migration downgrade 必須可用。
- `docs/` 為本機 gitignore 文件：Phase 10 的 docs 任務直接改主 checkout，不進分支。

## 實作偏差紀錄（/speckit-implement，2026-09-24）

實作時發現下列任務若照原文執行，會與「既有測試斷言零修改」或邊界規則衝突，改採等價做法。勾選代表以下列做法完成。

| 任務 | 原計畫 | 實際做法 | 原因 |
|---|---|---|---|
| T003、T041（test-setup 預載） | vitest `setupFiles` 同步預載 `net-rally` 模組 | 撤掉 setup 檔；specs 需要時各自在自己的 bundle 內 `preloadSportTypeModule()` | Angular 單元測試建置把 setup 與每個 spec 打成不同 bundle，setup 預載的元件是另一份副本（資源未解析、DI token 不同，spec 的 mock 套不上）。且實測沒有既有 spec 依賴羽球 surface 同步渲染 |
| T032（match_stats 拆分） | 發球／落點／結束型態的純函式搬進 `net_rally/stats.py` | 純函式庫留在核心 `group/match_stats.py`；**讀寫外掛表的程式**（查詢、轉換、詳細頁組裝）全部搬進 `net_rally/{serve,placement,detail}.py` | `player_dashboard` 的樣本型別依賴這些結果型別；若搬走，核心儀表板管線必須匯入外掛（違反邊界），或整條管線搬進外掛並改動 100+ 個釘住匯入路徑的測試。邊界規則真正要守的「核心不查外掛表、不依名稱分支」由 T028 的 grep 測試驗證 |
| T033（23 項指標目錄） | 搬到 `net_rally/dashboard.py` | 目錄留在 `member/player_dashboard.py`；US2 的 T055／T056 讓外掛依模組回傳過濾後的目錄 | 同上；既有測試以模組路徑釘住 23 項與順序 |
| T039（整面搬移羽球元件） | `git mv` 進 `sports/types/net-rally/` | 元件留在原位；`net-rally.module.ts` 的 surfaces 指向它們（外掛→核心為合法方向） | 實體搬移會讓仍由核心頁面引用的檔案（分享圖卡的 `score-trend`、四個詳細頁宿主、全部場地殼層）違反邊界，且需改 54＋38＋29 個 spec 的路徑。宿主與 registry 的機制不受影響，新類型仍只需加模組 |
| T042／T043（四個宿主元件） | 每個 surface 一個宿主 | 一個通用 `app-sport-surface`（依 `typeKey`＋`surface` 名稱渲染、轉送輸入與輸出）＋路由用的 `CourtSurfaceHostComponent` | 四個宿主邏輯相同 |

## 術語對照

| 本文用語 | 程式名稱 | 說明 |
|---|---|---|
| 脊椎 | `score_events`／`ScoreEvent`（加 `kind`） | 比賽事件序列；場級比分只由 `kind='point'` 改變（Decision 1、2） |
| 外掛／類型模組 | 後端 `api/app/sports/types/<key>/`；前端 `web/sports/types/<key>/` | `net_rally`、`frames`、`generic` |
| 核心外掛基礎 | `api/app/sports/{registry,plugin,presentation,scoring,catalog}.py`；`web/sports/{registry.ts,section-outlet,generic-sections,hosts}` | 核心的一部分，不得匯入外掛 |
| 宿主 | `web/sports/hosts/*-host.component.ts` | 依 `type_key` 解析類型模組並渲染整面元件 |
| 整面元件（surface） | `SportTypeModule.surfaces.*` | 計分板、控制板、全部場地區塊、管理頁場地控制、開團表單欄位 |
| 區塊（section） | `{kind, title_key, data}` | 詳細頁／儀表板由伺服器回傳的清單，`SectionOutlet` 渲染 |
| 通用參數 | `team_size`、`end_mode`、`target_score`、`win_by`、`cap_score`、`allow_draw`、`score_steps` | 所有類型共用，快照到 `matches` |
| 放棄比賽 | 既有 `POST …/end`（`abandoned`） | 原「提前結束」，所有類型可用（FR-017a） |
| 結束並記錄結果 | 新 `POST …/finish` | 只在 `end_mode='manual'`（FR-017） |

---

## Phase 1: Setup（工具、邊界規則、目錄骨架）

**Purpose**: 建立邊界檢查與目錄骨架，所有規則先以「空目錄」通過，之後每個 phase 都在關卡保護下進行。

- [X] T001 在 `api/requirements-dev.txt` 加 `import-linter`，於 `api/pyproject.toml` 新增 `[tool.importlinter]` 與 contracts/plugin-boundary.md §1 的三條契約（forbidden 核心→外掛、independence 三個外掛、forbidden 外掛→realtime／核心 service）；在主 checkout 安裝後於 worktree 執行 `lint-imports` 確認通過（FR-034a、Decision 15）
- [X] T002 [P] 在 `apps/web/eslint.config.js` 新增 contracts/plugin-boundary.md §3 的 `no-restricted-imports` 覆寫（核心禁 `**/sports/types/**`；三個類型互禁），執行 `npx ng lint` 確認通過（FR-034a）
- [X] T003 [P] 在 `apps/web/angular.json` 的 `test` 目標加 `options.setupFiles: ["src/test-setup.ts"]`，建立 `apps/web/src/test-setup.ts`（暫時空檔，附註記其用途），執行 `npx ng test --watch=false` 確認既有 spec 仍全綠（Decision 14）
- [X] T004 [P] 建立後端骨架：`api/app/sports/__init__.py`、`api/app/sports/types/__init__.py`（`register_all()` 先為空函式）、`api/tests/unit/sports/__init__.py`；在 `api/app/main.py` 建立 app 時呼叫 `register_all()` 並以行內註記標示組裝根例外（憲章 XII）
- [X] T005 [P] 建立前端骨架：`web/sports/sport-type-module.ts`（`SportTypeModule`、`SectionComponent`、`SectionContext` 型別，依 contracts/plugin-boundary.md §4）、`web/sports/types/.gitkeep`、`web/sports/hosts/.gitkeep`
- [X] T006 [P] 在 `api/README.md` 的品質關卡指令加入 `lint-imports`（與 `ruff check`、`mypy` 並列），並註明前端 `npm run lint` 已含邊界規則（憲章技術治理新增的 blocking check）
- [X] T007 建立零變更基準：在分支起點執行完整後端與前端測試，把輸出存到 `$CLAUDE_JOB_DIR/tmp/043-baseline-{api,web}.txt`，記錄通過數（SC-001 的比對基準）

---

## Phase 2: Foundational（外掛基礎與資料遷移；不碰羽球行為）

**Purpose**: 核心外掛介面、參數化達標判定、migration、通用參數欄位、前端 registry／outlet／通用區塊。完成後羽球行為仍與今日完全相同（新欄位全為預設值）。

**⚠️ CRITICAL**: 本 phase 完成且既有測試全綠前，不得開始任何 story。

### 後端

- [X] T008 [P] 先寫 `api/tests/unit/sports/test_scoring.py`：複製 `api/tests/unit/domains/schedule/test_match_wins.py` 的表格以 `target=21, win_by=2, cap=30` 驗證等價，再加 `win_by=1`（局數制）、`cap=None`（桌球 15:13 結束、14:14 不結束）、`win_by` 大於差距時不結束的案例（Decision 3、FR-016）
- [X] T009 實作 `api/app/sports/scoring.py::match_wins(x, y, *, target, win_by, cap)`；把 `api/app/domains/schedule/service.py::match_wins` 與 `api/app/domains/group/match_stats.py::_wins` 改為呼叫它（簽名對既有呼叫端相容：`match_wins(my, opp, target, cap)` 轉呼叫 `win_by=2`），T008 與既有 `test_match_wins.py` 全綠
- [X] T010 撰寫 migration `api/alembic/versions/<rev>_sport_type_plugin_foundation.py`（down_revision `b7e2d4a9c130`）：`groups` 與 `matches` 的通用參數欄位＋`server_default`＋回填（`team_size` 由 `match_mode`；`matches.team_size` 由參賽人數）、`groups.custom_sport_id`、`score_events.kind`（預設 `point`）與 `side` 可空、`groups.cap_score`／`matches.cap_score` 可空、新表 `member_sports`（局數制的兩張表由 US3 的外掛 migration 建立，不在此）、`system_config` 的 `default_group_name_suffix.<sport_key>`／`default_court_name.<sport_key>` 種子；完整 downgrade；執行 `alembic upgrade head && alembic downgrade -1 && alembic upgrade head`（data-model §2–§7）
- [X] T011 [P] 先寫 `api/tests/unit/domains/group/test_group_sport_params.py`：`Group(match_mode="doubles")` ⇒ `team_size==2`、`Group(team_size=1)` ⇒ `match_mode=="singles"`、兩者衝突 ⇒ `ValueError`、`end_mode='target'` 的 `target ≥ win_by`／`cap ≥ target` 不變量、`sport_key='other'` 需 `sport_name`、`detailed_scoring_enabled` 只在 `modules.shot_placement` 時允許（Decision 6、7；data-model §2）
- [X] T012 在 `api/app/domains/group/models.py` 新增 data-model §2 的欄位（Python 端預設值＝羽球）與 `team_size`↔`match_mode` 同步 validator、不變量檢查；T011 全綠
- [X] T013 [P] 在 `api/app/domains/schedule/models.py` 新增 `Match` 的快照欄位（data-model §3，Python 預設羽球值）、`ScoreEvent.kind`（預設 `'point'`）、`side` 可空、`cap_score` 可空；既有 `Match(...)`／`ScoreEvent(...)` 建構式呼叫零變更
- [X] T014 [P] 建立核心 ORM `api/app/domains/member/sports_models.py::MemberSport`（data-model §5），並在 `api/alembic/env.py` 匯入（附註記：組裝根例外）
- [X] T015 [P] 撰寫 `api/app/sports/presentation.py`（`Section`、`SportSummary`、`MetricView` pydantic）與 `api/app/sports/plugin.py`（`SportTypePlugin` Protocol、`SpineEventContext`、`SpineEffect`、`PluginEventContext`、`PluginEventResult`、`UnknownSportType`；data-model §10）
- [X] T016 先寫 `api/tests/unit/sports/test_registry.py`（註冊、重複註冊拒絕、未知 key 拋 `UnknownSportType`），再實作 `api/app/sports/registry.py`
- [X] T017 [P] 先寫 `api/tests/unit/sports/test_catalog.py`（9 筆內建活動、`other` 排最後、每筆 `defaults` 符合通用不變量、`type_key` 皆已註冊或為本期三種），再實作 `api/app/sports/catalog.py`（data-model §6 的 `BuiltinSport` 與名詞集合）
- [X] T018 在 `api/app/domains/schedule/service.py::create_match_with_participants` 把 data-model §3 的通用參數與 `type_params` 一併快照到 `Match`（憲章 III）
- [X] T019 [P] 先寫 `api/tests/unit/test_system_config_sport_keys.py`（`badminton` 走既有 key 回傳既有值；`billiards` 回傳 `的撞球團`／`球桌一`；未種子的 key 退回既有 key），再改 `api/app/system_config/service.py::get_default_group_name_suffix(session, sport_key)`／`get_default_court_name(session, sport_key)`（既有無參數呼叫視為 `badminton`）
- [X] T020 在 `api/` 執行後端完整測試與 `lint-imports`，輸出存 `$CLAUDE_JOB_DIR/tmp/043-phase2-api.txt`，確認與 T007 基準相同通過數（Phase 2 後端檢查點）

### 前端

- [X] T021 [P] 在 `web/core/api/sport.models.ts` 定義 `SportSummary`、`Section`、`SportsCatalogResponse`、`BuiltinSport`、`CustomSport`、`ActivitySummary`、`SportType`（與 contracts/sports-api.md、sections-manifest.md 一對一）
- [X] T022 [P] 先寫 `web/sports/registry.spec.ts`（`peek` 未載入回 `undefined`、`resolve` 快取、載入失敗拋錯可重試、`register()` 同步註冊後 `peek` 命中），再實作 `web/sports/registry.ts`（`SPORT_TYPE_LOADERS` 空表＋`SportTypeRegistry`；載入表以行內 eslint 註記標示例外）（Decision 14、20）
- [X] T023 [P] 先寫 `web/sports/section-outlet/section-outlet.component.spec.ts`（已註冊 kind 渲染對應元件、通用 kind 走通用區塊、未知 kind 渲染退路且不拋錯、`data:null` 傳遞 context），再實作 `web/sports/section-outlet/section-outlet.component.ts` 與退路元件 `web/sports/generic-sections/fallback-section.component.ts`（FR-021、SC-008）
- [X] T024 [P] 實作通用區塊與其 spec：`web/sports/generic-sections/{metric-grid,stat-table,score-timeline,text-note}-section.component.ts`（資料形狀依 contracts/sections-manifest.md §2；`score_timeline` 只畫 `kind==='point'`）
- [X] T025 [P] 放寬既有前端型別：`web/core/api/court-live-state.models.ts`（`cap_score: number | null`、新增 `sport`、`end_mode`、`win_by`、`allow_draw`、`score_steps`、`sport_state`）、`web/core/api/group-member-view.models.ts`（`ScoreEventSummary.delta: number`、`kind`、`winner_team` 含 `'D'`、`MatchRecordDetailResponse.sport`／`sections`、`draws` 欄位）、`web/features/group-admin/schedule-management/schedule.models.ts`（`MatchSummary` 同步）；`npx ng build` 通過
- [X] T026 在 `apps/web/` 執行前端完整測試、lint、build，輸出存 `$CLAUDE_JOB_DIR/tmp/043-phase2-web.txt`，確認與 T007 基準相同（Phase 2 前端檢查點）

**Checkpoint**: 外掛基礎就緒；羽球行為零變更；可開始 US1。

---

## Phase 3: User Story 1 - 既有羽球團一切如舊（Priority: P1）🎯 MVP

**Goal**: 把羽球的發球、落點、統計、指標目錄與前端元件整個搬進 `net_rally` 外掛，核心改為透過外掛介面呼叫；既有測試在允許變更清單內全綠（FR-022、FR-030～FR-032、SC-001、SC-002）。

**Independent Test**: quickstart §1：後端 278 檔與前端 97 spec 全數通過，`git diff origin/ut -- apps/api/tests apps/web/src/app/**/*.spec.ts` 只含匯入路徑／providers／setup；升級前後種子資料的羽球畫面逐項比對零差異。

### 後端：先釘住行為

- [X] T027 [US1] 先寫 `api/tests/integration/test_scoring_payload_pin.py`：沿用 `test_scoring_flow.py` 的 `monkeypatch.setattr("app.domains.schedule.service.publish", …)` 模式，釘住羽球 +1／−1 的 `match.scoreUpdated` 完整 payload（含 `serve`）、`ScoreMutationResult` 欄位、達標後 `match.ended`／`standings.updated` 順序，作為 T033 重構的回歸保證（Decision 8、plan Risks）
- [X] T028 [P] [US1] 先寫 `api/tests/unit/sports/test_core_boundary_grep.py`：(a) `api/app/domains`、`api/app/core`、`api/app/sports/{registry,plugin,presentation,scoring}.py` 不得出現 `select(ScoreServeRecord`、`select(ShotPlacementRecord`、`select(FrameResult`、`select(FramePoint`；(b) 同範圍不得出現字面比較 `== "badminton"`、`== "net_rally"`、`== "frames"`、`== "generic"`、`in ("badminton"`（允許清單：`api/app/sports/catalog.py`、`api/app/system_config/service.py` 的預設 key 退回、`api/alembic/versions/**`，以檔案路徑列於測試內）（Decision 9、15；FR-034）

### 後端：搬移與骨架化

- [X] T029 [US1] 建立 `api/app/sports/types/net_rally/{__init__,params,schemas}.py`：`NetRallyParams`（`modules: {serve_tracking, shot_placement}`）；`schemas.py` 從核心 `api/app/domains/schedule/schemas.py` 匯入並重新匯出 `EndingType`（核心保留該型別因落點端點的請求 schema 在核心 router；外掛→核心方向允許）
- [X] T030 [US1] 把發球純函式與狀態函式搬到 `api/app/sports/types/net_rally/serve.py`（`_compute_station`、`_team_station`、`_initialize_serve_state`、`_advance_serve_state_and_snapshot`、`_build_serve_station`、`_serve_before_point`，名稱不變）；`api/app/domains/schedule/service.py` 不再定義也不 re-export；以 `grep -rl "_compute_station\|_initialize_serve_state\|_advance_serve_state_and_snapshot\|_serve_before_point\|_build_serve_station" api/tests` 列出的測試檔改匯入路徑（允許變更清單）
- [X] T031 [US1] 把落點幾何常數、`_is_serve_fault_zone`、`_remove_last_shot_placement_record` 與 `attach_shot_placement` 的驗證主體搬到 `api/app/sports/types/net_rally/placement.py`；核心 `attach_shot_placement` 保留為薄包裝（`_fetch_match_for_court` → `MODULE_NOT_SUPPORTED` 守門 → 委派外掛）；相關測試改匯入路徑
- [ ] T032 [US1] 把 `api/app/domains/group/match_stats.py` 的 `serve_stats`、`_receiver`、`player_landings`、`landing_distribution`、`ending_stats`、`ERROR_TYPES` 搬到 `api/app/sports/types/net_rally/stats.py`；核心保留 `effective_points`、`momentum_stats`、`tempo_stats`、`clutch_stats`（改用 `scoring.match_wins`）；`api/tests/unit/domains/group/test_match_stats.py` 改匯入路徑，`EndingType` 釘點改為 `net_rally.stats.EndingType is schedule.schemas.EndingType`（Decision 10）
- [ ] T033 [US1] 把 `api/app/domains/member/player_dashboard.py::_METRICS` 的 23 項搬到 `api/app/sports/types/net_rally/dashboard.py::METRIC_SPECS`；`aggregate(samples, metric_specs=…)`／`overall_values`／`metric_specs()` 改為參數化（預設值仍為 23 項以維持既有呼叫）；`api/app/domains/member/insights.py` 的 `_SPECS`／`_METRIC_ORDER` 改為 `derive(..., metric_specs)` 注入；相關測試改匯入路徑（Decision 11）
- [X] T034 [US1] 撰寫 `api/app/sports/types/net_rally/plugin.py::NetRallyPlugin`：`tables()`（`ScoreServeRecord`、`ShotPlacementRecord`）、`on_match_start`（`modules.serve_tracking` 時初始化發球）、`on_match_requeued`（undo-completion 時清發球欄位，自 `undo_match_completion` 搬來）、`on_spine_event`（+1 換發快照、−1 刪落點與依比分還原；回傳 `SpineEffect(live_payload=serve)`）、`live_state`（回 `None`）、`after_undo` → `UNDO_NOT_SUPPORTED`、`load_stat_inputs`（自 `group/service.py` 搬來的發球／落點查詢）、`match_detail`（既有頂層欄位＋`[{kind:"net_rally.match_detail", data:null}]`）、`dashboard_metric_specs`（23 項）、`dashboard_sections`（`[{kind:"net_rally.dashboard", data:null}]`）、`estimate_minutes`（`0.6 × target`）、`match_wins`（委派核心）；在 `types/__init__.py::register_all()` 註冊
- [X] T035 [US1] 把 `api/app/domains/schedule/service.py::apply_score_delta` 重構為固定骨架（原子 UPDATE → `last_activity_at` → 寫脊椎 `point` → `plugin.on_spine_event` → commit → `match_wins` → 終局 → publish），`serve` 鍵由 `SpineEffect.live_payload` 填入、`sport_state` 新增；`_start_match` 呼叫 `on_match_start`；`undo_match_completion` 呼叫 `on_match_requeued`；排點時間預估改呼叫 `estimate_minutes`；T027 全綠（Decision 8）
- [X] T036 [US1] 核心讀者改為只看 `kind=='point'`：在 `api/app/domains/group/service.py` 新增 `point_events(session, match_ids)` 查詢，`_record_completeness`、`_to_raw_events`、`load_match_stat_inputs`、`build_match_record_detail` 改用之；發球／落點查詢改為 `registry.get(match.type_key).load_stat_inputs()`；`_build_derived_stats` 改由外掛 `match_detail()` 產出；T028 全綠
- [X] T037 [US1] `court_live_state`、`build_schedule_snapshot`、all-courts 狀態組裝加入 `sport`（`SportSummary`）、通用參數與 `sport_state = plugin.live_state()`；`api/app/domains/schedule/schemas.py` 與 `api/app/domains/group/schemas.py` 對應 schema 新增欄位（contracts/match-events-api.md §7）；`MatchRecordDetailResponse` 新增 `sport`、`sections`
- [X] T038 [US1] 在 `api/` 執行後端完整測試、`ruff`、`mypy`、`lint-imports`：通過數與 T007 相同；`git diff origin/ut -- apps/api/tests` 只含匯入路徑（US1 後端檢查點）

### 前端：整面搬移與宿主

- [ ] T039 [US1] 建立 `web/sports/types/net-rally/` 並搬移（`git mv`，類別名與內部邏輯不變）：`web/features/scoreboard/` → `net-rally/scoreboard/`、`web/features/control-panel/control-panel.component.*` → `net-rally/control-panel/`、`web/features/control-panel/all-courts/all-courts-court-block.component.*` → `net-rally/all-courts-block/`、`web/features/group-admin/schedule-management/court-control.component.*` → `net-rally/court-control/`、`web/features/shot-placement/` → `net-rally/shot-placement/`、`web/core/court-diagram/` → `net-rally/court-diagram/`、`web/core/match-record-detail/` → `net-rally/match-record-detail/`、`web/core/player-dashboard/` → `net-rally/player-dashboard/`、`web/core/match-share-card/share-card-highlights.{ts,spec.ts}` → `net-rally/share-card-highlights.*`、`web/core/match-point.{ts,spec.ts}` → `net-rally/match-point.*`；修正搬移檔與其 spec 的相對匯入（允許變更清單）；搬移後的 `MatchRecordDetailDialogComponent` 選擇器改為 `app-net-rally-match-detail`（結構性調整；其 54 個 spec 以 `componentInstance` 與 `By.directive` 操作，不以自身選擇器查詢），`app-match-record-detail-dialog` 保留給 T044 的宿主
- [X] T040 [US1] 撰寫 `web/sports/types/net-rally/net-rally.module.ts`：匯出 `NET_RALLY: SportTypeModule`（surfaces 指向搬移後元件；`sectionKinds` 的 `net_rally.match_detail` → 新包裝元件 `net-rally/sections/match-detail-section.component.ts`（內嵌搬移後的 dialog 主體，讀頂層欄位）、`net_rally.dashboard` → `net-rally/sections/dashboard-section.component.ts`（內嵌 `app-player-dashboard`＋insights＋benchmark，自行呼叫既有 `match-dashboard` 端點並帶 `sport`）；`shareHighlights` → `pickHighlights`）；為兩個包裝元件寫 spec
- [X] T041 [US1] 在 `web/sports/registry.ts` 的載入表加入 `net_rally: () => import('./types/net-rally/net-rally.module').then(m => m.NET_RALLY)`；`apps/web/src/test-setup.ts` 同步預載 `NET_RALLY` 進 registry（行內 eslint 註記）（Decision 14）
- [X] T042 [P] [US1] 先寫 `web/sports/hosts/scoreboard-host.component.spec.ts`（`peek` 命中時同步渲染子元件、未命中時顯示載入並於 `resolve` 後渲染、載入失敗顯示 `errors.sportModuleLoadFailed` 與重試、`initialState` 透傳），再實作 `web/sports/hosts/scoreboard-host.component.ts`（先取一次 `GET /courts/by-token/{token}/state` 得 `sport.type_key`，渲染 `surfaces.scoreboard`）
- [X] T043 [P] [US1] 同 T042 模式實作 `web/sports/hosts/control-panel-host.component.{ts,spec.ts}`、`all-courts-block-host.component.{ts,spec.ts}`（輸入 `token, courtId, name, state`，由 `state.sport.type_key` 決定）、`court-control-host.component.{ts,spec.ts}`（輸入 `groupId, court`，由 `ScheduleResponse.sport` 決定）
- [ ] T044 [P] [US1] 實作 `web/sports/hosts/match-detail-host.component.{ts,spec.ts}`（輸入同原 dialog：`detail, loading, loadError, shareContext`；依 `detail.sport.type_key` 解析模組後把 `detail.sections` 交給 `SectionOutlet`；宿主使用選擇器 `app-match-record-detail-dialog`（原 dialog 已於 T039 改名），並保留原輸入名稱與 `open()`／`close()` 方法簽名以維持四個宿主頁 spec 的查詢與呼叫）與 `web/sports/hosts/dashboard-host.component.{ts,spec.ts}`（輸入 `sport: ActivitySummary | null`、`filters`；隔網回合制走 `net_rally.dashboard` 區塊）
- [ ] T045 [US1] 接線：`web/app.routes.ts` 的 `scoreboard/:courtToken`、`control/:courtToken`、`control/all/:allCourtsToken` 改掛宿主（全部場地殼 `web/features/control-panel/all-courts/all-courts-control-panel.component.*` 改用 `app-all-courts-block-host`）；`web/features/group-admin/admin-page/admin-page.component.html` 改用 `app-court-control-host`；`match-history`、`group-history`、`group-member-view/match-records`、`friend-match-records` 改用 `app-match-detail-host`；`match-history` 與 `friend-match-records` 的儀表板改用 `app-dashboard-host`（本 story 只有羽球，宿主固定傳 `badminton`）；四個宿主頁 spec 依允許變更清單補 providers
- [X] T046 [US1] 在 `apps/web/` 執行 `npx ng test --watch=false`、`npx ng lint`、`npx ng build --configuration production`：通過數與 T007 相同；`git diff origin/ut -- apps/web/src/app` 中的 `*.spec.ts` 只含允許變更；`apps/web/dist/` 出現 `net-rally` 獨立 chunk（US1 前端檢查點）
- [ ] T047 [US1] 手動比對：以 `api/scripts/seed_dashboard_demo.py` 種子資料，依 quickstart §1 逐畫面比對羽球團排行榜、詳細頁、儀表板、分享圖卡（SC-002）；結果記錄到 `docs/043-zero-change-check/`（本機文件）

**Checkpoint**: 羽球已在外掛內、核心不含羽球規則、邊界關卡通過、既有測試全綠。這是 MVP：可獨立合併。

---

## Phase 4: User Story 2 - 開團時選活動，用該活動的規則計分（Priority: P1）

**Goal**: 活動目錄端點、開團／編輯的通用參數、回應帶活動摘要、開團表單第一區塊選活動、非羽球隔網活動（桌球）關閉發球與落點（FR-001、FR-002、FR-005～FR-012、FR-016、FR-018、FR-019、FR-025）。

**Independent Test**: quickstart §2：選撞球開團帶入預設、選桌球開團後控制板無發球與落點且 15:13 結束、`PATCH` 改活動被拒。

### 後端

- [X] T048 [P] [US2] 先寫 `api/tests/contract/test_sports_catalog.py`：`GET /sports` 形狀（`types[]` 含 `params_schema` 與 `section_kinds`、`builtin[]` 9 筆且 `other` 最後、未登入無 `custom`）（contracts/sports-api.md §1）
- [X] T049 [P] [US2] 先寫 `api/tests/contract/test_create_group_sport.py`：`sport` 省略 ⇒ 羽球且回應與既有相同；`billiards` 帶入預設（`team_size=1`、`target=5`、`win_by=1`、`cap=null`）；`team_size` 與 `match_mode` 衝突 ⇒ 422；`team_size` 不在 `team_size_options` ⇒ 422；`type_params` 不符 schema ⇒ 422；`PATCH` 改 `sport` ⇒ `409 SPORT_IMMUTABLE`；`PATCH` 改 `win_by`／`cap_score` 成功；回應含 `sport`、`team_size`；預設團名「的撞球團」與場地「球桌一」（contracts/sports-api.md §3）
- [X] T050 [P] [US2] 先寫 `api/tests/integration/test_table_tennis_flow.py`：桌球團開團→排點→計分到 10:10→15:13 結束；期間不產生 `score_serve_records`；`match.scoreUpdated` 的 `serve` 為 `null`；`shot-placement` ⇒ `409 MODULE_NOT_SUPPORTED`；`PUT detailed-scoring` ⇒ 409；詳細頁回應 `serve_stats`／`landing_distribution` 為 null 但 `clutch_stats` 存在（FR-025）
- [X] T051 [US2] 實作 `api/app/sports/router.py::GET /sports`（`optional_member`；`types[]` 由 registry 產生 JSON Schema 與 `section_kinds`；`builtin[]` 自 catalog）並在 `api/app/main.py` 註冊；T048 全綠
- [X] T052 [US2] `api/app/domains/group/schemas.py`：`SportRef`、`SportSummary` 輸出、`CreateGroupRequest`／`EditGroupRequest` 新欄位與跨欄位驗證（`team_size`／`match_mode` 至少一個且一致、通用參數不變量、`score_steps` 非空遞增正整數）、各回應 schema 加 `sport`／`team_size`
- [X] T053 [US2] `api/app/domains/group/service.py::create_group`：解析 `sport`（catalog／`other`；`custom` 於 US4）、以活動 `defaults` 補齊未給參數、`registry.get(type_key).params_schema()` 驗證 `type_params`、`team_size` 檢查、依 `sport_key` 取預設團名後綴與場地名（T019）；`edit_group`：`SPORT_IMMUTABLE`、通用參數可改；`_to_public` 與列表項帶 `sport`；T049 全綠
- [X] T054 [US2] `set_detailed_scoring`（`api/app/domains/group/service.py`）與三個 `shot-placement` 端點（`api/app/domains/schedule/router.py`、`api/app/domains/group/router.py`）依 `type_params.modules.shot_placement` 守門 `409 MODULE_NOT_SUPPORTED`；`NetRallyPlugin.on_match_start`／`on_spine_event` 依 `modules.serve_tracking` 跳過發球；T050 全綠
- [X] T055 [P] [US2] 先寫 `api/tests/unit/sports/test_net_rally_dashboard_specs.py`：`dashboard_metric_specs(modules)` 在 `serve_tracking=false` 時不含 `team_serve`／`team_receive`／`own_serve`／`own_receive`，在 `shot_placement=false` 時不含落點與結束型態相關指標，羽球（兩者皆 true）仍為原 23 項且順序不變（FR-025）
- [X] T056 [US2] `NetRallyPlugin.dashboard_metric_specs(modules)` 依模組過濾；`api/app/domains/member/service.py::build_member_match_dashboard` 依 `sport` 解析出的活動 `type_params.modules` 取目錄（不帶 `sport` 或 `sport=badminton` 時為完整 23 項，既有釘點不變），`landing`／`error_breakdown` 在模組關閉時回 `null`；`api/tests/contract/test_member_match_dashboard_endpoint.py` 新增「`sport=table_tennis` 回應的 `metrics` 不含發球、落點、結束型態鍵」案例，既有案例不改；T055 全綠
- [X] T057 [US2] 排程核心改讀 `team_size`：`api/app/domains/schedule/service.py` 約 12 處 `match_mode == "singles"`／`"doubles"` 與 `api/app/domains/schedule/rest.py:131` 改為 `team_size == 1`／`== 2`（行為等價，既有排程測試全綠）

### 前端

- [X] T058 [US2] 在 `web/sports/types/net-rally/match-point.ts` 與 `net-rally` 各控制板的 `plusPressed`／match-point 判定處把 `cap_score` 可空納入（`isMatchPoint` 對 `cap=null` 只看 `target`＋`win_by`；`web/sports/types/net-rally/match-point.spec.ts` 加案例但既有案例不改）
- [X] T059 [P] [US2] 先寫 `web/core/api/sports.service.spec.ts`，再實作 `web/core/api/sports.service.ts::getCatalog()`（快取一次）
- [X] T060 [P] [US2] 先寫 `web/sports/types/net-rally/create-form-fields/create-form-fields.component.spec.ts`（羽球顯示既有 `21pt/15pt/custom` 下拉且預設 `21pt`；桌球只顯示 `custom` 且預設 11／2／空；`modules` 不可編輯），再實作該元件（輸入 `form`、`sport`）
- [X] T061 [US2] 實作 `web/sports/hosts/create-form-fields-host.component.{ts,spec.ts}`（依 `sport.type_key` 解析模組後渲染 `surfaces.createFormFields`）
- [X] T062 [US2] `web/features/group-admin/create-group/create-group.component.{ts,html,scss}`：最上方新增「活動」區塊（內建活動卡片 `<button aria-pressed>` 含圖示與 i18n 名稱、「其他」需輸入名稱；預設羽球）；`match_mode` 下拉改為 `team_size`（1／2，依活動 `team_size_options`）並在 payload 同時送 `match_mode`；通用參數欄位（`end_mode`、`target_score`、`win_by`、`cap_score` 可空、`allow_draw`、`score_steps`）與類型欄位由 `app-create-form-fields-host` 渲染；團名佔位文字依活動名詞；既有 17 個 spec 不改（表單初始狀態不變），新增 spec 覆蓋活動切換與預設帶入（FR-006、FR-009、FR-012）
- [X] T063 [US2] `web/features/group-admin/shared/group-form-validators.ts`：`minMembersForMode` 改以 `team_size`（`2 × team_size`）、新增 `genericScoringValidator`（`target ≥ win_by`、`cap ≥ target` 或空、`score_steps` 非空遞增）；spec 補案例、既有案例不改
- [X] T064 [US2] `web/features/group-admin/admin-page/admin-page.component.{ts,html}`：顯示活動標籤（不可編輯）；`editForm` 改 `team_size`（同步送 `match_mode`）與通用參數；`manual-assign.component.ts` 的 `singles ? 1 : 2` 改讀 `team_size`；`SPORT_IMMUTABLE` 錯誤提示
- [X] T065 [US2] i18n：`i18n/zh-TW.json` 與 `i18n/en.json` 新增 `sports.*`（9 個活動名稱、名詞集合）、`createGroup.activity*`、`createGroup.generic*`（通用參數標籤與說明）、`errors.SPORT_IMMUTABLE`／`MODULE_NOT_SUPPORTED`；新增 `web/sports/sports-i18n.spec.ts` 做 key 一致性檢查（FR-037）
- [ ] T066 [US2] 在 `api/` 與 `apps/web/` 執行完整測試與關卡；依 `specs/043-sport-type-plugin-foundation/quickstart.md` §2 手動驗證，撞球流程以碼錶計時並記錄於 `docs/043-quickstart-run.md`（SC-003）（US2 檢查點）

**Checkpoint**: 可用目錄中任一隔網活動開團計分；撞球可開團但控制板仍是通用 +1（局數制在 US3 補上）。

---

## Phase 5: User Story 3 - 局數制活動有自己的計分板、詳細頁與儀表板（Priority: P1）

**Goal**: `frames` 外掛（局內逐分、局結束、自動達標、復原）、`/events` 與 `/undo` 端點、Ably `match.eventApplied`、詳細頁區塊、`dashboard-sections` 與 `activities` 端點、對戰紀錄「統計」頁籤改為活動頁籤（FR-013～FR-015、FR-018a、FR-019、FR-021、FR-023、FR-026）。

**Independent Test**: quickstart §3：撞球搶五全流程、局內比分 11:9 自動結束該局、復原語意、詳細頁逐局清單、儀表板「撞球」頁籤指標，羽球頁籤與升級前相同。

### 後端：測試先行

- [X] T067 [P] [US3] 先寫 `api/tests/unit/sports/test_frames_plugin.py`：`FramesParams` 驗證（`frame_target` 可空、`frame_win_by ≥ 1`）；事件→狀態：`frame_point` 累加、`frame_target=11` 且 `win_by=2` 時 11:9 自動產生 `frame_result(ended_by='target')`＋`follow_up_point`、10:10 不結束、`frame_end` 任意比分手動結束、下一局歸零；`frame_scoring_enabled=false` 拒絕 `frame_point`；`live_state()` 推導；`after_undo()` 回到該局結束前比分；`match_wins` 以 `win_by=1` 判定先贏 5 局（data-model §7）
- [X] T068 [P] [US3] 先寫 `api/tests/contract/test_match_events_endpoint.py`：三個授權面的 `POST …/events`（合法 kind、未宣告 kind ⇒ `422 EVENT_KIND_NOT_ALLOWED`、羽球比賽任何 kind ⇒ 422、非 `in_progress` ⇒ 409、`follow_up_score_event_id`、達標後 `completed`）與 `POST …/undo`（無事件 ⇒ `409 NOTHING_TO_UNDO`、刪 `point` 時比分回退、羽球 ⇒ `409 UNDO_NOT_SUPPORTED`）；`match.eventApplied` 以 monkeypatch `publish` 斷言（contracts/match-events-api.md §2、§4、§8）
- [X] T069 [P] [US3] 先寫 `api/tests/contract/test_dashboard_sections_endpoint.py`（`sport` 必填、隔網回 `net_rally.dashboard` 標記、局數制回 `metric_grid`＋`frames.dashboard_summary`＋`stat_table`、無比賽回 `text_note`、授權同 `match-dashboard`）與 `api/tests/contract/test_member_activities_endpoint.py`（依場數降冪、`filter_value` 形狀、`other:<name>` 歸類）（contracts/sections-manifest.md §4、sports-api.md §5）
- [X] T070 [P] [US3] 先寫 `api/tests/integration/test_frames_flow.py`：撞球團開團→排點→局內計分→自動與手動結束局→復原→贏到 5 局→排行榜以場計→詳細頁 `sections` 含 `frames.frame_list`／`frames.frame_trend` 且羽球欄位為 null→`dashboard-sections?sport=billiards` 指標值正確（局勝率、先贏第一局後勝率、平均局數）
- [X] T071 [P] [US3] 為 `match_filters_query` 新增 `sport` 參數先補測試：`api/tests/contract/test_member_match_dashboard_endpoint.py` 與 `test_member_match_records_endpoint.py`（若存在）新增「`sport=badminton` 回應與無參數相同」「`sport=billiards` 對 `match-dashboard` ⇒ `409 SPORT_TYPE_NOT_SUPPORTED`」案例，以及「會員同時有羽球與撞球紀錄、不帶 `sport` 呼叫 `match-dashboard` 與 `match-records`，只回隔網回合制的比賽」案例（既有案例不改；`test_member_matchups.py:300-320` 的參數集合一致性因四路由同時加入而維持）

### 後端：實作

- [X] T072 [US3] 建立 `api/app/sports/types/frames/{__init__,models,params}.py`（`FrameResult`、`FramePoint` ORM；`FramesParams`）與外掛自己的 migration `api/alembic/versions/<rev>_frames_tables.py`（down_revision 為 T010 的 rev；建立 `frames_frame_results`、`frames_frame_points`，含 downgrade），並在 `api/alembic/env.py` 匯入 models；執行 `alembic upgrade head && alembic downgrade -1 && alembic upgrade head`
- [X] T073 [US3] 實作 `api/app/sports/types/frames/{events,stats,presentation,plugin}.py::FramesPlugin`（`event_schemas` 兩種 kind、`apply_event`、`live_state`、`after_undo`、`load_stat_inputs`、`match_detail`（`frames.frame_list`、`frames.frame_trend`）、`dashboard_metric_specs` 回 `None`、`dashboard_sections`（`metric_grid` 每項指標附 `group_average`／`delta`，以核心 `group_benchmark.build()` 餵入局數制指標值計算；`frames.dashboard_summary`；對手 `stat_table`）、`estimate_minutes`）；在 `register_all()` 註冊；T067 全綠（FR-027）
- [X] T074 [US3] `api/app/domains/schedule/service.py` 新增 `apply_plugin_event(session, court, match_id, kind, payload, source)`（脊椎事件 `delta=0` → `plugin.apply_event` → `follow_up_point` 走 `apply_score_delta` 骨架 → publish `match.eventApplied`）與 `undo_last_event(session, court, match_id)`（刪最後一筆 → 比分回退 → `after_undo` → publish）；`schedule/schemas.py` 新增 `PluginEventRequest`、`PluginEventResult`
- [X] T075 [US3] 在 `api/app/domains/schedule/router.py`（token 與管理頁）與 `api/app/domains/group/router.py`（全部場地）新增 `POST …/events` 與 `POST …/undo`，授權沿用同路徑的 `/score`；T068 全綠
- [X] T076 [US3] `api/app/domains/member/{router,service,schemas}.py`：`match_filters_query` 與 `MemberMatchFilters` 加 `sport`（值域解析：內建 key、`custom:<id>`、`other:<name>`、`custom_or_other`）並套用到四個 records／dashboard 路由；`match-dashboard` 對非隔網類型回 `409 SPORT_TYPE_NOT_SUPPORTED`；新增 `GET /members/me/dashboard-sections`、`/members/{id}/dashboard-sections`（`build_dashboard_sections`：`_filtered_member_matches` → `plugin.load_stat_inputs` → `plugin.dashboard_sections`）與 `GET /members/me/activities`、`/members/{id}/activities`；T069、T071 全綠
- [X] T077 [US3] `api/app/domains/group/service.py::build_match_record_detail` 對非隔網類型把羽球專屬欄位設為 null、`events[]` 帶 `kind` 與 int `delta`（`api/app/domains/group/schemas.py::ScoreEventSummary`）；T070 全綠

### 前端

- [ ] T078 [P] [US3] `web/core/api/court-control.service.ts` 與 `web/features/group-admin/schedule-management/schedule.service.ts` 新增 `applyEvent(kind, payload)`、`undoLastEvent()`（三個授權面）＋ spec
- [ ] T079 [P] [US3] `web/core/api/sports.service.ts` 新增 `getActivities(memberId?)`、`getDashboardSections(filters, sport, memberId?)` ＋ spec
- [ ] T080 [P] [US3] 先寫 spec 再實作 `web/sports/types/frames/scoreboard/frames-scoreboard.component.{ts,html,scss,spec.ts}`（雙方局數大字、目前局次／先贏幾局、啟用時本局比分；訂閱 `match.scoreUpdated`、`match.eventApplied`、`match.ended`、`rotation.updated`、`match.nextRound`；下一組預告與離線提示沿用既有樣式）（FR-019）
- [ ] T081 [P] [US3] 先寫 spec 再實作 `web/sports/types/frames/control-panel/frames-control.component.{ts,html,scss,spec.ts}`（本局 +1／−1 各隊、「標記本局勝方」A／B、分低者被標勝二次確認、「復原」、「放棄比賽」沿用既有確認；未啟用局內比分時只顯示標記與復原）與其包裝成三個 surface 的元件 `frames-control-panel`（token）、`frames-all-courts-block`、`frames-court-control`（管理頁 `ScheduleService`）（FR-018）
- [ ] T082 [P] [US3] 先寫 spec 再實作區塊元件 `web/sports/types/frames/sections/{frame-list,frame-trend,dashboard-summary}-section.component.ts`（`frame_list` 為表格：局序、勝方、局內比分、結束方式；`frame_trend` 用 `shared/line-chart`）
- [ ] T083 [P] [US3] 先寫 spec 再實作 `web/sports/types/frames/create-form-fields/frames-create-form-fields.component.ts`（先贏幾局＝`target_score`、記局內比分開關、局內達標分可空、局內需領先分）
- [ ] T084 [US3] `web/sports/types/frames/frames.module.ts` 匯出 `FRAMES`；`web/sports/registry.ts` 載入表加 `frames`
- [ ] T085 [US3] `web/features/member/match-history/match-history.component.{ts,html}`：「統計」頁籤改為活動頁籤（`getActivities()`；只有一筆時不顯示頁籤列；每個頁籤渲染 `app-dashboard-host` 並把 `filter_value` 併入篩選）；`friend-match-records` 同樣處理；既有 46＋27 個 spec 依允許變更清單補 mock 方法，斷言不改（FR-026）
- [ ] T086 [US3] i18n：在 `i18n/zh-TW.json` 與 `i18n/en.json` 新增 `frames.*`（控制板、計分板、區塊標題、指標名稱、確認文案）、`playerDashboard.activityTabs*`、`errors.EVENT_KIND_NOT_ALLOWED`／`NOTHING_TO_UNDO`／`UNDO_NOT_SUPPORTED`／`UNDO_CONFLICT`／`SPORT_TYPE_NOT_SUPPORTED`；更新 `web/sports/sports-i18n.spec.ts`
- [ ] T087 [US3] 在 `api/` 與 `apps/web/` 執行完整測試與關卡；依 `specs/043-sport-type-plugin-foundation/quickstart.md` §3 手動驗證；`apps/web/dist/` 出現 `frames` 獨立 chunk（SC-006）（US3 檢查點）

**Checkpoint**: 撞球等局數制活動完整可用；羽球與桌球頁籤與之前相同。

---

## Phase 6: User Story 5 - 通用類型：只有比分與勝負（Priority: P2）

**Goal**: `generic` 外掛、`/score` 放寬 `delta`、`/finish`（手動結束並記錄結果）、平手 `D` 與 `draws` 彙總、前端通用模組與兩個結束動作（FR-017、FR-017a、FR-018、FR-020、FR-024）。

**Independent Test**: quickstart §4：「其他」開團 +1／+2、7:7 記平手、不允許平手時被拒、放棄比賽不計成績。

### 後端：測試先行

- [ ] T088 [P] [US5] 先寫 `api/tests/unit/sports/test_generic_plugin.py`（`GenericParams` 為空物件；`dashboard_sections` 的 `metric_grid` 鍵集合；`match_detail` 的 `score_timeline`＋`metric_grid`；`estimate_minutes` 達標 0.6×target、手動 15）
- [ ] T089 [P] [US5] 先寫 `api/tests/unit/domains/group/test_standings_draws.py`：`winner_team='D'` 的 completed 比賽在 `build_group_standings`／`build_group_final_standings`／`build_group_match_records` 計為 `draws`，不計勝敗；名次依勝場；`abandoned` 仍不計（Decision 4、FR-020）
- [ ] T090 [P] [US5] 先寫 `api/tests/contract/test_finish_endpoint.py`（三授權面：`end_mode='target'` ⇒ `409 FINISH_NOT_AVAILABLE`；分高者勝；同分＋`allow_draw` ⇒ `winner_team='D'` 與 `match.ended` payload；同分不允許 ⇒ `409 DRAW_NOT_ALLOWED`；`/end` 仍 `abandoned`）與 `api/tests/contract/test_score_steps.py`（`score_steps=[1,2]` 接受 ±2、拒絕 ±3 ⇒ `422 SCORE_STEP_NOT_ALLOWED`；羽球拒絕 ±2）
- [ ] T091 [P] [US5] 先寫 `api/tests/integration/test_generic_flow.py`：「其他」團（每隊 2、`[1,2]`、manual、allow_draw）一場平手一場勝負→排行榜勝敗平→我的團場數含平手→詳細頁 `score_timeline`；不允許平手的團同分結束被拒

### 後端：實作

- [ ] T092 [US5] 建立 `api/app/sports/types/generic/{__init__,params,presentation,plugin}.py::GenericPlugin`（`dashboard_sections` 的 `metric_grid` 每項指標附 `group_average`／`delta`，以核心 `group_benchmark.build()` 計算；FR-027）並註冊；T088 全綠
- [X] T093 [US5] `api/app/domains/schedule/schemas.py::ScoreRequest.delta` 放寬為 `int`；`apply_score_delta` 檢查 `abs(delta) ∈ match.score_steps`（`SCORE_STEP_NOT_ALLOWED`）；`end_mode='manual'` 跳過達標判定
- [X] T094 [US5] 新增 `api/app/domains/schedule/service.py::finish_match(session, court, match_id)` 與三個授權面的 `POST …/finish`（`api/app/domains/schedule/router.py`、`api/app/domains/group/router.py`）；沿用 `_advance_after_terminal`／`_publish_match_ended`；T090 全綠
- [ ] T095 [US5] 平手彙總：`api/app/domains/group/schemas.py`（`MatchRecordSummary.winner_team` 加 `D`；`RoundRecord`、`MemberStandingRow`、`FinalStandingRow`、`OpponentRecord` 加 `draws=0`）、`api/app/domains/group/service.py`（三個彙總函式與 `player_records`）、`api/app/domains/member/service.py`（`won`／`_sample_from`、`MemberMatchRecordsResponse` 的 `total_losses` 改為 `total − wins − draws` 並加 `total_draws`）、`api/app/domains/member/matchups.py`（平手不計勝負）；T089、T091 全綠

### 前端

- [ ] T096 [P] [US5] `web/core/api/court-control.service.ts`、`schedule.service.ts` 新增 `finishMatch()`；`score()` 的 `delta` 型別放寬為 `number` ＋ spec
- [ ] T097 [P] [US5] 先寫 spec 再實作 `web/sports/types/generic/control-panel/generic-control.component.{ts,html,scss,spec.ts}`（依 `score_steps` 渲染 +N 各隊與「復原」；`end_mode='manual'` 顯示「結束並記錄結果」（確認文案含目前比分與平手提示）與「放棄比賽」（既有確認），兩者名稱、圖示、確認文字不同；`target` 模式只顯示「放棄比賽」）與三個 surface 包裝（token／all-courts／court-control）（FR-017a、憲章 V）
- [ ] T098 [P] [US5] 先寫 spec 再實作 `web/sports/types/generic/scoreboard/generic-scoreboard.component.*`（比分大字、平手結果顯示「平」文字）與 `web/sports/types/generic/create-form-fields/generic-create-form-fields.component.*`（本期無類型專屬欄位，僅說明文字）
- [ ] T099 [US5] `web/sports/types/generic/generic.module.ts` 匯出 `GENERIC`；`web/sports/registry.ts` 載入表加 `generic`
- [ ] T100 [US5] 排行榜與紀錄畫面顯示平手：`web/features/group-admin/**`（團內排行榜）、`web/features/member/my-groups/group-history/**`（最終排名）、`web/features/group-member-view/**`、`shared/match-card`（勝／敗／平標籤，文字不只靠顏色）；相關 spec 補案例
- [ ] T101 [US5] i18n：在 `i18n/zh-TW.json` 與 `i18n/en.json` 新增 `genericSport.*`、`controlPanel.finish*`／`abandon*`、`common.draw`、`errors.SCORE_STEP_NOT_ALLOWED`／`FINISH_NOT_AVAILABLE`／`DRAW_NOT_ALLOWED`；更新 `web/sports/sports-i18n.spec.ts`
- [ ] T102 [US5] 在 `api/` 與 `apps/web/` 執行完整測試與關卡；依 `specs/043-sport-type-plugin-foundation/quickstart.md` §4 手動驗證；`apps/web/dist/` 出現 `generic` 獨立 chunk（US5 檢查點）

**Checkpoint**: 任何 1v1／2v2 的活動都能以「其他」開團並完整記錄勝敗平。

---

## Phase 7: User Story 4 - 自訂活動（Priority: P2）

**Goal**: 會員自訂活動的建立、刪除、目錄顯示、用它開團；訪客「其他」不保存（FR-003、FR-004）。

**Independent Test**: quickstart §5。

- [ ] T103 [P] [US4] 先寫 `api/tests/contract/test_member_sports_endpoint.py`：`POST /members/me/sports`（201 形狀、未驗證會員 403、名稱長度 422、`type_key` 未註冊 422、`defaults` 不符 422、同名 `409 CUSTOM_SPORT_NAME_TAKEN`、`name="羽球"` 可成功建立（與內建同名允許）、第 21 筆 `409 CUSTOM_SPORT_LIMIT`）、`DELETE`（204、非本人 404、刪後既有團 `sport.name` 仍為快照）、`GET /sports` 登入後 `custom[]`；`POST /groups` 以 `custom` 開團（本人成功、他人 `403 CUSTOM_SPORT_FORBIDDEN`、未登入 403）；訪客 `other` 開團回應 `sport.name` 為輸入名稱（contracts/sports-api.md §2、§3）
- [ ] T104 [US4] `api/app/domains/member/{schemas,service,router}.py`：`CustomSportCreate`／`CustomSportResponse`、`create_custom_sport`（上限、同名、`defaults` 依類型驗證）、`delete_custom_sport`、`list_custom_sports`；`api/app/sports/router.py::GET /sports` 帶 `custom[]`；`create_group` 支援 `sport_key='custom'`（快照 `sport_name`、`type_key`、`defaults`）；T103 全綠
- [ ] T105 [P] [US4] `web/core/api/sports.service.ts` 新增 `createCustomSport()`、`deleteCustomSport()` ＋ spec
- [ ] T106 [US4] 先寫 spec 再實作 `web/features/group-admin/create-group/custom-sport-dialog.component.{ts,html,scss,spec.ts}`（名稱、類型、每隊人數選項、通用參數、類型欄位透過 `app-create-form-fields-host`、名詞選擇）；`create-group` 活動區塊新增「我的自訂」區（列出、選用、刪除含確認；只有已驗證會員可見）與訪客「其他」的名稱輸入（FR-004；US4 情境 3）
- [ ] T107 [US4] i18n：在 `i18n/zh-TW.json` 與 `i18n/en.json` 新增 `createGroup.customSport*`、`errors.CUSTOM_SPORT_*`；更新 `web/sports/sports-i18n.spec.ts`
- [ ] T108 [US4] 在 `api/` 與 `apps/web/` 執行完整測試與關卡；依 `specs/043-sport-type-plugin-foundation/quickstart.md` §5 手動驗證（US4 檢查點）

**Checkpoint**: 目錄外的活動可由會員自訂並重用。

---

## Phase 8: User Story 6 - 依活動找團、看戰績、分享（Priority: P2）

**Goal**: 開團列表與我的團的活動篩選與標籤、分享圖卡活動名稱與類型亮點（FR-028、FR-029）。

**Independent Test**: quickstart §6。

- [ ] T109 [P] [US6] 先寫 `api/tests/contract/test_group_list_sport_filter.py`（`sport=billiards`、`sport=custom_or_other`、與 `match_mode` 並用、無效值 422）與 `api/tests/contract/test_my_groups_sport_filter.py`（`sport=custom:<id>` 只列本人自訂活動的團、他人 id 空結果、與既有篩選並用）
- [ ] T110 [US6] `api/app/domains/group/{router,service}.py::list_groups` 與 `api/app/domains/member/{router,service}.py::get_my_groups` 新增 `sport` 篩選；T109 全綠
- [ ] T111 [P] [US6] `web/features/group-join/group-list/group-list.component.{ts,html}`＋`web/features/group-join/group-join.service.ts::listGroups`：活動篩選下拉（內建各一項＋「自訂／其他」）、篩選 chip、團卡活動名稱與圖示；`GroupListFilters` 加 `sport`；spec 補案例
- [ ] T112 [P] [US6] `web/features/member/my-groups/my-groups.component.{ts,html}`＋`web/features/friends/friends.service.ts::getMyGroups`：活動篩選（內建＋「自訂／其他」＋本人自訂活動各一項，來源 `getCatalog().custom`）、團卡活動標籤；`MyGroupsFilters` 加 `sport`；spec 補案例
- [ ] T113 [P] [US6] 分享圖卡活動名稱：`web/core/match-share-card/share-card-model.ts`／`share-card-renderer.ts`（標題下的 meta 行加活動名稱；亮點改為 `registry.peek(type_key)?.shareHighlights?.(detail, protagonist) ?? []`，空陣列則省略區塊；走勢圖只在 `net_rally` 且有 `point` 事件時繪製）、`web/core/group-share-card/{leaderboard,my-stats}-card-renderer.ts`（副標題加活動名稱）；既有 renderer spec 的 `texts()` 斷言不改，新增活動名稱案例與局數制單場卡案例（US6 情境 4）
- [ ] T114 [US6] i18n：在 `i18n/zh-TW.json` 與 `i18n/en.json` 新增 `groupJoin.sportFilter*`、`myGroups.sportFilter*`、`shareCard.activityLabel`；更新 `web/sports/sports-i18n.spec.ts`
- [ ] T115 [US6] 在 `api/` 與 `apps/web/` 執行完整測試與關卡；依 `specs/043-sport-type-plugin-foundation/quickstart.md` §6 手動驗證（US6 檢查點）

**Checkpoint**: 多活動在瀏覽與分享層面可辨識。

---

## Phase 9: User Story 7 - 維護者新增一種比賽類型不必改核心（Priority: P2）

**Goal**: 把可擴充性變成可機械驗證的關卡（FR-033～FR-036、SC-005、SC-006、SC-008）。

**Independent Test**: quickstart §7。

- [ ] T116 [P] [US7] 先寫 `api/tests/unit/sports/test_plugin_contracts.py`：對每個已註冊外掛驗證 `event_schemas()` 的 kind 以 `<type_key>.` 為前綴、`match_detail()`／`dashboard_sections()` 產出的 kind ⊆ `section_kinds ∪ GENERIC_KINDS`、`params_schema()` 可產生 JSON Schema、`tables()` 的每張表都有 `score_event_id` 外鍵 cascade；並把 `section_kinds` 匯出成 `api/app/sports/section-kinds.json`（`pytest --update-section-kinds` 更新、預設模式比對不得漂移）
- [ ] T117 [P] [US7] 先寫 `web/sports/section-outlet/section-outlet.contract.spec.ts`：讀 `apps/api/app/sports/section-kinds.json`（以相對路徑匯入 JSON），對每個 kind 斷言三個類型模組（測試中同步註冊）有元件或屬於 `GENERIC_KINDS`；`unknown.kind` 走退路（SC-008）
- [ ] T118 [US7] 建立 `api/scripts/check_plugin_scope.sh`（quickstart §7 的 SC-005 指令：給定 commit 範圍與 `type_key`，列出不在允許路徑內的改動檔，非空即失敗）並在 tasks 提交紀錄上驗證 `frames` 與 `generic` 各自的實作提交範圍為空
- [ ] T119 [US7] 執行 quickstart §7 的邊界破壞測試（核心加一行匯入外掛 → `lint-imports` 失敗；前端同理 → `npm run lint` 失敗），把結果記錄到 `docs/043-extensibility-check/`（本機文件）
- [ ] T120 [US7] 在 `apps/web/` 執行 `npx ng build --configuration production`：`apps/web/dist/` 有 `net-rally`、`frames`、`generic` 三個獨立 chunk 且 `main-*.js` 不含 `frames.frame_list`（SC-006）

**Checkpoint**: 邊界與契約皆由工具守住；新增類型的檢查清單（contracts/plugin-boundary.md §5）可照做。

---

## Phase 10: Polish & Cross-Cutting Concerns

- [ ] T121 [P] 更新 `docs/features.md`（功能總覽加「活動與比賽類型」、移除「羽球專用」描述、我的團活動頁籤）、`docs/tools.md`（`system_config` 新 key）、`docs/cicd-pipeline.md`（關卡指令加 `lint-imports`）——本機 docs，直接改主 checkout
- [ ] T122 [P] 在 `specs/043-sport-type-plugin-foundation/plan.md` 的 Post-design re-check 段補一句：`EndingType`／`RecordShotPlacementRequest` 留在核心 schema 的妥協（research.md Decision 10 已於 tasks 階段更新）
- [ ] T123 [P] 移除死碼：`api/app/domains/schedule/service.py` 的 `_FALLBACK_MINUTES_PER_TARGET_POINT`、`api/app/domains/group/service.py` 中已搬走的發球／落點查詢；`api/scripts/reset_data.py` TRUNCATE 清單加 `member_sports`、`frames_frame_results`、`frames_frame_points`
- [ ] T124 [P] i18n 全量 parity：確認所有新增 key 在 `i18n/zh-TW.json` 與 `i18n/en.json` 一致（既有 parity spec 全綠，`grep -c` 對照）（SC-007）
- [ ] T125 [P] 無障礙檢查：以 `docs/043-a11y-check/shoot.mjs`（沿用 `docs/my-groups-match-count-check/shoot.mjs` 的 360／414／1280 與 WebKit 模式）檢查 `web/features/group-admin/create-group/` 的活動卡片、`web/sports/types/{frames,generic}/control-panel/` 的 `+N`／「標記本局勝方」／「結束並記錄結果」按鈕觸控目標 ≥ 44px、鍵盤可達、`aria-pressed`／`aria-label`；平手與勝敗標籤不只靠顏色；360px 無橫向捲動（憲章 VII）
- [ ] T126 執行完整 quickstart（§1～§8）並把各節結果記錄到 `docs/043-quickstart-run.md`（本機文件）
- [ ] T127 最終關卡：後端 `ruff check app tests && mypy app && lint-imports && python -m pytest -q`、前端 `npm run lint && npx ng test --watch=false && npx ng build --configuration production` 全綠；`git diff origin/ut -- apps/api/tests apps/web/src/app/**/*.spec.ts` 複核允許變更清單；推送 `feature/sport-type-plugin-foundation`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1（Setup）**：無依賴；T001–T006 可平行，T007 最後。
- **Phase 2（Foundational）**：依賴 Phase 1；後端 T008→T009；T010 獨立；T011→T012；T013、T014、T015 平行；T016、T017 平行（依賴 T015）；T018 依賴 T013；T019 獨立；T020 最後。前端 T021–T025 平行，T026 最後。**阻擋所有 story。**
- **Phase 3（US1）**：依賴 Phase 2。後端 T027、T028 先；T029→T030→T031→T032→T033→T034→T035→T036→T037→T038 大致序列（同一批核心檔）。前端 T039→T040→T041；T042–T044 平行（依賴 T041）；T045→T046→T047。
- **Phase 4（US2）**：依賴 US1（`NetRallyPlugin.modules` 與宿主）。
- **Phase 5（US3）**：依賴 US2（開團可選撞球）。
- **Phase 6（US5）**：依賴 US1；與 US3 可平行（不同檔案：`generic/` 對 `frames/`；共用的 `schedule/service.py` 新增函式互不重疊，但 `schemas.py` 與 router 需先後合併）。
- **Phase 7（US4）**：依賴 US2 與 US5（「其他」為通用類型）。
- **Phase 8（US6）**：依賴 US2；圖卡亮點部分依賴 US1 的 `shareHighlights`。
- **Phase 9（US7）**：依賴 US3 與 US5（要有三個外掛才有意義的契約）。
- **Phase 10**：依賴全部。

### User Story Dependencies

- **US1**：只依賴 Phase 2；是 MVP，可獨立合併（對使用者無感）。
- **US2**：依賴 US1。
- **US3**：依賴 US2。
- **US5**：依賴 US1（可與 US3 平行）。
- **US4**：依賴 US2、US5。
- **US6**：依賴 US2（亮點依賴 US1）。
- **US7**：依賴 US3、US5。

### Within Each User Story

- 測試先寫並確認失敗 → 後端 models → 外掛／service → router → 前端 service → 元件 → 接線 → i18n → 全量關卡。
- 每個 story 結束時執行完整前後端測試與 `lint-imports`／`ng lint`。

### Parallel Opportunities

- Phase 1：T001–T006 全部平行。
- Phase 2：T008、T010、T011、T013、T014、T015、T017、T019 平行；T021–T025 平行。
- US1：T027／T028 平行；T042／T043／T044 平行。
- US2：T048／T049／T050 平行；T059／T060 平行。
- US3：T067–T071 平行；T078–T083 平行。
- US5：T088–T091 平行；T096–T098 平行。
- US3 與 US5 可由兩人平行推進。
- US6：T111／T112／T113 平行。

---

## Parallel Example: User Story 3

```bash
# 測試先行（全部平行）
Task: "test_frames_plugin.py"            # T067
Task: "test_match_events_endpoint.py"    # T068
Task: "test_dashboard_sections_endpoint.py + test_member_activities_endpoint.py"  # T069
Task: "test_frames_flow.py"              # T070
Task: "match_filters_query sport 參數測試"  # T071

# 後端實作（序列）：T072 → T073 → T074 → T075 → T076 → T077

# 前端（平行）：T078、T079、T080、T081、T082、T083 → T084 → T085 → T086 → T087
```

---

## Implementation Strategy

### MVP First（US1）

1. Phase 1 → Phase 2（外掛基礎，不碰羽球行為，既有測試全綠）。
2. Phase 3：把羽球搬進外掛、核心骨架化。**停下來驗證**：既有測試全綠、spec diff 只含允許變更、邊界關卡通過、手動比對零差異。
3. 可在此合併：對使用者無感，但架構已就位。

### Incremental Delivery

1. US2：開團選活動（桌球、匹克球、網球搶十立即可用）→ 驗證 → 可合併。
2. US3：局數制（撞球、飛鏢、桌遊、電競）→ 驗證 → 可合併。
3. US5：通用與平手 → US4：自訂活動 → US6：篩選與分享 → US7：可擴充性關卡 → Polish。
4. 每個 story 都是加法：後一個 story 不修改前一個 story 的核心檔（US3 與 US5 各自新增函式與路由，不改既有函式簽名）。

### 提交策略（供 SC-005 驗證）

- `frames` 與 `generic` 各自的外掛實作（外掛目錄、migration 中對應區段已於 T010 建立、i18n、registry／`register_all` 各一行、測試）收斂成可獨立檢視的提交群，讓 T118 的範圍檢查對它們回空。
- 核心變更（`/events`、`/finish`、`/undo`、`sport` 篩選、`dashboard-sections`）在本功能內屬「建立擴充點」，以獨立提交標示，不混入外掛提交。

---

## Notes

- [P] tasks = 不同檔案、無未完成依賴。
- 每個 story 結束都要跑完整關卡；US1 之後任何一次既有測試斷言的改動都是紅燈。
- 核心檔（`schedule/service.py`、`group/service.py`、`member/service.py`）是多個 story 的共用熱點：同一時間只讓一個 story 動它，其餘 story 先做外掛目錄與前端。
- `docs/` 任務直接改主 checkout（gitignore）。
- 憲章 1.1.0 已於 plan 階段修訂完成，不需再執行 `/speckit-constitution`。
