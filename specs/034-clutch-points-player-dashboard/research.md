# Phase 0 Research: 關鍵分表現與跨場個人技術儀表板

Technical Context 沒有 NEEDS CLARIFICATION——技術堆疊完全沿用既有。以下是針對「怎麼做」的設計決策，每一項都先查證過既有程式。

## Decision 1：關鍵分是 `match_stats.py` 的第五個純函式，賽制以參數傳入

- **Decision**：在既有 `apps/api/app/domains/group/match_stats.py` 新增 `clutch_stats(points, target_score, cap_score) -> ClutchResult`。輸入是 033 既有的 `list[EffectivePoint]`（已完成撤銷、比分已重新累計），外加該場比賽自己的賽制快照。
- **Rationale**：033 已確立「規則只存在於一個不碰資料庫的模組」；關鍵分的所有判定都只需要「每一分開打前的比分」＝前一個 `EffectivePoint` 的 `score_a/score_b`（第一分為 0:0），不需要任何新查詢。`Match.target_score`／`cap_score` 是建立當下的快照（Constitution III），直接讀它就自動滿足「不同賽制混合彙總時各依該場賽制判定」。
- **Alternatives considered**：(a) 另開新模組——關鍵分與 momentum 共用同一個輸入型別且同屬單場推導，拆開只會讓 `EffectivePoint` 被跨檔 import；(b) 在前端由 `events[]` 推導——違反 033 已定的「前端不自行推導統計規則」，且儀表板無法重用。

## Decision 2：獲勝判定在純模組內重述一次，以測試鎖定與寫入路徑一致

- **Decision**：`match_stats.py` 內新增私有 `_wins(x, y, target, cap) = x >= cap or (x >= target and x - y >= 2)`；單元測試以 `target∈{1,11,15,21}`、`cap∈{target, target+9}`、`0 ≤ x,y ≤ cap` 的網格，斷言它與 `schedule.service.match_wins()` 逐格相等。
- **Rationale**：`schedule/service.py` 會 import ORM、session、Ably 發布等，純模組不能依賴它（否則失去「不需資料庫即可窮舉測試」）。規則只有一行，重述的成本低，網格測試讓兩者日後無法悄悄分歧。
- **賽末點**：某一分開打前比分為 `(a, b)`；`_wins(a+1, b)` 為真 → A 握有賽末點，`_wins(b+1, a)` 為真 → B 握有。兩者可同時為真（封頂前一分，例如 29:29、cap 30；或 `cap == target` 的無延長賽制在 `target-1` 平手時）。
- **平分延長**：開打前 `a ≥ target-1 且 b ≥ target-1`。**不讀** `deuce_threshold`——已查證 `match_wins()` 的 docstring 明言該欄位不參與勝負運算。
- **局末階段**：開打前 `max(a, b) ≥ target-3`；`target < 11` 時整個項目回傳 `None`（不適用，FR-010）。

## Decision 3：已完成的比賽必然以賽末點收尾——「未出現賽末點」不是需要處理的狀態

- **Decision**：不為「全場沒有賽末點」設計回應形狀或文案。
- **Rationale**：已查證 `completed` 只由 `apply_score_delta()` 在 `match_wins()` 為真時寫入（`schedule/service.py`）；`end_match_early()` 與所有強制中止路徑一律轉 `abandoned`（Constitution III），而 `_completed_matches_query()` 本就排除之。再加上 `effective_points()` 在有效得分與最終比分對不上時回傳 `None`（整塊無資料），因此只要走到 `clutch_stats()`，最後一分必為勝方兌現的賽末點：勝方 `held ≥ 1`、`converted_on == held`。這同時是一條便宜的單元測試不變式。規格原先的「手動結束的已完成比賽」情境已據此修正。

## Decision 4：逆轉摘要直接取自 033 的 `max_leads`，不重算

- **Decision**：`ClutchResult` 不含逆轉欄位；組回應時由既有 `MomentumResult.max_leads` 取「敗方」那一筆（`margin`、`score_a`、`score_b`），放進 `clutch_stats.comeback`。
- **Rationale**：「勝方最大落後」與「敗方最大領先」是同一個數字。FR-014 要求與 033 顯示一致——從同一個值取用，一致性由建構保證而非由測試保證。`margin == 0` → `comeback = null`，前端顯示「勝方全場未曾落後」。

## Decision 5：儀表板是新端點，不擴充既有 `match-records` 回應

- **Decision**：新增 `GET /members/me/match-dashboard` 與 `GET /members/{member_id}/match-dashboard`，query 參數與既有 `match-records` 的篩選參數完全相同（**不含** `page`）。
- **Rationale**：既有 `build_member_match_records()` 每次**翻頁**都會被呼叫，`get_member_group_history()` 也以 `group_id=` 呼叫它。儀表板要載入篩選結果內**所有**比賽的逐分事件（300 場 ≈ 1.3 萬筆 `score_events`），掛在既有回應上等於每翻一頁重算一次，並且平白拖慢 014 的頁面。獨立端點讓前端只在「篩選條件改變」時請求一次，並與清單平行載入（SC-007：既有內容不因儀表板變慢）。
- **路徑選擇**：不用 `/match-records/dashboard`——既有 `/match-records/{match_id}` 的 `match_id` 是 UUID 型別，FastAPI 依宣告順序比對，若順序放錯會得到 422 而非命中新路由。`/match-dashboard` 從根本避開這個順序陷阱。`/members/me/...` 仍須宣告在 `/members/{member_id}/...` 之前（既有 `match-records` 已是這個順序，照做即可）。
- **Alternatives considered**：在既有回應加 `include_dashboard=true` 參數——仍與分頁請求綁在一起，前端要多維護「這次要不要帶」的狀態，沒有比較簡單。

## Decision 6：抽出「篩選後的完整比賽集合」，兩個函式共用

- **Decision**：把 `build_member_match_records()` 前半（查詢 → 我的隊伍／roster entry → summaries → Python 端逐項篩選）抽成 `_filtered_member_matches(session, member_id, filters) -> list[FilteredMatch]`（`match`、`summary`、`won`、`my_team`、`my_entry_id`），排序維持 `ended_at desc, round_number desc`。既有函式改為呼叫它後再做勝敗彙總與分頁；新的 `build_member_match_dashboard()` 也呼叫它。12 個篩選參數收進一個 `@dataclass(frozen=True) MemberMatchFilters`；既有函式的對外簽章**不變**（內部自行組出 dataclass），兩個新端點則用一個 FastAPI dependency 直接產生 dataclass，避免第五、第六次複製那 12 個 `Query` 宣告。
- **Rationale**：FR-019 要求儀表板與既有勝敗統計「對同一批比賽」計算；兩份篩選邏輯遲早分歧，共用一份是唯一能保證的做法。既有函式的外部行為零變動，現有 `test_member_match_records.py`／`test_member_match_records_endpoint.py` 即為重構的安全網。
- **028 綁定的比賽**（US2 情境 7）：查詢以 `RosterEntry.member_id == member_id` 為條件，綁定後的 roster entry 自然符合，未綁定者自然不符——沿用同一個查詢即自動與清單一致，不需額外處理。

## Decision 7：逐分資料批次載入；單場詳情與儀表板共用同一組轉接函式

- **Decision**：在 `group/service.py` 新增 `load_match_stat_inputs(session, matches) -> dict[UUID, MatchStatInputs]`：以 `match_id IN (...)`（每批 500 個 id）各查一次 `score_events`（`order by match_id, created_at, id`）、`score_serve_records`、`shot_placement_records`，三者的 `match_id` 皆已有索引（已查證）。ORM → 純函式輸入的轉換（`RawEvent`／`ServeSnapshot`／`Placement`、完整度三態判定）抽成模組層級的小函式，`_build_derived_stats()` 改為呼叫同一組函式。
- **Rationale**：FR-003 要求單場詳情與儀表板對同一場比賽得到同一個數字——最可靠的方式是兩條路徑**共用同一段轉接碼與同一組純函式**，而不是寫兩份再用測試比對。查詢次數固定為 3（＋既有的 summaries 查詢），不隨比賽場數成長；絕不可逐場呼叫 `build_match_record_detail()`（N+1，且會多做暱稱查詢等儀表板用不到的事）。
- **完整度**：沿用 016 的判定（首筆事件 `score_a + score_b == 1` 才算 `complete`）；非 `complete` 或 `effective_points()` 回傳 `None` 的比賽，不提供任何逐分類樣本，但仍提供最終比分類樣本（Edge Case）。

## Decision 8：跨場彙總是 `member` domain 的新純函式模組，兩段式

- **Decision**：新增 `apps/api/app/domains/member/player_dashboard.py`（不 import ORM／session）：
  1. `build_sample(...) -> MatchSample`——把一場比賽的單場推導結果（`ClutchResult`、`ServeStatsResult`、球員得失分與落點）轉成「我」的視角：挑出我方隊伍的計數、我本人的發球／接發球計數（僅雙打）、我本人的得分／失分次數，並完成落點視角正規化（Decision 10）。
  2. `aggregate(samples_newest_first, recent_window=10) -> DashboardResult`——只做加總、對比、趨勢，完全不知道羽球規則。
- **Rationale**：規則（什麼是賽末點）留在 `match_stats`；視角轉換與彙總（什麼是「我的」、什麼是「最近」）屬於會員視圖，放 `member`。兩段都可用手寫的小型 dataclass 測試，不需資料庫。`member` → `group` 的 import 方向既有（`member/service.py` 已 import `group.service`），未新增反向依賴（Constitution VI）。
- **`landing_distribution()` 的小重構**：現行函式在「沒有任何一點被標落點」時回傳 `[]`，連 `scored_total`／`lost_total` 也一併丟掉；但儀表板的「個人得分／失分次數」需要這兩個 total（球員有記、落點沒標的比賽也要計）。抽出 `player_landings()` 回傳完整結果，`landing_distribution()` 變成套上空值規則的薄包裝——對外行為不變。

## Decision 9：比率以「總和相除」計算；對比與進步判定全在後端

- **Decision**：每項指標回傳 `all` 與 `recent` 兩個 `MetricValue { value, numerator, denominator, matches_used }`，外加 `better_when`（`higher`／`lower`／`null`）與後端算好的 `verdict`（`improved`／`declined`／`unchanged`／`insufficient`／`null`）。
  - 比率類：`value = Σ得分 ÷ Σ總分`（FR-022）。平均類：`Σ值 ÷ 場數`。`denominator == 0` 但有納入比賽 → `value = null`、`matches_used > 0`（前端顯示「0／0 —」）。`matches_used == 0` → 整個 `MetricValue` 為 `null`（前端顯示該指標專屬的無資料提示）。
  - `recent`＝篩選結果依 `ended_at` 最新的 10 場中、具備該指標資料者（FR-025）。總場數 ≤ 10 → 所有指標 `recent = null`、`verdict = null`（FR-027 後段）。
  - `verdict`：`recent.matches_used < 3` 或任一方 `value` 為 `null` → `insufficient`；差異小於門檻（比率類 1 個百分點、平均／比值類 0.1）→ `unchanged`；其餘依 `better_when` 判定。`better_when = null`（賽末點化解次數——救得多也代表面臨得多，無好壞方向）→ `verdict = null`；`recent` 與差異照常回傳。該指標的 `value` 取**每場平均**而非總次數——全部比賽的總和與 10 場的總和不可比，平均才能比較、也才能畫趨勢；總次數仍在 `numerator`。
- **Rationale**：「數字變大算不算進步」是規則，不是呈現（FR-026）；放後端才只有一份、才測得到。以總和相除避免「3 分的局末階段」與「12 分的局末階段」被等權平均。
- **Alternatives considered**：前端自行比較兩個數字——門檻與方向表會散落在模板裡，且好友頁與本人頁要各寫一次。

## Decision 10：落點視角正規化＝我在 B 隊時旋轉 180°

- **Decision**：已查證 `landing_x`：`0`＝A 隊底線、`1`＝B 隊底線；`CourtDiagramComponent` 以 `left = x%`、`top = y%` 繪製，即 A 在左、B 在右。我方為 A → 座標不動；我方為 B → `(x, y) → (1 - x, 1 - y)`。結果：**我方恆在左半場**，前端在圖下加一行文字「← 我方｜對手 →」（FR-031）。
- **Rationale**：必須是**旋轉**而非只翻轉 x——只翻 x 會把我的正手邊與反手邊對調（鏡像），使「失分都在反手後場」這類洞見變成錯的。旋轉 180° 同時保持左右手性與前後場。界外座標（`[-0.3, 1.3]`）經 `1 - v` 後仍落在同一範圍，不需另外處理。
- **測試**：同一個物理落點（例如「對方反手後場角落」）分別以 A 隊與 B 隊身分記錄，正規化後 MUST 得到相同座標（SC-006）。

## Decision 11：落點以「新到舊排序的陣列＋前綴長度」一次回傳兩個範圍

- **Decision**：`landing.scored`／`landing.lost` 為 `[[x, y], ...]`（四捨五入到小數 3 位），依比賽新到舊排列；另回傳 `recent_scored_count`／`recent_lost_count`——「最近 10 場」的落點恰為陣列前綴，前端 `slice(0, n)` 即可切換，不需第二份陣列或第二次請求。各範圍的 `*_total`（有球員紀錄的總分數）與 `matches_used` 分別給。
- **Rationale**：300 場 × 每場約 15 個本人落點 ≈ 4500 點；物件陣列約 200 KB，數對陣列約 60 KB。
- **密度呈現（FR-033，MAY）**：首版不做色塊熱力圖。`CourtDiagramComponent` 新增選用輸入 `dense`（預設 `false`）：當標記數 > 150 時由儀表板設為 `true`，標記縮小並降低不透明度，重疊處自然加深——形狀區分（圓／菱形）與圖例維持不變，仍符合 FR-008／FR-032。既有呼叫端不傳、行為不變。

## Decision 12：趨勢＝5 場移動區間，每項指標最多回傳最近 60 點

- **Decision**：對每個 `rate`／`average`／`ratio` 類指標，取具備資料的比賽依時間**舊到新**排列，以連續 5 場為一窗、步進 1，窗內同樣用「總和相除」；每點回傳 `{ from_ended_at, to_ended_at, value, numerator, denominator }`。具備資料的比賽 < 6 場 → 該指標不出現在 `trends`（前端顯示「場數不足」，FR-029）。每項指標只保留最新的 60 點。18 項指標皆屬這三類，皆提供趨勢（FR-028「任一項指標」）。
- **Rationale**：單場的發球得分率只有約 20 個樣本，逐場畫線幾乎全是雜訊（US3 情境 6）。全部趨勢一次回傳，切換指標不需再打 API——避免每切一次就讓後端重新載入上萬筆事件。上限 60 點使回應大小有界（實測 300 場、15 條趨勢 × 60 點約 109 KB——每點帶兩個 ISO 時間戳，比原先估計的「數十 KB」大；仍在可接受範圍，且只在篩選條件改變時請求一次）；一週打兩次、每次 5 場的球員，60 點仍涵蓋約一個半月的逐場移動，搭配「全部 vs. 最近」對比已足以回答「有沒有進步」。上限已記入規格 Assumptions。
- **Alternatives considered**：`?trend=<key>` 逐項請求——每次切換都重算整份儀表板；回傳逐場原始樣本讓前端自己算移動平均——把「總和相除」這條規則複製到前端。

## Decision 13：前端——一個共用儀表板元件，兩個頁面掛載；關鍵分是 033 元件內的第五個區塊

- **Decision**：
  - **單場**：新增 `core/match-record-detail/match-clutch-stats/`（獨立元件，輸入 `clutchStats`、隊伍標籤），由既有 `MatchDerivedStatsComponent` 掛在「比分走勢摘要」之後，同樣包在原生 `<details>`、預設收合。
  - **儀表板**：新增 `core/player-dashboard/`：`PlayerDashboardComponent`（輸入：`DashboardResponse | null`、載入／錯誤狀態）＋子元件 `dashboard-metric-card`（數值、分子／分母、依據場數、對比與 verdict 圖示＋文字）與 `dashboard-trend-chart`（手刻 SVG `polyline`，寫法比照 `match-history` 既有的 `roundTrendPolyline()`——專案沒有圖表套件，不為此引入）。落點重用 `CourtDiagramComponent`。
  - **掛載**：`match-history`（本人，請求帶目前篩選條件）與 `friend-match-records`（好友，該頁沒有篩選表單，請求不帶篩選）。球場圖預設畫雙打場地；`match-history` 在已套用的篩選為 `match_mode === 'singles'` 時傳入 `singlesCourt`，使單打邊線外的走道顯示為界外（否則單打的出界球會看似界內）。單雙打混合時沒有唯一正確的畫法，維持雙打場地。指標依主題分成 4 個原生 `<details>` 群組（發球與接發球／關鍵分／得失分與分差／落點分布），第一組預設展開（SC-009）。
  - **載入時機**：`match-history` 的 `load(page)` 目前同時處理翻頁與篩選；儀表板請求只在 `applyFilters()`／初次載入時發出，`goToPage()` 不觸發。
- **Rationale**：兩個頁面呈現同一份資料，元件只寫一次（US5 數值一致由「同一端點邏輯＋同一元件」保證）。`<details>` 的選擇理由同 033 Decision 8（內建鍵盤操作與語意、零狀態管理、手機上不擠壓既有內容）。
- **好友頁的拒絕情境**：好友端點先過既有 `_resolve_viewable_member()`，錯誤代碼與 `match-records` 相同；`friend-match-records` 既有的錯誤呈現已涵蓋整頁，儀表板請求失敗時元件**不另外顯示**錯誤（避免同一原因出現兩則提示，US5 情境 2）。

## Decision 14：不新增第三方套件、不新增 migration、不新增權限

- **Decision**：全部唯讀推導；無新資料表／欄位／索引；後端與前端皆無新依賴；兩個新端點皆使用 `require_verified_member`（好友端點另加 `_resolve_viewable_member()`）。憲章原則 IV 明定對戰紀錄在信箱驗證前 MUST 鎖定，`require_verified_member` 正是為此而設。既有 `GET /members/me/match-records` 用的是較寬鬆的 `require_member`（其 docstring 自承「未鎖定於信箱驗證」）——那是 005 留下的既有偏離，本功能**刻意不比照**，也不在此修正它。
- **Rationale**：FR-001、FR-005。三個 `match_id` 索引已存在；SC-007 的 300 場情境為 3 次 IN 查詢＋記憶體內線性走訪，預期遠低於 3 秒——quickstart 以實測確認，若不達標再另行評估快取（規格 Assumptions 已載明不屬本功能承諾）。
