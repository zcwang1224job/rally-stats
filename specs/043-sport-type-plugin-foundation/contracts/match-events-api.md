# Contract: 比賽事件脊椎、控制動作與即時訊息

**Feature**: 043-sport-type-plugin-foundation | **Date**: 2026-09-24

所有控制動作在三個授權面各有一份路徑（既有慣例），授權沿用既有依賴，不新增管理員專屬操作到免驗證畫面（憲章 IV）：

| 授權面 | 路徑前綴 | 授權 |
|---|---|---|
| 場地連結 | `/courts/by-token/{token}/matches/{match_id}` | `get_court_by_token` + `_can_score_by_token` |
| 管理頁 | `/groups/{group_id}/courts/{court_id}/matches/{match_id}` | `require_admin` + `_admin_court` |
| 全部場地 | `/groups/by-all-courts-token/{token}/courts/{court_id}/matches/{match_id}` | all-courts token + `_all_courts_court` |

## 1. `POST …/score`（既有，放寬）

Body：`{ "side": "A"|"B", "delta": int }`。

- `delta ≠ 0` 且 `abs(delta) ∈ match.score_steps`，否則 `422 SCORE_STEP_NOT_ALLOWED`。羽球 `score_steps=[1]` ⇒ 只接受 ±1，與今日相同。
- `end_mode='manual'` 的比賽同樣接受（累計比分），只是不做達標判定。
- 負 `delta` 只允許隔網回合制（既有 −1 語意）；局數制與通用類型的 `delta` 必須為正（`422 SCORE_STEP_NOT_ALLOWED`），復原一律走 `/undo`。
- 回應 `ScoreMutationResult` 新增 `sport_state`（外掛即時狀態，隔網回合制為 `null`）；既有 `serve` 欄位不變。

## 2. `POST …/events`（新增）

Body：`{ "kind": "frames.frame_point", "payload": { "side": "A", "delta": 1 } }`

- `kind` 必須在該比賽類型外掛的 `event_schemas()` 內，否則 `422 EVENT_KIND_NOT_ALLOWED`；`payload` 依該 schema 驗證。
- 比賽須 `in_progress`（`409 MATCH_NOT_IN_PROGRESS`）。
- 核心寫一筆脊椎事件（`kind`、`side` 由 payload 決定或 NULL、`delta=0`、`score_a/b` 現值、`source`），呼叫外掛 `apply_event()`；外掛可回傳 `follow_up_point: {side, delta}` 讓核心在同一交易追加一筆 `point`（局內達標自動結束該局），並回傳 `live_payload`。
- 回應：

```jsonc
{ "applied": true, "score_a": 2, "score_b": 1, "status": "in_progress", "winner_team": null,
  "score_event_id": "…", "follow_up_score_event_id": "…"|null, "sport_state": { "frame_no": 4, "frame_score_a": 0, "frame_score_b": 0, … } }
```

- 若 `follow_up_point` 造成達標（局數制贏到 `target_score` 局），核心走既有終局流程（`completed`、`_advance_after_terminal`、`match.ended`、`standings.updated`）。

本期宣告的 kind：

| type_key | kind | payload |
|---|---|---|
| `frames` | `frames.frame_point` | `{side, delta: 1\|-1}`（需 `frame_scoring_enabled`） |
| `frames` | `frames.frame_end` | `{winner_team: "A"\|"B"}` |
| `net_rally`、`generic` | （無） | 隔網回合制的發球與落點沿用既有專用端點 |

## 3. `POST …/finish`（新增：手動結束並記錄結果）

Body：`{}`。

- `end_mode ≠ 'manual'` → `409 FINISH_NOT_AVAILABLE`。
- 比賽須 `in_progress`。
- `score_a > score_b` ⇒ `winner_team='A'`；反之 `'B'`；同分且 `allow_draw` ⇒ `'D'`；同分且不允許 ⇒ `409 DRAW_NOT_ALLOWED`。
- 走既有終局流程；`match.ended` 的 `winner_team` 可為 `"D"`；`standings.updated` 照發。
- 回應與 `/score` 相同形狀（`applied: true, status: "completed", winner_team: …`）。

## 4. `POST …/undo`（新增：取消最後一筆事件）

Body：`{}`。

- 比賽須 `in_progress`；沒有事件 → `409 NOTHING_TO_UNDO`。
- 取最後一筆脊椎事件（`(created_at, id)` 降冪）：刪除該列（外掛表 cascade）；若 `kind='point'` 同時 `matches.score_x -= delta`（不得為負，否則 `409 UNDO_CONFLICT`）；然後呼叫外掛 `after_undo()`。
- 回應同 `/score` 形狀，`sport_state` 為復原後狀態。
- 隔網回合制本期不使用此端點：核心在刪除任何列之前先呼叫 `plugin.can_undo()`（順序：查最後一筆 → `can_undo()` → 刪除 → `after_undo()`），`NetRallyPlugin.can_undo()` 回 `False` ⇒ `409 UNDO_NOT_SUPPORTED`，不改動任何資料；既有 −1 語意保留。

## 5. `POST …/end`（既有：放棄比賽）

不變。對所有類型與結束模式可用；`abandoned`、`winner_team=NULL`、不寫事件、不計成績（憲章 III）。

## 6. 既有專用端點的模組門檻

- `POST …/shot-placement`：`type_params.modules.shot_placement` 為 false 的活動 → `409 MODULE_NOT_SUPPORTED`。
- `PUT /groups/{id}/detailed-scoring`（`set_detailed_scoring`）：同上。
- `undo-completion`：不變（隔網回合制）。

## 7. 即時狀態回應

`CourtStateResponse.current_match`（`MatchLiveDetail`）、`AllCourtsLiveState.courts[].current_match`、`ScheduleResponse.courts[].current_match`（`MatchSummary`）一律新增：

```jsonc
"sport": { …SportSummary… },
"end_mode": "target", "win_by": 1, "allow_draw": false, "score_steps": [1],
"cap_score": null,                 // 型別改為 int | null
"sport_state": { "frame_no": 3, "frame_score_a": 7, "frame_score_b": 5, "frames_to_win": 5, "frame_scoring_enabled": true, "frame_target": 11 } | null
```

`CourtStateResponse`／`ScheduleResponse`／`AllCourtsLiveState` 頂層新增 `sport`（團層級，方便宿主在沒有進行中比賽時也能決定要載入哪個類型模組）。

## 8. Ably 訊息

| 事件 | 變更 |
|---|---|
| `match.scoreUpdated` | payload 新增 `sport_state`；既有 `{match_id, score_a, score_b, serve}` 不變（隔網回合制 `serve` 照舊，`sport_state: null`） |
| `match.ended` | `winner_team` 可為 `"D"`；其餘不變 |
| `match.eventApplied`（新增） | `/events` 與 `/undo` 成功後發布：`{match_id, score_a, score_b, sport_state, score_event_id | null}`；隔網回合制永不發此事件 |
| 其他 | 不變 |

發布一律由 `app.domains.schedule.service.publish` 執行（研究 Decision 8）。

## 9. 錯誤碼總表（新增）

`SCORE_STEP_NOT_ALLOWED`、`EVENT_KIND_NOT_ALLOWED`、`FINISH_NOT_AVAILABLE`、`DRAW_NOT_ALLOWED`、`NOTHING_TO_UNDO`、`UNDO_CONFLICT`、`UNDO_NOT_SUPPORTED`、`MODULE_NOT_SUPPORTED`、`SPORT_IMMUTABLE`、`CUSTOM_SPORT_FORBIDDEN`、`CUSTOM_SPORT_NOT_FOUND`、`CUSTOM_SPORT_NAME_TAKEN`、`CUSTOM_SPORT_LIMIT`。前端 `errors.*` 語系檔需對應（zh-TW／en）。
