# Quickstart: 團內成員視圖

## 前置條件

- 一個已有 ≥2 位成員（含 1 位 Guest、1 位已登入會員，皆為 `active`）、
  排程機制為 `fair_rotation`、已完成至少 2 輪比賽（含至少 1 場自然
  完成、1 場提前結束/捨棄）的團。
- 團內至少 1 位成員已於某輪開始前主動退出或被踢除。
- 已取得該 Guest 成員的 `guest_session_token`、該會員的 member access
  token、以及該團 `group_id`。

## 情境 1：一般成員導覽與唯讀賽程頁（US1，FR-001~004）

1. 以 Guest token 呼叫 `GET /groups/{group_id}/member-schedule
   ?guest_session_token={token}`。
   **預期**：`200`，回應形狀與管理頁 `GET /groups/{group_id}/schedule`
   相同（`current_round_number`/`courts[].current_match`/
   `waiting_reason`/`roster`），但呼叫端點與驗證方式不同（無需管理
   PIN）。
2. 不帶任何 token 呼叫同一端點。
   **預期**：`403 MEMBERSHIP_REQUIRED`。
3. 前端確認畫面上不存在任何「新增場地」「Next Round」「踢除成員」
   等管理員專屬按鈕（比照 007 quickstart.md 情境 4 之靜態掃描精神）。
4. 對該團任一場地呼叫既有 `.../score` 端點（007 已建立）觸發一次
   +1；1 秒內，訂閱同一 Ably 頻道的一般成員畫面應同步更新（沿用
   007 既有事件，本 feature 不新增）。

## 情境 2：團內戰績四狀態判定（US2，FR-005~010）

1. 呼叫 `GET /groups/{group_id}/standings?guest_session_token={token}`。
2. **預期**：`rounds` 陣列涵蓋第 1 輪起至目前輪次；`members[]` 內
   每位成員的 `rounds` 物件對每個輪次皆有值，四種狀態之一：
   - 已完賽且該員所屬隊伍等於 `winner_team` → `"won"`
   - 已完賽但該員所屬隊伍不等於 `winner_team` → `"lost"`
   - 候補中/該輪尚未加入/所屬比賽被捨棄/比賽仍進行中 → `"did_not_play"`
   - 該員於此輪開始前已離開/被踢 → `"left"`（且該員後續所有輪次
     皆為 `"left"`，不再變回 `"did_not_play"`）
3. 針對前置條件中「已於某輪開始前退出的成員」，逐一檢查其退出輪次
   之後的每一輪，確認皆為 `"left"`。

## 情境 3：團內對戰紀錄（US3，FR-011、FR-012）

1. 呼叫 `GET /groups/{group_id}/match-records?guest_session_token={token}`。
2. **預期**：`matches[]` 僅包含 `status == 'completed'` 的比賽，每筆
   含 `round_number`/`team_a`/`team_b`/`score_a`/`score_b`/
   `winner_team`；提前結束/捨棄的比賽 MUST NOT 出現。

## 情境 4：退出組團（US4，FR-013~016）

1. Guest 成員呼叫 `POST /groups/{group_id}/roster/{roster_entry_id}/leave`
   body `{"guest_session_token": "{token}"}`。
   **預期**：`201`，`status: "left"`。
2. 立即再用同一 `guest_session_token` 呼叫情境 1 的端點。
   **預期**：`403 MEMBERSHIP_REQUIRED`（token 已失效）。
3. 確認該團所有場地控制板收到既有 `member.left` Ably 事件；賽程表
   未因此觸發 Round 重新排點（`current_round_number` 不變）。
4. 用另一位成員（非本人）的 token 嘗試對第 1 步的 `roster_entry_id`
   呼叫同一端點。
   **預期**：`404 ROSTER_ENTRY_NOT_FOUND`（不可代替他人退出）。

## 情境 5：會員跨團對戰紀錄（US5，FR-017~020）

1. 已登入會員呼叫 `GET /members/me/match-records`（Bearer token）。
2. **預期**：`matches[]` 涵蓋該會員名下所有團的已完成比賽，含
   `group_name`；`total_matches`/`total_wins`/`total_losses`/
   `win_rate` 正確彙總。
3. 確認 `matches[]` 不包含前置條件中該 Guest 成員的任何一場比賽
   （即使日後該 Guest 使用同一瀏覽器註冊為此會員帳號，兩者
   `roster_entries` 記錄無任何關聯欄位，見 research.md #9）。

## 驗證通過標準

- 所有 5 個情境之「預期」項目皆吻合。
- `pytest`（單元/契約/整合）與前端 `ng test` 皆全數通過；`ruff`/
  `mypy --strict`/`ng lint` 皆無錯誤。
- 情境 2 的四狀態判定 MUST 有涵蓋全部四種狀態、且涵蓋「候補中」
  「捨棄」「加入前」「退出後」四種 `did_not_play`/`left` 成因的單元
  測試（不可僅靠本 quickstart 手動情境驗證，屬 constitution 原則 II
  之強制測試範圍）。
