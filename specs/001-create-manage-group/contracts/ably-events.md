# Ably Event Contract: 開團與管理

沿用 `specs/architecture.md` §3.2 之頻道/Token capability 設計；本文件聚焦本 feature 發布的事件。

## `group.disbanded`

**觸發時機**：`POST /groups/{group_id}/disband` 成功交易後，或 APScheduler 自動解散任務判定團閒置逾 1 小時後（`FR-036`）。

**發布方式**（MUST 逐一發布，MUST NOT 僅發布一次到單一萬用字元頻道 — 見 architecture.md 之釐清）：

1. 對該團底下每個 `deleted_at IS NULL` 的 Court，各自發布一次至 `court:{group_id}:{court_id}`。
2. 額外發布一次至 `group:{group_id}:notifications`。

**Payload**：

```json
{ "event": "group.disbanded" }
```

（無需 `link_type` 欄位——任何收到此事件的客戶端一律做出相同反應，不存在需要區分連結種類的情境。）

**訂閱端預期行為**：

| 訂閱端 | 收到後行為 |
|---|---|
| 計分板 | 停止監聽，顯示「此團已解散」+ 停留在解散當下最終比分 |
| 單一場地控制板 | 停止監聽，顯示「此團已解散」，停用所有操作 |
| 全部場地控制板 | 同上（僅需訂閱 `group:{group_id}:notifications`） |
| 管理頁 | 同上，並切換為唯讀模式（`GET /groups/{group_id}/admin` 之 `read_only: true`） |

## `link.regenerated`（`link_type: admin`）

**觸發時機**：`POST /groups/{group_id}/regenerate-admin-pin` 成功交易後（本 feature 擁有）；006 spec 之「忘記管理 PIN 碼」端點成功後 MUST 沿用完全相同的發布邏輯（架構層面共用同一段 service 程式碼，非重複實作）。

**發布頻道**：`group:{group_id}:notifications`

**Payload**：

```json
{ "event": "link.regenerated", "group_id": "uuid", "link_type": "admin" }
```

**訂閱端預期行為**：僅持有「管理 Token」的畫面（例如另一位管理員正開著的管理頁）在比對 `link_type === 'admin'` 後，MUST 顯示「此操作已由其他管理員執行，請重新整理頁面確認最新狀態」並停止當前連線；其餘 `link_type` 不符的訂閱端（例如計分板不訂閱此頻道；全部場地控制板 Token 收到此事件時因 `link_type` 不符而忽略）MUST NOT 受影響。

## 心跳備援端點（本 feature 相關部分）

`GET /groups/{group_id}/link-status?type=all-courts` 與管理頁沿用之 `admin_token_version` 比對機制，皆 MUST 一併檢查 `groups.status`；若為 `disbanded`，回應 MUST 視為「連結已失效」且文案與泛用的「連結已由管理員更新」明確區隔（前端顯示「此團已解散」），呼應 spec FR-035 之 30 秒週期心跳備援設計（見 architecture.md §3.2 之心跳端點完整規格，本 feature 僅補完「一併檢查解散狀態」這一項行為）。
