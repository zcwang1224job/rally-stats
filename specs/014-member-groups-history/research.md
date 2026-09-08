# Research: 我的團完整參與紀錄與戰績

7 decisions, all resolving directly from the existing codebase — no new
technology, no new database table.

## 1. 團內完整比賽清單：直接重用既有 `build_group_match_records()`

**Decision**：FR-004（點進某團看到該團所有已完成比賽）直接呼叫既有
`group/service.py` 的 `build_group_match_records(session, group_id, page)`
——005-member-view 建的既有函式，回傳既有 `GroupMatchRecordsResponse`/
`MatchRecordSummary` 形狀，完全不修改。改變的只有「誰能呼叫它」——見決策
#3。

**Rationale**：這正是目前現役成員在 `/groups/{id}/member-view` 的
「對戰紀錄」分頁已經在用的同一支查詢，該團所有比賽（不分是不是自己打的）
本來就是它的既有語意，與 spec FR-004「該團所有已完成比賽」逐字吻合。重用
既有、已上線測試過的函式，不重新發明一套查詢邏輯（憲章原則 VI）。

**Alternatives considered**：另外寫一支「只回傳我自己打過的比賽」的新查詢
——被拒絕，因為 spec FR-004 明確要求的是「該團所有」而非「我自己的」，
且既有函式已完整涵蓋此語意。

## 2. 個人在該團的戰績統計：擴充既有 `build_member_match_records()`

**Decision**：FR-005（我在該團的個人統計）透過在 `member/service.py` 的
`build_member_match_records()` 新增一個預設關閉的 keyword-only 參數
`group_id: uuid.UUID | None = None`——給定時，在既有 `base_query` 多加一條
`Match.group_id == group_id` 篩選，其餘既有邏輯（勝敗計算、win_rate）完全
不變。新的組合端點只取用其計算出的 `total_matches`/`total_wins`/
`total_losses`/`win_rate` 四個欄位，組裝進一個新的精簡回應
（`MemberGroupStatsResponse`），不曝露該函式順便算出的 `round_win_rates`/
`opponent_records`（spec FR-005 只要求「至少」總場次/勝/敗/勝率，這兩者
非必要）。

**Rationale**：避免寫出第三套「算某人在某個範圍內的勝敗場次」邏輯——
`build_member_match_records()` 已經是這套計算的唯一事實來源（既有
`/members/me/match-records` 端點在用），比照 013 feature 替 `join_group()`
新增 `skip_password`（預設關閉、既有呼叫端零行為變動）的既有先例，安全地
擴充它而不影響既有呼叫端。

**Alternatives considered**：獨立寫一支只算「場次/勝/敗/勝率」四個數字的
輕量新函式——被拒絕，因為這會與既有函式的篩選/勝負判斷邏輯重複，未來兩邊
容易分岔出不一致的計算方式。

## 3. 新授權判斷式：`verify_ever_group_member()`（獨立於既有的「現役」判斷）

**Decision**：在 `group/service.py`（`resolve_active_roster_membership()`
旁邊）新增 `verify_ever_group_member(session, group_id, member_id) ->
None`——只要該會員在此團「曾經」有過任一狀態（現役／已離開／已被踢除）的
`RosterEntry` 即通過，否則丟出新的 `GROUP_INVITE_NOT_FOUND` 風格語意化
錯誤代碼 `GROUP_MEMBERSHIP_NEVER_HELD`（403）。

**Rationale**：既有 `resolve_active_roster_membership()` 是給「賽程/戰績/
退出組團」這些即時操作用的，刻意要求「現役」——這是正確的既有設計，本功能
MUST NOT 更動它或放寬它的既有語意（否則會意外讓已離開的成員重新拿到「退出
組團」之類的即時操作權限，破壞既有的授權邊界，違反憲章原則 IV「不同信任
層級的授權路徑不可混用」的精神）。因此新增一支語意完全不同、專屬於「唯讀
歷史查詢」的獨立判斷式，而不是放寬既有那支的門檻——這正是 Clarifications
2026-09-07 定案的「曾經是成員即可查看」這個存取邊界的直接落地。

**Alternatives considered**：直接放寬 `resolve_active_roster_membership()`
本身的門檻（改成「現役或曾經現役皆可」）——被拒絕，因為該函式同時也是
「退出組團」端點的授權依據，放寬它會不小心讓已離開的成員也能呼叫退出組團
等即時操作端點，是一個真正的授權邊界錯誤，而非本功能的設計意圖。

## 4. 「我的團」清單：既有查詢 UNION 上「曾經是輪替名單成員」

**Decision**：`member/service.py` 的既有 `get_my_groups()` 擴充為兩個查詢
的聯集：(a) 既有「自己建立過的團」查詢（不變）；(b) 新增「自己曾經是
`RosterEntry.member_id` 的團」查詢（不限現役／已離開／已被踢除）。以
`group_id` 去重合併成一份清單。每筆項目新增 `is_creator: bool`（是否為
建立者）與 `member_status`（自己在該團「最新一筆」`RosterEntry` 的狀態
——依 `joined_at` 由新到舊取第一筆，因為同一位會員可能在同一團「加入→
離開→重新加入」多次，產生多筆歷史紀錄；比照 013 feature `
list_invitable_friends()` 對同一好友多筆邀請歷史「取最新一筆」的既有作法）。

**Rationale**：訪客身份加入的紀錄天生被排除——`RosterEntry.member_id` 對
訪客加入永遠是 `NULL`，(b) 查詢的 `WHERE member_id = :member_id` 條件本身
就自然濾掉，不需要額外的防護判斷（FR-003）。

**Alternatives considered**：改寫成單一條 SQL（用 `OR`／`UNION` 語法在
資料庫層合併）——技術上可行，但拆成兩個各自簡單、各自可獨立測試的查詢在
Python 端合併，可讀性與既有程式風格（例如 013 feature 的
`list_invitable_friends()`）更一致，且此規模（單一會員參與過的團數量）不
需要資料庫層優化（Scale/Scope 假設）。

## 5. 新端點：`GET /members/me/groups/{group_id}/history`

**Decision**：新增一個端點，把決策 #1（該團完整比賽清單）與決策 #2（我在
該團的統計）合併成一個回應（`MemberGroupHistoryResponse`：`group_id`/
`group_name`/`stats`/`matches`/`page`/`total_pages`），而非讓前端分兩次
呼叫。授權層級採 `require_member`（與既有的
`/members/me/match-records`——同樣是「查看自己的比賽歷史」這一類端點
——一致，不採用 `/members/me/groups` 本身用的 `require_verified_member`，
因為信箱驗證狀態與「能否查看自己已經打過的歷史比賽」無關，比照既有
`/members/me/match-records` 端點的既有寬鬆基準）。

**Rationale**：一次回應涵蓋兩塊資料，符合 SC-002「3 秒內看到比賽清單與
個人統計」的單一載入體驗，且與既有 `AdminGroupResponse`（把多個子資料
包成一個回應）的既有慣例一致。

**Alternatives considered**：拆成兩個獨立端點（`.../match-records` +
`.../stats`），前端平行呼叫——被拒絕，純粹是不必要的一次多的
往返（round-trip），且沒有任何一方需要獨立快取或獨立重新整理的理由。

## 6. 不需要新資料表／新 migration

**Decision**：本功能涉及的所有實體（`Group`／`RosterEntry`／`Match`／
`MatchParticipant`）皆為既有資料表，純粹是唯讀查詢範圍的擴充——不新增、
不修改任何資料表結構。

**Rationale**：「我曾經參加過哪些團」與「該團打過哪些比賽」这些事实本來就
已經完整記錄在既有的 `roster_entries`／`matches` 表中，只是既有查詢的
`WHERE` 條件過去只覆蓋「現役」或「自己建立」這兩種子集合，本功能只是把
這個子集合擴大到「曾經參與過」而已。

## 7. 前端：重用既有對戰紀錄分頁的 UI 型別與呈現邏輯

**Decision**：新頁面（`member/my-groups/:groupId`）直接重用
`core/api/group-member-view.models.ts` 既有的 `MatchRecordSummary`/
`GroupMatchRecordsResponse` TypeScript 介面（一字不改），呈現邏輯比照既有
`group-member-view/match-records` 分頁（`winnerNames()` 顯示獲勝方姓名而非
單純的 A/B 隊伍字母）。「我的團」清單本身（`MyGroupsComponent`）新增身份
／狀態徽章（圖示＋文字並用，非僅顏色，憲章原則 VII），每列可點擊導向新
頁面；既有「忘記管理PIN碼」按鈕維持原樣、僅限 `is_creator` 為真的列顯示
（FR-007）。

**Rationale**：型別零改動地重用，前後端契約风险最低；沿用既有分頁的視覺
慣例，使用者在「我的團」點進去看到的畫面與現役成員在自己團裡看到的
「對戰紀錄」分頁長得一致，降低認知負擔。
