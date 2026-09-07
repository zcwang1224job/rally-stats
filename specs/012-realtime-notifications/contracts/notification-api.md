# API Contract: 通知系統

所有端點皆需 `Authorization: Bearer {access_token}` 且已驗證
（`require_verified_member`，FR-010）。所有端點僅操作/回傳當前登入會員
自己的通知，路徑/請求皆不接受指定其他會員（避免任何跨會員存取路徑）。

## GET /notifications?page=

**Response 200**

```json
{
  "notifications": [
    {
      "notification_id": "uuid",
      "type": "friend_request",
      "read": false,
      "created_at": "2026-09-07T10:00:00Z",
      "friend_request": {
        "friend_request_id": "uuid",
        "status": "pending",
        "requester": { "member_id": "uuid", "nickname": "小明", "user_number": "aB3dEfGh" }
      }
    }
  ],
  "unread_count": 3,
  "page": 1,
  "total_pages": 1
}
```

依 `created_at` 新到舊排序（FR-004）。`friend_request.status` 為即時
查詢的最新狀態，MUST NOT 快取——若該筆好友申請已在 `/friends/requests`
被接受/拒絕，此處會同步反映（data-model.md「既有實體」段落）。

## GET /notifications/unread-count

**Response 200**：`{ "unread_count": 3 }`

專用輕量端點（FR-006），供 `nav-shell` 在每個主要頁面載入、以及收到
`notification.created` 即時事件/斷線重連時呼叫（research.md #3）。精確
數字；封頂顯示「99+」為前端呈現邏輯，此端點一律回傳精確值。

## POST /notifications/{notification_id}/read

會員點擊/開啟一則通知時呼叫（FR-007）。冪等——已是已讀狀態時重複呼叫
不報錯，`read` 恆為 `true`。

**Response 200**：`{ "notification_id": "uuid", "read": true }`

**錯誤代碼**：`NOTIFICATION_NOT_FOUND`（404，含「非本人所屬通知」之
情況，比照好友申請 `FRIEND_REQUEST_NOT_FOUND` 之既有慣例，不洩漏其他
會員的通知是否存在）。

## POST /notifications/read-all

「全部標示已讀」（FR-008）。

**Response 200**：`{ "marked_count": 5 }`

`marked_count` 為本次操作實際轉為已讀的筆數（原本已讀的不重複計入）；
呼叫時已無任何未讀通知時，回傳 `{ "marked_count": 0 }`，非錯誤。
