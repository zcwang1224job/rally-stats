# Phase 0 Research: 好友戰績檢視入口

## #1 頁面範圍：精簡版 vs. 完整複製「我的戰績」頁面

**Decision**：新頁面只包含對戰紀錄列表（新到舊、分頁）＋四項基本彙總
統計（總場次/勝場/敗場/勝率），**不包含**既有「我的戰績」頁面
（`match-history.component`）的進階篩選表單、各輪勝率趨勢圖、對戰對象
排行榜三個區塊。

**Rationale**：spec.md 的 Assumptions 已明確排除這三項（範圍收斂的
產品決策，非技術限制）；`MemberMatchRecordsResponse` 這個既有回應本身
就同時含有 `round_win_rates`/`opponent_records`兩個欄位——換句話說，
即使不顯示，後端也不需要為了「精簡版」另外設計一支瘦身過的 API，前端
單純不渲染這兩個區塊即可，未來若要恢復完整功能，資料早就在回應裡，
不需要任何後端改動。

**Alternatives considered**：
- 完全比照「我的戰績」頁面一比一複製（含篩選＋圖表＋排行榜）——拒絕：
  超出 spec.md 已定案的範圍，且會讓「檢視戰績」這個新增的、風險相對
  高（涉及他人資料揭露）的入口一次背負過多 UI 複雜度。

## #2 頁面如何取得好友的暱稱以顯示標題

**Decision**：好友列表的「檢視戰績」連結導覽時，額外帶一個
`nickname` query 參數（例如 `/friends/{memberId}/match-records?
nickname=小明`），新頁面優先使用這個參數組出「小明的戰績」標題；若
是透過網址直接開啟（未帶這個參數，spec.md Edge Case #1 明確允許此存取
路徑），頁面 MUST 改用不含具體暱稱的通用標題（例如「好友的戰績」），
MUST NOT 因為缺少暱稱而顯示錯誤或阻擋內容呈現——暱稱純粹是畫面上的
稱呼文字，不是授權判斷的一部分（授權完全由後端依 member_id 當下判斷，
research.md #1/#6 of 022）。

**Rationale**：後端目前沒有、也不需要新增一支「依 member_id 查詢單一
會員公開暱稱」的端點——`MemberMatchRecordsResponse`本身不含目標會員的
暱稱欄位（因為它原本是給「查看自己」的端點設計的，「自己是誰」不需要
在回應裡再說一次）。從已經在好友列表頁面上、本來就看得到的
`FriendSummary.nickname` 直接帶過去，是零後端成本、對使用者體感也完全
不會有延遲的做法。

**Alternatives considered**：
- 新增一支「依 member_id 查詢單一會員公開資訊」的後端端點——拒絕：
  純粹為了畫面標題而新增一支端點，超出本 feature「不動後端」的範圍
  （plan.md Summary），且會引入新的、需要額外授權考量的資訊揭露面
  （這支端點該對誰開放？又是一個新的隱私判斷，不必要地擴大範圍）。
- 從對戰紀錄列表本身反推暱稱（例如取任一筆比賽中屬於該好友的
  participant nickname）——拒絕：`roster_entries.nickname` 是歷史快照，
  不隨會員之後修改暱稱而更新（006 既有設計），用它來代表「好友現在的
  暱稱」並不準確，可能顯示過時的名稱。

## #3 好友戰績檢視頁面的資料存取方式：新 service vs. 擴充既有 AuthService

**Decision**：在既有 `AuthService`（`apps/web/src/app/features/auth/
auth.service.ts`）新增兩個方法：`getFriendMatchRecords(memberId, page)`
與 `getFriendMatchRecordDetail(memberId, matchId)`，直接呼叫 022 既有的
`GET /members/{member_id}/match-records`／
`GET /members/{member_id}/match-records/{match_id}`，回傳型別沿用既有
`MemberMatchRecordsResponse`/`MatchRecordDetailResponse`（不新增任何
TS interface）。

**Rationale**：`AuthService` 已經是這兩支姊妹端點（`/members/me/
match-records*`）既有呼叫方法（`getMatchRecords()`/
`getMatchRecordDetail()`）所在之處，新增兩個同型態的方法比新開一個
service 檔案更符合既有慣例、也讓兩者的相似性（唯一差異只是 URL 帶
`member_id` 而非 `me`）在程式碼組織上一目了然。

**Alternatives considered**：
- 新建 `FriendMatchRecordsService`——拒絕：這兩支端點在概念上就是既有
  「戰績」API 家族的一部分（後端本來就刻意設計成共用同一組回應形狀，
  022 research.md #1），拆成獨立 service 反而製造不必要的概念邊界。

## #4 單場比賽詳情呈現方式

**Decision**：直接重用既有 `MatchRecordDetailDialogComponent`
（`apps/web/src/app/core/match-record-detail/`），不新增任何 dialog
元件。新的好友戰績列表元件呼叫 `AuthService.getFriendMatchRecordDetail()`
取得資料後，以完全相同的方式（`detail`/`loading`/`loadError` 三個
input）餵給這個既有元件，比照 `match-history.component.ts` 現有的
`openDetail()` 寫法。

**Rationale**：`MatchRecordDetailDialogComponent` 的既有設計本來就是
「純呈現、不知道任何端點、資料完全交給呼叫端」（該元件現有的文件註解
明確寫出這個設計意圖，是 016-match-score-timeline 規劃階段修正過的
結果），三個既有呼叫端（`match-history`、群組內兩處對戰紀錄清單）都是
用這個模式——本 feature 是第四個呼叫端，完全符合這個元件當初的設計
初衷，不需要任何修改。

**Alternatives considered**：
- 複製一份新的 dialog 元件——拒絕：與既有元件邏輯 100% 相同，純粹是
  不必要的重複，違反憲章原則 VI。
