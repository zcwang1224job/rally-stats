# Phase 1 Data Model: 會員個人設定（四大分區）

沿用 `specs/006-member-friends/data-model.md` 既有的 `members` 表（本
feature 以 **ALTER TABLE** 補齊 3 個新欄位），新建 1 張表
（`member_login_records`）。

## 1. `members`（ALTER 既有表）

| 欄位 | 型別 | 約束 | 說明 |
|---|---|---|---|
| `language_preference` | VARCHAR(8) | **新增**，NOT NULL，DEFAULT `'zh-TW'` | 合法值清單為程式碼常數（見 research.md #4），非 DB CHECK 約束，未來新增語言不需 migration |
| `allow_search` | BOOLEAN | **新增**，NOT NULL，DEFAULT `true` | FR-022：關閉時 `search_member()` 對非本人一律回應 `MEMBER_NOT_FOUND` |
| `share_match_records_with_friends` | BOOLEAN | **新增**，NOT NULL，DEFAULT `true` | FR-023：關閉時已成立好友關係者亦無法查看逐場對戰紀錄明細與彙總統計（FR-018 涵蓋兩者） |

三個欄位皆為既有 `members` 表的一般屬性，不影響既有欄位（`email`、
`password_hash`、`nickname`、`user_number`、`verification_status`、
`token_version`、`created_at`）語意。

## 2. `member_login_records`（新建）

| 欄位 | 型別 | 約束 | 說明 |
|---|---|---|---|
| `id` | UUID | PK，`gen_random_uuid()` | |
| `member_id` | UUID | FK → `members(id)` ON DELETE CASCADE，索引 `ix_member_login_records_member_id` | |
| `device_category` | VARCHAR(16) | NOT NULL | `desktop \| mobile \| unknown`（research.md #3，程式碼常數非 DB CHECK） |
| `created_at` | TIMESTAMPTZ | NOT NULL，`server_default=now()` | 登入發生時間（UTC，絕對時間戳，憲章原則 VIII） |

**MUST NOT** 包含 IP 位址、地理位置、或任何其他個資欄位（FR-007，見
Clarifications 2026-09-13 第 3 題）。

**生命週期**：每次「主動登入」成功（`member/service.py` 既有的
`login()` 函式——Email＋密碼提交成功、簽發新 token pair 的當下）新增
一筆；token refresh（既有 `refresh()` 函式）**MUST NOT** 新增紀錄（見
Clarifications 2026-09-13 第 4 題）。同一交易內裁切超出最近 50 筆範圍的
舊紀錄（research.md #2）——因此此表對單一會員恆常維持「至多 50 筆」，
不需要獨立的資料保留/刪除排程。

**唯讀性**：此表只有系統寫入（`login()` 內部呼叫的
`record_login(session, member_id, device_category)`），沒有任何使用者可
觸發的更新/刪除操作（FR-010：僅本人可查閱，無好友或他人存取路徑）。

## 3. Pydantic Schema 對應（`app/domains/member/schemas.py`）

- `MemberPublicResponse`（既有，擴充）：新增
  `language_preference: str`、`allow_search: bool`、
  `share_match_records_with_friends: bool` 三個欄位。
- `SupportedLanguagesResponse`（新增）：`languages: list[str]`——
  `GET /members/me` 回應內嵌，或獨立於 `MemberPublicResponse` 之外的
  常數端點，供前端組出語言偏好下拉選單選項（見 research.md #4；最終形狀
  於 contracts/member-settings-api.md 定案）。
- `SetLanguagePreferenceRequest`（新增）：`language: str`（validator 檢查
  屬於 `SUPPORTED_LANGUAGES` 常數清單，否則 `ApiError("LANGUAGE_NOT_SUPPORTED")`）。
- `PrivacySettingsRequest`（新增）：`allow_search: bool | None = None`、
  `share_match_records_with_friends: bool | None = None`（至少一個非
  `None`，否則視為無效請求）。
- `PrivacySettingsResponse`（新增）：`allow_search: bool`、
  `share_match_records_with_friends: bool`（回傳變更後的完整目前狀態）。
- `LoginRecordSummary`（新增）：`created_at: datetime`、
  `device_category: str`。
- `LoginRecordsResponse`（新增）：`records: list[LoginRecordSummary]`、
  `page: int`、`total_pages: int`（分頁 pattern 比照既有
  `MemberGroupHistoryResponse`/`MemberMatchRecordsResponse`）。

`GET /members/{member_id}/match-records`、
`GET /members/{member_id}/match-records/{match_id}` 兩支新端點**沿用既有**
`MemberMatchRecordsResponse`／`MatchRecordDetailResponse`（不新增回應
型別——research.md #1：直接重用既有 service 函式與其既有回傳形狀）。

## 4. 狀態轉換 / 不變量摘要

- `language_preference`：目前僅一個合法值，無狀態機；未來新增語言時只是
  合法值集合擴大，不改變欄位本身的讀寫語意。
- `allow_search` / `share_match_records_with_friends`：各自獨立的布林
  開關，會員本人隨時可切換，無中間狀態、無需二次確認（憲章原則 V 不適用
  於非破壞性設定變更）。
- `member_login_records`：只增不減的 append-only 紀錄，例外是「裁切超出
  50 筆範圍」這個系統自動行為（非使用者可觸發的刪除操作）。
