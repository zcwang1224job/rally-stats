# Phase 1 Data Model: 好友戰績檢視入口

## 摘要：本 feature 不新增或修改任何資料庫實體

與大多數 feature 的 data-model.md 不同，本文件不新增任何資料表欄位或
新建資料表——022-member-personal-settings 已經完整建立好本功能需要的
全部資料模型（`members.share_match_records_with_friends`、既有的
`friend_requests`/`matches`/`match_participants` 等）。本 feature 純粹是
在既有資料模型之上，新增一個**前端**的檢視入口。

## 沿用的既有實體（無變更）

- **好友關係（Friend Relationship）**：022/006 既有 `FriendRequest`
  狀態機（`status = 'accepted'` 視為好友），`get_friendship_status()`
  判斷。
- **隱私設定（Privacy Setting）**：022 既有
  `members.share_match_records_with_friends`（布林，預設 `true`）。
- **對戰紀錄（Match Record）／彙總戰績統計（Match Statistics）**：既有
  `Match`/`MatchParticipant` 資料模型與既有
  `build_member_match_records()`（005-member-view 建立）計算邏輯，透過
  022 新增的授權層（`view_member_match_records()`/
  `view_member_match_record_detail()`）對外暴露，回應形狀為既有
  `MemberMatchRecordsResponse`/`MatchRecordDetailResponse`
  （`apps/api/app/domains/group/schemas.py`，前端對應型別於
  `apps/web/src/app/core/api/group-member-view.models.ts`）——皆為既有
  型別，本 feature 不新增、不修改任一欄位。

## 新增的前端概念（非資料庫實體）

- **好友戰績檢視情境（Friend Match Records View Context）**：純前端、
  存在於單次頁面瀏覽期間的暫時狀態，不落地儲存。由路由參數
  `memberId`（必要，決定要查詢哪位好友的戰績）與 query 參數 `nickname`
  （選填，僅供畫面標題顯示用，research.md #2）組成。此狀態 MUST NOT
  被當作授權依據——每次資料請求仍一律由後端依當下的好友關係與隱私設定
  重新判斷（spec.md FR-008）。

## 狀態轉換 / 不變量摘要

本 feature 不引入任何新的狀態轉換——「是否能檢視」不是一個會被前端
記錄下來的狀態，而是每次請求當下由後端即時判斷的結果（沿用 022 既有
的無狀態授權模型）。
