# Quickstart: 開團與管理

驗證本 feature 端到端可運作的最小步驟。假設已依 `specs/architecture.md` §5 完成 `docker-compose up` 啟動 `db` + `backend`（前端驗證步驟為選用，本文件以直接呼叫 API 驗證後端行為為主）。

## 前置準備

```bash
cd infra
docker compose up -d db backend
# 等待 backend healthcheck 通過
docker compose exec backend alembic upgrade head
```

Turnstile 測試金鑰（`.env`，本地開發固定通過）：

```
TURNSTILE_SITE_KEY=1x00000000000000000000AA
TURNSTILE_SECRET_KEY=1x0000000000000000000000000000000AA
```

## 情境 1：匿名建立團（對應 spec US1、驗收情境 1–3）

```bash
curl -s -X POST http://localhost:8000/groups \
  -H "Content-Type: application/json" \
  -d '{
    "name": "週三夜羽球團",
    "max_members": 8,
    "match_mode": "doubles",
    "scheduling_mechanism": "fair_rotation",
    "scoring_mode": "21pt",
    "creator_nickname": "小明",
    "turnstile_token": "XXXX.DUMMY.TOKEN.XXXX"
  }' | tee /tmp/group.json
```

**預期**：HTTP 201；回應含 `group_number`（≥100000）、`admin_pin`（6 碼純數字）、`admin_token`、`guest_session_token`（因未帶會員登入 Header）。

```bash
GROUP_ID=$(jq -r .group_id /tmp/group.json)
ADMIN_TOKEN=$(jq -r .admin_token /tmp/group.json)
curl -s http://localhost:8000/groups/$GROUP_ID | jq .
```

**預期**：`current_member_count: 1`。

## 情境 2：重新驗證進入管理頁（對應 spec US3）

```bash
GROUP_NUMBER=$(jq -r .group_number /tmp/group.json)
ADMIN_PIN=$(jq -r .admin_pin /tmp/group.json)
curl -s -X POST http://localhost:8000/groups/reauth \
  -H "Content-Type: application/json" \
  -d "{\"group_number\": $GROUP_NUMBER, \"admin_pin\": \"$ADMIN_PIN\"}"
```

**預期**：HTTP 200，回傳新的 `admin_token`。

```bash
curl -s -X POST http://localhost:8000/groups/reauth \
  -H "Content-Type: application/json" \
  -d "{\"group_number\": $GROUP_NUMBER, \"admin_pin\": \"000000\"}"
```

**預期**：HTTP 401，`error_code: GROUP_ADMIN_PIN_INCORRECT`。重複 10 次後應變為 `GROUP_ADMIN_LOCKED`（驗證 research.md #1 之防暴力破解門檻）。

## 情境 3：管理頁編輯（對應 spec US4）

```bash
curl -s -X PATCH http://localhost:8000/groups/$GROUP_ID \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"expected_version": 0, "name": "週三夜羽球團（改期）"}'
```

**預期**：HTTP 200，`base_settings_version` 變為 1。再次以 `expected_version: 0` 呼叫應得到 HTTP 409 `VERSION_CONFLICT`（驗證樂觀鎖）。

## 情境 4：主動重設管理 PIN 碼（對應 spec US6）

```bash
curl -s -X POST http://localhost:8000/groups/$GROUP_ID/regenerate-admin-pin \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

**預期**：HTTP 200，回傳新 `admin_pin` 與新 `admin_token`；用**舊** `ADMIN_TOKEN` 呼叫任一寫入端點（如情境 3 之 PATCH）應得到 HTTP 401 `ADMIN_TOKEN_INVALID`（驗證 `admin_token_version` 失效機制）。

## 情境 5：解散團（對應 spec US2）

```bash
curl -s -X POST http://localhost:8000/groups/$GROUP_ID/disband \
  -H "Authorization: Bearer $ADMIN_TOKEN"
curl -s http://localhost:8000/groups/$GROUP_ID | jq .status
```

**預期**：`"disbanded"`；再次呼叫 `PATCH /groups/{id}` 應得到 `GROUP_DISBANDED` 錯誤，`GET /groups/{id}/admin` 應回傳 `read_only: true`。

**Ably 驗證（選用，需前端或 Ably 官方 debug console 訂閱 `group:{group_id}:notifications`）**：解散當下應收到 `{"event": "group.disbanded"}`。

## 情境 6：自動解散（對應 spec US5，需手動調整資料庫時間以模擬 1 小時）

```bash
docker compose exec db psql -U rally -d rally_stats -c \
  "UPDATE groups SET last_activity_at = now() - interval '61 minutes' WHERE id = '$GROUP_ID';"
# 等待 APScheduler 下一次執行（每分鐘一次，最壞情況等待 60 秒）
sleep 65
curl -s http://localhost:8000/groups/$GROUP_ID | jq .status
```

**預期**：`"disbanded"`（不需任何管理員手動操作）。

## 驗收對照

| Quickstart 情境 | 對應 spec 驗收情境 |
|---|---|
| 1 | US1 #1, #3 |
| 2 | US3 #1, #2 |
| 3 | US4 #1 |
| 4 | US6 #1, #2, #3 |
| 5 | US2 #1, #3 |
| 6 | US5 #1 |
