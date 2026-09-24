# Research: 多活動支援與比賽類型外掛基礎（043）

**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md) | **Date**: 2026-09-24

本文件記錄 `/speckit-plan` 階段對程式碼實際盤查後做出的技術決策。每一條都以「零變更承諾」（FR-030～FR-032：既有羽球行為與測試不改）為最高優先，其次是「新增類型不改核心」（FR-033～FR-034a）。

盤查中影響最大的既有事實（後續決策反覆引用）：

- **F1 測試釘住 ORM 名稱**：10 個測試檔從 `app.domains.schedule.models` 匯入 `ScoreEvent`／`ScoreServeRecord`／`ShotPlacementRecord` 並直接建構；斷言 `(side, delta, score_a, score_b, source)` 與 `record.score_event_id`。沒有任何測試用 raw SQL 碰這三張表。
- **F2 測試釘住 `publish` 路徑**：3 個測試檔 `monkeypatch.setattr("app.domains.schedule.service.publish", …)` 並斷言 `match.scoreUpdated` 的 `serve` 內容與 `standings.updated`。
- **F3 測試釘住回應形狀**：`test_member_match_dashboard_endpoint.py` 以 `set(body) == set(EMPTY)` 釘住儀表板回應的頂層欄位集合、23 個指標鍵與順序；比較與基準端點同樣釘死；`test_member_matchups.py:300-320` 要求四個 records／dashboard 路由的查詢參數集合完全相同。
- **F4 `match_mode` 無所不在**：210 個測試檔、402 次；95 個檔以 ORM kwarg `Group(match_mode=…)` 建構、130 個檔在 JSON 送 `"match_mode"`；4 處直接斷言其值。
- **F5 測試 DB 每次 `TRUNCATE … members, groups … CASCADE`**：任何有 FK 指向 `members` 的表都會被連帶清空；且每次測試 session 都 `alembic downgrade base` → `upgrade head`，新 migration 必須有可用的 downgrade。
- **F6 新增 NOT NULL 欄位必須有 `server_default`**：3 個測試用 raw SQL `INSERT INTO matches (…)` 與 `roster_entries`；84 個單元測試檔直接建構 `Group(...)`、15 個建構 `Match(...)`，因此也需要 Python 端預設值。
- **F7 私有函式被測試直接匯入**：`_compute_station`（11）、`_initialize_serve_state`（6）、`_advance_serve_state_and_snapshot`（5）、`_serve_before_point`、`_remove_last_shot_placement_record`、`_build_serve_station` 等，全部從 `app.domains.schedule.service` 匯入。規格 US1 明文允許「搬移路徑等結構性調整」。
- **F8 前端 spec 皆為同步**：詳細頁、儀表板、控制板的 spec 直接讀 `componentInstance` 成員、`querySelector('app-…')`，不 await；程式中沒有任何動態元件渲染、沒有路徑別名、沒有 import 邊界規則、沒有 `.github/workflows`。
- **F9 `apply_score_delta` 是單一交錯交易**：核心步驟（原子 UPDATE、`last_activity_at`、ScoreEvent、commit、`match_wins`、`_advance_after_terminal`、publish）與羽球步驟（+1 換發快照、−1 刪落點與依比分還原發球）在同一個 commit 前交錯執行；發球 payload 同時放在 `ScoreMutationResult.serve` 與 `match.scoreUpdated` 訊息裡。
- **F10 平手目前無法表達**：`MatchRecordSummary.winner_team: Literal["A","B"]` 非空；所有勝負統計把「不是勝方」當敗方或當 B 勝；`completed` 的比賽一律有 `winner_team`，`abandoned` 一律為 NULL。

---

## Decision 1：脊椎就是既有的 `score_events`，不改表名、不改類別名

**Decision**：`score_events` 表與 `ScoreEvent` ORM 類別保留原名與原路徑（`app.domains.schedule.models`），作為「比賽事件脊椎」；新增欄位 `kind String(24) NOT NULL server_default 'point'`；`side` 改為可空；`delta` 允許任意整數（含 0）。`source` 欄位即規格所稱「操作者」（記錄操作來源：控制板／管理頁／全部場地／計分板／復原）。既有資料回填 `kind='point'`。

**Rationale**：F1 讓改名毫無收益只有風險（索引名、`scripts/reset_data.py`、10 個測試檔的匯入）；規格要的是「脊椎語意」而非表名。`kind` 讓非得分事件（換局、局內得分）能在同一序列占序號（clarify Q1、FR-013）。`side` 可空是因為換節這類事件沒有隊別；`delta=0` 表示「不改變場級比分」。

**Alternatives considered**：(a) 改名為 `match_events` 並在 models 留 alias——`op.rename_table` 在本專案沒有先例，索引與 reset 腳本要跟著改，測試斷言雖不變但風險純增；(b) 另建一張 `match_events` 而 `score_events` 只存得分——兩張表要維持全域序號，違反「單一順序」的目的。

**Impact on core readers**：`group/service.py` 的 `_record_completeness`、`_to_raw_events`、`_serve_before_point`（搬進外掛）、−1 的依比分還原，全部改為只看 `kind == 'point'` 的事件。這是脊椎語意（不是羽球分支），且對既有資料（全部 `point`）結果相同。

## Decision 2：場級比分永遠是脊椎上的 `point` 事件；局數制的「局」就是一個 `point`

**Decision**：任何類型「贏一場」的計數單位都寫成脊椎 `point` 事件的 `delta`：羽球 +1、通用 +N（N ∈ 加分級距）、局數制「贏一局」+1。因此局數制的「先贏幾局」就是通用參數 `target_score`（`win_by=1`、`cap=None`），核心的達標判定不需要任何局數制專用程式。局內逐分（clarify Q1 選 B）是局數制外掛自己的事件種類 `frames.frame_point`（脊椎 `delta=0`，細節在外掛表），局結束時由外掛寫一筆 `point`（+1 給勝方）並在外掛表記下該局比分與結束方式。

**Rationale**：讓排行榜、我的團場數、走勢、分享圖卡、`match_wins` 這些核心功能對所有類型只認 `point`，不必知道「局」的存在（FR-020）。

**Alternatives considered**：把局內得分也寫成 `point` 並加「層級」欄位——核心的比分投影（`matches.score_a/b`）會失去單一語意，所有讀者都要過濾層級。

## Decision 3：達標判定改為參數化的通用規則，放在核心 `app/sports/scoring.py`

**Decision**：`match_wins(x, y, *, target, win_by, cap)` = `(cap is not None and x >= cap) or (x >= target and x - y >= win_by)`。`schedule/service.py:match_wins` 與 `group/match_stats.py:_wins` 都改為呼叫它。手動結束模式（`end_mode='manual'`）不呼叫達標判定。

**Rationale**：以 `target=21, win_by=2, cap=30` 代入與現行公式完全等價（含 `deuce_threshold` 不參與運算的既有事實），可用既有 `test_match_wins.py` 的表格直接驗證零變更。局數制 `win_by=1`、桌球 `cap=None` 都只是參數。

**Alternatives considered**：讓每個外掛各自實作勝負規則——三個類型會寫出三份幾乎相同的程式；規格 FR-016 已把規則定義為通用參數。外掛介面仍保留 `match_wins` 覆寫點供日後特殊規則使用（預設委派核心）。

## Decision 4：平手以 `winner_team='D'` 表示，不用 NULL

**Decision**：`matches.winner_team` 值域 `A|B|D|NULL`；`completed` 的比賽一律非空（`D`＝平手），`abandoned` 一律 NULL。`MatchRecordSummary.winner_team` 型別放寬為 `Literal["A","B","D"]`。所有勝負彙總（`build_group_standings`、`build_group_final_standings`、`build_group_match_records`、`member/service.py` 的 `won`、`_sample_from`）顯式處理 `D`：各回應在既有 `wins/losses` 之外**新增** `draws` 欄位（預設 0）。

**Rationale**：F10 指出「NULL＝未完賽」是全系統的既有不變量（憲章 III「已捨棄不計入」）；用 NULL 表達平手會與放棄比賽混淆，且 `get_completed_match_or_404` 之類的守門邏輯全要重寫。`D` 讓「completed ⇒ winner_team 非空」的不變量保持成立。

**Alternatives considered**：NULL＋`is_draw` 欄位——多一個欄位仍要處理 NULL 的雙重語意。

**Test impact**：排行榜與紀錄回應多 `draws` 欄位屬新增；F3 釘死形狀的三個端點（儀表板／比較／基準）不在此列。羽球團永遠 `draws=0`。

## Decision 5：內建活動目錄放在程式碼；資料表只存會員自訂活動

**Decision**：不建 `sports` 種子表。內建活動以 `app/sports/catalog.py` 的常數宣告（key、類型、預設參數、允許人數、名詞 key、圖示 key），前端從 `GET /sports` 取得。會員自訂活動存在新表 `member_sports`（FK `members` ON DELETE CASCADE）。團上記錄 `sport_key`（內建 key、`custom`、`other`）、`custom_sport_id`（FK `member_sports` ON DELETE SET NULL）、`sport_name`（自訂／其他的名稱快照；內建為 NULL）。

**Rationale**：F5：若內建與自訂同表且自訂列有 FK 到 `members`，測試 teardown 的 `TRUNCATE members CASCADE` 會把內建列一起清掉，每個測試都得重新種子。憲章 VIII 也要求顯示文字進語系檔：內建活動的名稱本來就必須是 i18n key，不該存 DB。刪除自訂活動時既有團靠 `sport_name` 快照維持顯示（US4 情境 4）。

**Alternatives considered**：(a) 同一張 `sports` 表＋固定 UUID 種子——F5 的 TRUNCATE 問題無解，除非把 `created_by` 去掉 FK（失去完整性）；(b) 把 teardown 改成不 TRUNCATE `sports`——內建列不動，但自訂列會跨測試殘留。日後管理後台若要在 DB 維護內建目錄，可在該功能中把常數搬成表，`sport_key` 的語意不變。

## Decision 6：`team_size` 為主、`match_mode` 保留為相容別名（本期不刪）

**Decision**：`groups` 新增 `team_size SmallInteger NOT NULL server_default 1`，migration 由 `match_mode` 回填（singles→1、doubles→2）。`match_mode` 欄位保留，模型層以 validator 維持兩者一致：建構或修改時任一方給值即推導另一方，兩者都給則必須一致。API 的建立／編輯請求同時接受 `team_size` 與 `match_mode`（至少一個）；所有回應同時輸出兩者。核心排程邏輯改讀 `team_size`（`team_size == 1` 取代 `match_mode == "singles"`）。

**Rationale**：F4：刪除 `match_mode` 會讓 95 個單元測試檔的 `Group(match_mode=…)` 與 130 個契約測試的 JSON 全部失效，遠超「搬移路徑」的允許範圍。規格 FR-010 要求 `team_size` 取代單雙打「作為設定」，相容別名不影響此要求。

**Alternatives considered**：只在 API 層做別名、DB 只留 `team_size`——ORM kwarg `match_mode=` 仍會壞（84 個檔直接建構 `Group`）。

**Sunset**：第二期（每隊 3 人以上）時 `match_mode` 無法表達 `team_size ≥ 3`，屆時移除別名並一次調整測試。

## Decision 7：通用參數落在 `groups`／`matches`，類型專屬參數放 `type_params JSONB`

**Decision**：`groups` 與 `matches` 各新增：`sport_key`、`type_key`、`sport_name`、`end_mode`（`target|manual`，預設 `target`）、`win_by`（預設 2）、`allow_draw`（預設 false）、`score_steps JSONB`（預設 `[1]`）、`type_params JSONB`（預設 `{}`）；`cap_score` 改為可空；`custom_sport_id` 只在 `groups`。`matches` 在 `create_match_with_participants` 時一併快照（沿用既有 target／deuce／cap／detailed_scoring 快照）。`type_params` 的 schema 由各類型外掛的 pydantic model 定義並驗證（`params_schema()`），核心只負責存取與快照。

**Rationale**：憲章 III 要求設定快照到比賽；既有機制已在。通用參數是所有類型共用的固定欄位（可索引、可驗證）；類型專屬參數（局數制的 `frame_scoring_enabled`／`frame_target`／`frame_win_by`、隔網回合制的 `modules`）數量與形狀依類型而異，JSONB 是「設定」而非「事件」，符合規劃文件的取捨。所有新 NOT NULL 欄位皆有 `server_default`（F6），既有資料回填羽球值。

**Alternatives considered**：每個類型各自的參數表——每加一種類型就要動 `groups` 的 join；參數只在開團與快照時讀寫，不需要查詢能力。

## Decision 8：外掛在核心交易中以「掛鉤回傳值」參與，永不自行 publish

**Decision**：`apply_score_delta` 重構為固定骨架：原子 UPDATE → `last_activity_at` → 寫脊椎事件 → `plugin.on_spine_event(session, ctx)` → commit → 達標判定 → 終局處理 → publish。外掛掛鉤回傳 `SpineEffect(live_payload: dict | None, extra_publish: list[…] | None)`；核心把 `live_payload` 放進 `ScoreMutationResult.sport_state` 與 `match.scoreUpdated` 訊息；羽球外掛的 `live_payload` 就是既有 `serve` 站位（核心同時維持 `serve` 這個既有鍵名以達零變更）。外掛程式碼 **MUST NOT** 匯入 `app.core.realtime.publish`。

**Rationale**：F2：三個測試 monkeypatch `app.domains.schedule.service.publish`，若外掛自己 publish，這些 mock 看不到訊息、測試失敗；F9：換發快照必須在同一個 commit 內完成，掛鉤在 commit 前執行即可。

**Alternatives considered**：讓外掛拿到 publisher 介面——需要把 publish 改成可注入物件，會動到 F2 釘住的模組屬性。

## Decision 9：羽球規則搬進 `app/sports/types/net_rally/`，測試只改匯入路徑

**Decision**：`_compute_station`、`_team_station`、`_initialize_serve_state`、`_advance_serve_state_and_snapshot`、`_build_serve_station`、`_serve_before_point`、`_remove_last_shot_placement_record`、`attach_shot_placement` 的幾何與判定部分、`_SINGLES_SIDELINE_INSET` 等常數，全部搬到 `app/sports/types/net_rally/{serve,placement}.py`，函式名不變。`schedule/service.py` **不得**再 re-export 這些名稱（否則核心匯入外掛，違反 FR-034a）。F7 列出的測試檔改匯入路徑（規格 US1 允許）。`ScoreServeRecord`／`ShotPlacementRecord` 的 ORM 類別**留在** `app.domains.schedule.models`（F1），但由 `net_rally` 外掛宣告擁有（`tables()`），核心不再直接查詢它們——`group/service.py` 中 `_to_serve_snapshots`／`_to_placements`／`_build_derived_stats` 對這兩張表的查詢改由外掛的 `load_stat_inputs()` 提供。

**Rationale**：規格 FR-015、FR-034 要求核心不讀外掛表、不含羽球邏輯；F7 的私有匯入是唯一阻礙，而規格已明文放行路徑搬移。ORM 類別留在原模組是 F1 與「零斷言修改」的必要妥協，在 data-model.md 註明擁有權由外掛宣告、核心禁止查詢（由 import-linter 契約強制：核心模組不得匯入這兩個類別名？——做不到細到類別；改以「核心不得 `select(ScoreServeRecord|ShotPlacementRecord)`」的 grep 契約測試守住，見 Decision 15）。

**Alternatives considered**：把兩張表的 ORM 也搬進外掛並在 `schedule.models` 留 alias——alias 本身就是核心匯入外掛。

## Decision 10：`match_stats.py` 拆成「核心純函式」與「隔網回合制純函式」

**Decision**：`group/match_stats.py` 中只依 `point` 事件的部分（`effective_points`、`momentum_stats`、`tempo_stats`、`clutch_stats`、`_wins`→Decision 3）留在核心；依發球快照與落點的部分（`serve_stats`、`player_landings`、`landing_distribution`、`ending_stats`、`_receiver`、`EndingType` 複本）搬到 `app/sports/types/net_rally/stats.py`。測試 `test_match_stats.py` 改匯入路徑；`match_stats.EndingType is schedule.schemas.EndingType` 的釘點改為 `net_rally.stats.EndingType is schedule.schemas.EndingType`。`EndingType` 與 `RecordShotPlacementRequest` **留在核心** `schedule/schemas.py`：落點端點的 router 與請求 schema 在核心（三個授權面共用），若把型別搬進外掛，核心 schema 就得匯入外掛而違反 Decision 15；外掛以匯入方式重用（外掛→核心方向允許）。這是核心中僅存的羽球語彙，屬「端點合約」而非規則邏輯（tasks T029、T120）。

**Rationale**：規格 FR-025：隔網回合制的非羽球活動也要 endgame／deuce／match point 等只靠比分的指標，這些正是核心該保留的；發球與落點是模組。

## Decision 11：儀表板指標目錄改由類型宣告；既有 23 項成為 `net_rally` 的目錄，回應形狀零變更

**Decision**：`player_dashboard.aggregate()` 改為接受 `metric_specs: Sequence[MetricSpecView]` 參數（預設值＝隔網回合制目錄，維持既有呼叫相容）；`_METRICS` 的 23 項搬到 `net_rally/dashboard.py`。`insights.py` 在匯入時綁定目錄的做法改為函式參數注入。既有端點 `GET /members/me/match-dashboard`（與 `/members/{id}/…`）在 `sport` 為隔網回合制活動時回應**完全不變**（F3）。非隔網類型的儀表板不走這個端點，走 Decision 12 的區塊清單端點。

**Rationale**：F3 釘死了 23 個鍵與頂層欄位集合，任何加欄位都會被 `set(body) == set(EMPTY)` 抓到。把目錄變成參數是最小改動。

## Decision 12：區塊清單（manifest）用新端點承載；既有詳細頁回應以「新增欄位」方式帶 `sport` 與 `sections`

**Decision**：
- 比賽詳細頁：既有三個 `GET …/match-records/{id}` 端點的 `MatchRecordDetailResponse` **新增** `sport: SportSummary` 與 `sections: list[Section]` 兩個欄位（F3 沒有釘住此回應的形狀）。隔網回合制的 `sections` 為 `[{kind: "net_rally.match_detail", data: null}]`——`data: null` 表示「用本回應的頂層欄位」，既有欄位對羽球完全不變；其他類型的專屬欄位（`serve_stats`、`landing_distribution`…）為 `null`／空，內容全在 `sections`。
- 會員儀表板：新增 `GET /members/me/dashboard-sections` 與 `GET /members/{member_id}/dashboard-sections`，查詢參數與 `match_filters_query` 完全相同再加 `sport`（必填）；回應 `{sport, type_key, sections}`。隔網回合制回 `[{kind: "net_rally.dashboard", data: null}]`（前端該區塊元件自行呼叫既有 `match-dashboard` 端點），其餘類型的 `data` 直接內嵌。
- 活動頁籤：新增 `GET /members/me/activities`（與 `/members/{member_id}/activities`）回傳會員有紀錄的活動清單（`sport_key`、`custom_sport_id`、`name`、`type_key`、`match_count`）。
- 四個 records／dashboard 路由的 `match_filters_query` 新增 `sport` 參數（F3 要求四者一致）。

**Rationale**：規格 FR-021 要「伺服器決定區塊」，F3 禁止改儀表板回應形狀，因此新端點是唯一路徑。詳細頁回應沒有形狀釘點，新增欄位即可，且讓前端一次呼叫就拿到全部。

**Alternatives considered**：把羽球詳細頁的既有欄位整包搬進 `sections[0].data`——前端四個宿主頁面與 54 個 dialog spec 都讀頂層欄位，會全面破壞零變更。

## Decision 13：控制動作端點——`/score` 放寬 `delta`，新增 `/events`、`/finish`、`/undo`

**Decision**：三個授權面（token、管理頁、全部場地）各自新增同名端點，沿用既有的 `_can_score_by_token`／`require_admin`／all-courts token 三套授權：
- `POST …/score`：`delta` 由 `Literal[1,-1]` 放寬為 `int`，服務層驗證 `abs(delta) ∈ score_steps`（羽球 `[1]` → 行為與今日完全相同）。
- `POST …/events`：`{kind, payload}`；核心查外掛宣告的 `event_schemas()`，未宣告即 `422 EVENT_KIND_NOT_ALLOWED`；外掛負責寫自己的表並可回傳要附加的脊椎 `point`（例如局內達標時自動結束該局）。
- `POST …/finish`：手動結束模式專用，`{}`；核心依比分決定 `A|B|D`，`allow_draw=false` 且同分 → `409 DRAW_NOT_ALLOWED`；`end_mode='target'` → `409 FINISH_NOT_AVAILABLE`。
- `POST …/undo`：取消最後一筆脊椎事件（任何 kind）；核心刪除脊椎列與（cascade）外掛細節列後呼叫 `plugin.after_undo()` 重算投影（局數制回到該局結束前的比分）。隔網回合制本期不使用 `/undo`（既有 −1 語意不變，控制板不顯示新按鈕）。
- 既有 `POST …/end`（提前結束＝放棄）**不變**，對所有類型可用（clarify Q2、FR-017a）。

**Rationale**：既有 `/score` 與 `/end` 路徑、schema、測試零變更；新動作用新路徑，授權模型沿用（憲章 IV：無需驗證的畫面不得有管理員專屬操作——這四個動作都是計分員操作，與 `/score` 同級）。

**Undo 為刪除而非負事件**：既有羽球的 −1 是「新增一筆 delta −1 事件」（時間軸會顯示），本期保留；`/undo` 對其他類型採「刪除最後一筆」是因為局內得分與局結束的組合用負事件表達會讓外掛表的還原規則複雜化（clarify Q1）。兩種語意並存但各自封閉在不同類型，資料模型章節註明。

## Decision 14：前端採「宿主＋類型模組」的絞殺者模式；羽球元件整個搬進 `net-rally` 模組，spec 只改匯入路徑

**Decision**：
- 新增 `src/app/sports/`：`registry.ts`（`typeKey → () => import(...)` 的載入表＋`SportTypeRegistry` 服務：`resolve()` 非同步、`peek()` 同步）、`section-outlet/`（依 `kind` 找元件，找不到用 `generic-sections/` 的通用退路）、`generic-sections/`（`metric_grid`、`stat_table`、`score_timeline`、`text_note`）、`types/{net-rally,frames,generic}/`。
- 類型模組介面 `SportTypeModule` 提供**整面元件**（surfaces）：`scoreboard`、`controlPanel`、`allCourtsBlock`、`courtControl`、`createFormFields`、`shareHighlights`，以及 `sectionKinds: Record<kind, Component>`。
- 既有 `ScoreboardComponent`、`ControlPanelComponent`、`AllCourtsCourtBlockComponent`、`CourtControlComponent`、`MatchRecordDetailDialogComponent`、`PlayerDashboardComponent`、`features/shot-placement/*`、`core/court-diagram`、`core/match-share-card/share-card-highlights.ts` **整個搬**到 `sports/types/net-rally/` 下，類別名不變，內部邏輯不變；它們的 spec 只改相對匯入路徑。路由與宿主頁面改為掛新的宿主元件（`ScoreboardHostComponent` 等），宿主先取一次狀態得知 `type_key`，再 `resolve()` 類型模組並渲染其整面元件（可選輸入 `initialState` 避免二次請求；未給則元件自行取狀態，與今日相同）。
- 隔網回合制的 `sections` 由 `net_rally.match_detail`／`net_rally.dashboard` 兩個 kind 對應到搬過去的 dialog 與 dashboard 元件；局數制與通用的區塊由 `generic-sections` 與各自模組的專屬區塊渲染。
- **測試同步性**：新增 vitest `setupFiles`（`src/test-setup.ts`，在 `angular.json` 的 test 目標註冊），在測試啟動時同步預載 `net-rally` 模組進 registry，讓宿主在既有 spec 中同步渲染。允許的 spec 調整＝匯入路徑、TestBed providers／mock 物件補新方法、setup 檔；`expect` 斷言不動（規格 US1 情境 3 的解讀，寫入 plan 的 Constitution Check）。

**Rationale**：F8：四個計分宿主把 `plusPressed`／picker／match-point 邏輯各複製一份且 spec 直接呼叫這些成員，若在本期把它們拆成「通用殼＋發球區塊」，54＋38＋29＋17 個測試的斷言都會失效。整面搬移把「不改行為」變成可機械驗證的事（diff 只有路徑）。細粒度拆分留給日後獨立功能。

**Alternatives considered**：(a) 只用 manifest、宿主頁面在 Phase 0 就殼化——與 F8 衝突；(b) 用 Angular `@defer`——`@defer` 綁在模板上，無法依執行期的 `type_key` 選模組。

## Decision 15：邊界檢查——後端 `import-linter`、前端 eslint `no-restricted-imports`、外加兩個契約測試

**Decision**：
- 後端新增 dev 依賴 `import-linter`，`pyproject.toml` `[tool.importlinter]` 三個契約：(1) forbidden：`app.domains`、`app.core`、`app.sports.{registry,plugin,presentation,scoring,catalog}`、`app.system_config` 不得匯入 `app.sports.types`；(2) independence：`app.sports.types.net_rally`、`.frames`、`.generic` 互不匯入；(3) forbidden：`app.sports.types` 不得匯入 `app.core.realtime`。允許例外只有 `app.main`（組裝根，呼叫 `register_all()`）、`alembic.env`（匯入外掛 models 供 metadata）、`tests`。指令 `lint-imports` 加入既有品質關卡指令（README／docs 的 `ruff check` 旁）。
- 前端 `eslint.config.js` 以 `files` 覆寫加 `no-restricted-imports`：`src/app/{core,features,shared}/**` 禁止 `**/sports/types/**`；`src/app/sports/types/<a>/**` 禁止 `**/sports/types/<b>/**`（每型一條）；`src/app/sports/{registry,section-outlet,generic-sections}/**` 禁止 `**/sports/types/**`。唯一例外：`src/app/sports/registry.ts` 的動態 `import()`（用 eslint 行內 disable 並註明）與 `src/test-setup.ts`。不需新套件。
- 契約測試：(a) 後端 `tests/unit/sports/test_plugin_contracts.py`：每個註冊類型的 `event_schemas()`、`params_schema()`、`dashboard_sections()` 回傳的 kind 都在該類型宣告的 `section_kinds` 內；(b) 前端 `src/app/sports/section-outlet/section-outlet.contract.spec.ts`：讀取後端匯出的 kind 清單（`apps/api/app/sports/section-kinds.json`，由後端測試同步產生並提交）逐一確認 registry 有元件或落入通用退路。
- 補一個 grep 型契約測試守住 Decision 9 的妥協：核心目錄不得出現 `select(ScoreServeRecord` 或 `select(ShotPlacementRecord`。

**Rationale**：規格 FR-034a 與 clarify Q3 要求自動化強制；專案目前沒有任何 import 規則（F8），`import-linter` 是 Python 生態最直接的工具，eslint 內建規則不需新依賴。專案尚無 CI（docs/cicd-pipeline.md 只是規劃），所以「納入 CI 關卡」在本期落實為：寫進品質關卡指令清單，並在 docs/cicd-pipeline.md 的 workflow 骨架加入這兩個步驟。

## Decision 16：建立表單保持單頁，「選活動」為表單第一個區塊，預設羽球

**Decision**：`create-group` 維持單一 reactive form，不做多步驟精靈；在最上方加「活動」區塊（內建活動卡片＋「我的自訂」＋「其他／自訂」），預設選中羽球，因此表單初始狀態（singles、21pt）與今日相同，17 個 spec 不變。選定活動後：`team_size` 選項、計分區塊（隔網回合制沿用既有 `21pt/15pt/custom` 下拉，但預設與選項來自目錄；局數制與通用改渲染該類型模組的 `createFormFields`）、名詞、預設團名佔位文字隨之切換。送出時 payload 新增 `sport`、`team_size`、`end_mode`、`win_by`、`cap_score`（可空）、`allow_draw`、`score_steps`、`type_params`；`match_mode` 仍一併送出（Decision 6）。管理頁的編輯表單同步支援新參數但不可改活動（FR-007）。

**Rationale**：規格說「第一步」，單頁表單中的第一個區塊在使用者流程上即為第一步，且避免重寫表單與 42＋17 個 spec。

## Decision 17：`GET /sports` 一次給前端目錄、類型描述與參數 schema

**Decision**：回應含 `types[]`（`type_key`、支援的 `team_size` 範圍、`modules`、`params_schema`（JSON Schema，由外掛 pydantic model 產生）、`section_kinds`）、`builtin[]`（key、`type_key`、`name_key`、`icon`、`team_size_options`、預設通用參數、預設 `type_params`、名詞 keys）、`custom[]`（登入會員自己的自訂活動）。`optional_member` 授權。

**Rationale**：讓前端不複製任何常數（規格 FR-021 的精神），表單驗證範圍與後端一致。

## Decision 18：排點時間預估改由外掛 `estimate_minutes()` 提供

**Decision**：`_FALLBACK_MINUTES_PER_TARGET_POINT = 0.6` 搬進 `net_rally` 的 `estimate_minutes(params)`（結果與今日相同）；局數制 `4 分鐘 × target_score`（局內比分啟用時 `0.5 × frame_target × target_score`）；通用達標 `0.6 × target`、手動 15 分鐘。這些數值是 plan 層級假設，寫進 data-model 供日後調整。

## Decision 19：局數制外掛的表與即時狀態

**Decision**：兩張表 `frames_frame_results`（`score_event_id` PK/FK→`score_events` CASCADE、`match_id`、`frame_no`、`winner_team`、`score_a`、`score_b`、`ended_by: target|manual`）與 `frames_frame_points`（`score_event_id` PK/FK、`match_id`、`frame_no`、`side`、`delta`、`frame_score_a`、`frame_score_b`）。即時狀態（`frame_no`、本局比分、是否啟用局內比分、`frame_target`）由外掛 `live_state()` 從最後一筆 `frame_result` 之後的 `frame_points` 推導，不另存投影表。

**Rationale**：資料量小（一場數十筆），推導成本可忽略；少一張需要與事件保持一致的投影表，`/undo` 也只需刪脊椎列（cascade 帶走細節）。

## Decision 20：類型模組的前端程式獨立 chunk 由 registry 的動態 `import()` 保證

**Decision**：`registry.ts` 的載入表是唯一引用 `sports/types/*` 的核心檔案，且只用動態 `import()`；Angular application builder 會為每個動態匯入產生獨立 chunk。驗收方式：`ng build` 後 `dist/` 中存在 `frames-*.js` 與 `generic-*.js` chunk，且 `main-*.js` 不含 `frames.frame_list` 字串（quickstart 提供指令）。

## Decision 21：憲章修訂範圍

**Decision**：於本 plan 完成後執行 `/speckit-constitution`，MINOR 版本 1.0.0 → 1.1.0：(1) 專案定位改為「回合制對戰活動揪團與即時計分系統」；(2) 原則 III「只有達到目標分數自然結束才產生 MatchResult」改為「只有依該團所選活動的結束規則完賽（達標，或手動結束模式下由計分員宣告結束並記錄結果）才產生 MatchResult；放棄比賽與其他中止情境一律 abandoned」；(3) 新增原則 XII「比賽類型外掛邊界」：核心不得依特定活動分支、不得匯入類型模組、不得查詢外掛表；新增類型 MUST 附規則／統計／區塊測試；邊界由 import-linter 與 eslint 規則強制並列為品質關卡。

**Rationale**：Constitution Check 對原則 III 的現行文字是實質衝突（手動結束記錄結果），必須以修訂而非例外處理。
