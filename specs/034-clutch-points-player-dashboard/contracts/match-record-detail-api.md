# Contract: 比賽詳情回應新增 `clutch_stats`

## 範圍

**不新增端點。** 既有三個回傳 `MatchRecordDetailResponse` 的端點（皆經 `build_match_record_detail()` 組裝；四個 UI 入口——團內對戰紀錄、個人對戰歷史、團歷史戰績、好友對戰紀錄——共用這三個端點與同一個詳情彈窗）同時多出一個欄位；路徑、參數、授權判斷、錯誤代碼完全不變：

- `GET /groups/{group_id}/match-records/{match_id}`
- `GET /members/me/match-records/{match_id}`
- `GET /members/{member_id}/match-records/{match_id}`（023）

## 新增欄位

```jsonc
{
  // ...既有欄位（含 033 的 serve_stats / momentum_stats / tempo_stats / landing_distribution）完全不變...
  "clutch_stats": {
    "endgame_from": 18,                       // target_score - 3；null = 此賽制不適用（target < 11）
    "endgame": [                              // null ⇔ endgame_from 為 null
      { "team": "A", "won": 5, "total": 9 },
      { "team": "B", "won": 4, "total": 9 }
    ],
    "deuce": [                                // null = 本場未進入平分延長
      { "team": "A", "won": 3, "total": 5 },
      { "team": "B", "won": 2, "total": 5 }
    ],
    "match_points": [
      { "team": "A", "held": 3, "converted_on": 3, "saved": 1 },
      { "team": "B", "held": 1, "converted_on": null, "saved": 2 }
    ],
    "by_state": [
      { "team": "A",
        "leading":  { "won": 10, "total": 18 },
        "tied":     { "won": 4,  "total": 7 },
        "trailing": { "won": 9,  "total": 18 } },
      { "team": "B",
        "leading":  { "won": 9,  "total": 18 },
        "tied":     { "won": 3,  "total": 7 },
        "trailing": { "won": 8,  "total": 18 } }
    ],
    "comeback": { "winner": "A", "max_deficit": 5, "score_a": 8, "score_b": 13 }  // null = 勝方全場未曾落後
  }
}
```

## 規則

| 情況 | 回應 |
|---|---|
| `record_completeness != "complete"`，或有效得分與最終比分不符 | `clutch_stats: null`（與 033 四個欄位同一條件；前端顯示整塊無資料提示，FR-016） |
| `target_score < 11` | `endgame_from: null`、`endgame: null`；其餘欄位照常（FR-010） |
| 全場沒有任何一分在雙方皆 ≥ `target − 1` 時開打 | `deuce: null`（FR-011） |
| 某隊從未處於某比分狀態 | 該組 `{ "won": 0, "total": 0 }`——前端顯示「0／0 —」，MUST NOT 顯示 0%（FR-015） |
| 敗方從未握有賽末點 | `{ "held": 0, "converted_on": null, "saved": n }`——前端顯示「未曾握有賽末點」（US1 情境 9） |
| 封頂前同時為雙方的賽末點（如 29:29、cap 30） | 雙方 `held` 各 +1（US1 情境 6） |

## 保證（契約測試斷言）

- `endgame`／`deuce`／`match_points`／`by_state` 非 null 時恆為兩筆，順序 `A`、`B`。
- 每隊 `by_state` 三組 `total` 相加 ＝ `score_a + score_b`（SC-002）。
- 勝方 `held ≥ 1` 且 `converted_on == held`；敗方 `converted_on == null`。
- `comeback.max_deficit` ＝ 同一回應 `momentum_stats.max_leads` 中**敗方**那一筆的 `margin`，比分亦同（FR-014）。
- 既有欄位的值與形狀在本功能前後完全一致；`clutch_stats` 具預設值 `null`，既有呼叫端零變動。
