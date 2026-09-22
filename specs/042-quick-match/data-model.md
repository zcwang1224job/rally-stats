# Data Model: 快速開始比賽（042-quick-match）

**Plan**: [plan.md](./plan.md) | **Research**: [research.md](./research.md)

一支 migration（接在 `b7e2d4a9c130` 之後）：`groups` 加一欄、新表 `quick_match_slots`、`system_config` 加兩列。純新增、既有資料零變動、可 downgrade。所有時間欄位 `TIMESTAMPTZ`、UTC。

## 1. `groups`（擴充）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `kind` | `VARCHAR(16) NOT NULL DEFAULT 'normal'` | `normal` \| `quick`。migration 以 `server_default='normal'` 回填既有列。 |

索引：`ix_groups_kind_status (kind, status)`——sweep 與「我的團／開團列表排除」都以這兩欄過濾。

快速比賽（`kind='quick'`）的列固定為：

| 欄位 | 值 | 理由 |
|---|---|---|
| `name` | `"快速比賽"`（後備值，畫面一律依 `kind` 換語系標籤） | `varchar(30)`；不接受使用者輸入 |
| `scheduling_mechanism` | `manual` | research Decision 3 |
| `match_mode` | `singles` \| `doubles` | 表單選擇 |
| `max_members` | 2（單打）\| 4（雙打） | FR-003；`join_group()` 的人數上限據此擋多餘的加入 |
| `password_ciphertext` | `NULL` | 不設密碼 |
| `admin_pin_hash` | 隨機 PIN 的雜湊 | 欄位 NOT NULL；PIN **不回傳**，僅供既有「忘記 PIN」流程（登入建立者）取回 |
| `scoring_mode / target_score / deuce_threshold / cap_score` | 表單選擇（preset 或自訂） | 與開團相同驗證 |
| `detailed_scoring_enabled` | 表單選擇 | |
| `scoreboard_scoring_enabled` | `false` | 不提供切換（spec Assumptions） |
| `auto_next_round / continuous_rotation` | `false` | 手動排程 |
| `current_round_number` | `1`（建立時寫一列 `round_history`） | 之後不換輪 |
| `created_by_member_id` | 建立者會員或 `NULL` | 「忘記 PIN」、FR-021 首頁橫幅、換人再打挑好友的授權依據 |
| `status` | `active` → `disbanded`（結束／取消／閒置收尾） | 「已收尾」＝`disbanded`，無新狀態 |

## 2. `quick_match_slots`（新）

一次快速比賽**目前名單**的每一個位置。建立時寫入；「換人再打」整組重寫（舊列刪除）；「再打一場」只交換 `team`。不對外呈現。

| 欄位 | 型別 | 說明 |
|---|---|---|
| `id` | `UUID PK` | |
| `group_id` | `UUID NOT NULL FK groups.id ON DELETE CASCADE` | 所屬快速比賽 |
| `team` | `CHAR(1) NOT NULL` | `A` \| `B` |
| `position` | `SMALLINT NOT NULL` | 1 或 2（單打只有 1） |
| `source` | `VARCHAR(8) NOT NULL` | `self`（建立者本人，A1 固定）\| `friend` \| `guest` |
| `nickname` | `VARCHAR(20) NOT NULL` | 顯示用；好友位置為該好友暱稱的快照 |
| `member_id` | `UUID NULL FK members.id` | `self`／`friend` 有值 |
| `invite_id` | `UUID NULL FK group_invites.id` | `friend` 且尚未回應時有值 |
| `roster_entry_id` | `UUID NULL FK roster_entries.id` | `ready` 時必有值 |
| `status` | `VARCHAR(8) NOT NULL` | `pending` \| `ready` |
| `expires_at` | `TIMESTAMPTZ NULL` | `pending` 時＝建立時間＋`quick_match_invite_timeout_seconds` |
| `created_at` | `TIMESTAMPTZ NOT NULL` | |

約束：`UNIQUE (group_id, team, position)`；`CHECK (status <> 'ready' OR roster_entry_id IS NOT NULL)`；索引 `ix_quick_match_slots_pending (group_id) WHERE status = 'pending'`（sweep 用）。

### 位置的狀態轉移

```
guest / self ──建立時 join_group()──▶ ready
friend ──建立時 send_invite()──▶ pending ──好友接受(join_group 成功)──▶ ready(member_id 保留)
                                          ├─拒絕 / 逾時 / 「不等了」 / 好友在別團──▶ ready(轉為訪客：source='guest', member_id=NULL,
                                          │                                              invite→invalidated, join_group(member=None))
                                          └─建立者「取消」──▶ 整個快速比賽收尾（列隨 group 保留，invite→invalidated）
```

「全部位置 `ready`」是唯一的開賽條件；判定與開賽在同一交易內、對 `groups` 列取 `FOR UPDATE`，避免兩位好友同時接受各開一場。

## 3. 沿用的表（不改結構）

| 表 | 用法 |
|---|---|
| `courts` | 每次快速比賽固定一列（`name` 用 `default_court_name`），`scoreboard_token`／`control_panel_token` 即使用者拿到的兩個連結 |
| `roster_entries` | 建立者 `is_creator=true`（會員有 `member_id`；訪客建立者＝A1，發 `guest_session_token`）；訪客位置各一列（含 `guest_session_token`，028 綁定入口）；好友接受後由 `join_group()` 建立；「換人再打」被換掉的人走 `handle_member_left(new_status='left')` |
| `matches` / `match_participants` / `score_events` / `score_serve_records` / `shot_placement_records` / `pair_history` | 完全沿用；`round_number` 固定 1 |
| `round_history` | 建立時一列 `(group_id, 1)` |
| `group_invites` | 好友位置的邀請列：`inviter_member_id` = 建立者、狀態沿用 `pending | accepted | declined | invalidated | cancelled` |
| `notifications` | `type = 'quick_match_invite'`、`source_id = invite_id`；既有唯一鍵 `(type, source_id, member_id)` 自然去重 |
| `system_config` | 新列 `quick_match_invite_timeout_seconds`（`'120'`）、`quick_session_idle_minutes`（`'60'`，與一般團相同） |

## 4. 快速比賽的整體狀態（推導，不儲存）

| 狀態 | 判定 | 使用者看到 |
|---|---|---|
| `waiting` | `status='active'` 且存在 `pending` 位置 | 等待畫面（每位好友的回應狀態、「不等了」、「取消」） |
| `playing` | `status='active'`、無 `pending`、場地有 `in_progress` 比賽 | 控制板計分 |
| `idle` | `status='active'`、無 `pending`、場地無進行中比賽 | 控制板的「再打一場／換人再打／結束」 |
| `closed` | `status='disbanded'` | 「這場快速比賽已結束」 |

`GET /quick-matches/by-token/{control_token}` 回傳這個推導值（`state`），前端不自行推論。

## 5. 既有回應的新增欄位（皆具預設值，舊欄位不動）

| 回應 | 新欄位 |
|---|---|
| `CourtByTokenResponse`、`CourtStateResponse` | `group_kind: 'normal' \| 'quick'` |
| `MemberMatchRecordSummary`、`MemberMatchRecordDetail`、好友對戰紀錄列、`MemberGroupHistoryResponse`、`MyGroupSummary` | `group_kind` |
| `GroupInviteDetail`（`GET /group-invites/{id}`）、`NotificationSummary.quick_match_invite`（新的 detail 物件） | `group_kind`、`match_mode`、`inviter_nickname` |
| `POST /group-invites/{id}/accept` 回應 | `scoreboard_token: UUID \| null`（快速比賽時有值） |
| 錯誤 `ALREADY_ACTIVE_IN_ANOTHER_GROUP` 的 `detail` | `group_kind` |

## 6. 驗證規則（來自 FR-003／FR-006／FR-013／FR-030）

- 位置數：單打 2、雙打 4，A1 固定為建立者本人（會員）或第一位訪客（訪客建立者）。
- 暱稱：非空、去頭尾空白、≤ 20 字；同一場內暱稱（含好友暱稱快照）不得重複；同一好友不得出現兩次；好友不得是建立者本人。
- 自訂計分制：沿用 `group/schemas.py` 的 `deuce_threshold ≤ target_score`、`cap_score ≥ deuce_threshold`。
- 換人再打：建立者為會員時 `self` 位置不可移除、不可改暱稱；已 `ready` 且仍在名單的好友保留其 `roster_entry_id`，不重發邀請；可切換單雙打（位置數隨之變）。
- 再打一場：名單不變、`team` 對調；上一場為 `abandoned` 亦允許。
