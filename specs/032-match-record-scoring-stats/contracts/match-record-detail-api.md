# Contracts: 比賽詳情回應擴充（`MatchRecordDetailResponse`）

本功能**不新增任何端點**——擴充既有四個端點共用的回應形狀。四個端點的請求路徑、權限驗證、既有錯誤代碼完全不變，只有回應 body 多了 `events[].detail` 與 `player_stats` 兩個欄位。

## 受影響的既有端點（皆不變更路徑/權限，僅回應內容擴充）

| 端點 | 授權 | 服務層函式 |
|---|---|---|
| `GET /groups/{group_id}/match-records/{match_id}` | 現役 Guest/Member（`resolve_active_roster_membership`） | `get_group_match_record_detail` → `build_match_record_detail` |
| `GET /members/me/match-records/{match_id}` | 已登入會員（`require_member`） | `get_member_match_record_detail` → `build_match_record_detail` |
| `GET /members/{member_id}/match-records/{match_id}` | 已登入且已驗證信箱的會員，檢視好友（`require_verified_member` + 好友關係） | `view_member_match_record_detail` → `get_member_match_record_detail` → `build_match_record_detail` |
| （`get_member_match_record_detail` 同時也是「我的團→歷史」清單使用的既有共用函式，路徑同上第二列） | | |

四者最終都呼叫同一個 `build_match_record_detail(session, match)`（`apps/api/app/domains/group/service.py`），因此本次擴充自動套用到全部四處。

## Response（`MatchRecordDetailResponse`，擴充後）

```jsonc
{
  // ...既有欄位完全不變：match_id、round_number、team_a、team_b、
  // score_a、score_b、winner_team、started_at、ended_at、record_completeness...

  "events": [
    {
      "side": "A",
      "delta": 1,
      "score_a": 5,
      "score_b": 3,
      "elapsed_seconds": 128,
      "detail": {
        "scoring_roster_entry_id": "3f9e...uuid",
        "scoring_nickname": "小明",
        "losing_roster_entry_id": "8a1c...uuid",
        "losing_nickname": "小美",
        "landing_x": 0.62,
        "landing_y": 0.18
      }
    },
    {
      "side": "B",
      "delta": 1,
      "score_a": 5,
      "score_b": 4,
      "elapsed_seconds": 145,
      "detail": null  // 這一分：非詳細計分模式、或當時按了「跳過」、
                       // 或按了「確認記錄」但什麼都沒選（research.md Decision 2）
    },
    {
      "side": "A",
      "delta": -1,
      "score_a": 4,
      "score_b": 4,
      "elapsed_seconds": 150,
      "detail": null  // 扣分事件永遠是 null（FR-005）
    }
  ],

  "player_stats": [
    { "roster_entry_id": "3f9e...uuid", "nickname": "小明", "team": "A", "scored_count": 3, "fault_count": 1 },
    { "roster_entry_id": "...uuid",     "nickname": "小華", "team": "A", "scored_count": 0, "fault_count": 0 },
    { "roster_entry_id": "8a1c...uuid", "nickname": "小美", "team": "B", "scored_count": 2, "fault_count": 2 },
    { "roster_entry_id": "...uuid",     "nickname": "小強", "team": "B", "scored_count": 0, "fault_count": 1 }
  ]
}
```

`detail` 個別欄位可能局部為 `null`（例如只記錄了 `scoring_*` 沒有記錄 `losing_*`，或只記錄了落點沒有記錄任一位球員）——前端逐欄位判斷是否顯示，不得因為看到 `detail` 非 `null` 就假設四個子欄位都有值。

## 空資料情境

一場非詳細計分模式的比賽，或詳細計分但每一分都被跳過的比賽：

```jsonc
{
  "events": [
    { "side": "A", "delta": 1, "score_a": 1, "score_b": 0, "elapsed_seconds": 12, "detail": null },
    { "side": "B", "delta": 1, "score_a": 1, "score_b": 1, "elapsed_seconds": 30, "detail": null }
  ],
  "player_stats": []
}
```

`player_stats` 為空陣列時，前端 MUST 顯示「此比賽沒有球員得失分紀錄」提示（FR-008），MUST NOT 顯示全部掛零的統計表。

## 錯誤代碼

不新增任何錯誤代碼——四個端點既有的錯誤代碼（`MEMBERSHIP_REQUIRED`、`MATCH_NOT_FOUND`、`MEMBER_TOKEN_INVALID`、`EMAIL_NOT_VERIFIED`、`SELF_VIEW_NOT_SUPPORTED`、`MEMBER_NOT_FOUND`、`FRIENDSHIP_REQUIRED`、`MATCH_RECORDS_PRIVATE`、`GROUP_MEMBERSHIP_NEVER_HELD`）完全不變，本功能只在既有成功回應的 body 內新增欄位。
