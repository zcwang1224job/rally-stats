# Quickstart: 比賽加減分紀錄與趨勢圖

## 前置條件

- 後端、前端服務皆已啟動。
- 會員 A：已建立一個團並加入，會員 B 也加入該團。
- 該團有一場已完成的比賽（A、B 分別代表 A/B 隊），比賽是在本功能上線
  **之後**才透過控制板/管理頁進行加減分直到自然達標結束（`status =
  "completed"`），過程中至少一次扣分（模擬操作修正）。
- 另有一場「模擬舊資料」的已完成比賽：直接在資料庫將其標記為
  `completed` 且不建立任何對應的 `score_events` 列，代表本功能上線前就
  已完成的比賽（US3）。
- 另有一場「模擬跨越上線時間點」的已完成比賽：只保留部分
  `score_events`（例如刻意刪除前幾筆，使第一筆事件的 `score_a +
  score_b != 1`），代表比賽開打於上線前、結束於上線後（FR-006a）。

## 情境 1：團內對戰紀錄點進比賽看到完整加減分紀錄（US1，FR-001/002/005）

1. 以 B 的 Guest 現役 token（或已登入的現役 Member）呼叫 `GET
   /groups/{group_id}/match-records/{match_id}`（`match_id` 為上線後
   完成、有完整紀錄的那場）。
   **預期**：`200`，`record_completeness = "complete"`，`events`
   陣列依 `elapsed_seconds` 升冪排序，且第一筆的 `score_a + score_b ==
   1`；陣列中可見至少一筆 `delta = -1` 的紀錄（對應测試資料中的扣分）。
2. 以從未加入過此團、且未持有此團任何 Guest token 的另一位使用者呼叫
   同一端點。
   **預期**：`403 MEMBERSHIP_REQUIRED`——與既有 `GET
   /groups/{group_id}/match-records` 清單端點的授權結果一致（FR-005）。

## 情境 2：趨勢圖數值與最終比分一致、扣分呈現下降（US2，FR-003/004）

1. 沿用情境 1 步驟 1 的回應，比對 `events` 最後一筆的 `score_a`/
   `score_b` 與回應最上層的 `score_a`/`score_b`（正式最終比分）。
   **預期**：兩者相等。
2. 前端開啟該比賽詳情彈出視窗。
   **預期**：畫面上的趨勢圖，扣分那個時間點對應那一方的曲線呈現下降，
   而非單調上升；兩條曲線以非純色彩的方式可區分（例如一實一虛，並有
   文字圖例）——FR-008 之無障礙檢查點，人工檢視。
3. 找一位未參與開發的人，只給看步驟 2 的趨勢圖（遮住/不展示逐筆文字
   紀錄清單），請其回答「哪一方獲勝」與「過程中是否出現扣分修正」。
   **預期**：兩題皆答對（SC-005，人工驗收，非自動化測試）。

## 情境 3：舊比賽沒有紀錄時顯示清楚提示（US3，FR-006）

1. 呼叫「模擬舊資料」那場比賽對應的詳情端點
   （視其所屬清單為 `GET /groups/{group_id}/match-records/{match_id}`
   或 `GET /members/me/match-records/{match_id}`）。
   **預期**：`200`（不是錯誤），`record_completeness = "none"`，
   `events = []`；`score_a`/`score_b`/`winner_team` 等基本資訊仍正常
   回傳（FR-007）。前端顯示明確的「無加減分紀錄」提示，不出現空白圖表。

## 情境 4：跨越上線時間點的比賽顯示部分紀錄並註明不完整（FR-006a）

1. 呼叫「模擬跨越上線時間點」那場比賽對應的詳情端點。
   **預期**：`200`，`record_completeness = "partial"`，`events`
   非空但第一筆的 `score_a + score_b != 1`。前端顯示現有的加減分紀錄與
   趨勢圖，並附上「此為部分紀錄，比賽前段未被記錄」之類的明確提示。

## 情境 5：會員跨團/我的團兩個清單共用同一支端點（US1，FR-001/005）

1. 以會員 B 的 Bearer token 呼叫 `GET
   /members/me/match-records/{match_id}`（同情境 1 的那場比賽）。
   **預期**：`200`，回應形狀與情境 1 完全相同。
2. 讓 B 退出該團後，重複呼叫同一端點。
   **預期**：仍為 `200`（`verify_ever_group_member` 只要求「曾經」是
   成員），與既有 `GET /members/me/groups/{group_id}/history` 的既有
   存取邊界一致。
3. B 退出該團後，改呼叫團內對戰紀錄分頁專用的 `GET
   /groups/{group_id}/match-records/{match_id}`（同一場比賽）。
   **預期**：`403 MEMBERSHIP_REQUIRED`——因為 B 已非現役成員，證明兩個
   端點的授權語意確實不同（步驟 2 用「曾經」通過，這裡用「現役」被拒）。
4. 以從未加入過此團的會員 C 呼叫 `GET
   /members/me/match-records/{match_id}`。
   **預期**：`403 GROUP_MEMBERSHIP_NEVER_HELD`。
5. **前端整合檢查**（對應 tasks.md T013/T015a 之修正——避免只驗證 API
   本身、漏掉前端呼叫錯誤端點的情況）：B 退出該團後，於前端「我的團 →
   歷史」頁面點擊情境 1 那場比賽。
   **預期**：仍可正常開啟詳情彈出視窗看到完整紀錄，而不是被拒絕——前端
   MUST 是呼叫步驟 1/2 驗證過的 `GET /members/me/match-records/{match_id}`，
   而非步驟 3 已證實 B 退出後會失敗的
   `GET /groups/{group_id}/match-records/{match_id}`。

## 驗證通過標準

- 所有情境的「預期」項目皆吻合。
- `pytest`（後端單元/契約/整合測試）與 `ng test`（Vitest，前端）皆全數
  通過；`ruff`/`mypy --strict`/`ng lint` 皆無錯誤（憲章技術治理關卡）。
- 情境 1 步驟 1 的回應時間，人工抽測應在 3 秒內完成（SC-001，SHOULD
  等級，非嚴格自動化效能測試，比照既有 014 基準）。
