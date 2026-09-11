# API Contract: 我的團最終團隊排名

擴充既有 `specs/014-member-groups-history` 之 `GET
/members/me/groups/{group_id}/history` 端點的**回應形狀**（新增欄位，
不新增端點、不修改請求參數、不修改既有錯誤碼）。

## `GET /members/me/groups/{group_id}/history?page=N`（既有端點，回應新增 1 個欄位）

**用途不變**：014-member-groups-history 之比賽清單與個人統計查詢，本次
擴充為額外提供「該團所有曾參與者的最終排名」（019 FR-001~FR-012）。

**權限不變**：`require_member`，沿用既有 `verify_ever_group_member`（曾經
是該團正式成員即可，不限現役，research.md #5）。

**查詢參數不變**：`page`、`nickname`——`nickname` 只影響既有 `matches`
欄位，MUST NOT 影響新增的 `final_standings`（見下方）。

**回應** `200`：`MemberGroupHistoryResponse`——`group_id`、`group_name`、
`my_stats`、`matches`、`page`、`total_pages` 五個既有欄位不變，新增
`final_standings`：

```json
{
  "group_id": "uuid",
  "group_name": "週三夜羽球團",
  "my_stats": { "...": "既有欄位，不變" },
  "final_standings": [
    {
      "roster_entry_id": "uuid",
      "nickname": "小明",
      "current_status": "active",
      "is_self": true,
      "rank": 1,
      "total_matches": 6,
      "total_wins": 5,
      "total_losses": 1
    },
    {
      "roster_entry_id": "uuid",
      "nickname": "小美",
      "current_status": "left",
      "is_self": false,
      "rank": 2,
      "total_matches": 6,
      "total_wins": 4,
      "total_losses": 2
    },
    {
      "roster_entry_id": "uuid",
      "nickname": "小華",
      "current_status": "kicked",
      "is_self": false,
      "rank": 3,
      "total_matches": 6,
      "total_wins": 3,
      "total_losses": 3
    },
    {
      "roster_entry_id": "uuid",
      "nickname": "小強",
      "current_status": "active",
      "is_self": false,
      "rank": 4,
      "total_matches": 0,
      "total_wins": 0,
      "total_losses": 0
    }
  ],
  "matches": [ "既有欄位，不變" ],
  "page": 1,
  "total_pages": 1
}
```

**`final_standings` 涵蓋範圍與排序規則**（spec.md FR-002~FR-010，
research.md #1/#2）：

- 涵蓋該團**所有曾參與過的人**——不論現役、已離開、已被踢除，也不論是
  否擁有會員帳號（含訪客）；同一位會員的多筆歷史 `RosterEntry`（先退出
  後又重新加入）合併為同一列，統計彙總其全部參與期間的所有已完成比賽。
- 只計入狀態為「已完成」的比賽；不計入排隊中／進行中／已捨棄
  （abandoned）的比賽。
- 依 `total_wins` 由高到低排序；完全相同時依「（合併後最早的）加入團
  時間」排定順序，先加入排前面；並列名次之後的名次跳過對應的名次數量
  （standard competition ranking）。
- `total_matches` 為 `0` 代表這位參與者尚無任何已完成比賽紀錄——前端
  MUST 顯示「尚無比賽紀錄」文字，MUST NOT 誤判為並列最後一名或敗場
  掛零。
- `is_self` 由伺服器依「這一組是否包含目前呼叫此 API 的會員」計算好，
  前端 MUST 直接渲染，MUST NOT 自行比對任何 ID。
- 若該團完全沒有任何已完成比賽，`final_standings` 內每一列的
  `total_matches`／`total_wins`／`total_losses` 皆為 `0`（陣列本身
  仍包含所有曾參與者，不是空陣列）；前端依此顯示整體「尚無比賽紀錄」
  提示。

**Errors**：不變——`MEMBER_TOKEN_INVALID`（401）、`GROUP_NOT_FOUND`
（404）、`GROUP_MEMBERSHIP_NEVER_HELD`（403，見
`specs/014-member-groups-history/contracts/member-groups-history-api.md`）。

---

## 與既有契約的關係

- 本契約**擴充**而非取代 `specs/014-member-groups-history/contracts/member-groups-history-api.md`
  中同一個端點的定義；該檔案中 `my_stats`／`matches` 相關描述維持有效，
  不重複列出。
- 本端點**不**觸發任何即時廣播——與 018-group-leaderboard 的
  `standings.updated` 事件無關；`final_standings` 是快照式回應，重新
  呼叫本端點即可取得最新資料（spec.md FR-012，research.md 前言）。
