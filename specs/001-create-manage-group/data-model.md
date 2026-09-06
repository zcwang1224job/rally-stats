# Phase 1 Data Model: 開團與管理

本文件詳述 `spec.md` Key Entities 段落所定義實體之欄位、驗證規則、狀態轉換；資料表 DDL 沿用 `specs/architecture.md` §2 已定案的專案共用 schema（本文件僅聚焦本 feature 擁有/直接操作的欄位，並註記本 feature 僅「引用」而非擁有的欄位）。

## 1. Group（團）— 本 feature 擁有

對應資料表：`groups`（見 architecture.md，本節列出本 feature 相關欄位子集並補充驗證規則）。

| 欄位 | 型別 | 驗證規則 / 備註 |
|---|---|---|
| `id` | UUID PK | |
| `group_number` | BIGINT | `SEQUENCE` 產生（`START WITH 100000`），單調遞增、永不重複分配（FR-008） |
| `name` | VARCHAR(30) | 必填，trim 後不可為空字串，≤30 字（FR-002） |
| `password_ciphertext` / `password_nonce` | BYTEA, nullable | AES-256-GCM；有值時對應明文長度 1–20 字（FR-037） |
| `max_members` | INT | 依 `match_mode` 動態最小值（單打≥2、雙打≥4，FR-003）；不可超過 `system_config.max_group_members`（FR-004） |
| `match_mode` | ENUM('singles','doubles') | |
| `scheduling_mechanism` | ENUM('fair_rotation','fixed_partner','individual_mixed','manual') | 四選一，本 feature 僅儲存，行為由 003 定義 |
| `activity_time_start` / `activity_time_end` | TIME, nullable | 成對填寫，`start < end`（FR-005） |
| `current_member_count` | INT | 建立時初始化為 1（FR-012） |
| `status` | ENUM('active','disbanded') | |
| `last_activity_at` | TIMESTAMPTZ | 每次符合 FR-036 定義的活動即更新 |
| `created_at` | TIMESTAMPTZ | |
| `created_by_member_id` | UUID, nullable FK→members | NULL = 匿名建立 |
| `admin_pin_hash` | VARCHAR(255) | bcrypt；PIN 本身為 6 碼純數字 0-9（FR-008） |
| `admin_failed_attempts` | INT, default 0 | 見 research.md #1 |
| `admin_locked_until` | TIMESTAMPTZ, nullable | 見 research.md #1 |
| `admin_token_version` | INT, default 0 | 僅「忘記/主動重設 PIN 碼」時 +1（FR-026，006 spec 之忘記 PIN 碼功能亦操作此欄位） |
| `base_settings_version` | INT, default 0 | 團名/時間/比賽模式/比賽設定/通關密碼等一般編輯之樂觀鎖（FR-028） |
| `join_link_version` / `all_courts_link_version` | INT, default 0 | 本 feature 定義欄位存在，實際重新產生操作由 002 spec 實作 |
| `scoring_mode` | ENUM('21pt','15pt','custom') | 預設 `21pt`（FR-013） |
| `target_score` / `deuce_threshold` / `cap_score` | INT | 自訂模式下之驗證見 FR-014；21pt/15pt 為固定對應數值（21/20/30、15/14/21） |

**狀態轉換**：`active → disbanded`（單向、不可逆，FR-032）。

## 2. Match Scoring Settings（比賽設定）— 本 feature 擁有（內嵌於 Group）

非獨立資料表，即 `groups.scoring_mode/target_score/deuce_threshold/cap_score` 四欄位（見上）。`matches` 表（003 spec 擁有）於建立比賽當下複製這四個數值到自身欄位，構成快照（FR-016）；本 feature 不直接操作 `matches` 表，僅保證 `groups` 上的值在讀取當下正確反映「目前生效設定」。

**驗證規則（FR-014，自訂模式）**：
- `target_score >= 1`（正整數）
- `deuce_threshold >= 1 AND deuce_threshold <= target_score`
- `cap_score >= deuce_threshold AND cap_score >= target_score`

## 3. Admin Credential（管理憑證）— 本 feature 擁有（內嵌於 Group）

即 `groups.group_number` + `groups.admin_pin_hash` + `groups.admin_token_version` 三者的組合（非獨立資料表）。

**驗證流程**（`POST /groups/reauth`）：
1. 檢查 `admin_locked_until` 是否仍在未來 → 是則拒絕（`GROUP_ADMIN_LOCKED`）。
2. 以 `group_number` 查找 Group；查無則回覆與「PIN 錯誤」相同的訊息（避免透過錯誤訊息差異枚舉存在的組團編號）。
3. bcrypt 比對 PIN；錯誤則 `admin_failed_attempts += 1`，達 10 次則寫入 `admin_locked_until = now() + 15min`。
4. 正確則核發 JWT（payload 含 `admin_token_version`），`admin_failed_attempts` 歸零。

## 4. Roster Entry / Player（輪替名單項目）— 本 feature 僅建立初始記錄

對應資料表：`roster_entries`（003/004/006 共同擁有並擴充）。本 feature 於建立團成功時 MUST 建立一筆：

| 欄位 | 本 feature 寫入值 |
|---|---|
| `group_id` | 剛建立的 Group |
| `member_id` | 已登入會員之 ID，或 NULL（匿名） |
| `nickname` | 會員暱稱快照，或表單填寫的匿名暱稱 |
| `status` | `active` |
| `is_creator` | `true` |
| `joined_at` | `now()` |
| `wait_count` | `NULL`（尚未上場，交由 003 spec 之排點邏輯詮釋） |
| `guest_session_token` | 匿名建立時產生隨機字串；會員建立時為 NULL |

## 5. Guest Session Token（訪客身分延續憑證）— 本 feature 核發，全域生命週期由 004 spec 補完

本 feature 僅負責「匿名建立團時核發」這個時間點（FR-011），欄位即 `roster_entries.guest_session_token`。失效規則（團解散、退出、被踢除）之完整定義見 004 spec；本 feature 僅需確保「團解散時，該團所有 `roster_entries.guest_session_token` 皆隨之失效」——實作上不需額外操作（驗證邏輯讀取時一併檢查所屬 `groups.status`，見 FR-030）。

## 6. Court（場地）— 外部引用，唯讀

本 feature 於「解散團」流程需要：(a) 逐一查詢該團底下 `deleted_at IS NULL` 的 Court 列表以逐一發布解散事件（FR-034）；(b) 不需寫入 Court 資料表任何欄位（連結失效為讀取時檢查 `groups.status`，非寫入 Court 本身）。

## 7. SystemConfig（系統參數）— 外部引用，唯讀

```sql
CREATE TABLE system_config (
    key   VARCHAR(64) PRIMARY KEY,
    value TEXT NOT NULL,
    description TEXT
);
```

本 feature 讀取 `max_group_members`（預設 `'200'`，FR-004）。初始資料由本 feature 的 migration 一併 seed（因為是本專案第一個依賴 SystemConfig 的 feature）：

```sql
INSERT INTO system_config (key, value, description) VALUES
  ('max_group_members', '200', '單一團人數上限硬上限'),
  ('default_timezone', 'Asia/Taipei', '活動時間區間顯示基準時區（見 008 之其他 feature）')
ON CONFLICT (key) DO NOTHING;
```

## 8. 驗證規則彙總（跨實體）

| 規則 | 適用欄位 | 對應 FR |
|---|---|---|
| 團名必填、trim 非空、≤30 字 | `groups.name` | FR-002 |
| 通關密碼選填，若填寫則 1–20 字 | `groups.password_*` | FR-037 |
| 人數上限最小值依比賽模式動態決定 | `groups.max_members` | FR-003 |
| 人數上限不可超過 `max_group_members` | `groups.max_members` | FR-004 |
| 活動時間區間成對填寫、start < end | `groups.activity_time_*` | FR-005 |
| 開團者暱稱：Guest 必填 ≤20 字 | `roster_entries.nickname` | FR-009 |
| 自訂比賽設定三欄位邏輯一致性 | `groups.target_score` 等 | FR-014 |
| 切換雙打時人數上限連動檢查 | `groups.match_mode` + `max_members` | FR-020 |

## 9. 狀態機圖（文字描述）

```
Group.status:
  [建立] ──▶ active ──(手動解散 FR-029 / 自動解散 FR-036)──▶ disbanded
                │                                                  │
                └────────────── 唯讀查閱（FR-032） ─────────────────┘
                                （不可逆，無 disbanded → active 路徑）

Group.admin_token_version:
  0 ──(重設 PIN 碼，忘記或主動)──▶ 1 ──(再次重設)──▶ 2 ──▶ …
  （單調遞增，用於使舊管理 Token 失效；不因一般編輯操作遞增）

Group.admin_failed_attempts / admin_locked_until:
  0 ──(PIN 錯誤 ×10)──▶ 鎖定（admin_locked_until = now()+15min）
  鎖定期滿 ──▶ 0（下次驗證嘗試時歸零重新起算）
```
