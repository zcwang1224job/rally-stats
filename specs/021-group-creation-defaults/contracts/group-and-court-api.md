# API Contract: 開團流程優化——合理預設值與自動預設場地

擴充既有 `specs/001-create-manage-group/contracts/groups-api.md` 之
`POST /groups`（回應行為調整，`name` 請求欄位改為選填）；**不修改**
既有 `specs/002-court-management/contracts/courts-api.md` 之
`PATCH /courts/{court_id}`（更名端點本身零變更，僅補上先前缺少的
測試覆蓋，見 quickstart.md）。

## `POST /groups`（既有端點，`name` 請求欄位改為選填，回應新增副作用）

**Request**：`name` 欄位由必填改為選填——省略、傳入 `null`，或傳入
空字串/純空白字串，三者皆視為「未提供」，效果相同。非空時仍需符合
既有 1–30 字長度限制（超過限制時仍回傳既有 `VALIDATION_ERROR`）。

```json
{
  "max_members": 4,
  "match_mode": "singles",
  "scheduling_mechanism": "fair_rotation",
  "creator_nickname": "阿宏",
  "turnstile_token": "..."
}
```

（`name` 整個欄位可以省略，如上例；也可以顯式傳 `"name": null` 或
`"name": ""`，效果相同。）

**回應行為（既有 `CreateGroupResponse` 形狀不變）**：

- 若請求省略/留空 `name`：新建立的 `Group.name` MUST 為
  「{建立者暱稱}的羽球團」——建立者暱稱依實際身份決定（登入會員為其
  既有會員暱稱；訪客為請求中 `creator_nickname` 的值，data-model.md）。
- 不論 `name` 是否提供，回應成功時 MUST 已經在同一個交易內建立一筆
  名為「球場一」的球場（data-model.md、research.md #2）——這筆球場
  不會出現在 `POST /groups` 的回應本文中（`CreateGroupResponse` 不含
  球場資訊），但呼叫既有 `GET /groups/{group_id}/courts`（需
  `admin_token`）即可查到它，行為與手動新增的球場完全一致。

**錯誤代碼**：既有 `VALIDATION_ERROR`／`CAPTCHA_INVALID`／
`CAPTCHA_EXPIRED`／`GROUP_MEMBER_CAP_EXCEEDED`／
`NICKNAME_REQUIRED_FOR_GUEST`／`MEMBER_NICKNAME_NOT_SET` 皆不變；
若整個開團請求失敗（任何既有錯誤代碼），MUST NOT 建立任何球場
（spec.md FR-007）。

## `PATCH /courts/{court_id}`（既有端點，零變更——本 feature 只新增測試覆蓋）

**現況**：此端點（`RenameCourtRequest`／`rename_court()`）與對應的
前端 `CourtManagementService.renameCourt()` 方法皆已存在且行為正確，
只是先前從未被任何畫面呼叫、也從未被任何單元或契約測試覆蓋
（research.md #3）。本 feature **不修改此端點的任何請求/回應形狀或
行為**，僅：

1. 在既有球場管理畫面新增呼叫這個既有端點的操作入口（見
   quickstart.md）。
2. 補上這條既有路徑原本缺少的單元測試（`rename_court()`）與契約測試
   （`PATCH /courts/{court_id}`）。

為完整起見，既有形狀摘要如下（沿用
`specs/002-court-management/contracts/courts-api.md` 之既有定義，
非本 feature 新增）：

**Auth**：`Authorization: Bearer {admin_token}`（既有 `_admin_court`
依賴）。

**Request**：`{ "name": "新場地名稱" }`（1–20 字，既有規則）。

**Response 200**：既有 `CourtResponse`（`name` 為更新後的值，
`scoreboard_token`／`control_panel_token` 等既有欄位維持不變，
research.md #3）。

**錯誤代碼**：既有 `VALIDATION_ERROR`／`COURT_NAME_ALREADY_EXISTS`
（同團內另一現役球場已使用該名稱；更名為自己目前的名稱 MUST 視為
合法操作，不觸發此錯誤，spec.md Edge Cases）／`COURT_DELETED`／
`ADMIN_TOKEN_INVALID`。

---

## 兩個相關契約的共通行為

- 自動建立的「球場一」與手動新增的球場在資料上完全無法區分
  （data-model.md「狀態/邊界摘要」），因此上述 `PATCH
  /courts/{court_id}` 端點對它的行為與對任何其他球場完全相同，
  不需要額外的特殊情境說明。
