# Phase 0 Research: 得分方式紀錄（主動得分 vs. 對手失誤）

Technical Context 沒有 NEEDS CLARIFICATION——技術堆疊完全沿用既有。以下是設計決策，每一項都先查證過既有程式。

## Decision 1：得分方式是 `shot_placement_records` 的第四個選填欄位，不另開資料表

- **Decision**：在既有 `shot_placement_records` 新增一個可為 NULL 的欄位 `ending_type`（`String(16)`）。值域為 `winner`／`out`／`net`／`serve_fault`／`other_error`；NULL＝未記錄。需要一支 Alembic migration（接在目前的 head `d0c14187b0e3` 之後），只做 `add_column`／`drop_column`。
- **Rationale**：該表本來就是「一個加分事件的選填附帶細節」（得分球員、失分球員、落點，032 起三者各自可空），與 `score_event_id` 一對一。得分方式是同一件事的第四個面向，生命週期完全相同：只在確認時寫入一次、只在 `-1` 修正時隨整列刪除。放在同一列，FR-012（一併收回）由既有的 `_remove_last_shot_placement_record()` **不需任何修改**就自動滿足，也不會出現「落點列還在、得分方式列被刪」這種不一致。
- **不用 DB enum、不加 CHECK constraint**：沿用本專案既有慣例——`team`（`String(1)`）、`status` 等同類欄位都是字串＋應用層驗證（Pydantic `Literal`＋service 再檢查一次）。日後新增一種得分方式不需要 migration。
- **Alternatives considered**：(a) 獨立的 `point_endings` 表——要自己再實作一次「隨 `-1` 收回」，且查詢多一次 join；(b) 放在 `score_events` 上——那張表簡易模式也在寫，會把詳細計分的概念滲進每一筆 `-1`。

## Decision 2：自動帶入發生在選擇畫面（前端），後端只存最終值

- **Decision**：FR-006／FR-007 的自動帶入是 `ShotPlacementPickerComponent` 的一個 `computed`，直接建立在它**既有**的兩個判定上：`landingSide() === 'out'` → `out`；`isServeFault()` → `serve_fault`；其餘（含界內落在失分方半場、或沒有落點）→ 不帶入。後端不做任何推定，request 裡有什麼就存什麼。
- **Rationale**：自動帶入是「替計分員預先點好」，屬於互動預設值，不是資料規則——計分員看得到、改得掉（FR-008）。放後端反而有害：計分員若刻意取消選取（想存「未記錄」），後端會無從分辨「沒選」與「取消了」，又把它推回去。Constitution X 要求的是「寫入經後端驗證」，由 Decision 4 的驗證滿足。
- **「親手選過就不再被覆蓋」（FR-009）**：選擇器新增一個 signal `manualEndingType: EndingType | null | undefined`——`undefined`＝計分員還沒碰過，生效值取自動帶入；一旦計分員點選（含點同一個以取消 → `null`），生效值固定為它，直到畫面關閉重置。生效值 `endingType = computed(() => manual !== undefined ? manual : auto)`。
- **Alternatives considered**：後端在 `ending_type` 缺省時依落點推定——見上，且會讓「略過」這個合法選擇消失。

## Decision 3：選項隨落點收斂，計分員只看到說得通的選項

- **Decision**：選擇器依目前落點停用說不通的選項：落點在**界外** → 停用「主動得分」（打進場內才算）；落點在**界內** → 停用「對手出界」。沒有落點時五個選項全部可選。被停用的選項若正是計分員先前親手選的，重新點落點時清回 `undefined`（回到自動帶入），避免存下矛盾的組合。
- **Rationale**：界內落在失分方半場時，實際可選的只剩「主動得分／對手掛網／發球失誤／其他失誤」，其中前兩個佔絕大多數——這就是 US1 情境 3 的「一次點擊」。同時讓 Decision 4 的後端驗證在正常操作下永遠不會被觸發。
- **版面（FR-013、SC-011）**：選擇器在窄螢幕已有「落點｜球員」兩個分頁（`useTabs`）。得分方式以一排 chip 放在**落點分頁**內、球場圖正下方——它與落點語意相連（自動帶入的結果就顯示在剛點的位置旁），且不增加分頁數、不把確認按鈕往下推（chip 列高度固定一行，窄螢幕可橫向捲動）。

## Decision 4：後端只驗證兩種「與落點矛盾」的組合

- **Decision**：`attach_shot_placement()` 新增參數 `ending_type`；除了值域檢查外，只在**同時提供了落點**時檢查兩條：`winner` 且落點界外 → 拒絕；`out` 且落點界內 → 拒絕。錯誤代碼 `ENDING_TYPE_CONTRADICTS_LANDING`（422）。界內／界外沿用該函式既有的判定（含單打較窄邊線）。
- **Rationale**：與既有的 `SCORING_PLAYER_WRONG_TEAM_FOR_LANDING` 同一精神——只擋「資料本身自相矛盾」，不擋「計分員的判斷」。`net`／`serve_fault`／`other_error` 與落點沒有必然關係（掛網的球可能落在任何地方；發球失誤可以是出界也可以是掛網），不加限制。沒有落點時不檢查（FR-010）。
- **被拒的代價比看起來高**（analyze I1）：已查證三個掛載點呼叫補記 API 時沒有錯誤處理（既有行為），請求被拒就等於整筆細節無聲消失。Decision 3 讓前端不會送出矛盾的組合，但界內／界外是前後端**各算一次**（含單打邊線的浮點邊界），因此以共用的邊界測試向量（data-model.md）鎖定兩邊一致。
- **「整列皆空」的既有規則要跟著改**：目前 `build_match_record_detail()` 把「四個欄位全為 NULL 的列」視同沒有明細。新增欄位後，只記了得分方式的列是有意義的——該判斷改為五個欄位全空才算空。

## Decision 5：單場拆分是 `match_stats.py` 的新純函式 `ending_stats()`

- **Decision**：`match_stats.Placement` 新增 `ending: EndingType | None`；新增 `ending_stats(points, placements, participants) -> EndingStatsResult | None`：
  - 走訪**有效得分**（與 033／034 同一序列），對每一分取其 placement 的 `ending`。
  - 隊伍層級：`winners`（本隊以 `winner` 得到的分）、`errors`（本隊**犯下**的失誤＝對手以失誤類得到的分）、`errors_by_type`（四種各幾次）。
  - 球員層級：得分端拆 `winners`／`opponent_errors`／`scored_unrecorded`；失分端拆 `beaten_by_winners`／`own_errors`／`lost_unrecorded`；另有 `own_errors_by_type`。三項相加恆等於 `player_landings()` 的 `scored_total`／`lost_total`（FR-015）——以單元測試鎖定。
  - `recorded_points`／`total_points`（FR-016 的涵蓋範圍）。
  - 全場沒有任何一分記錄得分方式 → 回傳 `None`（FR-017）。
- **歸屬（FR-003）**：`winner` 記在 `scorer_id` 上；失誤記在 `loser_id` 上。缺少對應球員的那一端只進隊伍層級。
- **Rationale**：規則只存在於一處、不碰資料庫、可窮舉測試——與 033／034 完全相同的結構。單場詳情與儀表板都呼叫它，FR-024 的一致性由建構保證。
- **既有 `player_stats`（032）不動**：新的拆分放在新的回應欄位 `ending_stats`，032 的 contract 零變動。

## Decision 6：儀表板新增 5 項指標＝在 034 的 `_METRICS` 多加 5 筆

- **Decision**：`member/player_dashboard.py` 的 `PlayerSample` 新增 `winners`／`opponent_errors`／`beaten_by_winners`／`own_errors` 與 `own_errors_by_type`；新增 `EndingSample`（只在該會員該場至少有一分記錄了得分方式時存在，FR-020）。5 項指標以既有的「每場 (分子, 分母)」機制表達：

  | key | kind | better_when | 每場貢獻 |
  |---|---|---|---|
  | `winner_share` | rate | higher | (`winners`, `winners + opponent_errors`) |
  | `winners_per_match` | average | higher | (`winners`, 1) |
  | `errors_per_match` | average | lower | (`own_errors`, 1) |
  | `error_share_of_lost` | rate | lower | (`own_errors`, `own_errors + beaten_by_winners`) |
  | `winner_error_ratio` | ratio | higher | (`winners`, `own_errors`) |

  `aggregate()` 本體**不需修改**：recent／verdict／trend／`matches_used`／「0／0 —」全部自動套用（FR-019）。指標總數 18 → 23。
- **失誤組成（FR-021）**：`DashboardResult` 新增 `error_breakdown`——`all` 與 `recent` 各一組四種失誤的次數；沒有任何失誤紀錄 → `None`。它是組成而非指標，不參與 verdict／trend。
- **比例的分母只含「已記錄得分方式」的分數**（US3 情境 3）：`winner_share` 的分母是 `winners + opponent_errors`，刻意**不含** `scored_unrecorded`。
- **Alternatives considered**：把 5 項指標寫成 `aggregate()` 內的特例——違背 034 已建立的「指標是資料、不是程式分支」。

## Decision 7：前端——選擇器加一排 chip；詳情與儀表板各加一塊

- **Decision**：
  - **選擇器**：`ShotPlacementConfirmed` 新增 `endingType`；三個掛載點（計分板、單一場地控制板、全部場地控制板）只是把它多傳一格給 `CourtControlService` 的兩個既有方法。
  - **逐點清單**（FR-014）：`ShotPlacementSummary` 新增 `ending_type`；既有的明細列多顯示一個帶**圖示＋文字**的標籤——主動得分用「★」、失誤用「✕」，類別以形狀區分而非僅顏色（Constitution VII）。
  - **單場拆分**（FR-015／FR-016）：新元件 `core/match-record-detail/match-ending-stats/`，由 `MatchDerivedStatsComponent` 掛為第六個 `<details>`，重用 034 抽出的 `_derived-blocks.scss`。
  - **儀表板**：`DASHBOARD_METRIC_KEYS` 加 5 個 key；`GROUP_OF` 新增群組 `ending`（TypeScript 的 exhaustive `Record` 會在漏掉時編譯失敗——034 當初就是為此設計）；失誤組成以四列「次數＋佔比＋細長條」呈現，四類是名目類別，用同一個顏色（不用漸層、不用四種色相）。「最近 10 場／全部」提升為**儀表板層級的單一切換**，由落點分布與失誤組成共用（analyze I3）——034 原本放在落點群組內的那兩顆按鈕移到群組清單上方；指標卡不受影響，它們本來就同時顯示兩個範圍的數字。
- **Rationale**：每一處都是在 034／033 已有的骨架上加一格，沒有新的互動模式。

## Decision 8：舊資料、即時廣播、權限——都不動

- **舊比賽不回填**（FR-025）：migration 只加欄位，既有列的 `ending_type` 全為 NULL，自然成為「未記錄」。
- **不廣播**：比照 031，`match.scoreUpdated` 不新增欄位。
- **權限**：不新增端點。三支既有的 `shot-placement` 端點共用同一個 request schema 與 `attach_shot_placement()`，授權判斷完全不變；儀表板沿用已更正的 `require_verified_member`。
- **測試 fixture**：034 的 `tests/unit/domains/_match_history.py`（`Shot`）新增 `ending` 欄位，預設 `None`，既有測試零影響；`scripts/seed_dashboard_demo.py` 一併帶入得分方式，供 quickstart 與畫面檢查使用。
