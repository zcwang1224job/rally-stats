# Phase 1 Data Model: 對戰紀錄衍生統計

本功能**不新增、不修改任何 SQLAlchemy model、資料表欄位或 migration**。以下記錄：(1) 唯讀依賴的既有實體；(2) 純函式模組的輸入／中間模型；(3) 新增的 API 回應 schema 與對應的前端 interface。

## 既有實體（唯讀依賴，不修改）

| 實體 | 用途 |
|---|---|
| `ScoreEvent`（`schedule/models.py`，007） | 每一次 +1／-1。讀 `id`／`side`／`delta`／`score_a`／`score_b`／`created_at`，依 `created_at, id` 排序（016 既有排序）。 |
| `ScoreServeRecord`（`schedule/models.py`，030） | 每個 +1 事件 0 或 1 筆，**得分之後**的發球狀態快照（research.md Decision 3）。讀 `score_event_id`／`server_team`／`server_roster_entry_id`／四個站位欄位。**本功能是第一個讀取此表的查看畫面。** |
| `ShotPlacementRecord`（`schedule/models.py`，031/032） | 讀 `score_event_id`／`roster_entry_id`／`losing_roster_entry_id`／`landing_x`／`landing_y`。032 已查詢過同一批資料，本功能直接重用該次查詢結果，不重複查詢。 |
| `Match` | 讀 `started_at`（第一分耗時起點）、`score_a`／`score_b`（有效得分數的防呆比對）。 |
| `MatchParticipant`／`RosterEntry` | 經既有 `_build_match_record_summaries()` 取得的 `team_a`／`team_b`（`roster_entry_id`／`nickname`／`team`），作為球員清單與暱稱來源。 |

## 純函式模組的輸入與中間模型（`group/match_stats.py`，皆為 `@dataclass(frozen=True)`）

不 import 任何 ORM model——`build_match_record_detail()` 負責把 ORM 物件轉成這些輸入。

| 型別 | 欄位 | 說明 |
|---|---|---|
| `RawEvent` | `event_id: UUID`、`side: "A"\|"B"`、`delta: 1\|-1`、`score_a: int`、`score_b: int`、`at_seconds: float` | 一筆原始事件；`at_seconds` 為距 `Match.started_at` 的浮點秒數（不截斷）。 |
| `ServeSnapshot` | `server_team`、`server_id: UUID`、`team_a_right`／`team_a_left`／`team_b_right`／`team_b_left: UUID \| None` | 一筆發球快照，以 `event_id` 為鍵傳入（`dict[UUID, ServeSnapshot]`）。 |
| `Placement` | `scorer_id`／`loser_id: UUID \| None`、`landing: tuple[float, float] \| None` | 一筆落點紀錄，以 `event_id` 為鍵傳入。 |
| `Participant` | `roster_entry_id: UUID`、`team` | 參賽者（暱稱不進純函式，由呼叫端在組回應時補上）。 |
| `EffectivePoint`（中間） | `event_id`、`side`、`score_a`／`score_b`（**重新累計**後、這一分結束時的比分）、`recorded_score_a`／`recorded_score_b`（事件上原本記錄的比分）、`at_seconds`、`gap_is_clean: bool` | `gap_is_clean`＝原始序列中緊鄰的前一筆事件也是有效得分，或本筆為全場第一筆事件（research.md Decision 5）。 |

**核心函式**：

- `effective_points(events, final_score_a, final_score_b) -> list[EffectivePoint] | None`——逐隊堆疊撤銷（Decision 2）；有效得分數與最終比分不符 → `None`（四類統計全部無資料）。
- `serve_stats(points, snapshots, participants) -> ServeStatsResult | None`（Decision 3/4）
- `momentum_stats(points) -> MomentumResult`（Decision 6）
- `tempo_stats(points) -> TempoResult | None`（Decision 5）
- `landing_distribution(points, placements, participants) -> list[PlayerLandingResult]`（Decision 7）

## 新增 Schema（`apps/api/app/domains/group/schemas.py`）

### 發球／接發球

`ServeCounts`（共用欄位，供下列兩者繼承）：

| 欄位 | 型別 | 說明 |
|---|---|---|
| `serve_points_won` | `int` | 擔任發球方（者）時拿下的分數。 |
| `serve_points_total` | `int` | 擔任發球方（者）的總分數。 |
| `receive_points_won` | `int` | 擔任接發球方（者）時拿下的分數。 |
| `receive_points_total` | `int` | 擔任接發球方（者）的總分數。 |

百分比**不**由後端回傳——前端以 `won / total` 計算並在 `total == 0` 時顯示「—」（FR-014），避免後端為除以零另立表示法。

- `TeamServeStat(ServeCounts)`：加上 `team: "A" | "B"`。
- `PlayerServeStat(ServeCounts)`：加上 `roster_entry_id: str`、`nickname: str`、`team`。

`ServeStats`：

| 欄位 | 型別 | 說明 |
|---|---|---|
| `teams` | `list[TeamServeStat]` | 恆為兩筆，A 在前、B 在後。 |
| `players` | `list[PlayerServeStat]` | 雙打：全部四位參賽者（`team_a` 順序在前、`team_b` 在後，含全為 0 者，FR-014）。**單打：`[]`**（FR-013，球員層級與隊伍層級內容相同，不重複）。 |
| `excluded_points` | `int` | 無法判定發球方而未列入的有效得分數，恆 ≥ 1（第一分）。不變量：`teams[0].serve_points_total + teams[1].serve_points_total + excluded_points == score_a + score_b`。 |

### 比分走勢

| Schema | 欄位 |
|---|---|
| `ScoringRun` | `team`、`length: int`、`start_score_a`／`start_score_b`／`end_score_a`／`end_score_b: int \| None`（`length == 0` 時四者皆 `None`；`start_*` 為該段開始**前**的比分，`end_*` 為結束**後**的比分） |
| `MaxLead` | `team`、`margin: int`、`score_a`／`score_b: int \| None`（`margin == 0` 時為 `None`；否則為**首次**達到該分差時的比分） |
| `LeadChange` | `new_leader: "A" \| "B"`、`score_a: int`、`score_b: int`（易手當下的比分） |
| `MomentumStats` | `longest_runs: list[ScoringRun]`（兩筆，A、B）、`max_leads: list[MaxLead]`（兩筆，A、B）、`lead_changes: list[LeadChange]`（依發生順序，可為空） |

### 每分耗時

| Schema | 欄位 |
|---|---|
| `LongestPoint` | `seconds: float`、`score_a: int`、`score_b: int`（該分結束後的比分） |
| `TempoStats` | `average_seconds: float`（四捨五入至小數一位）、`counted_points: int`（列入計算的分數，≥ 1）、`longest: LongestPoint` |

### 落點分布

| Schema | 欄位 |
|---|---|
| `LandingPoint` | `x: float`、`y: float`（座標系同 031 data-model Decision 1：`x` 0＝A 隊底線、1＝B 隊底線；範圍 `[-0.3, 1.3]`，界外值原樣回傳，FR-025） |
| `PlayerLandingDistribution` | `roster_entry_id`、`nickname`、`team`、`scored: list[LandingPoint]`、`scored_total: int`、`lost: list[LandingPoint]`、`lost_total: int` |

`scored_total`＝該球員被記為得分球員的有效得分數（不論有無落點），必與 032 `player_stats[].scored_count` 相等；`lost_total` 同理對應 `fault_count`（FR-026 的分母）。

### `MatchRecordDetailResponse`（既有 schema 擴充，四個欄位皆有預設值）

| 欄位 | 型別 | 無資料條件（→ 前端顯示提示） |
|---|---|---|
| `serve_stats` | `ServeStats \| None = None` | 紀錄不完整；有效得分與最終比分不符；該場沒有任何發球快照；或所有分數皆被排除。 |
| `momentum_stats` | `MomentumStats \| None = None` | 紀錄不完整；有效得分與最終比分不符。 |
| `tempo_stats` | `TempoStats \| None = None` | 同上；或沒有任何一分可列入計算。 |
| `landing_distribution` | `list[PlayerLandingDistribution] = []` | 同上；或全場沒有任何含座標的落點紀錄。非空時恆列出**全部**參賽者。 |

「紀錄不完整」＝既有 `record_completeness != "complete"`（FR-004）。既有欄位完全不變；`MatchRecordSummary` 與所有清單端點零變動。

## 前端對應 interface（`apps/web/src/app/core/api/group-member-view.models.ts`）

欄位名稱與後端 JSON 一對一（沿用該檔案實際採用的 snake_case）：`ServeCounts`／`TeamServeStat`／`PlayerServeStat`／`ServeStats`／`ScoringRun`／`MaxLead`／`LeadChange`／`MomentumStats`／`LongestPoint`／`TempoStats`／`LandingPoint`／`PlayerLandingDistribution`，並於 `MatchRecordDetailResponse` 新增 `serve_stats: ServeStats | null`、`momentum_stats: MomentumStats | null`、`tempo_stats: TempoStats | null`、`landing_distribution: PlayerLandingDistribution[]`。

`CourtDiagramComponent` 新增輸入型別：

```typescript
export interface CourtMarker {
  x: number;
  y: number;
  kind: 'scored' | 'lost';
}
```

## 關聯圖

```text
Match 1───* ScoreEvent 1───0/1 ScoreServeRecord      ← 本功能首度讀取
                       └───0/1 ShotPlacementRecord   ← 032 已讀取，本功能重用同一次查詢

ScoreEvent[] ──effective_points()──▶ EffectivePoint[]   （撤銷後、比分重新累計）
                                          │
        ┌─────────────────┬───────────────┼──────────────────┐
        ▼                 ▼               ▼                  ▼
   serve_stats()    momentum_stats()  tempo_stats()   landing_distribution()
  (+ServeSnapshot)                                      (+Placement)
        │                 │               │                  │
        └─────────────────┴───────┬───────┴──────────────────┘
                                  ▼
                    MatchRecordDetailResponse（新增四個欄位）
```
