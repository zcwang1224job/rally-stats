# Quickstart: 場地管理

驗證本 feature 端到端可運作的最小步驟。承接 001 的 quickstart：先透過 `POST /groups` 建立一個團並取得 `GROUP_ID`、`ADMIN_TOKEN`（見 `specs/001-create-manage-group/quickstart.md` 情境 1）。

## 前置準備

```bash
GROUP_ID=$(jq -r .group_id /tmp/group.json)
ADMIN_TOKEN=$(jq -r .admin_token /tmp/group.json)
```

## 情境 1：新增場地並取得專屬連結（對應 spec US1）

```bash
curl -s -X POST http://localhost:8000/groups/$GROUP_ID/courts \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "1號場"}' | tee /tmp/court.json
```

**預期**：HTTP 201；回應含 `court_id`、`scoreboard_token`、`control_panel_token`（皆為 UUID）、兩個版本欄位皆為 0。

```bash
curl -s -X POST http://localhost:8000/groups/$GROUP_ID/courts \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "1號場"}'
```

**預期**：HTTP 409（或對應狀態碼），`error_code: COURT_NAME_ALREADY_EXISTS`（同名場地重複檢查）。

```bash
curl -s http://localhost:8000/groups/$GROUP_ID/courts -H "Authorization: Bearer $ADMIN_TOKEN" | jq .active_court_count
```

**預期**：`1`。

## 情境 2：重新產生連結，優先檢查刪除狀態（對應 spec US5、FR-028）

```bash
COURT_ID=$(jq -r .court_id /tmp/court.json)
curl -s -X POST http://localhost:8000/courts/$COURT_ID/regenerate-scoreboard-link \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"expected_version": 0}'
```

**預期**：HTTP 200，`scoreboard_link_version` 變為 1，`scoreboard_token` 與原本不同。再次以 `expected_version: 0` 呼叫應得到 `VERSION_CONFLICT`。

```bash
OLD_TOKEN=$(jq -r .scoreboard_token /tmp/court.json)
curl -s http://localhost:8000/courts/by-token/$OLD_TOKEN
```

**預期**：HTTP 404 或 `error_code: LINK_NOT_FOUND`（舊 token 已失效）。

## 情境 3：刪除場地（對應 spec US2）

```bash
curl -s -X DELETE http://localhost:8000/courts/$COURT_ID -H "Authorization: Bearer $ADMIN_TOKEN"
```

**預期**：HTTP 200，`deleted: true`。

```bash
curl -s -X POST http://localhost:8000/courts/$COURT_ID/regenerate-scoreboard-link \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"expected_version": 1}'
```

**預期**：HTTP 409，`error_code: COURT_DELETED`（優先於版本衝突檢查——即使版本號正確仍拒絕）。

```bash
curl -s http://localhost:8000/groups/$GROUP_ID/courts -H "Authorization: Bearer $ADMIN_TOKEN" | jq .active_court_count
```

**預期**：`0`（已刪除場地不列入清單）。

```bash
curl -s -X POST http://localhost:8000/groups/$GROUP_ID/courts \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"name": "1號場"}'
```

**預期**：HTTP 201（已刪除場地的名稱可被沿用，不視為重複，FR-003）。

## 情境 4：全部場地控制板初始化（對應 spec US3）

```bash
curl -s http://localhost:8000/groups/by-all-courts-token/$(jq -r .guest_session_token /tmp/group.json 2>/dev/null; true)
# 實際 token 取自建團回應或團的 all_courts_control_panel_token 欄位；
# 若需直接查詢，可透過管理頁 GET /groups/{id}/admin 回應取得（見 001 plan 之 AdminGroupResponse 擴充）。
```

**預期**：HTTP 200，`courts` 陣列包含目前有效場地清單（不含各場地自己的連結 Token）。

## 情境 5：連結重新產生後的 Ably 通知（對應 spec US5，選用）

**Ably 驗證（選用，需前端或 Ably 官方 debug console 訂閱 `court:{group_id}:{court_id}`）**：情境 2 觸發計分板連結重新產生時，應收到 `{"event": "link.regenerated", "court_id": "...", "link_type": "scoreboard"}`。

## 驗收對照

| Quickstart 情境 | 對應 spec 驗收情境 |
|---|---|
| 1 | US1 #1–5 |
| 2 | US5 #1, #6 |
| 3 | US2 #1, #3, #4 |
| 4 | US3 #1 |
| 5 | US5 #2 |
