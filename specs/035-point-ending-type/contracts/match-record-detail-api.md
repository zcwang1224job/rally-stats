# Contract: 比賽詳情回應新增得分方式

## 範圍

**不新增端點。** 既有三支回傳 `MatchRecordDetailResponse` 的端點（皆經 `build_match_record_detail()` 組裝，四個 UI 入口共用）同時得到下列兩處新增；路徑、授權、既有欄位完全不變：

- `GET /groups/{group_id}/match-records/{match_id}`
- `GET /members/me/match-records/{match_id}`
- `GET /members/{member_id}/match-records/{match_id}`

## 新增 1：逐點明細多一個欄位

```jsonc
"events": [
  {
    "side": "A", "delta": 1, "score_a": 9, "score_b": 5, "elapsed_seconds": 412,
    "detail": {
      "scoring_roster_entry_id": "…", "scoring_nickname": "小明",
      "losing_roster_entry_id": "…",  "losing_nickname": "小美",
      "landing_x": 1.04, "landing_y": 0.5,
      "ending_type": "out"            // 新增；null＝未記錄
    }
  }
]
```

`detail` 為 `null` 的條件隨之調整：**五個**欄位（兩位球員、落點 x／y、`ending_type`）全空才視為沒有明細。只記了得分方式的一分，`detail` 不為 `null`，其餘欄位為 `null`。

## 新增 2：`ending_stats`

```jsonc
"ending_stats": {
  "recorded_points": 31,     // 記錄了得分方式的有效得分數
  "total_points": 40,        // 有效得分總數＝score_a + score_b
  "teams": [                 // 恆為 [A, B]
    { "team": "A", "winners": 9, "errors": 8,
      "errors_by_type": { "out": 4, "net": 3, "serve_fault": 1, "other_error": 0 } },
    { "team": "B", "winners": 6, "errors": 8,
      "errors_by_type": { "out": 5, "net": 2, "serve_fault": 0, "other_error": 1 } }
  ],
  "players": [               // 全部參賽者，順序 team_a + team_b
    { "roster_entry_id": "…", "nickname": "小明", "team": "A",
      "winners": 6, "opponent_errors": 4, "scored_unrecorded": 2,
      "beaten_by_winners": 3, "own_errors": 5, "lost_unrecorded": 1 }
  ]
}
```

- `teams[].winners`＝該隊以 `winner` 得到的分；`teams[].errors`＝該隊**犯下**的失誤（＝對手以失誤類得到的分）。
- 球員的 `winners` 記在得分球員上；`own_errors` 記在失分球員上。沒有記錄對應球員的分數只進隊伍層級（FR-003）。

## 規則

| 情況 | 回應 |
|---|---|
| 全場沒有任何一分記錄得分方式（舊比賽、簡易計分、全部略過） | `ending_stats: null`；`events[].detail.ending_type` 皆為 `null`——其餘內容與上線前一致（FR-017） |
| `record_completeness != "complete"`，或有效得分與最終比分不符 | `ending_stats: null`（與 033／034 的欄位同一條件）；`events[].detail.ending_type` 仍照實回傳 |
| 只有部分分數記錄了得分方式 | 照常回傳；`recorded_points < total_points`（FR-016） |
| 被 `-1` 撤銷的那一分 | 不計入任何數字 |

## 保證（契約測試斷言）

- 每位球員：`winners + opponent_errors + scored_unrecorded` ＝同一回應 `landing_distribution`／`player_stats` 中該球員的得分總數；失分端同理（FR-015）。
- `teams[A].winners + teams[B].errors + teams[B].winners + teams[A].errors == recorded_points`。
- 每隊 `errors == out + net + serve_fault + other_error`。
- 既有欄位（含 032 的 `player_stats`、033 的四個欄位、034 的 `clutch_stats`）的值與形狀在本功能前後完全一致；`ending_stats` 具預設值 `null`，`ending_type` 具預設值 `null`，既有呼叫端零變動。
- 回應不新增任何暱稱以外的識別資訊；可見範圍與既有完全相同。
