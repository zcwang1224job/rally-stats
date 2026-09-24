# 038: 開團管理頁分數控制板支援比賽詳細設定

## 問題

團開啟「比賽詳細設定」後，只有三個**公開連結**畫面（控制頁面、全場地控制板、記分板）在按「+」時會跳出詳細記錄視窗。最常實際在計分的人——開團的管理員——用的是**開團管理頁面**的場地控制板，那裡的「+1」始終是純粹加一分。

後果有三個：同一場比賽的統計會有洞（管理員記的分沒有落點與球員資料）；設定開關與失效的地方是同一頁，特別像壞掉；想記詳細資料就得另外開一個公開控制連結，等於放棄管理頁的排程與名單視野。

## 做法

調查後發現管理員路徑的後端**早就完整**：`score_by_admin` 會回傳 `score_event_id`，`record_shot_placement_by_admin` 與 `undo_match_completion_by_admin` 都已實作且有契約測試。唯一缺口是排程快照沒把「這場比賽是否啟用詳細設定」送到前端。

因此本次是一次**移植**，不是新設計：`AllCourtsCourtBlockComponent` 與管理頁的 `CourtControlComponent` 架構幾乎相同（同為 per-court 子元件、無自身 live state、靠 `changed` output 請父元件重抓），把它的詳細計分流程整段搬過來，只替換資料來源與狀態型別。

### 唯一需要設計的部分：凍結

管理頁的場地控制元件直接讀 `court` input。賽末點會讓後端推 `match.ended`、父元件重抓、`current_match` 變成 `null`，模板的 `@if` 就會在計分者填資料時把整塊區塊連同視窗的 DOM 拆掉。

`frozenCourt` signal + `displayCourt()` computed 讓**這一塊**在視窗開啟期間忽略輸入更新；`changed.emit()` 照常立即發出，所以名單與其他場地完全不受影響。凍結期間顯示的是**加分回應本身帶回的伺服器值**，不是前端推算的比分。

## 憲章對照（技術治理與品質關卡要求）

- **原則 III（設定快照不回溯）**：是否進入詳細模式一律讀 `matches.detailed_scoring_enabled`（比賽建立當下的快照），**不是**管理頁已持有的團設定 `view.detailed_scoring_enabled`。新增的契約測試 `test_schedule_snapshot_flag_does_not_follow_a_mid_match_group_toggle` 專門鎖住這件事：比賽開打後把團開關關掉，進行中的那場仍維持詳細模式。
- **原則 III（即時性）**：凍結的範圍是單一子元件對輸入的採用，不是全頁暫停；其他場地與名單在視窗開啟期間照常即時更新。
- **原則 X（伺服器為唯一可信來源）**：所有比分與詳細資料變更都先經後端 API 寫入才反映到畫面；前端不發布任何事件，凍結期間顯示的也是後端回應的值。
- **原則 IV（管理員操作邊界）**：**方向確認**——憲章禁止的是「把管理員專屬操作放到免驗證畫面」。本次是把**已存在於公開畫面的非專屬能力**（詳細計分）補進管理頁，方向相反。全程走既有的管理員 PIN session（`authHeader(groupId)` + 後端 `require_admin`），**未新增任何端點，權限模型零變動**。
- **原則 VIII（i18n）**：**新增 0 個語系 key**。視窗與錯誤提示所需的文案全部既有（`shotPlacement.*` 19 個 key、`ROUND_ALREADY_ADVANCED` 等 5 個錯誤碼在 `zh-TW.json`／`en.json` 皆已存在）。
- **原則 II（測試優先）**：後端 2 條新契約測試、前端 15 條新元件測試。

## 變更範圍

8 個檔案。**無 migration、無新端點、無新錯誤碼、無新語系 key。**

**後端（2 行實質改動）**
- `schedule/schemas.py`：`MatchSummary` 新增 `detailed_scoring_enabled: bool = False`
- `schedule/service.py`：`build_schedule_snapshot()` 填入比賽快照值
- `tests/contract/test_detailed_scoring_toggle.py`：+2 條測試（快照值正確、不隨團設定回溯）

**前端**
- `schedule.models.ts`：`MatchSummary` 新增該欄位；`ScoreMutationResult` 補上後端早已回傳、前端漏宣告的 `score_event_id`
- `schedule.service.ts`：新增 `recordShotPlacement()`、`undoMatchCompletion()`
- `court-control.component.ts`：凍結、`PendingPoint` 流程、確認／略過／取消、`ScoreTapGuard`
- `court-control.component.html`：「+1」依模式分流、掛上共用的詳細記錄視窗、取消失敗提示
- `court-control.component.spec.ts`：+15 條測試

## 順帶修掉的既有缺口

管理頁的場地控制板**本來就沒有 `ScoreTapGuard`**——其他三個計分畫面自 032 起都有。也就是說在此之前，管理頁連按兩次「+1」會真的記兩分。詳細模式會讓它更嚴重（開兩個視窗、兩個 `PendingPoint`），所以一併補上。這是本次唯一觸及簡易模式的改動，方向是防誤觸，不影響既有操作流程。

## 測試

```
後端：tests/contract/test_detailed_scoring_toggle.py  6 passed（4 既有 + 2 新增）
      ruff check app/ tests/  ✅   mypy app/  ✅（66 files）
前端：ng test  798 passed（基準 783 + 15 新增），68 test files
      ng lint ✅   tsc --noEmit（app + spec）✅
```

> `ng test` 一律會報 1 個來自 `admin-page.component.spec.ts` 的 `NG04002` unhandled error，是既有現象、與本次無關（改動前的基準執行同樣會報）。

## 部署

**無 migration。** 後端先、前端後；但新欄位是純新增且有預設值，順序互換也不會壞——新版前端搭舊版後端時讀到 `undefined`，管理頁退回現行的一鍵加分，功能尚未生效而已。回滾只要前端退版。

## 手動驗收

`specs/038-admin-detailed-scoring/quickstart.md` 列了 9 個情境與 FR／SC 對照表。其中情境 5 最值得看：**A 場的詳細視窗開著時，B 場仍要照常即時更新**——凍結只影響單一場地，不是整頁停更。

🤖 Generated with [Claude Code](https://claude.com/claude-code)
