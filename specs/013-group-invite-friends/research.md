# Research: 邀請好友加入組團

## #1 新增獨立 `group_invite` domain 模組，不塞進 `group` 或 `friend` 模組

**Decision**：新增 `apps/api/app/domains/group_invite/`
（`models.py`/`schemas.py`/`service.py`/`router.py`），比照 012
`notification` 模組的既有規模與慣例。此模組：
- 讀取 `group.service`（重用 `join_group()`、`verify_password()`）與
  `friend.service`（重用 `get_friendship_status()`）——單向依賴，不修改
  這兩個既有模組的核心邏輯。
- 呼叫 `notification.service`（建立/發布通知）——同樣單向依賴，重用 012
  已建立的通用通知機制，不重新設計列表/未讀計數/已讀機制。

**Rationale**：「組團邀請」是跨 `group`/`friend`/`notification` 三個既有
模組的複合概念，若塞進任一既有模組，會讓該模組承擔不屬於它的職責（原則
VI）。獨立模組讓邀請本身的狀態機（pending/accepted/declined/invalidated）
與唯一性規則有自己清楚的邊界，同時透過重用既有服務函式避免重複實作
「加入團」「好友關係判斷」「通知投遞」這些已經存在且經過測試的邏輯。

**Alternatives considered**：把 `GroupInvite`模型與服務邏輯直接寫進
`group` 模組——被否決，`group` 模組已經很大，且好友關係判斷、通知投遞都
不是它原本的職責範圍。

## #2 循環 import 的解法：沿用既有的 Hook 參數模式，而非直接互相 import

**Decision**：兩個既有函式需要在特定事件發生時「順便」讓
`group_invite` 模組把相關的待回覆邀請標記為失效，但這兩個函式所在的模組
（`group`、`friend`）如果直接 import `group_invite.service`，會與
`group_invite.service`（它本身需要 import `group.service`／
`friend.service`）形成循環 import。解法是沿用 `disband_group()`
既有的 `abandon_unfinished_matches: AbandonMatchesHook | None` 參數模式
（見 `group/service.py`，供 003 的 `abandon_group_matches` 以同樣方式
注入，`group/router.py` 才是實際 import 兩邊並把函式當參數傳進去的組合
點）：

- `disband_group()` 新增 `invalidate_pending_invites:
  InvalidatePendingInvitesHook | None = None` 參數（型別同樣是
  `Callable[[AsyncSession, uuid.UUID], Awaitable[None]]`），在既有邏輯內
  於同一交易呼叫。`group/router.py` 的 `disband` 端點與
  `scheduler/auto_disband.py` 的 `sweep_idle_groups()`
  兩個呼叫點皆 import `group_invite.service
  .invalidate_pending_invites_for_group` 並傳入——兩者都會觸發解散（手動
  /自動閒置），此為 spec Edge Cases「團在受邀好友回應之前被解散」不分手動
  /自動皆須成立的直接對應。
- `unfriend()` 新增 `invalidate_pending_invites:
  InvalidatePendingInvitesForPairHook | None = None` 參數（型別
  `Callable[[AsyncSession, uuid.UUID, uuid.UUID], Awaitable[None]]`），
  `friend/router.py` 的 unfriend 端點 import `group_invite.service
  .invalidate_pending_invites_for_member_pair` 並傳入。

**Rationale**：這是本專案已經確立的既有解法（`AbandonMatchesHook`），不
是為本 feature 新發明的模式；沿用可維持一致性，也不需要為了打破循環而把
`group_invite` 的邏輯拆得更細或改變既有模組的職責邊界。

**Alternatives considered**：把 `get_friendship_status()`/`join_group()`
挪到更底層的共用模組，讓三邊都能 import 而不互相依賴——被否決，這兩個
函式的定義權本來就屬於 `friend`/`group` 模組，搬動它們會模糊既有模組的
職責歸屬，且既有的 Hook 模式已經是本專案驗證過、成本更低的解法。

## #3 「接受邀請」重用 `join_group()`，新增 `skip_password` 參數

**Decision**：`join_group()` 新增 `skip_password: bool = False`
（keyword-only）參數；密碼驗證這一行改為
`if not skip_password and not verify_password(group, password or ""):`。
所有既有呼叫點（列表加入、加入連結、訪客重連）不傳這個參數，維持
`False`，行為完全不變。`group_invite.service` 的接受邀請函式是唯一會傳
`skip_password=True` 的呼叫端（Clarifications Q1，FR-007）。

**Rationale**：`join_group()` 的 docstring 本來就明講它是「the core join
write path, shared by every join entry point」——人數上限、一人僅能活躍
一團、暱稱解析、`RosterEntry` 建立、`member.joined` 事件發布等邏輯，接受
邀請這條路徑全部需要且不應該重新實作一份（原則 VI）。新增一個預設關閉的
參數是最小改動，不影響任何既有呼叫端的行為或既有測試。

**Alternatives considered**：另外寫一個獨立的
`accept_group_invite_join()` 函式、複製 `join_group()` 的邏輯但跳過密碼
——被否決，會重複維護人數上限/一人一團/暱稱解析等核心規則兩份，違反
原則 VI，且未來 `join_group()` 若修正邊界情境（例如目前的
race-condition 防呆），複製出去的版本不會同步得到修正。

## #4 額滿失敗（FR-013）：攔截 `join_group()` 的 `GROUP_FULL`，不修改該錯誤本身

**Decision**：`group_invite.service.accept_invite()` 呼叫
`join_group(..., skip_password=True)`，以 `try/except ApiError` 包裹；
命中 `error_code == "GROUP_FULL"` 時，在**同一次**函式呼叫內建立一筆
`type="group_invite_capacity_full"` 的通知給邀請人（團長）、commit、
publish，然後重新拋出原本的 `GROUP_FULL` 錯誤給呼叫端（受邀好友本人也
需要立即看到失敗訊息，見 spec Edge Cases）。這筆 `GroupInvite` 的
`status` 完全不變動，仍是 `pending`（Clarifications Q2）。

其餘由 `join_group()` 拋出的錯誤（`GROUP_DISBANDED`——理論上不會發生，
因為解散已透過 #2 的 hook 讓邀請先變成 `invalidated`，此處僅為防禦性
保留；`ALREADY_ACTIVE_IN_ANOTHER_GROUP`）一律直接往上拋，不觸發任何額外
通知——FR-013 明確把「通知團長」限定在「已額滿」這一種失敗原因（好友
自己的處境，團長無從協助，通知了也無意義）。

**Rationale**：`join_group()` 本身已經用一句原子 `UPDATE ... WHERE
current_member_count < max_members` 防呆額滿的競態（見其實作），不需要
在 `group_invite` 這層重新判斷「是否已滿」——直接攔截它拋出的錯誤代碼
反應即可，避免兩處各自維護一份額滿判斷邏輯。

**Alternatives considered**：在呼叫 `join_group()` 之前，`group_invite`
自己先 `SELECT` 一次目前人數是否已達上限——被否決，這只是重複一次
`join_group()` 內部已經做的檢查，且存在檢查後、寫入前人數被其他請求
佔滿的競態視窗（TOCTOU），不如直接依賴 `join_group()` 本身的原子防呆。

## #5 `GroupInvite` 狀態機：四態，`invalidated` 統一涵蓋「好友關係解除」與「團已解散」兩種觸發來源

**Decision**：
```text
                 團長送出邀請
                     │
                     ▼
                 pending ──── 好友按下接受（成功）────→ accepted
                     │
                     ├──── 好友按下拒絕 ──────────────→ declined
                     │
                     └──── 好友關係解除（任一方）
                           或本團解散（手動/自動）─────→ invalidated
```
`pending` 是唯一的非終態；`accepted`/`declined`/`invalidated` 皆為終態，
不可再轉換。額滿導致的接受失敗（#4）不算狀態轉換，`pending` 原地不動。

**Rationale**：spec 的兩輪 Clarifications 分別定案「額滿失敗不影響邀請
狀態」與「好友關係解除讓邀請自動失效」；「團已解散」雖然 spec 本身只要求
「操作時明確告知團已不存在」，但若不讓邀請本身也轉為終態，待回覆列表會
永遠留著一筆事實上不可能再成立的「pending」——與「好友關係解除」是
同一類「前提消失、邀請失去存在基礎」的情境，統一用同一個 `invalidated`
狀態涵蓋，UI 與資料模型都不需要為兩種觸發來源分別設計。

**Alternatives considered**：「團已解散」保留為獨立的第五種狀態（例如
`group_disbanded`）——被否決，對使用者而言「這筆邀請已經沒有意義」的
結論相同，沒有必要讓前端多處理一種狀態分支。

## #6 唯一性約束：`(group_id, invitee_member_id)` 於 `status='pending'` 時唯一，不需要 `LEAST/GREATEST`

**Decision**：partial unique index `ux_group_invites_pending_invitee`
於 `(group_id, invitee_member_id)`、`WHERE status = 'pending'`，比照
`friend_requests` 既有的 `ux_friend_requests_pending_pair` 寫法，但**不**
需要該索引使用的 `LEAST(requester_id, addressee_id)`/`GREATEST(...)`
方向無關寫法。

**Rationale**：好友申請雙方都可能是發起人（A 可以申請 B，B 也可以申請
A），所以需要方向無關的唯一性；組團邀請只有一個方向——邀請人恆為該團
的團長（FR-001），不會有「好友反過來邀請團長」的情境，`invitee_member_id`
本身已經足以唯一識別「這筆邀請是邀請誰」，不需要額外處理方向對稱性。

**Alternatives considered**：比照好友申請的 `LEAST/GREATEST` 寫法——
被否決，多此一舉，這裡的關係本來就是單向的。

## #7 通知內容：新增共用的 `GroupInviteNotificationDetail`，`type` 決定呈現角度

**Decision**：`notification.schemas` 新增
`GroupInviteNotificationDetail`（`invite_id`/`group_id`/`group_name`/
`status`/`inviter`/`invitee`，後兩者皆重用既有 `FriendSummary` 形狀），
`NotificationSummary.type` 擴充為
`Literal["friend_request", "group_invite", "group_invite_capacity_full"]`，
新增 `group_invite: GroupInviteNotificationDetail | None` 欄位（比照
012 `friend_request` 欄位的「依 type 決定是否非 null」慣例，FR-011 of
012 之可擴充性設計於此正式派上用場）。`type="group_invite"` 與
`type="group_invite_capacity_full"` 共用同一個巢狀欄位與同一個
`GroupInvite` 來源列（`source_id`），差別只在通知的**接收者**不同（受邀
好友 vs. 團長）與前端點擊後導向的畫面不同，不需要兩套不同形狀的 schema。

**Rationale**：直接沿用 012 已經設計好的「`type` 決定巢狀欄位是否有值」
擴充模式，這正是當初把 `friend_request` 欄位設計成 nullable、而非寫死
唯一形狀的原因——新增第二、第三種通知類型時，不需要重新設計
`NotificationSummary`、列表、未讀計數等既有機制（012 FR-011 的可擴充性
承諾）。

**Alternatives considered**：`group_invite_capacity_full` 另外設計一組
獨立欄位（例如 `group_invite_failure: ... | None`）——被否決，兩種通知
指向同一筆 `GroupInvite`、需要的展示資料完全相同（團名、對方暱稱、目前
狀態），拆成兩組欄位只是重複定義，前端還要多判斷該讀哪一個欄位。

## #8 「可邀請好友＋邀請狀態」合併成單一唯讀端點

**Decision**：`GET /groups/{group_id}/invitable-friends`（`require_admin`）
一次回傳團長的**全部**好友，每位好友附帶：`invite_status`
（`not_invited`／`pending`／`accepted`／`declined`／`invalidated`／
`already_member`）。`already_member` 由即時查詢該好友在本團是否有
`status='active'` 的 `RosterEntry` 決定，**優先於** `GroupInvite` 本身
的狀態欄位——呼應 spec Edge Cases「受邀好友已透過其他管道加入時，管理
頁面應反映其已在團內」。非 `already_member` 時，狀態取該好友在本團「最
新一筆」`GroupInvite`（依 `created_at` 排序，因為同一位好友可能經歷
「先前一筆已拒絕、之後重新邀請一筆待回覆」的歷史）。

**Rationale**：US1（挑選好友發送邀請）與 US3（查看已發送邀請狀態）在
UI 上很自然是同一個畫面、同一份好友清單，只是每一列的操作/顯示依當下
狀態而定（「尚未邀請」列可按邀請按鈕，「待回覆」列顯示狀態文字，「已在
團內」列不可再邀請）——用一個端點取一次資料，前端不需要分別呼叫好友
列表 API 與邀請列表 API 再自行比對合併。

**Alternatives considered**：兩個獨立端點（`GET .../invites` 回傳已發送
邀請清單、另外沿用既有 `GET /friends` 取好友列表，前端自行合併）——被
否決，前端合併邏輯（比對哪些好友有邀請、哪些沒有、哪些已在團內）在後端
一次做掉更簡單，也避免兩個端點之間的分頁/篩選參數不一致問題。

## #9 `GroupPublicResponse` 新增 `created_by_member` 布林欄位

**Decision**：`GroupPublicResponse` 新增 `created_by_member: bool`
（`group.created_by_member_id is not None`），於既有唯一組裝點
`group/router.py` 的 `_to_public()` 填入。管理頁面前端依此欄位判斷是否
顯示「邀請好友」區塊（FR-012）。

**Rationale**：`AdminGroupResponse.group` 直接重用 `GroupPublicResponse`
（既有慣例），這是最小改動就能讓管理頁前端拿到判斷依據的方式，不需要
新增一個管理頁專屬的欄位或端點。此欄位是否為會員建立本身不是敏感資訊
（不洩漏「是哪位會員」，只回答是非題），沿用既有 `has_password` 等同樣
性質欄位混在同一個回應形狀裡的既有慣例，沒有額外的資訊揭露疑慮。

**Alternatives considered**：只在 `AdminGroupResponse` 加這個欄位、不動
`GroupPublicResponse`——被否決，`_to_public()` 是唯一組裝點，兩者本來
就共用同一個轉換函式，分開處理反而要複製欄位賦值邏輯。
