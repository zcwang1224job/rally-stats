# Data Model: 訪客即時戰況頁面建立帳號並綁定戰績

本 feature **不新增任何資料表、不新增任何欄位**。唯一的資料變化是既有
`RosterEntry.member_id`（`apps/api/app/domains/roster/models.py:16-42`）
從 `NULL` 轉為某個 `Member.id` 的一次性狀態轉換。

## 1. `RosterEntry.member_id`——狀態轉換規則

既有欄位：`member_id: UUID | None`，FK → `members.id`，NULL 代表訪客
（無會員帳號）。

**新增的狀態轉換規則**（僅規則，非 schema 變更）：

- 轉換方向唯一：`NULL → <member_id>`，一旦轉換完成 MUST NOT 再變更
  （不支援「改綁到別的帳號」或「解除綁定」——spec 未要求，不在此
  feature 範圍內新增此類操作）。
- 觸發轉換的唯一路徑：`POST /groups/guest-token/{token}/bind`（見
  `contracts/guest-binding-api.md`）或其 OAuth 對應的
  `GET /auth/oauth/{provider}/start?...&bind_guest_token=...` →
  `GET /auth/oauth/{provider}/callback` 交握。
- 轉換條件（原子性，見 research.md #4）：
  `UPDATE roster_entries SET member_id = :member_id WHERE id = :id AND member_id IS NULL`，
  受影響 row 數 = 1 才視為成功。
- 轉換 MUST NOT 依賴 `RosterEntry.status`（active/left/kicked 皆可轉換，
  FR-004、Acceptance Scenario 4）也 MUST NOT 依賴所屬 `Group.status`
  （active/disbanded 皆可轉換，FR-004、Acceptance Scenario 5）。
- 轉換 MUST NOT 修改 `RosterEntry.nickname`（FR-011）——這是該筆名冊
  身份在比賽紀錄中的顯示名稱，與綁定後的 `Member.nickname`（若不同）
  彼此獨立。

## 2. 綁定後的既有資料如何「自動歸戶」

`MatchParticipant`（`apps/api/app/domains/schedule/models.py:84-93`）
以單一 FK `roster_entry_id → roster_entries.id` 關聯，**不**直接持有
`member_id`。這代表：

- 綁定動作完成的當下，不需要另外去逐筆更新既有 `MatchParticipant` 列
  ——它們透過 `roster_entry_id` 這一層間接關聯，`RosterEntry.member_id`
  一旦被設定，既有「依 `Member.id` 查詢對戰紀錄」的既有查詢邏輯（會員
  專區 -> 對戰紀錄）只要在既有的 join 路徑上，將 `RosterEntry.member_id`
  這個過濾條件從「必為某會員」放寬為「透過此關聯查得到即可」，自然涵蓋
  這筆剛綁定的名冊身份名下所有既有與後續的 `MatchParticipant` 列
  （SC-002）。
- 這也是 FR-003「立即歸戶」在資料庫層面唯一需要做的事——寫一次
  `RosterEntry.member_id`，不需要任何批次回填/複製既有比賽紀錄列。

## 3. 涉及但不修改的既有實體（僅列出關聯，供實作對照）

- **`Member`**（`apps/api/app/domains/member/models.py`）：綁定動作的
  「目的地」，透過既有 `register()`/`login()`/OAuth 流程建立或取得，本
  feature 不新增欄位。
- **`Group`**（`apps/api/app/domains/group/models.py`）：`status`
  （`active`/`disbanded`）與 `disbanded_at` 兩個既有欄位用於 #1 的
  「binding-status」查詢回應（告知前端這是「進行中」還是「已完結」
  畫面），不修改。
- **`OAuthState`/`OAuthCallbackResult`**（`apps/api/app/domains/member/
  security.py`、`service.py`）：research.md #3 各新增一個可選欄位
  （`bind_guest_token`／`bound_group_id`），非新實體，僅為既有 dataclass
  的欄位擴充。
