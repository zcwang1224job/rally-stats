# Phase 0 Research: 休息／準備切換

Technical Context 沒有 NEEDS CLARIFICATION——技術堆疊完全沿用既有，不新增套件。以下是設計決策，每一項都先查證過既有程式（`apps/api/app/domains/schedule/service.py`、`algorithms.py`、`roster/models.py`、`group/service.py`）。

## Decision 1：狀態存在名單列上的一個時間欄位，不擴充 `status`

- **Decision**：`roster_entries` 新增 `resting_since TIMESTAMPTZ NULL`。`NULL`＝準備中，有值＝休息中（值為開始休息的時間）。`status`（`active | left | kicked`）不動。
- **Rationale**：`status == "active"` 這個條件出現在排程、名單、人數上限、授權、歷史戰績等數十處查詢；把休息做成第四種 `status` 會讓每一處都要重新判斷「休息中算不算在團內」，而答案一律是「算」（FR-028、FR-030）。獨立欄位讓「在不在團內」與「現在排不排他」各自只有一個來源。用時間而非布林，是因為 Decision 3 需要知道休息從何時開始。
- **離開／被踢**：`handle_member_left()` 不需要清這個欄位——所有讀取休息狀態的查詢都同時帶 `status == "active"`；重新加入會建立新的名單列（預設 `NULL`），自然是準備中（FR-001）。
- **Alternatives considered**：(a) `status = "resting"`——見上；(b) 獨立的狀態資料表——每個排程查詢都要多一個 join，換不到任何東西。

## Decision 2：所有「誰是候選人」的查詢在同一處加上「準備中」條件

- **Decision**：`schedule/service.py` 新增一個模組層級的條件 `_IS_READY = RosterEntry.resting_since.is_(None)`，加在下列讀取點（皆已帶 `status == "active"`）：
  - `_get_active_roster_for_selection()`——公平輪替雙打的整輪挑人與「場地一空就排下一場」（FR-009、FR-010）。
  - `_get_active_roster_ids()`／`_get_active_roster_ordered()`——單打循環、個人全混搭、固定搭檔的整輪產生，以及中途加入者流程與替補候選（FR-009、FR-012、FR-016）。
  - `apply_wait_count_updates()` 的「沒被挑到的人 +1」那一句（FR-024）。
  - `_seat_waiting_players_on_court()` 的 `passed_over`——它由 `idle_roster` 推得，`idle_roster` 來自上面第一個函式，因此自動排除（FR-024、US3 情境 4）。
- **固定搭檔**（兩種搭檔來源都已查證）：
  - `partner_source == "auto"`：`compute_auto_partner_teams_for_round()` 每一輪從名單重新組隊，沒有跨輪的固定隊伍——名單只含準備中的人即可，休息者的前一輪搭檔會自然與別人組隊。
  - `partner_source == "manual"`：`_resolve_manual_fixed_partner_teams()` 以 `Partnership` 為單位，再由 017 的自動補位把落單者臨時配對。任一人休息的 `Partnership` MUST **整隊**排除，且另一人 MUST NOT 進入自動補位的候選（FR-009）——否則他會被臨時配給別人，休息者一回來就變成落單，要等到下一輪才能歸隊。
- **不加條件的地方**：`build_schedule_snapshot()` 的名單（休息中的人要顯示）、`manual_assign()` 與 `change_match_player()` 的驗證（FR-029：管理員可選休息中的人）、人數上限、排行榜與所有紀錄查詢（FR-028）。
- **Rationale**：休息對排程的全部影響就是「候選人名單少了他」。把條件收斂在讀取名單的三個函式，各排程方式的配對邏輯一行都不用改（spec Assumptions：「不改變任何排程方式本身的配對邏輯」）。

## Decision 3：「坐著等了幾場」要扣掉休息期間——需要保存休息區間

- **查證**：`PlayerHistory.rest`（球員上一場結束後又有幾場比賽上場）不是存起來的計數，而是 `player_histories()` 每次從比賽的 `started_at`／`ended_at` 重新推導。它在 `stage1_select_players()` 是第三順位的比較鍵（不設上限），在 `pick_next_match()` 是第一順位（上限 `RESTED_AFTER_MATCHES = 1`）。休息一小時回來的人，`rest` 會是十幾場，在所有平手中勝出——正是 FR-025 禁止的事。
- **Decision**：新資料表 `roster_rest_periods(id, roster_entry_id, started_at, ended_at)`，只存**已結束**的休息區間，在切回準備中時寫入一列（`started_at = resting_since`、`ended_at = now`）。`player_histories()` 多收一個參數 `rest_periods: Mapping[player, Sequence[(start, end | None)]]`；計算 `rest` 時，落在該球員任一休息區間內的上場時間點不計。進行中的休息（`resting_since` 有值）以 `(resting_since, None)` 一併傳入，讓管理頁上看到的數字一致。`_get_player_histories()` 多一個查詢載入該團的區間。
- **Rationale**：這是純函式上的一個參數，門檻邊界可以不碰資料庫直接測（Constitution II、VI）。資料量極小（每次休息一列）。
- **為什麼不是兩個欄位記「上一段休息」**：同一位球員在兩場比賽之間可能切換多次；只記最後一段會讓前幾段的場數被算成「坐著等」，等於可以靠反覆切換累積優先權（US3 情境 6）。
- **為什麼不是一個「折抵場數」計數欄位**：折抵只在下一次上場前有效，要在每一條「球員上場」的路徑上清零（整輪產生、叫場、連續輪轉、手動安排、替補、換人）——漏一條就是難以察覺的公平性錯誤。從區間推導沒有「忘記清」的問題。
- **`run`（連續上場數）不受影響**：它只看兩場之間有沒有別的比賽上場，與休息無關。
- **規格說「不要求保存休息歷史」**：那是指不需要為了顯示或統計而保存；這張表是 FR-025 的計算依據，不對外呈現。

## Decision 4：回來的人不能靠「打得少」一路優先——`played_credit`

- **查證（規格沒提到、讀程式才發現）**：`stage1_select_players()` 的第二順位是「打過的場數少者優先」。休息很久的人回來後，第一場結束他與所有人同為 `wait_count = 0`，之後每一次平手他都因為場數最少而勝出，直到追平為止——在 10 人 2 面場地的連續輪轉中，等於他之後整晚都不會被輪下去。這是變相補償，違反 FR-023 與 US3。
- **Decision**：`roster_entries` 新增 `played_credit INT NOT NULL DEFAULT 0`。切回準備中時，取**其他準備中球員**的「有效場數」（實際場數＋各自的 credit）的下中位數為目標；本人有效場數低於目標時，把差額加到 `played_credit`。`_get_player_histories()` 回傳的 `played` 一律含 credit，因此所有使用者（整輪挑人、連續輪轉）只有一個入口。純函式 `returning_played_credit(own, others) -> int` 放在 `algorithms.py`。
- **為什麼是中位數**：取最小值會被「剛加入、0 場」的新人拉到 0，等於沒有折抵；取平均會受極端值影響且需要處理小數。下中位數讓回來的人「視同團裡典型的一位」，最多與一半的人平手，不優於他們。
- **不影響什麼**：`played_credit` 只進入排程的優先順序，不是比賽紀錄——排行榜、對戰紀錄、個人統計完全不讀它（FR-028、SC-008）。
- **中途加入者同樣有「場數少而優先」的現象**：那是 003 既有且有意的行為（讓新人盡快上場），不在本功能範圍。
- **Alternatives considered**：(a) 不處理——違反 FR-023；(b) 休息期間每有一場比賽就加 1——回來的人會被算成打得比任何人都多，反而被懲罰；(c) 以休息前後與團平均的差距還原——要處理休息期間有人加入／離開，複雜度不成比例。

## Decision 5：叫場——先叫沒有休息者的場次；輪到有休息者的場次時依排程方式處理

- **現況**：`_choose_next_queued_match()` 是「真正叫場」與「下一場預告」共用的唯一判斷（`pull_queued_match_for_court()` 與 `peek_next_queued_match()`），已排除「有人正在別的場地比賽」的場次。
- **Decision**：
  1. 候選查詢加一個 `NOT EXISTS`：場次內沒有休息中的球員。有候選就照既有的 `pick_next_match()` 選（FR-015）。
  2. 沒有候選、且排程方式為公平輪替雙打或個人全混搭循環賽：依叫場順序逐一檢視「含休息者、但沒有人在別場比賽」的場次，為每位休息者找替補；第一個所有休息者都找得到替補的場次即為下一場（FR-016）。都找不到就回傳 `None`（FR-017：場次原封不動留在排隊中）。
  3. 沒有候選、且為單打循環或固定搭檔循環賽：回傳 `None`（FR-018）。
  - 函式改為回傳 `(match, substitutions)`；`peek` 只呈現、`pull` 才寫入 `MatchParticipant`。同一份狀態下兩者結果相同，預告不會與實際叫場不符（FR-015）。
- **替補的挑選**：重用 `_pick_substitute()` 的排序（本輪出賽最少 → 與留下者交手最少 → 最早加入），新增參數 `must_be_free=True`——候選人另須「準備中」且「當下不在任何 `in_progress` 的比賽裡」。離場替補不要求後者（場次還沒要上場），叫場替補必須現在就能上場（spec Assumptions）。
- **併發**：兩面場地同時空出時，兩個 `pull` 可能為兩場不同的比賽挑到同一位替補，造成同一人同時在兩面場地。走到替補路徑時 MUST 先取得團列鎖（`SELECT … FOR UPDATE`，會等待——與 `_seat_waiting_players_on_court()` 同一個做法），取得後重新讀取「誰在場上」再挑。沒有休息者的一般路徑不加鎖，維持既有的 `SKIP LOCKED` 行為與效能。
- **替補者的計數**：比照離場替補——公平輪替下 `wait_count` 歸零（FR-027）。被替補者的 `wait_count` 不動（凍結中）。
- **`PairHistory`**：在比賽上場時才記錄，而替補發生在上場之前，因此自然記到替補者身上，不需額外處理。
- **按下休息的當下什麼都不改**（FR-013）：因為所有處理都延後到叫場那一刻，切換端點本身只改名單列。

## Decision 6：這一輪「被休息卡住」時的自動換輪

- **查證**：`round_is_complete()` 要求該輪所有場次皆為 `completed`／`abandoned`。被保留的場次永遠是 `queued`，所以這一輪永遠不會結束；而且 `check_round_complete_and_maybe_auto_advance()` 只在比賽結束時被呼叫——沒有比賽在打就沒有任何事件會再觸發它。
- **Decision**：新函式 `round_is_stalled_by_rest(session, group)`：當前這一輪沒有 `in_progress` 的比賽、至少有一場 `queued`、且 `_choose_next_queued_match()` 回傳 `None`、且每一場 `queued` 都含休息中的球員。`check_round_complete_and_maybe_auto_advance()` 的條件改為「已結束 **或** 被休息卡住」，其餘不變（`generate_next_round()` 本來就會把殘留的 `queued` 取消）。
- **防空轉的兩個守門條件**（新函式 `_can_generate_any_match()`：準備中的人數是否足以排出至少一場——單打 2 人、雙打 4 人、固定搭檔 2 隊）：
  - 被卡住而換輪：下一輪排不出任何一場時**不換輪**——換了只會把保留的場次取消、得到一個空的輪次；不如留著等他回來。
  - 已結束而換輪（由切換事件觸發時）：同樣排不出來就不換，否則每一次切換都會讓輪次編號加一。由比賽結束觸發的既有路徑行為不變。
- **觸發點**：既有的「比賽結束後」之外，新增「休息狀態變更後」（Decision 7 的收斂流程）。兩個方向都要：切成休息可能讓這一輪變成被卡住；切回準備中可能讓一個空的輪次有人可排。
- **誤觸的後果（已知、接受）**：所有場地閒置、只剩一場含 A 的比賽、開著自動換輪——A 一按休息，這一輪立刻結束，那一場被取消。A 再按準備好了，會由 Decision 8 的流程把他補進新的一輪，損失是那一場。這與「最後一場比賽打完就自動換輪」是同一種、由管理員自己開啟的自動行為；為此在切換上加確認框，會讓最常用的操作（隨手按一下休息）變慢，不划算。
- **未開啟自動換輪**：什麼都不做；管理頁由 Decision 9 的欄位顯示提示（FR-021）。

## Decision 7：切換是一個「設定為某狀態」的端點，後面接一段固定的收斂流程

- **Decision**：請求內容是目標狀態 `{ "resting": true | false }`，不是「切換」。已經是目標狀態時為 no-op 並回傳現況（連點兩下、或本人與管理員同時按，不會互相抵銷）。
- **兩支路由、一個服務函式**：
  - 本人：`PUT /groups/{group_id}/roster/{roster_entry_id}/rest-state`，放在 `group/router.py` 的 `leave` 旁邊，擁有權檢查與 `leave_group()` 完全相同（訪客 token 或會員身分相符；不符一律 `ROSTER_ENTRY_NOT_FOUND`，不洩漏該列是否存在）。
  - 管理員：`PUT /groups/{group_id}/members/{roster_entry_id}/rest-state`，放在 `schedule/router.py` 的踢人旁邊，`Depends(require_admin)`。
  - 兩者都呼叫新模組 `schedule/rest.py` 的 `set_rest_state()`。它 import `service`，`service` 不 import 它，沒有循環相依。
- **收斂流程**（`set_rest_state()` 內，順序固定）：
  1. 取團列鎖（與連續輪轉、替補同一把），讀名單列；非 `active` → `ROSTER_ENTRY_NOT_FOUND`。
  2. 切成休息：寫 `resting_since = now`。切回準備中：寫入一列 `roster_rest_periods`、清 `resting_since`、依 Decision 4 調整 `played_credit`，再呼叫 `_schedule_late_joiner_matches()`（Decision 8）。
  3. commit。
  4. `refresh_courts_after_roster_change()`——既有函式：輪次進行中就把閒置場地填滿（叫排隊中的場次，否則連續輪轉排人），並對每面場地發 `match.nextRound` 讓畫面重抓。這一步同時滿足 FR-019（回來就立刻叫場）。
  5. `check_round_complete_and_maybe_auto_advance()`（Decision 6）。
  6. 發布 `roster.restChanged`（Decision 10）。
- **併發**：切換本身只改一列，不需要與叫場互斥——若叫場的交易先讀到「準備中」而把他叫上場，結果等同「上場後才按休息」（FR-014）；若休息先提交，該場就依 Decision 5 處理。任何順序都不會出現「已上場的場次裡有人被移除」。

## Decision 8：整輪產生時被排除的人，輪中回來時走既有的「中途加入者」流程

- **查證**：`_schedule_late_joiner_matches()` 把「在團內、但這一輪沒有任何場次」的人視為 newcomer，補上他的場次（單打循環：對這一輪還沒交手的每個人；固定搭檔：新隊伍對每一隊；個人全混搭：與每個人搭檔一次）。公平輪替雙打不需要（下一次挑人自然納入）。輪次尚未規劃或已結束時不做事。
- **Decision**：回到準備中時直接呼叫它（FR-012）。它的 `active` 名單經 Decision 2 已只含準備中的人，因此：休息中的人不會被誤判為 newcomer，也不會被排成別人的對手。
- **需要用測試釘住的兩個風險**：
  - 固定搭檔：回來的人有正式搭檔、但搭檔還在休息——該函式對落單的 newcomer 有「依加入順序臨時配對」的邏輯，MUST NOT 把他配給別人；要等兩人都準備好才以原隊伍補入。
  - `wait_count`：該流程不碰 `wait_count`，回來的人維持凍結的值，不會變成 `NULL`（FR-026）。
- **已知限制**：單打循環中，A 休息期間才加入的 B 不會被排一場對 A（A 當時不在候選名單）；A 回來時因為這一輪已有場次，不算 newcomer，也不會補這一場。下一輪即恢復正常。為了這一場去改寫「newcomer」的定義，會動到 011 已穩定的邏輯，不值得。

## Decision 9：畫面需要的資訊由後端給，前端不自行推論

- `RosterScheduleStatus` 新增 `resting: bool`、`resting_since: datetime | None`、`partner_roster_entry_id: str | None`（只在固定搭檔循環賽時填，取自**當前這一輪的場次**裡與他同隊的人——這樣自動搭檔、手動搭檔、臨時配對三種來源都正確，而且說明的對象正是「這一輪被暫緩的那幾場」。成員頁用它找到「我的搭檔」那一列，判斷要不要顯示 FR-022 的說明。隊伍組成本來就出現在每一場比賽裡，不是新曝露的資訊）。
- `NextUpPreview.participants` 呈現**替補後**的陣容，另加 `substitutions: [{ resting, substitute }]`，讓畫面能標示「代替 XX（休息中）」。
- `RoundMatchSummary` 新增 `rest_effect: "held" | "substitute" | null`——只對 `queued` 且含休息者的場次有值，依排程方式決定；管理頁的本輪賽程清單與成員頁據此標示。
- `RoundMatchesResponse` 新增 `waiting_on_rest: { match_count, players: [RosterSummary], stalled: bool } | null`（FR-021）。`match_count > 0` 就顯示提示，`stalled`（Decision 6 的判斷）為真時以較醒目的樣式呈現。
- `WaitingReason` 新增兩個值（FR-011、FR-017）：`held_for_rest`（排隊中還有場次，但全部在等休息中的球員）、`not_enough_ready`（沒有排隊中的場次、開著連續輪轉、閒置且準備中的人不足四人、且有人在休息）。其餘情況維持 `no_queued_match`。
- **Rationale**：Constitution X（伺服器為可信來源）；而且「這場算保留還是會被替補」取決於排程方式與替補可得性，是後端才有的判斷。

## Decision 10：即時同步——一個新事件，當作重抓的觸發

- **查證**：前端所有即時事件的處理方式都是「收到就 `load()` 重抓」，沒有任何地方套用 payload 的差異。名單類事件（`member.joined`、`member.left`）走 `group:{id}:notifications` 頻道；場地類走各場地頻道。
- **Decision**：新事件 `roster.restChanged`，發布於 `group:{id}:notifications`，payload `{ roster_entry_id, nickname, resting }`（精簡，比照 `member.left`）。訂閱端：成員頁的 `member-schedule`、管理頁的 `admin-page`，處理方式為重抓。場地相關畫面（計分板、控制面板、全場地面板）不需要訂閱——Decision 7 第 4 步本來就會對每面場地發 `match.nextRound`。
- **由系統端發出**（FR-007、Constitution X）：前端切換成功後不自行廣播，也不樂觀更新他人的畫面；自己的畫面以回應內容更新。

## Decision 11：測試策略

- **純函式（先寫、先紅）**：`player_histories()` 的休息區間（區間內不計、區間前後照計、多段區間、進行中的區間、在場上時按休息）；`returning_played_credit()`（下中位數、只有自己、已高於目標、新人拉低最小值時不受影響）。
- **服務層（經資料庫）**：每個排程方式各一組——整輪產生排除休息者、固定搭檔整隊排除；`apply_wait_count_updates()` 與連續輪轉不對休息者 +1；叫場優先序；替補的三個條件與找不到時保留；單打循環／固定搭檔保留；回來後立即叫場；`round_is_stalled_by_rest()` 與兩個守門條件；回來走中途加入者流程與 Decision 8 的兩個風險；兩面場地同時空出不會挑到同一位替補。
- **模擬（SC-004）**：擴充既有的 `tests/unit/domains/schedule/test_fairness_simulation.py`——多人、多輪、固定亂數種子、隨機休息與回來；斷言 (a) 休息前後 `wait_count` 差值為 0，(b) 回來後第一次挑人時，順位不優於同一時刻 `wait_count` 相同且一直準備中的人，(c) 回來後的上場比例不高於全體的中位數加一個容許值（防 Decision 4 的回歸）。
- **契約**：兩支端點的授權矩陣（本人會員、本人訪客、他人、管理員、未登入；已離開／被踢的列；別的團的列）、冪等、回應形狀；`ScheduleResponse`／`RoundMatchesResponse` 的新欄位。
- **既有測試零變動的範圍**：排行榜、對戰紀錄、個人統計（SC-008）；沒有人休息時，所有排程測試的結果 MUST 與現在相同——新條件在沒有休息者時是恆真。
