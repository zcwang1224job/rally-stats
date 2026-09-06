# Research: 循環賽賽程排程

## 1. 決議：單打與固定搭檔循環賽採「循環法（Circle Method）」一次性生成零重複賽程

**Decision**：對於公平輪替的單打情境（n 位球員）與固定搭檔循環賽（m 支隊伍，隊伍已由手動設定或自動配對決定，見 #6），採用經典的循環賽排點演算法「循環法」：固定一人（或一隊）不動，其餘繞圓周旋轉，每一輪產生 ⌊count/2⌋ 場零衝突（同一人/同一隊不會同時出現在兩場）的比賽，共執行 count-1 輪（count 為奇數時補一個虛擬「輪空」位，實際執行 count 輪、每輪捨棄輪空所在的那場）。全部輪次攤平串接即為完整賽程，總場次恰為 C(count, 2)，且每兩人/兩隊恰對戰一次，不需額外去重邏輯。

**Rationale**：這正是單打與固定搭檔的目標（「每兩人/兩隊恰對戰一次」）與循環法的定義完全吻合，屬於已有標準解法的問題，不需要另外設計貪婪演算法或證明覆蓋率。額外好處：循環法每一輪產生的比賽彼此天生無衝突（同一輪內任何人/隊最多出現一次），將這些輪次依序攤平寫入賽程表後，多個場地同時消耗賽程表前段時，天然不太需要跳過（見 #4）就能拿到不衝突的比賽，場地利用率較單純字典序枚举（如 1v2, 1v3, 1v4, ...）更好——字典序枚举會讓第 1 位球員连续出现在前 count-1 筆，其餘場地在賽程表前段幾乎都要跳過涉及第 1 位球員的場次。

**Alternatives considered**：
- 單純雙迴圈窮舉 `for i in players: for j in players[i+1:]: yield (i, j)`——場次集合結果與循環法相同（皆為 C(n,2) 組合），但賽程表前段幾乎全部包含同一位球員，多場地消耗初期需要頻繁跳過（見 #4），場地利用率明顯較差；循環法零成本換取更好的體驗，故採循環法。
- 隨機打亂配對順序——同樣能產生正確的 C(n,2) 組合，但不保證每個批次無衝突，且排序不可重現、不利測試斷言；循環法排序固定、可重現，更利於單元測試驗證。

## 2. 決議：個人混搭循環賽採「多波次貪婪迴圈」，重用既有兩階段配對函式

**Decision**：個人混搭循環賽（每個人都要跟其他每個人搭檔過一次）在數學上屬於「whist tournament / 社交高爾夫球問題」一類的組合設計問題，只在特定人數條件下存在完美解，不存在通用構造公式。本 feature 採務實的多波次貪婪迴圈，完全重用 `algorithms.py` 既有的兩個函式，不新增新的配對演算法：

1. 每一波（wave）：
   - 以目前的 `pair_count_lookup`（讀 `PairHistory`，含本次 Round 生成過程中已寫入但尚未 commit 的新場次，因 `create_match_with_participants` 在同一交易內 `flush()` 後即可被同交易的後續查詢讀到）呼叫既有 `stage2_pair_players(active_player_ids, pair_count_lookup)` 決定本波的搭檔（隊伍）。
   - 呼叫既有 `team_matchup_stage2(teams, pair_count_lookup)` 決定本波的隊伍對戰組合。
   - 對本波每一組對戰呼叫既有 `create_match_with_participants(..., status="queued")`，`PairHistory` 隨之立即累加（既有行為，見 003 research.md #5，不變）。
2. 重複步驟 1，直到停止條件成立（見下）。

**停止條件**（避免人數不滿足完美覆蓋條件時無限迴圈）：
- 「本次 Round 生成過程中已形成過的隊友組合」集合（見 #3，執行期狀態，非資料表）涵蓋全部 C(n,2) 種可能組合，或
- 某一波未產生任何「這是這對玩家在本次生成過程中第一次成為隊友」的新組合即停止（不寫入該波比賽）。由於每一波的貪婪結果純粹是當下 `PairHistory` 數值的決定性函式，沒有寫入新比賽就代表輸入完全不變，再跑一次必然得到一模一樣的結果——不需要「連續兩次」才能確認已經卡住。

達到停止條件時即結束生成，賽程表所有已產生波次的比賽攤平即為本輪完整賽程；未能 100% 覆蓋的情況下，以「已產生波次中盡量減少重複搭檔次數」作為 spec SC-001 所稱之最大可行覆蓋。

**Rationale**：完全重用既有 003 已實作、已測試、已被 `fair_rotation`（雙打）與現行 `individual_mixed` dispatch 共用的兩個核心函式，符合原則 VI（不重複發明新演算法）與 spec Assumptions 中「沿用專案既有貪婪演算法、非全域最佳解」的既定設計哲學；停止條件以「連續無進展」偵測取代嘗試證明數學可行性，實作成本低且對任何人數輸入皆能在有限步驟內終止。

**Alternatives considered**：
- 實作精確的組合設計演算法（例如 Kirkman 系統構造）以保證特定人數下的完美覆蓋——已否決，複雜度與既有專案「貪婪法、非最佳解可接受」的哲學不符，且僅在特定人數下才有封閉解，一般化仍需 fallback 邏輯，等於還是要實作本方案的多波次貪婪迴圈作為後盾，不如直接採用單一方案。
- 以固定波次數上限（例如 n-1 波，仿循環法的執行次數）取代「連續無進展」偵測——已否決，個人混搭的搭檔決定同時受隊伍對戰配對的貪婪結果影響，執行次數與人數的關聟不像循環法那樣有簡單封閉式關係，「連續無進展」的偵測方式對任何人數皆穩健、不需要另外推導波次數公式。

## 3. 決議：「本次 Round 生成中已形成過的隊友組合」為執行期暫存狀態，不落地為新資料表

**Decision**：#2 停止條件所需的「這對玩家是否已在本次生成中當過隊友」判斷，於 `generate_next_round()` 執行期間以記憶體中的 Python `set[tuple[uuid.UUID, uuid.UUID]]`（標準化為 `(min_id, max_id)` 排序後的 tuple）追蹤，隨每一波新建立的比賽即時寫入該 set；函式執行結束（Round 生成完畢）後即捨棄，不持久化。

**Rationale**：這個集合只在單次 Round 生成過程中有意義（判斷「這一輪還有沒有覆蓋到的搭檔組合」），Round 產生完畢後其資訊已完整反映在該輪所有 `Match`/`MatchParticipant` 紀錄中，之後任何人想知道「這一輪誰跟誰搭檔過」都可以直接查詢當輪的 `Match` 資料重建，不需要額外持久化一份會隨時間增長、且只有生成當下用得到的暫存狀態；避免無謂的資料表與遷移成本（符合原則 VI 精神，不引入非必要的持久化結構）。

**Alternatives considered**：
- 沿用既有 `PairHistory` 數值判斷覆蓋——已否決，`PairHistory` 计数語意为「同场比赛任两人皆计一次」，不區分隊友與對手（003 research.md #5），無法單獨反映「是否已當過隊友」，會誤判已對戰但未搭檔過的組合為「已覆蓋」。
- 另建一張持久化的 `partner_coverage`／`round_pairings` 表——已否決，如上所述、當輪的覆蓋狀態可完全由既有 `Match`/`MatchParticipant` 重建，新增表格屬於重複儲存同一份資訊，不符合資料正規化與精簡原則。

## 4. 決議：場地領取排隊中比賽時，新增「跳過任何參與者正在其他場地進行中」的可行性檢查

**Decision**：既有 `pull_queued_match_for_court(session, group_id, round_number, court_id)`（見 003）原本邏輯是「該 round_number 底下任一 `status='queued'` 的比賽即可領取」；本 feature 修改其查詢，加入條件：候選比賽的所有 `MatchParticipant` 對應的 `roster_entry_id`，都不可出現在同團「目前 `status='in_progress'` 的其他比賽」的參與者名單中。查詢邏輯調整為：依原本排序（建立順序）逐一檢查候選比賽，取第一筆通過此條件的比賽；找不到任何一筆通過條件的候選時，維持原本「查無可領取比賽」的行為（回傳 `None`，場地顯示等待狀態）。

**Rationale**：這是 spec FR-005 的直接落實——循環賽賽程下同一位球員會被排入多場尚未上場的比賽，若不檢查就領取，可能讓同一人同時出現在兩個場地的進行中比賽（分身重複上場），違反 spec SC-002 與現實世界的物理限制。採用循環法生成單打/固定搭檔賽程（#1）已讓賽程表前段大多數情況下不需要跳過；此檢查是保證正確性的必要防線，而非取代 #1 的排序優化。

**Alternatives considered**：
- 只在生成階段保證不衝突、消耗階段不做檢查——已否決，無法涵蓋「多場地非同步消耗導致原本不衝突的批次被打亂」的情況（例如場地 A 提前結束、跳過原本該由它消耗的批次，改領取後面批次的比賽，可能與場地 B 目前正在進行的比賽衝突），消耗階段的檢查是唯一能在任何消耗順序下都保證正確性的方式。
- 消耗階段偵測到衝突時直接跳過整批（而非逐筆檢查下一筆）——已否決，賽程表批次界線只在生成演算法內部有意義，消耗端沒有必要感知「批次」概念，逐筆檢查下一筆候選更簡單、且不需要額外欄位標記批次歸屬。

## 5. 決議：`wait_count`／`stage1_select_players`／`team_stage1_select` 停止在三種演算法機制的 Round 生成路徑上被呼叫，僅保留給手動安排模式

**Decision**：`generate_next_round()` 內，`fair_rotation`（含個人混搭 dispatch）與 `fixed_partner` 分支不再呼叫 `_get_active_roster_for_selection`/`stage1_select_players`/`team_stage1_select`/`apply_wait_count_updates`；改為直接對「當時所有在場（`status='active'`）的輪替名單成員／隊伍」生成完整循環賽賽程（見 #1、#2）。`manual_assign()`（手動安排模式的既有函式）與其對 `apply_wait_count_updates` 的呼叫完全不變。既有 `wait_count` 欄位本身不刪除、不遷移，僅停止在這三種機制下被寫入與讀取作為排序依據；其數值在切換到演算法機制後會維持切換當下的最後數值，不再變動。

**Rationale**：spec Assumptions 已明確「完整循環賽本身已保證所有人機會均等，`wait_count` 的優先上場排序用途在演算法排程機制下不再需要」；手動安排模式仍以「單場、逐次指定上場者」為模型，`wait_count` 對它而言仍是唯一的公平性依據，繼續保留其既有行為。前端（`admin-page.component.html` 的 `member.wait_count` 徽章）需要一併調整為「僅在 `scheduling_mechanism === 'manual'` 時顯示」，否則會顯示凍結不變的過期數字——此為前端任務，將於 `/speckit-tasks` 展開，不在此重新設計 UI。

**Alternatives considered**：
- 讓 `wait_count` 在演算法機制下持續依「本輪是否出場」更新（例如每輪結束後全體歸零）——已否決，循環賽下每個人在同一輪內通常會打好幾場、不存在「這一輪完全沒上場」的個人概念（除非在場人數不足以配對，屬例外情況），持續更新一個「總是接近 0」的數字沒有實質資訊價值，徒增寫入成本。
- 直接刪除 `wait_count` 欄位——已否決，手動安排模式仍依賴此欄位，刪除會是破壞性變更且超出本 feature 範圍（spec 未要求變更手動安排模式）。

## 6. 決議：新增 `Group.partner_source`（`manual`/`auto`）欄位，兩種來源切換互不清除對方資料

**Decision**：`groups` 表新增 `partner_source` 欄位（字串列舉 `'manual'` | `'auto'`，預設 `'manual'`，僅在 `scheduling_mechanism = 'fixed_partner'` 時有意義）。`partner_source = 'manual'` 時，隊伍組成沿用既有 `Partnership` 表（管理員於搭檔設定畫面手動指定，行為完全不變）；`partner_source = 'auto'` 時，隊伍組成於每次 Round 生成當下即時計算（依 `PairHistory` 配對次數最少原則，重用既有 `stage2_pair_players`），不寫回 `Partnership` 表。管理員切換 `partner_source` 值本身不觸發 `Partnership` 資料的新增、修改或刪除；切回 `'manual'` 時直接讀取切換前既有的 `Partnership` 資料。

**Rationale**：直接落實 spec FR-008～FR-010 與兩則 Clarifications 決議（保留手動搭檔設定功能、切換來源不遺失資料）。用一個欄位表達「目前生效的搭檔來源」是最小變更；不將自動配對結果寫回 `Partnership` 表，是因為 `Partnership` 這張表在既有 003 spec 的語意就是「管理員手動指定、跨 Round 持續生效的固定搭檔」，自動配對的結果本質是「每次 Round 生成時即時決定、下次生成可能不同」的暫時性資料，寫回會混淆兩種語意、也會在切回手動模式時污染管理員原本的手動設定。

**Alternatives considered**：
- 用 `Partnership.source` 欄位標記每一筆搭檔紀錄是手動或自動產生，共用同一張表——已否決，自動配對每次 Round 都可能改變，若寫入 `Partnership` 表（該表 `player_a_id`/`player_b_id` 皆有 `unique` 約束，語意上是「一人只能有一組固定搭檔」），每次自動重新配對都要先刪除舊紀錄再新增，且與「手動設定應保留」的需求互相打架，複雜度明顯高於新增一個團層級列舉欄位。
- 在切換為 `'auto'` 時清空 `Partnership` 表——已否決，直接牴觸 spec 的 Clarifications 決議（保留手動設定資料）。

**命名澄清（避免與既有函式混淆）**：`group/router.py` 既有的 `auto_pair_on_enter_fixed_partner()` 是「切換進入 `fixed_partner` 機制、或有新成員落單時，依加入順序自動兩兩配對一次、寫入 `Partnership` 表」的既有一次性初始化邏輯（003 既有行為），只在 `partner_source = 'manual'` 情境下作為「管理員尚未手動調整前的預設值」持續使用、完全不變。本節新增的 `partner_source = 'auto'` 是**不同**的機制：每次 Round 生成都重新計算、依 `PairHistory` 最小化重複、且不寫入 `Partnership` 表。實作時 MUST 用不同的函式名稱（例如 `compute_auto_partner_teams_for_round()`）以避免與既有 `auto_pair_on_enter_fixed_partner()` 混淆。

## 7. 決議：`round_is_complete()` 與 Next Round 悲觀鎖/捨棄邏輯不需修改

**Decision**：既有 `round_is_complete(session, group_id, round_number)`（檢查該 `round_number` 底下所有 `Match` 是否皆達終態）與 `generate_next_round()` 的悲觀鎖（`_lock_group_for_round_generation`）、`abandon_group_matches()` 呼叫順序，在新的完整循環賽模型下語意依然成立且不需要修改——差別只在於「該 `round_number` 底下的 `Match` 數量」從「場地數量」變成「C(n,2) 或多波次總和」，判斷邏輯本身（`COUNT(*) WHERE status NOT IN ('completed','abandoned')`）不受影響。

**Rationale**：避免不必要的改動範圍，符合最小變更原則；確認這兩處既有邏輯的正確性不依賴「一輪固定等於場地數場比賽」這個即將被推翻的假設，只依賴「同一 `round_number` 底下的所有比賽」這個不變的資料模型事實。

**Alternatives considered**：（無——確認不需修改後不存在需要比較的替代方案。）

## 8. 待處理事項：003/005 既有 spec 與測試的過時假設

**Decision**：`specs/003-schedule-rotation`（data-model.md 的 `current_round_number` 語意、quickstart.md 情境 1 之預期產出場次數）與 `specs/005-member-view`（research.md #2 已在 011-spec 撰寫時同步修正，見 spec.md 之 Assumptions）中，凡是基於「一輪＝場地數場比賽」推導出的具體數字或斷言，將隨本 feature 實作失真；哪些檔案、哪些段落、對應哪些既有測試檔案需要更新，於 `/speckit-tasks` 階段以任務清單逐一列出並指派，本研究文件僅記錄「已知會失真」這個事實與其成因（即 #1、#2、#5 三項演算法決議本身），不在此重複列出既有測試的行號清單。

**Rationale**：`/speckit-plan` 階段的產出是設計決策而非任務分解；既有文件/測試的盤點與修訂屬於可獨立追蹤、獨立驗收的工作項目，適合放在 `tasks.md` 以可勾選的任務呈現，避免研究文件與任務清單重複維護同一份清單造成之後不同步。
