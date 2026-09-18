# Contract: 個人技術儀表板新增優缺點摘要

## 範圍

**不新增端點。** 034／035 的兩支端點回應多一個 `insights`，query 多兩個參數；路徑、授權、既有的 23 項 `metrics`、`trends`、`landing`、`error_breakdown` 完全不變：

- `GET /members/me/match-dashboard`
- `GET /members/{member_id}/match-dashboard`

基準文件：`specs/034-clutch-points-player-dashboard/contracts/member-match-dashboard-api.md`、`specs/035-point-ending-type/contracts/member-match-dashboard-api.md`。本文件只列差異。

## 差異 1：query 參數

新增 `partner_key`、`opponent_key`，定義見 [member-match-records-api.md](./member-match-records-api.md)。

## 差異 2：`insights`

```jsonc
"insights": {
  "status": "ok",                  // ok | insufficient_data | balanced
  "benchmark_group_name": null,    // 本端點恆為 null（團內來源只出現在團內比較端點）
  "strengths": [
    {
      "list": "strength",
      "rule": "rate_vs_overall",
      "level": "strong",           // strong | mild
      "source": "self",            // self | trend | matchup | benchmark
      "metric_key": "team_serve",
      "player": null,
      "params": {
        "value": 0.5810, "numerator": 183, "denominator": 315, "matches_used": 14,
        "baseline": 0.4720, "diff": 0.1090
      }
    }
  ],
  "weaknesses": [ /* ≤ 3 */ ],
  "recent":     [ /* ≤ 2；rule = recent_change */ ],
  "matchups":   [ /* ≤ 2；rule = partner_above_overall | opponent_below_overall；
                     player = { "key": "m:…", "nickname": "…", "member_id": "…" } */ ]
}
```

規則、門檻、`params` 內容、排序與去重：見 [data-model.md](../data-model.md) 的規則表。後端**不回傳句子**；前端以 `playerInsights.rule.<rule>.<variant>` 加 `params` 組句。

## 規則

| 情況 | 回應 |
|---|---|
| 篩選條件（含 `partner_key`／`opponent_key`） | `insights` 與 `metrics` 依同一批比賽產生（FR-019） |
| 沒有任何規則達最低樣本 | `status: "insufficient_data"`，四個清單皆空 |
| 有規則達樣本但無一達門檻 | `status: "balanced"`，四個清單皆空 |
| 某個清單為空、其他不為空 | `status: "ok"`；前端為空清單顯示說明行（FR-018） |
| `total_matches` 為 0 | `status: "insufficient_data"`（儀表板本身沿用 034 的空狀態） |
| `params` 中的每個數字 | 與同一回應 `metrics[].all`／`recent`，或對戰紀錄回應的 `partner_records`／`opponent_records` 中的同一數字**逐位相等**（FR-002、SC-002） |
| 同一份資料重複請求 | 位元組相同的 `insights`（SC-002） |
| `when_leading`／`when_trailing`／`match_point_conversion` | 永不以 `source: "self"` 出現（FR-012、SC-003） |
| 好友端點 | 相同結構；`source` 永不為 `benchmark`（FR-037） |

## 相容性

`insights` 具預設值（`status: "insufficient_data"`、空清單），舊版前端忽略即可。034／035 的 contract 零變動。
