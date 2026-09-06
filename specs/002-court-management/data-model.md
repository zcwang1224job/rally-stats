# Phase 1 Data Model: 場地管理

沿用 `specs/architecture.md` §2 已定案的 `courts` 資料表 DDL（本 feature 首次填滿其完整欄位——001 僅建立最小 stub：`id`/`group_id`/`deleted_at`，供解散流程查詢用）。

## 1. Court（場地）— 本 feature 擁有

對應資料表：`courts`。

| 欄位 | 型別 | 驗證規則 / 備註 |
|---|---|---|
| `id` | UUID PK | 001 已建立 |
| `group_id` | UUID FK → `groups.id` | 001 已建立 |
| `name` | VARCHAR(20) | 必填，trim 後不可為空字串，≤20 字（FR-002）；同團「目前有效」（`deleted_at IS NULL`）範圍內唯一，已軟刪除場地的名稱不列入比對（FR-003） |
| `scoreboard_token` | UUID, unique, default `gen_random_uuid()` | 計分板連結識別 Token（FR-004） |
| `control_panel_token` | UUID, unique, default `gen_random_uuid()` | 控制板連結識別 Token（FR-004） |
| `scoreboard_link_version` | INT, default 0 | 樂觀鎖，僅計分板連結重新產生時 +1（FR-036，與控制板連結版本互相獨立） |
| `control_panel_link_version` | INT, default 0 | 樂觀鎖，僅控制板連結重新產生時 +1（FR-036） |
| `deleted_at` | TIMESTAMPTZ, nullable | 軟刪除（FR-008）；001 已建立 |
| `created_at` | TIMESTAMPTZ | |

**未新增欄位**：不新增用於「重新命名」的泛用版本欄位（見 research.md #5）——重新命名採最後寫入為準 + `ux_courts_group_name_active` 唯一索引作為並發防呆。

**狀態轉換**：

```
Court:
  [新增] ──▶ (deleted_at IS NULL，「目前有效」) ──(刪除，FR-007~012)──▶ (deleted_at 為刪除時間戳)
                                                                            │
                                                              不可逆，無「復原」路徑；
                                                              名稱可被新場地沿用（FR-003）
```

## 2. All-Courts Control Panel Token（全部場地控制板憑證）— 外部引用，操作由本 feature 實作

對應欄位：`groups.all_courts_control_panel_token` / `groups.all_courts_link_version`（001 `data-model.md` §1 已建立欄位，操作移交本 feature，見 research.md #1）。本 feature 不新增欄位，僅新增：

- `POST /groups/{group_id}/regenerate-all-courts-link` 端點（樂觀鎖比對 `all_courts_link_version`，+1，發布 `link.regenerated`(`link_type: all_courts`)）
- `GET /groups/by-all-courts-token/{token}` 端點（初始化 + 心跳，見 research.md #4）

## 3. Join Link Token（加入連結憑證）— 外部引用，操作由本 feature 實作

對應欄位：`groups.join_link_token` / `groups.join_link_version`（001 已建立）。本 feature 新增：

- `POST /groups/{group_id}/regenerate-join-link` 端點（樂觀鎖比對 `join_link_version`，+1；依 FR-033，MUST NOT 發布即時事件——加入連結不對應任何持續訂閱連線，故此端點交易內**不**呼叫 `publish()`）。

## 4. Match（比賽，關聯實體）— 本 feature 不擁有，僅定義互動邊界

`courts` 表本身不新增任何指向 `matches` 的欄位（`matches.court_id` 由 003 spec 建立與擁有）。本 feature 於 `delete_court()` 提供 `AbandonCourtMatchesHook`（見 research.md #2）作為未來串接點，本 feature 內預設為 no-op，**不**建立 `matches` 資料表或其模型。

## 5. Roster Entry（關聯實體）— 本 feature 不擁有

US4 之手動安排選人介面（FR-021/022）依賴 `roster_entries` 的「目前是否已在其他場地進行中比賽」「是否已離開」查詢，此邏輯由 003/004 spec 之領域模組提供；本 feature 於管理頁場地控制區塊僅建立畫面骨架與串接點（見 research.md #3），不實作實際選人查詢邏輯。

## 6. 驗證規則彙總（跨實體）

| 規則 | 適用欄位 | 對應 FR |
|---|---|---|
| 場地名稱必填、trim 非空、≤20 字 | `courts.name` | FR-002 |
| 場地名稱於「目前有效」場地範圍內唯一（排除已軟刪除） | `courts.name` + `deleted_at` | FR-003 |
| 重新產生場地層級連結前 MUST 先檢查 `deleted_at`，優先於版本衝突檢查 | `courts.deleted_at` | FR-028 |
| 計分板連結版本與控制板連結版本彼此獨立 | `courts.scoreboard_link_version` / `control_panel_link_version` | FR-036 |
| 場地數量不設系統上限 | （無對應欄位限制） | FR-037 |

## 7. Migration 範圍

本 feature 的 Alembic migration MUST 為既有 `courts` 表新增：`name`、`scoreboard_token`、`control_panel_token`、`scoreboard_link_version`、`control_panel_link_version`、`created_at` 六個欄位（`id`/`group_id`/`deleted_at` 已由 001 的初始 migration 建立），並新增三個索引：

```sql
ALTER TABLE courts
  ADD COLUMN name VARCHAR(20) NOT NULL,
  ADD COLUMN scoreboard_token UUID NOT NULL DEFAULT gen_random_uuid(),
  ADD COLUMN control_panel_token UUID NOT NULL DEFAULT gen_random_uuid(),
  ADD COLUMN scoreboard_link_version INT NOT NULL DEFAULT 0,
  ADD COLUMN control_panel_link_version INT NOT NULL DEFAULT 0,
  ADD COLUMN created_at TIMESTAMPTZ NOT NULL DEFAULT now();

CREATE UNIQUE INDEX ux_courts_scoreboard_token ON courts (scoreboard_token);
CREATE UNIQUE INDEX ux_courts_control_panel_token ON courts (control_panel_token);
CREATE UNIQUE INDEX ux_courts_group_name_active ON courts (group_id, name) WHERE deleted_at IS NULL;
```

（`name` 無 `DEFAULT`，故此 migration 僅在 `courts` 表目前為空時安全套用——符合現況：001 完工至今尚無任何 feature 會實際寫入 `courts` 資料列。）
