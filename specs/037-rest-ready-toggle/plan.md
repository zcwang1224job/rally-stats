# Implementation Plan: 休息／準備切換

**Branch**: `feature/rest-toggle` | **Date**: 2026-09-19 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/037-rest-ready-toggle/spec.md`，交叉比對 `/apps/api/app/domains/schedule/service.py`（`apply_wait_count_updates()`、`_get_active_roster_for_selection()`、`_get_active_roster_ids()`、`_get_active_roster_ordered()`、`_get_player_histories()`、`_choose_next_queued_match()`、`pull_queued_match_for_court()`、`peek_next_queued_match()`、`_seat_waiting_players_on_court()`、`round_is_complete()`、`check_round_complete_and_maybe_auto_advance()`、`_schedule_late_joiner_matches()`、`refresh_courts_after_roster_change()`、`remove_roster_entry_from_schedule()`、`_pick_substitute()`、`build_schedule_snapshot()`、`build_round_matches_list()`）、`/apps/api/app/domains/schedule/algorithms.py`（`PlayerHistory`、`player_histories()`、`stage1_select_players()`、`pick_next_match()`）、`/apps/api/app/domains/roster/models.py`（`RosterEntry`）、`/apps/api/app/domains/group/service.py`（`leave_group()` 的擁有權檢查）、`/apps/api/app/core/realtime.py`、`/apps/web/src/app/features/group-member-view/member-schedule/`、`/apps/web/src/app/features/group-admin/admin-page/`、`/apps/web/src/app/features/group-admin/schedule-management/`

## Summary

在「在團裡」與「離開」之間加入第三種狀態「休息中」：人還在團裡、所有紀錄不受影響，只是暫時不被排上場；回來時不因休息而得到任何優先權。

1. **狀態與切換（US1、US4）**：`roster_entries.resting_since`（`NULL`＝準備中）。兩支 `PUT …/rest-state` 端點（本人／管理員）共用一個服務函式；請求是目標狀態而非「切換」，因此冪等。成功後走一段固定的收斂流程（填滿閒置場地 → 檢查自動換輪 → 發布 `roster.restChanged`）。
2. **候選人名單（US1、US3）**：休息對排程的全部影響就是「候選人名單少了他」。條件收斂在讀取名單的函式與 `wait_count` 累加的一處，各排程方式的配對邏輯一行不改。**正式搭檔關係的建立不受休息影響**（FR-034）——`_get_active_roster_ordered()` 的 7 個呼叫端中有 2 個是在建立正式 `Partnership`，因此拆成 ready／active 兩個版本（research Decision 2 的對照表）。
3. **已排定的場次（US2）**：按下休息的當下什麼都不改。叫場時先叫沒有休息者的場次；只剩含休息者的場次時，公平輪替雙打／個人全混搭在**叫場那一刻**找一位「現在就能上場」的替補，單打循環／固定搭檔保留。「下一場預告」與實際叫場共用同一個判斷，預告呈現替補後的陣容。
4. **公平性（US3）**——讀程式後發現兩件規格沒提到的事，皆已納入設計：
   - 「坐著等了幾場」是從比賽時間推導的，不是儲存的計數——要扣掉休息期間，必須保存休息區間（新表 `roster_rest_periods`，research Decision 3）。
   - 挑人的第二順位是「打得少的人優先」——休息很久的人回來後會一路優先到追平為止，等於變相補償。以 `played_credit` 把他拉到其他人的下中位數（research Decision 4）。
5. **被休息卡住的輪次（FR-020）**：`round_is_complete()` 要求所有場次都結束，被保留的場次會讓這一輪永遠不結束、自動換輪永遠不觸發。新增「被休息卡住」的判斷並接進既有的自動換輪，另加兩個守門條件避免輪次編號空轉（research Decision 6）。FR-020 已於 2026-09-19 由使用者確認維持。
6. **按下去就會結束這一輪——先提醒（FR-031～FR-033）**：使用者於 `/speckit-analyze` 後決定——維持 FR-020，但球員按休息若會使這一輪**立刻**結束，要先提醒「本輪還沒打的比賽會被取消、直接進入下一輪」。做法是兩段式請求：後端在交易內試算，會立刻換輪而請求未帶確認 → rollback 並回 409 `REST_ENDS_ROUND`（含將取消的場次數）；前端收到才跳既有的 `app-confirm-dialog`，確認後帶 `confirm_round_end: true` 重送。判斷式與真正換輪用的是同一個函式（research Decision 6）。

## Technical Context

**Language/Version**：延續既有（後端 Python 3.12+，FastAPI + SQLAlchemy 2.0 async；前端 Angular 20 + TypeScript strict mode）。

**Primary Dependencies**：沿用既有堆疊，**不新增任何第三方套件**。即時同步沿用 Ably（後端 `core/realtime.py` 的 `publish()`）。

**Storage**：PostgreSQL。**一支 migration**（接在 `b5c8e2f41a07` 之後）：`roster_entries` 加 `resting_since TIMESTAMPTZ NULL`、`played_credit INTEGER NOT NULL DEFAULT 0`；新表 `roster_rest_periods`。純新增、既有資料零變動、可 downgrade。詳見 [data-model.md](./data-model.md)。

**Testing**：
- 後端：pytest。
  - `tests/unit/domains/schedule/test_rest_histories.py`（新，無資料庫）——`player_histories()` 的休息區間：區間內上場的比賽不計入 `rest`、區間前後照計、多段區間、進行中的區間（`end=None`）、在場上時開始的區間、不影響 `played` 與 `run`、不傳區間時結果與現在逐位相同。`returning_played_credit()`：下中位數、沒有其他人、已不低於目標、0 場的新人不把目標拉到 0、只回傳非負整數。
  - `tests/unit/domains/schedule/test_rest_state.py`（新，經資料庫）——設定／冪等（`changed: false`、不寫區間、不發事件）；切回時寫入一列區間且起訖正確；`played_credit` 調整；離開／被踢後不可切換；重新加入為準備中；換輪不改變狀態。
  - `tests/unit/domains/schedule/test_rest_round_generation.py`（新）——四種自動排程方式產生新一輪皆排除休息者；固定搭檔（手動搭檔）整隊排除且搭檔不進自動補位、（自動搭檔）只從準備中的人組隊；`apply_wait_count_updates()` 與連續輪轉的 `passed_over` 不對休息者 +1；準備中的人不足時不產生人數不足的場次；`sitting_out` 不含休息者；回來走中途加入者流程（單打循環、固定搭檔、個人全混搭各一），其中固定搭檔「搭檔仍在休息」時 MUST NOT 被臨時配給別人，且 `wait_count` 不變成 `NULL`。
  - `tests/unit/domains/schedule/test_rest_call_up.py`（新）——有無休息者的場次並存時先叫沒有的；只剩含休息者的場次時替補模式找替補、保留模式回 `None`；替補三條件（準備中、不在該場、當下不在場上）；一場有兩位休息者；找不到替補時場次原封不動；`peek` 與 `pull` 對同一狀態結果相同且 `peek` 不寫入；替補者 `wait_count` 歸零、休息者不變；`PairHistory` 記在替補者；**兩面場地同時空出不會為兩場挑到同一位替補**（併發測試，比照既有 `test_pull_queued_match_conflict.py`）；回來後閒置場地立即叫場。
  - `tests/unit/domains/schedule/test_rest_round_stall.py`（新）——`round_is_stalled_by_rest()` 的四個條件各缺一時為假；開啟自動換輪時比賽結束與狀態變更兩個觸發點皆會換輪；守門條件：下一輪排不出任何一場時不換輪、反覆切換不使輪次編號增加；未開啟時不換輪。**`REST_ENDS_ROUND`**：會立刻換輪而未帶確認 → 409、`matches_to_cancel` 正確、球員狀態／場次／區間表／事件計數全部不變；帶確認 → 生效並換輪；帶確認但當下已不需要 → 一般休息、不換輪；還有比賽在打、未開啟自動換輪、下一輪排不出來三種情況皆不回 409；切回準備中永遠不回 409；提醒的判斷式與 `check_round_complete_and_maybe_auto_advance()` 用的是同一個 `round_would_auto_advance()`。
  - `tests/unit/domains/schedule/test_rest_fairness.py`（新）——`wait_count` 凍結（整輪挑人、連續輪轉）、`_get_player_histories()` 的 `rest` 扣除休息期間、`played_credit` 的調整與累加、回來不變成 `NULL`、排行榜不受 credit 影響。
  - `tests/unit/domains/schedule/test_rest_return.py`（新）——回來時走中途加入者流程（三種排程方式）、固定搭檔「搭檔仍在休息」不被臨時配給別人、回來後閒置場地立即叫場、連續輪轉湊滿四人立即排出、`awaiting_start` 時不替管理員開始這一輪。
  - `tests/integration/test_schedule_fairness_simulation.py`（擴充——既有的情境驅動模擬在這裡，不是 `tests/unit/…/test_fairness_simulation.py`）——固定亂數種子、多人多輪、隨機休息與回來：休息前後 `wait_count` 差值恆為 0；回來後第一次挑人的順位不優於同一時刻 `wait_count` 相同且一直準備中的人；回來後的上場比例不高於全體中位數加容許值（防 Decision 4 回歸）。
  - 既有排程測試（`test_fair_rotation_stage1.py`、`test_wait_count_update.py`、`test_advance_court.py`、`test_peek_next_queued_match.py`、`test_round_completion.py`、`test_member_joined.py`、`test_member_removal.py` 等）**零變動且全數通過**——沒有人休息時，所有新條件恆真。
  - `tests/contract/test_rest_state_endpoints.py`（新）——授權矩陣（本人會員、本人訪客、他人會員、他人訪客 token、未帶身分、管理員、別團的管理員；已離開／被踢的列；別的團的列；不存在的列）——所有拒絕情況的回應 MUST 逐位相同；回應形狀；`currently_playing`。`tests/contract/` 既有的賽程與本輪賽程清單契約測試擴充新欄位與兩個新的 `waiting_reason`。
  - `tests/integration/test_rest_toggle_flow.py`（新）——開團 → 加入 → 排點 → 休息 → 替補上場 → 回來 → 計分完賽 → 排行榜與對戰紀錄與「沒有休息功能」的對照組一致（Constitution II 的端到端要求、SC-008）。
- 前端：Vitest。`rest-toggle-button.component.spec.ts`（新）——兩種狀態的文字與 `aria-pressed`、送出中停用、`currently_playing` 時的說明、失敗時還原並顯示錯誤。`member-schedule.component.spec.ts`（擴充）——名單的休息標示、只有自己的列有切換按鈕、搭檔休息的說明、兩個新等待原因、預告的替補註記、訂閱 `roster.restChanged` 後重抓、不認得的 `waiting_reason` 退回既有文字。`admin-page.component.spec.ts`（擴充）——每一列的切換按鈕（含建立者）、`waiting_on_rest` 提示與 `stalled` 樣式、訂閱新事件。`round-matches-list.component.spec.ts`（擴充）——`rest_effect` 標示；替換候選標示休息中但仍可選。`manual-assign.component.spec.ts`（新——該元件目前沒有測試檔）——候選清單標示休息中但仍可選。`rest-toggle-button.component.spec.ts` 另含一條測試，比照 `player-insights.component.spec.ts` 的做法讀入兩份語系檔，斷言本功能的每個新 key 在 `zh-TW.json` 與 `en.json` 都存在。

**Target Platform**：延續既有（Docker on AWS ECS；行動裝置優先）。

**Project Type**：Web application（monorepo，`apps/api` 與 `apps/web`）。

**Performance Goals**：切換到所有人畫面更新 < 2 秒（SC-001）。叫場的一般路徑（沒有休息者）**不增加查詢、不增加鎖**；只有走到替補路徑時才取團列鎖。`_get_player_histories()` 多一個以 `group_id` 過濾的小查詢（每次休息一列）。

**Constraints**：按下休息的當下 MUST NOT 修改任何場次（FR-013）；進行中的比賽 MUST 完全不受影響（FR-014）；預告與實際叫場 MUST 一致（FR-015）；休息 MUST NOT 帶來任何排程優先權（FR-023～FR-026）；排行榜、對戰紀錄、個人統計零變動（FR-028）；沒有人休息時，所有排程行為 MUST 與現在逐位相同；狀態變更事件只由後端發出（FR-007）；新文字全數進語系檔。

**Scale/Scope**：後端 1 支 migration＋1 個新 model＋`RosterEntry` 兩欄＋`algorithms.py` 1 個函式擴充與 1 個新純函式＋新模組 `schedule/rest.py`＋`service.py` 約 10 處修改（3 個名單讀取函式、2 處 `wait_count`、叫場、替補、自動換輪、固定搭檔組隊、2 個回應建構函式）＋2 支新端點＋5 個 schema 擴充與 4 個新 schema；前端 1 個新元件＋成員頁與管理頁各 1 個擴充＋2 個清單／選單元件擴充＋2 個 service 方法＋1 個 models 檔＋兩份語系檔。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | `WaitingReason`、`rest_effect` 為 `Literal`；前端為字串聯集，`waiting_reason` → 語系 key 的對應是 exhaustive `Record` 並有不認得的值的退回分支。`_choose_next_queued_match()` 的回傳型別由 `Match \| None` 改為具名的 `NextMatchChoice \| None`（場次＋替補對照），所有呼叫端由 `mypy --strict` 強制更新。 | PASS |
| II. 測試優先 | **直接觸及輪替（排點）演算法**——這是本原則點名的核心邏輯。純函式（`player_histories()` 的新參數、`returning_played_credit()`）的測試 MUST 先於實作撰寫；叫場、替補、自動換輪、`wait_count` 凍結各有正常路徑與邊界；既有排程測試零變動且全數通過是回歸的底線；`test_rest_toggle_flow.py` 是「開團 → 加入 → 排點 → 計分」含休息的端到端測試；公平性以固定種子的模擬驗證。 | PASS（列入 tasks.md 強制項） |
| III. 即時性與資料一致性 | 狀態變更 2 秒內同步；前端一律重抓、不套用 payload，斷線重連沿用既有的強制重抓。**設定快照原則不涉及**——休息是球員的即時狀態，不是團設定；它只影響「之後」的挑人與叫場，已在進行中的比賽完全不動（FR-014）。**比賽紀錄完整性**：被保留的場次於換輪時走既有的 `abandon_group_matches()`，成為 `abandoned`、不產生結果；被替補的場次由替補者完賽並計入替補者——沒有為休息發明任何新的中止規則。 | PASS |
| IV. 權限與安全 | 本人端點的擁有權檢查與 `leave_group()` 逐行相同（訪客 token 或會員身分），所有拒絕情況回傳同一個錯誤、不洩漏該列是否存在；契約測試比對回應全文。管理員端點 `require_admin`，**只出現在管理頁**；計分板、控制面板、全場地面板等免驗證畫面不提供任何切換。暱稱顯示沿用 `app-nickname`／Angular 插值逸出。不新增 token 類型。 | PASS |
| V. 破壞性操作二次確認 | 一般的切換**不**加確認框——它隨時可還原，且是設計上要「隨手按」的操作。**唯一不可還原的情況**（開著自動換輪、沒有比賽在打、按休息會使這一輪立刻結束並取消尚未上場的場次）MUST 先提醒並取得確認（FR-031～FR-033）——與同樣會取消場次的「離開團」一致，沿用同一個 `app-confirm-dialog`。要不要提醒由後端以真正換輪的同一個判斷式決定，取消提醒時系統狀態完全不變。*（原先此項自行判為「可接受、不需確認」，經 `/speckit-analyze` D1 指出與離團的前例不一致，使用者決定加上提醒。）* 管理員手動結束一輪的既有確認框不變。 | PASS |
| VI. 可維護性 | 公平性規則是 `algorithms.py` 的純函式（無 ORM）；切換與收斂流程在新模組 `schedule/rest.py`，它 import `service`、`service` 不 import 它。候選人條件收斂為一個模組層級常數、用在三個讀取函式——不散落在各排程方式的產生器裡。`roster` domain 只增加欄位與 model，不含排程邏輯。前端的切換按鈕是一個獨立元件，成員頁與管理頁共用。 | PASS |
| VII. 無障礙與行動裝置優先 | 休息標示＝圖示＋文字，不只靠顏色（FR-008）；切換是原生 `<button>` 並帶 `aria-pressed`；等待原因、`rest_effect`、替補註記皆為文字。375px 寬不產生水平溢出（quickstart 情境 12）。計分板不新增任何內容。 | PASS |
| VIII. i18n 與時區 | 後端只回傳狀態、代碼與時間；所有新文字在 `zh-TW.json`／`en.json` 各一份。新增一個錯誤代碼 `REST_ENDS_ROUND`（提醒框的標題、內文、按鈕文字與 `errors.REST_ENDS_ROUND` 的後備訊息皆進兩份語系檔；場次數以語系參數帶入），其餘沿用 `ROSTER_ENTRY_NOT_FOUND`、`GROUP_DISBANDED`。`resting_since` 與休息區間以 UTC 儲存、只用於比較先後，首版不顯示給使用者，不涉及顯示時區。 | PASS |
| IX. 可攜性與可部署性 | 一支純新增的 migration，可 downgrade；無新套件、無新環境變數。新回應欄位皆有預設值。部署順序：migration → 後端 → 前端（前端先上會讓切換按鈕得到 404，已寫入 quickstart）。 | PASS |
| X. 伺服器為可信來源 | `roster.restChanged` 只由後端在交易提交後發布；前端不自行廣播、不樂觀更新他人畫面。「這場算保留還是替補」「這一輪是否被卡住」「替補是誰」全部由後端判斷並放進回應，前端不推論。 | PASS |
| XI. 防濫用 | 不新增「建立新資源」的端點；切換只改一列、需證明擁有該列或為管理員。不設頻率限制（spec Assumptions）——反覆切換不帶來任何排程優勢（US3 情境 6 有測試），每次最多寫入一列區間。 | PASS |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

**Post-design re-check（Phase 1 完成後）**：data-model.md 與 contracts/ 確認——儲存變更為兩欄一表、皆純新增；兩支新端點各自重用既有的授權方式，沒有新的授權分支；既有端點只新增具預設值的欄位，排行榜與紀錄類回應零變動。設計期間有三項回頭對照規格：(1) 規格 Key Entities 寫「本功能不要求保存休息的歷史紀錄」——設計新增了 `roster_rest_periods`，兩者不衝突：那張表是 FR-025 的計算依據、不對外呈現，理由記於 research Decision 3；(2) 規格 FR-009「固定搭檔任一人休息則整隊排除」——查證後發現手動搭檔模式下若不處理，另一人會被 017 的自動補位臨時配給別人，已在 research Decision 2 明訂他不進自動補位候選；自動搭檔模式每輪重新組隊，沒有「隊」可排除，行為是「只從準備中的人組隊」，與 FR-009 的意圖一致；(3) 規格未提及「打得少者優先」造成的變相補償——屬 FR-023／US3 的涵蓋範圍，以 Decision 4 處理，不需修改規格。Gate 結果維持 PASS。

**`/speckit-analyze` 後修正（2026-09-19）**：0 項 CRITICAL、2 項 HIGH、5 項 MEDIUM、5 項 LOW，全數處理。(D1) 按休息會使這一輪立刻結束而沒有確認——使用者決定維持 FR-020 並加上事前提醒，新增 FR-031～FR-033、SC-009、錯誤代碼 `REST_ENDS_ROUND`、兩段式請求；Constitution V 的說明改寫。(F1) `_IS_READY` 套得太廣——`_get_active_roster_ordered()` 的 7 個呼叫端逐一查證，其中 2 個是在建立正式 `Partnership`，拆成 ready／active 兩個函式，新增 FR-034。(F2) FR-020／SC-006 補上「下一輪排不出來就不換輪」的例外。(E1) 管理頁的休息標示與事件訂閱移進 US1。(E2) 上線單位改為三個 P1 一起。(F3) plan／quickstart／research 的測試清單與 tasks 同步。(C1、C2) 兩位休息者同場、單打循環的已知限制寫進 spec Edge Cases。(F4) spec 改為「不對外呈現」休息歷史。(F5) spec 加用語註。(F6) FR-021 放寬為與設計一致。(B1、E3) 見 tasks.md。

## Project Structure

### Documentation (this feature)

```text
specs/037-rest-ready-toggle/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── rest-state-api.md            # 新：兩支 PUT …/rest-state
│   ├── schedule-api-additions.md    # 既有賽程／本輪賽程清單回應的新增欄位
│   └── ably-events-additions.md     # 新事件 roster.restChanged
├── checklists/
│   └── requirements.md  # /speckit-specify output
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
apps/api/
├── alembic/versions/<new>_rest_state.py   # 新增：down_revision = b5c8e2f41a07
├── app/domains/roster/
│   └── models.py            # 擴充：RosterEntry.resting_since、played_credit；新增 RosterRestPeriod
├── app/domains/schedule/
│   ├── algorithms.py        # 擴充：player_histories(matches, rest_periods=…)；
│   │                        # 新增：returning_played_credit()
│   ├── rest.py              # 新增：set_rest_state()——授權後的狀態寫入、區間、credit、
│   │                        #       收斂流程、發布 roster.restChanged
│   ├── service.py           # 修改：_IS_READY 條件用於 _get_active_roster_for_selection()、
│   │                        #       _get_active_roster_ids()、apply_wait_count_updates()；
│   │                        #       新增 _get_ready_roster_ordered()（5 個呼叫端改用；
│   │                        #       _get_active_roster_ordered() 不變——正式搭檔關係用）；
│   │                        #       round_would_auto_advance()（換輪與 REST_ENDS_ROUND 共用）；
│   │                        #       _get_player_histories()（載入區間、played 含 credit）；
│   │                        #       _choose_next_queued_match() → NextMatchChoice（含替補）；
│   │                        #       pull_queued_match_for_court()（套用替補、替補路徑取團列鎖）；
│   │                        #       _pick_substitute(must_be_free=…)；
│   │                        #       _resolve_manual_fixed_partner_teams()（整隊排除）；
│   │                        #       round_is_stalled_by_rest()、_can_generate_any_match()、
│   │                        #       check_round_complete_and_maybe_auto_advance()；
│   │                        #       build_schedule_snapshot()、build_round_matches_list()
│   ├── schemas.py           # 擴充：WaitingReason、RosterScheduleStatus、NextUpPreview、
│   │                        #       RoundMatchSummary、RoundMatchesResponse；
│   │                        # 新增：RestStateRequest／Response、SubstitutionPreview、WaitingOnRest
│   └── router.py            # 新增：PUT /groups/{id}/members/{entry}/rest-state（require_admin）
├── app/domains/group/
│   ├── service.py           # 新增：set_own_rest_state()——與 leave_group() 相同的擁有權檢查，
│   │                        #       之後委派 schedule.rest.set_rest_state()
│   └── router.py            # 新增：PUT /groups/{id}/roster/{entry}/rest-state
└── tests/                   # 見 Technical Context

apps/web/src/
├── app/core/rest-toggle-button/           # 新增：app-rest-toggle-button（成員頁與管理頁共用）
├── app/features/group-admin/schedule-management/
│   ├── schedule.models.ts                 # 擴充：見 contracts/schedule-api-additions.md
│   ├── schedule.service.ts                # 擴充：setMemberRestState()
│   ├── round-matches-list.component.*     # 擴充：rest_effect 標示；替換候選標示休息中
│   └── manual-assign.component.*          # 擴充：候選標示休息中（仍可選）
├── app/features/group-admin/admin-page/
│   └── admin-page.component.*             # 擴充：名單列的切換按鈕與標示、waiting_on_rest 提示、
│                                          #       訂閱 roster.restChanged
├── app/features/group-member-view/
│   ├── group-member-view.service.ts       # 擴充：setOwnRestState()（重用 resolveRosterEntryId()）
│   └── member-schedule/
│       └── member-schedule.component.*    # 擴充：自己的切換按鈕、名單標示、搭檔休息說明、
│                                          #       兩個新等待原因、預告的替補註記、訂閱新事件
└── assets/i18n/{zh-TW,en}.json            # 擴充
```

**Structure Decision**：沿用既有 monorepo 配置，沒有新的模組邊界。休息狀態的**資料**屬 `roster` domain（它是名單列的屬性），休息對排程的**影響**屬 `schedule` domain——與 `wait_count` 的既有分工相同（欄位在 `roster`、所有讀寫邏輯在 `schedule`）。兩支端點依既有慣例分屬兩個 router：本人操作與 `leave` 同在 `group/router.py`，管理員操作與踢人同在 `schedule/router.py`；兩者最後都進入 `schedule/rest.py` 的同一個函式，規則只有一份。切換按鈕在成員頁與管理頁都出現，因此放 `core/`。

**建議實作順序**（供 `/speckit-tasks` 參考）：
1. **前置**：migration、model、兩個純函式與其測試（先紅後綠）。此時沒有任何行為改變。
2. **US1（後端）**：`_IS_READY` 條件＋`wait_count` 凍結＋`set_rest_state()` 的寫入部分＋兩支端點＋`roster.restChanged`＋`RosterScheduleStatus.resting`。到這裡，「休息者不進新場次」已可獨立交付與示範。
3. **US3**：`_get_player_histories()` 接上休息區間與 `played_credit`、切回時的 credit 調整、模擬測試。與 US2 互不相依，可平行。
4. **US2**：`_choose_next_queued_match()` 改為回傳 `NextMatchChoice`（先只做「略過含休息者的場次」，保留模式即完成）→ 替補路徑與團列鎖 → 預告的 `substitutions` → 收斂流程（回來立即叫場、中途加入者流程）→ `round_is_stalled_by_rest()` 與自動換輪 → `rest_effect`、`waiting_on_rest`、兩個新等待原因。
5. **前端**：`app-rest-toggle-button` → 成員頁 → 管理頁（US4）→ 清單與選單的標示 → 語系檔。
6. **整合測試與 quickstart 全情境**。

**上線單位＝US1＋US2＋US3 一起**（`/speckit-analyze` E2）。三者各自可以獨立開發與示範，但不能分開上線：少了 US3，休息就是插隊的捷徑；少了 US2，畫面上標示「休息中」的人仍會被叫上場打這一輪已排好的場次（違反 SC-002，而且對使用者是矛盾的訊息）。曾考慮只把 US2 裡「叫場時跳過含休息者的場次」這一小塊提前——但單獨提前它會讓這些場次永遠留在排隊中、這一輪永遠不結束，必須連同「被休息卡住」的判斷與自動換輪一起上，那就是 US2 的大半了，不如整個一起。US4 可同時或稍後上線。

## Complexity Tracking

無違反項目，本節不適用。
