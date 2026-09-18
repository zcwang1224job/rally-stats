# Phase 1 Data Model: 得分方式紀錄

本功能新增**一個資料表欄位**（一支 migration），其餘皆為由既有紀錄於查看當下推導的呈現模型。

## 儲存：`shot_placement_records.ending_type`（新增）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `ending_type` | `String(16)`, **nullable** | 這一分怎麼結束。NULL＝未記錄（含所有上線前的既有列）。 |

**值域**（應用層驗證，無 DB enum／CHECK——research.md Decision 1）：

| 值 | 畫面用語 | 大類 | 功過歸屬 |
|---|---|---|---|
| `winner` | 主動得分 | 主動得分 | 得分球員（`roster_entry_id`） |
| `out` | 對手出界 | 失誤 | 失分球員（`losing_roster_entry_id`） |
| `net` | 對手掛網 | 失誤 | 失分球員 |
| `serve_fault` | 發球失誤 | 失誤 | 失分球員 |
| `other_error` | 其他失誤 | 失誤 | 失分球員 |

**驗證規則**（`attach_shot_placement()`）：

- 值 MUST 為上表五者之一或 NULL → 否則 `INVALID_ENDING_TYPE`（422；Pydantic `Literal` 已先擋，service 為直接呼叫時的防線）。
- 同時提供落點時：`winner` ∧ 落點界外 → `ENDING_TYPE_CONTRADICTS_LANDING`；`out` ∧ 落點界內 → 同。界內／界外沿用該函式既有判定（單打用較窄邊線）。
- 與 `roster_entry_id`／`losing_roster_entry_id`／落點**互相獨立**：可單獨存在（FR-010）。

**界內／界外的邊界測試向量**（analyze I1）：界內／界外由前端（選擇畫面）與後端（`attach_shot_placement()`）**各自判定一次**，兩者 MUST 一致——任何一點判定不同，補記請求就會被拒，而三個掛載點呼叫補記 API 時沒有錯誤處理（既有行為），整筆細節（落點＋球員＋得分方式）會無聲消失。後端 `test_shot_placement.py` 與前端 `shot-placement-picker.component.spec.ts` MUST 逐字採用同一張表，並互相註明出處：

| 賽制 | (x, y) | 判定 |
|---|---|---|
| 雙打 | (0.0, 0.5)、(1.0, 0.5)、(0.5, 0.0)、(0.5, 1.0) | 界內（線上算界內） |
| 雙打 | (-0.0001, 0.5)、(1.0001, 0.5)、(0.5, -0.0001)、(0.5, 1.0001) | 界外 |
| 單打 | (0.5, INSET)、(0.5, 1 − INSET) | 界內 |
| 單打 | (0.5, INSET − 0.0001)、(0.5, 1 − INSET + 0.0001) | 界外 |
| 單打 | (0.5, 0.03)——雙打邊線內、單打邊線外 | 界外 |

`INSET = 0.46 / 6.1`（兩邊既有的常數：後端 `_SINGLES_SIDELINE_INSET`、前端 `SINGLES_SIDELINE_INSET`）。

**生命週期**：與所在列完全相同——確認時隨列寫入一次；不可 UPDATE；`-1` 修正時隨列刪除（既有 `_remove_last_shot_placement_record()`，不需修改）。

**Migration**：`down_revision = 'd0c14187b0e3'`；`upgrade` 只有一個 `op.add_column`，`downgrade` 只有一個 `op.drop_column`。不回填。

## 純函式模型 (1)：`group/match_stats.py`

| 型別 | 變更 |
|---|---|
| `EndingType` | 新增 `Literal["winner","out","net","serve_fault","other_error"]`；`ERROR_TYPES` 常數＝後四者。 |
| `Placement` | 新增欄位 `ending: EndingType \| None = None`（有預設值，既有建構呼叫不受影響）。 |
| `TeamEndingResult`（新） | `team`、`winners: int`、`errors: int`、`errors_by_type: dict[EndingType, int]`。`errors`＝**本隊犯下**的失誤。 |
| `PlayerEndingResult`（新） | `roster_entry_id`、`team`、`winners`、`opponent_errors`、`scored_unrecorded`、`beaten_by_winners`、`own_errors`、`lost_unrecorded`、`own_errors_by_type`。 |
| `EndingStatsResult`（新） | `recorded_points`、`total_points`、`teams: dict[Team, TeamEndingResult]`、`players: dict[UUID, PlayerEndingResult]`（依 `participants` 順序）。 |

**函式**：`ending_stats(points, placements, participants) -> EndingStatsResult | None`——沒有任何一分記錄得分方式時回傳 `None`。

**不變式**（單元測試）：

- 每位球員 `winners + opponent_errors + scored_unrecorded == player_landings()[id].scored_total`；失分端同理對 `lost_total`。
- `teams[A].winners + teams[B].errors` ＝ A 隊「已記錄得分方式」的得分數；`recorded_points` ＝ 兩隊該值之和。
- `sum(errors_by_type.values()) == errors`。
- 被 `-1` 撤銷的那一分不計入任何數字（走訪的是 `effective_points()` 的結果）。

## 純函式模型 (2)：`member/player_dashboard.py`

| 型別 | 變更 |
|---|---|
| `EndingSample`（新） | `winners`、`opponent_errors`、`beaten_by_winners`、`own_errors`、`own_errors_by_type: dict[str, int]`。 |
| `MatchSample` | 新增 `ending: EndingSample \| None`——只在該會員該場**至少一分**（得或失）記錄了得分方式時有值（FR-020）。 |
| `ErrorBreakdown`（新） | `out`／`net`／`serve_fault`／`other_error` 四個次數。 |
| `DashboardResult` | 新增 `error_breakdown_all: ErrorBreakdown \| None`、`error_breakdown_recent: ErrorBreakdown \| None`。 |
| `_METRICS` | 新增 5 筆（見下），總數 18 → 23；`aggregate()` 本體不變。 |

**新增指標**（接在既有 18 項之後，順序固定）：

| key | kind | better_when | 分子 ÷ 分母 | 納入條件 | FR |
|---|---|---|---|---|---|
| `winner_share` | rate | higher | Σ主動得分 ÷ Σ(主動得分＋對手失誤得分) | `ending` 有值 | 018a |
| `winners_per_match` | average | higher | Σ主動得分 ÷ 場數 | 同上 | 018b |
| `errors_per_match` | average | lower | Σ自己失誤 ÷ 場數 | 同上 | 018c |
| `error_share_of_lost` | rate | lower | Σ自己失誤 ÷ Σ(自己失誤＋被主動得分) | 同上 | 018d |
| `winner_error_ratio` | ratio | higher | Σ主動得分 ÷ Σ自己失誤 | 同上 | 018e |

比例類的分母**只含已記錄得分方式的分數**（不含 `*_unrecorded`）。

## 回應 Schema（後端）

### `schedule/schemas.py`——寫入

```python
EndingType = Literal["winner", "out", "net", "serve_fault", "other_error"]

class RecordShotPlacementRequest(BaseModel):
    ...                                   # 既有欄位不變
    ending_type: EndingType | None = None  # 新增；省略＝未記錄
```

### `group/schemas.py`——單場詳情

```python
class ShotPlacementSummary(BaseModel):
    ...                                   # 既有欄位不變
    ending_type: EndingType | None = None  # 新增

class ErrorsByType(BaseModel):
    out: int
    net: int
    serve_fault: int
    other_error: int

class TeamEndingStat(BaseModel):
    team: Literal["A", "B"]
    winners: int
    errors: int                  # 本隊犯下的失誤
    errors_by_type: ErrorsByType

class PlayerEndingStat(BaseModel):
    roster_entry_id: str
    nickname: str
    team: Literal["A", "B"]
    winners: int
    opponent_errors: int
    scored_unrecorded: int
    beaten_by_winners: int
    own_errors: int
    lost_unrecorded: int

class EndingStats(BaseModel):
    recorded_points: int
    total_points: int
    teams: list[TeamEndingStat]      # 恆為 [A, B]
    players: list[PlayerEndingStat]  # 全部參賽者，順序 team_a + team_b
```

`MatchRecordDetailResponse` 新增 `ending_stats: EndingStats | None = None`（`None`＝沒有任何得分方式紀錄、或逐分紀錄不完整——與 033／034 的欄位同一條件）。既有 `player_stats`（032）**不變**。

### `member/schemas.py`——儀表板

```python
class DashboardErrorBreakdown(BaseModel):
    all: ErrorsByType
    recent: ErrorsByType | None   # None：總場數 ≤ 10，沒有對比

class MemberMatchDashboardResponse(BaseModel):
    ...                                            # 既有欄位不變
    metrics: list[DashboardMetric]                 # 0 或 23 項
    error_breakdown: DashboardErrorBreakdown | None = None  # None：沒有任何失誤紀錄
```

## 前端 interface

- `core/api/court-live-state.models.ts`（或選擇器所在檔）：`EndingType` 聯集；`ShotPlacementConfirmed.endingType`。
- `core/api/group-member-view.models.ts`：`ShotPlacementSummary.ending_type`、`EndingStats` 及子型別、`MatchRecordDetailResponse.ending_stats`。
- `core/api/player-dashboard.models.ts`：`DASHBOARD_METRIC_KEYS` 加 5 個 key；`DashboardErrorBreakdown`；`MemberMatchDashboardResponse.error_breakdown`。
- `core/player-dashboard/player-dashboard.component.ts`：`MetricGroup` 加 `'ending'`，`GROUP_OF` 補 5 筆（exhaustive `Record`，漏掉即編譯失敗）。

## 語系 key

- `shotPlacement.ending.*`：區塊標題、五個選項、自動帶入的提示、被停用選項的說明。
- `matchRecordDetail.ending.*`：區塊標題、隊伍摘要、球員拆分表的欄位、涵蓋範圍、無資料提示；逐點清單的五個標籤。
- `playerDashboard.group.ending`、`playerDashboard.metric.<5 個 key>.{label,hint,empty}`、`playerDashboard.errorBreakdown.*`。
