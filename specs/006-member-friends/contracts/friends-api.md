# API Contract: 好友系統

所有端點皆需 `Authorization: Bearer {access_token}` 且已驗證（`require_verified_member`）。

## GET /friends?page=&nickname=&user_number=

**Response 200**

```json
{ "friends": [{ "member_id": "uuid", "nickname": "小美", "user_number": "aB3dEfGh" }], "page": 1, "total_pages": 3 }
```

`nickname`/`user_number` 篩選為子字串比對（部分符合即列入，FR-034）；僅回傳 `status='accepted'` 的關係。

## POST /friends/requests

**Request**：`{ "addressee_user_number": "aB3dEfGh" }`

**Response 201**：`{ "friend_request_id": "uuid", "status": "pending" }`

**錯誤代碼**：`MEMBER_NOT_FOUND`（404，對應 FR-036 未驗證帳號查無）、`CANNOT_FRIEND_SELF`（400，FR-037）、`FRIEND_REQUEST_ALREADY_PENDING`（409，FR-039 唯一索引衝突之語意化錯誤）、`ALREADY_FRIENDS`（409）。

## GET /friends/requests/incoming

**Response 200**

```json
{ "requests": [{ "friend_request_id": "uuid", "requester": { "member_id": "uuid", "nickname": "小明", "user_number": "..." }, "created_at": "..." }] }
```

僅列出 `addressee_id == 本人` 且 `status='pending'` 者。

## POST /friends/requests/{id}/accept

**Response 200**：`{ "friend_request_id": "uuid", "status": "accepted" }`

**錯誤代碼**：`FRIEND_REQUEST_NOT_FOUND`（404，含「非本人為 addressee」之情況，避免洩漏他人邀請是否存在）、`FRIEND_REQUEST_NOT_PENDING`（409）。

## POST /friends/requests/{id}/reject

**Response 200**：`{ "friend_request_id": "uuid", "status": "rejected" }`（同上錯誤代碼）

## DELETE /friends/{friend_request_id}

解除好友（FR-043~046）；`{friend_request_id}` 為狀態 `accepted` 的既有列 id。

**Response 200**：`{ "friend_request_id": "uuid", "status": "unfriended" }`

**錯誤代碼**：`FRIEND_REQUEST_NOT_FOUND`（404，含「非本人所屬關係」）、`FRIEND_REQUEST_NOT_ACCEPTED`（409，目標列非 `accepted` 狀態）。

**注意**：MUST NOT 對另一方發送任何通知（FR-045，無 Ably 事件、無 Email）；雙方各自查看 `GET /friends` 時即時反映（因直接查詢 DB，非快取）。
