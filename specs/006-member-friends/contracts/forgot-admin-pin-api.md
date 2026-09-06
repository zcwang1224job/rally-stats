# API Contract: 忘記管理 PIN 碼（會員限定）

實作位置：`apps/api/app/domains/group/router.py`（既有模組，非新建 `member`/`friend`），依 research.md #7 之跨模組串接決議——本端點修改的資料屬 `group` 模組所有權，僅登入驗證與建立者比對讀取 `member` 資訊。收錄於本 feature 之 contracts 是因為其 FR（FR-028~033）屬於 006 spec 範圍。

## POST /groups/{group_id}/forgot-admin-pin

需 `Authorization: Bearer {access_token}`（`require_verified_member`，見 member-api.md）。

**Request**：無 body。

**Response 200**

```json
{ "admin_pin": "123456", "admin_token": "..." }
```

比照既有 `POST /groups/{group_id}/regenerate-admin-pin`（001）之回應形狀——直接核發新 PIN 明文（供會員記錄）與新管理 Token（直接導向管理頁，MUST NOT 要求重新輸入剛顯示的 PIN，見 FR-032）。

**同一筆交易內**：`groups.admin_pin_hash` 更新為新 PIN 之雜湊、`groups.admin_token_version += 1`（沿用既有欄位，使舊 token 立即失效）。

**廣播**：複用既有 `link.regenerated`（`link_type: "admin"`）事件，發布至團通知頻道（002 已建立之機制，FR-032a）。

**錯誤代碼**：`MEMBER_TOKEN_INVALID`（401）、`GROUP_NOT_FOUND`（404）、`NOT_GROUP_CREATOR`（403，`group.created_by_member_id != member.id`，含「該團為匿名建立」之情況——`created_by_member_id IS NULL` 時同樣回傳此代碼，不特別區分，避免洩漏團的建立方式細節）。

**注意**：已解散的團 MUST NOT 被此邏輯排除（FR-028 後半段、FR-033 情境 5）——不檢查 `groups.status`。
