# Contracts: 計分板發球站位顯示

本功能**不新增任何端點**，延伸兩個既有介面的既有回應/事件形狀（新增
欄位，不移除、不變更任何既有欄位的型別或語意）。

## `GET /courts/by-token/{token}/state`（既有端點，`court_live_state()`）

`CourtStateResponse.current_match`（型別 `MatchLiveDetail | null`）新增
一個欄位：

```jsonc
{
  // ...既有欄位（court_id、group_id、name、link_type、link_version、
  // deleted、group_disbanded、scoreboard_scoring_enabled、round_number、
  // waiting_reason、next_up）完全不變...
  "current_match": {
    "match_id": "...",
    "status": "in_progress",
    "score_a": 8,
    "score_b": 5,
    "participants": [/* 既有欄位，不變 */],
    // 新增：
    "serve": {
      "server_roster_entry_id": "<roster_entry_id>",
      "server_team": "A",
      "team_a_right_roster_entry_id": "<roster_entry_id>",
      "team_a_left_roster_entry_id": "<roster_entry_id>",
      "team_b_right_roster_entry_id": "<roster_entry_id>",
      "team_b_left_roster_entry_id": null
    }
  }
}
```

`serve` 為 `null` 的兩種情況：(a) `current_match` 本身為 `null`（沒有
進行中比賽，FR-007）；(b) 有進行中比賽，但該比賽尚未有發球狀態（
research.md Decision 4，`matches.serving_team IS NULL`，僅發生於
`030-score-serve-record` 部署前建立的舊比賽）。

此端點供 `scoreboard`、`control-panel`、`all-courts` 三種 courtToken
共用，`serve` 欄位在所有情境下都會回傳（不依 `link_type` 條件排除），
但依 spec Assumptions，本次只有計分板畫面會渲染它。

## `match.scoreUpdated`（既有 Ably 事件，`apply_score_delta()` 發布）

負載新增一個欄位：

```jsonc
{
  "match_id": "...",
  "score_a": 9,
  "score_b": 5,
  // 新增，形狀與上方 GET .../state 的 serve 完全相同：
  "serve": { "server_roster_entry_id": "...", "server_team": "A", "...": "..." }
}
```

訂閱端（計分板前端）既有的「淺層合併進本地 `current_match` 狀態」邏輯
一併合併這個新欄位，比照既有 `score_a`/`score_b` 的合併方式。

## 不變更的既有介面

- `POST /courts/by-token/{token}/matches/{match_id}/score`
  （`ScoreRequest`/`ScoreMutationResult`）——請求/回應形狀完全不變。
- `POST /courts/by-token/{token}/matches/{match_id}/end`——完全不變。
- `GET /groups/{group_id}/schedule`（`ScheduleResponse`/
  `CourtScheduleStatus`）與 `GET /groups/{group_id}/rounds/{round}`
  （`RoundMatchesResponse`）——這兩者是管理/回顧用清單，不使用
  `MatchLiveDetail`，不受本功能影響。
