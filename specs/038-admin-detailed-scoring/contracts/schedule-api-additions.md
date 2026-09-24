# Contract: 排程快照新增 `detailed_scoring_enabled`

**Feature**: 038-admin-detailed-scoring | **Date**: 2026-09-20

本功能對外契約的改動只有一項：`MatchSummary` 多一個布林欄位。其餘所需端點全部已存在，本文一併列出以供實作與測試對照。

## 1. 唯一的契約變更：`MatchSummary.detailed_scoring_enabled`

### 影響範圍

`MatchSummary` 是 `ScheduleResponse.courts[].current_match` 的型別，因此**所有回傳 `ScheduleResponse` 的端點**都會帶上這個新欄位：

| 端點 | 方法 |
|---|---|
| `/groups/{group_id}/schedule` | GET |
| `/groups/{group_id}/next-round` | POST |
| `/groups/{group_id}/schedule/end-round` | POST |
| `/groups/{group_id}/schedule/plan` | POST |
| `/groups/{group_id}/schedule/start` | POST |

全部走既有的 `require_admin`（組團編號 + 管理 PIN session），權限模型不變。

### 回應片段

```jsonc
{
  "courts": [
    {
      "court_id": "…",
      "name": "A 場",
      "current_match": {
        "match_id": "…",
        "status": "in_progress",
        "participants": [ /* … */ ],
        "score_a": 9,
        "score_b": 5,
        "serve": { /* … */ },
        "detailed_scoring_enabled": true   // ← 新增
      },
      "waiting_reason": null,
      "next_up": null
    }
  ],
  "roster": [ /* … */ ]
}
```

### 語意

- 值來自 **`matches.detailed_scoring_enabled`**——這場比賽建立當下對團設定所做的快照，**不是** `groups.detailed_scoring_enabled` 的即時值（憲章原則 III）。
- 管理員在比賽進行中切換團的開關，這個欄位 MUST NOT 跟著改變；下一場新建立的比賽才會反映新設定。
- 預設 `false`：舊版前端或缺欄位的情況一律視為「簡易模式」，退回一鍵加分。

### 非變更

- 不新增端點、不移除欄位、不改變任何既有欄位的型別或語意。
- 純新增可選欄位，對既有前端**向後相容**。

## 2. 既有端點（本功能只是開始呼叫，契約不變）

以下三個管理員端點都已實作且有契約測試，本功能不修改它們。

### 2.1 加分 — `POST /groups/{group_id}/courts/{court_id}/matches/{match_id}/score`

```jsonc
// Request
{ "side": "A", "delta": 1 }

// Response: ScoreMutationResult
{
  "applied": true,
  "match_id": "…",
  "status": "in_progress",
  "score_a": 10,
  "score_b": 5,
  "winner_team": null,
  "score_event_id": "…",   // 詳細模式接續 shot-placement 用；未 applied 時為 null
  "serve": { /* … */ }
}
```

`score_event_id` 後端**早已回傳**；本功能只需要在前端 `schedule.models.ts` 的 `ScoreMutationResult` 補上對應欄位宣告。

錯誤：`ADMIN_TOKEN_INVALID`、`MATCH_NOT_FOUND`。

### 2.2 記錄落點詳細資料 — `POST /groups/{group_id}/courts/{court_id}/matches/{match_id}/shot-placement`

```jsonc
// Request
{
  "score_event_id": "…",
  "roster_entry_id": "…",          // 可為 null
  "losing_roster_entry_id": "…",   // 可為 null
  "landing_x": 0.62,               // 可為 null
  "landing_y": 0.18,               // 可為 null
  "ending_type": "smash"           // 可為 null
}

// Response
{ "recorded": true }
```

錯誤（既有，語系檔已有對應文案的部分見 research.md Decision 4）：
`ADMIN_TOKEN_INVALID`、`MATCH_NOT_FOUND`、`DETAILED_SCORING_NOT_ENABLED`、
`INVALID_LANDING_COORDINATES`、`SCORE_EVENT_NOT_FOUND`、`SCORE_EVENT_NOT_A_POINT`、
`SHOT_PLACEMENT_ALREADY_RECORDED`、`PARTICIPANT_NOT_IN_MATCH`、
`SCORING_PLAYER_NOT_ON_CREDITED_SIDE`、`SCORING_AND_LOSING_PLAYER_SAME_TEAM`、
`SCORING_PLAYER_WRONG_TEAM_FOR_LANDING`、`ENDING_TYPE_CONTRADICTS_LANDING`、
`ENDING_TYPE_CONTRADICTS_SERVE`。

### 2.3 撤銷賽末點 — `POST /groups/{group_id}/courts/{court_id}/matches/{match_id}/undo-completion`

```jsonc
// Request
{ "side": "A" }

// Response: ScoreMutationResult（同 2.1 形狀）
```

錯誤：`ADMIN_TOKEN_INVALID`、`MATCH_NOT_FOUND`、`MATCH_NOT_COMPLETED`、
`SIDE_DID_NOT_WIN_THIS_MATCH`、`ROUND_ALREADY_ADVANCED`、`NEXT_MATCH_ALREADY_STARTED`。

後四者即 FR-009 要顯示的「賽程已往前推進」情況，`zh-TW.json` 與 `en.json` 均已有對應文案。

## 3. 前端服務層需補的方法（`ScheduleService`）

既有：`scoreMatch()`、`endMatch()`。需補兩個，簽章比照 `CourtControlService` 的同名方法，差別只在改用 `this.authHeader(groupId)`：

```ts
recordShotPlacement(
  groupId: string, courtId: string, matchId: string,
  scoreEventId: string,
  rosterEntryId: string | null,
  losingRosterEntryId: string | null,
  landingX: number | null,
  landingY: number | null,
  endingType: EndingType | null,
): Observable<ShotPlacementAttachResponse>

undoMatchCompletion(
  groupId: string, courtId: string, matchId: string, side: Team,
): Observable<ScoreMutationResult>
```

## 4. 契約測試要求

- **新增**（建議放在 `apps/api/tests/contract/test_detailed_scoring_toggle.py`，該檔已有 `_create_group_with_active_match()` 可直接沿用；repo 中沒有專屬的 schedule 契約測試檔）：`GET /groups/{group_id}/schedule` 回應中 `current_match.detailed_scoring_enabled` 反映比賽快照——團開啟時建立的比賽回 `true`，團關閉時建立的回 `false`。
- **新增**：比賽開打後把團的開關切到相反值，同一場比賽的 `detailed_scoring_enabled` MUST 維持原值（憲章原則 III 的快照保證）。
- **不需新增**：2.1 / 2.2 / 2.3 三個端點的契約測試已存在於
  `apps/api/tests/contract/test_admin_score_endpoints.py`、
  `test_shot_placement_endpoint.py`、`test_undo_match_completion_endpoint.py`。
