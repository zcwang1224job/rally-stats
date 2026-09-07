# API Contract Addendum: 通知系統擴充（組團邀請）

延伸 `specs/012-realtime-notifications/contracts/notification-api.md`
——本檔案僅記錄本 feature 對既有通知回應形狀的擴充，端點本身
（`GET /notifications`、`GET /notifications/unread-count`、
`POST /notifications/{id}/read`、`POST /notifications/read-all`）完全
不變，不重複列出。

## `NotificationSummary.type` 擴充

新增兩個合法值：`"group_invite"`（投遞給受邀好友）、
`"group_invite_capacity_full"`（投遞給團長，research.md #7）。

## 新增巢狀欄位 `group_invite`

`type` 為上述兩者其中之一時，`group_invite` 欄位（型別
`GroupInviteNotificationDetail | null`）必定非 null：

```json
{
  "notification_id": "uuid",
  "type": "group_invite",
  "read": false,
  "created_at": "2026-09-07T10:00:00Z",
  "friend_request": null,
  "group_invite": {
    "invite_id": "uuid",
    "group_id": "uuid",
    "group_name": "週三夜羽球團",
    "status": "pending",
    "inviter": { "member_id": "uuid", "nickname": "團長暱稱", "user_number": "..." },
    "invitee": { "member_id": "uuid", "nickname": "小美", "user_number": "..." }
  }
}
```

`type="group_invite_capacity_full"` 的通知也是同一個 `group_invite`
形狀（同一筆 `GroupInvite` 的資料，僅接收者不同）——前端依 `type` 決定
呈現角度與點擊後的導向目標（邀請本人 → 邀請詳情/接受拒絕畫面；團長 →
管理頁的邀請狀態區塊），不需要後端提供兩種不同的巢狀欄位形狀。
