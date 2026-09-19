# API Contract: 賽程與輪替名單

沿用 `specs/architecture.md` §3.1 已定義的路徑草案。所有端點皆需 `Authorization: Bearer {admin_token}`（沿用 001 之 `require_admin`）。錯誤格式統一為 `{"error_code": "...", "detail": {...}}`。

## GET /groups/{group_id}/schedule

管理頁「場地控制」區塊與手動安排介面之資料來源，取代 002 US4 目前的空狀態骨架。

**Response 200**

```json
{
  "current_round_number": 3,
  "scheduling_mechanism": "fair_rotation",
  "auto_next_round": true,
  "courts": [
    {
      "court_id": "uuid",
      "name": "1號場",
      "current_match": {
        "match_id": "uuid",
        "status": "in_progress",
        "participants": [
          { "roster_entry_id": "uuid", "nickname": "小明", "team": "A" }
        ]
      },
      "waiting_reason": null
    },
    { "court_id": "uuid", "name": "2號場", "current_match": null, "waiting_reason": "manual_assignment" }
  ],
  "roster": [
    {
      "roster_entry_id": "uuid",
      "nickname": "小明",
      "status": "active",
      "wait_count": null,
      "currently_playing": false
    }
  ]
}
```

`waiting_reason`：`"manual_assignment"`（手動安排模式，等待管理員安排）、`"no_queued_match"`（演算法模式，本輪賽程表已無排隊中比賽，等待下一輪）、或 `null`（該場地目前有比賽進行中）。`roster[].currently_playing`：供手動安排選人介面即時擋下 FR-013(a)。

**錯誤代碼**：`ADMIN_TOKEN_INVALID`。

## POST /groups/{group_id}/next-round

**Request**：無 body。

**Response 200**：同 `GET .../schedule` 之結構（回傳重新產生後的最新狀態）。

同一筆交易內：悲觀鎖（`SELECT ... FOR UPDATE NOWAIT`，見 research.md #8）、依 `scheduling_mechanism` 分支捨棄目前未完成比賽並產生下一輪、`current_round_number += 1`（該團第一次呼叫本端點時例外：維持為 1，產生的就是第 1 輪，避免跳過第 1 輪直接產生第 2 輪）、發布 `match.nextRound` 至各受影響場地頻道。

**錯誤代碼**：`ADMIN_TOKEN_INVALID`、`ROUND_GENERATION_IN_PROGRESS`（409，悲觀鎖取得失敗）、`NO_COURTS_AVAILABLE`（400，FR-029 零場地防呆）。

## PATCH /groups/{group_id}/auto-next-round

**Request**

```json
{ "enabled": true }
```

**Response 200**

```json
{ "auto_next_round": true }
```

`enabled: true` 且 `scheduling_mechanism == 'manual'` 時 MUST 拒絕（FR-016 之反向情境：手動安排模式下不可啟用）。

**錯誤代碼**：`ADMIN_TOKEN_INVALID`、`AUTO_NEXT_ROUND_NOT_SUPPORTED_IN_MANUAL_MODE`（400）。

## PATCH /groups/{group_id}/continuous-rotation

（feature/schedule-fairness 新增）公平輪替雙打專用：場地打完且沒有排隊中的比賽時，立刻從不在場上的人依優先序（wait_count、上場次數少、最久沒打）排 4 位上場，列入目前這一輪，不必等所有場地打完才開下一輪。

**Request**

```json
{ "enabled": true }
```

**Response 200**

```json
{ "continuous_rotation": true }
```

`enabled: true` 且不是 `fair_rotation` + `doubles` 時 MUST 拒絕。之後切換成其他排程方式時旗標保留但不生效。

**錯誤代碼**：`ADMIN_TOKEN_INVALID`、`CONTINUOUS_ROTATION_NOT_SUPPORTED`（400）。

## feature/schedule-fairness 其他行為變更

- `GET /groups/{group_id}/schedule` 回應新增 `match_mode`、`continuous_rotation`。
- `GET /groups/{group_id}/schedule/matches` 回應新增 `remaining_count`（排隊中＋進行中場數）、`estimated_remaining_minutes`（粗估剩餘分鐘，沒有剩餘場次時為 `null`；以本團最近 30 場已完成比賽的中位時長估算，不足 3 場時以目標分數 × 0.6 分鐘估算）、`sitting_out`（本輪沒有排到任何比賽的現役成員）。清單順序改為：已上場的依上場先後，其餘依叫號順序。
- 固定搭檔人數為奇數時不再回 `FIXED_PARTNER_REQUIRES_EVEN_HEADCOUNT`：上場次數最多的一人本輪輪空（同分時最晚加入者）。
- 場地空出來時，不再固定取叫號順序第一的場次：在球員都沒有正在別場比賽的候選中，優先挑「球員休息最少者也休息最多」的場次；候選場次的球員都至少休息過 1 場時才依叫號順序。都有人還沒休息時，挑還沒休息的人較少、且他們連續上場場數較短的場次。「即將登場」預告用同一套規則。
- **休息一律以場數計，不看實際分鐘數**：某人的「休息場數」＝他上一場下場之後，又開打了幾場比賽（他在場邊看了幾場）；他還在場上時別的場地開打的比賽不算。「連續上場」＝兩場之間沒有其他比賽開打。時間戳記只用來排先後順序。雙打公平輪替與連續輪轉挑人時，同樣依序看：輪空次數（`wait_count`）→ 上場場數少者 → 休息場數多者 → 連續上場超過 2 場者優先休息 → 與已選中的人碰面次數少者。
- 回合規劃後才加入的成員，會自動補排進目前這一輪（單打：對每位尚未交手的人；固定搭檔：新成員兩兩成組後對每一隊；個人混雙：與每位成員各搭檔一次）。
- 成員離開時，公平輪替雙打與個人混雙的排隊中比賽改由本輪場次最少的人遞補；單打與固定搭檔維持作廢（每人剛好少一場，仍然公平）。
- `pair_history` 新增 `teammate_count`，並改為比賽上場時才計數（規劃了但沒打的比賽不計）；migration `b5c8e2f41a07` 以已上場的比賽重建整張表。

## GET /groups/{group_id}/partnerships

**Response 200**

```json
{
  "partnerships": [
    { "partnership_id": "uuid", "player_a": { "roster_entry_id": "uuid", "nickname": "小明" }, "player_b": { "roster_entry_id": "uuid", "nickname": "小華" } }
  ],
  "unpaired": [
    { "roster_entry_id": "uuid", "nickname": "阿強" }
  ]
}
```

**錯誤代碼**：`ADMIN_TOKEN_INVALID`、`SCHEDULING_MECHANISM_MISMATCH`（409，目前非固定搭檔循環賽模式）。

## PATCH /groups/{group_id}/partnerships

手動重新配對（FR-021）。

**Request**

```json
{ "player_a_id": "uuid", "player_b_id": "uuid" }
```

**Response 200**：同 `GET .../partnerships`（回傳更新後的完整清單）。

同一筆交易內：若兩人原本各自有搭檔，原搭檔記錄先行刪除（原搭檔各自變回落單）；建立新的 `Partnership`。

**錯誤代碼**：`ADMIN_TOKEN_INVALID`、`SCHEDULING_MECHANISM_MISMATCH`、`VALIDATION_ERROR`（`player_a_id == player_b_id`，或任一方非 active）。

## POST /courts/{court_id}/manual-assign

**Request**

```json
{ "participant_ids": ["uuid", "uuid", "uuid", "uuid"], "teams": { "uuid1": "A", "uuid2": "A", "uuid3": "B", "uuid4": "B" } }
```

`participant_ids` 長度依團的 `match_mode` 固定為 2（單打）或 4（雙打）。

**Response 201**：新建立的 `Match` 物件（`match_id`, `status: "in_progress"`, `participants`, 比賽設定快照欄位）。

同一筆交易內：FR-013 三項擋下檢查（進行中重複／已離開／同場重複）、`wait_count` 歸零、`pair_history` 累加、發布 `rotation.updated` 至該場地頻道。

**錯誤代碼**：`ADMIN_TOKEN_INVALID`、`COURT_NOT_WAITING`（409，該場地目前已有進行中比賽）、`SCHEDULING_MECHANISM_MISMATCH`（409，非手動安排模式）、`PARTICIPANT_ALREADY_PLAYING`（400）、`PARTICIPANT_NOT_ACTIVE`（400）、`DUPLICATE_PARTICIPANT`（400）、`VALIDATION_ERROR`（人數不符 `match_mode` 要求）。

## DELETE /groups/{group_id}/members/{roster_entry_id}

踢除成員（FR-037，二次確認於前端）。

**Request**：無 body。

**Response 200**

```json
{ "roster_entry_id": "uuid", "status": "kicked" }
```

同一筆交易內：`roster_entries.status = 'kicked'`；依 FR-039～041 收斂賽程表（移除排隊中比賽相關組合，人數不足則整場移除；進行中比賽不受影響）；若固定搭檔模式且該成員有搭檔，對應 `Partnership` 刪除、原搭檔變回落單；發布 `member.left` 至團通知頻道。

**錯誤代碼**：`ADMIN_TOKEN_INVALID`、`ROSTER_ENTRY_NOT_FOUND`、`ROSTER_ENTRY_ALREADY_LEFT`（409）。

## 與既有 feature 的邊界

- 成員「主動退出」（非管理員踢除）之 HTTP 端點屬 005 spec 範圍（`POST /groups/{group_id}/leave`，見 `architecture.md`），本 feature 僅提供其呼叫的內部 service 函式（`handle_member_left`），不在此提供對應 REST 端點。
- 成員「加入」之 HTTP 端點屬 004 spec 範圍，本 feature 僅提供 `handle_member_joined` service 函式供其呼叫。
- 比賽的 +1/-1、提前結束（改變 `matches.status` 為 `completed`/`abandoned` 的實際觸發來源）屬 007 spec 範圍；本 feature 提供 `advance_court_after_match_ends(session, match)` 供其在比賽終態確立後呼叫。
