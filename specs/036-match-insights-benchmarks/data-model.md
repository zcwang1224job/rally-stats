# Phase 1 Data Model: 對戰紀錄洞察

決策見 [research.md](./research.md)。**沒有任何儲存變更**：無新資料表、無新欄位、無 migration。以下全部是查看當下推導出的純資料結構與回應 schema。

## 身分鍵 `player_key`（貫穿三個模組）

定義於新的小模組 `member/player_identity.py`（無 ORM）：`player_key(member_id, roster_entry_id) -> str`、`parse_player_key(value) -> ParsedKey`（格式不合 → `ValueError`，由路由層轉為 `422 INVALID_PLAYER_KEY`）、`PlayerRef`。獨立成檔是為了讓 `matchups.py`（US2）、`group_benchmark` 的服務層（US3）、比較端點（US4）各自引用，而不互相依賴。

| 名單列 | `player_key` | 合併範圍 |
|---|---|---|
| `roster_entries.member_id` 不為 NULL（含依 028 綁定後） | `m:<member_id>` | 跨團、跨多段參與期間合併 |
| `member_id` 為 NULL（未綁定訪客） | `r:<roster_entry_id>` | 只有這一列；不跨團 |

- 格式：`^(m|r):[0-9a-f-]{36}$`。
- 顯示暱稱：該 `player_key` 在範圍內**最近一場**比賽（`ended_at` 最大）中的 `ParticipantSummary.nickname`。
- 已刪除帳號：名單列的 `member_id` 仍在、暱稱為 `"Deleted User"`；各自成一列（不再併計），前端沿用 `app-nickname` 既有的灰階呈現。

## 純函式模型 (1)：`member/matchups.py`（新增，無 ORM）

```text
MatchupInput      # 每場一筆，由 FilteredMatch 轉出
  ended_at: datetime
  won: bool
  margin: int                      # 我方得分 − 對方得分
  is_doubles: bool
  partners:  tuple[PlayerRef, ...] # 單打為空；雙打 1 位（排除自己的 roster_entry_id）
  opponents: tuple[PlayerRef, ...] # 1 或 2 位

PlayerRef         key: str, nickname: str, member_id: str | None

MatchupRecord
  player_key, nickname, member_id | None
  matches, wins, losses: int
  win_rate: float                  # wins ÷ matches
  avg_margin: float                # Σmargin ÷ matches，四捨五入到 0.1，可為負
  low_sample: bool                 # matches < LOW_SAMPLE_BELOW (3)

MatchupHighlights                  # 值為 player_key；無人達門檻 → None
  most_played_partner, best_partner, most_faced_opponent, toughest_opponent

MatchupResult
  partner_records:  list[MatchupRecord]   # 依 matches 由多到少；同場數依 player_key 穩定排序
  opponent_records: list[MatchupRecord]
  highlights: MatchupHighlights
  doubles_matches: int             # 0 → 前端顯示「單打比賽沒有搭檔」（FR-026）
  overall_win_rate: float | None   # 供 insights 使用
  doubles_win_rate: float | None
```

`build(inputs) -> MatchupResult`。常數：`LOW_SAMPLE_BELOW = 3`、`HIGHLIGHT_MIN_MATCHES = 5`。重點摘要規則（FR-024）：「最常」取場數最多者（不設門檻，但須 ≥ 3 場）；「勝率最高的搭檔／勝率最低的對手」只從 ≥ 5 場的列中選，勝率相同取場數多者，再相同取 `player_key` 較小者（確保可重現）。

另一個函式 `head_to_head(inputs, friend_key) -> HeadToHead`（US4）：

```text
HeadToHead
  as_opponents: MatchupTally | None   # 從未互為對手 → None
  as_partners:  MatchupTally | None
MatchupTally      matches, wins, losses, win_rate, avg_margin   # 皆從檢視者的角度
```

## 純函式模型 (2)：`member/insights.py`（新增，無 ORM）

```text
Insight
  list:   "strength" | "weakness" | "recent" | "matchup"
  rule:   InsightRule
  level:  "strong" | "mild"
  source: "benchmark" | "self" | "trend" | "matchup"
  metric_key: str | None           # 034／035 的 23 個 key 之一
  player: PlayerRef | None         # 只有 matchup 類有
  params: dict[str, float | int | str | None]

InsightsResult
  status: "ok" | "insufficient_data" | "balanced"
  strengths:  list[Insight]        # ≤ 3
  weaknesses: list[Insight]        # ≤ 3
  recent:     list[Insight]        # ≤ 2
  matchups:   list[Insight]        # ≤ 2（搭檔、對手各至多 1）
  benchmark_group_name: str | None # 有納入團內比較來源時
```

`derive(samples, dashboard, matchups, benchmark=None) -> InsightsResult`。

### 規則表

| `rule` | 來源 | 適用指標 | 基準 | 候選條件（輕微／明顯） | 最低樣本 |
|---|---|---|---|---|---|
| `rate_vs_overall` | self | `team_serve` `team_receive` `own_serve` `own_receive` `endgame` | 發球類：Σ(該場此指標的分母 × `(points_for − 1) ÷ (played − 1)`) ÷ Σ分母；接發球類同式但用 `points_for ÷ (played − 1)`；`endgame`：該指標所涵蓋比賽的 Σ`points_for` ÷ Σ`played`（FR-011；`insights.expected_rate()`） | 偏離 ≥ 0.05／≥ 0.10 | 分母 ≥ 30 分且 `matches_used` ≥ 3 |
| `deuce_vs_even` | self | `deuce` | 0.50 | 同上 | 同上 |
| `error_share_high` | self | `error_share_of_lost` | — | ≥ 0.60／≥ 0.70 → weakness | 分母 ≥ 20 分 |
| `winner_share_high` | self | `winner_share` | — | ≥ 0.50／≥ 0.60 → strength | 分母 ≥ 20 分 |
| `recent_change` | trend | 所有 `better_when` 非空、`verdict ∈ {improved, declined}` 的指標 | 「全部」的值 | `rate`：差 ≥ 0.05／0.10；`average`／`ratio`：相對變化 ≥ 15%／30%；「全部」的值為 0 時相對變化無定義 → 不產生候選 | 沿用 034（`recent.matches_used` ≥ 3） |
| `partner_above_overall` | matchup | — | `doubles_win_rate` | 勝率高出 ≥ 0.15／≥ 0.30 | 一起出賽 ≥ 5 場 |
| `opponent_below_overall` | matchup | — | `overall_win_rate` | 勝率低於 ≥ 0.15／≥ 0.30 | 交手 ≥ 5 場 |
| `benchmark_quartile` | benchmark | 所有有名次的指標 | 團內平均 | `q = pool_size // 4`（無條件捨去；`pool_size ≥ 4` 故 q ≥ 1）；`pool_size − rank_from_bottom + 1`（同名次或更好的人數）`≤ q` → strength；`pool_size − rank + 1`（同名次或更差的人數）`≤ q` → weakness；並列因此佔用名額；第 1 名或倒數第 1 名**且** `pool_size ≥ 8` 為明顯，其餘輕微 | `pool_size` ≥ 4 |

- **明訂排除**（FR-012）：`when_leading`、`when_tied`、`when_trailing`、`match_point_conversion` 不進 `rate_vs_overall`；`match_points_saved`（`better_when` 為空）不進任何規則。
- **成對指標**（FR-016）：`(team_serve, team_receive)`、`(own_serve, own_receive)` 每組只留偏離絕對值較大者；相同留 weakness。
- **同一指標多來源**（Edge Cases）：strength／weakness 清單中同一個 `metric_key` 只留 `source` 優先序最高者（benchmark > self）。`recent` 是獨立清單，不去重。
- **排序**（FR-015）：`level`（strong 先）→ `source`（benchmark 先）→ 樣本數（同一來源內比較：self 取 `denominator`、benchmark 取 `mine.matches_used`，大者先）→ `_METRICS` 的固定順序。
- **`recent` 至少一句進步**（FR-014）：若候選同時有進步與退步而前兩名皆為退步，第二名換成排名最高的進步。
- **`error_share_high` 的 `dominant_error`**：034／035 的 `error_breakdown_all` 中佔本人失誤 > 50% 的種類（`out`／`net`／`serve_fault`／`other_error`），否則 `None`。
- **`status`**：四個清單皆空時——若**沒有任何規則達到最低樣本** → `insufficient_data`；若有規則達樣本但無一達門檻 → `balanced`。否則 `ok`（個別清單為空由前端顯示該清單的說明行，FR-018）。

### `params` 內容（前端組句用；全部是回應中其他地方也查得到的同一個數字，FR-002）

| `rule` | `params` |
|---|---|
| `rate_vs_overall`／`deuce_vs_even` | `value`, `numerator`, `denominator`, `matches_used`, `baseline`, `diff` |
| `error_share_high` | `value`, `numerator`, `denominator`, `matches_used`, `dominant_error`, `dominant_share` |
| `winner_share_high` | `value`, `numerator`, `denominator`, `matches_used` |
| `recent_change` | `direction`（`improved`｜`declined`）, `all_value`, `recent_value`, `diff`, `recent_matches_used`, `kind` |
| `partner_above_overall`／`opponent_below_overall` | `win_rate`, `matches`, `wins`, `losses`, `baseline`, `diff` |
| `benchmark_quartile` | `mine`, `group_average`, `diff`, `rank`, `pool_size`, `kind` |

## 純函式模型 (3)：`member/group_benchmark.py`（新增，無 ORM）

```text
PlayerValues      player_key: str, values: dict[str, MetricValue]   # 只存在於服務函式內，不進回應

BenchmarkMetric
  key, kind, better_when            # 與 034 的 _METRICS 同源
  mine: MetricValue | None          # 我只依此團比賽的值；我在此團沒有該指標資料 → None
  status: "ok" | "pool_too_small" | "self_below_minimum" | "no_direction"
  group_average: float | None       # status = pool_too_small → None
  pool_size: int                    # 達門檻人數（含我，若我達門檻）
  rank: int | None                  # 只有 status = ok 才有；並列同名次
  rank_from_bottom: int | None      # 相反方向的 1224 名次；只供 insights 使用，**不進回應 schema**

BenchmarkResult   metrics: list[BenchmarkMetric]   # 23 項，順序同 _METRICS
```

`build(me_key, players: list[PlayerValues]) -> BenchmarkResult`。常數：`MIN_MATCHES_PER_PLAYER = 5`、`MIN_POOL = 3`、（四分之一的人數門檻 `QUARTILE_MIN_POOL = 4`／`QUARTILE_STRONG_MIN_POOL = 8` 屬於摘要規則，定義在 `insights.py`）。

- **達門檻**：該球員該指標的 `matches_used ≥ 5` 且 `value` 不為 `None`。
- **`group_average`**：達門檻者 `value` 的算術平均（每人權重相同），四捨五入規則與 034 相同（`rate` 4 位、其餘 2 位）。
- **`status` 判定順序**：`pool_size < 3` → `pool_too_small`；`better_when` 為空 → `no_direction`（有平均、無名次）；我未達門檻 → `self_below_minimum`（有平均、無名次）；否則 `ok`。
- **名次**：依 `better_when` 排序（`higher` 由大到小、`lower` 由小到大），標準競賽排名（1224）。`rank_from_bottom` 以相反的排序方向、同一規則算出（最後一名並列兩人時，兩人的 `rank_from_bottom` 皆為 1）。

`player_dashboard.py` 新增一個函式：`overall_values(samples) -> dict[str, MetricValue]`——對 `_METRICS` 逐項呼叫既有的 `_metric_value()`，不算對比、趨勢、落點。`aggregate()` 不變。

## 服務層（`member/service.py`）

| 函式 | 變更 |
|---|---|
| `MemberMatchFilters` | ＋`partner_key`、`opponent_key` |
| `_filtered_member_matches()` | ＋兩個精確身分的後置篩選 |
| `build_member_match_records()` | 以 `matchups.build()` 取代 `opponent_tallies`；回應＋`partner_records`、`matchup_highlights`、`doubles_matches` |
| `_dashboard_sample()` | 拆為 `_match_derivations()`＋`_sample_from()`；對外行為不變 |
| `build_member_match_dashboard()` | ＋`insights`（`insights.derive(samples, result, matchups)`） |
| `list_benchmark_groups()` | 新增 |
| `build_group_benchmark()` | 新增；純運算以 `asyncio.to_thread()` 執行 |
| `view_member_match_comparison()` | 新增；經 `_resolve_viewable_member()` |

`group/service.py`：修正 `verify_ever_group_member()`（research Decision 7）；新增公開的 `load_group_completed_matches(session, group_id)`（把 `_completed_matches_query()`＋`_build_match_record_summaries()` 包成一個不帶篩選與分頁的載入器，供 `member` 使用，避免跨模組呼叫私有函式）。

## 回應 Schema（後端）

完整欄位與範例見 [contracts/](./contracts/)。

- `group/schemas.py`：新增 `MatchupRecord`、`MatchupHighlights`；`MemberMatchRecordsResponse.opponent_records` 型別由 `list[OpponentRecord]` 改為 `list[MatchupRecord]`（既有五個欄位不變），＋`partner_records: list[MatchupRecord] = []`、`matchup_highlights`、`doubles_matches: int = 0`。`OpponentRecord` 與團的 `player_records` **不變**。
- `member/schemas.py`：新增 `DashboardInsight`、`DashboardInsights`；`MemberMatchDashboardResponse.insights`（具預設值）。新增 `BenchmarkGroupOption`、`BenchmarkGroupsResponse`、`GroupBenchmarkMetric`、`GroupBenchmarkResponse`、`ComparisonMetric`、`HeadToHeadTally`、`MatchComparisonResponse`。

## 前端 interface

- `core/api/group-member-view.models.ts`：`MatchupRecord extends OpponentRecord`、`MatchupHighlights`；`MemberMatchRecordsResponse` 與 `MemberMatchRecordFilters` 擴充。
- `core/api/player-dashboard.models.ts`：`INSIGHT_RULES`（字串聯集，與後端以測試綁定）、`DashboardInsight`、`DashboardInsights`。
- `core/api/group-benchmark.models.ts`（新）、`core/api/match-comparison.models.ts`（新）。
- `core/benchmark-group-preference.ts`（新）：`getBenchmarkGroup(memberId)`／`setBenchmarkGroup(memberId, groupId)`。

## 語系 key（`zh-TW.json`／`en.json`）

- `playerInsights.*`：`title`、`list.{strength,weakness,recent,matchup}`、`listEmpty.*`、`status.{insufficientData,balanced}`、`benchmarkPending`、`benchmarkOmittedByFilters`、`evidence`、`rule.<rule>.<variant>`（每條規則的每個變體一句，參數即上表 `params`）。
- `member.matchHistory.matchups.*`：`partnerTitle`、`opponentTitle`、`columns.*`、`sort.*`、`lowSample`、`noDoubles`、`highlights.*`、`activePartner`、`activeOpponent`、`clear`。
- `groupBenchmark.*`：`title`、`pickGroup`、`scopeNote`、`noGroups`、`columns.*`、`rank`、`status.{poolTooSmall,selfBelowMinimum,noDirection}`、`loading`、`failed`。
- `friendComparison.*`：`toggle`、`me`、`friend`、`better`、`headToHead.*`、`neverPlayed`。
