# Quickstart: 賽程與輪替名單

承接 001/002 的 quickstart：先建立一個團（`fair_rotation`、doubles）、取得 `GROUP_ID`/`ADMIN_TOKEN`，並新增至少 2 個場地。

## 前置準備

```bash
GROUP_ID=$(jq -r .group_id /tmp/group.json)
ADMIN_TOKEN=$(jq -r .admin_token /tmp/group.json)
# 新增 8 位輪替名單成員（透過 004 join-group 端點尚未實作前，
# 可直接以 psql 插入 roster_entries 測試資料，或等待 004 spec 完工後改用真實加入流程）
```

## 情境 1：公平輪替 Round 產生（對應 spec US1）

```bash
curl -s -X POST http://localhost:8000/groups/$GROUP_ID/next-round \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

**預期**：HTTP 200；`current_round_number` 維持為 1（此為第 1 輪，首次呼叫不遞增）；`courts[].current_match` 依場地數量填入對應場次（人數足夠時每個場地皆非 `null`）；賽程表以外的成員 `wait_count` 皆 +1，上場者歸零。

```bash
curl -s http://localhost:8000/groups/$GROUP_ID/schedule -H "Authorization: Bearer $ADMIN_TOKEN" | jq .roster
```

**預期**：上場者 `wait_count: 0`，未上場者 `wait_count` 遞增 1。

## 情境 2：零場地防呆（對應 spec US3 情境 5）

```bash
# 於一個尚未新增任何場地的團上：
curl -s -w "\nhttp=%{http_code}\n" -X POST http://localhost:8000/groups/$GROUP_ID_NO_COURTS/next-round \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

**預期**：HTTP 400，`error_code: NO_COURTS_AVAILABLE`；`current_round_number` 不變。

## 情境 3：手動安排（對應 spec US2）

```bash
# 先將排程機制切換為 manual（PATCH /groups/{id} per 001 contract，scheduling_mechanism 欄位）
COURT_ID=$(jq -r '.courts[0].court_id' /tmp/schedule.json)
curl -s -X POST http://localhost:8000/courts/$COURT_ID/manual-assign \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"participant_ids": ["p1","p2","p3","p4"], "teams": {"p1":"A","p2":"A","p3":"B","p4":"B"}}'
```

**預期**：HTTP 201，比賽狀態直接為 `in_progress`（不經過 `queued`）。

## 情境 4：Next Round 強制捨棄（對應 spec US3 情境 4）

```bash
curl -s -X POST http://localhost:8000/groups/$GROUP_ID/next-round \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

**預期**：HTTP 200，即使前一輪仍有排隊中/進行中比賽，也全數轉為 `abandoned`；若這是該團第一次生成 Round，`current_round_number` 維持 1（產生第 1 輪），否則 +1。

## 情境 5：踢除成員（對應 spec US6 情境 1）

```bash
ROSTER_ENTRY_ID=$(jq -r '.roster[0].roster_entry_id' /tmp/schedule.json)
curl -s -X DELETE http://localhost:8000/groups/$GROUP_ID/members/$ROSTER_ENTRY_ID \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

**預期**：HTTP 200，`status: "kicked"`；若該成員原在某場「排隊中」比賽的組合中，該比賽組合或整場（人數不足時）自動移除；不影響「進行中」比賽。

## 驗收對照

| Quickstart 情境 | 對應 spec 驗收情境 |
|---|---|
| 1 | US1 #1, #2 |
| 2 | US3 #5 |
| 3 | US2 #2 |
| 4 | US3 #4 |
| 5 | US6 #1 |
