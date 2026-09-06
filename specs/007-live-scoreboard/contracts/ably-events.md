# Ably Event Contract: 即時計分板與控制板

沿用 `specs/architecture.md` §3.2 之頻道設計，並延續
`specs/003-schedule-rotation/contracts/ably-events.md` 已定義之事件
（`rotation.updated`、`match.nextRound`、`member.joined`/`member.left`）
——本檔案僅新增 007 專屬的 2 個事件，其餘沿用 003 既有定義不重複贅述。

## `match.scoreUpdated`（新增）

**觸發時機**：`POST .../matches/{match_id}/score` 成功交易後，且
`applied=true`、比賽**仍為** `in_progress`（尚未達標）。

**發布頻道**：`court:{group_id}:{court_id}`（場地層級，沿用 003 既有
`court_channel()` helper）。

**Payload**

```json
{ "event": "match.scoreUpdated", "match_id": "uuid", "score_a": 12, "score_b": 10 }
```

**訂閱端預期行為**：計分板、控制板（兩種模式，僅更新對應場地區塊）、
管理頁場地控制區塊 MUST 立即更新顯示的比分，不需重新整理（FR-019、
SC-001，約 1 秒內）。

## `match.ended`（新增）

**觸發時機**：`POST .../matches/{match_id}/score`（達標）或
`POST .../matches/{match_id}/end`（提前結束）成功交易後，且
`applied=true`——比賽轉為終態的那一刻。

**發布頻道**：`court:{group_id}:{court_id}`。

**Payload**

```json
{
  "event": "match.ended",
  "match_id": "uuid",
  "status": "completed",
  "winner_team": "A",
  "score_a": 21,
  "score_b": 18,
  "waiting_reason": null
}
```

`waiting_reason`：`"no_queued_match" | "manual_assignment" | null`——
`null` 代表同一次交易內緊接著會（或已經）發布 `rotation.updated`，
訂閱端 MUST 等待該事件以顯示新對戰組合，MUST NOT 因為 `waiting_reason`
為 `null` 就自行顯示「等待中」文字（research.md #7，避免閃爍）。

**訂閱端預期行為**：
- 立即以 payload 內的最終比分/`winner_team` 更新畫面一次（避免最後一次
  `match.scoreUpdated` 若因網路順序問題晚到而顯示不一致的中間值）。
- `waiting_reason` 非 `null` 時，MUST 立即顯示對應的等待文案（FR-011、
  FR-012、FR-018）；為 `null` 時等待緊接而來的 `rotation.updated`。
- 提前結束（`status: "abandoned"`）情境下，`winner_team` 恆為 `null`，
  畫面 MUST NOT 顯示任何勝負結果，直接進入上述「等待/下一場」邏輯
  （FR-009）。

## 既有事件的延伸適用說明（非新增，僅澄清 007 之呼叫責任）

- **`rotation.updated`**（003 定義）：003 之 contract 已明確將
  `advance_court_after_match_ends` 領取下一場比賽列為觸發時機之一——
  007 的比分/提前結束端點在呼叫該既有函式並取得非 `None` 回傳值時，
  MUST 依 003 既有邏輯發布此事件（重用既有的 `_publish_rotation_updated`
  helper，見 research.md #6），不重新定義 payload 形狀。
- **`match.nextRound`**：Auto Next Round 由 007 觸發（比賽終態轉換後
  呼叫 `check_round_complete_and_maybe_auto_advance`）時，該既有函式
  內部的 `generate_next_round` 已自行發布，007 不需重複發布。
