# Phase 0 Research: 賽程與輪替名單

## 1. 決議：新建 `app/domains/schedule/` 領域模組

**Decision**：新增 `app/domains/schedule/`，擁有 `Match`、`MatchParticipant`、`PairHistory`、`Partnership` 四個實體與全部排點演算法、Round 生命週期、手動安排、成員異動處理邏輯。`Court`（002 擁有）與 `RosterEntry`（001 建立、003 擴充其排點語意）維持各自模組，本 feature 僅讀取／更新其既有欄位，不搬移其擁有權。

**Rationale**：呼應 constitution 原則 VI（模組化，以實體所屬領域劃分）；`matches`/`match_participants`/`pair_history`/`partnerships` 四張表皆為本 feature 首次實際寫入（架構文件 DDL 已預先定案，見 §2 `architecture.md`），邏輯高度耦合（排點演算法同時讀寫這四張表），獨立成一個模組最符合單一職責。

## 2. 決議：`AbandonMatchesHook`（001）與 `AbandonCourtMatchesHook`（002）於本 feature 串接

**Decision**：001 的 `disband_group()`、002 的 `delete_court()` 皆已預留可選 hook 參數（目前皆為 no-op 預設值）。本 feature 於 `app/domains/schedule/service.py` 實作對應的真正邏輯（`abandon_group_matches(session, group_id) -> None`、`abandon_court_matches(session, court_id) -> bool`），並在 **router 層**（`group/router.py` 的 disband 端點、`court/router.py` 的 delete 端點）串接——即傳入這兩個函式作為呼叫時的具名參數，而非修改 001/002 既有 service 函式的簽章。

**Rationale**：維持 001/002 既有程式碼與其既有測試不被本 feature 破壞（僅新增兩行 import + 傳參，不變更既有邏輯）；此模式已於 002 的 `research.md` #2 驗證可行。

## 3. 決議：FR-042（比賽模式 × 排程機制組合驗證）直接寫入 001 的 `group/service.py`

**Decision**：FR-042 是 Group 自身兩個既有欄位（`match_mode`、`scheduling_mechanism`）之間的組合驗證，不涉及 `schedule` 領域的任何資料表查詢。比照 001 已有的 FR-020（切換雙打時人數上限連動檢查）precedent，直接於 `create_group()`、`edit_group()` 內新增此驗證規則（而非透過 hook 或事件），前後端皆須驗證。

**Rationale**：這是純粹的欄位組合一致性檢查，與「本 feature 尚不存在時 001/002 如何運作」的前向相依問題（見 #2）性質不同——FR-042 本來就必須在 create/edit 當下立即擋下，沒有「延後生效」的空間；且驗證邏輯完全不依賴 `matches`/`partnerships` 等本 feature 才有的資料。

## 4. 決議：`scheduling_mechanism` 切換的 Partnership 副作用串接於 router 層

**Decision**：「切換進入固定搭檔循環賽時自動配對」（FR-020）與「切換離開時清空 Partnership」（FR-024）不修改 `edit_group()` 本身，而是在 `group/router.py` 的 `PATCH /{group_id}` 端點內，比對呼叫前後的 `scheduling_mechanism`，變動時呼叫 `schedule` 模組對應函式（`auto_pair_on_enter_fixed_partner()` / `clear_partnerships_on_exit()`）。

**Rationale**：與 #2 相同的模組邊界考量——`edit_group()` 是 001 擁有的通用編輯邏輯，不應為了 003 才存在的搭檔概念而承擔額外知識；router 層天然知道「呼叫前 vs 呼叫後」的差異，是最合適的串接點。

## 5. 決議：PairHistory 的計數語意——同場比賽任兩人皆計一次，建立當下即累加

**Decision**：`pair_history.pair_count` 代表「任兩人曾經出現在同一場比賽（不論同隊或對戰）的次數」。一場雙打比賽建立時，對 4 位參與者的所有 C(4,2)=6 種兩兩組合各自 `pair_count += 1`；單打比賽對僅有的 1 組組合 `+= 1`。**於比賽建立（`matches` 列寫入）的同一筆交易內立即累加**，MUST NOT 等到比賽進入終態才累加——因為 FR-009 已明定捨棄的比賽依然計入，若等到終態才寫入,則需要額外追蹤「已計入 vs 未計入」的狀態，不如建立當下即定案來得單純，且與「配對關係已實際發生過」的精神一致。

**Rationale**：FR-008 原文「每一對成員（不論搭檔或對手）MUST 維護一個『配對次數』計數器」未區分隊友/對手，且 FR-019（跨隊配對次數加總）與 FR-025（個人全混搭第一步沿用 FR-008 配對次數決定搭檔）都讀取同一個計數器做不同用途，故確認為單一、不分角色的計數語意。

## 6. 決議：階段二貪婪配對的決定性排序（tie-break）

**Decision**：貪婪配對（FR-008 個人配對、FR-019 跨隊對戰、FR-025 兩步驟）在「配對次數總和」相同時，依「階段一已決定的上場順序」（即 wait_count 由高到低、次要依 `joined_at` 由早到晚 的排序結果）作為決定性 tie-break，確保結果可重現、不依賴隨機性或資料庫回傳順序。演算法本身採貪婪法（依序處理排序最前面尚未配對的實體，選擇當下配對次數總和最小的對象配對，重複至全部配對完畢）——spec Assumptions 已明文接受非全域最佳解。

**Rationale**：spec 未定義 tie-break 規則，但 SC-002（累計上場次數差距 ≤1）與可測試性皆要求確定性行為；沿用階段一已排序的名單順序是最小成本的實作方式，不需額外欄位或隨機數。

## 7. 決議：Round 產生 = 建立全部 queued 比賽 + 立即對每個場地執行一次「領取」

> **011-round-robin-scheduling 修訂說明**：本節「N 恆等於場地數 × 每場所需
> 人數，比賽數量必然 ≤ 場地數，無場地在該輪等待中途領取」的推論，自 011
> 起僅對**公平輪替之雙打情境**成立；單打、固定搭檔循環賽、個人混搭循環賽
> 三種情境下，一輪的比賽數量遠多於場地數是常態，`advance_court_after_match_ends()`
> 與新增的 `_advance_other_idle_courts()`（見 011 research.md #4）在這三種
> 情境下才是「場地日常運作的主要路徑」，不再只是本節所述的邊緣情況。以下
> 決議內容維持原樣作為 003 當時（僅有雙打填滿場地模型）的設計紀錄。

**Decision**：`generate_next_round()`（演算法排程機制）在同一筆交易內：(a) 依演算法選出上場名單與分組，建立對應的 `matches`（`status='queued'`, `court_id=NULL`）+ `match_participants`；(b) 立即依場地建立時間排序，對每個「目前有效」場地各執行一次「領取下一場排隊中比賽」（即 FR-027 所述機制），將 `court_id` 填入、`status` 轉為 `in_progress`、`started_at=now()`。由於 N（上場人數上限）恆等於「場地數 × 每場所需人數」，比賽數量必然 ≤ 場地數，此「領取」步驟在 Round 剛產生的當下即可讓所有可湊滿的場地立即進入 `in_progress`，無場地在該輪等待中途領取；`advance_court_after_match_ends()`（FR-027，供 007 spec 呼叫）沿用同一支「領取」函式，僅在尚有排隊中比賽時才會實際找到可領取的比賽（三種演算法模式下，此情況只會發生在同一輪內，理論上不會再有——因為每輪比賽數已 ≤ 場地數；此函式仍需存在並正確運作，因為手動安排以外的未來擴充或例外情境──例如場地於 Round 進行中被刪除又重新新增──皆可能造成「場地數 > 目前該輪已建立比賽數」的情況，需要一致的領取邏輯處理）。

**Rationale**：架構文件之 `matches.court_id` 註解明確指出「演算法模式排隊中時可為 NULL」，代表建立與領取本為兩個步驟——本決議之目的是讓兩步驟合併在同一次 Round 產生操作中一次完成，使用者不需額外操作即可看到所有場地立即開始計分（呼應 SC-001「2 秒內完成」）。

## 8. 決議：Next Round 的並發控制採悲觀鎖（沿用 architecture.md 端點註記）

**Decision**：`POST /groups/{group_id}/next-round` 於交易開始時對該 Group 資料列執行 `SELECT ... FOR UPDATE NOWAIT`；取得鎖失敗（另一請求正在處理中）時，MUST 立即回傳語意化錯誤 `ROUND_GENERATION_IN_PROGRESS`（409），不等待、不重試。Auto Next Round（由比賽終態觸發，非使用者直接呼叫的端點）比照使用同一支內部函式，天然序列化於同一個資料庫交易內，不需額外處理。

**Rationale**：`specs/architecture.md` §3.1 已將此端點註記為「悲觀鎖 + `lock_timeout`」，與 001/002 其餘端點慣用的樂觀鎖（版本欄位）不同——因為 Next Round 的操作內容（整批建立/捨棄多筆 `matches`）遠比單一欄位更新複雜，樂觀鎖版本號在此處難以精確定義「哪個版本」，悲觀鎖直接鎖住整個操作區間更為單純可靠，此為架構文件既有決策，本 feature 予以落實而非重新評估。

## 9. 決議：`RosterEntry.wait_count` 更新一律採「整批 UPDATE」而非逐筆迴圈

**Decision**：Round 產生時，「上場者歸零、未上場者 +1」以兩道 SQL `UPDATE ... WHERE id IN (...)` 完成（上場者 IN 上場名單清單 SET wait_count=0；其餘 active 且未上場者 SET wait_count = COALESCE(wait_count, 0) + 1），而非在 Python 迴圈中逐筆 `session.add`。

**Rationale**：Round 內參與者可能達數十人，整批 SQL 更新是效能與正確性皆較佳的做法（避免 N+1）；`COALESCE(wait_count, 0) + 1` 正確處理「原本為 NULL（尚未上場過）→ 未被選中 → 應變為 1」的邊界情況（NULL 代表無限大，錯過這次仍是「已經等了 1 輪」而非繼續維持 NULL）。

## 10. 決議：手動安排（US2）與其餘三種演算法模式共用 `advance_court_after_match_ends`，但 Round 邊界判斷邏輯分歧

**Decision**：手動安排模式下，比賽結束後 MUST NOT 觸發任何自動領取（FR-010, FR-015），`advance_court_after_match_ends()` 於偵測到 `group.scheduling_mechanism == 'manual'` 時直接 no-op 並讓該場地維持「等待管理員安排」；Round 是否結束的判斷（FR-028 vs FR-015）依 `scheduling_mechanism` 分支處理，手動安排模式的 Round 邊界僅由管理員手動按下「Next Round」決定，不存在自動偵測「賽程表是否消耗完畢」的概念（因為手動安排根本不產生賽程表）。

**Rationale**：FR-015 明文排除手動安排適用「賽程表是否還有非 completed 比賽」的 Round 結束機制；統一入口＋內部分支比為兩種模式各寫一套呼叫路徑更不易遺漏邊界情況。
