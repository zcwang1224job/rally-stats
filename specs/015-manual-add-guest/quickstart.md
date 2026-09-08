# Quickstart: 團長手動新增訪客入團

## 前置條件

- 後端、前端服務皆已啟動。
- 已開一個團，團長持有 `admin_token`（開團回應或 `/groups/reauth` 取得）。
- 該團 `max_members` 設定為一個容易測試「額滿」情境的小數字（例如 2）。

## 情境 1：團長手動新增一位訪客（US1，FR-001~005、FR-009~010）

1. 團長呼叫 `POST /groups/{group_id}/members`，`Authorization: Bearer
   <admin_token>`，body `{ "nickname": "小明" }`。
   **預期**：`201`，回應含 `roster_entry_id`／`nickname="小明"`／
   `guest_session_token`（非 null）／`created_new=true`。
2. 團長呼叫既有 `GET /groups/{group_id}/schedule`（或既有花名冊查詢）。
   **預期**：「小明」出現在花名冊中，`status="active"`，尚未上場（可被
   排入下一場比賽）。
3. 團長不重新發起新的流程，直接再呼叫一次
   `POST /groups/{group_id}/members`，body `{ "nickname": "小華" }`。
   **預期**：`201`，成功建立第二筆項目（FR-009：可連續新增）。
4. 承上，若這時團的現役人數已達 `max_members`，團長再呼叫一次
   `POST /groups/{group_id}/members`。
   **預期**：`409 GROUP_FULL`，不建立任何新項目。
5. 團長對一個已解散的團呼叫 `POST /groups/{group_id}/members`。
   **預期**：`409 GROUP_DISBANDED`。
6. 團長帶錯的 `group_id`（不是自己 token 對應的團）呼叫此端點。
   **預期**：`401 ADMIN_TOKEN_INVALID`。
7. 團長帶空白暱稱 `{ "nickname": "  " }` 呼叫此端點。
   **預期**：`400 NICKNAME_REQUIRED_FOR_GUEST`。

## 情境 2：訪客用自己的裝置查看賽況（US2，FR-006）

1. 延續情境 1 步驟 1 取得的 `guest_session_token`，組出連結
   `http://localhost:4200/guest-access/<guest_session_token>`。
2. 用另一支裝置（或無痕視窗，確保沒有既有 localStorage 狀態）開啟此連結。
   **預期**：自動導向 `/groups/{group_id}/member-view`，畫面顯示「小明」
   本人的賽況與輪替狀態，過程不需要輸入密碼、不需要再走一次加入流程。
3. 重新整理該頁面。
   **預期**：因為 `setGuestSessionToken()` 已寫入 localStorage，重新整理
   後仍維持登入該訪客身份，行為與自行加入的訪客完全一致。

## 情境 3：後續功能對手動新增的訪客一視同仁（驗證重用設計是否成立）

1. 團長透過既有排點/比賽功能，把「小明」排入一場比賽並完成比賽。
2. 團長對「小明」呼叫既有 `DELETE /groups/{group_id}/members/{roster_entry_id}`
   （踢人）。
   **預期**：`200`，行為與踢除一位自行加入的訪客完全相同——不需要任何
   額外程式碼改動即可涵蓋（若需要改動，代表重用設計有誤）。

## 驗證通過標準

- 所有情境的「預期」項目皆吻合。
- `pytest`（後端 unit/contract/integration）與 `ng test`（Vitest，前端）
  皆全數通過；`ruff`/`mypy --strict`/`ng lint` 皆無錯誤（憲章技術治理
  關卡）。
- 情境 1 步驟 1，人工抽測應在 3 秒內完成（呼應 spec SC-001 的「30 秒內
  完成新增」，含使用者輸入時間）。
