# Ably Event Contract: 賽程與輪替名單

沿用 `specs/architecture.md` §3.2 之頻道設計。

## `rotation.updated`

**觸發時機**：場地領取新比賽——Round 產生後的初次領取（research.md #7）、`advance_court_after_match_ends` 領取下一場排隊中比賽、或手動安排建立新比賽（`POST /courts/{court_id}/manual-assign`）成功交易後。

**發布頻道**：`court:{group_id}:{court_id}`（場地層級）

**Payload**

```json
{
  "event": "rotation.updated",
  "match_id": "uuid",
  "round_number": 3,
  "participants": [{ "roster_entry_id": "uuid", "nickname": "小明", "team": "A" }]
}
```

**訂閱端預期行為**：計分板/控制板（單一場地、全部場地）、管理頁場地控制區塊收到後 MUST 立即更新為新對戰組合、比分歸零。

## `match.nextRound`

**觸發時機**：`POST /groups/{group_id}/next-round` 成功，或 Auto Next Round 自動觸發成功交易後。

**發布方式**：逐一發布至每個「目前有效」場地頻道（比照 001 之 `group.disbanded` 逐一發布原則，MUST NOT 僅發布至團通知頻道）。

**Payload**

```json
{ "event": "match.nextRound", "round_number": 4 }
```

**訂閱端預期行為**：所有畫面 MUST 捨棄本地暫存的賽程狀態，重新拉取（或等待緊接而來的 `rotation.updated`）以顯示新一輪內容；手動安排模式下，場地 MUST 顯示「等待管理員安排下一場」。

## `member.joined` / `member.left`

**觸發時機**：`handle_member_joined`（供 004 呼叫）成功後；`DELETE /groups/{group_id}/members/{roster_entry_id}`（踢除）或 `handle_member_left`（供 005 呼叫，主動退出）成功交易後。

**發布頻道**：`group:{group_id}:notifications`

**Payload**

```json
{ "event": "member.joined", "roster_entry_id": "uuid", "nickname": "小美" }
{ "event": "member.left", "roster_entry_id": "uuid", "nickname": "小美" }
```

**訂閱端預期行為**：所有場地控制板（訂閱團通知頻道）MUST 即時跳出提醒（FR-038, FR-039）；MUST NOT 觸發任何自動重新整理賽程表的行為——僅為提示，賽程表本身的變動（若有）已包含在對應場地各自的 `rotation.updated` 事件內。
