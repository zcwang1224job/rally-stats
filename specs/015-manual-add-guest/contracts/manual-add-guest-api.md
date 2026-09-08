# API Contract: 團長手動新增訪客入團

新增 1 個後端端點；US2 的「個人查看連結」不需要任何新後端端點，只需要
前端新增一個進入點路由（見下方「前端進入點」）。

## `POST /groups/{group_id}/members`（新增）

**Auth**：`require_admin`（Bearer `admin_token`，與 `kick_member` 同一套
機制）。Handler MUST 檢查 `group.id == group_id`（`require_admin` 注入的
`Group` 物件 vs 路徑參數），不符時回傳 `ADMIN_TOKEN_INVALID`（401）——
比照 `DELETE /groups/{group_id}/members/{roster_entry_id}` 既有模式。

**Path params**：`group_id` (UUID)。

**Request body** `AddGuestRequest`：

```json
{
  "nickname": "小明"
}
```

**回應** `201 Created`，`JoinGroupResponse`（既有形狀，不新增欄位）：

```json
{
  "roster_entry_id": "uuid",
  "nickname": "小明",
  "guest_session_token": "a1b2c3...(32-byte urlsafe token)",
  "created_new": true
}
```

**行為**：內部直接呼叫既有 `group.service.join_group(session, group,
member=None, password=None, nickname=payload.nickname,
skip_password=True)`——人數上限檢查、已解散團擋下、暱稱驗證、
`RosterEntry` 建立、排點掛勾、即時通知廣播全部沿用既有邏輯（見
research.md #1）。

**Errors**：
- `ADMIN_TOKEN_INVALID`（401）——`group_id` 與 token 不符。
- `GROUP_DISBANDED`（409）——團已解散（FR-007）。
- `GROUP_FULL`（409）——已達 `max_members` 上限，含併發搶名額情境
  （FR-002、FR-010，`join_group()` 既有的 atomic conditional update 保證）。
- `NICKNAME_REQUIRED_FOR_GUEST`（400）——暱稱空白或超過 20 字。

暱稱允許與團內其他成員重複（FR-005），不會回傳任何「暱稱重複」錯誤。

## 前端進入點：`GET /guest-access/:token`（前端路由，非後端端點）

**目的**：實現 US2——團長把這個連結（或其 QR code）轉交給手動新增的
訪客後，對方用自己的裝置開啟即可直接看到自己的賽況，不需要密碼、不需要
再走一次加入流程。

**行為**（`GuestAccessComponent`）：

1. 讀取路徑參數 `token`。
2. 呼叫既有 `GroupJoinService.resolveGuestSession(token)`——即既有
   `GET /groups/by-guest-token/{token}` 端點（本 feature 不修改此端點），
   解析出 `group_id`／`nickname`。
3. 呼叫既有 `GroupJoinService.setGuestSessionToken(group_id, token)` 寫入
   localStorage（與自行加入的訪客走的是同一套 session 儲存機制）。
4. 導向既有 `/groups/:groupId/member-view`（訪客個人賽況/輪替狀態頁面，
   本 feature 不修改此頁面）。

**Errors**：`token` 對應不到任何現役花名冊項目時（例如訪客已被踢出、
團已解散），`resolveGuestSession()` 的既有錯誤處理方式直接沿用（本
feature 不新增錯誤情境）。

## 花名冊管理頁 UI 變更（無新後端契約，純前端）

`admin-page.component` 花名冊區塊新增：
- 一個暱稱輸入框 + 「新增訪客」按鈕，呼叫新增的
  `ScheduleService.addGuest(groupId, nickname)`（內部呼叫上述
  `POST /groups/{group_id}/members`）。
- 送出成功後：（a）輸入框清空、保持在同一個表單，支援連續新增（FR-009）；
  （b）顯示這位訪客的分享連結／QR code
  （`${window.location.origin}/guest-access/${guest_session_token}`），
  沿用既有 `QRCodeComponent` + `copyTextToClipboard`（research.md #4）。
