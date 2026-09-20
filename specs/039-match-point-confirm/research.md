# Phase 0 Research: 決勝分二次確認

**Feature**: 039-match-point-confirm | **Date**: 2026-09-20

spec 的 Clarifications 已把產品面問題定案，無待解的 NEEDS CLARIFICATION。本文記錄實作面的調查結果，其中 Decision 1 與 Decision 3 是兩個不查就會踩到的坑。

## 現況盤點

四個計分畫面的「+」目前都是同一個兩路分支：

```html
(click)="match.detailed_scoring_enabled ? scoreThenOpenPicker(X) : score(X, 1)"
```

| 畫面 | 元件 |
|---|---|
| 單一場地控制頁面 | `control-panel.component` |
| 全場地控制板 | `control-panel/all-courts/all-courts-court-block.component` |
| 記分板 | `scoreboard.component` |
| 開團管理頁場地控制 | `group-admin/schedule-management/court-control.component` |

四者都已經匯入 `ConfirmDialogComponent`（各自有「提前結束」的確認框），所以要多掛一個確認框不需要新的相依。

## Decision 1：`ConfirmDialogComponent` 要新增 `closed` output，綁在原生 `close` 事件上

**Decision**：在 `apps/web/src/app/features/group-admin/shared/confirm-dialog.component.ts` 新增 `readonly closed = output<void>()`，由 `<dialog>` 的原生 `(close)` 事件觸發，而不是從 `cancel()` 方法發出。

**Rationale**：這是本功能最關鍵的一個調查結果。現在的 `ConfirmDialogComponent` **只有 `confirmed` 一個 output**，沒有任何「關閉了但沒確認」的訊號。而本功能必須在元件裡記住「這次確認是要幫哪一隊加分」（因為 `confirmed` 不帶 payload），這份狀態一旦沒被清掉，下一次按「+」就會卡住。

更關鍵的是**鍵盤 Esc**：原生 `<dialog>` 按 Esc 會直接關閉，**完全不會經過元件的 `cancel()` 方法**。所以若把訊號掛在 `cancel()` 上，使用者按 Esc 取消後狀態會殘留，那個場地的決勝分從此再也按不動——而且是靜默失效，最難查。綁在原生 `close` 事件上則三條路徑（確認鈕、取消鈕、Esc）全部涵蓋。

事件順序也剛好正確：`confirm()` 先 emit `confirmed`、再關閉 dialog 觸發 `closed`，所以 `confirmed` 的處理函式讀得到尚未被清除的隊伍。

**向後相容**：全專案有 14 個檔案使用 `app-confirm-dialog`，新增一個沒人繫結的 output 對它們零影響。

**Alternatives considered**：
- *從 `cancel()` 發出 `cancelled`*：漏掉 Esc，就是上面說的靜默卡死。
- *不存任何狀態*：`confirmed` 沒有 payload，無從得知要加哪一隊的分。
- *左右各放一個確認框*：兩個 dialog、兩組 viewChild，只為了省一個 signal，不划算；而且文案與行為完全相同。

## Decision 2：一個確認框 + `pendingMatchPointSide` signal

**Decision**：每個元件加一個 `readonly pendingMatchPointSide = signal<Team | null>(null)`，搭配單一個 `#matchPointDialog`。按下決勝分的「+」時設定它並開啟 dialog；`(confirmed)` 讀它送分；`(closed)` 清掉它。

**Rationale**：確認框的內容與哪一隊無關，沒有理由做兩個。dialog 以 `showModal()` 開啟是**模態**的，開啟期間底下的「+」按鈕點不到，所以不需要額外的互斥旗標。

## Decision 3：**不要**在開啟確認框時動 `ScoreTapGuard`

**Decision**：確認流程完全不碰 `ScoreTapGuard`；`(confirmed)` 直接呼叫既有的 `score(side, 1)`，由它自己 `tryAcquire()` / `release()`。

**Rationale**：這是第二個坑。直覺上會想「一按下去就先鎖住，免得連點」，但 `ScoreTapGuard.tryAcquire()` 之後**只有 `release()` 能解鎖**，而取消（尤其是 Esc）沒有任何 release 的時機。結果會是：使用者取消一次確認框，那個場地的計分按鈕就永久鎖死，而且畫面上毫無錯誤訊息。

把 guard 完全留在 `score()` 裡面，取消就是零成本——沒有送出任何請求，也沒有任何狀態需要回滾。連點的防護由 Decision 2 的模態特性負責。

**Alternatives considered**：*確認後才 `hold()`*：沒必要，`score()` 本來就會 `tryAcquire()`。

## Decision 4：判定邏輯抽成 `core/match-point.ts` 純函式

**Decision**：新增 `apps/web/src/app/core/match-point.ts`，匯出一個純函式，語意對應後端 `service.py` 的 `match_wins()`：

```
isMatchPoint(scoringSideScore, opponentScore, targetScore, capScore)
  = match_wins(scoringSideScore + 1, opponentScore, targetScore, capScore)
```

**Rationale**：四個元件需要完全相同的判斷，`core/*.ts` 搭配同名 `.spec.ts` 是本專案既有的純函式放置慣例（`waiting-reason-label.ts`、`benchmark-group-preference.ts`）。集中一處才能用一份單元測試釘住 deuce 與 cap 兩種邊界。

**必須注意**：後端的 `match_wins()` 有一行註解明寫 **`deuce_threshold` 不參與運算**。前端這支函式也 MUST NOT 使用它——20:20 加一分只有 21:20、領先 1 分，不算獲勝，**不該跳確認**。這是本功能最容易寫錯的地方，單元測試要直接鎖住。

## Decision 5：後端只送 `target_score` 與 `cap_score`，不送 `deuce_threshold`，也不送伺服器算好的布林值

**Decision**：`MatchSummary`（管理頁排程快照）與 `MatchLiveDetail`（公開畫面 live state）各新增 `target_score: int` 與 `cap_score: int`，值取自 `Match` 的**每場快照欄位**（`apps/api/app/domains/schedule/models.py:35-37`）。

**Rationale**：

1. **為什麼不送伺服器算好的 `match_point_a` / `match_point_b` 布林值**：那種欄位會失效。038 在管理頁做的凍結會在本地 patch `score_a` / `score_b`，控制頁面與記分板也各自就地 patch 比分——伺服器在送出快照當下算的布林值，到了下一分就是錯的，而且得額外掛到 `ScoreMutationResult` 上才能跟著更新。**靜態欄位不會過期**：目標分與上限分在一場比賽內恆定不變，取一次就能一直算。
2. **為什麼不送 `deuce_threshold`**：它不參與獲勝判定（Decision 4）。送過去只會讓人以為該用它，反而製造 bug。
3. **為什麼讀比賽快照而非團設定**：憲章原則 III，與 038 的 `detailed_scoring_enabled` 同一套語意。

**建構點各只有一處**，改動極小：
- `MatchSummary` → `service.build_schedule_snapshot()`（約 L2064）
- `MatchLiveDetail` → `service.py` 約 L3907

**Alternatives considered**：*前端改打 `GET .../matches/{id}` 拿 `MatchDetailResponse`*（它已經有這三個欄位）：等於每個場地每場比賽多一次請求，只為兩個永不改變的整數，不划算。

## Decision 6：「+」的三路分支移進 TypeScript，模板只呼叫一個方法

**Decision**：四個模板的「+」一律改成 `(click)="plusPressed(leftTeam())"`（右側同理），分支邏輯寫在元件的 `plusPressed(side: Team)` 裡：

```
詳細模式          → scoreThenOpenPicker(side)   （現狀不變）
簡易模式 + 決勝分 → 開啟確認框
其他              → score(side, 1)              （現狀不變）
```

**Rationale**：現在的模板已經是一個三元運算子，再塞第三個條件會變成巢狀三元式，既難讀也無法單獨測試。搬進 TS 之後模板反而比現在更乾淨，分支也能直接寫單元測試。

## Decision 7：確認文案沿用「提前結束」的句型，但語意相反

**Decision**：新增四個語系 key（`controlPanel.matchPointConfirmTitle` / `matchPointConfirmBody`，zh-TW 與 en 各一組），`variant` 用 `primary`。

既有的「提前結束」文案是：

> 此操作無法復原，本場比賽將視為**已捨棄，不計入戰績**。

本功能正好是它的鏡像，句型沿用、結論相反：

> 此操作無法復原，本場比賽將**結束並計入戰績**。

**Rationale**：兩個都是「結束比賽」的確認，放在同一個畫面上，句型一致才看得出差別在哪；而差別恰恰是計不計入戰績，這正是 spec FR-002 要講清楚的重點。`variant` 用 `primary` 而非 `danger`——依元件自己的註解，紅色保留給「會摧毀東西」的操作，而正常打完一場比賽不是破壞行為（「提前結束」同樣用 `primary`）。

## Decision 8：測試策略

- **後端**：契約測試驗證兩個 live state 端點都帶出比賽快照的 `target_score` / `cap_score`，且不隨團設定中途變更而改變。
- **前端（純函式）**：`core/match-point.spec.ts` 釘住邊界——一般領先、deuce（20:20 不跳）、cap（29:29 要跳）、雙方同時決勝分。
- **前端（元件）**：四個元件各自驗證三路分支、確認後才送分、取消後不送分且能繼續計分。

**Rationale**：憲章原則 II 要求比分相關邏輯附帶測試。風險集中在純函式的邊界判斷，所以那一支測試最密；元件層只需確認分支接對了。

## 風險與注意事項

1. **Esc 鍵**（Decision 1）：實作完成後務必實際用鍵盤 Esc 關掉確認框，再按一次「+」，確認還能正常開啟。這條路徑用 jsdom 單元測試驗不出來（jsdom 沒有實作 `<dialog>`），必須在真的瀏覽器上看。
2. **`ScoreTapGuard` 死鎖**（Decision 3）：若有人日後「順手」把 guard 移到確認框之前，會造成取消一次就永久鎖死。已在 Decision 3 寫明原因，實作時也應在程式碼加註解。
3. **`deuce_threshold` 誤用**（Decision 4）：最容易寫錯的一行。單元測試必須有 20:20 的案例。
4. **四個元件重複**：本功能在四個元件寫下幾乎相同的 `plusPressed()` 與確認框繫結。這是既有架構的既定樣貌（四個計分畫面本來就各自實作），本次不做共用抽象重構——真正的共用邏輯（判定）已經抽進 `core/match-point.ts`，剩下的只是繫結。
