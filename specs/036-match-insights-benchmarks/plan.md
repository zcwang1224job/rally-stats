# Implementation Plan: 對戰紀錄洞察（優缺點摘要、搭檔與對手戰績、比較基準）

**Branch**: `feature/match-insights-benchmarks` | **Date**: 2026-09-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/036-match-insights-benchmarks/spec.md`，交叉比對 `/apps/api/app/domains/member/player_dashboard.py`（034／035 的 `_METRICS`、`build_sample()`、`aggregate()`、`_metric_value()`）、`/apps/api/app/domains/member/service.py`（`_filtered_member_matches()`、`build_member_match_records()` 的 `opponent_tallies`、`_dashboard_sample()`、`build_member_match_dashboard()`、`_resolve_viewable_member()`、`get_my_groups()`）、`/apps/api/app/domains/member/router.py`（`match_filters_query`）、`/apps/api/app/domains/group/service.py`（`verify_ever_group_member()`、`load_match_stat_inputs()`、`_completed_matches_query()`、`build_group_final_standings()`）、`/apps/api/app/domains/group/match_stats.py`、`/apps/api/app/domains/roster/models.py`（`RosterEntry.member_id`）、`/apps/web/src/app/features/member/match-history/`、`/apps/web/src/app/core/player-dashboard/`、`/apps/web/src/app/features/friends/friend-match-records/`

## Summary

在既有的個人對戰紀錄頁與好友戰績頁上，補上「結論、對象、基準」三件事，全部由既有紀錄在查看當下推導——**無 migration、無新資料表、無新套件**。

1. **優缺點摘要（US1）**：新純函式 `member/insights.py` 讀 034 的 `MatchSample` 與 `aggregate()` 結果，依固定規則挑出強項／待加強／最近變化／對戰組合，回傳「規則代碼＋數字」，句子在前端語系檔。搭在既有儀表板回應上（多一個 `insights` 欄位），因此自動跟隨篩選、自動出現在好友頁。`aggregate()` 本體不動。
2. **搭檔／對手戰績（US2）**：新純函式 `member/matchups.py` 以球員身分鍵（`m:<member_id>`／`r:<roster_entry_id>`）取代既有的暱稱字串彙總，新增平均分差、搭檔列表與重點摘要。點擊某一列＝兩個新的精確篩選參數，加在對戰紀錄與儀表板**共用**的 dependency 上，整頁一起縮小。
3. **團內比較（US3）**：新端點。把 `_dashboard_sample()` 拆成「每場推導一次」與「每位球員取樣一次」，於是同一套函式可為該團每位球員（含訪客名單球員）算出同一組指標；新純函式 `member/group_benchmark.py` 算平均、名次、人數。**回應 schema 沒有任何可放他人資料的欄位**——匿名由結構保證。回應另帶一份已合併團內來源的摘要。
4. **與好友比較（US4）**：新端點，沿用 023 的授權檢查；回傳雙方 23 項數值、較佳的一方與交手紀錄。

另含一項**前置修正**：`verify_ever_group_member()` 對「離團後重新加入」的會員會拋例外（已查證），而團內比較重用這個檢查。

## Technical Context

**Language/Version**：延續既有（後端 Python 3.12+，FastAPI + SQLAlchemy 2.0 async；前端 Angular 20 + TypeScript strict mode）。

**Primary Dependencies**：沿用既有堆疊，**不新增任何第三方套件**。後端的執行緒卸載用標準函式庫的 `asyncio.to_thread()`（專案已有此用法）。

**Storage**：PostgreSQL，**唯讀**。無 migration、無新欄位、無新索引——讀取沿用 034 的批次載入（`load_match_stat_inputs()`，每 500 場 3 個查詢）與既有的 `match_id`／`roster_entry_id` 索引。「上次選定的比較團」存在瀏覽器 `localStorage`。

**Testing**：
- 後端：pytest。
  - `tests/unit/domains/member/test_matchups.py`（新，無資料庫）——`m:`／`r:` 鍵的合併與區分（同人不同暱稱、不同人同暱稱、多位 `"Deleted User"`）、顯示暱稱取最近一場、雙打兩位對手各計一次、單打不進搭檔、同一人兩種角色、`avg_margin` 的正負與四捨五入、`low_sample`、四個重點摘要的門檻與三層 tiebreak、`head_to_head` 的兩組與 `None`。
  - `tests/unit/domains/member/test_insights.py`（新，無資料庫）——每條規則的輕微／明顯邊界（剛好達門檻、差一點）、最低樣本、FR-012 的三個排除指標、成對指標只留一句（幅度相同留 weakness）、同一指標 benchmark 優先於 self、四層排序、`recent` 至少一句進步、`dominant_error` 過半才帶出、三種 `status`、各清單上限、**輸入相同則輸出相同**、`params` 與輸入的 `MetricValue` 逐位相等。
  - `tests/unit/domains/member/test_group_benchmark.py`（新，無資料庫）——5 場門檻、3 人門檻、四種 `status` 與判定順序、`higher`／`lower` 兩種方向的名次、並列跳號、與 `_assign_standard_competition_ranks()` 對同一組整數輸入結果一致、平均為每人等權、`pool_size` 在我未達門檻時不含我。
  - `tests/unit/domains/member/test_player_dashboard.py`（擴充）——`overall_values()` 與 `aggregate().metrics[].all` 逐項相等；既有測試零變動。
  - `tests/unit/domains/member/test_member_match_records.py`（擴充＋改寫）——`partner_key`／`opponent_key` 篩選、與暱稱篩選並存、`partner_records`、`matchup_highlights`、`doubles_matches`；**以暱稱斷言合併的既有案例改為以身分斷言**。
  - `tests/unit/domains/member/test_member_match_dashboard.py`（擴充）——`insights` 隨篩選改變；`_dashboard_sample()` 重構前後對同一批 fixture 的輸出相同；查詢次數不變。
  - `tests/unit/domains/member/test_member_group_benchmark.py`（新，經資料庫）——訪客名單球員被納入、會員多段參與期間合併、已離團球員被納入、`mine` 等於 `build_member_match_dashboard(group_id=…)` 的同一指標、查詢次數與比賽數無關、`insights` 的 `benchmark_quartile` 參數與 `metrics[]` 相等。
  - `tests/unit/domains/member/test_member_match_comparison.py`（新，經資料庫）——`friend`／`me` 等於各自未篩選儀表板的 `all`、`better` 的四種值、`head_to_head` 的角度。
  - `tests/unit/domains/group/`（擴充）——`verify_ever_group_member()` 對兩列名單的會員不拋例外（**先紅後綠**）；`load_group_completed_matches()`。
  - `tests/contract/`：`test_member_match_records_endpoint.py`、`test_member_match_dashboard_endpoint.py`、`test_member_groups_history_endpoints.py`（擴充）；`test_member_group_benchmark_endpoint.py`、`test_member_match_comparison_endpoint.py`（新）——含 422 `INVALID_PLAYER_KEY`、403 從未加入、已離團／已解散 200、**回應全文不含任何其他參賽者的暱稱與 id**、好友端點的四種拒絕、未驗證信箱被拒。
  - `tests/integration/test_member_match_records_flow.py`（擴充）——點擊篩選後對戰紀錄與儀表板的 `total_matches` 一致。
- 前端：Vitest。`player-insights.component.spec.ts`（新）——四個清單、三種 `status`、空清單說明行、非顏色的區分、點擊發出 `metricPicked`／`playerPicked`、每條規則每個變體的語系 key 存在於兩份語系檔。`matchup-records.component.spec.ts`（新）——三種排序、`low_sample` 標示、重點摘要、`clickable=false` 時列不是按鈕、無雙打說明。`group-benchmark.component.spec.ts`（新）——選單預設、記住選擇、四種 `status` 的呈現、無團說明、記住的團失效時退回預設。`friend-comparison.component.spec.ts`（新）。`match-history.component.spec.ts`（擴充）——兩個新參數進入請求、作用中對象的 chip 與清除、`insights` 來源切換的單一規則、團內比較的載入時機（research Decision 9）。`friend-match-records.component.spec.ts`（擴充）——呈現摘要與搭檔／對手、無團內比較。`player-dashboard.component.spec.ts`（擴充）——`focusMetric()`。`benchmark-group-preference.spec.ts`（新）——存取失敗不拋例外。後端 `InsightRule` 與前端 `INSIGHT_RULES` 以測試綁定（沿用 035 綁定 `EndingType` 的作法）。

**Target Platform**：延續既有（Docker on AWS ECS；行動裝置優先）。

**Project Type**：Web application（monorepo，`apps/api` 與 `apps/web`）。

**Performance Goals**：300 場會員的對戰紀錄頁既有內容不因本功能明顯變慢，摘要與搭檔／對手戰績 < 3 秒；40 位球員、1,000 場的團的團內比較 < 5 秒（SC-008）。摘要與搭檔／對手戰績**不新增任何查詢**（全部來自已載入的資料）；團內比較的查詢數與比賽數無關。

**Constraints**：所有內容查看當下推導、不寫入（FR-001）；034／035 的 23 項指標、對比、趨勢、落點的算法與既有測試零變動（FR-002）；團內比較的回應不得含他人的個別數值或身分（FR-032）；團內比較不得拖慢既有儀表板（FR-007）——因此是獨立請求且純運算不佔用事件迴圈；新文字全數進語系檔、後端只回傳代碼與數字；統計規則只存在於後端（前端只做呈現排序與來源切換）。

**Scale/Scope**：後端 3 個新純函式模組＋1 個純函式新增＋服務層 1 個重構、3 個新函式、2 個擴充＋3 支新端點、2 個新 query 參數＋1 行缺陷修正＋seed script 擴充；前端 4 個新元件＋2 個頁面擴充＋儀表板的錨點與 `focusMetric()`＋4 個 models 檔＋1 個偏好小工具＋兩份語系檔。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | `InsightRule`、`InsightList`、`BenchmarkStatus`、`player_key` 在後端為 `Literal`／具驗證的型別，前端為字串聯集；規則 → 語系 key 的對應是 exhaustive `Record`，新規則漏掉句型即編譯失敗。`mypy --strict`／`tsc --noEmit`／lint 沿用既有 blocking check。 | PASS |
| II. 測試優先 | 不觸及開團、加入、輪替、比分計算四項核心邏輯；但三個新模組是「使用者據以判斷自己強弱」的規則，比照核心邏輯處理：純函式測試 MUST **先於實作**撰寫，門檻邊界各有一正一反。`verify_ever_group_member()` 的修正 MUST 先有失敗的迴歸測試。三支新端點與兩支擴充端點 MUST 有契約測試。 | PASS（列入 tasks.md 強制項） |
| III. 即時性與資料一致性 | 純唯讀，不改變比分寫入與廣播，不新增廣播內容。只計 `completed` 比賽（已捨棄的比賽不產生戰績，沿用既有查詢條件）；被撤銷的得分沿用 033 的規則——本功能不自行解讀逐分紀錄，一律經 `match_stats`。無新的團設定，快照原則不涉及。 | PASS |
| IV. 權限與安全 | 三支新端點皆 `require_verified_member`。團內比較沿用 014 已定案的 `verify_ever_group_member()`，於每次請求判定；**匿名由回應 schema 保證**（research Decision 6），契約測試掃描回應全文。與好友比較沿用 `_resolve_viewable_member()` 的四段檢查，不新增隱私設定。新回應唯一的識別資訊是搭檔／對手的 `member_id`——既有的 `ParticipantSummary` 已在同一頁的對戰清單中回傳它，不構成新曝露。暱稱與團名出現在摘要句中時，經 Angular 插值與 `app-nickname` 逸出（不使用 `innerHTML`）；語系參數以純文字帶入。無管理員專屬操作。 | PASS |
| V. 破壞性操作二次確認 | 無任何寫入或破壞性操作。 | 不適用 |
| VI. 可維護性 | 三個規則模組皆為無 ORM 的純函式，與 `player_dashboard.py` 同層、同屬 `member` domain（個人視角與彙總）。`member` → `group` 的既有 import 方向不變；為避免跨模組呼叫私有函式，`group/service.py` 新增公開的 `load_group_completed_matches()`。「與本人相同的算法」由**呼叫同一個函式**保證，而非兩份實作對齊。前端四個新元件各自獨立，頁面只負責接線。 | PASS |
| VII. 無障礙與行動裝置優先 | 強項／待加強、進步／退步、較佳的一方皆以**圖示＋文字**區分，不只靠顏色（FR-006）。摘要的每一句是原生 `<button>`；`focusMetric()` 捲動後把焦點移到指標卡，鍵盤與螢幕報讀使用者被帶到同一處。排序控制為原生按鈕並帶 `aria-sort`。搭檔／對手戰績與團內比較為 `<details>`，手機上不把既有內容往下推太遠；表格在窄螢幕不產生水平溢出（quickstart 情境 11）。 | PASS |
| VIII. i18n 與時區 | 後端只回傳規則代碼、狀態代碼、錯誤代碼與數字，**不回傳句子**；每條規則的每個變體在 `zh-TW.json`／`en.json` 各一句。新錯誤代碼 `INVALID_PLAYER_KEY` 進語系檔。「最近一場」以 UTC 的 `ended_at` 比較，不涉及顯示時區。 | PASS |
| IX. 可攜性與可部署性 | 無 migration、無新套件、無新環境變數。新欄位皆具預設值、新參數皆選填，前後端任一先部署皆相容；回滾無資料面影響。 | PASS |
| X. 伺服器為可信來源 | 不涉及任何改變比分／賽程狀態的操作。規則、門檻、名次、「較佳」判定全部在後端；前端只做列的呈現排序與「顯示哪一份 `insights`」的單一條件切換。 | PASS |
| XI. 防濫用 | 不新增「建立新資源」端點。團內比較是較重的唯讀請求，但需已驗證會員且需曾為該團成員，攻擊面與 014 既有的團歷史端點相同；前端不隨頁面載入自動觸發，除非會員已選過團（research Decision 9）。 | PASS |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

**Post-design re-check（Phase 1 完成後）**：data-model.md 與 contracts/ 確認——零儲存變更；三支新端點各自重用既有的授權函式，沒有新的授權分支；兩支既有端點只新增具預設值的欄位與選填參數，034／035 的 contract 零變動；團的 `player_records`（`OpponentRecord`）不受影響。設計期間有兩項回頭確認規格：(1) 規格 Assumptions 把「重點摘要」與「摘要敘述」的門檻寫在同一句，容易誤讀為重點摘要也要求 15 個百分點的差距——已拆成兩句，與 data-model.md 的規則表一致；(2) 規格 FR-027「記住會員上次的選擇」在設計中定為裝置端儲存，與「不新增儲存資料」不衝突，已於 research Decision 8 記載理由。Gate 結果維持 PASS。

## Project Structure

### Documentation (this feature)

```text
specs/036-match-insights-benchmarks/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── member-match-records-api.md     # 搭檔／對手戰績、partner_key／opponent_key
│   ├── member-match-dashboard-api.md   # insights
│   ├── group-benchmark-api.md          # 新：benchmark-groups、group-benchmark
│   └── match-comparison-api.md         # 新：match-comparison
├── checklists/
│   └── requirements.md  # /speckit-specify output
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
apps/api/
├── app/domains/member/
│   ├── matchups.py          # 新增：純函式——身分鍵、搭檔／對手戰績、重點摘要、head_to_head
│   ├── insights.py          # 新增：純函式——規則表、門檻常數、排序與去重、status
│   ├── group_benchmark.py   # 新增：純函式——門檻、平均、名次、四種 status
│   ├── player_dashboard.py  # 擴充：overall_values()；aggregate() 不動
│   ├── schemas.py           # 擴充：DashboardInsight(s)、回應欄位；新增三組回應 schema
│   ├── service.py           # 擴充：MemberMatchFilters、_filtered_member_matches()、
│   │                        #       build_member_match_records()、build_member_match_dashboard()；
│   │                        #       重構 _dashboard_sample() → _match_derivations()＋_sample_from()；
│   │                        #       新增 list_benchmark_groups()、build_group_benchmark()、
│   │                        #       view_member_match_comparison()
│   └── router.py            # 擴充：match_filters_query ＋2 參數；新增 3 支路由
│                            #       （/{member_id}/match-comparison 須宣告在 /me/… 之後）
├── app/domains/group/
│   ├── service.py           # 修正：verify_ever_group_member()；新增 load_group_completed_matches()
│   └── schemas.py           # 擴充：MatchupRecord、MatchupHighlights、MemberMatchRecordsResponse
├── scripts/seed_dashboard_demo.py   # 擴充：見 quickstart 前置準備
└── tests/                            # 見 Technical Context

apps/web/src/
├── app/core/player-insights/        # 新增：app-player-insights（本人頁與好友頁共用）
├── app/core/matchup-records/        # 新增：app-matchup-records（共用；clickable 輸入）
├── app/core/player-dashboard/       # 擴充：指標卡 id 錨點、focusMetric()
├── app/core/api/
│   ├── group-member-view.models.ts  # 擴充：MatchupRecord、MatchupHighlights、篩選參數
│   ├── player-dashboard.models.ts   # 擴充：INSIGHT_RULES、DashboardInsight(s)
│   ├── group-benchmark.models.ts    # 新增
│   └── match-comparison.models.ts   # 新增
├── app/core/benchmark-group-preference.ts   # 新增：localStorage 小工具（比照 score-swap-preference.ts）
├── app/features/auth/auth.service.ts        # 擴充：getBenchmarkGroups()、getGroupBenchmark()、
│                                            #       getFriendMatchComparison()
├── app/features/member/match-history/
│   ├── match-history.component.*    # 擴充：接線、作用中對象 chip、insights 來源切換
│   └── group-benchmark/             # 新增：app-group-benchmark（只在本人頁）
├── app/features/friends/friend-match-records/
│   ├── friend-match-records.component.*   # 擴充：摘要、搭檔／對手（不可點擊）
│   └── friend-comparison/                 # 新增：app-friend-comparison
└── assets/i18n/{zh-TW,en}.json      # 擴充
```

**Structure Decision**：沿用既有 monorepo 配置，沒有新的模組邊界。三個新規則模組屬 `member` domain——與 034 的 `player_dashboard.py` 同一個理由：它們是「以某一位球員為視角的跨場彙總」。團內比較雖然讀取整個團的資料，但它回答的問題是「**我**在這個團的位置」、端點在 `/members/me/…` 之下、授權以會員為主體，因此也屬 `member`；`group` 只提供一個公開的載入器。共用於本人頁與好友頁的兩個元件放 `core/`，只出現在單一頁面的兩個放各自的 `features/` 之下。

**建議實作順序**（供 `/speckit-tasks` 參考）：
1. **前置**：`verify_ever_group_member()` 的迴歸測試與修正。
2. **US2 後端＋前端**：`matchups.py` → 對戰紀錄回應 → 兩個精確篩選參數 → `app-matchup-records` 與點擊篩選。US2 先做，因為它對**所有**歷史比賽立即生效，且 US1 的「對戰組合」清單依賴它。
3. **US1**：`insights.py`（自我對比＋最近變化＋對戰組合）→ 儀表板回應 → `app-player-insights`、指標卡錨點與 `focusMetric()`；好友頁接上摘要與搭檔／對手。
4. **US3**：`_dashboard_sample()` 重構（先以既有測試鎖住行為）→ `overall_values()` → `group_benchmark.py` → 兩支端點 → `insights` 的團內來源 → `app-group-benchmark` 與來源切換 → seed 與效能實測。
5. **US4**：`head_to_head()` → 比較端點 → `app-friend-comparison`。

每一步完成後皆可獨立交付：US2 與 US1 不需要 US3／US4 即有完整價值。

## Complexity Tracking

無違反項目，本節不適用。
