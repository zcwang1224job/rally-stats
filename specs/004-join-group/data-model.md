# Phase 1 Data Model: 加入團（嘎團）

本 feature 不新增資料表、不新增欄位——沿用 001 已建立的 `groups`（密碼欄位、`current_member_count`、`max_members`、`join_link_token`、`status`）、`roster_entries`（`member_id`、`nickname`、`status`、`guest_session_token`）與 002 已建立的 `courts`（`name`）。研究內容見 research.md，本檔案僅記錄查詢/寫入模式與 Pydantic schema 對應。

## 1. 讀取模式

### 開團列表查詢（`GET /groups`）

- 基礎查詢：`groups` WHERE `status = 'active'`（已解散團不出現在瀏覽列表——與已定案的「已解散團仍可透過連結唯讀查閱」原則不衝突，兩者是不同情境：列表瀏覽 vs. 持有既有連結直接進入）。
- 場地名稱/ID 篩選：`EXISTS (SELECT 1 FROM courts WHERE courts.group_id = groups.id AND courts.deleted_at IS NULL AND (courts.name ILIKE :name_pattern OR courts.id = :court_id))`（research.md #7）。
- 活動時間篩選：套用時 `activity_time_start IS NOT NULL AND activity_time_end IS NOT NULL AND activity_time_start < :filter_end AND activity_time_end > :filter_start`（區間重疊判斷，spec.md Assumptions 已定案邏輯）；未套用篩選時不加此條件（含未設定時間的團一併顯示）。
- 分頁：`ORDER BY created_at DESC LIMIT 20 OFFSET (:page - 1) * 20`（research.md #8）。
- 個人化（已登入時）：對每筆結果額外查詢 `EXISTS (SELECT 1 FROM roster_entries WHERE group_id = groups.id AND member_id = :member_id AND status = 'active')` → `joined_by_me`。

### 加入連結解析（`GET /join/{join_link_token}`）

- `SELECT * FROM groups WHERE join_link_token = :token`；查無 → `LINK_NOT_FOUND`（404）。
- 已登入時額外查詢同上 `joined_by_me` 邏輯，若為真則一併回傳該筆 `roster_entry_id`（`already_joined: true`）。

### Guest Session Token 解析（`GET /groups/by-guest-token/{token}`）

- `SELECT * FROM roster_entries WHERE guest_session_token = :token AND status = 'active'`，並 JOIN `groups` 確認 `groups.status = 'active'`；任一條件不成立 → `LINK_NOT_FOUND`（404，research.md #4，不區分失效原因）。

## 2. 寫入模式（`POST /groups/{group_id}/join`）

單一資料庫交易內，依序：

1. （若已登入會員）查詢既有 active `RosterEntry`（`group_id` + `member_id`）→ 若存在，直接回傳，交易提前結束（FR-020a，不進行以下步驟）。
2. 前置檢查（UX 用，非事實依據）：讀取 `groups.current_member_count`/`max_members`，已滿則提早回應 `GROUP_FULL`，不建立任何記錄。
3. 密碼比對（若 `groups.password_ciphertext IS NOT NULL`）：解密比對，不符 → `GROUP_PASSWORD_INCORRECT`。
4. 暱稱決定：已登入會員 → 讀取 `members.nickname`（`NULL` 則 `NICKNAME_REQUIRED_FOR_MEMBER`）；Guest → 使用 body 提供之 `nickname`（格式驗證，FR-017）。
5. 原子性人數保證：`UPDATE groups SET current_member_count = current_member_count + 1 WHERE id = :group_id AND current_member_count < max_members`；`rowcount = 0` → `GROUP_FULL`，交易回滾（research.md #5，唯一事實依據）。
6. 建立 `RosterEntry`：`group_id`、`member_id`（Guest 為 `NULL`）、`nickname`、`status='active'`、`is_creator=false`；Guest 額外產生 `guest_session_token = secrets.token_urlsafe(32)`（research.md #4）。
7. 呼叫 003 之 `handle_member_joined(session, group, new_roster_entry)`（不觸發任何賽程重排，僅供 003 之固定搭檔循環賽等機制視需要處理）。
8. Commit；回傳 `roster_entry_id`、`nickname`、`guest_session_token`（Guest 才有值，會員為 `null`）、`created_new: true`。

## 3. Pydantic Schema 對應（`app/domains/group/schemas.py` 新增）

- `GroupListItem`：`GroupPublicResponse` 既有全部欄位 + `court_names: list[str]` + `creator_nickname: str`（FR-002，取自該團 `is_creator=true` 之 `RosterEntry`，不受該成員之後是否退出影響——建立當下的暱稱快照）+ `joined_by_me: bool | None`（未登入時為 `null`，區別於「已登入但未加入」的 `false`）。
- `GroupListResponse`：`groups: list[GroupListItem]`、`page: int`、`total_pages: int`。
- `VerifyPasswordRequest`：`password: str`。
- `VerifyPasswordResponse`：`correct: bool`。
- `JoinLinkPreviewResponse`：`GroupPublicResponse` 既有欄位 + `court_names: list[str]` + `creator_nickname: str` + `already_joined: bool` + `roster_entry_id: str | None`。
- `JoinGroupRequest`：`password: str | None`、`nickname: str | None`。
- `JoinGroupResponse`：`roster_entry_id: str`、`nickname: str`、`guest_session_token: str | None`、`created_new: bool`。
- `GuestSessionResponse`：`roster_entry_id: str`、`group_id: str`、`nickname: str`。
