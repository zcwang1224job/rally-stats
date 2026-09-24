# Contract: 活動目錄、自訂活動、活動篩選

**Feature**: 043-sport-type-plugin-foundation | **Date**: 2026-09-24

## 1. `GET /sports`

授權：`optional_member`（登入時多回 `custom[]`）。回應：

```jsonc
{
  "types": [
    {
      "type_key": "net_rally",
      "team_size_range": [1, 2],
      "modules": ["serve_tracking", "shot_placement"],
      "params_schema": { /* JSON Schema，來自外掛 params_schema() */ },
      "section_kinds": ["net_rally.match_detail", "net_rally.dashboard"]
    },
    { "type_key": "frames", "team_size_range": [1, 2], "modules": [], "params_schema": {…}, "section_kinds": ["frames.frame_list", "frames.frame_trend", "frames.dashboard_summary"] },
    { "type_key": "generic", "team_size_range": [1, 2], "modules": [], "params_schema": {…}, "section_kinds": [] }
  ],
  "builtin": [
    {
      "sport_key": "badminton",
      "type_key": "net_rally",
      "name_key": "sports.badminton",
      "icon": "shuttle",
      "team_size_options": [1, 2],
      "defaults": { "team_size": 1, "end_mode": "target", "target_score": 21, "win_by": 2, "cap_score": 30,
                    "allow_draw": false, "score_steps": [1], "type_params": { "modules": { "serve_tracking": true, "shot_placement": true } } },
      "nouns": { "venue": "sports.nouns.court", "score": "sports.nouns.point", "member": "sports.nouns.player" }
    }
    // … table_tennis, pickleball, tennis_tiebreak, billiards, darts, board_game, esports, other
  ],
  "custom": [
    { "id": "…", "name": "躲避球對抗", "type_key": "generic", "team_size_options": [2],
      "defaults": { … }, "created_at": "2026-09-24T02:00:00Z" }
  ]
}
```

- `builtin` 順序即前端目錄顯示順序；`other` 永遠最後。
- `defaults.type_params` 已通過該類型的 `params_schema` 驗證。

## 2. 自訂活動

| 方法 | 路徑 | 授權 | 說明 |
|---|---|---|---|
| `POST` | `/members/me/sports` | `require_verified_member` | 建立；body 見下；`201` 回同 `custom[]` 元素 |
| `DELETE` | `/members/me/sports/{sport_id}` | `require_verified_member` | 硬刪除；`204`；非本人 → `404 CUSTOM_SPORT_NOT_FOUND` |

`POST` body：

```jsonc
{ "name": "躲避球對抗", "type_key": "generic", "team_size_options": [2],
  "defaults": { "team_size": 2, "end_mode": "manual", "target_score": 1, "win_by": 1, "cap_score": null,
                "allow_draw": true, "score_steps": [1], "type_params": {},
                "nouns": { "venue": "sports.nouns.arena", "score": "sports.nouns.point", "member": "sports.nouns.player" } } }
```

錯誤碼：`422 VALIDATION_ERROR`（名稱長度、`type_key` 未註冊、`team_size_options` 超出範圍、`defaults` 不符通用規則或 `params_schema`）、`409 CUSTOM_SPORT_NAME_TAKEN`（同會員同名）、`409 CUSTOM_SPORT_LIMIT`（第 21 筆）。名詞只能從固定集合選（`court|table|board|arena|station|venue` × `point|frame|score` × `player|member|competitor`），前端以 i18n key 顯示。

本期不提供 `PATCH`（clarify Q3）。

## 3. 開團與編輯的請求／回應變更

### `POST /groups`（`CreateGroupRequest`）新增欄位

```jsonc
{
  "sport": { "sport_key": "billiards" }                        // 內建
  // 或 { "sport_key": "custom", "custom_sport_id": "…" }        // 會員自訂（需登入且為本人）
  // 或 { "sport_key": "other", "name": "趣味賽" }               // 訪客或會員的一次性活動
  , "team_size": 1,                    // 與 match_mode 至少一個；兩者皆給須一致
  "match_mode": "singles",             // 相容別名，選填
  "end_mode": "target", "target_score": 5, "win_by": 1, "cap_score": null,
  "allow_draw": false, "score_steps": [1],
  "type_params": { "frame_scoring_enabled": false, "frame_target": null, "frame_win_by": 1 },
  "scoring_mode": "custom"            // 既有欄位；隔網回合制以外一律 custom；羽球沿用 21pt/15pt/custom
  // … 既有欄位不變
}
```

- `sport` 省略 ⇒ 羽球（零變更：既有 130 個契約測試的 payload 不含 `sport`）。
- 未給的通用參數以活動 `defaults` 補齊；給了則依 §2 規則驗證（`422`）。
- `sport_key='custom'` 但未登入或非本人 → `403 CUSTOM_SPORT_FORBIDDEN`。
- `team_size ∉ 活動的 team_size_options` → `422`。

### `PATCH /groups/{id}`（`EditGroupRequest`）

新增可編輯：`team_size`（與 `match_mode` 同步）、`end_mode`、`win_by`、`cap_score`、`allow_draw`、`score_steps`、`type_params`。**不可**編輯 `sport`：收到與現值不同的 `sport` → `409 SPORT_IMMUTABLE`。既有 `expected_version` 樂觀鎖沿用。

### 回應

`GroupPublicResponse`、`GroupListItem`、`JoinLinkPreviewResponse`、`AdminGroupResponse`、`MyGroupSummary` 一律新增：

```jsonc
"sport": { "sport_key": "billiards", "type_key": "frames", "name_key": "sports.billiards", "name": null,
           "icon": "billiards", "nouns": { "venue": "sports.nouns.table", "score": "sports.nouns.frame", "member": "sports.nouns.player" } },
"team_size": 1
```

自訂／其他：`name_key: null`、`name: "躲避球對抗"`。既有 `match_mode` 欄位保留。

## 4. 列表篩選

### `GET /groups`

新增查詢參數 `sport`：值為內建 `sport_key`，或 `custom_or_other`（涵蓋 `sport_key IN ('custom','other')`）。與既有 `match_mode` 等篩選可並用。

### `GET /members/me/groups`

新增查詢參數 `sport`：內建 `sport_key`、`custom_or_other`、或 `custom:<custom_sport_id>`（只列該自訂活動的團；非本人的 id → 空結果）。

### 四個 records／dashboard 路由（`match_filters_query`）

`/members/me/match-records`、`/members/{id}/match-records`、`/members/me/match-dashboard`、`/members/{id}/match-dashboard` 一律新增 `sport`（同上值域；另接受 `other:<name>` 以名稱歸類「其他」團）。四者參數集合維持相同（既有測試 `test_member_matchups.py:300-320` 驗證）。**`sport` 省略時只納入隔網回合制（`type_key='net_rally'`）活動的比賽**，因此只有羽球資料的既有測試結果不變；不同活動之間永不混算（FR-026）。`dashboard-sections` 的 `sport` 為必填。

## 5. 會員的活動清單

| 方法 | 路徑 | 授權 |
|---|---|---|
| `GET` | `/members/me/activities` | `require_verified_member` |
| `GET` | `/members/{member_id}/activities` | 既有好友檢視授權（與 `/members/{id}/match-records` 相同） |

回應（依 `match_count` 降冪，再依名稱）：

```jsonc
{ "activities": [
  { "sport": { …SportSummary… }, "filter_value": "badminton", "match_count": 42 },
  { "sport": { …SportSummary… }, "filter_value": "custom:9f1…", "match_count": 3 },
  { "sport": { …name: "趣味賽"… }, "filter_value": "other:趣味賽", "match_count": 1 }
] }
```

`filter_value` 即可直接餵給 §4 的 `sport` 參數，前端不自行組字串。只有一筆時前端不顯示頁籤列（FR-026）。

## 6. system_config

新增 key（讀取規則見 data-model §6）：`default_group_name_suffix.<sport_key>`、`default_court_name.<sport_key>`。`docs/tools.md` 的共同設定表需同步（實作任務）。
