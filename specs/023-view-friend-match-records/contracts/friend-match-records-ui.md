# UI/API Contract: 好友戰績檢視入口

本 feature **不新增、不修改任何後端 API**。本文件記錄前端消費既有
022 端點（`specs/022-member-personal-settings/contracts/
member-settings-api.md`）的方式，以及本 feature 唯一新增的前端路由。

## 新增前端路由

### `GET /friends/:memberId/match-records`（前端路由，非後端端點）

**Query 參數**：`nickname`（選填，research.md #2）——僅影響畫面標題
文字，MUST NOT 影響資料請求或授權判斷。

**行為**：

1. 進入頁面時，立即呼叫既有 `GET /members/{memberId}/match-records`
   （透過新增的 `AuthService.getFriendMatchRecords(memberId, page)`，
   `page` 預設 1）。
2. 成功（`200`）時：顯示對戰紀錄列表（新到舊排序）與彙總統計（總場次/
   勝場/敗場/勝率），提供分頁控制；換頁時以新的 `page` 重新呼叫同一
   端點（FR-008：MUST NOT 沿用前一次的授權判斷）。
3. 失敗時，依既有 `ApiError.errorCode`→`i18nKey` 機制（022 已註冊下列
   三個 key）直接呈現對應文字，MUST NOT 顯示空白頁：
   - `errors.MEMBER_NOT_FOUND`：目標好友不存在或未驗證。
   - `errors.FRIENDSHIP_REQUIRED`：與目標對象已非好友關係。
   - `errors.MATCH_RECORDS_PRIVATE`：目標已關閉「好友可查看我的戰績」。
4. 當回應成功但 `total_matches === 0` 時，顯示「尚無對戰紀錄」空狀態
   （FR-010），與上述三種錯誤狀態的視覺呈現明確不同（不得讓使用者
   誤判「沒有資料」與「沒有權限」為同一種畫面）。

## 呼叫既有端點的前端方法（新增於 `AuthService`）

### `getFriendMatchRecords(memberId: string, page = 1): Observable<MemberMatchRecordsResponse>`

呼叫既有 `GET /members/{memberId}/match-records?page={page}`（帶
`Authorization` header，比照既有 `getMatchRecords()` 寫法）。**不透傳**
既有端點支援的進階篩選查詢參數（`opponent1`/`date_from`/...等）——
research.md #1 已定案本 feature 不提供進階篩選 UI，故這些參數維持後端
預設（不篩選），前端不需要組出對應的 query string。

### `getFriendMatchRecordDetail(memberId: string, matchId: string): Observable<MatchRecordDetailResponse>`

呼叫既有 `GET /members/{memberId}/match-records/{matchId}`（帶
`Authorization` header，比照既有 `getMatchRecordDetail()` 寫法）。

## 好友列表新增的操作入口

### 「檢視戰績」連結（`friend-list.component.html`，既有頁面擴充）

每一列好友新增一個連結，`routerLink` 指向
`/friends/{friend.member_id}/match-records`，並帶上
`{ queryParams: { nickname: friend.nickname } }`（`friend.nickname` 可能
為 `null`——為 `null` 時 MUST NOT 帶入此 query 參數，交由新頁面套用
research.md #2 的通用標題後備方案）。此連結 MUST 對好友列表中每一位
已成立好友關係的對象一律顯示，不因任何前端已知資訊而選擇性隱藏
（spec.md Assumptions「檢視戰績入口的顯示邏輯」）。
