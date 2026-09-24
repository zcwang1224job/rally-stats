# Contract: 頁面區塊清單（詳細頁、儀表板）

**Feature**: 043-sport-type-plugin-foundation | **Date**: 2026-09-24

## 1. `Section` 形狀

```jsonc
{ "kind": "frames.frame_list", "title_key": "frames.sections.frameList" | null, "data": { … } | null }
```

- `kind` 命名：通用區塊無前綴（`metric_grid`、`stat_table`、`score_timeline`、`text_note`）；類型專屬區塊 `<type_key>.<name>`。
- `data: null` 且 kind 為 `net_rally.match_detail`／`net_rally.dashboard` 時，表示「資料在本回應的頂層欄位」或「由區塊元件自行取用既有端點」（研究 Decision 12）。
- 前端 `SectionOutlet` 解析順序：`registry.peek(type_key).sectionKinds[kind]` → 通用區塊表 → 通用退路（把 `data` 以 `stat_table` 或 JSON 摘要呈現，附「此區塊需要更新版本」提示）。找不到絕不留白或拋錯（FR-021、US7 情境 2）。

## 2. 通用區塊資料形狀

| kind | data |
|---|---|
| `metric_grid` | `{ metrics: [{ key, label_key, kind: "rate"\|"average"\|"ratio"\|"count", value: number\|null, numerator?, denominator?, better_when? }] }` |
| `stat_table` | `{ columns: [{ key, label_key }], rows: [{ [key]: string\|number\|null }] }` |
| `score_timeline` | `{ target_score, cap_score, events: [{ side, delta, score_a, score_b, elapsed_seconds, kind }] }`（只含 `point`） |
| `text_note` | `{ text_key, params? }` |

## 3. 各類型宣告的區塊（本期）

### `net_rally`

| 頁面 | sections |
|---|---|
| 詳細頁 | `[{ kind: "net_rally.match_detail", data: null }]`（區塊元件＝搬移後的 `MatchRecordDetailDialogComponent` 主體，讀頂層欄位） |
| 儀表板 | `[{ kind: "net_rally.dashboard", data: null }]`（區塊元件內含既有 `PlayerDashboardComponent`＋insights＋benchmark，自行呼叫既有 `match-dashboard`／`insights` 端點並帶 `sport` 參數） |

非羽球的隔網活動（發球／落點模組關閉）走同一組區塊；既有元件依回應中 `serve_stats`／`landing_distribution` 為 null 而省略對應區塊（既有行為：`record_completeness` 與 null 處理已存在，需確認 `court-diagram` 與 `serve` 區塊對 null 的處理並補測試）。

### `frames`

| 頁面 | sections |
|---|---|
| 詳細頁 | `frames.frame_list`：`{ frames: [{ frame_no, winner_team, score_a, score_b, ended_by, elapsed_seconds }] }`；`frames.frame_trend`：`{ points: [{ frame_no, frames_a, frames_b }] }` |
| 儀表板 | `metric_grid`（`match_win_rate`、`frame_win_rate`、`win_rate_after_first_frame`、`avg_frames_per_match`、`matches`、`wins`、`losses`）、`frames.dashboard_summary`：`{ best_comeback?: {…}, decider_record: { played, won } }`、`stat_table`（對手分析，來自核心 `matchups.build`） |

### `generic`

| 頁面 | sections |
|---|---|
| 詳細頁 | `score_timeline`（+N 事件）、`metric_grid`（`points_for`、`points_against`、`margin`） |
| 儀表板 | `metric_grid`（`match_win_rate`、`matches`、`wins`、`losses`、`draws`、`avg_points_for`、`avg_points_against`）、`stat_table`（對手分析） |

## 4. 端點

### 詳細頁（既有三個端點，回應新增欄位）

`GET /groups/{gid}/match-records/{mid}`、`GET /members/me/match-records/{mid}`、`GET /members/{id}/match-records/{mid}`：

```jsonc
{ …既有欄位（羽球不變）…,
  "sport": { …SportSummary… },
  "sections": [ … ] }
```

隔網回合制以外：`serve_stats`、`landing_distribution`、`ending_stats`、`player_stats`、`momentum_stats`、`tempo_stats`、`clutch_stats` 為 `null`；`events[]` 仍回脊椎 `point` 事件（`delta` 為 int、含 `kind`），`detail` 為 null。

### 儀表板區塊（新增）

`GET /members/me/dashboard-sections?sport=<filter_value>&…match_filters_query`
`GET /members/{member_id}/dashboard-sections?sport=…`

```jsonc
{ "sport": { …SportSummary… }, "type_key": "frames", "total_matches": 12, "sections": [ … ] }
```

- `sport` 必填；其餘篩選同 `match_filters_query`。
- `total_matches == 0` 時 `sections` 為 `[{ kind: "text_note", data: { text_key: "playerDashboard.empty" } }]`。
- 授權同對應的 `match-dashboard` 端點。

### 既有儀表板端點（不變形狀）

`GET /members/me/match-dashboard`、`/members/{id}/match-dashboard`、`/members/me/match-insights`（若存在）、`benchmark`：新增 `sport` 查詢參數；`sport` 指向非隔網回合制活動時回 `409 SPORT_TYPE_NOT_SUPPORTED`（前端不會呼叫）。回應形狀零變更。

## 5. 契約測試

- 後端：`tests/unit/sports/test_plugin_contracts.py` 對每個已註冊外掛：`dashboard_sections()` 與 `match_detail()` 產出的每個 `kind` ∈ `section_kinds ∪ 通用區塊`；`section_kinds` 匯出成 `app/sports/section-kinds.json`（測試以 `--update` 旗標更新，CI 比對不得漂移）。
- 前端：`sports/section-outlet/section-outlet.contract.spec.ts` 讀同一份 JSON，對每個 kind 斷言 `registry` 有元件或 `GENERIC_KINDS` 含之；另有一個 `unknown.kind` 案例斷言退路渲染且不拋錯。
