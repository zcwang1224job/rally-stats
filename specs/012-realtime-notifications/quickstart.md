# Quickstart: 即時通知功能

## 前置條件

- 後端、前端服務皆已啟動（延續既有 `docker compose` / 本地開發流程）。
- 已有兩個已完成信箱驗證的會員帳號：會員 A（申請人）、會員 B（接收
  通知者），皆已登入並持有各自的 `access_token`。

## 情境 1：即時收到好友申請通知（US1，FR-001~003，SC-001、SC-002）

1. 會員 B 開啟系統任一主要頁面（例如 `/groups`），保持連線中。
2. 呼叫 `POST /friends/requests`（以會員 A 的 `access_token`），body
   `{ "addressee_user_number": "<會員B的使用者編號>" }`。
3. **預期**：2 秒內，會員 B 的前端訂閱到 Ably `member:{B的
   member_id}:notifications` 頻道的 `notification.created` 事件，
   `nav-shell` 的未讀角標數字 +1（不需重新整理頁面）。
4. 呼叫 `GET /notifications`（以會員 B 的 `access_token`）。
   **預期**：回應內含剛建立的通知，`type="friend_request"`、
   `read=false`、`friend_request.status="pending"`、
   `friend_request.requester.member_id` 等於會員 A。
5. 將會員 B 登出（或直接不建立 Ably 連線），重複步驟 2（會員 A 再對
   會員 B 送出另一筆申請，需先用不同會員或先撤銷/處理前一筆——若
   `FRIEND_REQUEST_ALREADY_PENDING` 擋下，改用會員 C 對會員 B 送出）。
   之後會員 B 重新登入呼叫 `GET /notifications/unread-count`。
   **預期**：`unread_count` 正確反映離線期間收到的通知，未遺失
   （FR-003，SC-002）。

## 情境 2：通知列表與已讀/未讀狀態（US2，FR-004、FR-005、FR-013）

前置：會員 B 已累積至少 2 則未讀通知（重複情境 1 的步驟 2，改用不同
申請人會員）。

1. 呼叫 `GET /notifications`。
   **預期**：`notifications[]` 依 `created_at` 新到舊排序，
   `unread_count` 等於實際未讀筆數；此次「查詢」本身 MUST NOT 改變任何
   一則的 `read` 狀態（FR-013——開啟列表不會自動已讀）。
2. 呼叫 `POST /notifications/{其中一則的 notification_id}/read`。
   **預期**：回應 `read=true`；再次呼叫 `GET
   /notifications/unread-count`，`unread_count` 減 1。
3. 對同一則通知重複呼叫一次 `.../read`。
   **預期**：回應仍為 `read=true`，`unread_count` 不再重複減少
   （冪等）。

## 情境 3：全部標示已讀（US2，FR-008）

前置：會員 B 尚有 ≥1 則未讀通知。

1. 呼叫 `POST /notifications/read-all`。
   **預期**：回應 `marked_count` 等於呼叫前的未讀筆數；`GET
   /notifications/unread-count` 回傳 `unread_count=0`。
2. 立即重複呼叫一次 `POST /notifications/read-all`。
   **預期**：`marked_count=0`（無任何未讀可標記，非錯誤）。

## 情境 4：點擊通知直接前往相關內容（US3，FR-007）

1. 於通知列表點擊一則 `type="friend_request"` 的未讀通知
   （前端行為，非純 API 驗證）。
2. **預期**：畫面導向 `/friends/requests`（可查看/處理該筆好友申請的
   既有頁面）；該則通知同時轉為已讀（`POST .../read` 已於導向前呼叫，
   驗證方式同情境 2 步驟 2）。

## Edge Case 驗證：好友申請已在其他管道被處理（Assumptions）

1. 會員 A 對會員 B 送出好友申請（同情境 1 步驟 2）。
2. 在會員 B 點擊該通知**之前**，直接呼叫
   `POST /friends/requests/{friend_request_id}/accept`（以會員 B 的
   `access_token`，模擬會員 B 先從 `/friends/requests` 頁面直接處理，
   而非透過通知進入）。
3. 之後才呼叫 `GET /notifications`（或點擊該通知）。
   **預期**：`friend_request.status="accepted"`（即時查詢的最新狀態，
   非建立通知當下的 `"pending"` 快照）；點擊該通知導向
   `/friends/requests` 時，該筆申請已不在待處理列表中，畫面呈現「已
   無待處理項目」而非誤導使用者去接受一筆早已處理過的申請。

## Edge Case 驗證：僅通知實際接收者（FR-009）

1. 會員 A 對會員 B 送出好友申請。
2. 以**會員 C**（與此次申請無關的第三人）的 `access_token` 呼叫
   `GET /notifications`。
   **預期**：回應中**不含**這則通知（`unread_count` 不受影響）。
3. 以會員 C 的 `access_token` 嘗試呼叫
   `POST /notifications/{該則屬於會員B的notification_id}/read`。
   **預期**：`404 NOTIFICATION_NOT_FOUND`（不洩漏該通知是否存在）。

## 驗證通過標準

- 所有情境的「預期」項目皆吻合。
- `pytest`（後端單元/契約/整合測試）與 `ng test`（Vitest，前端）皆全數
  通過；`ruff`/`mypy --strict`/`ng lint` 皆無錯誤（憲章技術治理關卡）。
- 情境 1 之「2 秒內同步」建議以簡易計時（呼叫 API 到前端事件觸發的
  時間差）人工抽測至少 3 次，非嚴格自動化效能測試（SC-001 為 SHOULD
  等級的可觀察體驗指標，非 blocking gate，比照 007 quickstart.md 情境 1
  之既有精神）。
