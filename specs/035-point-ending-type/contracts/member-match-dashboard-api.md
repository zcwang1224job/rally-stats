# Contract: 個人技術儀表板新增得分方式指標

## 範圍

**不新增端點。** 034 的兩支端點回應多出 5 項指標與一個 `error_breakdown`；路徑、query 參數、授權（兩者皆 `require_verified_member`；好友端點另經 `_resolve_viewable_member()`）與既有內容完全不變：

- `GET /members/me/match-dashboard`
- `GET /members/{member_id}/match-dashboard`

基準文件：`specs/034-clutch-points-player-dashboard/contracts/member-match-dashboard-api.md`。本文件只列差異。

## 差異 1：`metrics` 由 18 項變為 23 項

新增的 5 項接在既有 18 項**之後**，順序固定；既有 18 項的 key、順序與數值不變。

```jsonc
{ "key": "winner_share",        "kind": "rate",    "better_when": "higher", … },
{ "key": "winners_per_match",   "kind": "average", "better_when": "higher", … },
{ "key": "errors_per_match",    "kind": "average", "better_when": "lower",  … },
{ "key": "error_share_of_lost", "kind": "rate",    "better_when": "lower",  … },
{ "key": "winner_error_ratio",  "kind": "ratio",   "better_when": "higher", … }
```

每項的 `all`／`recent`／`verdict`，以及 `trends` 中對應的序列，全部依 034 既有規則產生（總和相除、`matches_used`、分母 0 → `value: null`、≤ 10 場無對比、`insufficient`、`unchanged` 門檻、5 場移動區間、< 6 場無趨勢、60 點上限）。

| key | 分子 ÷ 分母 |
|---|---|
| `winner_share` | Σ我的主動得分 ÷ Σ(我的主動得分＋對手失誤讓我得的分) |
| `winners_per_match` | Σ我的主動得分 ÷ 納入場數 |
| `errors_per_match` | Σ我的失誤 ÷ 納入場數 |
| `error_share_of_lost` | Σ我的失誤 ÷ Σ(我的失誤＋我被對手主動得分) |
| `winner_error_ratio` | Σ我的主動得分 ÷ Σ我的失誤 |

**納入條件**（五項相同，FR-020）：該場逐分紀錄完整，且我在該場至少有一分（得分或失分）記錄了得分方式。比例類的分母只含**已記錄得分方式**的分數，未記錄的分數不進任何一邊。

## 差異 2：`error_breakdown`

```jsonc
"error_breakdown": {                       // null：篩選結果中我沒有任何失誤紀錄
  "all":    { "out": 41, "net": 28, "serve_fault": 6, "other_error": 3 },
  "recent": { "out": 7,  "net": 9,  "serve_fault": 1, "other_error": 0 }  // null：total_matches ≤ 10
}
```

只計「我被記為失分球員、且得分方式屬於失誤類」的分數；跟隨篩選條件。它是組成，不是指標——沒有 `verdict`，也不出現在 `trends`。

## 規則

| 情況 | 回應 |
|---|---|
| 篩選後沒有任何比賽 | 與 034 相同：`metrics: []`、`error_breakdown: null` |
| 有比賽，但沒有任何一場具備得分方式紀錄 | `metrics` 仍為 23 項；新增 5 項皆 `all: null`、`recent: null`、`verdict: null`；`error_breakdown: null`；既有 18 項不受影響 |
| 我有主動得分紀錄、但沒有任何失誤紀錄 | `winner_error_ratio` 為 `value: null`、`denominator: 0`（顯示「0／0 —」的同一規則）；`error_breakdown: null` |

## 保證（契約／整合測試斷言）

- `metrics` 恆為 0 或 23 項；前 18 項的 key 順序與 034 完全相同。
- 只有一場比賽時，5 項新指標的分子／分母 ＝ 該場 `MatchRecordDetailResponse.ending_stats.players` 中我那一筆的對應欄位（FR-024）。
- `error_breakdown.all` 四項相加 ＝ 各納入場次 `ending_stats.players[我].own_errors` 的總和。
- 未完成信箱驗證 → 403 `EMAIL_NOT_VERIFIED`；好友端點的四種拒絕情境與 034 相同，且回應不含任何新欄位。
- 查詢次數不隨比賽場數成長（沿用 034 的批次載入，不新增查詢）。
