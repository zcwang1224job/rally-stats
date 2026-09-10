# API Contract: 團內即時排行榜（強化既有戰績頁）

擴充既有 `specs/005-member-view` 之 `GET /groups/{group_id}/standings`
端點的**回應形狀**（新增欄位，不新增端點、不修改請求參數、不修改既有
錯誤碼）。

## `GET /groups/{group_id}/standings`（既有端點，回應新增 3 個欄位）

**用途不變**：US2（FR-005~010，005-member-view）之逐輪戰績查詢，本次
擴充為額外提供「總勝場排序後的名次」（018 FR-001~FR-009）。

**權限不變**：沿用既有 `resolve_active_roster_membership`（現役成員，
含訪客）。

**查詢條件變更**（見 data-model.md）：`members` 只回傳目前 `status ==
"active"` 的現役成員；已離開/被踢除者不再出現在清單中（spec.md FR-008）。

**回應** `200`：`GroupStandingsResponse`——`current_round_number`、
`rounds` 兩個既有欄位不變；`members` 陣列本身的排列順序改為依 `rank`
由小到大排序，每個成員物件新增 3 個欄位：

```json
{
  "current_round_number": 3,
  "rounds": [1, 2, 3],
  "members": [
    {
      "roster_entry_id": "uuid",
      "nickname": "小明",
      "current_status": "active",
      "rounds": { "1": { "wins": 2, "losses": 0, "left": false }, "2": { "...": "..." } },
      "rank": 1,
      "total_wins": 5,
      "total_losses": 1
    },
    {
      "roster_entry_id": "uuid",
      "nickname": "小華",
      "current_status": "active",
      "rounds": { "...": "..." },
      "rank": 2,
      "total_wins": 3,
      "total_losses": 3
    }
  ]
}
```

`rank` 並列時同一數字，緊接其後的名次依人數跳號（standard competition
ranking，research.md #6）；並列時的內部排序依 `joined_at`（先加入者在
`members` 陣列中排在前面，即使 `rank` 數字相同）。尚未有任何已完成比賽
的現役成員 MUST 仍然出現在 `members` 中（`total_wins`/`total_losses`
皆為 `0`），前端依 `rounds` 是否全空判斷是否顯示「尚無比賽紀錄」文字
（spec.md FR-007，呈現細節見 quickstart.md）。

**錯誤**：不變——`MEMBERSHIP_REQUIRED`（既有語意，沿用既有授權模式）。

---

## 兩個相關契約的共通行為

- 本端點本身**不**觸發任何即時廣播——`standings.updated` 事件（見
  `ably-events.md`）由 `schedule` domain 的比賽完成流程觸發，兩者是各自
  獨立的既有機制，這裡只是說明前端在收到該事件後應該呼叫的正是這支
  既有端點。
- 回應內容每次都是「當下」重新計算的結果，不做任何快取——與既有
  `build_group_standings()` 的既定行為一致（唯讀、無副作用）。
