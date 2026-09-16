# Phase 1 Data Model: 落點詳細計分模式

## 既有實體的變更

### `Group`（`apps/api/app/domains/group/models.py`）

新增欄位：

| 欄位 | 型別 | 說明 |
|---|---|---|
| `detailed_scoring_enabled` | `Boolean NOT NULL DEFAULT false` | 該團之後建立的比賽要用「詳細計分模式」還是既有「簡易（+1/-1）」；比照既有 `scoreboard_scoring_enabled` 的即時切換模式（research.md Decision 5），非樂觀鎖表單欄位。 |

### `Match`（`apps/api/app/domains/schedule/models.py`）

新增欄位：

| 欄位 | 型別 | 說明 |
|---|---|---|
| `detailed_scoring_enabled` | `Boolean NOT NULL` | 比賽建立當下由 `group.detailed_scoring_enabled` 快照而來（比照既有 `target_score`/`deuce_threshold`/`cap_score` 三個快照欄位），決定這場比賽整場都使用哪一種計分介面；建立後不再隨團設定變更而改變（FR-006）。既有資料列以 migration 的 `server_default=false` 回填（比照既有簡易模式，新功能上線前建立的比賽視為簡易模式）。 |

## 新實體

### `ShotPlacementRecord`（新表 `shot_placement_records`，`apps/api/app/domains/schedule/models.py`）

附屬於既有「得分事件」（`ScoreEvent`）的延伸資訊，只在詳細計分模式下、`delta > 0` 的加分動作才會產生；每一次得分各自獨立一筆，彼此不覆蓋（FR-008）。

| 欄位 | 型別 | 說明 |
|---|---|---|
| `id` | `UUID` (PK) | |
| `score_event_id` | `UUID` (FK → `score_events.id`, `UNIQUE`, `ON DELETE CASCADE`) | 一對一對應到產生這筆落點紀錄的加分事件；比照既有 `ScoreServeRecord`（030）同一欄位的做法。 |
| `match_id` | `UUID` (FK → `matches.id`, `ON DELETE CASCADE`, indexed) | 冗餘欄位，避免每次查詢都要 join `score_events`（比照 `ScoreServeRecord` 慣例）。 |
| `group_id` | `UUID` (FK → `groups.id`, indexed) | 冗餘欄位，供跨團查詢隔離（比照 `ScoreServeRecord` 為修正 029/030 分析發現 I1 而新增的既有慣例）。 |
| `roster_entry_id` | `UUID` (FK → `roster_entries.id`) | 計分員選擇的得分球員。 |
| `team` | `String(1)`（`"A"` 或 `"B"`） | 冗餘欄位，等於 `roster_entry_id` 所屬隊伍，避免每次查詢都要 join `match_participants` 才能知道是哪一隊得分。 |
| `landing_x` | `Float NOT NULL` | 落點座標，`x` 軸（research.md Decision 1：`0`=A 隊底線、`1`=B 隊底線、`0.5`=球網）；有效範圍 `[-0.3, 1.3]`，允許代表出界。 |
| `landing_y` | `Float NOT NULL` | 落點座標，`y` 軸（`0`/`1` 分別代表兩側邊線）；有效範圍同上。 |
| `created_at` | `TIMESTAMPTZ NOT NULL DEFAULT now()` | |

**Validation rules**（後端寫入前驗證，FR-004/FR-010/Constitution X）：
- `roster_entry_id` MUST 是 `match_id` 這場比賽的既有參賽者（`match_participants` 其中一筆），否則拒絕（`PARTICIPANT_NOT_IN_MATCH`，422）。
- `landing_x`/`landing_y` MUST 落在 `[-0.3, 1.3]`，否則拒絕（`INVALID_LANDING_COORDINATES`，422）。
- 只有目標比賽 `matches.detailed_scoring_enabled = true` 時才允許寫入，否則拒絕（`DETAILED_SCORING_NOT_ENABLED`，422）——伺服器端強制，不只是前端隱藏按鈕（Constitution X）。

**Lifecycle**：
- 建立：`apply_score_delta()` 的 `delta > 0` 分支，當呼叫端（`apply_detailed_score()`）提供 `shot_placement` 參數時，與該次 `ScoreEvent` 同一交易寫入。
- 刪除（單筆）：`apply_score_delta()` 的 `delta < 0` 分支，刪除該 `match_id`+`team` 最新一筆（`ORDER BY created_at DESC LIMIT 1`），對應 FR-007「修正比分同時收回最後一筆」；無記錄時為 no-op（簡易模式比賽恆為此情況）。
- 刪除（連帶）：`matches`/`score_events` 被刪除時透過 `ON DELETE CASCADE` 連帶刪除（比照 `score_serve_records` 既有慣例）；比賽被捨棄（`abandoned`）不觸發任何 `DELETE`，已寫入的紀錄不受影響（FR-009）。
- 不可變：一旦寫入，除了上述「刪除」動作外，MUST NOT 被任何其他動作更新／覆蓋（FR-008）。

## 關聯圖

```text
Group 1───* Match 1───* ScoreEvent 1───0/1 ShotPlacementRecord
                                    └──0/1 ScoreServeRecord（030，既有、獨立）
                    Match 1───* MatchParticipant *───1 RosterEntry
                                                       ▲
                                    ShotPlacementRecord.roster_entry_id ─┘
```

`ShotPlacementRecord` 與 030 既有的 `ScoreServeRecord` **各自獨立、平行存在**——兩者都掛在同一個 `ScoreEvent` 上（`score_event_id` 各自的 1:0/1 關聯），互不依賴、互不覆蓋，呼應 spec Assumptions「029/030 既有邏輯 MUST 照常運作」。
