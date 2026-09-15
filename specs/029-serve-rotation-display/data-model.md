# Data Model: 計分板發球站位顯示

本功能**不新增、不修改任何資料表欄位**——所有底層資料（`serving_team`、
`team_a_reference_server_id`、`team_b_reference_server_id`）皆由
`030-score-serve-record` 的 migration 提供。這裡定義的是「回應形狀」
層級的新增結構（Pydantic schema／TypeScript interface），純粹是既有
即時狀態的呈現層延伸。

## 新增回應結構

### `ServeStationInfo`（後端 `apps/api/app/domains/schedule/schemas.py` 新增；前端 `court-live-state.models.ts` 對應同名 interface）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `server_roster_entry_id` | `str` | 目前發球者。直接複用 `030-score-serve-record` data-model.md 的站位公式即時算出，語意與 `ScoreServeRecord.server_roster_entry_id` 完全一致（只是這裡是「即時」而非「該次加分當下的快照」）。 |
| `server_team` | `'A' \| 'B'` | 目前發球隊伍（`match.serving_team` 原樣）。 |
| `team_a_right_roster_entry_id` | `str \| None` | A 隊「右側站位」球員；單打且該球員這一刻站左側時為 `None`。 |
| `team_a_left_roster_entry_id` | `str \| None` | A 隊「左側站位」球員，語意同上。 |
| `team_b_right_roster_entry_id` | `str \| None` | B 隊「右側站位」球員，語意同上。 |
| `team_b_left_roster_entry_id` | `str \| None` | B 隊「左側站位」球員，語意同上。 |

四個站位欄位的計算規則（單打時恰有一個非 `None`，雙打時四個皆非
`None`）與驗證規則，完整定義於
`/specs/030-score-serve-record/data-model.md`「站位計算公式」一節，
本功能直接呼叫同一份共用函式，不重新定義。

## 既有回應結構（新增巢狀欄位，其餘不變）

### `MatchLiveDetail`（既有，`schedule/schemas.py`／`court-live-state.models.ts`）

新增一個欄位：

| 欄位 | 型別 | 說明 |
|---|---|---|
| `serve` | `ServeStationInfo \| None` | `None` 表示這場比賽尚未有發球狀態可顯示（research.md Decision 4：`match.serving_team IS NULL`，例如 030 尚未部署前建立的舊比賽）。有進行中比賽、且該比賽已有發球狀態時恆為非 `None`（FR-001 保證比賽一轉為 `in_progress` 就會初始化）。 |

既有欄位（`match_id`、`status`、`score_a`、`score_b`、`participants`）
完全不變。

### `match.scoreUpdated`（既有 Ably 事件負載，`apply_score_delta()` 發布）

新增一個欄位，其餘不變：

| 欄位 | 型別 | 說明 |
|---|---|---|
| `serve` | `ServeStationInfo \| None` | 與 `MatchLiveDetail.serve` 同一份計算結果，這次加分完成當下的最新值。 |

既有欄位（`match_id`、`score_a`、`score_b`）完全不變。前端既有的
合併邏輯（把事件負載淺層合併進本地 `current_match` 狀態）比照既有
`score_a`/`score_b` 的合併方式，一併合併 `serve` 欄位。

## 不受影響的既有回應結構

- `CourtScheduleStatus.current_match`（`MatchSummary`，管理頁排程列表用）
  與 `RoundMatchSummary`（本輪賽程清單）**不**新增 `serve` 欄位——這兩處
  是回顧/管理用途的清單呈現，不是即時計分板畫面，spec Assumptions
  明確排除本次範圍。
- `NextUpPreview`——「即將登場」的下一場比賽尚未開始，沒有發球狀態
  可言，不新增 `serve` 欄位。
