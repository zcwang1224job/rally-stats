# Research: 固定搭檔循環賽——手動配對後，剩餘未配對者自動隨機配對

5 decisions。無新資料表（暫時配對刻意 MUST NOT 持久化，見決策 #2），沿用
既有 `Partnership`/`RosterEntry` 資料與既有 circle-method 排點邏輯。

## 1. 暫時配對的計算與「調整」全程不新增持久化狀態——沿用既有端點、只加一個新的純運算端點

**Decision**：新增一支唯讀、無副作用的服務函式
`preview_random_partner_pairing(session, group)`，供搭檔設定畫面主動觸發
使用（FR-001）——純粹計算「目前現役成員中沒有正式搭檔的人」並隨機兩兩配
成暫時配對，回傳結果，**不寫入 `partnerships` 資料表**。管理員「調整」
這份暫時配對（FR-006）**全程留在前端**：前端把上一次算出的暫時配對存在
畫面自己的狀態裡，用跟既有「點兩位成員互換」完全相同的互動方式，直接在
這份本機資料上做陣列層級的交換——不呼叫任何後端端點。

**Rationale**：暫時配對的定位（見 spec.md Assumptions/FR-004）是「這一輪
用完即丟」，如果比照正式搭檔重新指定（`PATCH /groups/{id}/partnerships`）
也寫進 `partnerships` 資料表，就會違反「MUST NOT 被寫入或視為正式搭檔」
這條規格明文规定；但完全不落地又要能「調整」，最簡單、不需要新增任何
暫存資料表/快取層的做法，就是把這個草稿狀態留在前端——反正這份草稿本來
就被規格定義為「頁面關掉/離開就當作沒發生過」（Edge Cases）。後端只需要
一個「給我目前該怎麼隨機配」的純運算端點，調整本身不需要往返後端。

**Alternatives considered**：
- 新增一張暫存資料表（例如 `temporary_pairings`），比照正式 `Partnership`
  一樣可以用既有的 reassign 端點調整——被拒絕，這會讓系統多一套「看起來
  像正式搭檔、但其實不是」的資料生命週期需要管理（何時清除、如何避免
  跟正式搭檔搞混），複雜度不成比例；規格本來就定義這份資料極短命（單次
  賽程產生的輸入），沒有必要為它開一張表。
- 用某種伺服器端 session/cache 暫存草稿——被拒絕，本專案目前沒有這類
  基礎設施（見憲章原則 IX 可攜性，避免新增非必要基礎設施），且「調整」
  的操作本質（把兩人互換）純粹是前端陣列操作，不需要任何伺服器端計算
  能力。

## 2. 「產生下一輪賽程」端點新增可選的 `temporary_pairings` 參數，作為賽程產生當下的輸入，而非另一個獨立步驟

**Decision**：`POST /groups/{group_id}/next-round` 的既有請求（目前完全
無 body）新增一個**可選**欄位 `temporary_pairings`（預設空陣列，其他
既有排點機制/情境完全不受影響——US3 回歸驗證）。後端 `generate_next_round()`
/`_generate_fixed_partner_matches()` 收到這份清單後，在「手動配對」模式下：
(a) 先驗證清單中每一組是否仍然只涉及「目前確實未配對」的現役成員（Edge
Cases 之重新驗證規則），無效的組合直接捨棄；(b) 對於驗證通過的組合直接
採用（FR-007：不重新隨機配）；(c) 對於驗證後仍然沒有涵蓋到的未配對成員，
在這裡（賽程產生的當下）才呼叫與 `preview_random_partner_pairing()` 相同
的隨機配對邏輯，當場補齊（FR-002）。

**Rationale**：FR-007 要求「管理員預覽/調整過的結果 MUST 被直接採用、
MUST NOT 重新隨機配」——若把「產生賽程」與「套用暫時配對」拆成兩個獨立
API 呼叫，中間有資料不一致的風險（例如兩次呼叫之間名單又變了要怎麼辦）。
把 `temporary_pairings` 當成「產生賽程」這個動作本身的輸入之一，讓
「這次賽程要用哪些暫時配對」與「賽程真正落地」在同一個請求、同一個交易
（transaction）裡一起決定，天生就不會有中間狀態不一致的問題，也完全
符合憲章原則 X「會改變賽程狀態的操作 MUST 先經後端驗證並寫入資料庫」——
真正決定用哪個暫時配對組合、以及據此建立哪些 `Match` 列，全程都在後端
這唯一一次呼叫裡完成。

**Alternatives considered**：
- 先呼叫一個「確認暫時配對」端點把草稿存起來，「產生賽程」再讀取這份
  已確認的草稿——被拒絕，這其實就是決策 #1 拒絕掉的「暫存資料表/session」
  方案的另一種形式，一樣不必要地引入需要管理生命週期的中繼狀態。

## 3. 隨機配對演算法：新增一支獨立的純函式，不與 `stage2_pair_players`／`round_robin_pairs` 混用

**Decision**：在 `algorithms.py` 新增 `random_pair_units(units:
Sequence[T]) -> list[tuple[T, T]]`——單純用 `random.shuffle` 打散後兩兩
配對的純函式，供 `preview_random_partner_pairing()` 與
`_generate_fixed_partner_matches()` 的補齊邏輯共用同一套隨機邏輯（確保
兩處「隨機」的定義完全一致）。

**Rationale**：spec.md Assumptions 明確定義「隨機」= 均勻隨機、
**不套用**既有「自動配對」模式依歷史配對次數最佳化的 `stage2_pair_players()`
邏輯——這是本功能與「自動配對」模式故意做出的區隔（一個是單純補洞，一個
是持續智慧優化），所以不能重用 `stage2_pair_players()`；但兩處呼叫點
（預覽端點、賽程產生時的自動補齊）必須是「同一種隨機」，所以抽成一支
共用的純函式，而不是各自寫一次 `random.shuffle`（憲章原則 VI 可維護性）。

**Alternatives considered**：直接重用 `stage2_pair_players()`（依歷史
配對次數最佳化）——被拒絕，違反 spec.md 對「隨機」的明確定義，且會讓
「手動配對模式的補洞」跟「自動配對模式」的配對結果變得難以區分，混淆
兩種模式的定位。

## 4. 暫時配對的授權與模式防呆：沿用既有 `SCHEDULING_MECHANISM_MISMATCH`，新增 `PARTNER_SOURCE_MISMATCH`

**Decision**：新的預覽端點 `POST /groups/{group_id}/partnerships/random-preview`
沿用既有 `require_admin` 授權模式；除了既有的
`scheduling_mechanism != "fixed_partner"` → `SCHEDULING_MECHANISM_MISMATCH`
（409）防呆之外，新增一個 `partner_source != "manual"` →
`PARTNER_SOURCE_MISMATCH`（409）防呆，確保「自動配對」模式下即使有人
直接呼叫這支端點，也 MUST 被拒絕（FR-005/US3）。

**Rationale**：既有 `manual_partnership_reassign()`／
`build_partnerships_snapshot()` 刻意**不**檢查 `partner_source`（研究過
既有程式碼確認：即使團目前是「自動配對」，管理員仍可預先調整正式搭檔
資料，等切回「手動配對」時就能直接生效——這是既有、刻意保留的行為，
`partner_source` 只決定「產生賽程時讀不讀這份資料」，不決定「能不能編輯
它」）。但本功能新增的「隨機配對剩下的人」操作，spec.md FR-005 明文要求
「自動配對」模式下 MUST NOT 提供這個操作本身——語意上比「編輯正式搭檔」
更嚴格，所以需要一個新的、專屬於本功能的防呆檢查，而不是誤用既有
`SCHEDULING_MECHANISM_MISMATCH`（那個代表的是「這個團根本不是固定搭檔
模式」，語意不同，混用會讓前端無法區分兩種錯誤原因分別對應哪一個既有
下拉選單設定）。

**Alternatives considered**：重用 `SCHEDULING_MECHANISM_MISMATCH` 涵蓋
這個新情境——被拒絕，會讓同一個錯誤碼同時代表兩種不同原因（團不是固定
搭檔模式 / 團是固定搭檔但目前是自動配對），前端訊息與既有 i18n 文案
都難以準確對應。

## 5. 前端：暫時配對狀態放在管理頁（`admin-page.component`），透過既有的搭檔設定子元件雙向溝通

**Decision**：「產生下一輪賽程」按鈕與「搭檔設定」區塊本來就在同一個
管理頁（`admin-page.component.html`）上並列（研究確認：`app-partnership-settings`
與 `openNextRoundDialog()`/`confirmNextRound()` 是同一頁的兩個區塊）。
暫時配對的草稿狀態養在 `partnership-settings` 子元件內，透過一個新的
`@Output()`（每次草稿變動就往上發出目前完整清單）讓父層
`admin-page.component` 隨時持有「目前這次要用的暫時配對」，
`confirmNextRound()` 呼叫「產生下一輪賽程」時原樣帶上。

**Rationale**：兩個區塊本來就在同一個頁面、同一次載入的元件樹裡，不需要
任何跨頁面/跨路由的狀態傳遞機制；比起再引入一個共用 service 來持有這份
草稿狀態，父子元件 `@Output()` 傳遞是這個情境下最直接、最少新增概念的
做法（憲章原則 VI）。使用者一旦離開這一頁（換路由、重新整理），這份
草稿自然隨元件銷毀而消失——天生符合 spec.md Edge Cases「還沒產生賽程就
離開畫面，草稿 MUST NOT 被保留」的要求，不需要額外寫程式碼去清除它。

**Alternatives considered**：新增一個 Angular service 持有草稿狀態
（例如 `PartnershipDraftService`）——被拒絕，目前的頁面結構（同頁父子
元件）已經足夠簡單直接處理這個需求，額外的 service 層對這個範圍不大的
草稿狀態是不必要的抽象。
