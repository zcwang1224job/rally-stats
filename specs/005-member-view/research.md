# Research: 團內成員視圖

## #1 「Round 開始時間點」需要新增一張 `round_history` 表

**Decision**：新增 `round_history(group_id, round_number, started_at)` 表，於
003 既有的 `generate_next_round()`（`apps/api/app/domains/schedule/service.py`）
內、`group.current_round_number += 1` 之後、commit 之前，插入一筆
`(group.id, group.current_round_number, now())`。FR-008 判定「已離開」狀態
時，直接查詢此表取得對應輪次的 `started_at`。

**Rationale**：FR-008 明確要求「已離開」狀態的判定基準 MUST 是「該輪
開始的時間點」，且 MUST 對演算法排程機制與手動安排模式一視同仁——但
目前系統完全沒有任何地方記錄「第 N 輪是什麼時候開始的」：`groups` 表
只有 `current_round_number`（純數字），`matches.created_at` 只在演算法
模式下、Round 產生的當下才會被寫入，手動安排模式下 `matches` 是admin
之後才個別呼叫 `manual-assign` 建立，時間點可能遠晚於「這一輪開始」的
真正時刻，兩種模式無法共用同一套推導邏輯。唯一在四種排程機制下皆
一致存在的事件，是 `generate_next_round()` 本身被呼叫、
`current_round_number` 遞增的那一刻——這正是 spec 定義的「該輪編號
正式生效的時刻」，因此需要在此處新增一筆持久化紀錄。

第 1 輪也會有一筆 `round_history` 紀錄：`generate_next_round()` 該團
第一次被呼叫時，`current_round_number` 維持在群組建立時的預設值 `1`
（不遞增），產生的就是第 1 輪本身——見 research.md #2。

**Alternatives considered**：
- 用 `matches.created_at` 的 MIN 值推算 Round 開始時間——已否決，手動
  安排模式下不成立（見上）。
- 在 `groups` 表新增單一 `current_round_started_at` 欄位（只存「目前
  這一輪」的開始時間，不留歷史）——已否決，戰績表需要「每一輪各自的」
  開始時間以逐輪比對 `left_at`，單一欄位無法回溯查詢已過去的輪次。

## #2 「已發生的 Round」範圍：以 `round_history` 實際存在的紀錄為準

**Decision**：戰績頁／賽程頁所稱「各個已發生 Round」，就是該團所有
`round_history` 列所記錄的 `round_number`（依序排列；含目前這一輪，
若仍有進行中/排隊中比賽則以 FR-010 之「未上場」暫時顯示）。group
剛建立、管理員還沒按過任何一次 Next Round 時，`round_history` 沒有
任何紀錄，戰績表格自然為空陣列——不需要額外用 `current_round_number`
的數值範圍去回推。

**Rationale**：早期設計曾讓 003 的 `generate_next_round()` 在第一次
呼叫時就把 `current_round_number` 從預設值 `1` 直接遞增為 `2`，導致
「第 1 輪」變成一個從未真正產生任何比賽的占位狀態、玩家實際打的第一輪
比賽被誤標為「第 2 輪」——這不只讓戰績表格的欄位編號對不上使用者認知
的「第幾輪」，前台「按下 Next Round 開始比賽」的體驗上也等於第一次按
按鈕就跳過了第 1 輪。修正後，`generate_next_round()` 第一次為某團
呼叫時維持 `current_round_number = 1`（產生的就是真正的第 1 輪），
之後每次呼叫才 `+= 1`；`round_history` 也隨之从第 1 輪起、每輪都有一筆
紀錄。戰績範圍直接讀 `round_history` 的既有列，不必再對
`current_round_number` 做任何偏移運算，也不會有「有列但不在範圍內」
或「在範圍內但沒列」的不一致。

**Alternatives considered**：維持「範圍從 2 起」的舊規則、把
`generate_next_round()` 的遞增時機保留不動——已否決，這正是「按下
Next Round 就跳過第 1 輪」問題的根源，且對外顯示的輪次編號從第一次
生成起就與使用者實際認知的「這是第幾輪」錯開一位。

## #3 `RosterEntry.left_at` 需要新增欄位

**Decision**：`roster_entries` 新增 `left_at: TIMESTAMPTZ | NULL` 欄位。
003 既有的 `handle_member_left()`（`schedule/service.py`，目前僅設定
`entry.status = new_status`）擴充為同時設定 `entry.left_at =
datetime.now(UTC)`。

**Rationale**：FR-008 之「已離開」判定公式為「`left_at` 早於或等於
該輪 `round_history.started_at`」——若不記錄離開的精確時間，無法與
各輪開始時間比較先後順序。`status` 欄位本身只能表達「現在是否已離開」
這個二元狀態，不含時間資訊。

**Alternatives considered**：無——這是 FR-008 判定公式的必要前提，
沒有功能等價的替代方案。

## #4 戰績狀態判定：四狀態公式（不需要額外狀態機）

**Decision**：對每一位曾出現於 `roster_entries`（不限目前 status）的
成員 E、每一個已發生輪次 R（研究 #2 範圍），依序判定：

```text
1. 若 E.status ∈ {left, kicked} 且 E.left_at <= round_history[R].started_at
   → 「已離開」
2. 否則若 E.joined_at > round_history[R].started_at
   → 「未上場」（涵蓋 FR-007b：包含該成員加入之前、本團尚不存在的所有
      更早輪次）
3. 否則查詢 E 在第 R 輪是否有 MatchParticipant 紀錄：
   - 無 → 「未上場」（FR-007a，候補中）
   - 有，且該場 Match.status == 'completed'
     → 依 E.team 是否等於 Match.winner_team 判定「勝」／「敗」
   - 有，且該場 Match.status == 'abandoned'
     → 「未上場」（FR-007c）
   - 有，且該場 Match.status ∈ {queued, in_progress}
     → 「未上場」（FR-010，僅可能發生於 R == 目前輪次）
```

**Rationale**：由於 `round_history.started_at` 對遞增的輪次編號恆為
非遞減，規則 1 一旦於某輪 R 成立，對所有 R' > R 也必然成立——「已離開
狀態一經出現即固定、不會變回未上場」（FR-008、SC-004）因此是這套判定
公式的自然推論，不需要額外的狀態機或「鎖定旗標」欄位來人為強制此
不可逆性。003 已保證任一輪次一旦不再是「目前輪次」，其所有比賽必為
終態（`generate_next_round()` 呼叫 `abandon_group_matches()` 強制
清空上一輪未完成比賽），故規則 3 的 queued/in_progress 分支僅可能發生
於 R 等於目前輪次的情境，不需要為「過去輪次仍有未完成比賽」這個
不可能發生的情況另寫防呆。

**Alternatives considered**：在 `RosterEntry` 或另建一張表持久化
「每輪每人的戰績狀態」——已否決，上述四條規則已可用既有資料
（`roster_entries` + `round_history` + `matches` + `match_participants`）
即時查詢推導，不需要額外的寫入路徑與資料同步負擔，且與 FR-021（戰績/
對戰紀錄共用同一份底層資料模型）的精神更一致。

## #5 一般成員身分識別：新增「僅需已加入即可」的解析路徑，不重用 `resolve_guest_session`

**Decision**：新增 `resolve_active_roster_membership()`，接受
`group_id` + (`guest_session_token` 或已解碼的 `member_id`) ，僅檢查
`RosterEntry.status == 'active'`，**不**檢查 `Group.status`（不同於
004 既有的 `resolve_guest_session()`，後者額外要求
`Group.status == 'active'`，因為它服務的是「加入/續加入」情境）。

**Rationale**：spec Edge Cases 明確要求「團解散後，一般成員視圖的
戰績/對戰紀錄仍可透過有效連結唯讀查閱」——若沿用
`resolve_guest_session()` 現有的 `Group.status == 'active'` 條件，
團解散後所有 Guest 成員將立即被擋在自己的戰績頁外，違反此要求。
Member 身分則不受此限——已登入會員的 JWT 本來就與特定團無關，僅需
確認其在該團仍有一筆 `active` 的 `RosterEntry`（`active_roster_entry_
for_member()`，004 已建立，直接重用）。憲章原則 IV「有通關密碼的團，
加入前 MUST 驗證密碼才能查看賽程細節」確立了「一般成員視圖」屬於
密碼保護範圍、不可對外公開——因此本規格的所有讀取端點 MUST 透過此
函式驗證呼叫者確實持有該團的有效加入憑證，MUST NOT 僅憑
`group_id`（本身透過 004 之 `GET /groups` 公開可列出）即可存取。

**Alternatives considered**：直接重用 `resolve_guest_session()` 並移除
其 `Group.status` 檢查——已否決，該函式本身是 004 加入流程的一部分，
修改其既有語意有波及 004 現有行為（Guest 重新整理還原狀態）的風險；
新增一個語意單純、專供本 feature 使用的獨立函式更安全，符合原則 VI
（模組間以清楚定義的介面溝通，不共用內部實作細節）。

## #6 賽程頁（一般成員唯讀版）：重用既有 `build_schedule_snapshot()`，新增公開讀取端點

**Decision**：新增 `GET /groups/{group_id}/member-schedule` 端點（或
等效命名，見 contracts/），透過 research.md #5 之身分驗證取代
`require_admin`，直接呼叫既有的 `build_schedule_snapshot(session,
group)`（003/007 已建立，回傳 `ScheduleResponse`，已包含
`score_a`/`score_b`/`next_up`）回傳完全相同的資料結構——一般成員視圖
與管理頁的賽程資料本來就是同一份（spec Assumptions 明確說明「不涉及
資料庫層面的資料隔離或複製」），只是前端呈現時隱藏管理操作按鈕
（FR-002，屬前端關注點，後端無需另建一份精簡回應格式）。即時同步
（FR-004、SC-002）直接訂閱 007 已建立的既有 Ably 頻道
（`court:{group_id}:{court_id}` 之 `match.scoreUpdated`/`match.ended`/
`rotation.updated`/`match.nextRound`，`group:{group_id}:notifications`
之 `member.joined`/`member.left`），不需要新增事件。

**Rationale**：避免為「同一份資料、不同呈現權限」重新設計一套回應
格式，直接複用降低維護成本，且與原則 VI（可維護性）一致——模組邊界
應該畫在「誰可以呼叫」而非「資料長什麼樣子」。

**Alternatives considered**：新建一個精簡版 `MemberScheduleResponse`
（移除管理頁專用欄位）——已否決，`ScheduleResponse` 目前並無任何
管理員專屬的敏感欄位（PIN 碼、密碼明文等從不在此回應中），精簡沒有
安全效益，純屬不必要的重複定義。

## #7 退出組團：重用既有 `handle_member_left()`，新增身分驗證版本的端點

**Decision**：新增 `POST /groups/{group_id}/roster/{roster_entry_id}/leave`
端點，Request body 攜帶 `guest_session_token: str | None`（Guest 情境）；
`Authorization` header 攜帶 Bearer token 則走 Member 情境
（`optional_member` 解析）。服務層先確認呼叫者確實擁有這筆
`roster_entry_id`（Guest token 相符，或 `member_id` 相符），再呼叫
既有 `handle_member_left(session, group, entry, new_status="left")`
（003 已建立，`kick_member()` 也是呼叫同一函式，僅 `new_status`
不同）。回應後，若為 Guest，其 `guest_session_token` MUST 立即失效
（FR-016）——重用既有的失效機制：`handle_member_left` 本身不清除
`guest_session_token` 欄位（該欄位僅用於「查找」，`resolve_guest_session()`
與本規格新增之 `resolve_active_roster_membership()` 皆已檢查
`status == 'active'`，退出後 `status` 變為 `'left'`，token 自然失效，
MUST NOT 額外將 `guest_session_token` 欄位清空或改值——沿用 004 對
「Token 失效」的既有定義：失效 = 查找條件不再成立，而非刪除 token
本身）。

**Rationale**：`kick_member()` 與「一般成員主動退出」在賽程收斂規則上
完全相同（FR-014 明確引用「臨時退出成員的處理」規則，與 003 之
`remove_roster_entry_from_schedule`/`handle_member_left` 是同一套），
唯一差異是「誰有權觸發」——管理員 vs 本人。複用同一個服務函式，新的
路由只需要負責「驗證觸發者就是這個 roster_entry 本人」這一件事。

**Alternatives considered**：另外複製一份退出邏輯——已否決，違反
原則 VI，且會製造「踢除」與「退出」未來各自修改、行為逐漸分歴的風險
（003 的 `handle_member_left` docstring 已明確設計為兩者共用）。

## #8 對戰紀錄／會員跨團彙總：共用同一份查詢基礎，差異僅在篩選範圍

**Decision**：服務層提供一個共用的 `_completed_matches_query()`
建構子（`WHERE status = 'completed'`，JOIN `match_participants`），
依呼叫情境加上不同的 `WHERE` 條件：
- 團內對戰紀錄：`Match.group_id == group_id`
- 會員跨團對戰紀錄：`EXISTS (SELECT 1 FROM match_participants mp
  JOIN roster_entries re ON re.id = mp.roster_entry_id WHERE
  mp.match_id = matches.id AND re.member_id = :member_id)`

跨團彙總統計（總場次/總勝/總敗/勝率）在同一次查詢的基礎上，於應用層
（Python）累加每場比賽中「該會員所屬隊伍是否等於 winner_team」計算，
不另外維護一份彙總快取表。

**Rationale**：直接對應 FR-021（戰績/對戰紀錄 MUST 共用同一份底層
`MatchResult` 資料模型，差異僅在查詢範圍與呈現粒度）；規模上（單一
會員參與的比賽數量）不需要額外的彙總快取層，即時計算即可。

**Alternatives considered**：為跨團彙總統計另建 materialized
view 或彙總表——已否決，規模與更新頻率皆不足以證成額外的快取層
複雜度（YAGNI）。

## #9 Guest 紀錄不可回溯合併：資料模型層面天然滿足，不需額外防呆

**Decision**：FR-020（Guest 紀錄 MUST NOT 被任何會員帳號收錄，且此
規則不可逆）不需要新增任何防呆邏輯——`match_participants.roster_entry_id`
永久指向建立當下的那筆 `roster_entries` 記錄，而 `roster_entries
.member_id` 本身在建立當下就已經是「Guest 加入時為 NULL、會員加入時
為該會員 ID」，且系統中不存在任何「事後把一筆 `roster_entries` 的
`member_id` 從 NULL 改成某會員 ID」的寫入路徑（004/006 皆未提供
「認領」機制）。因此本規格的會員跨團對戰紀錄查詢（`re.member_id =
:member_id`）天然就不會撈到任何 Guest 時期的紀錄，即使該 Guest
日後真的註冊成為會員——因為那是「一筆新的、`member_id` 不同的
`roster_entries` 記錄」（新一次加入行為），與舊的 Guest 記錄之間在
資料庫層面完全沒有關聯欄位可供 JOIN。

**Rationale**：確認現有資料模型（001/004/006 已定案）已經自然滿足
此不可逆規則，不需要在本規格新增任何顯式的「封鎖認領」程式碼——這是
一個需要在 plan 階段明確驗證、寫入文件的既有保證，而非需要新實作的
需求。

**Alternatives considered**：無——此為現狀確認，非設計決策。
