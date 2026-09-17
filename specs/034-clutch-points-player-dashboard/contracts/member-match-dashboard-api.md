# Contract: 個人技術儀表板 API

兩個新的**唯讀** `GET` 端點，回應形狀相同（`MemberMatchDashboardResponse`，見 data-model.md）。

## `GET /members/me/match-dashboard`（本人）

- **授權**：`require_verified_member`（憲章原則 IV：對戰紀錄在信箱驗證前 MUST 鎖定）。與 `GET /members/me/match-records` 相同（Revision 2026-09-18：本功能上線時該端點仍是較寬鬆的 `require_member`，屬既有偏離；已於 `feature/require-verified-match-records` 一併更正，兩者現在一致）。
- **Query 參數**：與 `GET /members/me/match-records` 的篩選參數**完全相同**——`opponent1`、`opponent2`、`partner`、`result`、`date_from`、`date_to`、`round_from`、`round_to`、`self_score_cmp`、`self_score`、`opponent_score_cmp`、`opponent_score`、`match_mode`；驗證規則（長度、`ge`、列舉值）亦同。**沒有 `page`**——儀表板恆對整個篩選結果計算（FR-019）。
- **Errors**：`MEMBER_TOKEN_INVALID`、`EMAIL_NOT_VERIFIED`（403）。

## `GET /members/{member_id}/match-dashboard`（好友檢視，US5）

- **授權**：與既有 `GET /members/{member_id}/match-records` 相同——`require_verified_member`，再經**同一個** `_resolve_viewable_member()`；檢查順序不變：`SELF_VIEW_NOT_SUPPORTED`（400）→ `MEMBER_NOT_FOUND`（404）→ `FRIENDSHIP_REQUIRED` → `MATCH_RECORDS_PRIVATE`。每次請求當下重新檢查，不快取資格（023 FR-008）。
- **Query 參數**：同上（後端透傳整組篩選；目前好友頁前端不帶任何篩選）。
- **Errors**：`MEMBER_TOKEN_INVALID`、`EMAIL_NOT_VERIFIED`、上述四者。
- **副作用**：無。MUST NOT 產生任何通知（FR-036）。

**路由宣告順序**：`/members/me/match-dashboard` MUST 宣告在 `/members/{member_id}/match-dashboard` 之前（比照既有 `match-records`），否則 `me` 會被當成 `member_id` 而得到 422。

## Response（200）

```jsonc
{
  "total_matches": 42,          // 篩選後的比賽總數＝每項指標「共 M 場」的 M
  "recent_window": 10,
  "has_comparison": true,       // total_matches > recent_window
  "metrics": [
    {
      "key": "team_serve",
      "kind": "rate",
      "better_when": "higher",
      "all":    { "value": 0.512, "numerator": 389, "denominator": 760, "matches_used": 31 },
      "recent": { "value": 0.561, "numerator": 101, "denominator": 180, "matches_used": 8 },
      "verdict": "improved"
    },
    {
      "key": "avg_loss_margin",
      "kind": "average",
      "better_when": "lower",
      "all":    { "value": 6.4, "numerator": 147, "denominator": 23, "matches_used": 23 },
      "recent": { "value": 3.8, "numerator": 19,  "denominator": 5,  "matches_used": 5 },
      "verdict": "improved"     // 數字變小＝進步（FR-026）
    },
    {
      "key": "deuce",
      "kind": "rate",
      "better_when": "higher",
      "all":    { "value": 0.444, "numerator": 8, "denominator": 18, "matches_used": 6 },
      "recent": { "value": 0.5,   "numerator": 2, "denominator": 4,  "matches_used": 1 },
      "verdict": "insufficient" // 最近 10 場中具備資料者 < 3 場（FR-027）
    },
    {
      "key": "own_serve",
      "kind": "rate",
      "better_when": "higher",
      "all": null,              // 沒有任何一場具備資料 → 前端顯示該指標專屬的無資料提示（FR-004）
      "recent": null,
      "verdict": null
    }
    // ...恆回傳指標目錄全部 18 項，順序固定（見 data-model.md）
  ],
  "trends": [
    {
      "key": "team_serve",
      "points": [               // 舊到新；每點＝連續 5 場具備資料的比賽；最多 60 點
        { "from_ended_at": "2026-06-02T12:10:00Z", "to_ended_at": "2026-06-16T13:05:00Z",
          "value": 0.47, "numerator": 47, "denominator": 100 }
      ]
    }
    // 具備資料的比賽 < 6 場的指標不出現在此陣列 → 前端顯示「場數不足以呈現趨勢」（FR-029）
  ],
  "landing": {                  // null = 篩選結果中沒有任何落點（FR-034）
    "scored": [[0.82, 0.31], [1.04, 0.5]],   // 新到舊；已正規化：我方恆在左（x < 0.5）；界外值保留
    "lost":   [[0.21, 0.88]],
    "scored_total": 96,          // 我有球員紀錄的得分總數（不論有無落點）
    "lost_total": 71,
    "matches_used": 14,
    "recent_scored_count": 1,    // scored 的前綴長度＝最近 10 場的落點
    "recent_lost_count": 1,
    "recent_scored_total": 22,
    "recent_lost_total": 15,
    "recent_matches_used": 4
  }
}
```

## 規則

| 情況 | 回應 |
|---|---|
| 篩選後沒有任何比賽 | `total_matches: 0`、`has_comparison: false`、`metrics: []`、`trends: []`、`landing: null` |
| `total_matches ≤ 10` | `has_comparison: false`；所有指標 `recent: null`、`verdict: null`；`landing.recent_*` 等於全體值 |
| 指標有納入比賽但分母為 0（例如從未落後） | `value: null`、`denominator: 0`、`matches_used > 0`——前端顯示「0／0 —」 |
| 指標沒有任何一場具備資料 | `all: null`、`recent: null`、`verdict: null` |
| `better_when == null`（`match_points_saved`） | `verdict: null`；`value` 為每場平均、`numerator` 為總次數——前端顯示數值與差異，不標進步／退步 |
| 差異小於門檻（比率 1 個百分點；平均／比值 0.1） | `verdict: "unchanged"` |
| 逐分紀錄不完整的比賽 | 計入 `total_matches` 與最終比分類指標；不計入任何逐分類指標的 `matches_used` |
| `target_score < 11` 的比賽 | 不計入 `endgame` 的 `matches_used`；其餘逐分類指標照常 |
| 單打比賽 | 不計入 `own_serve`／`own_receive` |

## 保證（契約／整合測試斷言）

- 比率類 `value == numerator / denominator`（總和相除，FR-022），MUST NOT 是各場百分比的平均。
- 對任一場比賽，儀表板採用的該場貢獻 ＝ 同一場 `MatchRecordDetailResponse` 中對應欄位換算到該會員視角的值（FR-003）——以「單一比賽的儀表板」對照該場詳情回應做整合測試。
- 同一物理落點在會員分屬 A 隊與 B 隊的兩場比賽中，正規化後座標相同（SC-006）。
- 同一組篩選條件下，`total_matches` ＝ `GET .../match-records` 回應的 `total_matches`（FR-019）。
- 好友端點在四種拒絕情境下回傳與 `match-records` 好友端點完全相同的狀態碼與錯誤代碼，且回應不含任何儀表板資料（SC-010）。
- 查詢次數不隨比賽場數線性成長（逐分資料以批次 `IN` 查詢載入）。
- 時間欄位為 ISO 8601 UTC（Constitution VIII）。
- 尚未完成信箱驗證的會員請求任一端點 → 403 `EMAIL_NOT_VERIFIED`，回應不含任何儀表板資料（Constitution IV）。
