# Research: 即時計分板與控制板

## #1 MatchResult 不是獨立資料表

**Decision**：延用 `specs/architecture.md`（第 92 行）已定案的決策——`Match` 與
`MatchResult` 合併為單一 `matches` 資料表，`matches.winner_team`（nullable）
欄位承載「結果」：僅當 `status = 'completed'` 時填入 `'A'`/`'B'`，
`abandoned`/`queued`/`in_progress` 皆為 `NULL`。戰績/對戰紀錄查詢（未來
005 spec 範圍）一律加上 `WHERE status = 'completed'` 篩選。

**Rationale**：spec 的 Key Entities 段落沿用「MatchResult」一詞，但這是
003/007 共同依賴的既有架構決策，非本次需要重新設計的項目；本 feature 只需
遵守「提前結束不寫入 `winner_team`」這條規則即可滿足 FR-009 的「不產生
MatchResult」語意。

**Alternatives considered**：新建獨立 `match_results` 表——已在 architecture.md
明確否決（讀寫時機高度重疊，拆表徒增交易複雜度），不重新評估。

**影響**：本 feature **不需要新的 Alembic migration**——`matches` 表已具備
`score_a`/`score_b`/`winner_team`/`status`/`target_score`/`deuce_threshold`/
`cap_score`/`ended_at` 等全部必要欄位（見 003 之
`apps/api/app/domains/schedule/models.py`）。

## #2 達標判定公式：`deuce_threshold` 於執行期實際上不參與運算

**Decision**：勝負判定公式為：

```text
win(score_x, score_y, target_score, cap_score) :=
    score_x >= cap_score
    OR (score_x >= target_score AND score_x - score_y >= 2)
```

`deuce_threshold` 欄位**不**出現在此公式中——它只在 001 的 `/groups`
建團驗證（FR-014：`deuce_threshold <= target_score`、`cap_score >=
deuce_threshold`）與快照時使用，執行期判定不需要它。

**Rationale**：交叉比對 001 spec 的兩組固定預設值可驗證公式成立：
- 21 分制（target=21, deuce=20, cap=30）：21:19 時 `score>=21 且
  lead=2`→勝；20:20 後未達 21 分前公式恆為假（需等到 lead>=2）；21:20
  未達成 lead>=2（lead=1）不判定，直到 22:20 或觸及 30 分封頂為止——與
  spec FR-013 描述完全一致。
- 15 分制（target=15, deuce=14, cap=21）：15:13 判勝；20:20 後直到
  21:20（觸及封頂）判勝——同樣一致。

由於兩組預設值恰好滿足 `deuce_threshold = target_score - 1`，公式無需
顯式讀取 `deuce_threshold` 即可正確處理「20:20 才進入需 lead 2 分模式」
的行為——這是 `score >= target_score` 條件本身自然蘊含的結果，非巧合而是
badminton 標準賽制的數學特性（deuce 門檻恆等於目標分數 - 1）。自訂模式下
即使 `deuce_threshold` 与 `target_score - 1` 不同，此公式仍是唯一與
FR-014 之驗證規則（`deuce_threshold <= target_score`、`cap_score >=
target_score`）邏輯一致的判定方式。

**Alternatives considered**：顯式讀取 `deuce_threshold` 判斷「是否進入
deuce 模式」再切換判定邏輯——被否決，因為會與上述公式在所有合法輸入下
產生相同結果，純屬不必要的額外分支。

## #3 控制板操作端點僅接受 `control_panel_token`，不接受 `scoreboard_token`

**Decision**：+1/-1、提前結束等**寫入**端點，MUST 僅接受 `control_panel_token`
解析出的場地；若以 `scoreboard_token` 呼叫，MUST 回傳 `LINK_NOT_FOUND`
（視同該 token 對此操作不存在，而非洩漏「這是唯讀連結」的細節）。既有
`court.service.get_court_by_token()`（002 建立）會把兩種 token 都解析為
同一個場地物件並回傳 `link_type` 供呼叫端自行判斷——007 的寫入端點 MUST
在取得 `link_type` 後檢查其為 `"control_panel"`，不符合則拒絕。

**Rationale**：憲章原則 IV 明確要求「無需驗證即可開啟的畫面不可提供管理員
專屬操作」，雖然本情境不是管理員操作，但同一設計精神適用——002 刻意把
計分板與控制板設計成兩組獨立 token 就是為了讓「唯讀分享」與「可操作」
權限分離（例如管理員可以把計分板連結投影在螢幕上公開分享，而不必擔心
任何看到投影的人都能因此拿到操作權）。若寫入端點不區分 token 類型，將
完全架空這個既有的權限邊界設計。

**Alternatives considered**：兩種 token 都允許操作——被否決，違反上述
既有設計意圖，且 spec 驗收情境本身也隱含控制板與計分板是兩種不同權限
等級的畫面。

## #4 加減分請求 MUST 攜帶 `match_id`，不可由後端自行判斷「場地目前這場」

**Decision**：`POST .../score`、`POST .../end` 等寫入端點的路徑（或請求體）
MUST 包含前端當下持有的 `match_id`；原子 SQL 的 `WHERE` 子句 MUST 以
`Match.id = :match_id AND Match.status = 'in_progress'` 為準，MUST NOT
改以「查詢該場地目前 in_progress 的比賽」再操作。

**Rationale**：spec Edge Cases 明確描述「延遲送達的 +1 請求，此時場地
已經開始下一場比賽」的情境，MUST 視為無效操作、MUST NOT 誤改到新比賽的
分數。若後端以「場地目前這場」為準而非以請求攜帶的 `match_id` 為準，
延遲的舊請求會被錯誤地重新導向套用到全新的比賽上——這不是「拒絕」而是
「打錯對象」，比不生效更嚴重。前端在收到 `rotation.updated`／`match.ended`
事件或呼叫 state 端點時更新本地持有的 `match_id`，之後的操作一律使用
最新持有值；若使用者裝置上仍殘留舊 `match_id` 送出請求，後端的
`WHERE id = :match_id AND status = 'in_progress'` 自然無法命中（該筆
`match_id` 現在狀態已是 `completed`/`abandoned`），構成天然的 no-op。

**Alternatives considered**：後端查場地目前比賽——已否決，見上。

## #5 +1/-1 與提前結束之原子 SQL 樣式

**Decision**：三種寫入動作皆採「單一 `UPDATE ... WHERE ... RETURNING`」
達成 FR-005/FR-006/FR-006a/FR-007 之防呆，範例（SQLAlchemy Core，非
ORM `.flush()` 後續讀取）：

```sql
-- +1（A 方）
UPDATE matches
SET score_a = score_a + 1
WHERE id = :match_id AND status = 'in_progress'
RETURNING score_a, score_b;

-- -1（A 方，FR-005 下限防呆一併於同句達成）
UPDATE matches
SET score_a = score_a - 1
WHERE id = :match_id AND status = 'in_progress' AND score_a > 0
RETURNING score_a, score_b;

-- 提前結束（FR-006a）
UPDATE matches
SET status = 'abandoned', ended_at = now()
WHERE id = :match_id AND status = 'in_progress'
RETURNING id;
```

`rowcount = 0` 一律代表「無效操作（no-op）」——比賽已終態、或（`-1`
情境下）分數已在下限。呼叫端一律回傳 200（非 4xx），以 response body 的
`applied: bool` 欄位告知前端該次操作是否真正生效（研究 #9）。

達標判定（FR-003）**不**塞進同一句 `UPDATE`——`+1`/`-1` 的原子句只負責
FR-005/006/006a 的邊界防呆；`+1` 命中（`rowcount=1`）後，服務層在
**同一個資料庫交易**內讀取 `RETURNING` 回傳的最新比分，套用研究 #2 之
判定公式，若達標則在同一交易內再執行第二句 `UPDATE ... SET status =
'completed', winner_team = :side, ended_at = now() WHERE id = :match_id
AND status = 'in_progress'`（同樣帶 `status = 'in_progress'` 防呆，避免
理論上的 TOCTOU）。兩句 `UPDATE` 在同一交易、commit 前完成，對外仍是
單次原子的「使用者可觀察狀態轉換」，FR-007 要求的是「防呆不可拆成應用層
額外查詢再判斷」，而非「整個請求只能有一句 SQL」——比分遞增與達標後的
狀態轉換本來就是兩個不同語意的寫入。

**Alternatives considered**：把達標判定也塞進第一句 `UPDATE` 的 `CASE
WHEN` 子句——被否決，複雜度過高、可讀性差，且 FR-007 的防呆要求範圍
明確限定在 FR-005/006/006a（邊界與終態防呆），不含 FR-003 的達標轉換。

## #6 比賽結束後場地行為：重用 003 已預留的兩個 hook

**Decision**：任何一種終態轉換（達標 `completed`、提前結束 `abandoned`）
成功後，服務層依序呼叫：

1. `advance_court_after_match_ends(session, match)`（003 已建立，
   `apps/api/app/domains/schedule/service.py:477`——docstring 明確寫著
   「called once a match has reached a terminal state (by 007's scoring
   endpoints, once they exist)」）——演算法排程機制下自動領取賽程表下一場
   排隊中的比賽並綁定該場地；手動安排模式下為 no-op。
2. `check_round_complete_and_maybe_auto_advance(session, group)`（003
   已建立，`service.py:493`）——若 Auto Next Round 已開啟且本輪所有比賽
   皆已終態，自動產生下一輪（內部已包含 `generate_next_round` 的完整
   commit + Ably 廣播）。

兩者皆在**同一個資料庫交易**內、於 `advance_court_after_match_ends` 尚未
commit 前依序呼叫（`check_round_complete_and_maybe_auto_advance` 內部的
`generate_next_round` 會自行 commit，只在真正觸發自動進下一輪時才發生）。

**Rationale**：003 的 plan.md（第 114 行）明確寫著「比賽本身的計分、勝負
判定、`MatchResult`／`winner_team` 寫入邏輯屬 007 spec 範圍；本 feature
僅提供 `advance_court_after_match_ends(session, match)` 供其呼叫」——這是
003 對 007 的明確承諾介面，直接重用，不重新實作「領取下一場比賽」或
「Round 是否完成」的邏輯。

## #7 Ably 事件：新增 2 個，重用既有 2 個

**Decision**：

- 新增 `match.scoreUpdated`（+1/-1 命中、比賽仍 `in_progress`）
- 新增 `match.ended`（比賽轉為 `completed` 或 `abandoned`，payload 內含
  `waiting_reason` 欄位——若同一次交易緊接著發布了 `rotation.updated`
  則為 `null`，否則為 `"no_queued_match"` 或 `"manual_assignment"`，
  讓前端不需額外等待/猜測即可立即顯示正確的「即將登場」或「等待」畫面）
- 重用既有 `rotation.updated`（003 之 `ably-events.md` 已明確定義其
  觸發時機包含 `advance_court_after_match_ends` 領取下一場比賽的情境，
  本 feature 只需在該情境發生時實際呼叫既有的發布邏輯）
- 重用既有 `match.nextRound`（`check_round_complete_and_maybe_auto_advance`
  觸發自動進下一輪時，`generate_next_round` 內部已自行發布，不需 007
  重複發布）

**Alternatives considered**：把 `match.ended` 的「下一步」資訊拆成獨立
事件由前端自行組合——被否決，徒增前端狀態機複雜度且有短暫顯示錯誤
「等待」畫面又立刻被 `rotation.updated` 覆蓋的閃爍風險（研究 #7 之
`waiting_reason` 內嵌設計即為避免此問題）。

## #8 前端斷線重連：擴充既有 `RealtimeService.connectionState` 訂閱模式

**Decision**：計分板、控制板（兩種模式）、管理頁場地控制區塊，皆新增一段
`effect()`（或等效訂閱）觀察 `RealtimeService.connectionState`：

- 非 `'connected'` 狀態（`'disconnected'`/`'suspended'`/`'failed'`/
  `'connecting'`/`'closing'`/`'closed'`）→ 顯示斷線提示 UI（FR-022）；
  控制板類畫面額外停用或警示 +1/-1/提前結束按鈕（FR-023）。
- 狀態從非 `'connected'` **轉為** `'connected'`（曾經斷線後恢復，非初次
  連線）→ 觸發一次對應範圍的 state 端點重新拉取（研究 #11 之
  `GET .../state`），並以其結果**強制覆蓋**本地暫存（FR-024）。

此邏輯抽成共用的 `useReconnectRefetch`-等效 Angular service/composable
（研究命名待 tasks.md 展開時定案），避免四個畫面（計分板/單場地控制板/
全部場地控制板/管理頁場地控制區塊）各自重複實作同一段判斷。

**Rationale**：`RealtimeService.connectionState` signal 與其背後的 Ably
connection state machine（002 已建立，`ably.service.ts`）已完整涵蓋
「連線中/已連線/斷線/嘗試重連中」等所有必要狀態，不需要額外引入自訂的
心跳/超時判斷機制；FR-021~025 純粹是「觀察既有狀態 + 在特定轉換時機
觸發既有 GET 端點」的應用邏輯，不需要新的即時通訊基礎設施。

**Alternatives considered**：獨立實作 WebSocket ping/pong 心跳偵測斷線
——被否決，Ably SDK 的 `connection.on()` 已提供更完整且經過驗證的狀態
機，重複實作純屬多餘。

## #9 寫入端點回應：一律 200 + `applied: bool`，不用 4xx 表示「無效操作」

**Decision**：+1/-1/提前結束等寫入端點，只要 `match_id` 能被解析
（存在且屬於該 token/場地），一律回傳 `200`；回應 body 以 `applied: bool`
欄位區分「本次操作是否真正生效」，同時附上該筆比賽當下的最新
`score_a`/`score_b`/`status`/`winner_team`，讓前端不論 `applied` 為何都能
直接以回應內容校正畫面（不需要額外一次 GET）。

**Rationale**：FR-006/FR-006a 明確定義「延遲送達的請求視為無效操作
（no-op）」——這是業務邏輯上的正常情境（網路延遲本來就會發生），不是
客戶端的錯誤請求，用 4xx 表示語意不符；同時 200 + 最新狀態的設計讓前端
可以用同一份回應「順便」校正畫面，即使 Ably 事件因網路问题延遲抵達也有
一層保底。

**Alternatives considered**：無效操作回傳 409 Conflict——被否決，409
通常代表使用者需要採取行動（例如重新整理再試），但此處對使用者而言
「沒發生任何錯誤，只是這次點擊不巧慢了一步」，不需要特殊錯誤處理 UI，
分類為錯誤反而增加前端不必要的錯誤分支。

## #10 管理頁「場地控制」區塊：重用同一組服務函式，改走管理員驗證路徑

**Decision**：管理頁內建的場地控制區塊，其 +1/-1/提前結束操作 MUST
透過**另一組**（管理員驗證版本的）路由觸發，但路由 handler 直接呼叫與
公開控制板完全相同的服務層函式（`apply_score_delta()`／
`end_match_early()`），僅差在「如何解析出 `court`／`group`」這一步——比照
`schedule/router.py` 既有的 `_admin_court()` dependency 模式（管理 PIN
session + `group_id`/`court_id` path 參數），而非 `court.service
.get_court_by_token()`。狀態顯示（比分/Round/即將登場）則直接擴充既有
`GET /groups/{group_id}/schedule`（`ScheduleResponse`）——在
`MatchSummary` 補上 `score_a`/`score_b`，`CourtScheduleStatus` 補上
`next_up`（下一場排隊中比賽的參賽者預告，`null` 時比照 `waiting_reason`
語意），不另外新增一個管理頁專屬的 state 端點。

**Rationale**：憲章原則 VI（可維護性/模組化）與原則 IV（管理員操作 MUST
僅存在於管理頁、MUST NOT 與 Guest 端共用同一套機制）在此看似矛盾——
但「共用同一套機制」指的是**驗證機制**（PIN 驗證 vs 通關密碼驗證
MUST NOT 共用同一套程式碼路徑，這是原則 IV 明確講的是「認證」層級），
不是「業務邏輯」層級；比分加減的業務規則（原子防呆、達標判定、捨棄規則）
對管理員和一般控制板操作者而言是完全相同的規則，若各自重複實作一份，
才是真正違反原則 VI 的模組邊界要求（邏輯分裂、未來修改需要改兩處）。
管理頁的 `GET /groups/{group_id}/schedule` 本來就已經是admin-only、需要
PIN session 才能呼叫的既有端點，擴充其欄位不會意外把管理資訊外洩到
公開端點。

**Alternatives considered**：管理頁場地控制區塊改為直接嵌入 iframe 指向
控制板 URL——被否決，控制板 URL 本身無需登入，嵌入後等同繞過管理頁的
PIN 驗證邊界，且無法與管理頁其餘狀態（例如同畫面的 Next Round 按鈕）
共享即時資料。

## #11 「即將登場」預告：唯讀 peek，不重用 `pull_queued_match_for_court` 的鎖定/寫入版本

**Decision**：新增一個唯讀輔助函式（暫名 `peek_next_queued_match`），
`WHERE` 子句與既有 `pull_queued_match_for_court`（`service.py:208`）的
「找出這個場地/這一輪最早建立的 `queued` 且 `court_id IS NULL` 比賽」
邏輯相同，但**不**呼叫 `.with_for_update()`、不修改 `court_id`/`status`，
單純 `SELECT ... LIMIT 1` 供 `GET .../state` 端點組出「即將登場」欄位。

**Rationale**：預告本身是唯讀展示用途，混用會鎖定資料列的寫入版查詢
（`with_for_update(skip_locked=True)`）純屬不必要的鎖競爭來源，尤其
`GET .../state` 端點是斷線重連時的高頻呼叫路徑（研究 #8），不應該與
真正的「領取比賽」寫入路徑爭搶同一批列鎖。

**Alternatives considered**：重用 `pull_queued_match_for_court` 但立刻
回滾——被否決，多餘的鎖獲取/釋放對高頻讀取端點是不必要的效能負擔，且
`with_for_update` 需要包在明確交易邊界內，混用會讓這個唯讀函式的呼叫
慣例變得不一致。
