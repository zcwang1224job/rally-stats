# 039: 決勝分二次確認

## 問題

簡易模式（未啟用「比賽詳細設定」）的決勝分，是整個計分流程中唯一「一按定生死、而且完全沒有提示」的操作。而且情況比「沒有復原鍵」更糟：

1. **「-1」會靜默失效。** `apply_score_delta()` 的更新條件是 `Match.status == "in_progress"`，所以比賽一結束，任何加減分都只是回傳 `applied=False`，畫面上的比分紋風不動。計分者按了「-1」卻什麼都沒發生，第一反應是「我是不是沒按到」，不會想到真正的原因是比賽已經結束。
2. **那一分寫下的是永久紀錄。** 自然達標結束的比賽會產生比賽結果、計入戰績與排名。這和「提前結束」正好相反——提前結束視為已捨棄、不計入任何統計。
3. **開啟詳細設定的團早就有退路。** 038 的詳細記錄視窗有「取消這一分」，連賽末點都能連同比賽的結束判定一起撤銷。唯獨簡易模式什麼都沒有。

本功能替簡易模式的決勝分補上二次確認，四個計分畫面一致。

## 做法

**判定**：新增 `apps/web/src/app/core/match-point.ts` 一支純函式，對應後端 `service.py` 的 `match_wins()`。後端在兩個 live state schema 各補上 `target_score` 與 `cap_score`（取自比賽自己的快照欄位），前端才算得出「下一分會不會贏」。

**分支**：四個畫面的「+」統一走 `plusPressed()`，三路分支——詳細模式走 038 的 picker、簡易模式遇決勝分先確認、其餘直接送分。「-1」完全不變。

## 三個刻意的設計決定

### 1. 確認框的關閉訊號綁在原生 `close` 事件，不是 `cancel()`

`ConfirmDialogComponent` 原本**只有 `confirmed` 一個 output**。本功能必須記住「這次確認要幫哪一隊加分」（`confirmed` 不帶 payload），這份狀態沒清掉，下一次按「+」就會卡住。

關鍵在 **Esc**：原生 `<dialog>` 按 Esc 會直接關閉，**完全不經過元件的 `cancel()`**。訊號若掛在 `cancel()` 上，使用者按一次 Esc 取消後狀態就殘留，那個場地的決勝分從此再也按不動，而且是靜默失效。改綁原生 `close` 事件後，確認鈕／取消鈕／Esc 三條路徑全部涵蓋。純新增 output，全專案 14 處既有使用不受影響。

### 2. `plusPressed()` 絕不取得 `ScoreTapGuard`

直覺會想「先鎖住免得連點」，但 `tryAcquire()` 只有 `release()` 能解，而取消（尤其是 Esc）沒有任何 release 的時機。結果會是**取消一次，那個場地的所有計分按鈕永久鎖死**，畫面上毫無錯誤訊息。防連點改由 `plusPressed()` 自己的重入旗標負責。

### 3. 重入防護寫在程式碼裡，不依賴「dialog 是模態」

`showModal()` 在真實瀏覽器確實會擋住底下的按鈕，但 **jsdom 完全沒有實作 `<dialog>`**，所以這個假設既測不到也證不了。`plusPressed()` 開頭直接檢查 `pendingMatchPointSide() !== null`，讓 FR-014 由結構保證，測試也驗得出來。

（此外，確認後的送分走 `score(side, 1, force: true)`，用 `hold()` 取代 `tryAcquire()`：確認是使用者刻意的第二次動作，不該被前一次請求殘留的 400ms 冷卻靜默丟棄。）

## 最容易寫錯的一行：deuce

後端 `match_wins()` 的註解明寫 **`deuce_threshold` 不參與運算**：

```python
return score_x >= cap_score or (score_x >= target_score and score_x - score_y >= 2)
```

所以 **20:20 加一分只有 21:20、領先 1 分，還沒贏，不該跳確認**；而 **29:29 加一分到上限 30，不看分差，要跳**。後端**刻意不把 `deuce_threshold` 送到前端**，就是為了不讓人拿它來判斷。`core/match-point.spec.ts` 把 data-model.md 的邊界對照表逐列釘住。

## 憲章對照（技術治理與品質關卡要求）

- **原則 V（不可逆操作二次確認）**：本功能即是此原則在既有缺口上的落實。決勝分會產生計入戰績的永久紀錄且無法從 UI 復原，正是此原則的適用對象。`variant` 用 `primary` 而非 `danger`——紅色保留給破壞性操作，與「提前結束」一致。
- **原則 X（伺服器為唯一可信來源）**：前端的決勝分判定**只決定要不要先問一句**，不參與任何實際判定。比賽是否結束、是否產生比賽結果，一律由伺服器收到該分後決定；前端判斷錯誤最多是多問或少問一次，不會造成狀態不一致（測試 `accepts the server verdict when the confirmed point did not end it`）。
- **原則 III（設定快照不回溯）**：判定讀 `matches.target_score` / `cap_score`（比賽建立當下的快照），不讀團的當下設定。兩支契約測試分別鎖住管理頁與公開端點：比賽開打後改團設定，進行中比賽的門檻不動。
- **原則 IV（權限邊界）**：不新增端點、不改權限模型。四個畫面各自沿用原本的驗證路徑（token 或管理員 PIN session）。
- **原則 VIII（i18n）**：新增 4 個 key。文案刻意與既有 `endMatchConfirmBody`（「⋯視為已捨棄，不計入戰績」）同句型、相反結論（「⋯將結束並計入戰績」）——兩者都是結束比賽的確認，差別正是計不計入戰績。
- **原則 II（測試優先）**：後端 4 條新契約測試，前端 35 條新測試。

## 變更範圍

24 個檔案。**無 migration、無新端點、無新錯誤碼。**

**後端**：`schemas.py`（兩個 schema 各 +2 欄位）、`service.py`（兩個建構點各 +2 行）、兩個契約測試檔。

**前端**：`core/match-point.ts` + spec（新增）、`ConfirmDialogComponent`（+`closed` output）、四個計分元件的 `.ts`／`.html`／`.spec.ts`、兩個 models、兩個語系檔。`all-courts-court-block.component.spec.ts` 是新建的——這個元件原本完全沒有測試檔。

## 測試

```
後端：完整套件通過（見下方執行結果）
      ruff check app/ tests/ ✅   mypy app/ ✅（66 files）
前端：ng test 833 passed（基準 798，+35），70 test files
      ng lint ✅   tsc --noEmit（app + spec）✅
```

> `ng test` 一律會報 1 個來自 `admin-page.component.spec.ts` 的 `NG04002` unhandled error 與數則 `angularx-qrcode` canvas 警告，皆為既有現象、與本次無關。

## 部署

**無 migration。** 後端先、前端後；順序互換也不會壞——新版前端搭舊版後端時讀不到 `target_score`／`cap_score`，`isMatchPoint()` 回傳 `false`，四個畫面退回現行的直接加分，功能尚未生效而已。回滾只要前端退版。

## 手動驗收（務必做）

`specs/039-match-point-confirm/quickstart.md` 有 11 個情境。其中**情境 7 與 8 必須在真的瀏覽器上做，單元測試驗不出來**（jsdom 沒有 `<dialog>`）：

- **情境 7**：跳出確認框後用**鍵盤 Esc** 關掉，再按一次「+」——必須能正常再次開啟。
- **情境 8**：承上，Esc 取消後按「-1」與「+」——都必須仍然有反應（驗證計分鍵沒有被鎖死）。

這兩條正是上面「刻意的設計決定 1 與 2」要擋的失敗，而且失敗時都是靜默的。

🤖 Generated with [Claude Code](https://claude.com/claude-code)
