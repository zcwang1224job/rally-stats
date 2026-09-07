# Ably Event Contract: 即時通知功能

沿用 `specs/architecture.md` §3.2 之頻道設計慣例，新增 1 個頻道類型、
1 個事件；不修改既有頻道/事件（`court:{group_id}:{court_id}`、
`group:{group_id}:notifications` 及其事件維持原樣）。

## 新增頻道：`member:{member_id}:notifications`

`member_notifications_channel(member_id)` helper（`app/core/realtime.py`，
比照既有 `court_channel()`/`group_notifications_channel()` 命名慣例）。
`member_id` 為登入會員自己的 UUID（前端於初始化時解析，見
research.md #2）。安全模型與既有頻道相同——頻道名稱本身不可猜測即為
存取邊界，沿用完全相同、未經修改的 `/realtime/ably-token` 萬用字元
subscribe-only token（research.md #1）。

## `notification.created`（新增）

**觸發時機**：一則新通知成功寫入資料庫並 commit 後（本次唯一觸發來源：
`friend/service.py` 的 `create_friend_request()` 成功建立好友申請
的同一次請求，見 research.md #4）。

**發布頻道**：`member:{addressee_id}:notifications`——僅發給該通知的
接收者，不廣播給其他任何人（FR-009）。

**Payload**

```json
{ "event": "notification.created", "notification_id": "uuid", "type": "friend_request" }
```

刻意精簡，不含申請人暱稱等展示內容（research.md #6）。

**訂閱端預期行為**：收到事件後，MUST 呼叫 `GET
/notifications/unread-count` 以伺服器回應覆蓋本地未讀數量（FR-002，
SC-001：2 秒內反映於畫面）；若通知列表頁（`/notifications`）當下已開啟，
額外重新拉取列表（`GET /notifications`）以顯示新通知內容，MUST NOT 僅
依賴 payload 自行組裝列表項目。

## 斷線重連

比照 007 research.md #8，重用既有 `ReconnectRefetchService
.onReconnect()`（`apps/web/src/app/core/realtime/reconnect-
refetch.service.ts`，泛用、非計分板專屬）——連線狀態從非 `connected`
轉為 `connected` 時，觸發與收到 `notification.created` 事件完全相同的
重新拉取邏輯（未讀數量，及列表頁開啟時的列表本身），確保離線期間錯過
的 Ably 事件不會導致本地未讀數量與伺服器不同步（FR-003）。
