# API Contract: 快速比賽

新 router `apps/api/app/domains/quick_match/router.py`，prefix `/quick-matches`。除建立端點外，全部以**控制板 token** 授權（research Decision 5）：`get_court_by_token()` 解析後 `link_type != "control_panel"` → `LINK_NOT_FOUND` 404；所屬團 `kind != "quick"` → `QUICK_SESSION_ONLY` 404；已解散 → `QUICK_SESSION_CLOSED` 409。每個成功的寫入都更新 `groups.last_activity_at`。錯誤一律 `{"error_code", "detail"}`，前端以 `errors.<CODE>` 語系 key 顯示。

## `POST /quick-matches` — 建立並（若無好友）立即開賽

`optional_member`；Turnstile 必驗（fail-closed）；`@limiter.limit("20/minute")`。

```json
// QuickMatchCreateRequest
{
  "turnstile_token": "…",
  "match_mode": "singles",                 // singles | doubles
  "scoring_mode": "21pt",                  // 21pt | 15pt | custom
  "custom_target_score": null, "custom_deuce_threshold": null, "custom_cap_score": null,
  "detailed_scoring_enabled": false,
  "lineup": {
    "team_a": [ { "source": "self" }, { "source": "guest", "nickname": "小美" } ],
    "team_b": [ { "source": "friend", "member_id": "uuid" }, { "source": "guest", "nickname": "阿強" } ]
  }
}
```

- `lineup` 每隊 1（單打）或 2（雙打）個位置。`self` 只能出現一次且必須是 `team_a[0]`；呼叫者為會員時 **必須**有 `self`，為訪客時 **不得**有 `self`／`friend`（訪客建立者＝`team_a[0]` 的 `guest`，成為 `is_creator` 名單列）。
- 驗證錯誤（400）：`QUICK_LINEUP_INVALID`（`detail.reason`：`size` \| `self_position` \| `duplicate_nickname` \| `duplicate_friend` \| `self_as_friend` \| `guest_cannot_pick_friend`）、`NICKNAME_REQUIRED_FOR_GUEST`、既有的自訂計分制錯誤。
- 409：`ALREADY_ACTIVE_IN_ANOTHER_GROUP`（`detail.group_kind` 新增；FR-020 的自動收尾在此之前完成）；好友在別團 → `FRIEND_ACTIVE_ELSEWHERE`（`detail.member_id`）。403：Turnstile 失敗沿用既有 `TURNSTILE_FAILED`。
- 任一步失敗整筆 rollback（FR-008）。

```json
// 201 QuickMatchCreateResponse
{
  "group_id": "uuid",
  "control_panel_token": "uuid",
  "scoreboard_token": "uuid",
  "guest_session_token": "uuid|null",      // 訪客建立者才有（028 綁定用）
  "session": { …QuickSessionState… }       // 見下；state 為 waiting 或 playing
}
```

## `GET /quick-matches/by-token/{control_token}` — 狀態

先 `resolve_expired_slots()`。

```json
// QuickSessionState
{
  "group_id": "uuid",
  "state": "waiting",                       // waiting | playing | idle | closed（data-model §4）
  "match_mode": "singles",
  "scoring": { "scoring_mode": "21pt", "target_score": 21, "deuce_threshold": 20, "cap_score": 30, "detailed_scoring_enabled": false },
  "court_id": "uuid",
  "scoreboard_token": "uuid",
  "current_match_id": "uuid|null",
  "last_match": { "match_id": "uuid", "status": "completed", "winner_team": "A", "score_a": 21, "score_b": 17 } | null,
  "slots": [
    { "slot_id": "uuid", "team": "A", "position": 1, "source": "self",   "nickname": "我",   "status": "ready",   "member_id": "uuid", "guest_binding_token": null },
    { "slot_id": "uuid", "team": "B", "position": 1, "source": "friend", "nickname": "小美", "status": "pending", "member_id": "uuid", "expires_at": "2026-09-22T10:02:00Z" }
  ],
  "can_pick_friends": true,                 // 呼叫者為登入的建立者本人
  "closed_reason": null                     // closed 時：manual | cancelled | idle
}
```

- `guest_binding_token`：訪客位置的 `guest_session_token`，供控制板顯示「綁定戰績」連結（沿用 `guest-access/:token`）。
- `optional_member`：只用來算 `can_pick_friends`。

## `POST /quick-matches/by-token/{control_token}/rematch` — 再打一場

前置：`state == idle`。名單不變、A／B 對調，呼叫 `manual_assign()`。回 `QuickSessionState`（`state: playing`）。錯誤：`QUICK_SESSION_NOT_IDLE` 409。

## `POST /quick-matches/by-token/{control_token}/lineup` — 換人再打

前置：`state == idle`。`optional_member`。

```json
{ "match_mode": "doubles", "lineup": { "team_a": [ { "source": "self" }, { "source": "guest", "nickname": "新人" } ],
                                       "team_b": [ { "source": "friend", "member_id": "uuid" }, { "slot_id": "uuid" } ] } }
```

- 位置可用 `slot_id` 引用**目前已 ready 的位置**（保留其名單列，好友不重發邀請，FR-030），或提供新位置（規則同建立）。
- 建立者為會員時 `self` 必須保留（`QUICK_LINEUP_INVALID` / `self_position`）；`friend` 只有 `can_pick_friends` 時可用（否則 `QUICK_FRIEND_PICK_FORBIDDEN` 403）。
- 被移除的位置：名單列 `left`；新訪客位置立即 `ready`；新好友位置 `pending` 並發通知。全部 `ready` 立即開賽，否則 `state: waiting`。
- 錯誤：`QUICK_SESSION_NOT_IDLE`、`FRIEND_ACTIVE_ELSEWHERE`、既有 `NOT_FRIENDS`。

## `POST /quick-matches/by-token/{control_token}/slots/{slot_id}/convert` — 不等了，改用暱稱

前置：該位置 `pending`。轉為訪客（`source: guest`、`invite → invalidated`、`join_group(member=None)`），若已無 `pending` 立即開賽。回 `QuickSessionState`。錯誤：`QUICK_SLOT_NOT_PENDING` 409。

## `POST /quick-matches/by-token/{control_token}/cancel` — 等待中取消

前置：`state == waiting`。`disband_group()`（沒有任何比賽列，FR「不留下比賽紀錄」）、pending 邀請 `invalidated`。回 `QuickSessionState`（`closed`, `closed_reason: cancelled`）。錯誤：`QUICK_SESSION_NOT_WAITING` 409。

## `POST /quick-matches/by-token/{control_token}/close` — 結束

前置：`state in (idle, playing)`；`playing` 時進行中的比賽依 `disband_group()` 的既有行為轉 `abandoned`（前端在 playing 狀態先跳二次確認並說明）。回 `closed` / `manual`。

## `GET /members/me/quick-session` — 首頁橫幅（FR-021）

`require_verified_member`。回會員目前 `active` 且 `kind='quick'` 的團（名單列 active 或為建立者）：

```json
{ "group_id": "uuid", "state": "idle", "role": "creator", "control_panel_token": "uuid", "scoreboard_token": "uuid" }
// role: creator → 帶 control_panel_token；participant → control_panel_token 為 null，只帶 scoreboard_token
// 沒有時 200 null
```

## 好友接受／拒絕（沿用 `group_invite` router，行為擴充）

- `GET /group-invites/{id}`：回應新增 `group_kind`、`match_mode`、`inviter_nickname`。
- `POST /group-invites/{id}/accept`：既有流程 + `on_resolved` hook——快速比賽時位置轉 `ready`，全部 ready 立即開賽；回應新增 `scoreboard_token`。若 `join_group()` 拋 `ALREADY_ACTIVE_IN_ANOTHER_GROUP`，hook 先把位置轉為訪客（FR-029）再重新拋出。快速比賽已開賽或已收尾 → `GROUP_INVITE_NOT_PENDING`（邀請已被 invalidated），前端顯示「這場已經開始／已結束」。
- `POST /group-invites/{id}/decline`：位置轉為訪客。

## 既有端點的擴充

- `GET /groups`：基礎條件加 `kind = 'normal'`。
- `GET /members/me/groups`：新增查詢參數 `include_quick: bool = false`；`MyGroupSummary.group_kind`。
- `GET /members/me/match-records`、`…/dashboard`、`…/comparison`、好友對戰紀錄：新增查詢參數 `group_kind: normal | quick | null`；列與詳情新增 `group_kind`。
- `GET /courts/by-token/{token}`、`GET /courts/by-token/{token}/state`：新增 `group_kind`。
- 錯誤 `ALREADY_ACTIVE_IN_ANOTHER_GROUP`：`detail` 新增 `group_kind`。
