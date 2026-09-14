# API Contract: 隱私設定擴充（新增「允許透過對戰紀錄／即時戰況被加好友」）

延伸既有 `specs/022-member-personal-settings` 的隱私設定端點，新增第三個
獨立開關（FR-006/007）。端點路徑與既有既有兩個欄位完全共用，僅
request/response body 多一個欄位——不新增端點。

## PATCH /members/me/privacy-settings

需 `Authorization: Bearer {access_token}` 且已驗證。

**Request**（至少提供一個欄位，三者互相獨立，任意組合皆可）：

```json
{
  "allow_search": true,
  "share_match_records_with_friends": true,
  "allow_friend_invite_from_match_pages": false
}
```

**Response 200**

```json
{
  "allow_search": true,
  "share_match_records_with_friends": true,
  "allow_friend_invite_from_match_pages": false
}
```

**錯誤代碼**：沿用既有 `VALIDATION_ERROR`（三個欄位皆為 `null`/未提供時，
既有 `check_at_least_one_field` validator 現在同時檢查三個欄位）。

**行為**：`allow_friend_invite_from_match_pages` 的讀寫邏輯與既有
`allow_search`/`share_match_records_with_friends` 完全對稱——只更新請求中
明確提供（非 `None`）的欄位，其餘欄位維持原值不變。

## GET /members/me（既有端點，`MemberPublicResponse`）

回應新增 `allow_friend_invite_from_match_pages: boolean` 欄位（比照既有
`allow_search`/`share_match_records_with_friends` 兩欄位的既有位置），供
前端個人設定頁初始化開關的目前狀態。

## 預設值

新欄位 `allow_friend_invite_from_match_pages` 資料庫層級
`DEFAULT true`（FR-007），既有會員與新註冊會員皆不需要任何額外遷移步驟
即可取得正確的預設狀態。
