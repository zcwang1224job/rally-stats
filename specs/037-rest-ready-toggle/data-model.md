# Data Model: 休息／準備切換

決策依據見 [research.md](./research.md)。一支 migration（接在 `b5c8e2f41a07` 之後）：兩個新欄位、一張新表。既有欄位與既有資料零變動。

## 儲存變更

### `roster_entries`（既有，新增兩欄）

| 欄位 | 型別 | 預設 | 說明 |
|---|---|---|---|
| `resting_since` | `TIMESTAMPTZ NULL` | `NULL` | `NULL`＝準備中；有值＝休息中，值為開始休息的時間（UTC）。research Decision 1。 |
| `played_credit` | `INTEGER NOT NULL` | `0` | 只用於排程優先順序的「視同已打場數」。只增不減。research Decision 4。 |

- 既有列回填：`resting_since = NULL`、`played_credit = 0`——上線當下所有人都是準備中，排程行為與上線前完全相同。
- 不需要新索引：所有讀取都已先以 `group_id`（既有索引）縮到單一團，一團的名單上限為數十列。
- `status`（`active | left | kicked`）與 `wait_count` 的定義不變。`wait_count` 在休息期間不被任何路徑修改（research Decision 2）。

### `roster_rest_periods`（新）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `id` | `UUID PK` | |
| `roster_entry_id` | `UUID NOT NULL FK → roster_entries.id` | 索引。 |
| `group_id` | `UUID NOT NULL FK → groups.id` | 索引。冗餘欄位，讓 `_get_player_histories()` 以一個 `WHERE group_id = …` 載入整團的區間，不必 join。 |
| `started_at` | `TIMESTAMPTZ NOT NULL` | 取自當時的 `resting_since`。 |
| `ended_at` | `TIMESTAMPTZ NOT NULL` | 切回準備中的時間。`CHECK (ended_at >= started_at)`。 |

- 只存**已結束**的區間；進行中的休息由 `roster_entries.resting_since` 表示，兩者不重疊、不重複。
- 只有一個寫入點：`set_rest_state()` 切回準備中時。沒有更新、沒有刪除。
- 不對外呈現（不出現在任何回應裡）；唯一的讀取者是 `_get_player_histories()`。

## 狀態轉移

```text
                 set_rest_state(resting=true)
   ┌──────────┐ ─────────────────────────────▶ ┌──────────┐
   │  準備中   │                                │  休息中   │
   │ (NULL)   │ ◀───────────────────────────── │ (since)  │
   └──────────┘   set_rest_state(resting=false) └──────────┘
        ▲            ├─ 寫入 roster_rest_periods
        │            ├─ played_credit += max(0, 目標 − 有效場數)
   新加入／重新加入    └─ 走中途加入者流程（research Decision 8）
```

- 設定為已經是的狀態＝no-op（冪等），不寫入區間、不調整 credit、不發事件。
- 離開／被踢：`status` 改變，`resting_since` 原樣留著但不再被任何查詢讀到。進行中的那段休息不寫入 `roster_rest_periods`（他已不在排程裡，沒有人會讀）。
- 換輪、重新整理、斷線重連：不影響狀態（FR-005）。

## 推導規則（不儲存）

### 有效場數與 `played_credit`（純函式 `returning_played_credit()`）

```text
有效場數(p) = 實際上場過的場數(p) + played_credit(p)
目標       = 其他「active 且準備中」球員的有效場數的下中位數      （沒有其他人 → 不調整）
增加量     = max(0, 目標 − 有效場數(本人))
```

- 「實際上場過的場數」與 `PlayerHistory.played` 同一個定義（上過場的比賽，含打到一半被中止者）。
- 下中位數：排序後取第 `(n − 1) // 2` 個（0 起算）。整數進、整數出。
- `_get_player_histories()` 回傳的 `played` 一律為有效場數——這是 credit 進入排程的唯一入口。從沒上過場的人不在回傳結果裡（維持「沒有紀錄＝從未上場」的既有語意），其 credit 在他第一次上場後才開始作用。

### 坐著等的場數（純函式 `player_histories()` 的新參數）

```text
rest(p) = 上一場結束之後上場的比賽數
          − 其中上場時間落在 p 的任一休息區間 [start, end) 內的比賽數
```

- 區間來源：`roster_rest_periods` 的已結束區間，加上進行中的 `(resting_since, None)`（`None`＝到現在）。
- 在場上時按休息：區間從按下那一刻開始，但 `rest` 本來就從「上一場結束」起算，兩者取交集，結果正確。
- `played` 與 `run` 的算法不變。

### 場次因休息受到的影響（`rest_effect`）

只對 `status == "queued"` 且至少一位參賽者休息中的場次有值：

| 排程方式 | `rest_effect` | 意義 |
|---|---|---|
| 公平輪替（雙打）、個人全混搭循環賽 | `"substitute"` | 輪到它而人還在休息時，由替補上場。 |
| 公平輪替（單打＝單打循環）、固定搭檔循環賽 | `"held"` | 保留，等休息者回來；換輪時取消。 |
| 手動安排 | — | 沒有排隊中的場次。 |

### 這一輪是否被休息卡住（`round_is_stalled_by_rest()`）

下列全部成立：當前這一輪沒有 `in_progress` 的比賽；至少有一場 `queued`；每一場 `queued` 都含休息中的球員；`_choose_next_queued_match()` 回傳 `None`（替補模式下代表找不到替補）。

### 場地等待原因（`waiting_reason` 的兩個新值）

| 值 | 條件 |
|---|---|
| `held_for_rest` | 場地閒置、當前這一輪還有 `queued` 的場次、但 `_choose_next_queued_match()` 回傳 `None`，且那些場次全部含休息中的球員。 |
| `not_enough_ready` | 場地閒置、沒有 `queued` 的場次、連續輪轉適用、閒置且準備中的球員不足 4 人、且名單上有人休息中。 |

其餘情況維持既有的 `no_queued_match`／`manual_assignment`。

## 回應 schema 的新增欄位（皆有預設值，舊前端不受影響）

詳見 [contracts/schedule-api-additions.md](./contracts/schedule-api-additions.md)。

| Schema | 新欄位 |
|---|---|
| `RosterScheduleStatus` | `resting: bool = False`、`resting_since: datetime \| None = None`、`partner_roster_entry_id: str \| None = None` |
| `NextUpPreview` | `substitutions: list[SubstitutionPreview] = []` |
| `RoundMatchSummary` | `rest_effect: Literal["held", "substitute"] \| None = None` |
| `RoundMatchesResponse` | `waiting_on_rest: WaitingOnRest \| None = None` |
| `WaitingReason` | 加入 `"held_for_rest"`、`"not_enough_ready"` |

新 schema：`RestStateRequest`、`RestStateResponse`（見 [contracts/rest-state-api.md](./contracts/rest-state-api.md)）、`SubstitutionPreview { resting: RosterSummary, substitute: RosterSummary }`、`WaitingOnRest { match_count: int, players: list[RosterSummary], stalled: bool }`。

## 驗證規則

- 目標列 MUST 屬於路徑上的 `group_id` 且 `status == "active"`，否則 `ROSTER_ENTRY_NOT_FOUND`（404）。
- 本人端點：MUST 證明擁有該列（訪客 token 相符，或會員身分相符）；任何不符一律 `ROSTER_ENTRY_NOT_FOUND`，與「不存在」無法區分。
- 管理員端點：`require_admin`（該團的管理員 JWT）。
- 團已解散：`GROUP_DISBANDED`（409）。
- **會使這一輪立刻結束的休息**（FR-031～FR-033）：`resting: true`、生效後會立刻自動換輪、而 `confirm_round_end` 不為 `true` → `REST_ENDS_ROUND`（409，`detail.matches_to_cancel`），交易 rollback、不留下任何變更。判斷發生在授權檢查**之後**。判斷式＝`check_round_complete_and_maybe_auto_advance()` 實際用來決定換輪的同一個函式（新：`round_would_auto_advance(session, group) -> bool`，供兩邊呼叫）。新錯誤代碼一個：`REST_ENDS_ROUND`。
- 沒有頻率限制（spec Assumptions）。

## 名單讀取函式的分工（research Decision 2）

| 函式 | 回傳 | 誰用 |
|---|---|---|
| `_get_active_roster_for_selection()`、`_get_active_roster_ids()` | active **且準備中** | 整輪產生、連續輪轉（全部呼叫端都是挑人上場） |
| `_get_ready_roster_ordered()`（新） | active **且準備中** | 自動搭檔當輪組隊、手動搭檔當輪隊伍與自動補位、中途加入者流程、替補候選、017 臨時配對預覽 |
| `_get_active_roster_ordered()`（不變） | active（含休息中） | 建立正式 `Partnership`：切到固定搭檔時、新成員加入時（FR-034） |
