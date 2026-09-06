# API Contract: 加入流程

沿用 `specs/architecture.md` §3.1 已定案路徑（`GET /join/{join_link_token}`、`POST /groups/{group_id}/join` 列於「加入（004）」章節；`POST /groups/{group_id}/verify-password` 列於「團（001）」章節，由本 feature 實作，見 research.md #3）。

## GET /join/{join_link_token}

無需驗證；若帶有效 `Authorization: Bearer {member_access_token}`，回應包含 FR-020a 短路欄位。

**Response 200**

```json
{
  "group_id": "uuid",
  "group_number": 100234,
  "name": "週三夜羽",
  "has_password": true,
  "current_member_count": 6,
  "max_members": 12,
  "match_mode": "doubles",
  "scheduling_mechanism": "fair_rotation",
  "activity_time_start": "19:00:00",
  "activity_time_end": "21:00:00",
  "status": "active",
  "court_names": ["1號場"],
  "creator_nickname": "阿明",
  "already_joined": false,
  "roster_entry_id": null
}
```

**錯誤代碼**：`LINK_NOT_FOUND`（404，連結已失效）。**注意**：`status: "disbanded"` 或 `current_member_count >= max_members` 皆以 200 回應正常欄位值呈現，由前端依欄位值決定顯示「此團已解散」/「此團人數已滿」（FR-009），MUST NOT 導向一般錯誤頁或空白頁。

## POST /groups/{group_id}/verify-password

**Request**：`{ "password": "..." }`

**Response 200**：`{ "correct": true }` 或 `{ "correct": false }`（無次數限制，MUST NOT 鎖定，FR-016）

**錯誤代碼**：`GROUP_NOT_FOUND`（404）、`GROUP_DISBANDED`（409）。

## POST /groups/{group_id}/join

已登入會員：`Authorization: Bearer {member_access_token}`；Guest：無此 header。

**Request（Guest）**：`{ "password": "...", "nickname": "小明" }`（`password` 為 `null` 或省略，若該團無密碼）

**Request（已登入會員）**：`{ "password": "..." }`（`nickname` 欄位若提供則忽略，MUST NOT 覆蓋會員暱稱）

**Response 201**

```json
{ "roster_entry_id": "uuid", "nickname": "小明", "guest_session_token": "opaque-string-or-null", "created_new": true }
```

`created_new: false` 時代表 FR-020a 短路（已登入會員先前已是 active 成員，直接回傳既有記錄，`guest_session_token` 恆為 `null`）。

**錯誤代碼**：
- `GROUP_NOT_FOUND`（404）
- `GROUP_DISBANDED`（409）
- `GROUP_FULL`（409，前置檢查或最終原子性保證皆可能觸發，見 research.md #5）
- `GROUP_PASSWORD_INCORRECT`（400，無次數限制）
- `NICKNAME_REQUIRED_FOR_GUEST`（422，Guest 未提供暱稱或格式不符）
- `NICKNAME_REQUIRED_FOR_MEMBER`（409，已登入會員尚未完成首次暱稱設定，FR-019）

## GET /groups/by-guest-token/{token}

無需驗證。供 Guest 重新整理/斷線重連時還原身份（FR-023）。

**Response 200**

```json
{ "roster_entry_id": "uuid", "group_id": "uuid", "nickname": "小明" }
```

**錯誤代碼**：`LINK_NOT_FOUND`（404——Token 不存在、該筆 `RosterEntry` 已非 active、或所屬團已解散，三者統一回應同一錯誤代碼，不區分細節，research.md #4）。
