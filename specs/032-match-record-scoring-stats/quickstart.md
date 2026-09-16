# Quickstart: 對戰紀錄逐點得失分球員與落點資訊、球員得失分統計

本功能是純讀取擴充，不涉及任何寫入端點——以下情境使用 031/032-shot-placement-scoring 既有的計分/落點記錄端點準備測試資料，再驗證本功能新增的「查看」端點回應與畫面呈現。前端相關情境待 tasks.md 展開對應元件改動後才能實際操作，後端情境可在前端完成前先以 API 直接呼叫驗證。

## 前置準備

沿用既有後端本地開發環境（見 `apps/api/README.md`）。準備一個已開啟 `detailed_scoring_enabled` 的團、一個場地、一場**雙打**比賽（4 位參賽者，涵蓋「未列在統計中的 0 次球員」情境較完整）。

## 驗證情境 1：完整記錄的一分，`detail` 完整回傳

1. 對這場詳細模式比賽呼叫既有 `POST .../matches/{match_id}/score`（`{"side": "A", "delta": 1}`），取得 `score_event_id`。
2. 呼叫既有 `POST .../matches/{match_id}/shot-placement`，帶入 A 隊某球員的 `roster_entry_id`（得分）、B 隊某球員的 `losing_roster_entry_id`（失分）、與一組界內落點座標。
3. 呼叫本功能擴充後的 `GET /groups/{group_id}/match-records/{match_id}`（比賽需先自然結束才能查詢，可視需要重複加分至達到目標分數）。

**預期結果**：回應 `events` 陣列中，步驟 1 那一分對應的 `ScoreEventSummary.detail` 非 `null`，`scoring_nickname`/`losing_nickname` 與步驟 2 選擇的球員暱稱一致，`landing_x`/`landing_y` 與步驟 2 送出的座標一致。

## 驗證情境 2：跳過的一分，`detail` 為 `null`

1. 對同一場比賽再加一分（`POST .../score`），但**不**呼叫 `/shot-placement`（模擬前端「跳過」）。
2. 待比賽結束後查詢比賽詳情。

**預期結果**：這一分對應的 `ScoreEventSummary.detail` 為 `null`；不因為缺少落點紀錄而拋出錯誤或省略這筆事件本身（`side`/`delta`/`score_a`/`score_b`/`elapsed_seconds` 仍照常回傳）。

## 驗證情境 3：全空確認的一分，`detail` 仍為 `null`（research.md Decision 2）

1. 對同一場比賽再加一分，呼叫 `/shot-placement` 但四個欄位（`roster_entry_id`/`losing_roster_entry_id`/`landing_x`/`landing_y`）全部留空（等同前端「確認記錄」按鈕在什麼都沒選的情況下被按下）。
2. 待比賽結束後查詢比賽詳情。

**預期結果**：這一分對應的 `ScoreEventSummary.detail` 為 `null`（即使資料庫中確實存在一筆對應的 `ShotPlacementRecord`），與情境 2「完全沒有記錄」在回應上無法區分，呈現效果一致（皆不顯示球員徽章、皆不可展開落點）。

## 驗證情境 4：扣分事件永遠沒有 `detail`

1. 對同一場比賽呼叫既有 `POST .../score`（`{"side": "A", "delta": -1}`）。
2. 查詢比賽詳情。

**預期結果**：這一筆 `delta: -1` 的事件，`detail` 為 `null`（不論這次扣分是否連帶收回了某一筆 `ShotPlacementRecord`，`ScoreEventSummary` 本身描述的是「這個扣分事件」，扣分事件從未擁有自己的 `ShotPlacementRecord`）。

## 驗證情境 5：只記錄部分欄位（只選得分球員，沒選落點）

1. 對同一場比賽再加一分，呼叫 `/shot-placement` 只帶 `roster_entry_id`，其餘欄位留空。
2. 查詢比賽詳情。

**預期結果**：這一分 `detail.scoring_nickname` 有值，`detail.losing_nickname`/`detail.landing_x`/`detail.landing_y` 皆為 `null`——`detail` 本身非 `null`（因為至少一個欄位有記錄），但個別欄位各自反映實際記錄狀況。

## 驗證情境 6：球員得失分統計正確加總、含 0 次球員

待比賽依上述情境完整結束（含情境 1/2/3/5 累積的加分事件）後，查詢比賽詳情。

**預期結果**：`player_stats` 陣列包含這場比賽全部 4 位參賽者；情境 1 的得分球員 `scored_count` ≥ 1、情境 1 的失分球員 `fault_count` ≥ 1、情境 5 的得分球員 `scored_count` 再 +1；完全沒有被選為得分或失分球員的那些球員，仍出現在陣列中且兩個計數皆為 `0`（FR-009）——不得因為次數是 0 就從陣列中省略。

## 驗證情境 7：完全沒有詳細計分資料的比賽，`player_stats` 為空陣列

1. 使用一場**非**詳細計分模式（或詳細計分但每一分都跳過）的已完成比賽，查詢其比賽詳情。

**預期結果**：`player_stats` 為 `[]`；前端 MUST 顯示「此比賽沒有球員得失分紀錄」提示，MUST NOT 顯示全部掛零的統計表（FR-008）。

## 驗證情境 8（前端，待元件改動完成後可操作）：逐點清單球員徽章與原地展開

1. 在對戰紀錄清單（任一入口：某團對戰紀錄、我的跨團對戰紀錄、某團歷史戰績）點進情境 1～6 那場比賽。
2. 觀察逐點紀錄清單中，情境 1/5 對應的加分紀錄旁是否顯示球員暱稱徽章；情境 2/3 對應的加分紀錄旁是否維持原樣（無徽章）。
3. 點擊情境 1 那一筆紀錄。
4. 再點擊情境 5 那一筆紀錄。
5. 再次點擊情境 5 那一筆紀錄。

**預期結果**：步驟 3 在該筆紀錄下方原地展開球場示意圖並標示落點；步驟 4 收合步驟 3 的展開內容，改為展開情境 5 這筆（顯示「未記錄落點」，因為情境 5 沒有落點座標）；步驟 5 收合情境 5 這筆的展開內容，畫面回到全部收合狀態（Clarifications 2026-09-16，FR-004a）。

## 驗證情境 9（前端）：四個既有入口皆一致套用

分別從「某團對戰紀錄」「我的個人跨團對戰紀錄」「某團歷史戰績」「檢視好友的對戰紀錄」四個既有入口點進同一場情境 1～6 的比賽。

**預期結果**：四處看到的球員徽章、可展開的落點資訊、球員得失分統計內容完全一致（FR-010）——因為四者共用同一個 `MatchRecordDetailResponse` 與同一個 `MatchRecordDetailDialogComponent`。
