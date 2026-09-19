# API Contract: 休息／準備狀態

兩支端點、同一個請求與回應形狀、同一個服務函式（`schedule/rest.py` 的
`set_rest_state()`，research.md Decision 7）。差別只在「誰可以呼叫」。

請求內容是**目標狀態**，不是「切換」：已經是目標狀態時為 no-op，回傳
現況（`changed: false`），不發布任何事件。

```json
// RestStateRequest
{ "resting": true, "guest_session_token": "…（只有本人端點、且呼叫者為訪客時）" }
```

```json
// RestStateResponse
{
  "roster_entry_id": "uuid",
  "resting": true,
  "resting_since": "2026-09-19T12:34:56Z",   // resting 為 false 時為 null
  "currently_playing": true,                  // 為 true 且 resting 為 true → 畫面顯示「打完這一場後開始休息」（FR-014）
  "changed": true
}
```

## `PUT /groups/{group_id}/roster/{roster_entry_id}/rest-state`（本人）

**用途**：球員切換自己的狀態（US1，FR-002）。位於 `group/router.py`，
緊鄰既有的 `POST …/leave`。

**身分**：與 `POST …/leave` 完全相同——`Depends(optional_member)` 加上
body 的 `guest_session_token`；呼叫者 MUST 被證明擁有 `roster_entry_id`
（訪客 token 相符，或會員身分與該列的 `member_id` 相符）。兩者都提供時
以訪客 token 為準（與 `leave_group()` 一致）。

**回應** `200`：`RestStateResponse`。

**錯誤**：
- `GROUP_NOT_FOUND`（404）。
- `ROSTER_ENTRY_NOT_FOUND`（404）——該列不存在、不屬於此團、`status`
  不是 `active`、或呼叫者無法證明擁有它。四種情況 MUST 回傳完全相同的
  錯誤，MUST NOT 洩漏該列是否存在（FR-004）。
- `GROUP_DISBANDED`（409）——團已解散。

## `PUT /groups/{group_id}/members/{roster_entry_id}/rest-state`（管理員）

**用途**：管理員切換任一位在團內球員的狀態（US4，FR-003）。位於
`schedule/router.py`，緊鄰既有的 `DELETE …/members/{roster_entry_id}`
（踢人）。

**身分**：`Depends(require_admin)`。body 的 `guest_session_token` 會被
忽略。

**回應** `200`：`RestStateResponse`。

**錯誤**：
- 管理員驗證失敗——沿用 `require_admin` 既有的錯誤。
- `ROSTER_ENTRY_NOT_FOUND`（404）——該列不存在、不屬於此團、或
  `status` 不是 `active`。
- `GROUP_DISBANDED`（409）。

建立者自己的那一列**可以**被切換（與踢人不同——休息不是移除）。

## 成功後的副作用（兩支端點相同，順序固定）

只在 `changed: true` 時發生。細節見 research.md Decision 7。

1. 切回準備中時：寫入一列休息區間、調整 `played_credit`、走中途加入者
   流程（可能為他在當前這一輪補上場次）。
2. 輪次進行中時，把閒置的場地填滿——叫排隊中的場次，否則（連續輪轉）
   從閒置球員排出一場。每個因此開始比賽的場地發 `rotation.updated`，
   所有場地發 `match.nextRound`（既有事件，作為重抓的觸發）。
3. 開啟「自動進入下一輪」時，檢查這一輪是否已結束或被休息卡住
   （research.md Decision 6）；成立且下一輪排得出至少一場 → 換輪。
4. 發布 `roster.restChanged`（見
   [ably-events-additions.md](./ably-events-additions.md)）。

**切成休息的當下 MUST NOT 修改任何場次**（FR-013）——步驟 2、3 只會叫
別的場次上場或換輪，不會替補或取消他的場次；替補只發生在叫場那一刻。

## 不受影響的既有端點

`POST …/leave`、`DELETE …/members/{id}`（踢人）、手動安排、交換、替換
球員的驗證規則皆不變——管理員可以把休息中的球員排進場次，系統不會
因此改變他的休息狀態（FR-029）。
