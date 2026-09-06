# API Contract: 場地管理

沿用 `specs/architecture.md` §3.1 已定義的路徑草案，本文件依 research.md 之決議修正/補完為最終端點清單。所有錯誤回應格式統一為 `{"error_code": "...", "detail": {...}}`（constitution 原則 VIII）。除註明「公開」者外，其餘端點皆需 `Authorization: Bearer {admin_token}`（沿用 001 之 `require_admin`）。

## POST /groups/{group_id}/courts

新增場地。

**Request**

```json
{ "name": "string, 1-20 chars" }
```

**Response 201**

```json
{
  "court_id": "uuid",
  "name": "1號場",
  "scoreboard_token": "uuid",
  "control_panel_token": "uuid",
  "scoreboard_link_version": 0,
  "control_panel_link_version": 0,
  "created_at": "2026-09-01T10:00:00Z"
}
```

**錯誤代碼**：`VALIDATION_ERROR`（名稱格式不合法）、`COURT_NAME_ALREADY_EXISTS`、`GROUP_DISBANDED`、`ADMIN_TOKEN_INVALID`。

## GET /groups/{group_id}/courts

管理頁「場地設定」區塊之場地清單（僅「目前有效」場地，依 `created_at` 排序）。

**Response 200**

```json
{
  "courts": [
    {
      "court_id": "uuid",
      "name": "1號場",
      "scoreboard_token": "uuid",
      "control_panel_token": "uuid",
      "scoreboard_link_version": 0,
      "control_panel_link_version": 0,
      "created_at": "2026-09-01T10:00:00Z"
    }
  ],
  "active_court_count": 1
}
```

`active_court_count` 供前端標題「場地 (N)」使用（FR-006），與 `courts` 陣列長度理論上一致，獨立回傳避免前端自行計算。

**錯誤代碼**：`ADMIN_TOKEN_INVALID`。

## PATCH /courts/{court_id}

重新命名場地（見 research.md #5：不設專屬版本欄位）。

**Request**

```json
{ "name": "string, 1-20 chars" }
```

**Response 200**：更新後的場地物件（同新增回應格式）。

**錯誤代碼**：`VALIDATION_ERROR`、`COURT_NAME_ALREADY_EXISTS`、`COURT_DELETED`、`ADMIN_TOKEN_INVALID`。

## DELETE /courts/{court_id}

軟刪除場地（FR-007~012）。

**Request**：無 body。

**Response 200**

```json
{ "court_id": "uuid", "deleted": true, "had_active_match": false }
```

`had_active_match` 由 `AbandonCourtMatchesHook` 的回傳值決定（見 research.md #2）；本 feature 的預設 no-op hook 恆回傳 `false`，待 003 spec 串接真正的 Match 查詢邏輯後才會反映實際情況——前端 MUST NOT 假設此欄位在 003 完工前具備真實意義，僅作為未來擴充的欄位保留。

**錯誤代碼**：`COURT_DELETED`（已刪除場地不可再次刪除，非冪等）、`ADMIN_TOKEN_INVALID`。

## POST /courts/{court_id}/regenerate-scoreboard-link

**Request**

```json
{ "expected_version": 0 }
```

**Response 200**

```json
{ "scoreboard_token": "新 uuid", "scoreboard_link_version": 1 }
```

同一筆交易內：MUST 先檢查 `deleted_at IS NULL`（優先於版本比對，FR-028）；版本比對 `expected_version` 與 `scoreboard_link_version` 是否相符；成功後產生新 Token、版本 +1、發布 `link.regenerated`(`link_type: scoreboard`) 至 `court:{group_id}:{court_id}`。

**錯誤代碼**：`COURT_DELETED`、`VERSION_CONFLICT`、`ADMIN_TOKEN_INVALID`。

## POST /courts/{court_id}/regenerate-control-panel-link

同上，作用於 `control_panel_token`/`control_panel_link_version`，事件 `link_type: control_panel`。

**錯誤代碼**：同上。

## GET /courts/by-token/{token}

**公開，無需登入**。計分板/控制板畫面初始化資料，亦作為 5 分鐘週期心跳檢查重複呼叫（見 research.md #4）。依 `token` 比對 `scoreboard_token` 或 `control_panel_token`，兩者皆可能命中，回傳對應的 `link_type`。

**Response 200**

```json
{
  "court_id": "uuid",
  "group_id": "uuid",
  "name": "1號場",
  "link_type": "scoreboard",
  "link_version": 0,
  "deleted": false,
  "group_disbanded": false
}
```

`deleted: true` 或 `group_disbanded: true` 時，前端 MUST 顯示對應的「此場地已刪除」/「此團已解散」提示並停止操作/訂閱，MUST NOT 視為單純的斷線。

**錯誤代碼**：`LINK_NOT_FOUND`（token 不存在，例如已被重新產生後的舊 token）。

## POST /groups/{group_id}/regenerate-join-link

**Request**

```json
{ "expected_version": 0 }
```

**Response 200**

```json
{ "join_link_token": "新 uuid", "join_link_version": 1 }
```

依 FR-033，此交易內 **MUST NOT** 呼叫 `publish()`——加入連結不對應任何持續訂閱的即時連線。

**錯誤代碼**：`VERSION_CONFLICT`、`GROUP_DISBANDED`、`ADMIN_TOKEN_INVALID`。

## POST /groups/{group_id}/regenerate-all-courts-link

**Request**

```json
{ "expected_version": 0 }
```

**Response 200**

```json
{ "all_courts_control_panel_token": "新 uuid", "all_courts_link_version": 1 }
```

同一筆交易內版本 +1 後發布 `link.regenerated`(`link_type: all_courts`) 至 `group:{group_id}:notifications`。

**錯誤代碼**：`VERSION_CONFLICT`、`GROUP_DISBANDED`、`ADMIN_TOKEN_INVALID`。

## GET /groups/by-all-courts-token/{token}

**公開，無需登入**。全部場地控制板畫面初始化資料，亦作為 5 分鐘週期心跳檢查重複呼叫。

**Response 200**

```json
{
  "group_id": "uuid",
  "all_courts_link_version": 0,
  "group_disbanded": false,
  "courts": [
    { "court_id": "uuid", "name": "1號場" },
    { "court_id": "uuid", "name": "2號場" }
  ]
}
```

`courts` 僅含「目前有效」場地的識別資訊（不含各場地自己的 `scoreboard_token`/`control_panel_token`——全部場地控制板透過 `court_id` 直接操作，不需要、也不應該取得其他單一場地連結的 Token，避免權限範圍超出其應有邊界）。

**錯誤代碼**：`LINK_NOT_FOUND`。
