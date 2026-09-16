# Phase 1 Data Model: 對戰紀錄逐點得失分球員與落點資訊、球員得失分統計

本功能**不新增、不修改任何 SQLAlchemy model 或資料表欄位**——純粹讀取既有的 `ShotPlacementRecord`（031/032-shot-placement-scoring 已建立）、`ScoreEvent`（007 已建立）、`MatchParticipant`/`RosterEntry`（既有）。以下只記錄新增的 **API 回應 schema**（Pydantic，`apps/api/app/domains/group/schemas.py`）與對應的前端 TypeScript interface（`apps/web/src/app/core/api/group-member-view.models.ts`）。

## 既有實體（唯讀依賴，不修改）

| 實體 | 用途 |
|---|---|
| `ScoreEvent`（`apps/api/app/domains/schedule/models.py`） | 既有的每一次 +1/-1 加減分事件；本功能依 `id` 找出其對應的 `ShotPlacementRecord`（若有）。 |
| `ShotPlacementRecord`（`apps/api/app/domains/schedule/models.py`，031/032 已建立） | 見 research.md——`score_event_id`（1:0/1 對應）、`roster_entry_id`（得分球員，可為 `NULL`）、`losing_roster_entry_id`（失分球員，可為 `NULL`）、`landing_x`/`landing_y`（落點座標，兩者要嘛同時有值要嘛同時為 `NULL`）、`team`（永遠有值，等於該次得分的隊伍）。本功能是第一個讀取此表的「查看」畫面。 |
| `MatchParticipant`/`RosterEntry`（既有） | 提供 `roster_entry_id` → 暱稱的對應（`ParticipantSummary.nickname`，已經是 `MatchRecordDetailResponse.team_a`/`team_b` 既有回傳內容的一部分）。 |

## 新增 Schema（回應擴充，`apps/api/app/domains/group/schemas.py`）

### `ShotPlacementSummary`（新增）

巢狀掛在 `ScoreEventSummary.detail` 底下（research.md Decision 1），描述單一加分事件「當時記錄了什麼」。

| 欄位 | 型別 | 說明 |
|---|---|---|
| `scoring_roster_entry_id` | `str \| None` | 得分球員的 `roster_entry_id`；當時未選擇則為 `None`。 |
| `scoring_nickname` | `str \| None` | 得分球員暱稱，與上一欄位同時有值或同時為 `None`（後端組裝時一併查出，前端不需另外查詢）。 |
| `losing_roster_entry_id` | `str \| None` | 失分球員的 `roster_entry_id`；當時未選擇則為 `None`。 |
| `losing_nickname` | `str \| None` | 失分球員暱稱，與上一欄位同時有值或同時為 `None`。 |
| `landing_x` | `float \| None` | 落點座標 x 軸；未記錄則為 `None`（與 `landing_y` 同時有值或同時為 `None`，沿用 `ShotPlacementRecord` 既有的資料庫層保證）。 |
| `landing_y` | `float \| None` | 落點座標 y 軸；未記錄則為 `None`。 |

### `ScoreEventSummary`（既有 schema 擴充）

新增一個欄位：

| 欄位 | 型別 | 說明 |
|---|---|---|
| `detail` | `ShotPlacementSummary \| None`（預設 `None`） | 見 research.md Decision 2：`delta = -1` 的扣分事件、非詳細計分模式比賽的加分事件、或對應 `ShotPlacementRecord` 四個欄位全部是 `NULL`（全空確認）的加分事件，一律為 `None`；其餘情況為非 `None` 的 `ShotPlacementSummary`（其中個別欄位仍可能是 `None`，由前端逐欄位判斷是否顯示）。 |

既有欄位（`side`、`delta`、`score_a`、`score_b`、`elapsed_seconds`）不變。

### `PlayerScoringStat`（新增）

`MatchRecordDetailResponse.player_stats` 陣列中的單一元素，代表這場比賽中一位參賽球員的得失分統計。

| 欄位 | 型別 | 說明 |
|---|---|---|
| `roster_entry_id` | `str` | 該球員的 `roster_entry_id`（來自這場比賽既有的 `team_a`/`team_b` 名單）。 |
| `nickname` | `str` | 該球員暱稱。 |
| `team` | `Literal["A", "B"]` | 該球員所屬隊伍（`team_a` 或 `team_b`）。 |
| `scored_count` | `int` | 這場比賽中，這位球員被記錄為「得分球員」的加分事件次數（research.md Decision 3：只計算 `ShotPlacementRecord.roster_entry_id` 等於此球員的資料列數）。 |
| `fault_count` | `int` | 這場比賽中，這位球員被記錄為「失分球員」的加分事件次數（只計算 `ShotPlacementRecord.losing_roster_entry_id` 等於此球員的資料列數）。 |

### `MatchRecordDetailResponse`（既有 schema 擴充）

新增一個欄位：

| 欄位 | 型別 | 說明 |
|---|---|---|
| `player_stats` | `list[PlayerScoringStat]`（預設 `[]`） | 見 research.md Decision 4：空陣列代表整場比賽完全沒有任何一筆 `ShotPlacementRecord` 的 `roster_entry_id`/`losing_roster_entry_id` 有值（觸發 FR-008 的無資料提示）；非空陣列必定包含這場比賽 `team_a`/`team_b` 名單中的**全部**參賽者（含次數皆為 0 的球員，FR-009），依 `team_a` 全部球員在前、`team_b` 全部球員在後、各自維持原參賽名單順序排列。 |

既有欄位（`record_completeness`、`events`，以及繼承自 `MatchRecordSummary` 的 `match_id`/`round_number`/`team_a`/`team_b`/`score_a`/`score_b`/`winner_team`/`started_at`/`ended_at`）不變。

## 組裝邏輯（`build_match_record_detail()` 擴充，`apps/api/app/domains/group/service.py`）

在既有查詢 `ScoreEvent`（依 `match_id`）之後，新增：

1. 一次查詢該場比賽全部的 `ShotPlacementRecord`（`WHERE match_id = :match_id`，既有索引），並用兩次額外的 `RosterEntry` 查詢（或一次 join）把 `roster_entry_id`/`losing_roster_entry_id` 換成暱稱——沿用 `_build_match_record_summaries()` 既有「先查 id 集合、再一次查暱稱」的既有模式，避免 N+1。
2. 依 `score_event_id` 建立一個 dict 索引，組裝每筆 `ScoreEventSummary` 時查表決定其 `detail`（依 research.md Decision 2 的規則：四個欄位全空 → `None`）。
3. 對同一批 `ShotPlacementRecord` 分別依 `roster_entry_id`（非 `NULL` 者）與 `losing_roster_entry_id`（非 `NULL` 者）分組計數，得到兩個 `dict[roster_entry_id, int]`。
4. 若兩個 dict 合計為空（完全沒有任何一筆有值的欄位）→ `player_stats = []`；否則遍歷這場比賽既有的 `team_a + team_b` 參賽名單，依序組出每位球員的 `PlayerScoringStat`（`scored_count`/`fault_count` 取自上一步的 dict，缺項預設 0）。

此函式目前是四個既有端點（`GET /groups/{group_id}/match-records/{match_id}`、`GET /members/me/match-records/{match_id}`、`GET /members/{member_id}/match-records/{match_id}`、好友檢視變體）的唯一共用組裝入口，本次擴充自動套用到全部四處，不需要個別修改任何一個端點。

## 前端對應 TypeScript interface（`apps/web/src/app/core/api/group-member-view.models.ts`）

```typescript
export interface ShotPlacementDetail {
  scoringRosterEntryId: string | null;
  scoringNickname: string | null;
  losingRosterEntryId: string | null;
  losingNickname: string | null;
  landingX: number | null;
  landingY: number | null;
}

export interface ScoreEventSummary {
  side: Team;
  delta: 1 | -1;
  score_a: number;
  score_b: number;
  elapsed_seconds: number;
  detail: ShotPlacementDetail | null; // 新增
}

export interface PlayerScoringStat {
  rosterEntryId: string;
  nickname: string;
  team: Team;
  scoredCount: number;
  faultCount: number;
}

export interface MatchRecordDetailResponse extends MatchRecordSummary {
  record_completeness: 'complete' | 'partial' | 'none';
  events: ScoreEventSummary[];
  player_stats: PlayerScoringStat[]; // 新增
}
```

（沿用既有檔案風格：巢狀物件內部欄位採 camelCase 命名，頂層與後端 JSON 直接對應的欄位維持既有的 snake_case——比照既有 `ScoreEventSummary`/`MatchRecordSummary` 目前的命名慣例，本次不重新命名既有欄位。）

## 關聯圖

```text
Match 1───* ScoreEvent 1───0/1 ShotPlacementRecord（既有資料，本功能唯讀）
                                              │
                            roster_entry_id ──┼── losing_roster_entry_id
                                              ▼                ▼
                                         RosterEntry      RosterEntry
                                       （得分球員暱稱）   （失分球員暱稱）

MatchRecordDetailResponse
├── events: ScoreEventSummary[]
│     └── detail: ShotPlacementSummary | None   ← 逐筆對應同一場比賽的 ShotPlacementRecord
└── player_stats: PlayerScoringStat[]           ← 對同一批 ShotPlacementRecord 依欄位分組加總
```
