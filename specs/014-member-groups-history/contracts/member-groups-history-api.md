# API Contract: 我的團完整參與紀錄與戰績

延伸 `specs/006-member-friends/contracts/member-api.md` 既有的
`GET /members/me/groups`；新增 1 個端點。

## `GET /members/me/groups`（既有端點，回應形狀擴充）

**Auth**：`require_verified_member`（不變）。

**變更**：`MyGroupSummary` 新增 `is_creator`／`member_status` 兩個欄位
（見 data-model.md）；`groups` 陣列的涵蓋範圍從「只有自己建立的團」擴大為
「自己建立過 ∪ 自己曾經加入過」的聯集，不重複列出同一個團（FR-001）。

```json
{
  "groups": [
    {
      "group_id": "uuid",
      "group_number": 100123,
      "name": "週三夜羽球團",
      "status": "active",
      "is_creator": true,
      "member_status": "active"
    },
    {
      "group_id": "uuid",
      "group_number": 100456,
      "name": "假日雙打團",
      "status": "disbanded",
      "is_creator": false,
      "member_status": "left"
    }
  ]
}
```

**Errors**：`MEMBER_TOKEN_INVALID`、`EMAIL_NOT_VERIFIED`（皆既有，不變）。

## `GET /members/me/groups/{group_id}/history?page=N`（新增，Revision
2026-09-07b：`matches` 是該團全部比賽、`nickname` 搜尋全部參與者——修正
Revision 2026-09-07a 誤將整個端點窄化為「僅自己的比賽」的方向）

**Auth**：`require_member`（比照既有 `/members/me/match-records`，不要求
信箱已驗證——見 research.md #5）。

**Path params**：`group_id` (UUID)。

**Query params**：
- `page`（int, 預設 1）。
- `nickname`（str, 選填, FR-009）——搜尋該團全部已完成比賽中，任一位
  參與者（不分哪一隊）的暱稱是否包含此字串（大小寫不分）。只影響
  `matches`，不影響 `my_stats`。

**回應** `MemberGroupHistoryResponse`：

```json
{
  "group_id": "uuid",
  "group_name": "週三夜羽球團",
  "my_stats": {
    "total_matches": 12,
    "total_wins": 7,
    "total_losses": 5,
    "win_rate": 0.583,
    "round_win_rates": [
      { "round_number": 1, "wins": 1, "losses": 0, "win_rate": 1.0 }
    ],
    "opponent_records": [
      { "nickname": "小華", "wins": 3, "losses": 1, "matches": 4, "win_rate": 0.75 }
    ]
  },
  "matches": [
    {
      "match_id": "uuid",
      "round_number": 3,
      "team_a": [{ "roster_entry_id": "uuid", "nickname": "小明", "team": "A" }],
      "team_b": [{ "roster_entry_id": "uuid", "nickname": "小華", "team": "B" }],
      "score_a": 21,
      "score_b": 18,
      "winner_team": "A",
      "started_at": "2026-09-01T10:00:00Z",
      "ended_at": "2026-09-01T10:15:00Z"
    }
  ],
  "page": 1,
  "total_pages": 1
}
```

`matches` 是該團**所有**已完成比賽（不限自己是否參與那一場），套用
`nickname` 篩選後的結果（FR-004、FR-009）；`my_stats` 是會員自己的個人
統計/圖表資料，恆常反映完整參與紀錄，MUST NOT 受 `nickname` 篩選影響
（FR-005）。

**Errors**：
- `MEMBER_TOKEN_INVALID`（401）——未登入。
- `GROUP_NOT_FOUND`（404）——`group_id` 不存在。
- `GROUP_MEMBERSHIP_NEVER_HELD`（403）——該會員從未是此團的正式成員
  （不論現役／已離開／已被踢除），也不是此團的建立者
  （Clarifications 2026-09-07、FR-006、research.md #3）。

`已完成比賽數為 0`（FR-008）不是錯誤——`matches` 回傳空陣列、
`my_stats.total_matches` 為 `0`，前端顯示「尚無比賽紀錄」提示，`200`
狀態碼。
