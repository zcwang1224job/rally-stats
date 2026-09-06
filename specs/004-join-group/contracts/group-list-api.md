# API Contract: 開團列表

`GET /groups` — 沿用 `specs/architecture.md` §3.1 已定案路徑。無需驗證即可呼叫；若帶有效 `Authorization: Bearer {member_access_token}`（006），回應含個人化欄位（research.md #2）。

## GET /groups

**Query 參數**：
- `court_name`（可選）：場地名稱子字串比對
- `court_id`（可選）：場地 UUID 精確比對
- `time_start` / `time_end`（可選，皆須同時提供）：活動時間區間篩選（區間重疊判斷）
- `page`（預設 1）

**Response 200**

```json
{
  "groups": [
    {
      "group_id": "uuid",
      "group_number": 100234,
      "name": "週三夜羽",
      "has_password": true,
      "current_member_count": 6,
      "max_members": 12,
      "match_mode": "doubles",
      "scheduling_mechanism": "fair_rotation",
      "activity_time_start": "19:00:00",
      "activity_time_end": "21:00:00",
      "status": "active",
      "court_names": ["1號場", "2號場"],
      "creator_nickname": "阿明",
      "joined_by_me": false
    }
  ],
  "page": 1,
  "total_pages": 3
}
```

`joined_by_me` 為 `null`（未帶有效 Bearer token 時）、`true`、或 `false`。

**已解散團 MUST NOT 出現於此列表**（見 data-model.md #1）。
