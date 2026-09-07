# Ably Event Contract Addendum: 組團邀請

延伸 `specs/012-realtime-notifications/contracts/ably-events.md`——沿用
既有的 `member:{member_id}:notifications` 頻道與 `notification.created`
事件本身，不新增頻道或事件名稱，只多兩種觸發時機。

## `notification.created`（沿用既有事件，新增兩種觸發時機）

**觸發時機 1**：`POST /groups/{group_id}/invites` 成功後，建立
`type="group_invite"` 的通知，發布至
`member:{invitee_member_id}:notifications`。

**觸發時機 2**：`POST /group-invites/{invite_id}/accept` 因該團已額滿而
失敗時（`GROUP_FULL`，research.md #4），建立
`type="group_invite_capacity_full"` 的通知，發布至
`member:{inviter_member_id}:notifications`。

**Payload**（兩種觸發時機皆同一形狀，比照 012 既有慣例，刻意精簡）：

```json
{ "event": "notification.created", "notification_id": "uuid", "type": "group_invite" }
```

**訂閱端預期行為**：與 012 既有規則完全相同——收到事件後 MUST 呼叫
`GET /notifications/unread-count` 覆蓋本地未讀數量，MUST NOT 依賴
payload 自行組裝內容。

## 不新增事件的情境（明確排除）

- 拒絕邀請（`POST /group-invites/{invite_id}/decline`）——MUST NOT
  發布任何事件或建立任何通知給團長（spec Assumptions：拒絕不通知團長，
  沿用好友系統「解除好友不通知對方」的既有精神）。
- 好友關係解除、團解散導致邀請自動失效（FR-014、Edge Cases）——MUST NOT
  額外發布事件或建立通知；受邀好友是在「點擊既有的 `group_invite`
  通知」時才即時查詢到「已失效」的最新狀態（見
  `GET /group-invites/{invite_id}` 為即時查詢、非快照），不需要為失效
  這個時間點本身另外推播一次。
