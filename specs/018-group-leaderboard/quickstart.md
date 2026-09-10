# Quickstart: 團內即時排行榜（強化既有戰績頁）

## 前置條件

- 後端、前端服務皆已啟動。
- 一個團，持有至少一位現役成員的存取憑證（現役成員 Token／訪客
  session token 皆可，比照既有戰績頁的存取層級）。
- 團內已產生至少 1 輪賽程（`RoundHistory` 至少 1 筆），排點機制不拘
  （`fair_rotation`／`fixed_partner`／`individual_mixed`／`manual` 皆
  適用——spec.md FR-001）。

## 情境 1：戰績頁依勝場數排序，並顯示名次（US1）

1. 團內有 P0~P3 四位現役成員，P0 累計 5 勝、P1 累計 3 勝、P2 累計 3 勝、
   P3 累計 0 場已完成比賽。
2. 呼叫 `GET /groups/{group_id}/standings`。
   **預期**：`200`，`members` 陣列依序為 P0（`rank: 1`）、P1/P2（皆
   `rank: 2`，兩者之間依 `joined_at` 排序）、P3（`rank: 4`，`total_wins:
   0, total_losses: 0`）——驗證跳號規則（FR-006，research.md #6）。
3. P3 對應的 `rounds` 內每一輪皆為 `wins: 0, losses: 0, left: false`；
   前端 MUST 依此顯示「尚無比賽紀錄」，而非誤判為敗場掛零（FR-007，
   SC-004）。

## 情境 2：比賽結束後，戰績頁在數秒內自動更新（US2）

1. 開兩個瀏覽器分頁，皆檢視同一團的戰績頁（`groups/{groupId}/member-view`
   → 「戰績」分頁）。
2. 在其中一個分頁對應的場地，讓一場進行中的比賽比分到達致勝分數
   （`POST /groups/{group_id}/courts/{court_id}/matches/{match_id}/score`
   直到 `match_wins()` 條件成立，`Match.status` 轉為 `completed`）。
   **預期**：後端在同一次請求內發布 `standings.updated` 至
   `group:{group_id}:notifications`（見 `contracts/ably-events.md`）。
3. 觀察另一個分頁的戰績頁。
   **預期**：2 秒內（SC-002）自動重新拉取並顯示更新後的名次與勝敗場數，
   不需要手動重新整理頁面。

## 情境 3：並列名次，且多次重新整理順序穩定（US3）

1. 團內 P0、P1 兩人累計戰績完全相同（例如皆為 2 勝 1 敗），P0 的
   `joined_at` 早於 P1。
2. 呼叫 `GET /groups/{group_id}/standings` 三次（模擬多次重新整理）。
   **預期**：每次回應中 P0 與 P1 皆並列同一 `rank`，且 P0 在 `members`
   陣列中皆排在 P1 前面——三次呼叫結果完全一致（SC-003）。

## 情境 4：離團成員被排除，但不影響現役對手的戰績（US1 Edge Case）

1. P4 過去與 P0 打過並打贏一場已完成比賽，之後 P4 離開了團（`status`
   轉為 `left`）。
2. 呼叫 `GET /groups/{group_id}/standings`。
   **預期**：`200`，`members` 陣列中 MUST NOT 出現 P4（FR-008，SC-005）；
   P0 的 `total_losses` MUST 仍然正確計入這場輸給 P4 的紀錄（不因 P4
   離團而消失）。

## 情境 5：重新連線後強制拿到最新名次，且沒有斷線提示元件（US2 Edge Case）

1. 使用者正在檢視戰績頁，裝置與 Ably 的連線中斷一段時間（模擬：切換
   分頁、螢幕休眠、或直接斷開網路）。
2. 中斷期間，團內有一場比賽完成（因此漏接了 `standings.updated` 事件）。
3. 裝置重新恢復連線（或使用者切回分頁）。
   **預期**：`ReconnectRefetchService.onReconnect()` 觸發，前端自動重新
   呼叫 `GET /groups/{group_id}/standings`，畫面在使用者沒有手動操作的
   情況下更新為當下正確的名次（FR-012，SC-006）；畫面上全程 MUST NOT
   出現任何「連線中斷」提示元件（Clarifications Q4）。

## 情境 6：既有逐輪細目欄位保留（回歸驗證）

1. 呼叫 `GET /groups/{group_id}/standings`。
   **預期**：`rounds`（該團已產生過的輪次清單）與每位成員 `rounds`
   內逐輪的 `wins`/`losses`/`left` 欄位，內容與擴充前的既有行為完全
   一致——本次擴充只新增 `rank`/`total_wins`/`total_losses`，MUST NOT
   移除或改變任何既有欄位（spec.md Assumptions）。

## 驗證通過標準

- 所有情境的「預期」項目皆吻合。
- `pytest`（後端單元/整合測試）與 `ng test`（Vitest，前端）皆全數
  通過；`ruff`/`mypy --strict`/`ng lint` 皆無錯誤（憲章技術治理關卡）。
- 情境 1 的「自己所在列」標示（FR-011），人工檢視確認以圖示/文字（而非
  純顏色）與其他列區隔（憲章原則 VII）。
