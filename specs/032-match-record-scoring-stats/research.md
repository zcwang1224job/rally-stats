# Research: 對戰紀錄逐點得失分球員與落點資訊、球員得失分統計

## Decision 1: `ScoreEventSummary` 以巢狀 `detail` 物件呈現落點/球員資訊，不攤平成頂層欄位

**Decision**：新增 `ScoreEventSummary.detail: ShotPlacementSummary | None`，把「得分球員」「失分球員」「落點座標」四個欄位包在一個巢狀物件裡，而不是直接在 `ScoreEventSummary` 上新增四個頂層 `xxx | None` 欄位。

**Rationale**：專案既有 `MatchLiveDetail.serve: ServeStationInfo | None`（029/030-serve-rotation-display）已經是完全相同的既有慣例——「這筆紀錄本身可能沒有這份附加資訊，有的話是一整包相關欄位」，用一個可為 `None` 的巢狀物件表達「有沒有」比四個各自獨立的 `| None` 欄位更清楚地表達「這是同一批一起出現或一起不出現的資訊」，前端判斷「有沒有落點資訊可顯示」也只需要檢查一個欄位（`event.detail`）而非同時檢查四個。

**Alternatives considered**：
- 直接攤平四個欄位到 `ScoreEventSummary`（`scoring_roster_entry_id`、`scoring_nickname`、`losing_roster_entry_id`、`losing_nickname`、`landing_x`、`landing_y`）——可行但語意較弱：無法用單一欄位快速判斷「這筆有沒有任何詳細計分資訊」，且與既有 `serve` 慣例不一致，增加程式碼風格差異。

## Decision 2: `detail` 是否為 `None` 的判定，取決於「至少一個欄位有記錄」，而非「這筆 ScoreEvent 是否存在對應的 ShotPlacementRecord 資料列」

**Decision**：`detail` 為 `None` 的情況涵蓋兩種底層狀況，兩者對使用者呈現的效果必須相同：(a) 這筆 `ScoreEvent`（`delta=-1` 或非詳細計分模式的 `delta=1`）完全沒有對應的 `ShotPlacementRecord` 資料列；(b) 對應的資料列存在，但 `roster_entry_id`、`losing_roster_entry_id`、`landing_x`/`landing_y` 全部是 `NULL`（計分員按下「確認記錄」時什麼都沒選——032-optional-shot-placement-detail 允許的合法操作）。只要屬於 (a) 或 (b)，`detail` 一律回傳 `None`；只要至少一個欄位有值，就回傳非 `None` 的 `ShotPlacementSummary`（其餘未設定的個別欄位各自維持 `None`，由前端逐一判斷是否顯示，見 spec FR-001/FR-002）。

**Rationale**：情況 (b) 是目前程式碼實際允許發生、但先前規劃時容易被忽略的邊界——`shot-placement-picker.component.ts` 的 `canConfirm = !landingConflict()`，在沒有任何選擇的情況下 `landingConflict()` 恆為 `false`，因此「什麼都不選就按確認」在既有 UI 上是可以送出的合法操作，後端 `attach_shot_placement()` 也不會擋下這種全空的請求，會真的寫入一筆四個欄位全 `NULL` 的 `ShotPlacementRecord`。若只以「資料列是否存在」判斷，這種全空的紀錄會被誤判為「有 detail」，展開後卻什麼資訊都顯示不出來，違反 spec FR-002「沒有記錄任何球員的加分紀錄……MUST NOT 顯示球員資訊」與 US2 AC3「沒有顯示任何球員資訊的加分紀錄……MUST NOT 呈現任何落點資訊」的精神（全空紀錄等同於「沒有記錄任何東西」，行為上應與完全沒有資料列一致）。

**Alternatives considered**：
- 以「資料列是否存在」作為 `detail` 是否為 `None` 的唯一依據——實作最簡單，但會讓「全空確認」這個邊界情況顯示出一個空白、毫無資訊的展開區塊，造成使用者困惑，不符合 spec 的既有精神。
- 回頭以 `/speckit-clarify` 詢問使用者這個邊界情況——評估後認為這屬於「如何精確落實 spec 既有意圖」的實作層級細節，spec 本身的意圖已經很明確（沒有記錄的欄位就不顯示），不構成需要使用者judgement 的新分岔決策，因此在 `/speckit-plan` 階段直接以「至少一個欄位有值」精確定義並記錄於此，不重新開啟 clarify。

## Decision 3: 球員得失分統計以「兩個獨立欄位各自加總」計算，不把每筆紀錄視為單一得失分配對

**Decision**：`player_stats` 的計算方式是對該場比賽全部的 `ShotPlacementRecord` 資料列分別跑兩個獨立的加總：`scored_count`——依 `roster_entry_id` 分組計數（只計入該欄位不是 `NULL` 的資料列）；`fault_count`——依 `losing_roster_entry_id` 分組計數（只計入該欄位不是 `NULL` 的資料列）。這兩個加總彼此獨立，一筆紀錄可能同時貢獻給某位球員的 `scored_count` 與另一位球員的 `fault_count`，也可能只貢獻其中一個（另一個欄位當時未設定）。

**Rationale**：資料模型本身（`ShotPlacementRecord.roster_entry_id`/`losing_roster_entry_id` 皆獨立可為 `NULL`，032-optional-shot-placement-detail）就允許一筆紀錄只設定其中一個欄位；spec FR-007 明白要求「只計入確實記錄了得分球員/失分球員的加分紀錄」，這裡的「確實記錄」是逐欄位判斷，不是逐筆紀錄判斷——若把每筆紀錄視為「必須同時有得分方與失分方才算數的配對」，會錯誤地把「只選了得分球員、沒選失分球員」這類合法的部分記錄整筆排除在統計之外，低估兩邊的真實次數。

**Alternatives considered**：
- 只在兩個欄位都有值時才計入該筆紀錄的統計（視為一組配對）——會系統性低估只填了單一欄位的紀錄，不符合 FR-007 逐欄位判斷的要求。

## Decision 4: `player_stats` 用「空陣列」單一訊號同時代表「完全無資料」，不新增額外的 boolean 旗標

**Decision**：`MatchRecordDetailResponse.player_stats` 只有兩種合法狀態：(a) 空陣列 `[]`——代表整場比賽沒有任何一筆 `ShotPlacementRecord` 的 `roster_entry_id`/`losing_roster_entry_id` 有值（不論是因為非詳細計分模式、或詳細計分但每一分都跳過/全空確認），對應 spec FR-008 的「無資料提示」畫面；(b) 非空陣列——代表比賽 `team_a`/`team_b` 名單中的**全部**參賽者，即使某位球員的 `scored_count`/`fault_count` 都是 0，也會出現在陣列中並明確標示為 0（對應 FR-009）。前端只需要檢查陣列長度是否為 0 就能決定要顯示統計表還是無資料提示，不需要額外的 `has_data: bool` 欄位。

**Rationale**：只要有任何一筆紀錄的任一欄位有值，依照 FR-009 的規則就一定要把全部參賽者都列出來（不然無法呈現 0 次的球員），因此「非空」與「至少一位球員有非零數字」永遠同時成立，「空陣列」與「完全無資料」也永遠同時成立——這兩個狀態互斥且窮盡，不存在「非空但其實沒有真實資料」的情況，額外的旗標只會是重複資訊。

**Alternatives considered**：
- 永遠回傳全部參賽者（即使全部是 0），另外加一個 `has_any_record: bool` 欄位讓前端判斷要不要顯示無資料提示——多一個欄位卻不會讓語意更清楚，且需要前端同時檢查兩個欄位才能決定畫面，徒增前後端需要保持同步的介面複雜度。

## Decision 5: 前端抽出共用唯讀球場示意圖元件，而非在對戰紀錄畫面複製球場繪製邏輯

**Decision**：把 `shot-placement-picker.component.scss`/`.html` 中純粹負責「畫出球場、單打時的界外遮罩、落點標記」的 `.court`/`.out-of-play-band`/`.landing-marker` 區塊（不含外層 `.court-area` 的 pointer 事件處理，那些留在互動元件本身），抽出成一個新的共用唯讀元件（`core/court-diagram/`），輸入為「是否單打」與「落點座標（可為 `null`）」，純粹渲染、無任何互動事件。既有 `shot-placement-picker` 元件的 `.court-area` 包著新元件（維持既有 pointer 事件與座標運算不變）；本功能的比賽詳情對話框則直接唯讀使用新元件，不包 `.court-area`。

**Rationale**：直接檢視 `shot-placement-picker.component.html`/`.scss` 現有程式碼確認：球場的 CSS 繪製（BWF 規格球場線條的 `background-image`/`background-size`/`background-position` 三層漸層組合）與座標互動（`.court-area` 的 `pointerdown`/`pointermove`/`pointerup`）在既有結構中就已經是分層的兩個獨立 DOM 節點（`.court-area` 外層包 `.court` 內層），抽出成本低、風險小；呼應原則 VI（可維護性）與 spec Assumptions「落點視覺重用既有球場示意圖呈現方式」，避免在對戰紀錄畫面重新刻一份球場 CSS 造成兩處日後容易走樣不一致（例如未來調整球場線條粗細/顏色時，若有兩份 CSS 需要同時記得改）。

**Alternatives considered**：
- 直接在對戰紀錄畫面複製一份簡化版球場 CSS——實作起來更快，但違反 spec Assumptions 的「重用既有呈現方式」意圖，且製造兩份需要保持視覺一致的重複程式碼，日後任一處調整球場外觀都可能遺漏另一處。
- 把整個 `shot-placement-picker` 元件（含互動邏輯）包成「唯讀模式」的一個 input flag——會讓一個元件同時承擔「計分當下的互動輸入」與「事後唯讀檢視」兩種完全不同的職責與測試矩陣，違反單一職責，且對戰紀錄畫面完全不需要 `.court-area` 的 pointer 事件邏輯、球員選擇分頁、Skip/Cancel/Confirm 按鈕等一大部分既有介面，強行共用整個元件反而增加不必要的條件分支。

## Decision 6: 單打/雙打判斷沿用既有 `team_a`/`team_b` 人數推導，不新增 `match_mode` 欄位

**Decision**：`MatchRecordDetailResponse` 不新增任何 `match_mode` 或 `is_singles` 欄位；前端沿用既有 `shot-placement-picker.component.ts` 的 `isSinglesMatch()` 慣例（`team_a`/`team_b` 參賽人數合計 ≤ 2 視為單打），直接依既有回應中已有的 `team_a`/`team_b` 陣列長度推導。

**Rationale**：`MatchRecordDetailResponse`（繼承 `MatchRecordSummary`）本來就已經回傳完整的 `team_a`/`team_b` 參賽者陣列，陣列長度本身就是單打/雙打的可靠依據（一場比賽的參賽人數在建立當下就已固定，不會事後改變），新增一個衍生自既有資訊的欄位只會是重複資料，且會製造「這個新欄位與陣列長度萬一不一致該以哪個為準」的維護風險。

**Alternatives considered**：
- 新增 `match_mode: Literal["singles", "doubles"]` 欄位，從 `Match`/`Group` 既有欄位直接複製過來——技術上更「顯式」，但屬於不必要的冗餝欄位，違反本功能「不新增回應語意」的最小化擴充原則。
