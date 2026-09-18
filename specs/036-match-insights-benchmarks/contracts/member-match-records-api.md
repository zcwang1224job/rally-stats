# Contract: 個人對戰紀錄新增搭檔／對手戰績與精確篩選

## 範圍

**不新增端點。** 既有兩支端點的回應擴充、query 參數新增兩個；路徑、授權與其餘內容不變：

- `GET /members/me/match-records`（`require_verified_member`）
- `GET /members/{member_id}/match-records`（另經 `_resolve_viewable_member()`，023）

014 的 `GET /members/me/groups/{group_id}/history` 內含同一個建構函式的結果，但它的 `my_stats.opponent_records` 宣告為既有的 `OpponentRecord`，因此**維持原本五個欄位、不含新欄位**——該頁首版不呈現搭檔／對手戰績（規格 Assumptions），回應也就不多帶用不到的資料。列的切分同樣改為依身分。

## 差異 1：新增 query 參數

| 參數 | 格式 | 意義 |
|---|---|---|
| `partner_key` | `m:<uuid>` 或 `r:<uuid>` | 只留「該球員與我同隊」的比賽 |
| `opponent_key` | 同上 | 只留「該球員在對方隊伍」的比賽 |

- 與既有的 `opponent1`／`opponent2`／`partner`（暱稱子字串）及所有其他篩選**同時生效**（AND）。
- 同樣適用於 `GET /members/me/match-dashboard` 與好友版——四支路由的篩選參數集合 MUST 完全相同（以守門測試鎖定），見 [member-match-dashboard-api.md](./member-match-dashboard-api.md)。
- 格式不合 → `422 INVALID_PLAYER_KEY`。格式正確但無比賽符合 → 正常的空結果。

## 差異 2：回應欄位

```jsonc
{
  // …既有欄位完全不變：matches, total_matches, total_wins, total_losses,
  //   win_rate, round_win_rates, page, total_pages

  "opponent_records": [            // 型別擴充；既有五個欄位的名稱與意義不變
    {
      "player_key": "m:6b1f…",     // 新
      "member_id": "6b1f…",        // 新；訪客為 null
      "nickname": "阿哲",           // 改為「最近一場比賽中的暱稱」
      "matches": 12, "wins": 3, "losses": 9, "win_rate": 0.25,
      "avg_margin": -4.3,          // 新；我方 − 對方 的每場平均，一位小數
      "low_sample": false          // 新；matches < 3
    }
  ],
  "partner_records": [ /* 同上結構；只計雙打 */ ],   // 新
  "matchup_highlights": {                           // 新；值為 player_key 或 null
    "most_played_partner": "m:…",
    "best_partner": "m:…",
    "most_faced_opponent": "r:…",
    "toughest_opponent": null
  },
  "doubles_matches": 41                             // 新；0 → 前端顯示「單打比賽沒有搭檔」
}
```

## 規則

| 情況 | 回應 |
|---|---|
| 彙總範圍 | 目前篩選結果的**全部**比賽，不是目前這一頁（與既有 `opponent_records` 一致） |
| 排序 | 兩個列表皆依 `matches` 由多到少；同場數依 `player_key` 字典序（穩定、可重現） |
| 同一會員在不同團、不同暱稱 | 同一列（`m:` 鍵） |
| 不同球員同暱稱（含多位 `"Deleted User"`） | 各自一列 |
| 未綁定訪客 | 每個名單列各自一列（`r:` 鍵），不跨團合併 |
| 雙打的兩位對手 | 該場分別計入兩列，分差各計一次 |
| 單打 | 不進 `partner_records` |
| 同一人既當過搭檔也當過對手 | 兩個列表各有一列，各只計對應角色的比賽 |
| `best_partner`／`toughest_opponent` | 只從 `matches ≥ 5` 的列選；勝率相同取場數多者，再相同取 `player_key` 較小者；無人達門檻 → `null` |
| `most_played_partner`／`most_faced_opponent` | 場數最多且 `matches ≥ 3`；否則 `null` |
| 好友端點 | 回傳相同欄位（好友的搭檔／對手戰績，FR-037）；前端在好友頁不提供點擊篩選 |

## 相容性

- `opponent_records[].nickname`／`wins`／`losses`／`matches`／`win_rate` 仍在，既有前端不需修改即可運作。
- **行為變更（刻意）**：列的切分由暱稱改為身分，因此同一份資料的列數可能與上線前不同。既有測試 `test_member_match_records.py` 中以暱稱斷言合併的案例需改寫。
- 團的 `GroupMatchRecordsResponse.player_records`（`OpponentRecord`）**不變**。
