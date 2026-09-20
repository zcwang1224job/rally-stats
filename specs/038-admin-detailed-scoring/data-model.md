# Phase 1 Data Model: 管理頁分數控制板支援比賽詳細設定

**Feature**: 038-admin-detailed-scoring | **Date**: 2026-09-20

## 資料庫層：零變更

本功能**不新增資料表、不新增欄位、不需要 Alembic migration**。所有資料結構在 031（shot-placement-scoring）、032（score-then-record / cancel-score）、035（point-ending-type）已經建立完成：

| 既有結構 | 用途 | 本功能的關係 |
|---|---|---|
| `groups.detailed_scoring_enabled` | 團層級開關 | 唯讀，不改 |
| `matches.detailed_scoring_enabled` | 比賽建立當下的**設定快照**（憲章原則 III） | 唯讀，本功能新增的傳輸欄位就是把它送到管理頁 |
| `score_events` | 每個 `+1` 產生一筆；`id` 即 `score_event_id` | 唯讀，由既有加分流程產生 |
| `shot_placement_records` | 掛在某個 `score_event` 上的落點／球員／結束方式 | 由既有的管理員端點寫入，不改結構 |

## 傳輸層：一個新欄位

### `MatchSummary`（排程快照中的「這個場地正在打的比賽」）

**後端** `apps/api/app/domains/schedule/schemas.py`：

| 欄位 | 型別 | 狀態 | 說明 |
|---|---|---|---|
| `match_id` | `str` | 既有 | |
| `status` | `str` | 既有 | |
| `participants` | `list[ParticipantSummary]` | 既有 | 詳細視窗列球員用 |
| `score_a` / `score_b` | `int` | 既有 | |
| `serve` | `ServeStationInfo \| None` | 既有 | 詳細視窗判斷發球失誤用 |
| **`detailed_scoring_enabled`** | **`bool`** | **新增**，預設 `False` | **這場比賽**的快照值，非團的當下設定 |

**來源**：`service.build_schedule_snapshot()` 中唯一的 `MatchSummary(...)` 建構點，填 `entry[0].detailed_scoring_enabled`（`entry[0]` 是 `Match` ORM 物件）。

**預設值 `False` 的意義**：舊版前端讀不到這個欄位時視為關閉，行為退回一鍵加分——與 `serve`、`substitutions` 等既有欄位同一套向後相容約定。

**前端** `apps/web/src/app/features/group-admin/schedule-management/schedule.models.ts` 的 `MatchSummary` 同步新增 `detailed_scoring_enabled: boolean`。

### `ScoreMutationResult`（加分／減分／結束的回應）

後端**已有** `score_event_id: str | None`，但前端 `schedule.models.ts` 的對應介面**漏了**這個欄位。

| 欄位 | 型別 | 後端 | 前端 |
|---|---|---|---|
| `applied` / `match_id` / `status` / `score_a` / `score_b` / `winner_team` / `serve` | — | ✅ | ✅ |
| **`score_event_id`** | `string \| null` | ✅ 既有 | **補上** |

前端補這個欄位是純型別對齊，後端不需要動。

## 前端元件狀態（`CourtControlComponent`）

本功能在元件內新增的狀態，全部是既有模式的照搬（見 research.md Decision 1）：

| 狀態 | 型別 | 用途 | FR |
|---|---|---|---|
| `frozenCourt` | `signal<CourtScheduleStatus \| null>` | 視窗開啟期間忽略輸入更新 | FR-011 |
| `displayCourt` | `computed<CourtScheduleStatus \| null>` | `frozenCourt() ?? court()`，模板唯一顯示來源 | FR-011、FR-012 |
| `pendingPoint` | `PendingPoint \| null` | 這一分的狀態機：等 `score_event_id`、排隊使用者動作 | FR-002、FR-017 |
| `pickerOpen` | `boolean` | 視窗是否開著 | FR-011 |
| `pendingScoringSide` | `signal<Team>` | 視窗的 `scoringTeam` 輸入 | FR-004 |
| `pendingServingTeam` | `signal<Team \| null>` | 這一回合的發球方，**在加分前**擷取 | FR-004 |
| `pendingServingScore` | `signal<number \| null>` | 發球方加分前的自己分數（奇偶決定發球區） | FR-004 |
| `pendingServingRosterEntryId` | `signal<string \| null>` | 這一回合的發球員（發球失誤時預選為失分者） | FR-004 |
| `cancelScoreErrorKey` | `signal<string \| null>` | 取消失敗的語系 key | FR-009 |
| `scoreGuard` | `ScoreTapGuard` | 一次一個計分請求 + 冷卻 | FR-013 |

`PendingPoint` 與 `ScoreTapGuard` 是 `apps/web/src/app/features/shot-placement/` 下的既有類別，直接引用，不修改。

### `PendingPoint` 狀態轉移（既有行為，此處僅記錄以供測試對照）

```text
建立（按下 +）
   │  scoreEventId = null
   ├──► 使用者在拿到 score_event_id 前按了 確認/取消 → 動作排隊（queued）
   │
   ▼ 加分回應抵達
resolve(score_event_id, matchCompleted)
   ├─ applied 且有 score_event_id → 有排隊動作就立刻執行
   └─ 未 applied 或無 score_event_id → abandonPoint()：關閉視窗（FR-017）

確認 → POST .../shot-placement
取消 → matchCompleted ? POST .../undo-completion : POST .../score (delta -1)
略過 → 僅關閉視窗，不發任何請求（FR-006）
```

## 不變的約束

- **快照優先**（憲章原則 III）：管理頁判斷是否開啟詳細模式，一律依 `MatchSummary.detailed_scoring_enabled`（比賽快照），**不得**改讀管理頁自己已持有的團設定 `view.detailed_scoring_enabled`。
- **伺服器為唯一可信來源**（憲章原則 X）：凍結只影響「這個元件顯示哪一份已從伺服器取得的狀態」，不產生任何本地推測的比分；視窗關閉後立即回到伺服器狀態（FR-011）。
- **詳細資料的驗證規則不在此重新定義**：欄位合法性、隊伍歸屬、重複記錄等一律由既有的 `attach_shot_placement()` 把關，前端只負責呈現錯誤。
