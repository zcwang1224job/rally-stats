# Contracts: 詳細計分模式的加分/收回 API

## 新端點：`POST .../matches/{match_id}/score-detailed`

兩個版本，權限驗證完全比照既有 `/score` 端點的對應版本（見 `contracts` 目錄外的既有實作，不重新設計權限模型）：

- `POST /courts/by-token/{token}/matches/{match_id}/score-detailed`（token 版：`control_panel_token`，或該團已開啟 `scoreboard_scoring_enabled` 時的 `scoreboard_token`——與既有 `score_by_token` 同一組 `_can_score_by_token` 判斷）
- `POST /groups/{group_id}/courts/{court_id}/matches/{match_id}/score-detailed`（admin 版，`require_admin` 依賴）

### Request Body（`ScoreDetailedRequest`）

```jsonc
{
  "roster_entry_id": "<uuid>",
  "landing_x": 0.62,
  "landing_y": 0.18
}
```

- `roster_entry_id`：計分員選擇的得分球員，MUST 是該場比賽的既有參賽者之一。
- `landing_x`/`landing_y`：浮點數，有效範圍 `[-0.3, 1.3]`（data-model.md）。

### Response（沿用既有 `ScoreMutationResult`，不新增回應形狀）

```jsonc
{
  "applied": true,
  "match_id": "...",
  "status": "in_progress",
  "score_a": 9,
  "score_b": 5,
  "winner_team": null
}
```

`side`/`delta` 不需要由前端傳入——後端依 `roster_entry_id` 所屬隊伍換算 `side`，`delta` 恆為 `+1`（這是新增一分的端點，不是修正端點）。

### 錯誤（新增）

| 錯誤代碼 | 情境 | HTTP 狀態 |
|---|---|---|
| `PARTICIPANT_NOT_IN_MATCH` | `roster_entry_id` 不是這場比賽的既有參賽者 | 422 |
| `INVALID_LANDING_COORDINATES` | `landing_x`/`landing_y` 超出 `[-0.3, 1.3]` | 422 |
| `DETAILED_SCORING_NOT_ENABLED` | 目標比賽 `matches.detailed_scoring_enabled = false`（簡易模式比賽誤呼叫本端點） | 422 |

沿用既有的 `LINK_NOT_FOUND`（token 版）/`ADMIN_TOKEN_INVALID`（admin 版）/`MATCH_NOT_FOUND`。

### 內部實作備註（非對外契約，供 tasks.md 參照）

`apply_detailed_score()`（新函式）驗證上述三項後，換算 `side`，呼叫既有 `apply_score_delta(session, court, match_id, side, 1, source=..., shot_placement=ShotPlacementInput(roster_entry_id, landing_x, landing_y))`（research.md Decision 3）。

## 既有端點：「修正比分」不新增版本，直接沿用

```text
POST .../matches/{match_id}/score   { "side": "A", "delta": -1 }
```

請求/回應形狀完全不變（`ScoreRequest`/`ScoreMutationResult`）。差別僅在後端 `apply_score_delta()` 的 `delta < 0` 分支內部，新增「刪除該隊最新一筆 `ShotPlacementRecord`（若存在）」的副作用——對簡易模式比賽是 no-op，前端呼叫端完全不需要因為模式不同而改變呼叫方式（research.md Decision 4）。

## `GET .../state`（既有端點）——`MatchLiveDetail` 新增一個欄位

前端需要知道「目前這場比賽該顯示簡易 +1/-1 按鈕，還是開啟詳細模式的落點/選球員流程」，因此 `MatchLiveDetail`（`CourtStateResponse.current_match` 的型別，供計分板/控制板/全場地控制板三者共用的同一個既有端點）新增：

```jsonc
{
  // ...既有欄位（match_id、status、score_a、score_b、participants、serve〔029/030〕）完全不變...
  "detailed_scoring_enabled": true
}
```

直接反映 `matches.detailed_scoring_enabled`（比賽建立當下的快照值，見 data-model.md），**不是**即時讀取 `group.detailed_scoring_enabled`——一場已經在進行中的比賽，即使團設定之後被改變，這個欄位的值 MUST 維持不變（FR-006）。

## `match.scoreUpdated`（既有 Ably 事件）——不新增欄位

本功能刻意 MUST NOT 在這個既有事件負載中新增落點/球員欄位——落點紀錄本次不提供任何查詢/顯示介面（spec Assumptions），沒有前端消費者需要即時收到這個資料；`score_a`/`score_b`/`serve`（029/030 既有欄位）維持原樣，加分是否為詳細模式對訂閱端而言無感。
