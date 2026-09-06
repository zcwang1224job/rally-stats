# UI Contract: Friends Frontend & My Groups (US7)

**Feature**: [../spec.md](../spec.md) | **API contracts**: [reused-api-contracts.md](./reused-api-contracts.md)

## Routes

| Path | Component | Purpose |
|---|---|---|
| `/friends` | `friend-list/` | 好友列表：篩選（暱稱/使用者編號子字串）、分頁、每筆好友一個「解除好友」入口（二次確認 dialog）、頁面頂部「新增」按鈕導向 `/friends/add` |
| `/friends/add` | `friend-add/` | 搜尋使用者編號 → 顯示對應 `friendship_status` 狀態的按鈕/標籤 → 發送邀請 |
| `/friends/requests` | `friend-requests/` | 收到的待處理邀請列表，各自「接受」/「拒絕」 |
| `/member/my-groups` | `member/my-groups/` | 本人建立過的所有團（含已解散），各自「忘記管理 PIN 碼」入口（二次確認 dialog，因為會使舊 PIN 立即失效） |

All four routes are ordinary member-area pages under 009's nav shell
(default `navShell: true`, no route-data exclusion needed) and require the
member to be logged in and email-verified (mirrors the existing
`/member/*` pages' behavior — a page-level guard consistent with how
`/member/settings` etc. already behave, not a new auth mechanism).

## Behavioral contract

| # | Given | Then |
|---|-------|------|
| 1 | `friend-add`, valid `user_number`, `friendship_status: 'none'` | Shows a "發送好友申請" button; clicking calls `POST /friends/requests`, then re-renders the same search result as `pending_outgoing`. |
| 2 | `friendship_status: 'pending_outgoing'` \| `'pending_incoming'` \| `'friends'` | Shows the matching non-actionable label ("待回覆" / "待處理" / "已是好友") per spec.md US7 scenario 1 — no button that would create a duplicate request. |
| 3 | Search for own `user_number` or a `MEMBER_NOT_FOUND`/`CANNOT_SEARCH_SELF` error | Shows the corresponding inline error, no crash, no partial result rendered. |
| 4 | `friend-list`, user types into the filter field | List re-queries `GET /friends` with `nickname`/`user_number` params (debounced), showing only matching rows. |
| 5 | `friend-list`, user clicks "解除好友" on a row and confirms | Calls `DELETE /friends/{id}`; that row disappears from the list; **no toast/notification of any kind is shown to the other member** (contract: `friends-api.md` — this MUST NOT be violated by adding one on the frontend either). |
| 6 | `friend-requests`, user clicks "接受" | Calls `POST /friends/requests/{id}/accept`; the request disappears from the incoming list. |
| 7 | `friend-requests`, user clicks "拒絕" | Calls `POST /friends/requests/{id}/reject`; the request disappears from the incoming list; sending a new request to the same person later is unaffected (backend-owned invariant, not re-tested at UI level here). |
| 8 | `my-groups`, user clicks "忘記管理 PIN 碼" on a row and confirms (two-step, Constitution V — this invalidates the old PIN immediately) | Calls `POST /groups/{group_id}/forgot-admin-pin`; on success, stores the new admin token (same mechanism `GroupAdminService.setAdminToken` already uses) and navigates straight to that group's admin page — no re-entry of the newly-shown PIN required (FR-017). |

## Non-goals

- No push/toast notification for incoming friend requests (research.md
  Decision 5) — the mockup's notification screen is not built.
- No changes to `NavShellComponent`'s guest-facing behavior — only its
  member-only link list gains two new entries (好友 → `/friends`; the
  我的團 entry is reached via the member home menu per research.md Decision
  6, not directly from the global nav shell).
