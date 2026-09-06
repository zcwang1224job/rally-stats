# API Contract: 團內成員視圖

所有端點皆需通過 research.md #5 之 `resolve_active_roster_membership()`
身分驗證——呼叫者 MUST 提供以下其中一種、且對應的 `RosterEntry.status`
MUST 為 `active`：

- `guest_session_token`（query 參數 `?guest_session_token=...`）
- `Authorization: Bearer <member_access_token>`（006 既有格式），且
  該會員在此團仍有一筆 `active` 的 `RosterEntry`

兩者皆缺，或提供但查無對應 active 記錄，一律回傳 `MEMBERSHIP_REQUIRED`
（403）——不區分「從未加入」「已退出」「token 打錯」（research.md #5，
比照 004 對 Guest 相關錯誤的統一失敗語意，不洩漏額外細節）。此驗證
**不**檢查 `Group.status`（disbanded 團仍可查閱，見 Edge Cases）。

## `GET /groups/{group_id}/member-schedule`

**用途**：一般成員的唯讀賽程頁（US1，FR-003、FR-004）。

**回應** `200`：`ScheduleResponse`（003/007 既有型別，完整重用，見
research.md #6）。

**錯誤**：`MEMBERSHIP_REQUIRED`。

**即時同步**：前端訂閱既有 Ably 頻道（不需新事件，見 research.md #6）：
`court:{group_id}:{court_id}` 之 `match.scoreUpdated`/`match.ended`/
`rotation.updated`/`match.nextRound`；`group:{group_id}:notifications`
之 `member.joined`/`member.left`。

---

## `GET /groups/{group_id}/standings`

**用途**：團內戰績頁（US2，FR-005~010）。

**回應** `200`：`GroupStandingsResponse`（見 data-model.md）。

**錯誤**：`MEMBERSHIP_REQUIRED`。

---

## `GET /groups/{group_id}/match-records`

**用途**：團內對戰紀錄頁（US3，FR-011、FR-012）。

**Query 參數**：`page: int = 1`（沿用 004 既有分頁慣例）。

**回應** `200`：`GroupMatchRecordsResponse`（見 data-model.md）。

**錯誤**：`MEMBERSHIP_REQUIRED`。

---

## `POST /groups/{group_id}/roster/{roster_entry_id}/leave`

**用途**：退出組團（US4，FR-013~016）。

**Request Body**：`LeaveGroupRequest`（見 data-model.md）——Guest 身分
提供 `guest_session_token`；已登入會員則不需 body（走 `Authorization`
header）。

**授權**：呼叫者 MUST 就是 `roster_entry_id` 本人——Guest 情境比對
`guest_session_token` 相符；Member 情境比對 `roster_entry.member_id`
等於已驗證會員之 `id`。不符（或 `roster_entry_id` 不存在、已非
`active`）一律回傳 `ROSTER_ENTRY_NOT_FOUND`（404，同 003 `kick_member`
既有錯誤代碼，不新增專屬代碼）。

**回應** `201`：`LeaveGroupResponse`（見 data-model.md）。

**副作用**（重用 003 既有 `handle_member_left()`，research.md #7）：
- 該團所有場地控制板 MUST 收到既有 `member.left` Ably 事件
  （`group:{group_id}:notifications`，003 已定義，本 feature 不新增
  payload 欄位）。
- 賽程表中「排隊中」與此成員相關的比賽依既有規則自動調整；
  「進行中」比賽不受影響；MUST NOT 觸發 Round 重新排點。
- Guest 情境：回應成功後，該 `guest_session_token` 立即失效（下一次
  `GET /groups/by-guest-token/{token}` 或本規格任何端點皆回傳
  `MEMBERSHIP_REQUIRED`/`LINK_NOT_FOUND`，因 `status` 已非 `active`）。

---

## `GET /members/me/match-records`

**用途**：會員頁面跨團對戰紀錄（US5，FR-017~020）。需 006 既有
`require_member`（MUST 已登入；不要求 `verification_status ==
'verified'`——查看自己歷史紀錄不屬於 006 FR-009 鎖定範圍內的「功能」，
比照 `GET /members/me` 之既有寬鬆基準）。

**Query 參數**：`page: int = 1`。

**回應** `200`：`MemberMatchRecordsResponse`（見 data-model.md，含
`total_matches`/`total_wins`/`total_losses`/`win_rate` 彙總統計）。

**錯誤**：`MEMBER_TOKEN_INVALID`（006 既有代碼，`require_member`
本身之錯誤）。

**保證**（research.md #9，資料模型層面天然滿足，非本端點額外邏輯）：
回應 MUST NOT 包含任何該會員之前以 Guest 身分（`roster_entries
.member_id IS NULL`）打過的比賽——查詢條件為
`roster_entries.member_id = :member_id`，Guest 記錄之 `member_id`
恆為 `NULL`，天然不會被撈出。
