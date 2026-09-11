# Research: 我的團最終團隊排名

6 decisions。不新增資料表、不需要新 migration（最終團隊排名刻意設計為
完全由既有比賽資料即時計算而得，見 spec.md Assumptions）。

## 1. 涵蓋範圍與統計基礎：新函式 `build_group_final_standings()`，依
`member_id` 合併同一位會員的多筆 `RosterEntry`

**Decision**：既有 `build_group_standings()`（`group/service.py:858`，
018-group-leaderboard 擴充）是「逐輪矩陣 + 排序」的複合查詢，其
`roster_result` 查詢刻意加了 `RosterEntry.status == "active"` 過濾（018
research.md #3），且需要 `RoundHistory` 表來組出逐輪欄位——這兩者都與
本 feature的需求方向相反：本 feature（spec.md FR-002）MUST 涵蓋「該團
所有曾參與者」（含已離開／已被踢除／訪客，不限現役、不限有會員帳號），
且只需要「自成立以來的累計勝敗場次」（spec.md FR-004），不需要逐輪細目。
因此新增一個獨立的 `build_group_final_standings(session, group_id,
*, viewer_member_id)`：

1. 查詢該 `group_id` 底下**所有**曾經存在過的 `RosterEntry`（**不**加
   `status` 過濾、**不**加 `member_id IS NOT NULL` 過濾），依 `joined_at`
   排序。
2. **依身份分組**（spec.md Edge Cases：「同一位會員在同一個團有多筆
   歷史紀錄——最終排名清單中只需列出這個人一次」）：`member_id` 不為
   `NULL` 的列，依 `member_id` 分組（同一位會員的所有歷史 `RosterEntry`
   合併成一組）；`member_id` 為 `NULL`（訪客）的列，每一筆各自獨立成一組
   （訪客沒有跨場次的穩定身份可合併，比照既有 014 Assumptions「訪客
   時期的參與紀錄不會回溯歸戶」的既定立場）。
3. 每一組取：
   - **代表列**（顯示用的 `nickname`／`current_status`／
     `roster_entry_id`）＝該組內 `joined_at` **最新**的一筆——比照既有
     `MyGroupSummary.member_status` 的既定慣例（`friend.models.ts`
     註解：「reflects the newest one」），確保暱稱/狀態顯示的是這位會員
     目前（或最後一次）在團裡的樣子，而不是很久以前已經過期的暱稱。
   - **排序用的 `joined_at`**（次要排序依據，見 decision #2）＝該組內
     **最早**的一筆——反映這位會員第一次加入這個團的時間，不因為中途
     退出又重新加入而被視為「新加入者」，維持「先加入排前面」規則
     背後「資深優先」的直覺（018 research.md #6 之精神延伸）。
   - **統計彙總**：把該組內所有 `RosterEntry.id` 收集成一個集合，重用
     既有 `_completed_matches_query()`（`group/service.py:975`，僅
     `status == "completed"`）疊加 `Match.group_id == group_id`，join
     `MatchParticipant.roster_entry_id IN (該集合)`，依 `team ==
     winner_team` 判定勝負並加總 `total_matches`／`total_wins`／
     `total_losses`——涵蓋這位會員在該團全部參與期間（不論哪一次加入）
     的所有已完成比賽。
4. 依 `total_wins` 由高到低排序（`sorted` 穩定排序，各組已依「代表列的
   排序用 `joined_at`」升冪排列，並列時保留較早加入者在前）。

**Rationale**：把「涵蓋範圍」「是否需要逐輪矩陣」「是否需要合併多筆
`RosterEntry`」三個與既有 018 呼叫端都不同的需求硬塞進同一個函式，會讓
`build_group_standings()` 多長出好幾個條件分支，既有呼叫端完全不需要
這些分支，徒增既有函式的複雜度與回歸風險（違反憲章原則 VI）。拆成兩個
各自單純的函式，各自的查詢條件都能一眼看懂。

**Alternatives considered**：
- 讓 `build_group_standings()` 多接受參數讓兩種呼叫端共用一份查詢——
  被拒絕，兩者連「要不要逐輪矩陣」「要不要合併多筆 RosterEntry」都不同，
  參數化後函式簽名與內部邏輯會變得難以閱讀。
- 不合併，直接讓同一位會員的多筆 `RosterEntry` 各自成一列——被拒絕，
  明確違反 spec.md Edge Cases 的既定要求（「只需要列出這個人一次」），
  且會讓同一個人在排行榜上跟自己比較，觀感錯亂。

## 2. 排序與並列名次演算法：抽出共用函式 `_assign_standard_competition_ranks()`，
`build_group_standings()` 與 `build_group_final_standings()` 共用

**Decision**：把既有 `build_group_standings()` 內「依 `total_wins` 排序後
算 `rank`」的迴圈（`group/service.py:949-968`，standard competition
ranking／「1224」排名法，018 research.md #6 已定義精確規則）抽成一個
獨立的純函式：

```python
def _assign_standard_competition_ranks(
    total_wins_in_order: list[int],  # 已依 total_wins 降冪排序
) -> list[int]:
    ranks: list[int] = []
    previous_wins: int | None = None
    previous_rank = 0
    for position, total_wins in enumerate(total_wins_in_order, start=1):
        if total_wins != previous_wins:
            previous_rank = position
            previous_wins = total_wins
        ranks.append(previous_rank)
    return ranks
```

`build_group_standings()` 改為呼叫這個函式取得 `rank` 列表（行為完全不變，
純重構），`build_group_final_standings()` 也呼叫同一個函式。

**Rationale**：這正是 018-group-leaderboard 自己的 research.md #2 已經
指出的風險——「如果排序/名次規則留給多處各自實作，容易寫出不一致的版本」。
本 feature 是第二個需要「依總勝場排序＋並列跳號＋加入時間為次要依據」的
呼叫端，如果直接複製貼上 018 那段迴圈，就正好落入 018 自己想避免的陷阱；
抽出共用函式後，兩者永遠使用同一套規則，未來若排名規則有變動也只需要改
一個地方。

**Alternatives considered**：
- 直接複製 018 的排序迴圈到新函式——被拒絕，理由同上，違反憲章原則 VI
  （MUST NOT 依賴跨模組的內部實作細節或重複邏輯）。

## 3. 訪客的呈現：沿用既有欄位語意，不新增「是否為訪客」欄位

**Decision**：`FinalStandingRow` 沿用既有 `RosterEntry.status`
（`active`／`left`／`kicked`）作為 `current_status` 欄位；訪客
（`member_id IS NULL`）與一般會員在回應中**完全同構**，不額外標示
「訪客」身份——與既有「我的團」歷史頁面的既有慣例一致（`opponent_records`、
`matches` 內的 `nickname` 從未區分過訪客/會員），且 Clarifications
2026-09-10 之訪客涵蓋範圍決策也明確要求「不得因為沒有會員帳號而被排除
或另外特別標示為與一般參與者不同的類別」（spec.md FR-002）。

**Rationale**：這是 spec.md FR-002 已經明確定案的產品決策，本節只是確認
技術實作上不需要為此新增欄位或查詢條件——只要不主動加上
`member_id IS NOT NULL` 過濾條件即可達成，不需要額外程式碼；decision #1
的「依身份分組」步驟已經把「訪客各自獨立成一組」納入分組規則本身，不是
額外的特殊條件判斷。

**Alternatives considered**：無——這是 spec.md 已定案的範圍決策，不是本
`/plan` 階段的技術選型問題。

## 4. 自己所在列的標示：後端直接算好 `is_self`，不比照既有戰績頁「前端
比對 roster_entry_id」的做法

**Decision**：既有 018 即時戰績頁的 `isSelf()`（`standings.component.ts`）
是前端拿「目前這個瀏覽器session解析出的 `roster_entry_id`」跟每一列比對
——這個做法依賴「訪客/現役成員 session token」，而本 feature 所在的
「我的團」頁面是用**會員 JWT** 登入（`require_member`），從來不經過那套
roster/guest session 解析流程，且經過 decision #1 的合併後，一列可能對應
「這位會員好幾筆歷史 `RosterEntry` 中的任何一筆」，前端更不可能只憑單一
`roster_entry_id` 判斷「這是不是我自己」。因此改為：`build_group_final_
standings()` 新增 `viewer_member_id` 參數（呼叫端傳入既有
`require_member` 解析出的 `member.id`），分組時額外記錄「這一組的
`member_id` 是否等於 `viewer_member_id`」，直接輸出布林欄位
`FinalStandingRow.is_self`，不在回應中額外暴露任何一組的原始 `member_id`
（維持既有「暱稱是唯一對外身份」的呈現慣例）。前端只需要渲染
`is_self`，不需要自己比對任何 ID（憲章原則 X：排序/自己與否皆由伺服器
算好）。

**Rationale**：讓伺服器直接輸出「是不是我自己」，比讓前端自己想辦法比對
一個在這個頁面情境下根本取不到、且合併後語意也不再單純的
`roster_entry_id` 簡單且可靠得多；也避免在回應中多暴露一個不必要的
`member_id` 欄位。

**Alternatives considered**：
- 回應內附上每組的 `member_id`，前端自己跟登入中的會員 ID 比對——被
  拒絕，多餘地暴露內部識別碼，且前端本來就不需要知道除了「是不是我」
  以外的任何身份細節。

## 5. 存取權限：沿用既有 `verify_ever_group_member`，端點本身不變

**Decision**：`final_standings` 直接加進既有 `GET
/members/me/groups/{group_id}/history` 的回應（`MemberGroupHistoryResponse`），
沿用該端點既有的 `verify_ever_group_member` 授權檢查（`group/service.py:835`，
014-member-groups-history 既有邏輯）——不新增端點、不新增查詢參數、不
修改既有錯誤碼（`GROUP_MEMBERSHIP_NEVER_HELD`）。

**Rationale**：spec.md FR-010 明確要求「存取權限的判斷基準 MUST 與既有
『我的團』歷史頁面完全一致」，且該端點的授權檢查與涵蓋範圍語意
（「曾經是正式成員即可」）本來就與本 feature 的涵蓋範圍決策
（FR-002：所有曾參與者）完全對齊——沒有理由另外設計一套授權規則或新增
端點。

**Alternatives considered**：
- 新增一個獨立的 `GET /groups/{group_id}/final-standings` 端點——被拒絕，
  spec.md FR-001 明確要求 MUST NOT 新增獨立畫面/路由，既有歷史端點已經
  是這個頁面資料的唯一來源，新增端點只會讓前端多一次網路請求且無實質
  好處。

## 6. i18n：重用既有 `groupMemberView.standings.*` 系列 key，補上缺口

**Decision**：最終團隊排名表格重用既有 `groupMemberView.standings.*`
系列 key（`rankLabel`／`rankValue`／`nicknameLabel`／`totalLabel`／
`recordLabel`／`selfBadge`／`noRecordYet`／`status.left`）——這些 key 的
語意與本功能完全相同（名次/暱稱/總戰績/自己標示/尚無比賽紀錄/已離開）。
唯一缺口：`groupMemberView.standings.status` 底下目前只有 `left` 與
`did_not_play`，沒有 `kicked`（018 的即時戰績頁刻意排除被踢除成員，從未
需要這個文字）——新增 `groupMemberView.standings.status.kicked`
（比照既有 `left` 的圖示＋文字慣例，例如「🚫 已被踢除」）。區塊標題與
「完全無比賽紀錄」整體提示，新增至既有 `member.matchHistory.*` 命名空間
（例如 `member.matchHistory.finalStandingsTitle`／
`member.matchHistory.finalStandings.empty`），與同頁既有 `myStatsTitle`／
`groupRecordsTitle` 的既有命名慣例一致。

**Rationale**：重用既有 key 而非另開一套平行的文案，避免同一個概念
（例如「尚無比賽紀錄」）在語系檔裡出現兩份幾乎相同但字句不同的翻譯，
維持憲章原則 VIII 的「集中於語系檔」精神；`kicked` 是本 feature 第一次
需要呈現的既有資料狀態（因為涵蓋範圍決策的緣故），語系檔本身沒有更動
既有 key 的意義，純粹新增缺口。

**Alternatives considered**：
- 為最終團隊排名區塊新開一整套獨立的 i18n key（不重用
  `groupMemberView.standings.*`）——被拒絕，會造成兩份文案需要同步維護
  （例如「尚無比賽紀錄」在兩個命名空間各存在一份），增加未來修改文案時
  漏改一處的風險。
