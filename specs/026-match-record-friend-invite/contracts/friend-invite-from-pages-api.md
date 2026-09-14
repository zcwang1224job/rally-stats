# API Contract: 從對戰紀錄／即時戰況頁面加好友

所有端點皆需 `Authorization: Bearer {access_token}` 且已驗證
（`require_verified_member`）。這兩支端點是既有
`specs/006-member-friends/contracts/friends-api.md` 的延伸，共用同一套
`friend_requests` 資料與狀態機，僅新增「以 member_id 定位對方」與「批次
查詢多人狀態」兩個能力。

## POST /friends/requests/by-member

以 `member_id`（而非既有 `POST /friends/requests` 的 `user_number`）直接
對一位在對戰紀錄／即時戰況頁面看到的會員發送好友邀請（FR-001~005）。

**Request**：`{ "addressee_member_id": "uuid" }`

**Response 201**：`{ "friend_request_id": "uuid", "status": "pending" }`

**錯誤代碼**（送出當下即時重新驗證，FR-010）：

- `MEMBER_NOT_FOUND`（404）——目標不存在、未驗證、或已刪除帳號（與既有
  `POST /friends/requests` 完全相同的判斷）。
- `CANNOT_FRIEND_SELF`（400）。
- `FRIEND_REQUEST_ALREADY_PENDING`（409）。
- `ALREADY_FRIENDS`（409）。
- `INVITE_VIA_MATCH_PAGES_NOT_ALLOWED`（403，新增）——目標已將
  `allow_friend_invite_from_match_pages` 設為關閉，且雙方目前無好友關係／
  無待處理邀請（FR-008；若已是好友或已有待處理邀請，優先回傳上面
  `ALREADY_FRIENDS`/`FRIEND_REQUEST_ALREADY_PENDING`，因為此設定關閉
  MUST NOT 影響已存在關係，FR-009）。

**行為**：與既有 `POST /friends/requests` 共用完全相同的核心邏輯
（research.md #3）——建立 `FriendRequest`、建立好友邀請通知（非即時，
006 既有機制）、重複發送防呆（DB partial unique index 為最終防線）。

## POST /friends/invite-candidates

批次查詢多位會員相對於目前登入者的好友關係狀態與「透過本入口加好友」的
資格，供對戰紀錄／即時戰況頁面一次載入後渲染多個「加好友」入口
（research.md #2，避免逐列 N+1）。

**Request**：`{ "member_ids": ["uuid", "uuid", ...] }`（呼叫端負責去重、
排除自己與 Guest——不在 `member_ids` 清單中的參與者，前端本來就不會渲染
任何入口，見 FR-002/FR-003）。**未設硬性上限**——此端點需
`require_verified_member`（非匿名公開端點），且呼叫端（本 feature 四個
整合點）自然只會送出單一頁面上實際可見的參與者人數（plan.md Scale/Scope：
通常個位數到數十），與 006 既有 `list_friends()`「單一會員規模小到可在
Python 端過濾」的既有規模假設一致；不設上限為刻意決定，而非遺漏。

**Response 200**

```json
{
  "candidates": [
    {
      "member_id": "uuid",
      "friendship_status": "none",
      "invite_eligible": true
    },
    {
      "member_id": "uuid",
      "friendship_status": "pending_outgoing",
      "invite_eligible": false
    }
  ]
}
```

- `friendship_status`：`none` | `friends` | `pending_outgoing` |
  `pending_incoming`——與既有 `get_friendship_status()`（006）回傳值完全
  相同的四態語意，前端據此渲染既有的
  `friends.alreadyFriends`/`pendingOutgoing`/`pendingIncoming` 標籤
  （FR-004，重用既有 i18n key，不新增）。
- `invite_eligible`：`true` 僅當 `friendship_status == "none"` 且該
  `member_id` 對應的會員目前為已驗證、未刪除帳號、且
  `allow_friend_invite_from_match_pages == true`；否則一律 `false`（此欄位
  純粹是 UI 提示——實際送出仍必須通過 `POST /friends/requests/by-member`
  當下的伺服器端重新驗證，FR-010，本欄位不構成授權依據）。
- 若請求中的某個 `member_id` 查無對應會員（極端情況，例如帳號在批次查詢
  與畫面渲染之間被刪除），該筆從回應中省略（前端據此視為不可加好友，
  等同 `invite_eligible: false` 的效果）而非回傳錯誤，避免單一失效 id
  導致整批查詢失敗。

**權限邊界**：此端點僅回傳「關係狀態」與「布林資格旗標」，MUST NOT 回傳
任何目標會員的其他個人資訊（暱稱/使用者編號等——呼叫端頁面本來就已經從
各自的對戰紀錄/賽程回應中取得暱稱，不需要這支端點重複提供）。
