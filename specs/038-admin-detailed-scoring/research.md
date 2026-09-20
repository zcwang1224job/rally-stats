# Phase 0 Research: 管理頁分數控制板支援比賽詳細設定

**Feature**: 038-admin-detailed-scoring | **Date**: 2026-09-20

本功能沒有待解的 NEEDS CLARIFICATION——spec 的 Clarifications 一節已把四個產品面問題定案。本文記錄的是**實作面**的調查結果：既有系統已經有什麼、真正缺的是什麼、以及為什麼選現在這個做法。

## 現況盤點：詳細計分在四個計分畫面的支援度

| 畫面 | 元件 | 判斷開關 | 開啟詳細視窗 | 取消這一分 | 凍結畫面 |
|---|---|---|---|---|---|
| 單一場地控制板（公開 token） | `control-panel.component` | ✅ | ✅ | ✅ | ✅ |
| 全部場地控制板（公開 token） | `all-courts/all-courts-court-block.component` | ✅ | ✅ | ✅ | ✅ |
| 計分板（公開 token） | `scoreboard.component` | ✅ | ✅ | ✅ | ✅ |
| **開團管理頁場地控制**（管理員 PIN） | **`group-admin/schedule-management/court-control.component`** | ❌ | ❌ | ❌ | ❌ |

`court-control.component.html` 的「+1」目前直接呼叫 `score(leftTeam(), 1)`，沒有任何 `match.detailed_scoring_enabled` 分支，也沒有 `<app-shot-placement-picker>`。這就是本功能要補的唯一缺口。

## Decision 1：直接移植 `AllCourtsCourtBlockComponent` 的做法，不另行設計

**Decision**：把 `all-courts-court-block.component.ts` 的詳細計分流程整段移植進 `court-control.component.ts`，只替換掉資料來源（`CourtControlService` token 端點 → `ScheduleService` 管理員端點）與狀態型別（`CourtLiveState` → `CourtScheduleStatus`）。

**Rationale**：兩個元件的架構本來就幾乎相同——都是「父元件持有全部場地、每個場地一個子元件、子元件沒有自己的輪詢、靠 `changed` output 請父元件重抓」。`all-courts-court-block` 的註解甚至明寫它的設計是「比照管理頁 court-control 元件」。移植等於把當初分岔的兩邊重新收斂，而不是新增第三套寫法。

**Alternatives considered**：
- *抽出共用 base class / mixin 給四個計分畫面共用*：四個元件的資料來源、狀態型別、父子關係各不相同（`control-panel` 與 `scoreboard` 自己持有 live state 並就地 patch；另外兩個靠父元件重抓），共用抽象會被三種形狀撐成一堆泛型參數，可讀性反而比現在四份相似但各自清楚的實作差。本功能不做這個重構。
- *讓管理頁改用 `CourtLiveState` 那組端點*：得放棄管理員 PIN session 驗證路徑改走 token，直接違反憲章原則 IV（管理員操作僅限需驗證的管理頁），否決。

## Decision 2：凍結以 `frozenCourt` signal + `displayCourt()` computed 實作

**Decision**：在 `CourtControlComponent` 加入 `private readonly frozenCourt = signal<CourtScheduleStatus | null>(null)` 與 `readonly displayCourt = computed(() => this.frozenCourt() ?? this.court())`，模板全面改讀 `displayCourt()`，不再直接讀 `court()`。

**Rationale**：這是本次唯一需要特別小心的地方。`court-control` 的既有註解已經點出它與其他計分畫面最大的不同：**它沒有自己的 live state**，每次比分變動都只能以「父元件重抓 → 全新的 `court` 輸入」的形式抵達。賽末點會讓後端推 `match.ended`，父元件重抓後 `current_match` 變成 `null`，模板最外層的 `@if (court().current_match; as match)` 立刻為假，整個區塊（含詳細視窗的 DOM）在計分者手指底下被拆掉——正是 FR-011 要擋的情況。`frozenCourt` 讓這個元件在視窗開啟期間忽略輸入更新，同時 `changed.emit()` 照常發出，其他場地的區塊完全不受影響。

**Alternatives considered**：
- *把詳細視窗掛在 `@if` 外面*：視窗需要 `match.participants` 才能列出球員，移到外面就得另外保存一份參賽者清單，等於換個地方做同一件凍結，而且賽末點之後 `leftTeam()`／站位顯示仍會錯亂。
- *父元件在任一場地開著視窗時暫停重抓*：會讓其他場地在這段期間停止更新，違反憲章原則 III 的即時性要求。

## Decision 3：後端只缺一個欄位

**Decision**：在 `apps/api/app/domains/schedule/schemas.py` 的 `MatchSummary` 加上 `detailed_scoring_enabled: bool = False`，並在 `service.build_schedule_snapshot()`（`service.py` 約 2064 行，全檔唯一的 `MatchSummary(...)` 建構點）以 `entry[0].detailed_scoring_enabled` 填入。

**Rationale**：調查後端後確認，管理員路徑的能力**早就齊全**了：

| 需要的能力 | 端點 | 狀態 |
|---|---|---|
| 加分並取得 `score_event_id` | `POST /groups/{group_id}/courts/{court_id}/matches/{match_id}/score` | ✅ 已存在（`ScoreMutationResult.score_event_id`） |
| 記錄落點詳細資料 | `POST …/matches/{match_id}/shot-placement` | ✅ 已存在（`record_shot_placement_by_admin`） |
| 撤銷賽末點 | `POST …/matches/{match_id}/undo-completion` | ✅ 已存在（`undo_match_completion_by_admin`） |
| 判斷這場是否啟用詳細設定 | `GET /groups/{group_id}/schedule` 的 `current_match` | ❌ **缺這個欄位** |

三個端點連契約測試都已經有了（`test_shot_placement_endpoint.py:136`、`test_undo_match_completion_endpoint.py:122` 都涵蓋管理員路徑）。所以後端工作量是「一個欄位 + 一行填值」，不是一組新端點。

**Alternatives considered**：
- *前端改打 `GET .../state`（`MatchLiveDetail` 已有這個欄位）*：那是 token 版端點，管理頁拿不到；且管理頁一次顯示多個場地，為了一個布林值對每個場地各發一次請求並不划算。
- *前端改讀團設定（`view.detailed_scoring_enabled`，管理頁本來就有）*：**明確否決**。憲章原則 III 要求設定變更不得回溯影響進行中的比賽，必須以快照落實；讀團的當下設定會讓管理員中途切換開關時，進行中的比賽行為跟著改變。必須讀比賽自己的快照。

## Decision 4：不新增端點、不新增錯誤碼、不新增語系 key

**Decision**：完全沿用既有端點與既有錯誤碼；前端只在 `ScheduleService` 補上呼叫方法。

**Rationale**：逐一比對過語系檔，詳細視窗與取消失敗提示所需的 key **全部已經存在**：

- `shotPlacement.*`：`title`、`confirm`、`skip`、`cancelScore`、`selectLanding`、`sideScoring`、`sideLosing`、`serveFault`、`ending.*` 等 19 個 key 都在（視窗元件是共用的，本來就用這些）。
- 取消失敗的錯誤碼→文案：`ROUND_ALREADY_ADVANCED`、`NEXT_MATCH_ALREADY_STARTED`、`MATCH_NOT_COMPLETED`、`SIDE_DID_NOT_WIN_THIS_MATCH`、`ADMIN_TOKEN_INVALID` 在 `zh-TW.json` 與 `en.json` 都有對應句子。

前端的 `ApiError` 已經把後端的 `error_code` 正規化成 `i18nKey`，`cancelScoreErrorKey.set(error.i18nKey)` 直接可用。符合憲章原則 VIII，且本功能新增 0 個語系 key。

## Decision 5：補上 `ScoreTapGuard`（目前 court-control 沒有）

**Decision**：在 `CourtControlComponent` 引入 `private readonly scoreGuard = new ScoreTapGuard()`，`score()`、`scoreThenOpenPicker()` 與取消流程的 `-1` 都經過它。

**Rationale**：FR-013 要求連按兩次只記一分。其他三個計分畫面都已經有這個 guard，唯獨管理頁的 `score()` 沒有——所以這其實是管理頁本來就存在、只是沒人回報的既有缺口。詳細模式讓它變得更嚴重（連按兩次會開兩個視窗、產生兩個 `PendingPoint`），因此一併補上。這是本功能唯一會改動「簡易模式」行為的地方，而且改的是防誤觸方向，不影響 FR-001/SC-004 所要求的「操作流程不變」。

**Alternatives considered**：*只在詳細模式加 guard*：留下兩條行為不同的路徑，之後維護時容易改錯；且簡易模式的重複計分本來就該擋。

## Decision 6：比分跳動動畫改綁 `displayCourt()`

**Decision**：既有的 `effect()`（偵測比分變化觸發 `.score--pulse`）從讀 `this.court().current_match` 改為讀 `this.displayCourt()?.current_match`。

**Rationale**：凍結期間 `court()` 會帶著新比分抵達但畫面不顯示它；若 effect 仍綁 `court()`，動畫會在看不見的更新上播一次，解凍後畫面才真正變化卻不再播第二次——動畫與視覺變化錯開。綁 `displayCourt()` 則保證「畫面上的數字變一次，就跳一次」。簡易模式下 `frozenCourt` 恆為 `null`、`displayCourt() === court()`，行為與現在完全相同。

## Decision 7：`changed.emit()` 照常立即發出，不因凍結而延後

**Decision**：加分成功後立刻 `this.changed.emit()`，與 `all-courts-court-block` 一致；被凍結的只有這個元件自己對新輸入的採用。

**Rationale**：父元件（管理頁排程區）重抓的是**整份賽程**——名單、等待場數、其他場地全都靠它更新。為了一個場地的視窗而延後，會讓整頁停更，違反憲章原則 III。凍結必須是「單一子元件忽略輸入」，不是「全頁暫停」。

## Decision 8：測試策略

**Decision**：
- 後端：在既有的 schedule 契約測試中補一條，驗證 `GET /groups/{group_id}/schedule` 的 `current_match.detailed_scoring_enabled` 會反映比賽的快照值（開啟與關閉各一）。
- 前端：新增 `court-control.component.spec.ts` 的詳細模式測試，以 `scoreboard.component.spec.ts` 既有的詳細模式測試（`detailedMatchState`）為範本，涵蓋 FR-001/003/006/007/008/011/013。

**Rationale**：憲章原則 II 要求比分計算相關變更附帶測試。後端這次只多一個唯讀欄位，風險集中在前端的凍結與 pending-point 狀態機，測試重心因此放在元件層。`court-control.component.spec.ts` 目前只有 121 行、只測站位顯示，補測試的空間很乾淨。

## 風險與注意事項

1. **換讀 `displayCourt()` 的範圍比想像中小**（2026-09-20 實際清點）：`court-control.component.html` 只有**一處**讀 `court()`——第 6 行的 `@if (court().current_match; as match)`；其後整份模板都用 `match` 別名，站位與比分自然跟著凍結，不需要逐行改。`court-control.component.ts` 則有 6 處，其中只有 3 處與顯示有關、需要改讀 `displayCourt()`：

   | 位置 | 用途 | 處置 |
   |---|---|---|
   | `.html` L6 | 外層 `@if` | ✅ 改 `displayCourt()?.current_match` |
   | `.ts` L81 | 比分跳動 effect | ✅ 改（見 Decision 6） |
   | `.ts` L194 | `score()` 取 `match_id` | ✅ 改（凍結期間應對凍結的那一場） |
   | `.ts` L212 | `confirmEndMatch()` 取 `match_id` | ✅ 改（同上） |
   | `.ts` L103 | realtime 頻道的 `court_id` | ❌ 不改——`court_id` 生命週期內恆定，改了只會在凍結期間多餘地重新求值 |
   | `.ts` L123/L129 | `getScoreSwapPreference`／`setScoreSwapPreference` 的 `court_id` | ❌ 不改——同上 |

   檢查點不是「檔案中不再出現裸 `court()`」（`court_id` 的讀取本來就該留著），而是「**所有讀 `current_match` 的地方都走 `displayCourt()`**」。
2. **`ngOnInit` 讀 `court().court_id`**：`court_id` 在元件生命週期內恆定，凍結不影響它，維持讀 `court()` 即可，不需改。
3. **realtime 訂閱的 effect 也讀 `this.court().court_id`**：同上，維持不變；改成 `displayCourt()` 反而會在凍結期間產生不必要的重新求值。
4. **`endMatch`／`confirmEndMatch` 讀的是 `court().current_match`**：視窗開啟期間「提前結束」按鈕理論上碰不到（計分者正在 modal 裡），但為求一致仍應改讀 `displayCourt()`，避免凍結期間兩個來源打架。
