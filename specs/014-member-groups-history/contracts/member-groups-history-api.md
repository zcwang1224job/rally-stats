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

### Revision 2026-09-21：篩選與分頁

原規格「暫不特別設計分頁機制」（spec.md）就此取代：列表改為分頁，並可篩選。
回應多了 `page`／`total_pages`，形狀與 `GET /friends` 一致；每頁筆數取系統設定
`default_page_size`（預設 20）。排序不變（`created_at` 由新到舊）。篩選在分頁**之前**
套用，多個條件為 AND。超出範圍的頁碼回傳空的 `groups`，不是錯誤。

| Query 參數 | 型別 | 說明 |
|---|---|---|
| `page` | int ≥ 1，預設 1 | 頁碼 |
| `name` | string ≤ 30 | 團名，不分大小寫的部分比對 |
| `group_number` | string ≤ 20 | 團編號，部分比對（比對數字字串） |
| `role` | `creator` \| `member` | 我是不是這個團的建立者 |
| `created_from`／`created_before` | 含 UTC offset 的 datetime | 開團時間的半開區間：`created_from` ≤ `created_at` < `created_before`，兩端皆可單獨給 |
| `disbanded_from`／`disbanded_before` | 含 UTC offset 的 datetime | 解散時間的半開區間，同上。只要給了任一端，沒有 `disbanded_at` 的團（尚未解散，或在該欄位存在前就解散）一律排除 |
| `group_id` | uuid | 精確指定一個團。團戰績頁用它取得該團的 `created_at`，不受該團落在第幾頁影響 |

```json
{ "groups": [ ... ], "page": 1, "total_pages": 3 }
```

**時間區間是「時間點」，不是日期**：畫面上的開團／解散時間是以瀏覽者當地時區顯示的，
所以由前端把當地的「某一天」換成時間點再送出（起日 → 當地該日 00:00；迄日含當天 →
當地隔日 00:00 作為 `*_before`）。若後端直接拿 `date` 去比 UTC 日期，台北早上 8 點前
開的團會被算到前一天，與畫面不一致。（`/members/me/match-records` 原本的
`date_from`／`date_to` 就是比 UTC 日期、有這個落差；Revision 2026-09-22 已改為同一套
慣例的 `ended_from`／`ended_before`，見 034 合約。）

原本 Revision 2026-09-21 初版的 `status`（團的狀態）篩選已移除，改由解散時間篩選涵蓋
「已解散」的查找。

**Errors**：參數不合法（`page=0`、未知的 `role`、非 uuid 的 `group_id`、不是 datetime
或沒有 UTC offset 的時間）→ 422。

## `GET /members/me/groups/{group_id}/history?page=N`（新增，Revision
2026-09-07b：`matches` 是該團全部比賽、`nickname` 搜尋全部參與者——修正
Revision 2026-09-07a 誤將整個端點窄化為「僅自己的比賽」的方向）

**Auth**：`require_verified_member`，與 `/members/me/match-records` 相同。
（Revision 2026-09-18：原為 `require_member`。憲章原則 IV 明文將「對戰紀錄」列為信箱驗證前 MUST 鎖定的功能，原先的寬鬆設定與之不符，已更正。Google／LINE 登入的帳號建立時即為 verified，即使沒有信箱也不受影響；受影響的只有以信箱註冊、尚未點擊驗證連結的會員，他們會得到 `EMAIL_NOT_VERIFIED`（403）。）

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
