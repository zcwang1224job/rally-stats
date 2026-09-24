# Contract: 外掛介面與邊界規則（前後端）

**Feature**: 043-sport-type-plugin-foundation | **Date**: 2026-09-24

## 1. 後端目錄邊界

```
apps/api/app/
├── main.py                      # 組裝根：唯一可匯入 app.sports.types 的核心檔（呼叫 register_all()）
├── core/…                       # 核心
├── domains/…                    # 核心
├── system_config/…              # 核心
└── sports/
    ├── registry.py              # SPORT_TYPES、get(type_key)、register(plugin)
    ├── plugin.py                # SportTypePlugin Protocol、SpineEventContext、SpineEffect、PluginEventContext/Result
    ├── presentation.py          # Section、SportSummary、MetricView（給 metric_grid）
    ├── scoring.py               # match_wins(x, y, *, target, win_by, cap)
    ├── catalog.py               # 內建活動常數 + 名詞集合
    ├── section-kinds.json       # 由契約測試產生，供前端契約測試比對
    └── types/
        ├── __init__.py          # register_all()：匯入三個外掛並註冊
        ├── net_rally/  {plugin.py, params.py, serve.py, placement.py, stats.py, dashboard.py, schemas.py}
        ├── frames/     {plugin.py, params.py, models.py, events.py, stats.py, presentation.py}
        └── generic/    {plugin.py, params.py, presentation.py}
alembic/env.py                   # 允許匯入外掛 models（metadata）
tests/…                          # 不受限
```

`import-linter` 契約（`pyproject.toml`）：

```toml
[tool.importlinter]
root_package = "app"

[[tool.importlinter.contracts]]
name = "core must not import sport type plugins"
type = "forbidden"
source_modules = ["app.core", "app.domains", "app.system_config",
                  "app.sports.registry", "app.sports.plugin", "app.sports.presentation",
                  "app.sports.scoring", "app.sports.catalog"]
forbidden_modules = ["app.sports.types"]

[[tool.importlinter.contracts]]
name = "sport type plugins are independent"
type = "independence"
modules = ["app.sports.types.net_rally", "app.sports.types.frames", "app.sports.types.generic"]

[[tool.importlinter.contracts]]
name = "plugins never publish or touch core services"
type = "forbidden"
source_modules = ["app.sports.types"]
forbidden_modules = ["app.core.realtime", "app.domains.schedule.service", "app.domains.group.service", "app.domains.member.service"]
```

外掛允許匯入：`app.sports.{plugin,presentation,scoring}`、`app.domains.*.models`、`app.domains.*.schemas`（純型別）、`app.core.db`。

品質關卡指令（加入 README 與 docs 的既有清單）：`ruff check app tests && mypy app && lint-imports && python -m pytest -q`。

## 2. 後端外掛介面

見 [data-model.md §10](../data-model.md#10-後端外掛介面資料面)。補充呼叫時序：

| 核心流程 | 呼叫的掛鉤 | 時機 |
|---|---|---|
| `create_group` / `edit_group` | `params_schema()` | 驗證 `type_params` |
| `_start_match` | `on_match_start()` | 比賽進入 `in_progress` 後、commit 前 |
| `apply_score_delta` | `on_spine_event()` → commit → `match_wins()`（預設核心規則） | 寫脊椎 `point` 之後、commit 之前 |
| `apply_plugin_event`（`/events`） | `event_schemas()` 驗證 → `apply_event()` → 若有 `follow_up_point` 再走 `on_spine_event()` | 同一交易 |
| `undo_last_event`（`/undo`） | `after_undo()` | 刪除脊椎列之後、commit 之前 |
| `court_live_state` / `build_schedule_snapshot` / all-courts | `live_state()` | 組回應時 |
| `build_match_record_detail` | `load_stat_inputs()` → `match_detail()` | 組回應時 |
| `build_member_match_dashboard` | `dashboard_metric_specs()`（隔網回合制回 23 項；其他回 None ⇒ 不走此端點） | 既有端點 |
| `build_dashboard_sections` | `load_stat_inputs()` → `dashboard_sections()` | 新端點 |
| 排點時間預估 | `estimate_minutes()` | 既有預估處 |
| 分享圖卡（前端） | `share_highlights`（前端模組） | 前端 |

註冊：`app/sports/types/__init__.py::register_all()` 由 `main.py` 在建立 app 時呼叫；測試 `conftest.py` 亦呼叫（測試不受邊界限制）。`registry.get(type_key)` 對未註冊 key 拋 `UnknownSportType` → API 回 `422`。

## 3. 前端目錄邊界

```
apps/web/src/app/
├── core/ features/ shared/          # 核心：不得匯入 sports/types/**
├── sports/
│   ├── registry.ts                  # SPORT_TYPE_LOADERS（唯一允許動態 import sports/types/** 的核心檔）＋ SportTypeRegistry
│   ├── sport-type-module.ts         # SportTypeModule、SectionComponent、SectionContext 型別
│   ├── section-outlet/              # <app-section-outlet>
│   ├── generic-sections/            # metric-grid、stat-table、score-timeline、text-note、fallback
│   ├── hosts/                       # ScoreboardHost、ControlPanelHost、AllCourtsBlockHost、CourtControlHost、MatchDetailHost、DashboardHost、CreateFormFieldsHost
│   └── types/
│       ├── net-rally/               # 搬移：scoreboard、control-panel、all-courts-court-block、court-control、shot-placement、court-diagram、match-record-detail、player-dashboard、share-card-highlights、match-point.ts
│       ├── frames/                  # frames-scoreboard、frames-control、frame-list-section、frame-trend-section、dashboard-summary-section、create-form-fields
│       └── generic/                 # generic-scoreboard、generic-control、create-form-fields
└── test-setup.ts                    # vitest setupFiles：同步預載 net-rally 模組
```

eslint（`eslint.config.js`）新增覆寫：

```js
{ files: ['src/app/core/**', 'src/app/features/**', 'src/app/shared/**',
          'src/app/sports/section-outlet/**', 'src/app/sports/generic-sections/**', 'src/app/sports/hosts/**'],
  rules: { 'no-restricted-imports': ['error', { patterns: ['**/sports/types/**'] }] } },
{ files: ['src/app/sports/types/net-rally/**'], rules: { 'no-restricted-imports': ['error', { patterns: ['**/sports/types/frames/**', '**/sports/types/generic/**'] }] } },
// frames、generic 各一條同形規則
```

`registry.ts` 與 `test-setup.ts` 以行內 `// eslint-disable-next-line no-restricted-imports` 標註例外並附註。品質關卡：`npm run lint`（已含）。

## 4. `SportTypeModule`

```ts
export interface SportTypeModule {
  readonly typeKey: 'net_rally' | 'frames' | 'generic';
  readonly surfaces: {
    scoreboard: Type<unknown>;          // 輸入：token（既有）＋ initialState?: CourtStateResponse
    controlPanel: Type<unknown>;        // 同上
    allCourtsBlock: Type<unknown>;      // 輸入：token, courtId, name, state（既有）
    courtControl: Type<unknown>;        // 輸入：groupId, court（既有）
    createFormFields: Type<unknown>;    // 輸入：form: FormGroup, sport: BuiltinSport | CustomSport
  };
  readonly sectionKinds: Readonly<Record<string, Type<SectionComponent>>>;
  readonly shareHighlights?: (detail: MatchRecordDetailResponse, protagonist: Team) => Highlight[];
}
```

- 宿主（`hosts/`）只依賴此介面與 `SportTypeRegistry`。
- `SportTypeRegistry.resolve(typeKey): Promise<SportTypeModule>`（快取）；`peek(typeKey): SportTypeModule | undefined`（同步；測試 setup 預載後可得）。
- 載入失敗：宿主顯示 `errors.sportModuleLoadFailed` 與重試按鈕（Edge Case）。

## 5. 新增類型的檢查清單（可擴充性驗收，US7）

1. 後端：`app/sports/types/<key>/`（plugin、params、models、migration 檔以 `<key>_` 前綴）；在 `types/__init__.py::register_all()` 加一行；`catalog.py` 加內建活動列。
2. 前端：`sports/types/<key>/`（surfaces、sections、createFormFields）；`registry.ts` 載入表加一行。
3. i18n：`sports.<sport_key>`、`<key>.*` 鍵（zh-TW／en）。
4. 測試：外掛規則、統計、區塊各至少一個 spec；契約測試自動涵蓋。
5. **不得**改動：`core/**`、`domains/**`、`features/**`、`sports/hosts/**`、`section-outlet/**`、其他 `types/*`。SC-005 以 `git diff --name-only` 驗證。
