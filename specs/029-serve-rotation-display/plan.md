# Implementation Plan: 計分板發球站位顯示

**Branch**: `main`（本專案未使用 per-feature git branch，延續既有慣例） | **Date**: 2026-09-15 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/029-serve-rotation-display/spec.md`，直接建立在 `/specs/030-score-serve-record/` 已完成的 `/speckit-plan` 之上——該計畫已把兩個功能共用的發球輪替演算法（誰目前發球、站位公式）與資料模型（`Match.serving_team`/`team_a_reference_server_id`/`team_b_reference_server_id`）設計並落地，本計畫**不重新推導演算法**，只處理「把這份已存在的即時發球狀態，透過既有的 `GET .../state` 端點與 `match.scoreUpdated` 即時事件送到前端，並在計分板畫面呈現」。交叉比對 `apps/api/app/domains/schedule/service.py`（`court_live_state()`、`apply_score_delta()` 既有的 `match.scoreUpdated` 發布點）與 `apps/web/src/app/features/scoreboard/`（既有畫面結構）。

## Summary

`GET /courts/by-token/{token}/state`（`court_live_state()`）的 `MatchLiveDetail` 新增一個巢狀 `serve` 欄位（發球者 + 雙方四個站位，直接複用 030 的站位公式即時算出，不重新發明第二套邏輯），既有 `match.scoreUpdated` Ably 事件的負載一併擴充帶上最新的 `serve` 快照，讓計分板不需要額外一次 API 呼叫就能跟著比分同步更新。計分板畫面把原本「同一隊兩位隊員名字疊在一起」的呈現，改成兩個各自獨立、對應左右發球區站位的位置槽（單打時只佔用其中一槽，另一槽留白，FR-006），並在目前發球者的位置槽加上非純色彩的視覺標記（圖示＋文字，Constitution VII）。控制板／多球場總覽的回應形狀雖然也會多出 `serve` 欄位（同一個共用的 `court_live_state()`），但依 spec Assumptions 不在這些畫面上渲染，維持現狀。

## Technical Context

**Language/Version**：延續既有（後端 Python 3.12+ FastAPI/SQLAlchemy；前端 TypeScript 5 / Angular 20+，`strict` mode）。

**Primary Dependencies**：沿用既有堆疊，**不新增任何第三方套件**。

**Storage**：**不新增任何 migration**——本功能純粹讀取 `030-score-serve-record` 已建立的 `matches.serving_team`／`team_a_reference_server_id`／`team_b_reference_server_id` 三個欄位，不新增、不修改任何資料表結構。**前提**：`030-score-serve-record` MUST 已實作（至少其 `matches` 新欄位與站位公式的共用函式已存在），本功能才有資料可讀；若 `030` 尚未實作，本功能的 `serve` 欄位在既有資料列上永遠是 `NULL`（沿用 030 data-model.md 對舊資料「不回填」的既有決議，行為上等同於「沒有發球狀態可顯示」，不會壞掉，只是沒有內容）。

**Testing**：pytest + pytest-asyncio（後端：`court_live_state()` 回傳的 `serve` 欄位在單打/雙打、有/無進行中比賽時的正確性；契約測試涵蓋 `GET .../state` 新欄位形狀、`match.scoreUpdated` 新負載形狀）。Vitest（前端：計分板元件依 `serve` 欄位渲染四個站位槽、單打時另一槽留白、發球者標記的非純色彩渲染屬性存在性檢查，比照既有 016 對雙曲線圖例的既有測試慣例；即時事件到達後畫面正確更新、不需重新整理）。

**Target Platform**：延續既有（Docker on AWS ECS，本地 `docker-compose`）。

**Project Type**：Web application（monorepo，本功能同時涉及 `apps/api` 與 `apps/web`）。

**Performance Goals**：SC-004——發球者與站位資訊的更新延遲，MUST 與既有比分同步的即時性一致（Constitution III：端到端延遲 SHOULD 在 1 秒以內）；因為直接搭在既有 `match.scoreUpdated` 事件上，不需額外的網路往返。

**Constraints**：FR-005——發球者標記 MUST NOT 僅靠顏色區分（Constitution VII）。FR-006——單打時另外兩個站位槽 MUST 保持空白，不得顯示不存在的第三、四位球員。FR-007——沒有進行中比賽時 MUST NOT 顯示任何站位資訊。FR-008——比分變動時 MUST 即時更新、不需重新整理頁面。

**Scale/Scope**：與既有計分板的即時更新規模相同（單一 Ably channel、單場比賽），不新增訂閱管道。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | 後端新增 Pydantic `ServeStationInfo` 巢狀 schema，前端新增對應 TypeScript interface，兩者欄位一一對應；`ruff`/`mypy --strict`、Angular `strict` mode 沿用既有 CI 設定。 | PASS |
| II. 測試優先 | 站位/發球者呈現屬於既有「比分計算」核心領域邏輯（承接 030）之顯示延伸，MUST 有後端契約測試覆蓋新欄位形狀、前端單元測試覆蓋單打/雙打槽位與非色彩標記；MUST 有至少一條整合測試涵蓋「開賽 → 加分 → 計分板即時顯示更新」全流程。 | PASS（列入 tasks.md 強制項） |
| III. 即時性與資料一致性 | `serve` 欄位隨既有 `match.scoreUpdated` 事件一起送達，維持與比分本身相同的即時性與一致性保證；重新連線時既有 `ReconnectRefetchService` 強制重新拉取 `GET .../state`（已含 `serve` 欄位），沿用既有「以伺服器最新狀態覆蓋畫面」規則，不需新增邏輯。 | PASS |
| IV. 權限與安全 | 不新增任何端點；`serve` 欄位附加在既有公開、唯讀的 `GET .../state` 回應與既有 `match.scoreUpdated` 事件上，權限邊界與既有欄位（`score_a`/`score_b`/`participants`）完全相同，未擴大任何存取範圍。 | 不適用（無新增介面） |
| V. UX 一致性（破壞性操作二次確認） | 本功能全程唯讀顯示，無任何寫入或破壞性操作。 | 不適用 |
| VI. 可維護性 | 站位計算邏輯 100% 重用 030 已實作的共用函式（不新增第二套算法），後端改動集中在既有 `court_live_state()`／`apply_score_delta()` 所在模組；前端改動集中在既有 `scoreboard` feature 模組，不影響 control-panel/all-courts 的既有渲染。 | PASS |
| VII. 無障礙與行動裝置優先 | FR-005：發球者標記 MUST 搭配圖示＋文字，不僅靠顏色，比照既有 `status-badge`／`next-up` 圖示+文字並用慣例；字體/對比延續既有計分板遠距離可讀設計，不縮小既有比分顯示區域。 | PASS（前端落實於 tasks.md 展開） |
| VIII. i18n 與時區 | 新增的站位/發球者相關顯示文字（例如「發球中」標記）MUST 集中於既有語系檔，不寫死中文；不新增任何錯誤代碼。 | PASS |
| IX. 可攜性與可部署性 | 不新增任何第三方套件、不新增基礎設施、不新增 migration。 | PASS |
| X. 即時同步的可信來源 | `serve` 欄位由後端在既有的伺服器端計算並附加於既有回應/事件，前端純渲染、不自行重新計算或推斷站位，維持伺服器為唯一可信來源（research.md Decision 1）。 | PASS |
| XI. 防機器人/防濫用 | 不新增任何「建立新資源」的公開端點。 | 不適用 |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/029-serve-rotation-display/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md         # Phase 1 output (/speckit-plan command)
├── contracts/
│   └── court-state-serve-fields.md
└── tasks.md              # Phase 2 output (/speckit-tasks command — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
apps/api/
├── app/domains/schedule/
│   ├── schemas.py         # + ServeStationInfo；MatchLiveDetail 新增 serve: ServeStationInfo | None
│   └── service.py         # court_live_state()：查詢新增 3 欄位、呼叫 030 共用的站位公式函式組出 serve
│                           # apply_score_delta()：既有 match.scoreUpdated publish() 負載新增 serve 欄位
└── tests/
    ├── contract/test_court_state.py           # 既有檔案擴充：serve 欄位形狀、單打/雙打槽位
    └── integration/test_scoring_flow.py        # 既有檔案擴充：加分後 serve 快照隨事件送達

apps/web/
└── src/app/
    ├── core/api/court-live-state.models.ts     # + ServeStationInfo；MatchLiveDetail 新增 serve 欄位
    └── features/scoreboard/
        ├── scoreboard.component.html           # 站位槽改為各自獨立元素（右/左）+ 發球者標記
        ├── scoreboard.component.scss            # 站位槽版面樣式、發球者標記樣式（非純色彩）
        ├── scoreboard.component.ts              # match.scoreUpdated 訂閱：一併合併 serve 欄位
        └── scoreboard.component.spec.ts         # 新增：四站位渲染、單打留白、發球者標記存在性
```

**Structure Decision**：後端延伸集中在既有 `schedule` 模組（沿用 030 的資料與函式，不重新設計）；前端延伸集中在既有 `scoreboard` feature（不影響 `control-panel`/`all-courts`，它們共用同一個後端回應形狀但本次不改動其模板）。

## Complexity Tracking

*本 feature 無 Constitution Check 違反項目，此表格從略。*

## Post-Design Constitution Check

*Re-evaluated after Phase 1（`data-model.md`、`contracts/`、`quickstart.md`）產出。*

設計階段的關鍵決策——(1) 站位/發球者一律由後端算好、前端純渲染
（research.md Decision 1，直接對應 Constitution X）、(2) 搭既有
`match.scoreUpdated` 事件一起送達、不新增事件類型（research.md
Decision 2，維持 Constitution III 的一致性保證，避免雙事件到達順序
不一致的風險）、(3) 畫面改動限縮在既有兩欄式版面內部拆分位置槽、不
整個重新設計計分板（research.md Decision 3，明確排除更大改動範圍）
——皆未新增端點、未新增第三方依賴、未新增資料表，且未變更任何既有
欄位的既有語意（純新增欄位）。對照 Constitution Check 表格，Phase 1
設計沒有引入任何新的違反項目。**Gate 結果維持 PASS，無需新增
Complexity Tracking 項目。**

## Assumptions

- `030-score-serve-record` 的 `matches` 新欄位與站位公式已抽出為
  `apps/api/app/domains/schedule/service.py` 內可被 `court_live_state()`
  直接呼叫的共用函式（例如一個純函式：輸入 `serving_team` +
  雙方 `reference_server` + 當下比分，輸出四個站位 + 發球者）——若
  030 實作時未抽出成獨立可重用函式，本功能的 tasks.md 階段 MUST 先
  補這個重構，而不是在 `court_live_state()` 另外複製一份計算邏輯
  （Constitution VI）。
- 發球者標記的具體圖示/文字內容（例如「🏸 發球中」或等效呈現）留待
  tasks.md/實作階段依既有 `status-badge`／`next-up` 樣式慣例決定，
  本 plan 只定義「MUST 非純色彩」的邊界，不預先指定確切文案（文案本身
  MUST 走 i18n 語系檔，非本 plan 決定範圍）。
- 站位槽在畫面上的左右／上下確切像素排列，留待 tasks.md 依
  research.md Decision 3 的「既有兩欄式版面內部拆分」原則展開，本 plan
  不預先畫出逐像素的版面稿。
