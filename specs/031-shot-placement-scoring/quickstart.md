# Quickstart: 落點詳細計分模式

本功能同時涉及後端資料/API 與前端互動（與 029/030 純後端不同），以下情境同時涵蓋兩者；前端相關情境待 tasks.md 展開對應元件後才能實際操作，後端情境可以在前端完成前先以 API 直接呼叫驗證。

## 前置準備

沿用既有後端本地開發環境（見 `apps/api/README.md`），並準備一個團、一個場地、一場**雙打**比賽（4 位參賽者，涵蓋情境較完整）。

## 驗證情境 1：開啟團設定後，新比賽才會是詳細模式

1. 呼叫 `PATCH /{group_id}/detailed-scoring`，body `{"enabled": true}`。
2. 查詢該團既有一場**已經在進行中**的比賽（在步驟 1 之前就建立的），確認其 `matches.detailed_scoring_enabled` 仍是 `false`。
3. 透過既有流程建立一場**新**比賽並讓它進入 `in_progress`。
4. 查詢這場新比賽的 `matches.detailed_scoring_enabled`。

**預期結果**：步驟 2 的既有比賽維持 `false`（不回溯影響，FR-006）；步驟 4 的新比賽為 `true`（快照自步驟 1 之後的團設定，FR-006）。

## 驗證情境 2：標落點＋選球員成功加分

1. 對情境 1 步驟 4 的詳細模式比賽，呼叫 `POST .../matches/{match_id}/score-detailed`，body 帶入該比賽 A 隊某一位參賽者的 `roster_entry_id` 與任意合理落點座標（例如 `{"roster_entry_id": "<A隊某球員>", "landing_x": 0.7, "landing_y": 0.3}`）。
2. 查詢回應內容、`matches.score_a`、`shot_placement_records`（篩選這場比賽）。

**預期結果**：回應 `applied: true`、`score_a` 加一；`shot_placement_records` 新增一筆，`roster_entry_id`／`team`（`"A"`）／`landing_x`／`landing_y` 皆與請求一致，`score_event_id` 對應同一次加分產生的 `score_events` 資料列。

## 驗證情境 3：修正比分時一併收回落點紀錄

1. 對情境 2 的比賽，呼叫既有 `POST .../matches/{match_id}/score`，body `{"side": "A", "delta": -1}`。
2. 查詢 `matches.score_a`、`shot_placement_records`（篩選這場比賽、`team = "A"`）。

**預期結果**：`score_a` 少一（回到情境 2 之前的值）；情境 2 新增的那一筆 `shot_placement_records` 已經消失，若情境 2 之前 A 隊已有更早的落點紀錄，那些更早的紀錄不受影響（FR-007，只收回最後一筆）。

## 驗證情境 4：簡易模式比賽呼叫詳細端點會被拒絕

1. 建立/使用一場 `detailed_scoring_enabled = false` 的比賽，呼叫 `POST .../matches/{match_id}/score-detailed`。

**預期結果**：回應 422，錯誤代碼 `DETAILED_SCORING_NOT_ENABLED`；不寫入任何 `shot_placement_records`、不改動比分。

## 驗證情境 5：`roster_entry_id` 不屬於該場比賽會被拒絕

1. 對情境 1 的詳細模式比賽，呼叫 `score-detailed`，`roster_entry_id` 帶入一個不存在於這場比賽 `match_participants` 的合法 UUID（例如另一場比賽的參賽者）。

**預期結果**：回應 422，錯誤代碼 `PARTICIPANT_NOT_IN_MATCH`；不寫入任何 `shot_placement_records`、不改動比分。

## 驗證情境 6：`GET .../state` 回傳的模式旗標正確反映快照值

1. 分別查詢情境 1 步驟 2（簡易模式）與步驟 4（詳細模式）兩場比賽各自的 `GET /courts/by-token/{scoreboard_token}/state`。

**預期結果**：前者 `current_match.detailed_scoring_enabled` 為 `false`，後者為 `true`；即使兩場比賽所屬同一個團、團設定當下已經是 `true`，前者仍維持 `false`（反映各自的快照，不是即時讀團設定）。

## 驗證情境 7（前端，待共用元件完成後可操作）：三個既有計分畫面一致切換 UI

1. 分別開啟情境 1 步驟 4 那場詳細模式比賽的計分板連結、控制板連結，以及（若該場地所屬團有多場地）全場地控制板頁面。

**預期結果**：三處原本的「+1」按鈕位置，皆改為開啟「點落點 → 選球員 → 確認」的共用互動元件，而非簡易 +1/-1 按鈕；三處確認送出後都呼叫同一個 `POST .../score-detailed`，行為與情境 2 一致。

## 驗證情境 8：比賽被捨棄不影響已寫入的落點紀錄

1. 對已經累積若干筆 `shot_placement_records` 的詳細模式比賽，呼叫既有「提前結束比賽」（`end_match_early`）。
2. 重新查詢該比賽的 `shot_placement_records`。

**預期結果**：筆數與呼叫前完全相同，內容未被改動（FR-009，比照 030 既有情境 6 的驗證方式）。
