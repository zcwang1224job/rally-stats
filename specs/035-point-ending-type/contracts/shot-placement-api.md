# Contract: 補記得分細節的端點新增 `ending_type`

## 範圍

**不新增端點。** 既有三支「補記一分的細節」端點共用同一個 request schema（`RecordShotPlacementRequest`）與同一個 service 函式（`attach_shot_placement()`），同時多出一個選填欄位；路徑、授權判斷、既有錯誤代碼完全不變：

- `POST /courts/by-token/{token}/matches/{match_id}/shot-placement`（計分板／單一場地控制板 token）
- `POST /groups/{group_id}/courts/{court_id}/matches/{match_id}/shot-placement`（admin）
- `POST /groups/by-all-courts-token/{token}/courts/{court_id}/matches/{match_id}/shot-placement`（全部場地控制板 token）

「按 + 立即加分、再補記細節」的既有流程（032）不變：加分本身不等待這個請求。

## Request

```jsonc
{
  "score_event_id": "<uuid>",          // 既有：釘住要補記的那一分
  "roster_entry_id": "<uuid> | null",  // 既有，選填
  "losing_roster_entry_id": "<uuid> | null", // 既有，選填
  "landing_x": 1.04,                   // 既有，選填（與 landing_y 同有同無）
  "landing_y": 0.5,
  "ending_type": "out"                 // 新增，選填
}
```

`ending_type`：`"winner" | "out" | "net" | "serve_fault" | "other_error" | null`。省略或 `null`＝未記錄。可在其餘四個欄位皆為 `null` 的情況下單獨提供（FR-010）。

## Response

不變（`ShotPlacementAttachResponse`）。

## 錯誤（新增）

| 錯誤代碼 | 情境 | HTTP |
|---|---|---|
| （Pydantic 422） | `ending_type` 不在值域內 | 422 |
| `ENDING_TYPE_CONTRADICTS_LANDING` | 同時提供了落點，且 `winner` 配界外落點、或 `out` 配界內落點 | 422 |
| `ENDING_TYPE_CONTRADICTS_SERVE` | `serve_fault`，但被記分的一方正是這一分的發球方（發球失誤一定是接發方得分）。比賽第一分無從得知發球方，不檢查 | 422 |

界內／界外沿用該函式既有的判定（單打用較窄的邊線）。`net`／`serve_fault`／`other_error` 與落點沒有必然關係，不檢查；沒有落點時一律不檢查。

既有錯誤（`DETAILED_SCORING_NOT_ENABLED`、`SCORE_EVENT_NOT_FOUND`、`SCORE_EVENT_NOT_A_POINT`、`SHOT_PLACEMENT_ALREADY_RECORDED`、`PARTICIPANT_NOT_IN_MATCH`、`SCORING_PLAYER_NOT_ON_CREDITED_SIDE`、`SCORING_AND_LOSING_PLAYER_SAME_TEAM`、`SCORING_PLAYER_WRONG_TEAM_FOR_LANDING`、`INVALID_LANDING_COORDINATES`）與其判定順序不變；新檢查排在既有的落點檢查之後。

## 保證（契約測試斷言）

- 不帶 `ending_type` 的既有請求，行為與回應與上線前完全相同。
- 只帶 `score_event_id` 與 `ending_type` 的請求成功，並可在比賽詳情中讀回。
- 簡易計分模式的比賽仍回 `DETAILED_SCORING_NOT_ENABLED`（FR-004）。
- 對該隊執行 `-1` 後，該分的紀錄（含 `ending_type`）不再出現在比賽詳情中（FR-012）。
- 同一分第二次補記仍回 `SHOT_PLACEMENT_ALREADY_RECORDED`——確認後不可編輯。
- `match.scoreUpdated` 事件負載不新增欄位。
