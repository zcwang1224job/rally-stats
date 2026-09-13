# Quickstart: 會員個人設定（四大分區）

## 前置條件

- 後端、前端服務皆已啟動。
- 兩個已完成 Email 驗證的會員帳號 A、B（用於好友相關情境）。

## 情境 1：四分區皆可開啟，暱稱/密碼行為與既有一致（US1/US3）

1. 以會員 A 登入，開啟「會員專區 -> 個人設定」。
   **預期**：頁面呈現「基本設定／帳號詳細資訊／安全性／隱私設定」四個
   分區，皆可在不離開頁面的情況下切換（spec.md FR-024）。
2. 在「基本設定」分區修改暱稱並儲存。
   **預期**：與既有行為一致——`200`，出現「暱稱已更新」成功徽章，系統
   各處顯示身份之處反映新暱稱。
3. 在「安全性」分區輸入正確目前密碼＋相符的兩次新密碼並送出。
   **預期**：與既有行為一致——`200`，其他裝置的登入狀態失效，本裝置不
   中斷（contracts/member-settings-api.md）。

## 情境 2：語言偏好選單（US1）

1. 在「基本設定」分區開啟語言偏好選單。
   **預期**：呼叫 `GET /members/me/supported-languages` 取得選項，選單
   顯示「繁體中文」且為唯一選項、已選取（spec.md FR-004）。
2. 選擇「繁體中文」並送出（即使值未變）。
   **預期**：`PATCH /members/me/language` 回傳 `200`，出現成功徽章。

## 情境 3：登入紀錄顯示且不含 IP/地理位置（US2）

1. 以會員 A 用 Email＋密碼登出後重新登入兩次（模擬多次主動登入）。
2. 開啟「帳號詳細資訊」分區。
   **預期**：`GET /members/me/login-records` 回傳的 `records` 由新到舊
   列出，每筆僅含 `created_at`、`device_category`（`"desktop"` 或
   `"mobile"`），**不含**任何 IP/地理位置欄位（spec.md FR-007）。
3. 在瀏覽器維持登入狀態超過 access token 效期，觸發一次 token refresh
   （或直接呼叫既有 `POST /auth/refresh`）。
4. 重新整理「帳號詳細資訊」分區。
   **預期**：登入紀錄筆數 MUST 與步驟 2 完全相同，token refresh MUST NOT
   產生新紀錄（Clarifications 2026-09-13 第 4 題）。

## 情境 4：隱私設定——允許被搜尋（US4）

1. 以會員 A 登入，於「隱私設定」分區將「允許被搜尋」關閉。
   **預期**：`PATCH /members/me/privacy` 回傳 `200`，出現成功徽章。
2. 立即（不需重新登入）以會員 B 呼叫 `GET /members/search?user_number=
   <A的編號>`。
   **預期**：`404`，`error_code` 為 `MEMBER_NOT_FOUND`——與 A 帳號真的
   不存在時完全相同的回應（spec.md FR-017、SC-005）。
3. 會員 A 重新開啟「允許被搜尋」。
   **預期**：會員 B 立即重新搜尋，`200` 成功找到 A（不需等待/重新登入）。

## 情境 5：隱私設定——好友可查看戰績（US4）

前置：會員 A、B 已成立好友關係（既有好友邀請流程）。

1. 會員 A 將「好友可查看我的戰績」關閉。
2. 會員 B 呼叫 `GET /members/{A的member_id}/match-records`。
   **預期**：`403`，`error_code` 為 `MATCH_RECORDS_PRIVATE`（spec.md
   FR-018）。
3. 會員 A 重新開啟此設定；會員 B 立即重新呼叫同一端點。
   **預期**：`200`，回傳形狀與既有 `GET /members/me/match-records`
   相同，MUST 同時包含逐場對戰紀錄明細（`matches`）與彙總統計
   （`total_matches`/`win_rate`/`round_win_rates`/`opponent_records`）
   ——不得只回傳其中一種（FR-018 涵蓋兩者，Clarifications 第 2 題）。
4. 呼叫 `GET /members/{A的member_id}/match-records/{任一 match_id}`。
   **預期**：`200`，回傳形狀與既有 `GET /members/me/match-records
   /{match_id}` 相同。

## 情境 6：非好友一律無法查看戰績（US4 Edge Case）

前置：會員 C（與會員 A **未**成立好友關係）已登入。

1. 不論會員 A 的「好友可查看我的戰績」設定為開或關，會員 C 呼叫
   `GET /members/{A的member_id}/match-records`。
   **預期**：`403`，`error_code` 為 `FRIENDSHIP_REQUIRED`——與 A 的隱私
   設定狀態無關，一律拒絕（spec.md FR-019）。

## 情境 7：未驗證信箱會員無法開啟任一分區（Edge Case）

1. 以一個尚未完成 Email 驗證的會員帳號登入，嘗試開啟「個人設定」頁面
   任一分區（例如直接呼叫 `PATCH /members/me/language`）。
   **預期**：`403`，`error_code` 為 `EMAIL_NOT_VERIFIED`，沿用既有信箱
   驗證關卡導向規則（spec.md FR-025；不新增例外）。
