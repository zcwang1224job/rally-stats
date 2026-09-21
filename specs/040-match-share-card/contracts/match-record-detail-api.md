# Contract: 比賽詳情回應新增 `target_score`

**Feature**: 040-match-share-card | **Requirement**: FR-012a、FR-025、FR-026

## 受影響端點（路徑、方法、授權、錯誤碼全部不變）

| 端點 | 使用的入口 | 授權（不變） |
|---|---|---|
| `GET /groups/{group_id}/match-records/{match_id}` | 某團對戰紀錄 | 現役成員（會員或訪客 `guest_session_token`） |
| `GET /members/me/match-records/{match_id}` | 我的對戰紀錄、「我的團」團歷史戰績 | 已驗證會員，曾是該團成員 |
| `GET /members/{member_id}/match-records/{match_id}` | 好友的對戰紀錄 | 已驗證會員，好友關係與隱私設定 |

三者都由 `build_match_record_detail(session, match)` 組裝回應，所以這一項變更只需改一處。

## 回應變更

`MatchRecordDetailResponse` 新增一個欄位：

```jsonc
{
  "match_id": "…",
  "round_number": 3,
  "team_a": [ … ], "team_b": [ … ],
  "score_a": 21, "score_b": 17,
  "winner_team": "A",
  "started_at": "2026-09-21T11:02:10Z",
  "ended_at": "2026-09-21T11:20:42Z",
  "target_score": 21,            // ← 新增：int，必填
  "record_completeness": "complete",
  "events": [ … ],
  // …其餘既有欄位不變
}
```

| 欄位 | 型別 | 可為 null | 語意 |
|---|---|---|---|
| `target_score` | integer | 否 | 比賽建立時快照的獲勝分數（`matches.target_score`）。**與團目前的 `groups.target_score` 無關**；比賽建立後才修改團設定，不影響此值。 |

## 相容性

- 純新增欄位，既有前端呼叫端忽略它就不會有任何行為變化。
- 不新增任何錯誤碼。

## 契約測試（擴充）

1. `tests/contract/test_group_match_record_detail.py`：回應有 `target_score`，型別為 int，等於比賽的快照值。
2. `tests/contract/test_member_match_record_detail.py`：同上，另加一例：建立一場 11 分制比賽並完賽後，把團設定改成 21 分，回應仍為 `11`。
3. `tests/unit/domains/member/test_personal_settings.py`：好友詳情端點的回應同樣帶有 `target_score`。
