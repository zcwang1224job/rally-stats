# Quickstart: 我的團完整參與紀錄與戰績

## 前置條件

- 後端、前端服務皆已啟動。
- 會員 A：已完成信箱驗證，持有 `access_token`。
- 會員 B：已完成信箱驗證，持有 `access_token`。
- A 建立一個團（member-created），B 以會員身份加入該團並打完至少 1 場
  比賽，之後 B 退出該團。

## 情境 1：「我的團」同時顯示自建與加入過的團（US1，FR-001~003）

1. A 呼叫 `GET /members/me/groups`。
   **預期**：清單中出現該團，`is_creator=true`、`member_status="active"`。
2. B 呼叫 `GET /members/me/groups`。
   **預期**：清單中出現同一個團，`is_creator=false`、
   `member_status="left"`（B 已退出）。
3. 以訪客身份（無登入）加入過另一個團的情境（若有既有訪客測試資料）——該
   訪客身份**不**對應任何會員帳號，不會出現在任何會員的 `GET
   /members/me/groups` 清單中（FR-003，本情境無需額外操作驗證，屬既有
   `member_id IS NULL` 天生排除的既有事實）。

## 情境 2：點進團查看該團完整比賽清單、暱稱篩選、個人戰績圖表（US2，FR-004~006、FR-008~009）

1. B 呼叫 `GET /members/me/groups/{group_id}/history`（`group_id` 為情境 1
   已退出的那個團，該團另有一場 B 未參與的比賽）。
   **預期**：`200`，`matches` 陣列包含該團**所有**已完成比賽（含 B 未
   參與的那一場）；`my_stats.total_matches`/`total_wins`/`total_losses`/
   `win_rate` 只計 B 自己參與的場次；`my_stats.round_win_rates`/
   `opponent_records` 皆已計算完成，供前端繪製圖表。
2. B 加上 `?nickname=<某位球員暱稱>`（該球員未必是 B 本人的對手，也可能
   是 B 完全沒對戰過、但在該團其他比賽出現過的球員）再次呼叫。
   **預期**：`200`，`matches` 只反映該團**全部比賽**中有這位球員參與的
   場次（不限 B 本人是否也在場上）；`my_stats` 完全不受此篩選影響，維持
   與情境 1 相同的個人統計。
3. 呼叫方換成從未加入過此團的會員 C。
   **預期**：`403 GROUP_MEMBERSHIP_NEVER_HELD`。
4. B 呼叫另一個自己曾加入、但尚無任何已完成比賽的團的
   `.../history`。
   **預期**：`200`，`matches=[]`、`my_stats.total_matches=0`——前端顯示
   「尚無比賽紀錄」，非錯誤畫面（FR-008）。

## 情境 3：既有忘記管理PIN碼流程不受影響（US3，FR-007）

1. A 呼叫 `GET /members/me/groups`，取出自己建立的團那筆（
   `is_creator=true`）。
2. A 呼叫既有 `POST /groups/{group_id}/forgot-admin-pin`。
   **預期**：行為與擴充前完全一致（`200`，取得新 `admin_pin`/`admin_token`）
   ——本 feature 未修改 `forgot_admin_pin` 本身，僅擴充了清單的呈現內容。
3. 確認 B（`is_creator=false` 的那筆）在前端畫面上看不到「忘記管理PIN碼」
   這個操作（UI 層級檢查，非 API 層級——後端本來就沒有暴露給非建立者的
   PIN 復原端點）。

## 驗證通過標準

- 所有情境的「預期」項目皆吻合。
- `pytest`（後端單元/契約/整合測試）與 `ng test`（Vitest，前端）皆全數
  通過；`ruff`/`mypy --strict`/`ng lint` 皆無錯誤（憲章技術治理關卡）。
- 情境 2 步驟 1 的回應時間，人工抽測應在 3 秒內完成（SC-002，SHOULD 等級，
  非嚴格自動化效能測試）。
