# Phase 1 Data Model: 關鍵分表現與跨場個人技術儀表板

本功能**不新增、不修改任何 SQLAlchemy model、資料表欄位、索引或 migration**。以下記錄：(1) 唯讀依賴的既有實體；(2) 純函式模組的輸入／中間／輸出模型；(3) 新增的 API 回應 schema 與前端 interface；(4) 指標目錄。

## 既有實體（唯讀依賴，不修改）

| 實體 | 用途 |
|---|---|
| `Match`（`schedule/models.py`） | 讀 `target_score`／`cap_score`（**建立當下的賽制快照**，關鍵分判定依據；`deuce_threshold` 不讀，見 research.md Decision 2）、`score_a`／`score_b`、`started_at`／`ended_at`、`round_number`、`group_id`。只處理 `_completed_matches_query()` 回傳者。 |
| `ScoreEvent`（007） | 每一次 +1／-1，依 `created_at, id` 排序。儀表板以 `match_id IN (...)` 批次讀取（`match_id` 已有索引）。 |
| `ScoreServeRecord`（030） | 得分**之後**的發球快照；歸屬規則完全沿用 033（`serve_stats()`）。批次讀取。 |
| `ShotPlacementRecord`（031/032） | 得分球員／失分球員／落點。批次讀取。座標語意：`landing_x` 0＝A 隊底線、1＝B 隊底線。 |
| `MatchParticipant`／`RosterEntry` | 既有查詢已取得「我在這場比賽的 `team` 與 `roster_entry_id`」（`RosterEntry.member_id == member_id`），儀表板沿用。 |
| `Group` | 既有 `match_mode` 篩選沿用；單／雙打判定由參賽人數得出，不另外讀。 |

## 純函式模型 (1)：`group/match_stats.py` 新增

皆為 `@dataclass(frozen=True)`，不 import ORM。

| 型別 | 欄位 | 說明 |
|---|---|---|
| `PhaseCounts` | `won: int`、`total: int` | 某隊在某階段／某比分狀態下的得分數與該狀態總分數。 |
| `MatchPointResult` | `held: int`、`converted_on: int \| None`、`saved: int` | `held`＝握有賽末點的次數；`converted_on`＝第幾次兌現（1 起算；敗方恆為 `None`）；`saved`＝化解對手賽末點的次數＝對手 `held` −（對手有兌現 ? 1 : 0）。 |
| `StateCounts` | `leading`／`tied`／`trailing: PhaseCounts` | 依**開打前**比分狀態分組。 |
| `ClutchResult` | `endgame_from: int \| None`、`endgame: dict[Team, PhaseCounts] \| None`、`deuce: dict[Team, PhaseCounts] \| None`、`match_points: dict[Team, MatchPointResult]`、`by_state: dict[Team, StateCounts]` | `endgame_from = target - 3`；`target < 11` → `endgame_from` 與 `endgame` 皆 `None`（不適用）。`deuce is None` ⇔ 全場未進入平分延長。 |

**新增／調整的函式**：

- `clutch_stats(points, target_score, cap_score) -> ClutchResult`（research.md Decision 1–3）。
- `_wins(x, y, target, cap) -> bool`（Decision 2，私有；以網格測試鎖定與 `schedule.service.match_wins()` 一致）。
- `player_landings(points, placements, participants) -> dict[UUID, PlayerLandingResult]`——自既有 `landing_distribution()` 抽出的完整結果；`landing_distribution()` 改為其上的薄包裝，**對外行為不變**（Decision 8）。

**不變式**（單元測試）：

- 每隊 `by_state` 三組 `total` 相加 ＝ `len(points)`；A 與 B 的同一狀態互為鏡像（A `leading.total` ＝ B `trailing.total`；`tied.total` 相等）；每組 `A.won + B.won == total`。
- `endgame`／`deuce` 的 `A.total == B.total` 且 `A.won + B.won == total`。
- 勝方 `held ≥ 1` 且 `converted_on == held`；敗方 `converted_on is None`；`A.saved + B.saved + 1 == A.held + B.held`（全場恰有一個賽末點被兌現；封頂前同時為雙方賽末點的那一分，雙方各計一次 `held`，勝方同時計一次 `saved`）。

## 純函式模型 (2)：`member/player_dashboard.py`（新模組）

| 型別 | 欄位 | 說明 |
|---|---|---|
| `Ratio` | `won: int`、`total: int` | 我方（或我本人）視角的一組計數。 |
| `PointLogSample` | `endgame: Ratio \| None`、`deuce: Ratio \| None`、`match_points_held: int`、`match_point_converted: bool`、`match_points_saved: int`、`leading`／`tied`／`trailing: Ratio` | 需完整逐分紀錄。`endgame is None`＝該場賽制不適用；`deuce is None`＝該場未進入延長。 |
| `ServeSample` | `team_serve`／`team_receive: Ratio`、`own_serve`／`own_receive: Ratio \| None` | 需發球紀錄；`own_*` 僅雙打。 |
| `PlayerSample` | `scored: int`、`lost: int`、`scored_landings`／`lost_landings: list[tuple[float, float]]` | 需該場至少一位球員被記錄過得分／失分；座標**已正規化為我方在左**（Decision 10）。 |
| `MatchSample` | `ended_at: datetime`、`won: bool`、`points_for`／`points_against: int`、`point_log: PointLogSample \| None`、`serve: ServeSample \| None`、`player: PlayerSample \| None` | 一場比賽對儀表板的全部貢獻。最終比分類指標恆可算。 |
| `MetricValue` | `value: float \| None`、`numerator: int`、`denominator: int`、`matches_used: int` | 見 research.md Decision 9。 |
| `MetricResult` | `key`、`kind`、`better_when`、`all: MetricValue \| None`、`recent: MetricValue \| None`、`verdict` | |
| `TrendPoint`／`TrendSeries` | `from_ended_at`、`to_ended_at`、`value`、`numerator`、`denominator`／`key`、`points` | Decision 12。 |
| `LandingResult` | 見下方 schema | Decision 11。 |
| `DashboardResult` | `total_matches`、`recent_window`、`has_comparison`、`metrics`、`trends`、`landing` | |

**函式**：

- `normalize_landing(x, y, my_team) -> tuple[float, float]`
- `build_sample(*, ended_at, won, points_for, points_against, my_team, my_entry_id, is_doubles, clutch, serve, landings) -> MatchSample`
- `aggregate(samples_newest_first, *, recent_window=10, min_recent=3, trend_window=5, trend_cap=60) -> DashboardResult`

## 指標目錄（`MetricResult.key`）

| key | kind | better_when | 分子 ÷ 分母 | 納入條件 | FR |
|---|---|---|---|---|---|
| `team_serve` | rate | higher | 我方發球時得分 ÷ 我方發球總分 | `serve` 有值 | 021a |
| `team_receive` | rate | higher | 我方接發球時得分 ÷ 我方接發球總分 | 同上 | 021a |
| `own_serve` | rate | higher | 我親自發球時得分 ÷ 我親自發球總分 | 雙打且 `serve` 有值 | 021b |
| `own_receive` | rate | higher | 我親自接發球時得分 ÷ 總分 | 同上 | 021b |
| `points_scored` | average | higher | 我被記為得分球員的分數 ÷ 場數 | `player` 有值 | 021c |
| `points_lost` | average | lower | 我被記為失分球員的分數 ÷ 場數 | 同上 | 021c |
| `scored_lost_ratio` | ratio | higher | Σ得分 ÷ Σ失分 | 同上 | 021c |
| `endgame` | rate | higher | 局末階段我方得分 ÷ 階段總分 | `point_log.endgame` 有值 | 021d |
| `deuce` | rate | higher | 延長階段我方得分 ÷ 階段總分 | `point_log.deuce` 有值 | 021d |
| `match_point_conversion` | rate | higher | 握有賽末點且獲勝的場數 ÷ 握有賽末點的場數 | `point_log` 有值且 `held ≥ 1` | 021d |
| `match_points_saved` | count | — | Σ化解次數（`denominator`＝場數） | `point_log` 有值 | 021d |
| `when_leading` | rate | higher | 領先時得分 ÷ 領先時總分 | `point_log` 有值 | 021e |
| `when_tied` | rate | higher | 平手時得分 ÷ 平手時總分 | 同上 | 021e |
| `when_trailing` | rate | higher | 落後時得分 ÷ 落後時總分 | 同上 | 021e |
| `avg_points_for` | average | higher | Σ我方得分 ÷ 場數 | 所有比賽 | 021f |
| `avg_points_against` | average | lower | Σ對手得分 ÷ 場數 | 所有比賽 | 021f |
| `avg_win_margin` | average | higher | Σ贏球分差 ÷ 贏球場數 | 贏的比賽 | 021f |
| `avg_loss_margin` | average | lower | Σ輸球分差 ÷ 輸球場數 | 輸的比賽 | 021f |

`matches_used`＝符合納入條件的場數；FR-020 的「共 M 場」＝`total_matches`。

## 新增 Schema（後端）

### `group/schemas.py`——單場關鍵分

```python
class ClutchPhaseTotals(BaseModel):
    won: int
    total: int

class ClutchPhaseCounts(ClutchPhaseTotals):
    team: Literal["A", "B"]

class ClutchMatchPoints(BaseModel):
    team: Literal["A", "B"]
    held: int
    converted_on: int | None
    saved: int

class ClutchStateCounts(BaseModel):
    team: Literal["A", "B"]
    leading: ClutchPhaseTotals      # { won, total }
    tied: ClutchPhaseTotals
    trailing: ClutchPhaseTotals

class ClutchComeback(BaseModel):
    winner: Literal["A", "B"]
    max_deficit: int                # ≥ 1
    score_a: int
    score_b: int

class ClutchStats(BaseModel):
    endgame_from: int | None        # None = 此賽制不適用
    endgame: list[ClutchPhaseCounts] | None   # 恆為 [A, B] 兩筆，或 None
    deuce: list[ClutchPhaseCounts] | None     # None = 未進入平分延長
    match_points: list[ClutchMatchPoints]     # 恆為 [A, B]
    by_state: list[ClutchStateCounts]         # 恆為 [A, B]
    comeback: ClutchComeback | None           # None = 勝方全場未曾落後
```

`MatchRecordDetailResponse` 新增 `clutch_stats: ClutchStats | None = None`（`None`＝逐分紀錄不完整或有效得分與最終比分不符——與 033 四個欄位同一條件）。

### `member/schemas.py`——儀表板

```python
class DashboardMetricValue(BaseModel):
    value: float | None
    numerator: int
    denominator: int
    matches_used: int

class DashboardMetric(BaseModel):
    key: str                                   # 見指標目錄
    kind: Literal["rate", "average", "ratio", "count"]
    better_when: Literal["higher", "lower"] | None
    all: DashboardMetricValue | None           # None = 沒有任何一場具備資料
    recent: DashboardMetricValue | None        # None = 不顯示對比
    verdict: Literal["improved", "declined", "unchanged", "insufficient"] | None

class DashboardTrendPoint(BaseModel):
    from_ended_at: datetime                    # ISO 8601 UTC（Constitution VIII）
    to_ended_at: datetime
    value: float | None
    numerator: int
    denominator: int

class DashboardTrend(BaseModel):
    key: str
    points: list[DashboardTrendPoint]          # 舊到新，2..60 點

class DashboardLanding(BaseModel):
    scored: list[tuple[float, float]]          # 新到舊；我方在左（x < 0.5）
    lost: list[tuple[float, float]]
    scored_total: int                          # 有球員紀錄的得分總數（不論有無落點）
    lost_total: int
    matches_used: int
    recent_scored_count: int                   # scored 的前綴長度＝最近 10 場的落點
    recent_lost_count: int
    recent_scored_total: int
    recent_lost_total: int
    recent_matches_used: int

class MemberMatchDashboardResponse(BaseModel):
    total_matches: int                         # 篩選後的比賽總數（FR-020 的 M）
    recent_window: int                         # 10
    has_comparison: bool                       # total_matches > recent_window
    metrics: list[DashboardMetric]             # 恆為指標目錄全數、固定順序
    trends: list[DashboardTrend]               # 只含場數足夠的指標
    landing: DashboardLanding | None           # None = 沒有任何落點
```

`total_matches == 0` → `metrics = []`、`trends = []`、`landing = None`（前端顯示單一空狀態，FR-024）。

### `member/service.py`

- `MemberMatchFilters`（frozen dataclass）：既有 12 個篩選條件＋`group_id`。
- `FilteredMatch`（frozen dataclass）：`match`、`summary`、`won`、`my_team`、`my_entry_id`。
- `_filtered_member_matches()`、`build_member_match_dashboard()`、`view_member_match_dashboard()`。

## 前端 interface

- `core/api/group-member-view.models.ts`：`ClutchStats` 及其子型別；`MatchRecordDetailResponse.clutch_stats`。
- `core/api/player-dashboard.models.ts`（新）：`DashboardMetric`、`DashboardMetricValue`、`DashboardTrend`、`DashboardTrendPoint`、`DashboardLanding`、`MemberMatchDashboardResponse`；`DashboardMetricKey` 為字串聯集（對應指標目錄），使語系 key 與分組表在 strict mode 下受型別檢查。
- `core/court-diagram`：`CourtDiagramComponent` 新增選用輸入 `dense = input(false)`。

## 語系 key（`assets/i18n/zh-TW.json`／`en.json`）

- `matchRecordDetail.clutch.*`：區塊標題、五個項目標題、「本場未進入平分延長」、「此賽制不適用」、「未曾握有賽末點」、「勝方全場未曾落後」、賽末點與逆轉的敘述句（含參數）、無資料提示。
- `playerDashboard.*`：標題、四個群組標題、每個 `metric.<key>.label`／`.hint`／`.empty`、`basedOn`（「依據 {n} 場／共 {m} 場」）、`recentVsAll`、`verdict.*`、`trend.*`（含「場數不足」）、`landing.*`（含「← 我方｜對手 →」）、`serveExclusionNote`、空狀態。
