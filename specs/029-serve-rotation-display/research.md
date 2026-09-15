# Research: 計分板發球站位顯示

發球輪替演算法本身（誰目前發球、站位公式、`-1` 的處理方式）已由
`/specs/030-score-serve-record/research.md` 的 Decision 1–5 完整設計並
落地為 `Match` 的三個新欄位，本文件**不重新推導**，只處理「如何把這份
已存在的即時狀態送到前端並呈現」這三個新問題。

## Decision 1: 站位/發球者由後端算好、以結構化欄位回傳，前端不重新計算

**Decision**: `court_live_state()` 在組出 `MatchLiveDetail` 時，直接
呼叫 030 已實作的站位公式共用函式（輸入：`match.serving_team`、
`match.team_a_reference_server_id`、`match.team_b_reference_server_id`、
`match.score_a`、`match.score_b`；輸出：發球者 + 四個站位），包成一個
新的巢狀欄位 `serve: ServeStationInfo | None` 回傳給前端。前端只負責
依這個欄位渲染，不在 TypeScript 重新實作一份站位公式。

**Rationale**: 直接對應 Constitution X「伺服器為唯一可信來源」，也
呼應本專案既有慣例——`canScore`、`next_up`、`waiting_reason` 等欄位
都是後端算好的既成事實，前端純渲染。若前端自行重算，等於把同一套
規則（030 research.md Decision 2/3 的簡化雙打輪替規則）在兩個語言
（Python/TypeScript）各維護一份，日後任何一邊修改都可能悄悄產生
不一致（Constitution VI 明確禁止的「跨模組依賴內部實作細節」的鏡像
問題）。

**Alternatives considered**: 只回傳原始的 `serving_team`／兩個
`reference_server_id`，讓前端依 030 的公式自行算出四個站位——會需要
把站位公式重新 port 一份到 TypeScript，重複邏輯且有 drift 風險，不
採用。

## Decision 2: 搭既有 `match.scoreUpdated` 事件送達，不新增事件類型

**Decision**: `apply_score_delta()` 既有的 `match.scoreUpdated` Ably
發布負載，新增 `serve` 欄位（與 `GET .../state` 回傳的 `serve` 同一個
結構、同一份計算），跟 `score_a`／`score_b` 一起送出；不新增獨立的
`serve.updated` 事件。

**Rationale**: 站位資訊在時間上本來就與這次加分「同時」產生（030 已
在同一個資料庫交易內算好新的發球狀態），順手放進同一個既有事件負載
成本最低，也不會出現「比分更新事件先到、站位事件還沒到」的短暫不
一致視窗。這也直接對應 029 spec 的 Assumptions：「現有的比分即時同步
機制足以承載發球站位變更所需的即時性，不需要另外設計全新的即時通知
種類」。

**Alternatives considered**: 新增一個獨立的 `serve.updated` 事件——
同一次加分要發兩個事件，前端要額外處理兩個事件到達順序不保證一致的
邊界情況（例如網路延遲導致其中一個事件先到、畫面短暫呈現「比分」與
「站位」不同步的中間狀態），徒增複雜度且沒有對應的價值，不採用。

## Decision 3: 畫面佈局——既有兩欄式版面內部拆分，不整個重新設計

**Decision**: 計分板既有版面（`ui/ScoreBoardUI.drawio` 對應的既有
markup：畫面分左／右兩欄，左欄是 A 隊區塊、右欄是 B 隊區塊，各自內含
自己的比分與 +1/-1 按鈕）維持不變；本功能只把每個隊伍區塊內原本「兩位
隊員名字疊在同一個 `.names` 欄位」的呈現方式，拆成兩個各自獨立、對應
該隊右／左發球區站位的位置槽，並在目前發球者所在的位置槽加上一個
非純色彩的視覺標記（圖示＋文字，比照既有 `status-badge` 慣例，
Constitution VII）。單打時，該隊伍區塊只會用到其中一個位置槽，另一個
維持空白（呼應 spec FR-006）。

**Rationale**: 現有畫面本來就不是「比分置中、四個角落各自獨立」的
版面，而是「A 隊在左、B 隊在右」的兩欄式設計（既有 mockup 與現行程式
碼皆如此）。把使用者描述的「四個角落」落實為「每個既有隊伍區塊內部，
原本重疊的兩個名字改成各自獨立的位置槽」，是對既有結構最小的改動：
不需要重新設計整個計分板版面、不影響既有「比分需可遠距離閱讀」的
字體配置、也不會與既有的「即將登場」「全螢幕切換」「語言切換」等固定
角落 UI 元素的既有定位互相碰撞。

**Alternatives considered**: 整個畫面改為真正的 2×2 網格版面（比分
置中，四個角落各自獨立於畫面的四個實體角落，不再分為左/右兩欄）——
視覺上更貼近使用者描述的字面「四個角落」，但需要大幅重新設計整個
計分板版面（比分置中位置、+1/-1 按鈕相對位置、既有固定角落 UI 元素的
版面碰撞都要重新考慮），改動範圍遠超過本功能「顯示發球站位」的核心
價值。若未來有明確的視覺改版需求，SHOULD 另行 `/speckit-specify` 展開
純 UI 改版功能，本次不在此規劃範圍內擴大。

## Decision 4: 尚未有發球狀態的比賽（`serving_team IS NULL`）視同無站位可顯示

**Decision**: 若 `match.serving_team` 為 `NULL`（例如 030 尚未部署時
建立的舊比賽、或資料遷移前的既有進行中比賽），`serve` 欄位回傳
`None`，前端呈現方式與「沒有進行中比賽」時相同（不顯示任何站位資訊），
不視為錯誤、不特別提示。

**Rationale**: 直接沿用 030 data-model.md 對舊資料「不回填、不重新
計算」的既有決議；`serve` 欄位本來就宣告為 `Optional`，`None` 是這個
情境下唯一合理、不需要特殊錯誤處理的表示方式。

**Alternatives considered**: 對這類舊比賽嘗試「補算」一個發球狀態
（例如隨機重新指派）——030 明確排除任何回溯性補算，本功能沿用同一
決議，不引入例外。
