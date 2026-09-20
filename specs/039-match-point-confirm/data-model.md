# Phase 1 Data Model: 決勝分二次確認

**Feature**: 039-match-point-confirm | **Date**: 2026-09-20

## 資料庫層：零變更

**不新增資料表、不新增欄位、不需要 Alembic migration。**

本功能需要的資料庫欄位早就存在，而且從一開始就是每場比賽的快照：

| 既有欄位 | 位置 | 本功能的關係 |
|---|---|---|
| `matches.target_score` | `schedule/models.py:35` | 唯讀，要送到前端 |
| `matches.cap_score` | `schedule/models.py:37` | 唯讀，要送到前端 |
| `matches.deuce_threshold` | `schedule/models.py:36` | **刻意不送**（不參與獲勝判定，見 research.md Decision 4／5） |
| `matches.detailed_scoring_enabled` | `schedule/models.py:49` | 唯讀，038 已送到四個畫面，本功能用它決定要不要跳確認 |

## 傳輸層：兩個 schema 各加兩個欄位

### `MatchSummary`（管理頁排程快照）

`apps/api/app/domains/schedule/schemas.py`

| 欄位 | 型別 | 狀態 |
|---|---|---|
| `match_id` / `status` / `participants` / `score_a` / `score_b` / `serve` | — | 既有 |
| `detailed_scoring_enabled` | `bool` | 既有（038） |
| **`target_score`** | **`int`** | **新增** |
| **`cap_score`** | **`int`** | **新增** |

### `MatchLiveDetail`（公開畫面 live state）

同檔案。欄位與狀態同上——`detailed_scoring_enabled` 自 031 起既有，本功能加同樣兩個欄位。

### 預設值的選擇

兩個新欄位**不給預設值**（必填），與同 schema 的 `target_score` 在 `MatchDetailResponse` 中的既有寫法一致。理由：這兩個值在每一場比賽上都必然存在（資料庫欄位 `nullable=False`），給預設值反而會讓「後端忘了填」變成靜默的錯誤判定——例如預設 0 會讓每一分都被算成決勝分。

前端型別則宣告為**可選**（`target_score?: number`），讓舊版後端讀起來是 `undefined`；前端判定函式收到 `undefined` 時一律回傳 `false`（不跳確認），退回現行行為。

## 前端：新增一支純函式

`apps/web/src/app/core/match-point.ts`

```
isMatchPoint(
  scoringSideScore: number,      // 要加分那一隊目前的分數
  opponentScore: number,
  targetScore: number | undefined,
  capScore: number | undefined,
): boolean
```

**語意**：這一隊再得一分會不會獲勝。對應後端 `service.py:3072` 的 `match_wins()`：

```
加分後分數 = scoringSideScore + 1
回傳 加分後分數 >= capScore
     或 (加分後分數 >= targetScore 且 加分後分數 - opponentScore >= 2)
```

**約束**：
- `targetScore` 或 `capScore` 為 `undefined` 時 MUST 回傳 `false`（舊後端相容，退回現行行為）。
- MUST NOT 使用 `deuce_threshold`——它不參與判定，且刻意沒有被送到前端。

**邊界對照表**（單元測試直接照抄）：

| 情境 | 目前比分 | 目標／上限 | 加分後 | 是決勝分？ | 為什麼 |
|---|---|---|---|---|---|
| 一般賽末點 | 20:15 | 21 / 30 | 21:15 | ✅ | 達標且領先 6 |
| 還差兩分 | 19:15 | 21 / 30 | 20:15 | ❌ | 未達 21 |
| deuce | 20:20 | 21 / 30 | 21:20 | ❌ | 達標但只領先 1 |
| deuce 後領先 | 21:20 | 21 / 30 | 22:20 | ✅ | 達標且領先 2 |
| 打到上限 | 29:29 | 21 / 30 | 30:29 | ✅ | 達上限，不看分差 |
| 上限前一分 | 28:29 | 21 / 30 | 29:29 | ❌ | 未達上限、也沒領先 2 |
| 雙方同時 | 20:20→各自 | 21 / 30 | — | 兩邊都 ❌ | 見 deuce 列 |
| 雙方同時（上限） | 29:29 | 21 / 30 | — | 兩邊都 ✅ | 任一方得分都到 30 |

## 前端元件狀態

每個計分元件新增：

| 狀態 | 型別 | 用途 | FR |
|---|---|---|---|
| `pendingMatchPointSide` | `signal<Team \| null>` | 確認框正在替哪一隊確認；`null` 表示沒有進行中的確認 | FR-001、FR-003 |
| `matchPointDialog` | `viewChild<ConfirmDialogComponent>` | 決勝分專用的確認框（與既有的 `endMatchDialog` 並存） | FR-001 |

## 共用元件的擴充

`ConfirmDialogComponent` 新增一個 output：

| 成員 | 型別 | 狀態 | 說明 |
|---|---|---|---|
| `confirmed` | `output<void>` | 既有 | |
| **`closed`** | **`output<void>`** | **新增** | 由 `<dialog>` 的原生 `close` 事件觸發，涵蓋確認鈕、取消鈕與 **Esc** 三條關閉路徑 |

純新增，14 個既有使用處不繫結它、完全不受影響。

## 狀態轉移

```text
按下「+」
  ├─ 詳細模式                → scoreThenOpenPicker(side)    ［現狀，不變］
  ├─ 簡易模式 且 isMatchPoint → pendingMatchPointSide = side
  │                            matchPointDialog.open()
  │                              ├─ (confirmed) → score(side, 1) ──┐
  │                              │                                  │
  │                              └─ (closed)  → pendingMatchPointSide = null
  │                                 ↑ 確認鈕／取消鈕／Esc 都會走到這裡
  └─ 其他                    → score(side, 1)                ［現狀，不變］

註：(confirmed) 必定早於 (closed) 觸發，所以送分時讀得到尚未清除的 side。
```

## 不變的約束

- **伺服器仍是唯一判定者**（憲章原則 X）：前端的決勝分判定只決定「要不要先問一句」，真正的結束與比賽結果一律由伺服器在收到該分後決定（FR-013）。前端判斷錯了最多是多問或少問一次，不會造成比分或結果不一致。
- **快照優先**（憲章原則 III）：判定一律用比賽自己的 `target_score` / `cap_score`，不讀團的當下設定。
- **`ScoreTapGuard` 只在 `score()` 裡**（research.md Decision 3）：確認流程不得取得它，否則取消一次就會永久鎖死該場地的計分。
