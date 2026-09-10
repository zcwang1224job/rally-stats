# Ably Event Contract: 團內即時排行榜（強化既有戰績頁）

沿用 `specs/architecture.md` §3.2 之頻道設計慣例，新增 1 個事件，發布於
既有頻道 `group:{group_id}:notifications`（`group_notifications_channel()`
helper，`app/core/realtime.py`）——不新增頻道，不修改既有頻道上的其他
事件（`member.left`、`link.regenerated` 等維持原樣）。

## `standings.updated`（新增）

**觸發時機**：一場比賽的狀態被判定為 `"completed"` 之後（全系統唯一觸發
來源：`schedule/service.py` 的 `apply_score_delta()` → `_publish_match_
ended()`，見 research.md #1）。`abandoned`（提前結束/捨棄）路徑 MUST NOT
觸發本事件——捨棄的比賽不計入任何人的戰績（spec.md FR-005），排名不會
因此改變。

**發布頻道**：`group:{group_id}:notifications`——與該場比賽所屬的團一致，
廣播給任何目前正在檢視該團戰績頁的成員，不限特定場地（research.md #1）。

**Payload**

```json
{ "event": "standings.updated", "group_id": "uuid" }
```

刻意精簡，不含排名結果本身——訂閱端 MUST 收到事件後重新呼叫 `GET
/groups/{group_id}/standings` 取得伺服器計算好的最新完整排名，MUST NOT
依賴 payload 自行推算或增量更新排名（憲章原則 X，research.md #1/#2）。

**訂閱端預期行為**：戰績頁（`standings.component`）當下已開啟時，收到
事件後 MUST 在 2 秒內（spec.md SC-002）重新呼叫 `GET /groups/{group_id}
/standings` 並以回應完整覆蓋畫面上的名次與戰績。

## 斷線重連

比照 012-realtime-notifications，重用既有 `ReconnectRefetchService
.onReconnect()`（`apps/web/src/app/core/realtime/reconnect-
refetch.service.ts`，泛用、非計分板專屬）——連線狀態從非 `connected`
轉為 `connected`、或使用者重新切回/回到戰績頁畫面時，觸發與收到
`standings.updated` 事件完全相同的重新拉取邏輯，確保離線期間錯過的
事件不會導致畫面停留在過時的名次上（spec.md FR-012/SC-006）。**不**
新增任何「連線中斷」提示元件（與 007-live-scoreboard 之要求不同——本
畫面純唯讀、無操作遺失風險，spec.md Clarifications Q4）。
