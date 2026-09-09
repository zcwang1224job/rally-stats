# Research: 比賽加減分紀錄與趨勢圖

5 decisions。無新技術、無新資料表（`score_events` 表已於上一階段
建立，見 `apps/api/alembic/versions/f3a1c9d4e7b2_score_events_table.py`
與 `apps/api/app/domains/schedule/models.py` 的 `ScoreEvent`），本 feature
純粹是在既有資料上新增唯讀查詢端點與前端呈現。

## 1. 新增兩個端點，各自重用一支既有、未修改的授權判斷式

**Decision**：新增：

- `GET /groups/{group_id}/match-records/{match_id}`（`group/router.py`，
  緊鄰既有 `GET /groups/{group_id}/match-records`）——重用既有
  `resolve_active_roster_membership()`（`group/service.py:798`），與清單
  端點完全相同的授權語意（Guest 現役 token 或 Member 現役成員）。
- `GET /members/me/match-records/{match_id}`（`member/router.py`，緊鄰
  既有 `GET /members/me/match-records`）——`require_member` 之後，重用
  既有 `verify_ever_group_member()`（`group/service.py:832`，
  014-member-groups-history 建立）驗證該會員「曾經」是這場比賽所屬團的
  正式成員。

兩者皆呼叫同一支新的共用服務函式組裝回應（見 data-model.md），差異只在
「呼叫前先做哪一種既有授權檢查」。

**Rationale**：FR-005 要求「進入詳情畫面的權限 MUST 與使用者當下查看的
清單完全相同」。對戰紀錄目前有三個進入點，但收斂成只有兩種既有授權語意：
（a）團內對戰紀錄分頁（現役成員/訪客，`resolve_active_roster_membership`）；
（b）會員視角的兩個清單——「跨團對戰紀錄」與「我的團 → 歷史」——兩者皆是
已登入會員查看「自己有權看的比賽」，且都已經用 `require_member` +
（跨團清單本身即隱含「這是我打過的比賽」／「我的團」歷史則用
`verify_ever_group_member`）這組較寬鬆的「曾經」語意，不要求現役。因此
用同一支 `verify_ever_group_member(session, match.group_id, member.id)`
即可同時覆蓋這兩個會員清單，不需要為每個清單各開一支端點。全程不修改、
不放寬任何一支既有授權判斷式本身，只是「重新呼叫」既有函式——完全符合
憲章原則 IV「不同信任層級的授權路徑不可混用」與原則 VI「可維護性/
模組化」。

**Alternatives considered**：
- 比照三個進入點各開一支端點——被拒絕，因為（b）的兩個會員清單本來就
  共用同一種「曾經是這場比賽所屬團的成員」語意，開兩支端點是不必要的
  重複。
- 放寬 `resolve_active_roster_membership()` 本身、讓它同時支援「現役或
  曾經現役」——被拒絕，理由與 014 research.md #3 相同：該函式同時也是
  「退出組團」等即時操作端點的授權依據，放寬它會意外讓已離開的成員拿回
  即時操作權限，是真正的授權邊界錯誤。

## 2. 共用服務函式：重用既有 `_completed_matches_query()` / `_build_match_record_summaries()`

**Decision**：新增 `group/service.py`：

- `get_completed_match_or_404(session, match_id) -> Match`——套用既有
  `_completed_matches_query()`（`group/service.py:941`，`WHERE status =
  'completed'`）加上 `WHERE id = match_id`，查無結果一律 `ApiError
  ("MATCH_NOT_FOUND", 404)`。
- `build_match_record_detail(session, match: Match) ->
  MatchRecordDetailResponse`——內部呼叫既有
  `_build_match_record_summaries(session, [match])`（`group/service.py:949`）
  取得 `team_a`/`team_b`/`score_a`/`score_b`/`winner_team`/`started_at`/
  `ended_at`（與既有 `MatchRecordSummary` 完全相同的組裝邏輯，零重複），
  再查詢該場比賽的 `ScoreEvent`（`schedule/models.py`）並依 `created_at`
  排序，換算每筆的「開賽後經過秒數」與整體的「完整／部分／無」狀態（見
  決策 #3）。

群組範圍端點（`GET /groups/{group_id}/match-records/{match_id}`）在呼叫
`get_completed_match_or_404()` 之後，額外檢查 `match.group_id ==
group_id`，不符則同樣回傳 `MATCH_NOT_FOUND`（而非 403）——比照
007-live-scoreboard `scoring-api.md` 既有先例，不透露「這個 match_id
存在但屬於別的場地/團」。

**Rationale**：`_completed_matches_query()` 的既有文件字串本身就寫明
「shared 比賽結果 query base」，本來就是為多個消費端準備的共用基礎；直接
重用避免第三套「什麼算已完成比賽」的判斷邏輯（憲章原則 VI）。

**Alternatives considered**：另外寫一支獨立的單場查詢——被拒絕，
`_completed_matches_query()` 只需加一個 `WHERE id =` 條件即可重用，沒有
理由重寫。

## 3. 完整／部分／無紀錄三態判斷邏輯

**Decision**：對某場已完成比賽的 `ScoreEvent` 清單（依 `created_at`
升冪排序）：

- 清單為空 → `record_completeness = "none"`（FR-006）。
- 清單非空，且第一筆紀錄的 `score_a + score_b == 1`（代表這筆確實是全場
  第一分，比賽從 0:0 開始就被完整記錄）→ `"complete"`。
- 清單非空，但第一筆紀錄的 `score_a + score_b != 1`（代表這筆發生時，
  場上已經有既存分數，記錄是從比賽中途才開始的）→ `"partial"`
  （FR-006a）。

**Rationale**：這是唯一不需要額外欄位、單純從既有 `ScoreEvent`
資料本身就能推導出的判斷方式——一場比賽的第一分永遠是 1:0 或 0:1，任何
其他起始比分都直接證明「開賽當下這個功能還沒開始記錄」。不需要另外
新增欄位標記「這是不是第一筆」或「該功能何時上線」，避免多一個需要維護
一致性的資料來源。

**排序 tie-breaker**：`events` 查詢 MUST 依 `created_at, id` 升冪排序
（而非只有 `created_at`）——`test_score_concurrency.py` 證實同一場比賽的
並發加減分是系統實際支援的情境，兩筆 `ScoreEvent` 的 `created_at`
理論上可能相同，僅靠 `created_at` 無法保證每次查詢順序一致。`id`
雖是隨機 UUID、不具寫入先後意義，但至少讓排序結果「確定」（同一份資料
重複查詢恆為同一順序），滿足 spec.md Edge Case「近乎同時操作」之
「不可因時間精度不足而順序錯亂」的字面要求（見 data-model.md）。

**Alternatives considered**：新增一個全域設定值（本功能上線時間戳），
拿比賽的 `started_at` 與之比較——被拒絕，這需要新增一個新的
`SystemConfig`/常數並確保未來不被誤刪，且無法處理「比賽在上線後才開打，
但因為某種原因遺漏了前幾筆」這種資料異常情況（雖然目前系統設計下不會
發生，但用資料本身判斷比用一個外部時間戳判斷更穩固、更貼近「有記錄就
是有記錄」的資料事實，而非依賴一個容易被遺忘維護的部署時間戳）。

## 4. 前端：以彈出視窗（modal/dialog）呈現詳情，而非新增獨立路由；資料擷取交還各入口自己既有的 service（`/speckit-implement` 階段修訂）

**Decision**：新增一個共用的 Angular standalone 元件
（`MatchRecordDetailDialogComponent`，比賽詳情彈出視窗），由三個既有
清單元件（`group-member-view/match-records`、`member/match-history`、
`member/my-groups/group-history`）各自在列點擊時開啟。**此元件是純呈現
元件**——不注入任何 API service，不知道任何端點路徑，只接受
`@Input() detail: MatchRecordDetailResponse | null` 等資料型別 input。
取資料的責任交還給三個入口各自「本來就已經在用」的既有 service：

- 團內對戰紀錄分頁 → `GroupMemberViewService.getMatchRecordDetail(groupId,
  matchId)`（新方法，緊鄰既有 `getMatchRecords()`，重用同一支
  `guestTokenQuery()`/`authHeader()`）。
- 跨團對戰紀錄、我的團→歷史（兩者皆已登入會員視角）→ 同一支
  `AuthService.getMatchRecordDetail(matchId)`（新方法，緊鄰既有
  `getMatchRecords()`）。

**Rationale（含 `/speckit-implement` 階段的修訂原因）**：三個進入點所在
的父層路由結構彼此不同（有的在 `groups/:groupId/member-view` 底下、有的
在 `member/match-history`、有的在 `member/my-groups/:groupId`），若改用
獨立路由（例如 `matches/:matchId`），三個進入點各自導頁後還要想辦法把
「我是從哪個清單點進來的」這個授權所需的上下文（`groupId` 是否存在）帶
過去，徒增路由參數傳遞的複雜度；彈出視窗直接在原地開啟，呼叫端本來就已
經持有正確的上下文，語意最直接，也符合 SC-001「一次點擊」。

規劃階段（`/speckit-tasks`）原本設計是新增一支共用的
`match-record-detail.service.ts`，靠呼叫端傳不傳 `groupId` 參數決定呼叫
哪個端點——`/speckit-analyze` 抓到的 CRITICAL 發現 I1
（`我的團→歷史`頁被誤接到團內對戰紀錄分頁專用的端點，違反 FR-005）正是
出在這個設計上：「決定呼叫哪個端點」這件事一旦變成一個需要呼叫端手動
傳對參數才不會出錯的分支邏輯，就永遠有人會傳錯。`/speckit-implement`
階段發現三個入口其實各自本來就已經注入了各自負責清單資料的
service（`GroupMemberViewService`、`AuthService`——`member/match-history`
與`member/my-groups/group-history`剛好共用同一個 `AuthService`），於是
改為直接在這些既有 service 上各自新增一支「呼叫這個頁面原本就該用的
端點」的方法，讓 dialog 元件本身完全不參與「該呼叫哪個端點」的決定——
從結構上就不存在誤用的可能，不必再靠警語或迴歸測試補救同一類錯誤。

**Alternatives considered**：
- 新增獨立路由（例如 `matches/:matchId?groupId=`）——被拒絕，見上述理由；
  三個入口各自的路由深度、guard 邏輯不同，統一路由反而需要額外處理「這個
  路由參數組合到底該用哪一種授權」的分支，複雜度高於彈出視窗方案。
- 維持規劃階段的單一共用 `match-record-detail.service.ts` + 呼叫端傳
  `groupId?` 參數的設計——被拒絕，正是 I1 這個真實發生過的 bug 的根源，
  結構上比「各入口呼叫自己既有的 service」更容易出錯，且沒有帶來額外
  好處（兩個後端端點本來就分屬不同 domain，對應到不同前端 service 反而
  更貼合既有架構）。

## 5. 圖表：沿用既有 hand-rolled inline SVG + Angular computed signal 慣例，不新增套件

**Decision**：新的雙方比分趨勢圖沿用 `group-history.component.ts`／
`match-history.component.ts` 既有的「`viewBox` + `polyline`/`polygon` +
computed signal」手刻 SVG 慣例（`apps/web/package.json` 目前無任何圖表
套件依賴），横軸改為「開賽後經過秒數」而非既有的「第幾輪」。因涉及
**兩條**曲線（A、B 兩隊），且憲章原則 VII 要求視覺元素不得僅靠顏色區分，
兩條線 MUST 額外以線條樣式（例如一實一虛）與文字圖例（隊伍代號/參賽者
暱稱)雙重區分（FR-008）。

**Rationale**：專案至今沒有任何頁面引入圖表函式庫，貿然新增一個套件
依賴（bundle size、授權、維護成本）不是這個功能的必要條件——手刻 SVG
已經足以畫出兩條隨經過時間變化的折線。沿用既有慣例也讓使用者在不同
「對戰紀錄」相關頁面看到的圖表視覺語言一致。

**Alternatives considered**：引入第三方圖表套件（例如 ngx-charts/
Chart.js）——被拒絕，非必要依賴；且該類套件的無障礙色彩區分支援程度
不一，仍需要額外設定才能滿足 FR-008，手刻 SVG 反而更容易直接控制
`stroke-dasharray` 等樣式細節。
