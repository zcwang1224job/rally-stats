# Quickstart: 我的團最終團隊排名

## 前置條件

- 後端、前端服務皆已啟動。
- 一位已登入且信箱已驗證（或至少通過 `require_member`）的會員帳號，
  持有其會員 JWT。
- 一個團，該會員曾經是這個團的正式成員（現役／已離開／已被踢除皆可，
  research.md #5）。

## 情境 1：已解散的團，「我的團」顯示全團最終排名（US1）

1. 一個團已解散，解散前 P0~P3 四位參與者累計：P0 五勝一敗、P1 四勝二敗
   （後來離開）、P2 三勝三敗（後來被踢除）、P3 完全沒打過已完成的比賽。
   會員 A 就是 P0。
2. 會員 A 登入後開啟「我的團」，點進這個已解散的團。
3. 呼叫 `GET /members/me/groups/{group_id}/history`。
   **預期**：`200`，`final_standings` 依序為 P0（`rank: 1, is_self:
   true`）、P1（`rank: 2, current_status: "left"`）、P2（`rank: 3,
   current_status: "kicked"`）、P3（`rank: 4, total_matches: 0`）——驗證
   涵蓋範圍（含已離開/被踢除）、跳號規則、自己標示、與「尚無比賽紀錄」
   狀態（spec.md FR-002/FR-005/FR-006/FR-007/FR-011）。
4. 頁面上「最終團隊排名」區塊 MUST 與既有「我的戰績」（個人統計）、
   「對戰紀錄」（全團比賽清單）兩區塊並存，不取代既有內容（FR-001）。
5. 在資料不變的情況下，對同一個 `group_id` 連續呼叫
   `GET /members/me/groups/{group_id}/history` 三次（模擬多次重新整理）。
   **預期**：三次回應中 `final_standings` 的 `rank`／排列順序 100% 完全
   一致，不會忽先忽後地跳動（spec.md FR-005、SC-005）。

## 情境 2：尚未解散的團，同樣能在「我的團」看到快照（US2）

1. 一個團尚未解散，已有部分比賽完成。會員 B 曾經加入過這個團（現役或
   已離開皆可）。
2. 會員 B 開啟「我的團」，點進這個團。
3. 呼叫 `GET /members/me/groups/{group_id}/history`。
   **預期**：`200`，`final_standings` 反映呼叫當下該團已完成比賽的
   累計排名（FR-012）——不要求秒級即時推播，重新整理頁面即可看到最新
   資料。

## 情境 3：訪客參與者與同一會員多次加入的合併（Edge Cases）

1. 一個團裡，P4 是以訪客身份加入並打過幾場比賽的參與者（無會員帳號）。
2. 會員 C 曾經加入這個團、中途退出，後來又重新加入（產生兩筆歷史
   `RosterEntry`），兩次加入期間分別打贏 2 場、3 場。
3. 呼叫 `GET /members/me/groups/{group_id}/history`。
   **預期**：`final_standings` 中 P4 正常出現、沒有任何「訪客」特殊標記
   （spec.md FR-002）；會員 C MUST 只出現一列，`total_wins` 為兩次加入
   期間的加總（5 勝），而不是分成兩列各自列出（research.md #1，spec.md
   Edge Cases）。

## 情境 4：已捨棄的比賽不計入、固定搭檔以個人為單位

1. 團的排點機制為「固定搭檔」，一場比賽因團解散被強制結束、標記為
   `abandoned`（尚未產生勝負）。
2. 另有一場已正常完成的比賽，P5、P6 是搭檔（同隊）。
3. 呼叫 `GET /members/me/groups/{group_id}/history`。
   **預期**：`abandoned` 那場 MUST NOT 影響任何人的 `total_matches`／
   `total_wins`／`total_losses`（FR-003）；P5、P6 在 `final_standings`
   中 MUST 各自獨立列出自己的勝敗場次，不合併成一個「搭檔組合」列
   （FR-009）。

## 情境 5：完全沒有已完成比賽的團

1. 一個團剛成立，尚未有任何已完成的比賽。
2. 呼叫 `GET /members/me/groups/{group_id}/history`。
   **預期**：`final_standings` 陣列包含所有曾參與者，但每一列
   `total_matches`／`total_wins`／`total_losses` 皆為 `0`；前端 MUST
   顯示清楚的「尚無比賽紀錄」整體提示，不得顯示錯誤或空白畫面（FR-008）。

## 驗證通過標準

- 所有情境的「預期」項目皆吻合。
- `pytest`（後端單元/整合/契約測試）與 `ng test`（Vitest，前端）皆全數
  通過；`ruff`/`mypy --strict`/`ng lint` 皆無錯誤（憲章技術治理關卡）。
- 情境 1 的「自己所在列」標示（FR-011），人工檢視確認以圖示/文字（而非
  純顏色）與其他列區隔（憲章原則 VII）。
- 既有 `test_member_groups_history_flow.py`（014 既定情境：比賽清單、
  個人統計、`nickname` 篩選）全數維持通過，證明本次擴充未破壞既有行為
  （回歸驗證）。
