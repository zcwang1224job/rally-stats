# Phase 0 Research: 對戰紀錄衍生統計

Technical Context 沒有任何 NEEDS CLARIFICATION——技術棧、儲存、測試框架全數沿用既有。以下記錄的是「既有資料的實際語意」查證結果與由此導出的設計決策；每一項都已對照實際程式碼確認，不是推測。

## Decision 1：統計在後端計算，以獨立的純函式模組實作

- **Decision**：新增 `apps/api/app/domains/group/match_stats.py`，只含純函式與輕量 dataclass（不 import SQLAlchemy model、不接觸 `AsyncSession`）。`build_match_record_detail()` 負責查詢與把 ORM 物件轉成純函式的輸入，再把結果組進回應。
- **Rationale**：(a) Constitution II 要求核心計算邏輯有單元測試，純函式不需要資料庫即可窮舉邊界情境（連續修正、亂序撤銷、缺發球紀錄）；(b) Constitution X／032 既有慣例「前端不做跨欄位推論」——撤銷語意、發球歸屬這類規則只該存在一份，放後端；(c) `build_match_record_detail()` 是四個端點的唯一共用組裝入口，擴充它即自動套用到全部入口（FR-005），不需新增端點。
- **Alternatives considered**：
  - 前端從既有 `events[]` 自行推導走勢／耗時：不需改 API，但發球統計無論如何都需要後端提供發球紀錄，結果會變成規則一半在前端、一半在後端，撤銷語意要實作兩次。否決。
  - 直接把邏輯寫進 `build_match_record_detail()`：該函式已 140 行，且必須起資料庫才能測。否決。

## Decision 2：「有效得分」的判定——逐隊堆疊撤銷

- **Decision**：依 `created_at, id` 順序走訪全部事件，為 A、B 各維護一個「尚未被撤銷的 +1」堆疊；遇到某隊的 `-1` 就彈出該隊堆疊頂端並標記為已撤銷。走訪結束後未被標記的 `+1` 即為有效得分；其「當時比分」以有效得分序列**重新累計**，不直接採用事件上記錄的比分。
- **Rationale**：與既有 `_remove_last_shot_placement_record()`（`-1` 收回該隊最新一筆落點紀錄）語意一致（spec Assumptions）。重新累計比分是為了處理「亂序撤銷」（A+1、B+1、A−1）：此時 B 那一分事件上記錄的是 1:1，但最終成立的比分序列其實是 0:1。
- **防呆**：若有效得分數（分隊）不等於 `match.score_a`／`score_b`，視為紀錄與最終比分對不起來，四類統計一律回傳無資料（SC-003 的驗證基準直接變成執行期守門條件）。
- **Alternatives considered**：把 `-1` 視為撤銷「全場最近一分」——與既有寫入端語意不符，且 `-1` 本身帶有 `side`，明確指向某一隊。否決。

## Decision 3：發球歸屬——取「前一個有效得分」的快照，並以比分一致性把關

- **查證**：`_advance_serve_state_and_snapshot()`（`schedule/service.py`）先執行 side-out 換發球、再以**加分後**的比分計算站位、最後才寫入 `ScoreServeRecord`。因此每筆紀錄的 `server_team` 恆等於該分得分方；它描述的是「下一分開打時」的狀態。
- **Decision**：第 *i* 個有效得分的發球狀態＝第 *i−1* 個有效得分所附的 `ScoreServeRecord`。套用前先檢查一致性：該快照所屬事件記錄的比分 MUST 等於第 *i* 分開打前（重新累計）的比分；不一致、或該快照不存在，這一分就**不列入**發球統計，並計入 `excluded_points`。
- **Rationale**：單一條規則同時涵蓋三種情況——(a) 第一分（沒有前一筆，初始發球狀態從未保存，見 Decision 4）；(b) 亂序撤銷後比分與快照對不上；(c) 030 上線前後交界的比賽缺部分快照。不必為每種情況各寫一套特例。
- **接發球者**：發球者在快照中位於自己隊伍的右區或左區，接發球者＝對方隊伍**同名區**的球員（羽球發球為斜對角，雙方各自的「右區」互為斜對角）。單打時既有站位公式以各隊自己的比分奇偶決定站位，對方同名區可能為 `NULL`——此時退而取對方唯一的參賽者。雙打且同名區為 `NULL`（理論上不會發生）則該分只計入隊伍層級，不計入球員層級接發球。
- **整場無資料條件**：該場比賽一筆 `ScoreServeRecord` 都沒有 → `serve_stats = null`（FR-015）。有紀錄但全數被排除 → 同樣回傳 `null`，避免呈現分母全為 0 的表格（FR-003）。

## Decision 4：第一分的發球方無法還原——明確排除

- **查證**：`_initialize_serve_state()` 在比賽轉為 `in_progress` 時把隨機結果寫進 `matches.serving_team`／`team_{a,b}_reference_server_id`，這三欄隨後在每一分被原地覆寫；已完成比賽上留下的是**最後**狀態。`apply_score_delta()` 的 `-1` 分支註解也明載「the true pre-match-start random assignment was never persisted anywhere」。
- **Decision**：第一分一律排除（由 Decision 3 的規則自然達成），前端以 `excluded_points` 顯示一行說明（FR-012）。
- **Alternatives considered**：由第一筆快照反推（若第一分不是 side-out，發球方即得分方）——但單打完全沒有可資判別的資訊，雙打也需要知道初始 reference server 才能判斷是否換過人，兩者皆不可得。否決。要根治需新增儲存欄位，spec 已明訂不在本功能範圍。

## Decision 5：每分耗時的排除規則

- **Decision**：有效得分 *e* 的耗時，只有在「原始事件序列中緊鄰 *e* 的前一筆事件也是有效得分」（或 *e* 是全場第一筆事件，此時自 `started_at` 起算）時才列入；否則（前一筆是 `-1`、或是後來被撤銷的 `+1`）排除。
- **Rationale**：FR-021 要排除「中間發生過修正」的區間。以原始序列的相鄰關係判斷最直接：只要兩個有效得分之間夾了任何其他事件，那段時間就混入了修正操作。
- **精度**：以 `created_at` 的實際時間差（浮點秒）計算，平均值四捨五入至小數一位；不使用 `elapsed_seconds` 的整數截斷值，避免短回合累積誤差。
- **無資料條件**：沒有任何一分可列入 → `tempo_stats = null`。

## Decision 6：比分走勢的定義

- **最長連續得分**：有效得分序列中同一隊連續得分的最大長度；回報該段**開始前**與**結束後**的比分。同長度取最早一段（FR-016）。某隊整場 0 分 → 長度 0、比分欄位為 `null`。
- **最大領先**：重新累計比分的分差最大值，回報首次達到該分差時的比分；從未領先 → 0、比分 `null`（FR-017）。
- **領先易手**：維護「上一個領先者」（初始為無）。比分不平手時，若當前領先者與上一個領先者不同且上一個領先者非空 → 記一次易手；平手不重設上一個領先者。因此「A 領先 → 平手 → A 再領先」不計次，「A 領先 → 平手 → B 領先」計一次，且第一次有人取得領先不算易手（FR-018）。

## Decision 7：落點分布由後端彙整後回傳，不由前端從 `events[].detail` 重組

- **Decision**：回應新增 `landing_distribution`，每位參賽球員一筆，含 `scored`／`lost` 兩組座標與各自的 `*_total`（該球員有紀錄的總分數，不論有無落點）。
- **Rationale**：座標其實已經存在於 032 的 `events[].detail`，前端技術上可以自行重組；但 (a) 分母 `*_total` 與 032 `player_stats` 的計數必須一致，由同一處後端程式算出才不會漂移；(b) 維持「前端不做跨欄位推論」的既有慣例。額外 payload 為每分兩個浮點數，單場 ≤ 60 點，可忽略。
- **與撤銷的關係**：被撤銷得分的落點紀錄在 `-1` 當下已被既有邏輯實體刪除，留在表中的紀錄本來就只對應有效得分；本功能另外以「所屬事件為有效得分」過濾一次作為保險。
- **無資料條件**：沒有任何一位球員有可畫的點 → `landing_distribution = []`（FR-027）。這比「全場沒有座標」更嚴格：一筆只標了座標、沒選球員的紀錄不屬於任何球員的圖，回傳四張空球場沒有意義。否則列出**全部**參賽球員，個別球員兩組皆空時由前端顯示該球員專屬提示。
- **部署時序**：前端以 `landing_distribution ?? []` 讀取，前端先於後端上線時（回應尚無新欄位）四個區塊皆顯示無資料提示，不致讓整個彈窗崩潰。

## Decision 8：前端——新增一個呈現元件、擴充 `CourtDiagramComponent` 支援多標記

- **Decision**：
  - 新增 `MatchDerivedStatsComponent`（`core/match-record-detail/match-derived-stats/`），輸入為整份 `MatchRecordDetailResponse`，內部以四個原生 `<details>` 區塊呈現四類統計；由既有對話框在「球員得失分統計」之後引用。
  - `CourtDiagramComponent` 新增選用輸入 `markers`（`{x, y, kind: 'scored' | 'lost'}[]`）；既有的單點 `landingX`／`landingY` 輸入與行為完全不動。得分標記為圓形、失分標記為菱形（形狀區分，Constitution VII／FR-024），搭配文字圖例。
- **Rationale**：對話框元件與模板已不小，四個新區塊獨立成子元件可單獨測試（Constitution VI）。原生 `<details>` 不需任何狀態管理即具備鍵盤操作與無障礙語意，讓手機上既有內容不被擠遠（FR-009）：第一個區塊（發球統計）預設展開，其餘預設收合。球場繪製只維持一份（延續 032 research Decision 5）。
- **Alternatives considered**：分頁（tabs）——需要自製 roving tabindex 與 ARIA 管理，收益不比 `<details>` 高。否決。色塊式熱力圖——單場單人約十幾個點，密度圖沒有統計意義（spec Assumptions）。否決。

## Decision 9：不新增第三方套件、不新增 migration

- 走勢、耗時、發球統計為單次線性走訪，資料量為單場事件數（一般 ≤ 60）。唯一新增的查詢是 `SELECT ... FROM score_serve_records WHERE match_id = :id`（既有索引）。不需快取、不需分頁。
