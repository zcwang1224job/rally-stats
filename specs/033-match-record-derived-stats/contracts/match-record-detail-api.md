# Contracts: 比賽詳情回應擴充（`MatchRecordDetailResponse`）— 衍生統計

本功能**不新增任何端點**——擴充既有四個端點共用的回應形狀。請求路徑、權限驗證、既有錯誤代碼、既有回應欄位完全不變，只有回應 body 多了四個欄位：`serve_stats`、`momentum_stats`、`tempo_stats`、`landing_distribution`。

## 受影響的既有端點（皆不變更路徑／權限，僅回應內容擴充）

| 端點 | 授權 | 服務層函式 |
|---|---|---|
| `GET /groups/{group_id}/match-records/{match_id}` | 現役 Guest／Member（`resolve_active_roster_membership`） | `get_group_match_record_detail` → `build_match_record_detail` |
| `GET /members/me/match-records/{match_id}` | 已登入會員（`require_member`）；同時供「個人對戰歷史」與「我的團→歷史戰績」兩個入口使用 | `get_member_match_record_detail` → `build_match_record_detail` |
| `GET /members/{member_id}/match-records/{match_id}` | 已登入且已驗證信箱的會員，檢視好友 | `view_member_match_record_detail` → … → `build_match_record_detail` |

全部最終呼叫同一個 `build_match_record_detail(session, match)`，因此本次擴充自動套用到全部入口（FR-005）。

## Response（新增欄位；既有欄位省略）

```jsonc
{
  // ...既有欄位完全不變：match_id、round_number、team_a、team_b、score_a、score_b、
  // winner_team、started_at、ended_at、record_completeness、events、player_stats...

  "serve_stats": {
    "teams": [
      { "team": "A", "serve_points_won": 12, "serve_points_total": 19,
                     "receive_points_won": 9,  "receive_points_total": 16 },
      { "team": "B", "serve_points_won": 7,  "serve_points_total": 16,
                     "receive_points_won": 7,  "receive_points_total": 19 }
    ],
    "players": [   // 雙打：全部四位（含全 0）；單打：[]
      { "roster_entry_id": "3f9e...uuid", "nickname": "小明", "team": "A",
        "serve_points_won": 7, "serve_points_total": 10,
        "receive_points_won": 5, "receive_points_total": 8 }
      // ...
    ],
    "excluded_points": 1   // 恆 >= 1（開賽第一分）
  },

  "momentum_stats": {
    "longest_runs": [
      { "team": "A", "length": 5, "start_score_a": 8, "start_score_b": 9,
                                  "end_score_a": 13, "end_score_b": 9 },
      { "team": "B", "length": 3, "start_score_a": 2, "start_score_b": 1,
                                  "end_score_a": 2, "end_score_b": 4 }
    ],
    "max_leads": [
      { "team": "A", "margin": 6, "score_a": 21, "score_b": 15 },
      { "team": "B", "margin": 2, "score_a": 2,  "score_b": 4 }
      // 從未領先：{ "team": "B", "margin": 0, "score_a": null, "score_b": null }
    ],
    "lead_changes": [
      { "new_leader": "B", "score_a": 2,  "score_b": 3 },
      { "new_leader": "A", "score_a": 10, "score_b": 9 }
    ]
  },

  "tempo_stats": {
    "average_seconds": 24.6,
    "counted_points": 33,
    "longest": { "seconds": 71.2, "score_a": 14, "score_b": 12 }
  },

  "landing_distribution": [   // 非空時恆列出全部參賽者
    { "roster_entry_id": "3f9e...uuid", "nickname": "小明", "team": "A",
      "scored": [ { "x": 0.82, "y": 0.21 }, { "x": 1.04, "y": 0.55 } ],  // 1.04 = 界外，原樣回傳
      "scored_total": 4,
      "lost":   [ { "x": 0.18, "y": 0.77 } ],
      "lost_total": 2 }
    // ...
  ]
}
```

## 無資料的表示法（前端據此顯示提示，FR-003）

| 情況 | `serve_stats` | `momentum_stats` | `tempo_stats` | `landing_distribution` |
|---|---|---|---|---|
| `record_completeness` 為 `"partial"` 或 `"none"` | `null` | `null` | `null` | `[]` |
| 有效得分數與最終比分對不起來（防呆） | `null` | `null` | `null` | `[]` |
| 030 上線前的比賽（無發球快照） | `null` | 有值 | 有值 | 依落點資料 |
| 簡易計分模式（無落點紀錄） | 依發球資料 | 有值 | 有值 | `[]` |
| 每一分之間都夾著修正（無可計入耗時） | 依發球資料 | 有值 | `null` | 依落點資料 |

後端 MUST NOT 以全零結構表示無資料；四個欄位彼此獨立，一個為空不影響其他。

## 不變量（契約測試 MUST 斷言）

1. `serve_stats != null` 時：`teams` 長度恆為 2；`sum(teams[].serve_points_total) + excluded_points == score_a + score_b`；`teams[A].serve_points_total == teams[B].receive_points_total`（反之亦然）；`excluded_points >= 1`。
2. `serve_stats.players`：單打恆為 `[]`；雙打長度恆為 4 且順序＝`team_a` + `team_b`。
3. `momentum_stats != null` 時：`longest_runs`、`max_leads` 長度恆為 2（A、B）；勝方的 `max_leads.margin >= abs(score_a - score_b)`。
4. `landing_distribution` 非空時：長度＝參賽者總數；每位球員 `scored.length <= scored_total`、`lost.length <= lost_total`；`scored_total`／`lost_total` 分別等於 `player_stats` 中同一球員的 `scored_count`／`fault_count`。
5. 既有欄位（含 `events`、`player_stats`）的值與本功能上線前逐位元一致。

## 錯誤代碼

無新增。沿用既有 `MATCH_NOT_FOUND`（404）等行為。
