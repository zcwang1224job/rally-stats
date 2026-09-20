# Contract: live state 新增 `target_score` 與 `cap_score`

**Feature**: 039-match-point-confirm | **Date**: 2026-09-20

對外契約的改動只有一項：兩個既有 schema 各加兩個整數欄位。沒有新端點、沒有新錯誤碼、沒有 migration。

## 1. `MatchSummary` — 管理頁排程快照

`ScheduleResponse.courts[].current_match` 的型別，因此所有回傳 `ScheduleResponse` 的端點都會帶上新欄位：

| 端點 | 方法 |
|---|---|
| `/groups/{group_id}/schedule` | GET |
| `/groups/{group_id}/next-round` | POST |
| `/groups/{group_id}/schedule/end-round` | POST |
| `/groups/{group_id}/schedule/plan` | POST |
| `/groups/{group_id}/schedule/start` | POST |

全部走既有的 `require_admin`，權限模型不變。

```jsonc
{
  "current_match": {
    "match_id": "…",
    "status": "in_progress",
    "participants": [ /* … */ ],
    "score_a": 20,
    "score_b": 15,
    "serve": { /* … */ },
    "detailed_scoring_enabled": false,
    "target_score": 21,   // ← 新增
    "cap_score": 30       // ← 新增
  }
}
```

## 2. `MatchLiveDetail` — 公開畫面 live state

`CourtLiveState.current_match` 的型別，供單一場地控制板、全場地控制板與記分板使用。相關端點（皆為既有 token 驗證，不變）：

| 端點 | 回應型別 | 使用它的畫面 |
|---|---|---|
| `GET /courts/by-token/{token}/state` | `CourtStateResponse` | 單一場地控制頁面**與記分板**（兩者共用同一個場地 token 端點） |
| `GET /groups/by-all-courts-token/{token}/state` | `AllCourtsLiveState` | 全場地控制板 |

公開畫面總共只有這兩個 state 端點，兩者的 `current_match` 都是 `MatchLiveDetail`，所以改這一個 schema 就同時涵蓋三個公開畫面。回應片段與上方 `MatchSummary` 相同，欄位語意一致。

## 3. 欄位語意

- **值的來源**：`matches.target_score` 與 `matches.cap_score`——比賽建立當下對團設定所做的快照，**不是** `groups.*` 的即時值（憲章原則 III）。
- **管理員中途調整團的比賽設定**，進行中比賽的這兩個值 MUST NOT 改變；下一場新建立的比賽才反映新設定。
- **必填**（無預設值）：資料庫欄位本身 `nullable=False`，每場比賽都必然有值。刻意不給預設值，避免「後端漏填」退化成靜默的錯誤判定（例如預設 0 會讓每一分都被當成決勝分）。

## 4. 刻意不送的欄位

**`deuce_threshold` MUST NOT 被加進這兩個 schema。**

它不參與獲勝判定——後端 `service.py:3072` 的 `match_wins()` 有一行註解明寫這件事：

```python
def match_wins(score_x, score_y, target_score, cap_score) -> bool:
    """達標判定公式——`deuce_threshold` 不參與運算"""
    return score_x >= cap_score or (score_x >= target_score and score_x - score_y >= 2)
```

把它一併送到前端，只會誘使日後的實作者拿它來判斷 deuce 而寫出錯誤的確認時機。需要它的地方（`MatchDetailResponse`）已經有了。

## 5. 非變更

- 不新增端點、不移除欄位、不改變任何既有欄位的型別或語意。
- 純新增欄位，對既有前端**向後相容**。
- 前端型別宣告為可選（`target_score?: number`），舊版後端讀成 `undefined` 時判定函式回傳 `false`，退回現行的直接加分行為。

## 6. 前端共用介面

`apps/web/src/app/core/match-point.ts`

```ts
export function isMatchPoint(
  scoringSideScore: number,
  opponentScore: number,
  targetScore: number | undefined,
  capScore: number | undefined,
): boolean
```

語意與邊界對照表見 [data-model.md](../data-model.md)。這支函式是四個計分畫面唯一的判定來源。

## 7. 共用元件契約擴充

`ConfirmDialogComponent`（`features/group-admin/shared/confirm-dialog.component.ts`）新增：

```ts
readonly closed = output<void>();   // 由 <dialog> 原生 close 事件觸發
```

涵蓋確認鈕、取消鈕與 **Esc** 三條關閉路徑。純新增，14 個既有使用處不受影響。

## 8. 語系檔新增（本功能唯一的文案改動）

`apps/web/src/assets/i18n/zh-TW.json` 與 `en.json`，置於既有的 `controlPanel` 之下：

| key | zh-TW | en |
|---|---|---|
| `controlPanel.matchPointConfirmTitle` | 確認這一分結束比賽？ | Confirm the point that ends this match? |
| `controlPanel.matchPointConfirmBody` | 此操作無法復原，本場比賽將結束並計入戰績。 | This cannot be undone. The match will end and the result will count toward records. |

刻意與既有的 `endMatchConfirmBody`（「此操作無法復原，本場比賽將視為已捨棄，不計入戰績。」）採同一句型、相反結論——兩者都是結束比賽的確認，差別正是計不計入戰績。

## 9. 契約測試要求

- **新增**：`GET /groups/{group_id}/schedule` 的 `current_match` 帶出比賽快照的 `target_score` / `cap_score`。
- **新增**：公開 token 的 state 端點同樣帶出這兩個欄位。
- **新增**：比賽開打後調整團的比賽設定，進行中比賽的這兩個值維持原值（憲章原則 III）。
- **不需新增**：本功能不新增端點，既有端點的其他契約測試不受影響。
