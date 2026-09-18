# Contract: 與好友並排比較（新增一支端點）

## `GET /members/{member_id}/match-comparison`

`Depends(security.require_verified_member)`。唯讀；不寫入任何資料、不通知被檢視方（FR-039，沿用 023 FR-011）。

路由 MUST 宣告在 `/members/me/…` 系列之後（與既有 `/{member_id}/match-dashboard` 相同的注意事項）。

### 授權

完全沿用 `_resolve_viewable_member(viewer_id, member_id)`，於**每次請求當下**判定（023 FR-008）：

| 情況 | 回應 |
|---|---|
| `member_id` 是自己 | `400 SELF_VIEW_NOT_SUPPORTED` |
| 對象不存在或未驗證 | `404 MEMBER_NOT_FOUND` |
| 非好友 | `403 FRIENDSHIP_REQUIRED` |
| 對方關閉分享 | `403 MATCH_RECORDS_PRIVATE` |

檢視者本人**不需要**開啟自己的分享設定（規格 Assumptions）。

### 回應

```jsonc
{
  "friend_total_matches": 142,
  "my_total_matches": 97,
  "metrics": [                     // 23 項，key 與順序同儀表板；皆為未篩選的「全部」範圍
    {
      "key": "team_serve", "kind": "rate", "better_when": "higher",
      "friend": { "value": 0.5120, "numerator": 640, "denominator": 1250, "matches_used": 88 },
      "me":     { "value": 0.4870, "numerator": 380, "denominator": 780,  "matches_used": 52 },
      "better": "friend"           // me | friend | tie | null
    }
  ],
  "head_to_head": {
    "as_opponents": { "matches": 9, "wins": 4, "losses": 5, "win_rate": 0.4444, "avg_margin": -1.2 },
    "as_partners":  null           // 從未同隊
  }
}
```

### 規則

| 情況 | 回應 |
|---|---|
| `friend`／`me` 的值 | 分別等於對方與我的儀表板在未套用篩選時同一指標的 `all`（US4-1） |
| 任一方 `value` 為 null 或 `matches_used < 3` | `better: null`（US4-2）；有資料的一方照常回傳 |
| `better_when` 為 null | `better: null` |
| 兩值相等 | `better: "tie"` |
| `head_to_head` | 從**檢視者**的比賽中找出好友（`m:<friend_id>`）；`wins`／`avg_margin` 皆為檢視者的角度 |
| 兩人從未同場 | `as_opponents` 與 `as_partners` 皆為 null；前端顯示明確文字（US4-3） |
| 好友的團內比較 | 本端點與好友頁的任何端點皆不提供（FR-037） |

### 隱私

回應只含「對方已授權好友查看的彙總數字」與「檢視者自己的數字」。檢視者的數字不會因此對好友或任何第三者可見——沒有任何寫入、紀錄或通知。
