# Data Model: 多活動支援與比賽類型外掛基礎（043）

**Plan**: [plan.md](./plan.md) | **Research**: [research.md](./research.md)

本文件描述資料表變更、ORM 擁有權、快照規則與狀態轉換。表名與欄位以 Postgres 為準；ORM 類別以 SQLAlchemy 2 宣告式為準。所有新 NOT NULL 欄位都有 `server_default`（研究 F6），既有資料回填為羽球值。

## 1. 擁有權總表

| 表 | 擁有者 | 核心可否查詢 | 備註 |
|---|---|---|---|
| `groups`、`matches`、`match_participants`、`courts`、`roster_entries`… | 核心 | 是 | 新增通用參數欄位（§2、§3） |
| `score_events`（脊椎） | 核心 | 是 | 加 `kind`、`side` 可空（§4） |
| `member_sports` | 核心（活動目錄） | 是 | 會員自訂活動（§5） |
| `score_serve_records`、`shot_placement_records` | **`net_rally` 外掛** | **否** | ORM 類別留在 `app.domains.schedule.models`（研究 Decision 9），由外掛 `tables()` 宣告；核心不得 `select` 它們 |
| `frames_frame_results`、`frames_frame_points` | **`frames` 外掛** | 否 | 新表（§7） |
| （無） | `generic` 外掛 | — | 通用類型沒有自己的表 |

「核心不得查詢」由 research Decision 15 的契約測試守住。所有外掛表都以 `score_event_id` 外鍵到脊椎並 `ON DELETE CASCADE`，因此解散團／刪除比賽／`/undo` 只要處理脊椎與 `matches`，外掛表自動清理。

## 2. `groups` 新增欄位

| 欄位 | 型別 | 預設（server_default） | 說明 |
|---|---|---|---|
| `sport_key` | `String(32) NOT NULL` | `'badminton'` | 內建活動 key、`'custom'`、`'other'` |
| `type_key` | `String(16) NOT NULL` | `'net_rally'` | 比賽類型；由 `sport_key` 決定，快照下來避免目錄變動影響既有團 |
| `sport_name` | `String(20) NULL` | NULL | `custom`／`other` 時的活動名稱快照；內建為 NULL（前端用 i18n key） |
| `custom_sport_id` | `UUID NULL FK member_sports(id) ON DELETE SET NULL` | NULL | 來源自訂活動；刪除後 `sport_name` 仍可顯示 |
| `team_size` | `SmallInteger NOT NULL` | `1` | migration 回填：`match_mode='doubles'` → 2 |
| `end_mode` | `String(8) NOT NULL` | `'target'` | `target` / `manual` |
| `win_by` | `SmallInteger NOT NULL` | `2` | 需領先分數；≥ 1 |
| `allow_draw` | `Boolean NOT NULL` | `false` | 只在 `manual` 有意義 |
| `score_steps` | `JSONB NOT NULL` | `'[1]'` | 正整數陣列，非空、遞增、無重複 |
| `type_params` | `JSONB NOT NULL` | `'{}'` | 類型專屬參數，schema 由外掛定義 |
| `cap_score` | 既有 `Integer` → **改為 NULL 可空** | — | 既有資料不動（羽球 30） |

既有欄位維持：`match_mode`（相容別名，Decision 6）、`scoring_mode`、`target_score`、`deuce_threshold`、`detailed_scoring_enabled`、`scoreboard_scoring_enabled`、`partner_source`、`continuous_rotation`。

**模型層不變量**（`Group` 的 validator／`__init__` 處理）：
- `team_size` 與 `match_mode` 互相推導：1 ↔ `singles`、2 ↔ `doubles`；兩者都給且不一致 → `ValueError`。
- `end_mode='target'` 時 `target_score ≥ win_by ≥ 1`、`cap_score is None or cap_score ≥ target_score`；`end_mode='manual'` 時 `target_score`／`cap_score` 不參與判定（保留既有值以維持 NOT NULL）。
- `sport_key ∈ catalog ∪ {custom, other}`；`sport_key='custom'` ⇒ `custom_sport_id` 或 `sport_name` 至少一個非空；`sport_key='other'` ⇒ `sport_name` 非空。
- `type_params` 於建立／編輯時交由 `registry.get(type_key).params_schema()` 驗證；模型層只存。
- `detailed_scoring_enabled=true` 只允許外掛 `modules.shot_placement=true` 的活動（本期只有羽球）；其他活動的 `set_detailed_scoring` → `409 MODULE_NOT_SUPPORTED`。

**不可變**：`sport_key`、`type_key`、`custom_sport_id`、`sport_name` 在建立後不可修改（FR-007）；`edit_group` 若收到不同值 → `409 SPORT_IMMUTABLE`。

## 3. `matches` 快照欄位

| 欄位 | 型別 | 預設 | 來源 |
|---|---|---|---|
| `sport_key` | `String(32) NOT NULL` | `'badminton'` | `group.sport_key` |
| `type_key` | `String(16) NOT NULL` | `'net_rally'` | `group.type_key` |
| `sport_name` | `String(20) NULL` | NULL | `group.sport_name` |
| `team_size` | `SmallInteger NOT NULL` | `1` | `group.team_size`；migration 由參賽人數回填（≤2 人 → 1，否則 2） |
| `end_mode` | `String(8) NOT NULL` | `'target'` | `group.end_mode` |
| `win_by` | `SmallInteger NOT NULL` | `2` | `group.win_by` |
| `allow_draw` | `Boolean NOT NULL` | `false` | `group.allow_draw` |
| `score_steps` | `JSONB NOT NULL` | `'[1]'` | `group.score_steps` |
| `type_params` | `JSONB NOT NULL` | `'{}'` | `group.type_params` |
| `cap_score` | 既有 → **改為可空** | — | `group.cap_score` |
| `winner_team` | 既有 `String(1) NULL` | — | 值域擴為 `A|B|D`；`completed` ⇒ 非空、`abandoned` ⇒ NULL（Decision 4） |

快照時機：`create_match_with_participants`（與既有 `target_score`／`deuce_threshold`／`cap_score`／`detailed_scoring_enabled` 同一處）。憲章 III：比賽開始後團設定變更不影響進行中比賽。

既有 `serving_team`、`team_a_reference_server_id`、`team_b_reference_server_id` 留在 `matches`（研究 F7、風險點 3）：它們是 `net_rally` 外掛的狀態，但因 66 處測試直接讀取而保留原位；核心的 `_start_match` 改為呼叫 `plugin.on_match_start()`（`net_rally` 在此初始化發球狀態），核心本身不再引用這三欄的語意。

### 狀態轉換

```
queued ──start──▶ in_progress ──point 達標（end_mode=target）──▶ completed (winner A|B)
                      │──/finish（end_mode=manual）──▶ completed (winner A|B|D)
                      │──/end（放棄，所有類型）──▶ abandoned (winner NULL)
completed ──undo-completion（既有，隔網回合制）──▶ in_progress
```

`/undo`（Decision 13）只在 `in_progress` 可用；若最後一筆事件是造成 `completed` 的 `point`，本期不支援（回 `409 MATCH_NOT_IN_PROGRESS`，使用既有 undo-completion）。

## 4. `score_events`（脊椎）

| 欄位 | 變更 | 說明 |
|---|---|---|
| `kind` | **新增** `String(24) NOT NULL server_default 'point'` | `point`＝改變場級比分；其他 kind 由外掛宣告，命名 `<type_key>.<name>`（如 `frames.frame_point`） |
| `side` | `String(1)` → **改為可空** | 非得分事件可為 NULL |
| `delta` | 既有 `Integer` | `point`：非 0，且 `abs(delta) ∈ score_steps`；其他 kind：0 |
| `score_a`、`score_b` | 既有 | 事件後的場級比分投影（非得分事件＝不變的現值） |
| `source` | 既有 `String(16)` | 操作來源＝規格「操作者」：`control_panel|admin|all_courts|scoreboard|cancel_score` |
| `created_at` | 既有 | 全域順序以 `(created_at, id)` 為準；既有索引 `ix_score_events_match_created` 沿用 |

ORM：`ScoreEvent` 類別名、模組路徑、屬性名全部不變（研究 F1）。

**核心讀者的規則**：任何以「得分序列」為前提的核心邏輯（`_record_completeness`、`_to_raw_events`、比分走勢、`clutch_stats` 的 point log、分享圖卡走勢）一律過濾 `kind == 'point'`。

## 5. `member_sports`（會員自訂活動）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `id` | `UUID PK` | |
| `member_id` | `UUID NOT NULL FK members(id) ON DELETE CASCADE` | 建立者；索引 |
| `name` | `String(20) NOT NULL` | 1–20 字；`UNIQUE (member_id, name)` |
| `type_key` | `String(16) NOT NULL` | 本期 `net_rally|frames|generic` |
| `team_size_options` | `JSONB NOT NULL` | 子集合於 `{1,2}` |
| `defaults` | `JSONB NOT NULL` | `{team_size, end_mode, target_score, win_by, cap_score, allow_draw, score_steps, type_params, nouns}` |
| `created_at` | `TIMESTAMPTZ NOT NULL` | |

- 每位會員上限 20 筆（FR-003）：服務層計數檢查 → `409 CUSTOM_SPORT_LIMIT`。
- 刪除：硬刪除；`groups.custom_sport_id` 因 `SET NULL` 保留團的 `sport_name` 快照。
- 只有 `require_verified_member` 可建立／刪除；列出時只回自己的。

## 6. 內建活動目錄（程式常數，`app/sports/catalog.py`）

每筆 `BuiltinSport`：`key`、`type_key`、`name_key`（i18n）、`icon`、`team_size_options`、`defaults`（同 §5 的 `defaults` 形狀）、`nouns`（`venue|score|member` 的 i18n key）。本期清單與預設值（規格 Assumptions 的數值，plan 階段確認）：

| key | type | 每隊 | end_mode | target | win_by | cap | steps | type_params | 名詞（場地／分數／成員） |
|---|---|---|---|---|---|---|---|---|---|
| `badminton` | net_rally | 1,2 | target | 21 | 2 | 30 | [1] | `{modules:{serve_tracking:true, shot_placement:true}}` | 球場／分／球員 |
| `table_tennis` | net_rally | 1,2 | target | 11 | 2 | null | [1] | `{modules:{serve_tracking:false, shot_placement:false}}` | 球桌／分／球員 |
| `pickleball` | net_rally | 1,2 | target | 11 | 2 | null | [1] | 同上 | 球場／分／球員 |
| `tennis_tiebreak` | net_rally | 1,2 | target | 10 | 2 | null | [1] | 同上 | 球場／分／球員 |
| `billiards` | frames | 1 | target | 5 | 1 | null | [1] | `{frame_scoring_enabled:false, frame_target:null, frame_win_by:1}` | 球桌／局／球員 |
| `darts` | frames | 1 | target | 3 | 1 | null | [1] | 同上 | 靶台／局／選手 |
| `board_game` | frames | 1,2 | target | 1 | 1 | null | [1] | 同上 | 棋桌／局／玩家 |
| `esports` | frames | 1,2 | target | 2 | 1 | null | [1] | 同上 | 機台／局／選手 |
| `other` | generic | 1,2 | manual | 1 | 1 | null | [1] | `{}` | 場地／分／成員 |

羽球列的 `scoring_mode` 預設仍為 `21pt`（既有 `_SCORING_PRESETS` 保留給隔網回合制的 `21pt/15pt/custom` 下拉）；其他隔網活動的下拉只顯示 `custom` 與該活動預設（前端由 `defaults` 產生）。

`system_config` 新增 key：`default_group_name_suffix.<sport_key>`、`default_court_name.<sport_key>`（本期種子：`badminton`＝既有值、`table_tennis`／`pickleball`／`tennis_tiebreak`／`billiards`／`darts`／`board_game`／`esports`／`other`）；讀取時先找 `<key>.<sport_key>`，找不到退回既有 `<key>`（羽球團因此完全走既有路徑）。

## 7. `frames` 外掛表

（由 `frames` 外掛自己的 migration 建立，不放在核心的基礎 migration 中；符合 contracts/plugin-boundary.md §5「migration 放外掛」。）

### `frames_frame_results`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `score_event_id` | `UUID PK FK score_events(id) ON DELETE CASCADE` | 對應的脊椎 `point`（+1 給勝方） |
| `match_id` | `UUID NOT NULL FK matches(id) ON DELETE CASCADE`，索引 | |
| `frame_no` | `SmallInteger NOT NULL` | 從 1 起；`UNIQUE (match_id, frame_no)` |
| `winner_team` | `String(1) NOT NULL` | `A|B` |
| `score_a`、`score_b` | `SmallInteger NULL` | 局內比分（未啟用局內比分時 NULL） |
| `ended_by` | `String(8) NOT NULL` | `target`（局內達標自動）／`manual`（計分員標記） |

### `frames_frame_points`

| 欄位 | 型別 | 說明 |
|---|---|---|
| `score_event_id` | `UUID PK FK score_events(id) ON DELETE CASCADE` | 對應脊椎 kind `frames.frame_point`（`delta=0`） |
| `match_id` | `UUID NOT NULL FK matches(id) ON DELETE CASCADE`，索引 | |
| `frame_no` | `SmallInteger NOT NULL` | |
| `side` | `String(1) NOT NULL` | `A|B` |
| `delta` | `SmallInteger NOT NULL` | `+1` / `-1` |
| `frame_score_a`、`frame_score_b` | `SmallInteger NOT NULL` | 事件後的本局比分 |

### `type_params`（局數制）

| 鍵 | 型別 | 規則 |
|---|---|---|
| `frame_scoring_enabled` | bool | 是否記局內比分 |
| `frame_target` | int \| null | 局內達標分；`null` ⇒ 該局只能手動結束 |
| `frame_win_by` | int ≥ 1 | 局內需領先分數；`frame_target` 為 null 時忽略 |

### 即時狀態（外掛 `live_state()` 推導，不落表）

`{frame_no, frame_score_a, frame_score_b, frames_to_win: match.target_score, frame_scoring_enabled, frame_target}`；`frame_no` = 最後一筆 `frame_result.frame_no + 1`（無則 1）；本局比分 = 該 `frame_no` 的最後一筆 `frame_point` 的投影（無則 0:0）。

### 事件規則

- `frames.frame_point`：只在 `frame_scoring_enabled` 時接受；`delta=-1` 時本局該側分數不得為負；寫入後若 `frame_target` 非空且達標（含 `frame_win_by`），外掛**自動**追加一筆 `frame_result(ended_by='target')` 與脊椎 `point`。
- `frames.frame_end`：`{winner_team}`；任何比分皆可（分低者被標勝由前端二次確認）；寫 `frame_result(ended_by='manual')` 與脊椎 `point`。
- `/undo`：刪除最後一筆脊椎事件（cascade 帶走 `frame_result` 或 `frame_point`）；若刪的是 `point`，核心同時把 `matches.score_x -= delta`。

## 8. `net_rally` 外掛表（既有，僅擁有權變更）

`score_serve_records`、`shot_placement_records` 欄位與索引不變。`type_params.modules.serve_tracking=false` 的活動不寫 `score_serve_records`（`on_match_start` 不初始化發球、`on_spine_event` 不快照）；`modules.shot_placement=false` 的活動拒絕 `shot-placement` 端點（`409 MODULE_NOT_SUPPORTED`）且 `detailed_scoring_enabled` 不得為 true。

## 9. 回應／檢視模型的變更（節錄，完整見 contracts/）

| 模型 | 變更 |
|---|---|
| `GroupPublicResponse`、`GroupListItem`、`JoinLinkPreviewResponse`、`AdminGroupResponse`、`MyGroupSummary` | 新增 `sport: SportSummary`、`team_size`；保留 `match_mode` |
| `SportSummary` | `{sport_key, type_key, name_key: str \| null, name: str \| null, icon, nouns: {venue, score, member}}`；內建活動 `name_key` 非空、`name` 為 null；自訂／其他相反 |
| `MatchSummary`、`MatchLiveDetail`、`MatchRecordSummary` | `cap_score` 改可空；新增 `sport`、`end_mode`、`win_by`、`allow_draw`、`score_steps`、`sport_state: dict \| null` |
| `MatchRecordSummary.winner_team` | `Literal["A","B","D"]` |
| `RoundRecord`、`MemberStandingRow`、`FinalStandingRow`、`OpponentRecord` | 新增 `draws: int`（預設 0） |
| `MatchRecordDetailResponse` | 新增 `sport`、`sections: list[Section]`；隔網回合制以外的類型其羽球專屬欄位為 null／空 |
| `ScoreEventSummary.delta` | `Literal[1,-1]` → `int`；新增 `kind` |
| `ScoreMutationResult` | 新增 `sport_state`；`serve` 保留 |

## 10. 後端外掛介面（資料面）

```
class SportTypePlugin(Protocol):
    type_key: str
    team_size_range: tuple[int, int]          # 本期 (1, 2)
    modules: frozenset[str]                   # 可開關模組名
    def params_schema(self) -> type[BaseModel]                      # type_params 驗證
    def event_schemas(self) -> Mapping[str, type[BaseModel]]        # kind → payload schema（不含 'point'）
    def tables(self) -> Sequence[type[Base]]                        # 擁有的 ORM
    def on_match_start(self, session, match, participants) -> None
    def on_match_requeued(self, session, match) -> None                 # undo-completion 把替補比賽退回佇列時清外掛狀態
    def on_spine_event(self, session, ctx: SpineEventContext) -> SpineEffect
    def can_undo(self, session, match) -> bool                          # /undo 前詢問；預設 True，net_rally 回 False
    def apply_event(self, session, ctx: PluginEventContext) -> PluginEventResult   # /events
    def after_undo(self, session, match) -> None
    def live_state(self, session, match) -> dict | None
    def match_wins(self, x, y, params) -> bool                       # 預設委派核心 scoring.match_wins
    def load_stat_inputs(self, session, matches) -> Mapping[UUID, Any]
    def match_detail(self, match, inputs) -> tuple[dict, list[Section]]   # (羽球專屬頂層欄位, sections)
    def dashboard_metric_specs(self) -> Sequence[MetricSpecView] | None
    def dashboard_sections(self, samples, filters) -> list[Section]
    def share_highlights(self, detail) -> list[dict]
    def estimate_minutes(self, params) -> float
```

`Section = {kind: str, title_key: str | None, data: Any | None}`。核心的 `Section` 型別與 `SpineEffect`／`SpineEventContext` 定義在 `app/sports/presentation.py` 與 `app/sports/plugin.py`；外掛只能匯入這兩個模組、`app.domains.*.models`、`app.sports.scoring`，不得匯入核心 service（Decision 15）。

## 11. 前端型別（節錄）

- `SportTypeModule { typeKey; surfaces: { scoreboard, controlPanel, allCourtsBlock, courtControl, createFormFields }; sectionKinds: Record<string, Type<SectionComponent>>; shareHighlights?: (detail) => Highlight[] }`
- `SectionComponent { section: InputSignal<Section>; context: InputSignal<SectionContext> }`
- `SportSummary`、`Section`、`SportsCatalogResponse`、`ActivitySummary` 與後端一對一。
- `CourtLiveState.current_match.sport_state: unknown | null`、`cap_score: number | null`（`isMatchPoint` 需處理 null cap）。
