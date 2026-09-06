# Quickstart: 即時計分板與控制板

## 前置條件

- 後端、前端服務皆已啟動（延續既有 `docker compose` / 本地開發流程）。
- 已有一個團，排程機制設為 `fair_rotation`（用於情境 1-5），已建立至少
  1 個場地，且該團已透過 `POST /groups/{group_id}/next-round`（或
  Foundational 情境自動觸發）產生第 1 輪賽程表，該場地已領取一場
  `in_progress` 的比賽。
- 另備一個排程機制設為 `manual` 的團（用於情境 6），已透過管理頁
  `manual-assign` 端點手動安排一場 `in_progress` 比賽。
- 已取得該場地的 `control_panel_token`、`scoreboard_token`（管理頁
  「場地管理」區塊可查看，或直接查詢資料庫）。

## 情境 1：+1/-1 即時同步（US1，FR-003~007，SC-001）

1. 開啟控制板：`GET /courts/by-token/{control_panel_token}/state`，
   確認 `current_match.score_a = 0`、`score_b = 0`。
2. 開啟計分板：`GET /courts/by-token/{scoreboard_token}/state`（同一
   場地，另一組 token），確認顯示相同比分。
3. 呼叫 `POST /courts/by-token/{control_panel_token}/matches/{match_id}/score`
   body `{"side": "A", "delta": 1}`。
4. **預期**：回應 `applied=true`，`score_a=1`；1 秒內計分板端訂閱到
   `match.scoreUpdated` 事件並更新顯示（可用 Ably 頻道 log 或前端手動
   驗證）。
5. 重複呼叫 `delta: -1` 直到 `score_a=0`，再呼叫一次 `-1`。
   **預期**：`applied=false`，`score_a` 仍為 `0`（FR-005）。

## 情境 2：自然達標結束 + 場地正確等待下一輪（US1，FR-003、FR-011）

前置：該場地比賽的 `target_score` 快照值較小（例如自訂團設 `target=3`
以加速驗證）。**注意**：`fair_rotation`/`fixed_partner` 之 round
generation 一律只產生「剛好填滿目前場地數」的比賽（見
`research.md` 對 `_generate_fair_rotation_matches` 的說明），故單一
round 內不會有「已產生但尚未被任何場地領取」的排隊中比賽——一場比賽
結束後，`waiting_reason="no_queued_match"` 是演算法模式下的正常結果，
直到管理員觸發 Next Round 為止；`rotation.updated` 只在真的有排隊中
比賽可領取時才會發布（例如某成員中途退出導致的重新排隊情境）。

1. 連續呼叫 `.../score` 將 `score_a` 推進至 `target_score`（且領先
   ≥2 分，或觸及 `cap_score`）。
2. **預期**：最後一次呼叫回應 `status="completed"`、
   `winner_team="A"`；訂閱端收到 `match.ended`
   （`waiting_reason="no_queued_match"`）——場地 `current_match` 變為
   `null`，畫面顯示「等待下一輪」；同團其他場地與 `round_number` 皆不受
   影響（FR-011, FR-013）。
3. 針對**已結束**的舊 `match_id` 再呼叫一次 `.../score`。
   **預期**：`applied=false`（FR-006，延遲請求 no-op，且不影響其他
   場地）。
4. 管理員於管理頁觸發 Next Round。
   **預期**：該場地 `round_number` +1，`current_match` 變為新比賽、
   比分歸零。

## 情境 3：提前結束（US2，FR-008~010）

1. 對一場 `in_progress` 比賽（比分尚未達標）呼叫
   `POST .../matches/{match_id}/end`。
2. **預期**：回應 `applied=true`、`status="abandoned"`、
   `winner_team=null`；場地依排程機制自動領取下一場（演算法模式）或顯示
   `waiting_reason="manual_assignment"`（手動模式，見情境 6）。
3. 對**同一個**已 `abandoned` 的 `match_id` 再呼叫一次 `.../end`。
   **預期**：`applied=false`（FR-006a）。
4. 對同一個已 `abandoned` 的 `match_id` 呼叫 `.../score`。
   **預期**：`applied=false`（FR-006，捨棄比賽同樣拒絕加減分）。

## 情境 4：全部場地控制板（US5，FR-001）

前置：團內有 ≥2 個場地，皆有 `in_progress` 比賽。

1. `GET /groups/by-all-courts-token/{all_courts_control_panel_token}/state`。
   **預期**：`courts[]` 內每個場地各自的 `current_match`/比分正確。
2. 對其中一個場地呼叫
   `POST .../courts/{court_id}/matches/{match_id}/score`。
   **預期**：僅該場地的比分變動；用該場地**自己的**
   `control_panel_token` 呼叫 `GET .../state` 確認回傳比分與全部場地
   控制板一致（FR-001 之「兩者操作結果須完全一致並即時互相同步」）。
3. 檢查全部場地控制板與單一場地控制板的畫面/API，皆確認**找不到**任何
   Next Round 相關的操作端點（FR-014，SC-004）。

## 情境 5：斷線與重連強制覆蓋（US4，FR-021~025）

（此情境涉及前端 Ably 連線模擬，建議於瀏覽器開發工具離線模式下手動
驗證，或使用 Vitest 對 `RealtimeService.connectionState` mock 觸發轉換）

1. 開啟控制板，確認 `connectionState` 為 `connected`，畫面無斷線提示。
2. 模擬離線（開發工具切換離線，或關閉本機網路）。
   **預期**：畫面出現斷線提示（FR-022）；嘗試按 +1，畫面阻止操作或
   明確標示「離線中」（FR-023）。
3. 在離線期間，用另一個裝置（或直接呼叫 API）對同一場比賽送出 +1。
4. 恢復網路連線。
   **預期**：`connectionState` 轉回 `connected` 後，前端自動呼叫
   `GET .../state` 並以其結果覆蓋畫面——顯示步驟 3 的最新比分，而非
   離線前的舊比分（FR-024）。
5. 對計分板、單一場地控制板、全部場地控制板、管理頁場地控制區塊分別
   重複步驟 1-4，確認四者斷線重連後最終顯示彼此一致（FR-025，SC-005）。

## 情境 6：手動安排模式的等待畫面（Edge Case，FR-012、FR-018）

前置：使用 `manual` 排程機制的團與其 `in_progress` 比賽。

1. 對該比賽呼叫 `.../end`（提前結束）或推進至達標。
2. **預期**：回應成功；`GET .../state` 顯示 `current_match=null`、
   `waiting_reason="manual_assignment"`、`next_up=null`（即使賽程表另有
   `queued` 比賽也不自動領取，FR-012）。
3. 計分板/控制板畫面 MUST 顯示「等待管理員安排下一場」，MUST NOT 顯示
   任何「即將登場」預告內容（FR-018）。
4. 管理員於管理頁對該場地執行 `manual-assign`（003 既有端點）後，
   `GET .../state` 應恢復 `current_match` 非 `null`。

## 驗證通過標準

- 所有 6 個情境的「預期」項目皆吻合。
- `pytest`（後端單元/契約/整合測試）與 `ng test`（Vitest，前端）皆
  全數通過；`ruff`/`mypy --strict`/`ng lint` 皆無錯誤（憲章技術治理
  關卡）。
- 情境 1 之「1 秒內同步」建議以簡易計時（呼叫 API 到前端事件觸發的
  時間差）人工抽測至少 3 次，非嚴格自動化效能測試（SC-001 為 SHOULD
  等級的可觀察體驗指標，非 blocking gate）。
