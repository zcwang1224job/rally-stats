# Phase 0 Research: 落點詳細計分模式

## Decision 1: 座標系統定義

**Decision**：以整個雙打球場為參考框架，`x` 代表「從 A 隊底線（`x=0`）到 B 隊底線（`x=1`）」的相對位置，`y` 代表「從一邊邊線（`y=0`）到另一邊邊線（`y=1`）」的相對位置，球網位於 `x=0.5`。允許超出 `[0,1]` 的值代表明顯出界，但後端以 `[-0.3, 1.3]` 為 `x`/`y` 各自的驗證範圍上限——超出此範圍視為無效輸入（例如前端座標換算錯誤或惡意請求），拒絕寫入。

**Rationale**：
- 呼應 Clarifications 2026-09-16「自由座標」決議與 FR-010「允許代表邊界外的位置」——`[-0.3, 1.3]` 留出約 30% 球場尺寸的邊界外容許範圍，足以涵蓋真實比賽中合理的「出界」落點（羽球出界通常只會超出邊線/底線一段有限距離），同時仍能擋下明顯異常的輸入（例如座標值是負的一百萬），避免資料庫累積無意義的離群值。
- 用「整個雙打球場」而非「單一半場」當參考框架，是因為落點座標本質上是描述性資訊、不驅動任何比分計算邏輯（spec Assumptions），沒有必要為了計算而簡化成半場座標；用完整球場座標也讓未來若要疊加視覺化（例如把多次落點畫在同一張圖上）時不需要額外換算。

**Alternatives considered**：
- 固定分區（Clarifications 2026-09-16 已否決，選了自由座標）。
- 座標系統改用「相對於得分方半場」（每次得分都是 0~1 對應到那一分「所屬」半場）：否決，因為「哪一方半場」本身要先知道得分隊伍才能定義，而得分隊伍是由選球員決定、可能跟落點所在的視覺位置無關（例如落點在 A 隊半場但因為 A 隊接球出界而 B 隊得分）——用固定的整場座標系統可以完全不用管這層語意，簡化資料模型。

## Decision 2: 前端共用元件架構

**Decision**：新增一個獨立、無框架特定畫面依賴的共用 Angular standalone 元件（`features/shot-placement/shot-placement-picker.component.ts`），以彈出（modal/bottom sheet，具體視覺呈現留待實作階段依各畫面既有版面決定）的形式呈現「球場示意圖點落點 → 選球員 → 確認」三步驟；輸入為該場比賽的 `MatchLiveDetail`（取得球員清單），輸出為一個 `(rosterEntryId, landingX, landingY)` 的確認事件。計分板、控制板、全場地控制板三個既有畫面各自把原本「+1」按鈕的 `(click)` 行為，在 `match.detailedScoringEnabled` 為真時改成開啟這個共用元件，確認後呼叫新的 `CourtControlService.scoreDetailed()`（三處共用同一個 service 方法，本來就已經共用 `CourtControlService`，不需新增）。

**Rationale**：三個既有畫面（`scoreboard.component`、`control-panel.component`、`all-courts-court-block.component`）目前各自獨立實作 `score(side, delta)` 方法與 +1/-1 按鈕模板，已經是三份重複；若詳細模式的點落點/選球員互動也各自實作三次，違反原則 VI（可維護性），且三倍測試維護成本。抽成一個輸入輸出明確的共用元件，三處只需要「條件式開啟它、訂閱它的確認事件」，互動邏輯與其測試只需維護一份。

**Alternatives considered**：
- 三處各自實作：否決，違反原則 VI，且已有計分板/控制板/全場地控制板三份 +1/-1 邏輯重複的既有前例可以觀察到維護成本。
- 做成一個共用的「路由層級」畫面（跳轉到新網址再跳回）：否決，既有 +1/-1 是同頁彈出/立即生效的互動，跳轉頁面會讓詳細模式的操作明顯比簡易模式慢，違背 SC-001 的 10 秒中位數目標。

## Decision 3: 後端寫入路徑——擴充既有 `apply_score_delta()` 而非另立平行邏輯

**Decision**：`apply_score_delta()` 新增一個可選參數（例如 `shot_placement: ShotPlacementInput | None = None`）。`delta > 0` 分支：若提供 `shot_placement`，在既有交易內、與 `ScoreEvent`／`ScoreServeRecord`（030）共用同一個 `score_event_id`，額外寫入一筆 `ShotPlacementRecord`。`delta < 0` 分支：無論是否為詳細模式比賽，一律嘗試刪除該隊（`match_id` + `side`）最新一筆 `ShotPlacementRecord`（若不存在則無操作）——對簡易模式比賽（從未寫入過任何 `ShotPlacementRecord`）永遠是 no-op，對詳細模式比賽則同時完成 FR-007 的「收回」語意，不需要額外的旗標判斷「這是不是詳細模式比賽」。

**Rationale**：
- `apply_score_delta()` 已經是 003（比分核心邏輯）與 029/030（發球狀態/站位快照）共用的單一比分寫入入口，維持「單一入口」是原則 VI 與原則 X（伺服器為唯一可信來源）的直接延伸——新增一套平行的「詳細模式專用比分寫入函式」會複製一份原子防呆／達標判定／`match.ended` 廣播邏輯，等於重新引入 003 已經解決過的並發/防呆問題。
- `delta<0` 統一「嘗試刪除、不存在則略過」而非先判斷 `match.detailed_scoring_enabled` 再決定要不要刪除，是因為兩種寫法在簡易模式下的行為完全相同（都是 no-op），但「統一嘗試刪除」的程式碼路徑更短、不需要額外查詢/判斷欄位，且天然滿足「未來若某場比賽的模式設定被觀察到跟資料庫實際狀態不一致」時仍以資料庫實際有沒有記錄為準的防呆特性。

**Alternatives considered**：
- 新增一個平行的 `apply_detailed_score_delta()`，完整複製一份原子更新/達標判定邏輯：否決，重複核心邏輯，且兩份邏輯未來容易走鐘（例如某天 003 的達標判定規則改了，只改到其中一份）。
- `delta<0` 時依 `match.detailed_scoring_enabled` 判斷要不要嘗試刪除：否決，比「一律嘗試刪除」多一次欄位讀取與一個分支，換來的保護在實務上沒有對應的真實情境（沒有辦法讓一場簡易模式比賽的資料庫裡出現 `ShotPlacementRecord`）。

## Decision 4: 「修正比分」沿用既有 `/score` 端點，不新增獨立 undo 端點

**Decision**：詳細模式下的「收回最後一分」直接呼叫既有 `POST .../matches/{match_id}/score`（`{side, delta: -1}`），不新增新端點；FR-007「既有『修正比分』操作在詳細計分模式下的對應版本」在 API 層面就是同一支既有端點，差別只在 `apply_score_delta()` 內部（Decision 3）多做的「刪除最後一筆落點紀錄」動作。

**Rationale**：呼應 spec FR-007 的字面意思（既有操作的「對應版本」，不是全新操作）；前端呼叫端也不需要依模式判斷要打哪一支 API，簡化 `CourtControlService`（既有 `.score()` 方法完全不用改）。

**Alternatives considered**：新增 `/score-detailed/undo` 端點：否決，前端還要多一層「這是詳細模式所以要打不同的收回端點」的條件判斷，且後端邏輯本來就已經統一在 `apply_score_delta()`（Decision 3），沒有理由在 API 層面又拆開。

## Decision 5: 團設定切換——比照既有 `scoreboard_scoring_enabled` 模式

**Decision**：`Group.detailed_scoring_enabled` 為一個獨立的即時切換旗標（不併入既有「比分規則」`base_settings_version` 樂觀鎖表單），新增 `set_detailed_scoring(session, group, enabled)` 服務函式與 `PATCH /{group_id}/detailed-scoring` 端點，完整比照既有 `set_scoreboard_scoring()`／`PATCH /{group_id}/scoreboard-scoring` 的實作模式（切換後逐一廣播該團所有場地的 `match.nextRound` 讓已開啟的畫面重新拉取狀態）。

**Rationale**：呼應 Clarifications 2026-09-16「團層級，跟現有 `scoreboard_scoring_enabled` 一致」的決議；`scoreboard_scoring_enabled` 已經是這個專案「團級別、非樂觀鎖、立即生效」設定切換的既有範例，沿用其實作模式風險最低、程式碼可讀性最高（維護者只需要認得同一種模式一次）。

**Alternatives considered**：併入既有「比分規則」（`target_score`/`deuce_threshold`/`cap_score`）的樂觀鎖表單：否決，那份表單的樂觀鎖（`base_settings_version`）是為了保護「一次送出多個關聯欄位」的表單情境設計，詳細計分模式是單一布林開關，套用樂觀鎖只會讓前端多寫一層版本號比對邏輯卻沒有對應的併發保護需求。

## Decision 6: `Match.detailed_scoring_enabled` 快照時機——僅 `create_match_with_participants()`

**Decision**：只在 `create_match_with_participants()`（`Match` 資料列唯一的建立點）設定 `detailed_scoring_enabled=group.detailed_scoring_enabled`，比照既有 `target_score`/`deuce_threshold`/`cap_score` 三個快照欄位的既有寫法；`pull_queued_match_for_court()` 不需改動，因為它只是把「已經建立、狀態為 `queued`」的既有 `Match` 資料列轉為 `in_progress` 並綁定場地，快照欄位在該筆資料列建立當下就已經定案。

**Rationale**：與 030 的 `_initialize_serve_state()` 需要在兩處掛鉤（`create_match_with_participants()` 與 `pull_queued_match_for_court()`）不同——030 的發球狀態初始化必須發生在「比賽實際開始（`in_progress`）」那一刻，而快照欄位（`target_score` 們與新的 `detailed_scoring_enabled`）只需要在「資料列被建立」那一刻決定，兩者時機點不同，不能套用同一個掛鉤點清單。

**Alternatives considered**：在 `pull_queued_match_for_court()` 也重新讀一次 `group.detailed_scoring_enabled` 並覆蓋：否決，會讓一場「建立時是簡易模式排入佇列、真正開賽前團設定被改成詳細模式」的比賽，開賽當下才「回溯」變成詳細模式，違反 FR-006「MUST NOT 影響任何已在進行中的比賽」——雖然此時比賽技術上還是 `queued` 非 `in_progress`，但「已建立的比賽資料列」本身應視為已經定案的既有活動，比照既有 `target_score` 們的處理方式（也不會在 `pull_queued_match_for_court()` 重新讀取），保持一致。
