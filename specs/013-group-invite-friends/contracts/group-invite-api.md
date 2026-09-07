# API Contract: 組團邀請

## GET /groups/{group_id}/invitable-friends

`require_admin`（同既有管理頁端點）。僅限 `created_by_member` 為真的團
（FR-012）——否則回傳 `GROUP_NOT_MEMBER_CREATED`。

**Response 200**

```json
{
  "friends": [
    {
      "member_id": "uuid",
      "nickname": "小美",
      "user_number": "aB3dEfGh",
      "invite_status": "pending",
      "invite_id": "uuid"
    },
    {
      "member_id": "uuid",
      "nickname": "小明",
      "user_number": "cD4eFgHi",
      "invite_status": "not_invited",
      "invite_id": null
    }
  ]
}
```

依團長的完整好友列表組裝（research.md #8），`invite_status` 為
`already_member` 時優先於任何 `GroupInvite` 歷史紀錄；否則取該好友在本
團「最新一筆」邀請的狀態，從未邀請過則為 `not_invited`。

## POST /groups/{group_id}/invites

`require_admin`。送出邀請（FR-001~004）。

**Request**：`{ "invitee_member_id": "uuid" }`

**Response 201**：`{ "invite_id": "uuid", "status": "pending" }`

**錯誤代碼**：
- `GROUP_NOT_MEMBER_CREATED`（403，FR-012，匿名建團無法使用）
- `MEMBER_NOT_FOUND`（404，`invitee_member_id` 不存在）
- `NOT_FRIENDS`（400，FR-002，對方非團長好友）
- `ALREADY_GROUP_MEMBER`（409，FR-004，對方已是本團現有成員）
- `INVITE_ALREADY_PENDING`（409，FR-003，同一好友已有一筆待回覆邀請）

## GET /group-invites/{invite_id}

`require_verified_member`。僅邀請的受邀人本人可查看（FR-005/FR-010）。

**Response 200**

```json
{
  "invite_id": "uuid",
  "status": "pending",
  "group_id": "uuid",
  "group_name": "週三夜羽球團",
  "inviter_nickname": "團長暱稱"
}
```

**錯誤代碼**：`GROUP_INVITE_NOT_FOUND`（404，含「非本人受邀」之情況，
比照好友申請 `FRIEND_REQUEST_NOT_FOUND` 之既有慣例，不洩漏是否存在）。

## POST /group-invites/{invite_id}/accept

`require_verified_member`。僅受邀人本人可操作。內部重用 `join_group()`
（`skip_password=True`，research.md #3），依序套用人數上限、一人同時僅能
活躍於一個團的既有規則（FR-006）。

**Response 200**：`{ "group_id": "uuid", "roster_entry_id": "uuid", "nickname": "小美" }`

**錯誤代碼**：
- `GROUP_INVITE_NOT_FOUND`（404）
- `GROUP_INVITE_NOT_PENDING`（409，已是 accepted/declined/invalidated，
  含「已額滿故仍為 pending 但當下仍額滿」不算此錯誤——那是下面的
  `GROUP_FULL`）
- `GROUP_DISBANDED`（409，理論上不會發生——見 research.md #4 之防禦性
  說明）
- `GROUP_FULL`（409，FR-013：此錯誤發生的同時，系統會建立
  `group_invite_capacity_full` 通知給團長；`GroupInvite` 本身狀態不變，
  受邀人可稍後重試同一筆邀請）
- `ALREADY_ACTIVE_IN_ANOTHER_GROUP`（409）
- `MEMBER_NICKNAME_NOT_SET`（400，沿用 `join_group()` 既有規則）

## POST /group-invites/{invite_id}/decline

`require_verified_member`。僅受邀人本人可操作（FR-008）。

**Response 200**：`{ "invite_id": "uuid", "status": "declined" }`

**錯誤代碼**：`GROUP_INVITE_NOT_FOUND`（404）、
`GROUP_INVITE_NOT_PENDING`（409）。
