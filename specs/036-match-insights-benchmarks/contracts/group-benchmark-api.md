# Contract: 團內比較（新增兩支端點）

兩支皆 `Depends(security.require_verified_member)`，皆為唯讀、不寫入任何資料、不觸發通知或廣播。

## `GET /members/me/benchmark-groups`

會員可以拿來比較的團，附「我在該團的已完成比賽場數」，供選單與預設值使用。

```jsonc
{
  "groups": [
    { "group_id": "…", "group_number": "483920", "name": "週三羽球", "status": "active",
      "member_status": "active",        // active | left | kicked（沿用 014 的定義）
      "my_completed_matches": 86 }
  ]
}
```

- 範圍：我曾有 `member_id` 為我的名單列的團（不論狀態、不論團是否已解散）——與 `group-benchmark` 的授權檢查是**同一個條件**，確保清單上的每個團一定打得開。建立團時建立者必定同時取得一列名單（已查證 `create_group()`），因此實際涵蓋範圍與 014「我的團」相同。以訪客身分參加的團不在其中。
- 排序：`my_completed_matches` 由多到少，再依 `created_at` 新到舊。前端以第一筆為預設（FR-027）。
- 清單為空 → `{"groups": []}`；前端顯示說明（US3-10）。

## `GET /members/me/group-benchmark?group_id=<uuid>`

### 授權

`verify_ever_group_member(group_id, member_id)`，**每次請求當下判定**（FR-038）：

| 情況 | 回應 |
|---|---|
| 我曾是該團正式成員（現役／已離開／已被踢除／團已解散） | 200 |
| 我從未加入該團（即使知道 `group_id`） | `403 GROUP_MEMBERSHIP_NEVER_HELD` |
| 團不存在 | `403 GROUP_MEMBERSHIP_NEVER_HELD`——授權檢查只查名單列，與「從未加入」無法區分，因此不洩漏團是否存在 |
| 我在該團有多段參與期間（離開後重新加入） | 200（research Decision 7 的修正） |

### 回應

```jsonc
{
  "group": { "group_id": "…", "name": "週三羽球" },
  "total_matches": 1000,           // 該團已完成比賽總數（計算範圍，固定為全部歷史）
  "my_matches": 86,
  "metrics": [                     // 23 項，key 與順序同儀表板
    {
      "key": "team_serve", "kind": "rate", "better_when": "higher",
      "mine": { "value": 0.5310, "numerator": 412, "denominator": 776, "matches_used": 61 },
      "status": "ok",              // ok | pool_too_small | self_below_minimum | no_direction
      "group_average": 0.4870,
      "pool_size": 12,
      "rank": 3
    },
    { "key": "own_serve", "kind": "rate", "better_when": "higher",
      "mine": null, "status": "pool_too_small", "group_average": null, "pool_size": 2, "rank": null },
    { "key": "match_points_saved", "kind": "average", "better_when": null,
      "mine": { … }, "status": "no_direction", "group_average": 0.41, "pool_size": 9, "rank": null }
  ],
  "insights": { /* 與儀表板的 insights 同結構；已合併團內來源 */ }
}
```

### 匿名（FR-032、SC-007、Clarifications 2026-09-18）

**團內比較本身的產出——`group`、`metrics`，以及 `insights` 中 `source` 為 `benchmark` 的敘述——不含任何可識別或可還原其他球員的欄位。** 沒有名單、沒有個別數值、沒有最高／最低值。每位球員的個別數值只存在於伺服器端的運算過程中。

`insights` 是「檢視者未篩選的個人摘要＋團內來源」的合併版，因此它**也**包含檢視者**自己的**對戰組合敘述（`insights.matchups`，例如「和某某搭檔勝率較高」）。那是檢視者本人與某人的對戰紀錄，出自他自己的對戰清單，內容與 `GET /members/me/match-dashboard` 回傳的逐字相同——不是團內比較算出來的、也不含該球員自己的任何統計。這是回應中**唯一**可能出現其他球員暱稱的地方（實作時以 1,000 場的示範資料實測發現，初版契約寫「回應全文不含任何其他球員暱稱」過寬，已更正）。

契約測試：(1) `group`＋`metrics`＋團內來源敘述序列化後不含任何其他參賽者的暱稱、`member_id`、`roster_entry_id`；(2) `insights.matchups` 與同一位會員的儀表板回應**完全相等**。

### 規則

| 情況 | 回應 |
|---|---|
| 計算範圍 | 該團**全部**已完成比賽；不接受任何篩選參數（FR-028、FR-032）。多送的 query 參數被忽略 |
| 比較對象 | 在該團打過已完成比賽的所有球員，依 `player_key` 合併（會員跨多段參與期間合併；訪客每個名單列各自一人），不論目前狀態 |
| 某球員某指標 `matches_used < 5` 或 `value` 為 null | 不納入該指標的平均與名次（FR-030） |
| 達門檻者 < 3 人 | `status: "pool_too_small"`，`group_average`／`rank` 為 null |
| 指標無好壞方向 | `status: "no_direction"`，有 `group_average`、無 `rank` |
| 我未達門檻 | `status: "self_below_minimum"`，有 `group_average`／`pool_size`、無 `rank`；`pool_size` 不含我 |
| 並列 | 標準競賽排名（兩人並列第 2 → 下一位第 4） |
| `better_when: "lower"` | 數值最低者第 1 名 |
| `mine` 與其他人的值 | 由同一個函式、同一批比賽算出（FR-029） |
| `insights` | 以我的**未篩選**跨團儀表板＋本團基準，經同一個 `insights.derive()` 產生；`benchmark_group_name` 為本團名稱；`benchmark_quartile` 的 `params.mine`／`group_average`／`rank`／`pool_size` 與 `metrics[]` 中同一指標逐位相等 |
| 該團只用簡易計分 | 只有 `avg_*` 四項可能為 `ok`，其餘為 `pool_too_small` |

### 前端如何使用 `insights`

已載入本回應**且**頁面沒有任何作用中的篩選（含 `partner_key`／`opponent_key`）→ 摘要區塊顯示本回應的 `insights`。否則顯示儀表板回應的 `insights`；若此時已選定比較的團，另顯示一行說明（FR-034）。前端不做任何合併、排序或門檻判斷。

### 效能

40 位球員、1,000 場已完成比賽的團 < 5 秒（SC-008）。查詢數與比賽數無關：參賽者 1 次＋逐分紀錄每 500 場 3 次＋本人儀表板的固定查詢。純運算在 `asyncio.to_thread()` 中執行。
