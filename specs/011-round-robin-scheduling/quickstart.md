# Quickstart: 循環賽賽程排程

承接 003-schedule-rotation 的 quickstart：先建立一個團、取得 `GROUP_ID`/`ADMIN_TOKEN`，並新增場地。以下情境示範本 feature 帶來的行為差異（對照 003 quickstart 情境 1「一輪＝場地數場比賽」的舊行為）。

## 前置準備

```bash
GROUP_ID=$(jq -r .group_id /tmp/group.json)
ADMIN_TOKEN=$(jq -r .admin_token /tmp/group.json)
# 透過 004 join-group 端點（或直接 psql 插入 roster_entries 測試資料）
# 湊出下列各情境所需的人數。
```

## 情境 1：單打全員循環賽（對應 spec US1）

前置：`match_mode=singles`、`scheduling_mechanism=fair_rotation`、輪替名單 5 人、1 個場地。

```bash
curl -s -X POST http://localhost:8000/groups/$GROUP_ID/next-round \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

**預期**：HTTP 200；`courts[0].current_match` 非 `null`（1 個場地立即領到一場比賽）。

```bash
curl -s http://localhost:8000/groups/$GROUP_ID/schedule -H "Authorization: Bearer $ADMIN_TOKEN" | jq '.courts[0].current_match'
```

**驗證賽程表總場次數**（需直接查詢資料庫或等待逐場結束後累計，因 `GET .../schedule` 只回傳場地目前狀態、不回傳整份賽程表）：

```bash
docker exec infra-db-1 psql -U rally -d rally_stats -c \
  "SELECT COUNT(*) FROM matches WHERE group_id = '$GROUP_ID' AND round_number = 1;"
```

**預期**：`10`（= C(5,2)，5 人任兩人恰對戰一次）。

依序將場上比賽結束（`POST .../matches/{match_id}/end` 或計分至目標分數），每結束一場，該場地應立即領到賽程表中下一場「參與者目前皆未在其他場地進行中」的比賽，直到賽程表 10 場全部達終態。

## 情境 2：固定搭檔循環賽——手動搭檔（對應 spec US2）

前置：`match_mode=doubles`、`scheduling_mechanism=fixed_partner`、`partner_source=manual`、輪替名單 8 人（4 隊）、已於「搭檔設定」畫面配好 4 組搭檔、2 個場地。

```bash
curl -s -X POST http://localhost:8000/groups/$GROUP_ID/next-round \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

**預期**：HTTP 200；2 個場地皆立即領到比賽。

```bash
docker exec infra-db-1 psql -U rally -d rally_stats -c \
  "SELECT COUNT(*) FROM matches WHERE group_id = '$GROUP_ID' AND round_number = 1;"
```

**預期**：`6`（= C(4,2)，4 隊任兩隊恰對戰一次）。

## 情境 3：固定搭檔循環賽——人數為奇數防呆（對應 spec US2 情境 1）

前置：`scheduling_mechanism=fixed_partner`、輪替名單改為 7 人在場（透過踢除一人湊成奇數）。

```bash
curl -s -w "\nhttp=%{http_code}\n" -X POST http://localhost:8000/groups/$GROUP_ID/next-round \
  -H "Authorization: Bearer $ADMIN_TOKEN"
```

**預期**：`http=400`，`error_code: FIXED_PARTNER_REQUIRES_EVEN_HEADCOUNT`；不產生賽程表，`current_round_number` 不變。

## 情境 4：固定搭檔循環賽——切換為自動配對（對應 spec US2 情境 3、4）

前置：延續情境 2 的團（已有手動搭檔設定）。

```bash
curl -s -X PATCH http://localhost:8000/groups/$GROUP_ID \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"partner_source": "auto"}'
```

**預期**：HTTP 200，回應 `partner_source: "auto"`；資料庫中原本手動設定的 `partnerships` 資料列 MUST 完全不變（可另下 `SELECT * FROM partnerships WHERE group_id = '$GROUP_ID'` 比對切換前後筆數與內容一致）。

```bash
curl -s -X POST http://localhost:8000/groups/$GROUP_ID/next-round -H "Authorization: Bearer $ADMIN_TOKEN"
```

**預期**：HTTP 200；本輪隊伍組成由系統依配對次數最少原則即時決定，`partnerships` 表仍不受影響。

```bash
curl -s -X PATCH http://localhost:8000/groups/$GROUP_ID \
  -H "Authorization: Bearer $ADMIN_TOKEN" -H "Content-Type: application/json" \
  -d '{"partner_source": "manual"}'
```

**預期**：HTTP 200，切回後 `partnerships` 表內容與情境 2 設定的原始搭檔完全一致，管理員無需重新設定。

## 情境 5：個人混搭循環賽（對應 spec US3）

前置：`match_mode=doubles`、`scheduling_mechanism=individual_mixed`、輪替名單 8 人、2 個場地。

```bash
curl -s -X POST http://localhost:8000/groups/$GROUP_ID/next-round -H "Authorization: Bearer $ADMIN_TOKEN"
```

**預期**：HTTP 200；2 個場地皆立即領到比賽。

```bash
docker exec infra-db-1 psql -U rally -d rally_stats -c \
  "SELECT mp1.roster_entry_id AS a, mp2.roster_entry_id AS b, COUNT(*) \
   FROM match_participants mp1 JOIN match_participants mp2 \
     ON mp1.match_id = mp2.match_id AND mp1.team = mp2.team AND mp1.roster_entry_id < mp2.roster_entry_id \
   JOIN matches m ON m.id = mp1.match_id \
   WHERE m.group_id = '$GROUP_ID' AND m.round_number = 1 \
   GROUP BY 1, 2;"
```

**預期**：8 人共 C(8,2) = 28 種可能搭檔組合；此查詢結果應涵蓋（在此人數下組合數學可行的前提下）全部 28 組，每組恰出現一次（`COUNT = 1`）。若人數使完美覆蓋在數學上不可行，允許少數組合缺席或出現 `COUNT > 1`，但不應有大量重複集中在少數幾組（見 spec SC-001）。

## 情境 6：同一人被排入多場、場地正確跳過忙碌參與者（對應 spec Edge Cases、FR-005）

前置：延續情境 1（單打 5 人 1 場地）的循環賽賽程尚在消耗中。

```bash
# 假設場地目前比賽為 P1 vs P2；同時輪替名單中還有 P1 vs P3 尚在排隊中。
curl -s http://localhost:8000/courts/by-token/$COURT_TOKEN/state | jq '.current_match.participants'
```

**預期**：只要 P1 仍在某場地「進行中」，任何場地在領取下一場比賽時 MUST NOT 領到另一場也包含 P1 的排隊中比賽；該場地會改領取不含 P1 的下一筆可行場次，或在暫無可行場次時顯示等待狀態。

## 情境 7：Next Round 清空並重新排整輪（對應 spec US4）

前置：延續情境 1，賽程表 10 場中僅完成 3 場、其餘仍在排隊中或進行中。

```bash
curl -s -X POST http://localhost:8000/groups/$GROUP_ID/next-round -H "Authorization: Bearer $ADMIN_TOKEN"
```

**預期**：HTTP 200；原賽程表剩餘 7 場（排隊中＋進行中）全數轉為 `abandoned`；資料庫中新的 `round_number`（依既有規則遞增，見 003）底下重新產生一份完整的 10 場循環賽賽程。

```bash
docker exec infra-db-1 psql -U rally -d rally_stats -c \
  "SELECT round_number, status, COUNT(*) FROM matches WHERE group_id = '$GROUP_ID' GROUP BY 1, 2 ORDER BY 1, 2;"
```

**預期**：舊 `round_number` 底下可見多筆 `abandoned`；新 `round_number` 底下有 10 筆 `queued`（扣除已被場地立即領取而轉為 `in_progress` 的筆數）。
