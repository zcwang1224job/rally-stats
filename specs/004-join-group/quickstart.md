# Quickstart: 加入團（嘎團）

## 前置準備

```bash
GROUP_ID=$(jq -r .group_id /tmp/group.json)
JOIN_LINK_TOKEN=$(jq -r .join_link_token /tmp/group_admin_view.json)   # GET /groups/{id}/admin 之回應欄位（001）
```

## 情境 1：開團列表瀏覽與篩選（對應 spec US1、US5）

```bash
curl -s "http://localhost:8000/groups?court_name=1號場&page=1" | jq .
```

**預期**：HTTP 200；`groups[].court_names` 含符合篩選條件的場地名稱；已解散團不出現。

## 情境 2：透過加入連結進入（對應 spec US2）

```bash
curl -s "http://localhost:8000/join/$JOIN_LINK_TOKEN" | jq .
```

**預期**：HTTP 200；回傳團預覽資訊（`has_password`、`current_member_count` 等）；`already_joined: false`（未帶會員 token）。

## 情境 3：密碼驗證與 Guest 加入完整流程（對應 spec US1、US3）

```bash
curl -s -X POST "http://localhost:8000/groups/$GROUP_ID/verify-password" \
  -H "Content-Type: application/json" -d '{"password":"wrong"}'
# 預期 {"correct": false}，可無限次重試

curl -s -X POST "http://localhost:8000/groups/$GROUP_ID/join" \
  -H "Content-Type: application/json" \
  -d '{"password":"correct-password","nickname":"小明"}'
```

**預期**：HTTP 201；回傳 `guest_session_token`（非 null）；`current_member_count` 立即 +1。

## 情境 4：人數上限併發保證（對應 spec US3）

```bash
# 對僅剩 1 名額的團同時送出兩次 join 請求（背景執行模擬併發）
curl -s -X POST "http://localhost:8000/groups/$GROUP_ID/join" -H "Content-Type: application/json" -d '{"nickname":"甲"}' &
curl -s -X POST "http://localhost:8000/groups/$GROUP_ID/join" -H "Content-Type: application/json" -d '{"nickname":"乙"}' &
wait
```

**預期**：僅一方回傳 HTTP 201，另一方回傳 HTTP 409 `GROUP_FULL`；`current_member_count` 正確等於 `max_members`，不超過。

## 情境 5：Guest 身分延續（對應 spec US4）

```bash
GUEST_TOKEN=$(前一步驟回應之 guest_session_token)
curl -s "http://localhost:8000/groups/by-guest-token/$GUEST_TOKEN" | jq .
```

**預期**：HTTP 200，回傳同一筆 `roster_entry_id`；若該團已解散或該 Guest 已被踢除，改為 HTTP 404 `LINK_NOT_FOUND`。

## 驗收對照

| Quickstart 情境 | 對應 spec 驗收情境 |
|---|---|
| 1 | US1, US5 |
| 2 | US2 #1 |
| 3 | US1 #1, #3 |
| 4 | US3 #3 |
| 5 | US4 #1, #3 |
