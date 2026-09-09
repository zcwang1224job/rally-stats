# Quickstart: 固定搭檔循環賽——手動配對後，剩餘未配對者自動隨機配對

## 前置條件

- 後端、前端服務皆已啟動。
- 一個比賽模式為「雙打」、排點機制為「固定搭檔」、配對來源為「手動配對」
  的團，持有 `admin_token`。
- 團內有 8 位現役成員（P0~P7），皆尚未配對。

## 情境 1：完全沒手動配對，直接產生賽程（US1 驗收情境 2）

1. 直接呼叫 `POST /groups/{group_id}/next-round`（不帶 `temporary_pairings`）。
   **預期**：`200`，賽程正常產生；查詢該輪比賽，8 位成員 MUST 全部出現在
   某場比賽中，沒有人被排除（SC-001）。

## 情境 2：部分手動配對，剩下的人直接產生賽程時自動補齊（US1 驗收情境 1）

1. 用既有 `PATCH /groups/{group_id}/partnerships` 把 P0+P1、P2+P3 配成兩組
   正式搭檔（P4~P7 仍未配對）。
2. 直接呼叫 `POST /groups/{group_id}/next-round`（不帶
   `temporary_pairings`，模擬管理員沒有使用預覽功能）。
   **預期**：`200`，該輪賽程涵蓋全部 8 人；P0/P1 與 P2/P3 的正式搭檔組合
   MUST 維持不變（驗證 FR-003）；P4~P7 MUST 被自動隨機配成兩組暫時配對
   一起出現在賽程中。
3. 查詢 `GET /groups/{group_id}/partnerships`。
   **預期**：`partnerships` 陣列仍然只有 P0+P1、P2+P3 兩組——步驟 2 自動
   補齊的 P4~P7 暫時配對 MUST NOT 出現在正式搭檔清單中（SC-005）。

## 情境 3：預覽並調整暫時配對，產生賽程時採用調整後的結果（US2）

1. 沿用情境 2 步驟 1 的正式搭檔設定（P4~P7 未配對）。
2. 呼叫 `POST /groups/{group_id}/partnerships/random-preview`。
   **預期**：`200`，`pairings` 回傳 P4~P7 隨機配成的兩組（例如
   `[(P4,P6), (P5,P7)]`，實際組合隨機）。
3. 假設步驟 2 回傳 `[(P4,P6), (P5,P7)]`，管理員想改成 `(P4,P5)` 一組、
   `(P6,P7)` 一組——呼叫 `POST /groups/{group_id}/next-round`，帶入
   `{"temporary_pairings": [{"player_a_id": "<P4>", "player_b_id": "<P5>"}, {"player_a_id": "<P6>", "player_b_id": "<P7>"}]}`。
   **預期**：`200`，該輪賽程 MUST 使用 `(P4,P5)`／`(P6,P7)` 這個調整後的
   組合，MUST NOT 是步驟 2 原本隨機出的 `(P4,P6)`／`(P5,P7)`（FR-007）。
4. 再次呼叫 `GET /groups/{group_id}/partnerships`。
   **預期**：`partnerships` 陣列仍然只有情境 2 步驟 1 那兩組正式搭檔，
   `(P4,P5)`／`(P6,P7)` 這組暫時配對 MUST NOT 出現在裡面。

## 情境 4：所有人都手動配對完畢，不觸發任何隨機配對（US1 驗收情境 3）

1. 用既有 `PATCH /groups/{group_id}/partnerships` 把全部 8 人配成 4 組
   正式搭檔。
2. 呼叫 `POST /groups/{group_id}/next-round`。
   **預期**：`200`，賽程完全依照這 4 組正式搭檔產生，內容與擴充前的
   既有行為一致。

## 情境 5：「自動配對」模式不受影響（US3 回歸驗證）

1. 把團的配對來源改為「自動配對」。
2. 呼叫 `POST /groups/{group_id}/partnerships/random-preview`。
   **預期**：`409 PARTNER_SOURCE_MISMATCH`。
3. 呼叫 `POST /groups/{group_id}/next-round`（可選擇帶或不帶
   `temporary_pairings`）。
   **預期**：`200`，賽程配對結果 MUST 與擴充前既有「自動配對」邏輯一致
   （依歷史配對次數重新計算），`temporary_pairings`（若有帶）MUST 被
   忽略，不影響結果。

## 情境 6：暫時配對過期後的重新驗證（Edge Cases）

1. 沿用情境 3 步驟 2 取得的 `random-preview` 結果（例如涵蓋 P4~P7）。
2. 在呼叫 `next-round` 之前，先用 `PATCH /groups/{group_id}/partnerships`
   把 P4 跟 P6 配成一組**正式**搭檔（P4、P6 現在已經有正式搭檔了）。
3. 呼叫 `POST /groups/{group_id}/next-round`，仍然帶上步驟 1 那份（現在
   有部分過期的）`temporary_pairings`。
   **預期**：`200`，賽程 MUST 使用 P4+P6 這組新的正式搭檔（而非
   `temporary_pairings` 裡過期的組合）；P5、P7 MUST 被重新自動隨機配成
   一組補齊該輪賽程。

## 驗證通過標準

- 所有情境的「預期」項目皆吻合。
- `pytest`（後端單元/契約/整合測試）與 `ng test`（Vitest，前端）皆全數
  通過；`ruff`/`mypy --strict`/`ng lint` 皆無錯誤（憲章技術治理關卡）。
- 情境 2、3 的暫時配對呈現方式，人工檢視確認以圖示/文字（而非純顏色）
  與正式搭檔區隔（FR-008 US2 驗收情境 1，憲章原則 VII）。
