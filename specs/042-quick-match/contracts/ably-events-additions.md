# Ably Events: 快速比賽的新增與沿用

所有事件仍由後端在資料庫 commit 後發布（`core/realtime.py::publish()`，請求內由 `PublishAfterResponseMiddleware` 延後送出；hook 與 sweep 內直接送出）。前端只訂閱、不發布（Constitution X）。

## 新事件

### `quickMatch.lineupChanged`（頻道 `court:{group_id}:{court_id}`）

名單或位置狀態有任何變化時發布：好友接受／拒絕／逾時／被轉為訪客、換人再打送出、取消。

```json
{ "group_id": "uuid", "state": "waiting", "pending_count": 1 }
```

前端（等待畫面、控制板的 quick 區塊）收到後重新載入 `GET /quick-matches/by-token/{token}`，不從 payload 更新畫面。

## 沿用的事件（快速比賽不改語意）

| 事件 | 頻道 | 何時 | 前端反應 |
|---|---|---|---|
| `rotation.updated` | court | `manual_assign()` 開賽（首場、再打一場、換人再打、好友全部接受） | 控制板／計分板 `loadState()`；等待畫面收到後導向控制板 |
| `match.scoreUpdated` / `match.ended` | court | 計分、自然結束、提前結束 | 既有；`match.ended` 後控制板 `current_match` 為空 → 顯示 quick 區塊 |
| `group.disbanded` | court + group notifications | 結束／取消／閒置收尾 | 既有的 `group_disbanded` 畫面，文字依 `group_kind` |
| `standings.updated` | group notifications | 自然結束 | 既有 |
| `notification.created` | `member:{member_id}:notifications` | 好友收到 `quick_match_invite` | 既有的通知鈴與列表；型別→路由對應新增一條 |

## 訂閱

等待畫面與控制板以既有的 `create_subscribe_token_request()` 取得 court 頻道的訂閱 token；`GET /quick-matches/by-token/{token}` 回傳的 `group_id`／`court_id` 用來組頻道名。
