# Phase 0 Research: 對戰紀錄洞察（優缺點摘要、搭檔與對手戰績、比較基準）

Technical Context 沒有 NEEDS CLARIFICATION——技術堆疊完全沿用既有，不新增套件、不新增資料表、不需要 migration。以下是設計決策，每一項都先查證過既有程式。

## Decision 1：摘要的規則在後端，回傳「規則代碼＋數字」，句子在前端語系檔

- **Decision**：新純函式模組 `member/insights.py`（無 ORM／session）。輸入是 034 的 `MatchSample` 清單、`aggregate()` 的結果、Decision 3 的搭檔／對手戰績，以及（選填）Decision 5 的團內基準；輸出是一組 `Insight(list, rule, level, source, metric_key, player, params)`。後端只回傳規則代碼與數字，句子由前端以 `playerInsights.rule.<rule>.<variant>` 的語系 key 加參數組成。
- **Rationale**：034／035 已確立「統計規則只存在於後端」（FR-002、FR-010 的可重現性也靠這一點）；Constitution VIII 要求後端不回傳寫死的句子。規則輸出為代碼＋參數，中英文切換時挑出的項目與順序自然相同（US1-10）。
- **自我對比的基準怎麼算**：FR-011 的基準是**逐場加權**的全場得分率。`_METRICS` 每一項的 `contribution(sample)` 回傳該場的 `(分子, 分母)`，`None` 代表該場不具備所需資料；`MatchSample` 已有 `points_for`／`points_against`。基準＝Σ(該場分母 × 該場得分率) ÷ Σ該場分母，只對 contribution 不為 `None` 的 sample 計算——不需要任何新查詢。
- **為什麼不能直接合併相除**（analyze F1）：羽球是得分方發下一球，打得順的比賽發球的分數較多，合併後發球時得分率會自然高於全場得分率約「各場得分率的變異數 ÷ 平均」，接發球則自然偏低；局末與平手的分數集中在比分接近的比賽，會被拉向五成。粗估偏差 1 到 3 個百分點、方向固定——與 FR-012 排除領先／落後的理由是同一類問題，只是幅度較小。逐場加權後，在「每一分勝率於單場內固定」的假設下期望偏差為零；T005 以合成資料的零偏差測試鎖定。領先／落後仍排除，因為它們另有單場內的偏差（落後本身就是前面運氣差的結果，與該場的實際得分率相關）。
- **為什麼 `aggregate()` 本體不動**：`insights.derive()` 是 `aggregate()` 之後的另一步，讀它的結果而不改它。034／035 的 23 項指標、對比、趨勢的既有測試因此零變動（FR-002）。
- **Alternatives considered**：(a) 前端依儀表板回應自行挑選——規則會出現在兩端，且基準所需的逐場得分不在回應中；(b) 後端回傳完整句子——違反 Constitution VIII，也讓語系切換必須重新請求。

## Decision 2：摘要搭在既有儀表板回應上；含團內比較的版本由團內比較端點回傳

- **Decision**：
  - `GET /members/me/match-dashboard`（以及好友版）的回應新增 `insights` 區塊，內容來自自我對比、最近變化、對戰組合三種來源。它本來就跟隨篩選、本來就是獨立請求，好友頁也因此自動取得（FR-019、FR-037）。
  - 團內比較端點（Decision 5）的回應另帶一份 `insights`：以**未篩選**的本人儀表板＋該團基準，經同一個 `insights.derive()` 產生的「已合併」版本。
  - 前端規則只有一條、且不含任何統計判斷：**已載入團內比較、且頁面沒有套用篩選** → 顯示團內比較回應的 `insights`；否則顯示儀表板回應的 `insights`，並在有選定團但有篩選時顯示 FR-034 的說明行。
- **Rationale**：FR-015／FR-033 要求「同一指標以團內比較來源優先」「團內來源排在前面」——這是規則，必須只有一份實作，所以合併發生在後端的同一個函式裡。另一方面，團內比較要為整個團的每位球員推導指標，明顯比儀表板慢（SC-008：5 秒 vs. 3 秒）；若把它塞進儀表板請求，既有的儀表板會被拖慢，違反 FR-007。拆成兩個回應後，儀表板與摘要先出現，團內比較完成後摘要再換成合併版。
- **代價**：團內比較端點要再算一次本人的未篩選儀表板（3 個批次查詢＋純函式）。相對於整個團的推導，這是小頭。
- **Alternatives considered**：(a) 獨立的 `/match-insights` 端點——等於每次開頁把儀表板算兩次；(b) 儀表板端點接受 `benchmark_group_id`——拖慢既有內容；(c) 前端合併兩份候選——規則外流到前端。

## Decision 3：搭檔／對手戰績依「球員身分」彙總，取代暱稱字串

- **Decision**：新純函式模組 `member/matchups.py`。身分鍵 `player_key`：名單列有 `member_id` → `m:<member_id>`；否則 → `r:<roster_entry_id>`。顯示暱稱取該球員在**最近一場**比賽中的暱稱。`build_member_match_records()` 改用它產生 `opponent_records`（型別擴充為 `MatchupRecord`）與新的 `partner_records`、`matchup_highlights`。
- **已查證的既有問題**：目前 `opponent_tallies` 以 `opponent.nickname` 為鍵（`member/service.py` L1366–1375）。除了規格提到的「同人不同暱稱被拆開、不同人同暱稱被併計」，還有一個更具體的：帳號刪除（025）會把該會員所有名單列的暱稱改成同一個 `"Deleted User"`（`member/service.py` L1041、L1079）——**所有已刪除帳號的對手目前會被併成同一列**。改用身分鍵後自然分開。
- **身分來源已經在手上**：`ParticipantSummary` 已含 `roster_entry_id` 與 `member_id`（`schedule/schemas.py` L16–28），`_build_member_match_record_summaries()` 已一次載入，不需新查詢。與 019 `build_group_final_standings()`「依 `member_id` 合併、訪客各自獨立」的既有慣例一致；028 的綁定只是把 `roster_entries.member_id` 由 NULL 填上，綁定後自動併入會員。
- **不動共用型別**：`OpponentRecord` 同時被團的 `player_records` 使用（`group/schemas.py` L490–514），維持不變；會員回應改用新的 `MatchupRecord`，它是 `OpponentRecord` 既有五個欄位的超集，前端既有程式讀到的欄位名稱與意義不變。
- **平均分差**：每場的分差＝我方得分 − 對方得分；對雙打的兩位對手各計一次（與既有「一場雙打分別計入兩位對手」一致）。
- **排序**：後端維持既有的「依場數由多到少」；「依勝率／平均分差」是同一批列的純呈現排序，列數很少，由前端元件處理——不是統計規則，不違反「規則在後端」。
- **重點摘要（FR-024）與門檻屬於規則**，在 `matchups.py` 內以常數定義並由後端回傳 `matchup_highlights`（四個 `player_key`，可為 `null`）。
- **Alternatives considered**：沿用暱稱、只在前端加欄位——無法修正上述錯併，也無法支援 Decision 4 的精確篩選。

## Decision 4：點擊某一列＝兩個新的精確篩選參數

- **Decision**：`MemberMatchFilters` 新增 `partner_key`、`opponent_key`（值即 `player_key`），篩選本身只實作一次——在 `_filtered_member_matches()`，對戰紀錄與儀表板都經過它，因此清單、勝敗統計、儀表板、摘要、搭檔／對手戰績會一起縮小範圍（FR-023）。比對方式：該場的搭檔（或對手）中存在 `player_key` 完全相等者。
- **參數要加在四個地方（產生 tasks 時查證後更正）**：兩支儀表板路由共用 `match_filters_query` 這個 dependency（`member/router.py` L535），但兩支對戰紀錄路由（L466、L664）是**各自明列**同一組 query 參數，再以 keyword 傳給 `build_member_match_records()`／`view_member_match_records()`，到函式內才組成 `MemberMatchFilters`（`member/service.py` L1344）。因此新參數須加在：`match_filters_query`、兩支對戰紀錄路由、兩個服務函式的 keyword 參數。
- **不順手重構成單一 dependency**：把對戰紀錄路由也改用 `match_filters_query` 會改變 `build_member_match_records()` 的簽章，而 `test_member_match_records.py` 與 `get_member_group_history()` 都以 keyword 呼叫它——牽動面與本功能不成比例。改以一支守門測試防止兩邊漂移：以 FastAPI 的路由內省斷言四支路由的篩選參數名稱集合完全相同（`page` 除外）。
- **Rationale**：既有的 `opponent1`／`opponent2`／`partner` 是**不分大小寫的暱稱子字串**比對（`group/service.py` L1254–1276 的 `_matches_distinct_terms`）。用它實作「點某個人」會把暱稱相近的其他人一起帶進來，也會漏掉同一人在別團的不同暱稱——正好抵銷 Decision 3。兩組參數並存、互不影響（規格 Edge Cases「兩者同時生效」）。
- **格式驗證**：`^(m|r):<uuid>$`，不合 → 422 `INVALID_PLAYER_KEY`；合法但沒有任何比賽符合 → 空結果（不是錯誤）。
- **好友頁**：好友頁刻意沒有篩選表單（已查證 `friend-match-records.component`），因此該頁的搭檔／對手列表不可點擊；參數在好友端點上仍被接受（四支路由的參數集合保持一致），只是前端不送。

## Decision 5：團內比較——每場只推導一次，再從每位球員的視角取樣

- **Decision**：
  1. 重構 `member/service.py::_dashboard_sample()`，拆成兩步：`_match_derivations(match, summary, inputs)`（每場一次：`effective_points`、`clutch_stats`、`serve_stats`、`player_landings`、`ending_stats`）與 `_sample_from(derivations, my_team, my_entry_id, won)`（每位球員一次，只呼叫 `player_dashboard.build_sample()`）。既有儀表板走同一條路，行為不變。
  2. 新服務函式 `build_group_benchmark(session, member_id, group_id)`：`verify_ever_group_member()` → 載入該團全部已完成比賽與參賽者（一次查詢）→ `load_match_stat_inputs()`（每 500 場 3 個查詢，與 034 相同）→ 每場 `_match_derivations()` 一次 → 對該場每位參賽者 `_sample_from()` → 依 `player_key` 分組 → 新純函式 `player_dashboard.overall_values(samples)`（重用 `_metric_value`，不算趨勢與落點）→ 新純函式模組 `member/group_benchmark.py` 算平均、名次、人數。
- **已查證可行**：`match_stats` 的推導全部以 `roster_entry_id` 與隊伍為鍵，會員身分只在 `my_team`／`my_entry_id` 兩處進入（`member/service.py` L1185–1190）；因此同一套函式可以直接服務訪客名單球員，FR-029「與本人完全相同的算法」由「呼叫同一個函式」保證，而不是由兩份實作對齊。
- **名次**：依 `better_when` 排序後採標準競賽排名（並列同名次、下一位跳號，即 018／019 的「1224」規則）。既有的 `_assign_standard_competition_ranks()` 是 `group/service.py` 的私有函式且型別綁死在整數勝場，因此在 `group_benchmark.py` 以同一規則另寫一個對浮點值的版本，並以測試鎖定兩者行為一致。
- **不阻塞事件迴圈**：查詢完成後的純運算（1,000 場 × 4 位球員）以 `asyncio.to_thread()` 執行——專案已有此用法（`core/email.py` L39），不新增相依。
- **不快取**：已查證整個 API 沒有任何資料快取層（只有 `get_settings()` 的 `lru_cache`，沒有 redis）。規格 Assumptions 明訂即時推導；SC-008 以擴充後的 seed script 實測，超標再另案評估。
- **Alternatives considered**：對每位球員各呼叫一次 `build_member_match_dashboard(group_id=…)`——已查證它只能以 `member_id` 定位，無法處理沒有 `member_id` 的訪客，且每人重跑一次查詢與每場推導（40 人 → 40 倍）。

## Decision 6：匿名由回應結構保證

- **Decision**：團內比較的回應 schema **沒有任何可以放他人資料的欄位**——每項指標只有 `mine`、`group_average`、`pool_size`、`rank`、`status`。每位球員的個別數值只存在於 `build_group_benchmark()` 的區域變數中，算完平均與名次即丟棄。
- **Rationale**：Clarifications 2026-09-18 明訂匿名必須由系統端把關（FR-032、SC-007）。用 schema 保證比「記得不要回傳」可靠：Pydantic 回應模型會丟掉未宣告的欄位。契約測試另以「整個回應 JSON 序列化後不含任何其他球員的暱稱、`member_id`、`roster_entry_id`」驗證。
- **小樣本**：達門檻者 < 3 人時 `group_average` 為 `null`（FR-030）。3 人時平均值理論上可讓另外兩人互相反推——但同團成員本來就能逐場查看彼此的比賽詳情（014 FR-004、032），這不構成新的資訊曝露；門檻的目的是統計意義，不是保密。
- **日後開放具名**：只需在回應加一個名單欄位並讓前端呈現，推導完全相同（規格 Assumptions 已記載）。

## Decision 7：修正 `verify_ever_group_member()` 的既有缺陷（前置工作）

- **已查證**：該函式以 `select(RosterEntry.id).where(group_id, member_id)` 後呼叫 `scalar_one_or_none()`（`group/service.py` L1019–1025）。而 `join_group()` 每次加入都**新增一列**名單（L849–860），離團只改 `status`。因此**離團後再加入的會員有兩列以上**，`scalar_one_or_none()` 會拋 `MultipleResultsFound` → 500。014 的規格明確把「加入又離開又重新加入」列為要支援的情境。
- **Decision**：改為 `.limit(1)` 後取第一筆。先寫一支會失敗的迴歸測試（兩段參與期間的會員呼叫 `GET /members/me/groups/{id}/history`）確認缺陷，再修。
- **為什麼放在本功能**：團內比較與「可比較的團」清單都重用這個授權檢查；不修的話，重新加入過的會員打開團內比較就是 500。修正只有一行，且同時修好 014 既有的兩支端點。
- **未查證、不處理**：探索時另見 `get_my_groups()` 以 `member_status_by_group[row.id]` 取值，若「會員建立的團沒有任何自己的名單列」會 `KeyError`。目前建立團時會同時建立建立者的名單列，未見可重現路徑，列為觀察項，不在本功能範圍。

## Decision 8：「上次選定的比較團」存在裝置上

- **Decision**：`localStorage`，key `rally-stats:benchmark-group:<memberId>`，沿用 `core/score-swap-preference.ts` 的寫法（取值、寫入各一個小函式，存取包 try/catch）。
- **Rationale**：已查證會員偏好目前是 `members` 表上的具名欄位（022），沒有通用的偏好表；為一個介面偏好新增欄位與 migration 不成比例，也與規格「不新增儲存」的精神不合。換裝置後回到預設（場數最多的團）是可接受的退化。
- **預設值需要每團場數**：新增輕量端點 `GET /members/me/benchmark-groups`（一個 group-by 查詢），回傳會員可比較的團與「我在該團的已完成場數」，由多到少排序。既有的 `GET /members/me/groups` 不含場數，且其回應被「我的團」頁使用，不去動它。
- **記住的團失效**（例如資料被清除）→ 端點回 403／404 時前端改用預設值並覆寫記憶。

## Decision 9：團內比較不隨頁面載入自動計算，除非會員已選過團

- **Decision**：團內比較是頁面上一個預設收合的 `<details>`。會員從未選過團 → 展開時才載入「可比較的團」並以預設團發出第一次請求。已有記住的團 → 儀表板回應到達後，於背景自動載入（因為 FR-033 的摘要敘述需要它）。
- **Rationale**：這是全頁最貴的請求；對從不使用此功能的會員，開頁成本應為零。對使用者而言，摘要會先以「自我對比」版本出現，團內比較到達後換成合併版——期間以一行「正在加入團內比較…」告知，避免內容無預警跳動。

## Decision 10：與好友比較是一支專用端點

- **Decision**：`GET /members/{member_id}/match-comparison`，授權沿用 `_resolve_viewable_member()`（023 的四段檢查，於請求當下判定）。回應含每項指標的 `friend`、`me`、`better`（`me`｜`friend`｜`tie`｜`null`），以及 `head_to_head`（互為對手／互為搭檔各一組場數、勝敗、平均分差，從檢視者的角度）。
- **Rationale**：「哪一方較佳」要看 `better_when` 與雙方最低樣本（US4-2）——是規則，留在後端。交手紀錄需要在檢視者的比賽中找出好友，本來就得在後端做；直接重用 Decision 3 的 `matchups` 與 Decision 4 的身分鍵（`m:<friend_id>`）。雙方數值用 Decision 5 的 `overall_values()`，不算趨勢與落點。
- **不通知**：已查證好友檢視路徑上沒有任何通知呼叫；本端點同樣不寫入任何東西（FR-039）。
- **Alternatives considered**：前端各抓一次雙方儀表板自行比較——多傳兩份用不到的趨勢與落點，且「較佳」的判定外流到前端。

## Decision 11：從摘要跳到對應指標

- **Decision**：已查證儀表板底下沒有任何 `id`，指標卡只有 `data-metric`。在 `dashboard-metric-card` 的 `<article>` 加上 `id="metric-<key>"`，搭檔／對手列加上 `id="matchup-<player_key>"`；`PlayerDashboardComponent` 新增公開方法 `focusMetric(key)`：展開該指標所屬的 `<details>`（既有的 `GROUP_OF` 已有 key → 群組的對應）→ `scrollIntoView()` → 將焦點移到該卡片（`tabindex="-1"`），讓鍵盤與螢幕報讀使用者也被帶到同一處。
- **Rationale**：FR-010 要求每句敘述能帶到依據；純前端、不涉及路由。

## 門檻常數的位置

規格 Assumptions 的所有門檻集中為三個模組頂端的具名常數：`insights.py`（5／10 個百分點、30 分、3 場、60%／70%、50%／60%、20 分、15%、15 個百分點、5 場）、`matchups.py`（3 場、5 場）、`group_benchmark.py`（5 場、3 人、4 人、四分之一）。日後調整只改常數與對應測試，不影響契約。
