# Implementation Plan: 管理頁分數控制板支援比賽詳細設定

**Branch**: `feature/admin-detailed-scoring` | **Date**: 2026-09-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/038-admin-detailed-scoring/spec.md`

## Summary

開團管理頁面的場地控制板目前的「+1」是純粹加一分，即使團已開啟「比賽詳細設定」也不會跳出詳細記錄視窗——只有三個公開連結畫面（控制頁面、全場地控制板、記分板）支援。本功能把管理頁補齊到相同行為。

調查後確認這**幾乎是純前端工作**：管理員路徑的三個後端端點（加分回傳 `score_event_id`、記錄落點、撤銷賽末點）早就實作完成而且都有契約測試，唯一缺的是排程快照沒有把「這場比賽是否啟用詳細設定」送到前端。技術做法是把 `AllCourtsCourtBlockComponent`（架構上與管理頁 `CourtControlComponent` 幾乎相同的姊妹元件）的詳細計分流程整段移植過來，只替換資料來源與狀態型別。唯一需要特別設計的是**凍結**：管理頁的場地控制元件沒有自己的 live state，賽末點會讓父元件重抓後 `current_match` 變 `null`、把詳細視窗的 DOM 連同整塊區塊拆掉，因此需要 `frozenCourt` signal + `displayCourt()` computed 讓這個元件在視窗開啟期間忽略輸入更新，同時不影響其他場地的即時更新。

## Technical Context

**Language/Version**: TypeScript 5.9（前端）、Python 3.12（後端）

**Primary Dependencies**: Angular 20.3（standalone components + signals）、`@ngx-translate/core` 18、Ably 2.28、RxJS 7.8；FastAPI + Pydantic v2 + SQLAlchemy（async）

**Storage**: PostgreSQL。**本功能無資料庫變更、無 Alembic migration。**

**Testing**: 前端 Vitest（`ng test`）；後端 pytest（contract / integration / unit 三層）

**Target Platform**: 響應式網頁，主要使用情境是球場邊的手機瀏覽器

**Project Type**: Web application（`apps/web` Angular SPA + `apps/api` FastAPI）

**Performance Goals**: 按下「+1」後比分即時更新，不等詳細視窗（FR-002、SC-002）；即時同步端到端 < 1 秒（憲章原則 III）

**Constraints**:
- 詳細視窗開啟期間該場地區塊不得被即時更新拆除，但**其他場地必須照常更新**（FR-011、research.md Decision 7）
- 是否啟用詳細模式一律讀比賽快照，不得讀團的當下設定（憲章原則 III、FR-015）
- 0 個新端點、0 個新錯誤碼、0 個新語系 key

**Scale/Scope**: 1 個後端 schema 欄位 + 1 行填值；前端 3 個檔案實質改動（元件 ts/html、service、models）；新增前端元件測試與 1～2 條後端契約測試。無 NEEDS CLARIFICATION。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

逐條對照憲章 v1.0.0 核心原則 I–XI：

| 原則 | 是否觸及 | 如何符合 |
|---|---|---|
| **I. 程式碼品質與型別安全** | ✅ 觸及 | 新增欄位在前後端型別同步宣告（`MatchSummary`、`ScoreMutationResult.score_event_id`），不使用 `any` 或型別斷言。合併前跑 `npm run lint`、`npx tsc --noEmit`、`ruff`、`mypy`。 |
| **II. 測試優先** | ✅ 觸及（比分計算相關） | 後端補契約測試（快照值正確、且不因團設定變更而回溯）；前端補 `court-control.component.spec.ts` 的詳細模式測試，涵蓋加分即開視窗、略過、取消、賽末點撤銷、凍結、連點防護。 |
| **III. 即時性與資料一致性** | ✅ **重點觸及** | (a) **設定快照**：FR-015 明定讀 `matches.detailed_scoring_enabled`，research.md Decision 3 明確否決「改讀團當下設定」的捷徑。(b) **即時性**：凍結只讓**單一場地元件**忽略輸入，`changed.emit()` 照常立即發出，其他場地與名單不停更（Decision 7）。(c) **不顯示陳舊分數**：凍結期間顯示的是加分回應本身帶回的伺服器值（FR-012），不是本地推測；視窗關閉立刻回到伺服器狀態（FR-011）。(d) **離線**：沿用既有規則停用操作（FR-018）。 |
| **IV. 權限與安全** | ✅ 觸及 | 全程走既有的管理員 PIN session（`ScheduleService.authHeader(groupId)` + 後端 `require_admin`），不引入 token 路徑（FR-019）。**方向確認**：憲章禁止的是「把管理員專屬操作放到免驗證畫面」；本功能是把**已存在於公開畫面的非專屬能力**（詳細計分）補進管理頁，方向相反，不構成違反。無新端點，權限模型零變更。 |
| **V. UX 二次確認** | ➖ 不觸及 | 不新增破壞性操作。「取消這一分」是**修正**手段而非破壞性動作，且與公開控制頁面行為一致（該處也未加二次確認），維持一致不另加。既有的「提前結束」確認框不動。 |
| **VI. 可維護性** | ✅ 觸及 | 移植既有模式而非發明第三套寫法（Decision 1）；詳細記錄視窗沿用同一個共用元件 `ShotPlacementPickerComponent`，`PendingPoint` / `ScoreTapGuard` 直接引用不修改。模組邊界不變（計分板/控制板模組內部）。 |
| **VII. 無障礙與行動優先** | ✅ 觸及 | 沿用既有視窗元件，其無障礙處理（`aria-label`、非僅色彩區分）不變。取消失敗提示以 `role="alert"` 呈現，比照 `all-courts` 既有做法。 |
| **VIII. i18n** | ✅ 觸及 | **新增 0 個語系 key**——逐一核對後確認 `shotPlacement.*` 19 個 key 與五個取消失敗錯誤碼文案（`ROUND_ALREADY_ADVANCED`、`NEXT_MATCH_ALREADY_STARTED`、`MATCH_NOT_COMPLETED`、`SIDE_DID_NOT_WIN_THIS_MATCH`、`ADMIN_TOKEN_INVALID`）在 `zh-TW.json`／`en.json` 皆已存在（Decision 4）。後端不新增錯誤碼，前端不引入硬寫字串（FR-020）。時區邏輯不觸及。 |
| **IX. 可攜性與可部署性** | ➖ 幾乎不觸及 | 無新環境變數、無新密鑰、無 migration。Docker 建置流程不變。 |
| **X. 伺服器為唯一可信來源** | ✅ 觸及 | 所有比分／詳細資料變更都先經後端 API 寫入，前端僅訂閱事件；凍結期間顯示的是**後端回應帶回的值**，不是前端自行推算的比分，也不發布任何事件。 |
| **XI. 防機器人/防濫用** | ➖ 不觸及 | 不涉及公開的建立資源端點；操作限管理員已驗證的 session。 |

**Gate 結果**：全數通過，無偏離。Complexity Tracking 表為空。

**Post-Design re-check（Phase 1 後）**：data-model.md 與 contracts/ 完成後重新對照——設計確認為「零資料庫變更、零新端點、零新語系 key、一個唯讀布林欄位」，沒有引入任何新的複雜度來源，上表結論不變，仍無需 Complexity Tracking 條目。

## Project Structure

### Documentation (this feature)

```text
specs/038-admin-detailed-scoring/
├── plan.md              # This file (/speckit-plan command output)
├── spec.md              # /speckit-specify output
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── schedule-api-additions.md   # Phase 1 output
├── checklists/
│   └── requirements.md  # /speckit-specify output
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
apps/api/
├── app/domains/schedule/
│   ├── schemas.py              # MatchSummary += detailed_scoring_enabled
│   ├── service.py              # build_schedule_snapshot(): 填入快照值（唯一建構點，~L2064）
│   └── router.py               # 不改（三個管理員端點已存在）
└── tests/contract/
    └── test_detailed_scoring_toggle.py   # 補：排程快照反映比賽快照、不隨團設定回溯

apps/web/src/app/
├── features/group-admin/schedule-management/
│   ├── schedule.models.ts               # MatchSummary += detailed_scoring_enabled
│   │                                    # ScoreMutationResult += score_event_id
│   ├── schedule.service.ts              # 補 recordShotPlacement() / undoMatchCompletion()
│   ├── court-control.component.ts       # 主要改動：凍結 + PendingPoint + ScoreTapGuard
│   ├── court-control.component.html     # 改讀 displayCourt()、+1 分支、掛上 picker、取消失敗提示
│   └── court-control.component.spec.ts  # 補詳細模式測試
└── features/shot-placement/             # 不改，直接引用
    ├── shot-placement-picker.component.ts
    ├── pending-point.ts
    └── score-tap-guard.ts
```

**Structure Decision**：沿用既有的 `apps/api`（FastAPI）+ `apps/web`（Angular）雙專案結構，本功能不新增任何目錄或模組。改動集中在 `group-admin/schedule-management` 這一個前端資料夾，加上後端 schedule 模組的一個 schema 欄位；共用的詳細記錄視窗與狀態機類別位於 `features/shot-placement/`，本功能只引用不修改，以確保管理頁與公開控制頁面看到的是同一個介面（spec Assumptions）。

## 實作順序建議（供 `/speckit-tasks` 參照）

1. **後端欄位**：`schemas.py` + `service.py` 一行填值 + 契約測試。可獨立合併、對現有前端無影響。
2. **前端型別與服務層**：`schedule.models.ts` 兩個欄位、`schedule.service.ts` 兩個方法。純新增，無行為變化。
3. **US1（P1）**：`court-control.component.ts/html` 的 `scoreThenOpenPicker()` + picker 掛載 + `displayCourt()` 全面替換。交付後功能即可用。
4. **US2（P2）**：略過／取消／賽末點撤銷 + `cancelScoreErrorKey` 顯示。
5. **US3（P3）**：凍結的邊界情況（`abandonPoint`、`onShotPlacementClosed`）與 `ScoreTapGuard`、pulse effect 改綁 `displayCourt()`。

> 註：步驟 3 實務上必須連同 `frozenCourt`／`displayCourt()` 一起做（否則賽末點會把視窗拆掉），步驟 5 收的是其餘邊界；三者共用同一份凍結機制，不是三次獨立實作。

## Complexity Tracking

> 無憲章偏離，本表為空。
