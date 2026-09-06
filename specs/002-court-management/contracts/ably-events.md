# Ably Event Contract: 場地管理

沿用 `specs/architecture.md` §3.2 之頻道/Token capability 設計，以及 001 `contracts/ably-events.md` 已建立的 `link.regenerated` 事件格式（本文件補完本 feature 新增的三種 `link_type`）。

## `court.added` / `court.deleted`

**觸發時機**：`POST /groups/{group_id}/courts` 或 `DELETE /courts/{court_id}` 成功交易後。

**發布頻道**：`group:{group_id}:notifications`（團層級，全部場地控制板 Token 已訂閱此頻道）

**Payload**

```json
{ "event": "court.added", "court_id": "uuid", "name": "1號場" }
{ "event": "court.deleted", "court_id": "uuid" }
```

**訂閱端預期行為**：全部場地控制板畫面收到 `court.added` 時 MUST 即時新增一組對應控制項，收到 `court.deleted` 時 MUST 即時移除對應控制項，MUST NOT 需要重新整理頁面或重新產生連結（FR-015）。管理頁（同樣訂閱此頻道）可選擇性利用此事件即時更新其「場地控制」區塊，但管理頁本身已有 API 呼叫後的樂觀更新，此事件並非必要依賴。

## `link.regenerated`（`link_type: scoreboard` / `control_panel`）

**觸發時機**：`POST /courts/{court_id}/regenerate-scoreboard-link` 或 `.../regenerate-control-panel-link` 成功交易後。

**發布頻道**：`court:{group_id}:{court_id}`（場地層級，FR-032）

**Payload**

```json
{ "event": "link.regenerated", "court_id": "uuid", "link_type": "scoreboard" }
```

**訂閱端預期行為**：僅持有「與 `link_type` 相符連結」的畫面（例如 `link_type: scoreboard` 時，僅計分板畫面）MUST 依 FR-031 比對後顯示「此連結已由管理員更新，請洽管理員取得最新連結」並停止監聽、不再自動重連；`link_type` 不符的訂閱端（例如同場地的控制板，或其他場地）MUST 忽略、不受影響。

## `link.regenerated`（`link_type: all_courts`）

**觸發時機**：`POST /groups/{group_id}/regenerate-all-courts-link` 成功交易後。

**發布頻道**：`group:{group_id}:notifications`（團層級，FR-032）

**Payload**

```json
{ "event": "link.regenerated", "group_id": "uuid", "link_type": "all_courts" }
```

**訂閱端預期行為**：僅「全部場地控制板」畫面（訂閱 `group:{group_id}:notifications` 且比對 `link_type === 'all_courts'`）MUST 顯示失效提示並停止操作；管理頁（訂閱同一頻道）因比對 `link_type` 不符，MUST 忽略此事件——管理頁本身不透過此連結存取，不受影響。

## `link.regenerated`（`link_type: join`）—— 明確不適用

依 FR-033，加入連結重新產生 **MUST NOT** 觸發任何即時事件廣播；加入連結的有效性完全由後端於 `POST /groups/{group_id}/join`（004 spec 擁有）送出當下即時驗證。此處列出僅為明確排除，避免與其餘三種 `link_type` 混淆。

## 心跳備援端點（本 feature 新增部分）

- `GET /courts/by-token/{token}`：場地層級心跳（5 分鐘週期，FR-034），與計分板/控制板畫面初始化共用同一端點（見 research.md #4）。回應同時檢查 `deleted`（場地已刪除）與 `group_disbanded`（所屬團已解散）兩種情境，文案 MUST 與泛用的「連結已由管理員更新」提示區隔（分別顯示「此場地已刪除」/「此團已解散」）。
- `GET /groups/by-all-courts-token/{token}`：團層級（全部場地控制板）心跳，與場地層級心跳 MUST 使用彼此獨立的端點（FR-034 明文規定）。

兩者皆與管理頁內建場地控制區塊沿用相同的心跳判斷邏輯——該區塊本身已受 `require_admin`（001 之 `admin_token_version` 機制）保護，額外心跳僅需比照計分板/控制板之 `group_disbanded` 檢查（場地刪除對管理員而言並非「失效」而是清單即時更新，MUST NOT 觸發同一種失效提示）。
