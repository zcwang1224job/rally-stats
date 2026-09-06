# API Contract: 即時計分板與控制板

沿用 `specs/architecture.md` 之路徑慣例；公開（無需登入）端點與管理員
端點共用同一組服務層函式（research.md #10）。錯誤代碼皆為語意化字串
（憲章原則 VIII），由前端依語系檔轉換顯示。

## 公開端點（token-based，無需登入）

### `GET /courts/by-token/{token}/state`

**用途**：計分板、單一場地控制板的初始載入 + 斷線重連後強制覆蓋
（research.md #8、FR-024）。`token` 接受 `scoreboard_token` 或
`control_panel_token`（唯讀端點，不需區分 research.md #3 之權限邊界）。

**回應** `200`：`CourtLiveState`（見 data-model.md），另包含既有
`CourtByTokenResponse` 已有的 `court_id`/`group_id`/`name`/`link_type`/
`link_version`/`deleted`/`group_disbanded` 欄位（沿用 002 既有形狀，避免
前端需要組合兩個端點的回應才能顯示完整畫面）。

**錯誤**：`LINK_NOT_FOUND`（404，token 不存在/場地已刪除/團已解散——
沿用 002 既有語意）。

---

### `POST /courts/by-token/{token}/matches/{match_id}/score`

**用途**：+1/-1（FR-003~007）。**僅接受 `control_panel_token`**
（research.md #3）；以 `scoreboard_token` 呼叫 MUST 回傳
`LINK_NOT_FOUND`（不透露「這其實是合法的唯讀連結」）。

**Request Body**

```json
{ "side": "A", "delta": 1 }
```

`side`: `"A" | "B"`。`delta`: `1 | -1`（其餘數值 MUST 回傳
`VALIDATION_ERROR`）。

**回應** `200`：`ScoreMutationResult`（見 data-model.md）。

**錯誤**：
- `LINK_NOT_FOUND`（404）：token 無效、或以 `scoreboard_token` 呼叫。
- `MATCH_NOT_FOUND`（404）：`match_id` 不存在，或其 `court_id` 不等於
  此 token 對應的場地（research.md #4 之授權邊界；刻意不回傳 403，避免
  洩漏「這個 match_id 存在但屬於別的場地」）。

**冪等性/no-op 語意**：`match_id` 對應之比賽已為終態
（`completed`/`abandoned`）、或 `delta=-1` 且該方分數已為 `0` 時，
`applied=false`，仍回傳 `200`（research.md #9），MUST NOT 回傳 4xx。

---

### `POST /courts/by-token/{token}/matches/{match_id}/end`

**用途**：提前結束（FR-008~010）。**僅接受 `control_panel_token`**
（同上）。

**Request Body**：無（確認流程為前端二次確認 UI，憲章原則 V，不需要
後端額外的確認 token）。

**回應** `200`：`ScoreMutationResult`（`winner_team` 恆為 `null`，
`status` 成功時為 `"abandoned"`）。

**錯誤**：同上（`LINK_NOT_FOUND`、`MATCH_NOT_FOUND`）。

**冪等性/no-op 語意**：`match_id` 已為終態時 `applied=false`，仍回傳
`200`（FR-006a、research.md #9）。

---

### `GET /groups/by-all-courts-token/{token}/state`

**用途**：全部場地控制板的初始載入 + 斷線重連強制覆蓋（FR-001、
FR-024）。

**回應** `200`：

```json
{
  "group_id": "uuid",
  "round_number": 5,
  "courts": [
    { "court_id": "uuid", "name": "1號場", "current_match": { "...": "MatchLiveDetail" }, "waiting_reason": null, "next_up": null },
    { "court_id": "uuid", "name": "2號場", "current_match": null, "waiting_reason": "no_queued_match", "next_up": null }
  ]
}
```

（`courts[]` 之每個元素即 data-model.md 之 `CourtLiveState`，省略
`round_number` 因已在外層統一提供。）

**錯誤**：`LINK_NOT_FOUND`（沿用既有 `all_courts_control_panel_token`
語意）。

---

### `POST /groups/by-all-courts-token/{token}/courts/{court_id}/matches/{match_id}/score`

**用途**：全部場地控制板對單一場地執行 +1/-1。Body/回應/錯誤/no-op
語意與單一場地版本完全相同；差別僅在 token 類型與多一層 `court_id`
路徑參數（用於從全部場地 token 定位到具體場地，並比對 `match_id` 之
`court_id` 是否相符，research.md #4）。

### `POST /groups/by-all-courts-token/{token}/courts/{court_id}/matches/{match_id}/end`

同上，對應提前結束。

## 管理員端點（PIN session，供開團管理頁「場地控制」區塊使用）

沿用 `schedule/router.py` 既有的 `_admin_court()` dependency 模式
（`group_id` + `court_id` path 參數 + 既驗證的管理 PIN session）。

### `POST /groups/{group_id}/courts/{court_id}/matches/{match_id}/score`

Body/回應/錯誤/no-op 語意與公開版本完全相同，僅授權機制不同
（research.md #10）。

### `POST /groups/{group_id}/courts/{court_id}/matches/{match_id}/end`

同上。

**狀態顯示**：管理頁不需要新的 state 端點——直接擴充既有
`GET /groups/{group_id}/schedule`（`ScheduleResponse`，003 已建立）：
`MatchSummary` 新增 `score_a`/`score_b` 欄位；`CourtScheduleStatus`
新增 `next_up`（`NextUpPreview | null`，語意同上）欄位（research.md
#10）。此端點的既有 `waiting_reason` 欄位不需變更。
