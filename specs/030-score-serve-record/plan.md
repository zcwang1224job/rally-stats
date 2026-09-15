# Implementation Plan: 加分時記錄發球者與站位資訊

**Branch**: `main`（本專案未使用 per-feature git branch，延續既有慣例） | **Date**: 2026-09-15 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/030-score-serve-record/spec.md`，交叉比對 `/specs/029-serve-rotation-display/spec.md`（本 feature 依賴其定義的「正規發球順序規則」與「站位」概念，但該功能尚未有自己的 `/speckit-plan`——本計畫因此一併把兩者共用的發球輪替演算法設計完成，`029` 之後的 `/speckit-plan` 應直接引用本文件 research.md 的 Decision 1–5，不重新推導）、`/apps/api/app/domains/schedule/service.py`（`apply_score_delta()`、`create_match_with_participants()`、`pull_queued_match_for_court()`——本 feature 的三個既有掛鉤點，皆不新增外部呼叫介面）。

## Summary

每次比賽加分（`apply_score_delta()` 的 `delta > 0` 路徑）時，系統自動建立一筆與該次 `ScoreEvent` 一對一對應的 `ScoreServeRecord`，記錄「這一分由哪一位球員發球」以及「加分當下雙方（單打 2 位、雙打 4 位）球員各自的站位」，且每筆紀錄各自獨立保存、不被覆蓋。因為「目前是哪一隊/哪一位球員在發球」本質上是逐分累積的狀態（不是目前比分兩個數字就能反推的純函式），本功能在 `Match` 新增三個持久化欄位（`serving_team` + 雙方各自的 `reference_server`）作為比賽等級的即時發球狀態，隨每次加分於同一交易內遞移；「站位」則是這個發球狀態疊加當下比分奇偶（純函式，不需儲存）算出的結果，寫入 `ScoreServeRecord` 的快照欄位。`-1`（修正比分）依 Clarifications 決議完全不觸碰發球狀態、也不建立紀錄。本次不新增任何 API 端點或前端畫面（FR-005），純粹是後端資料模型與既有加分流程的延伸。

## Technical Context

**Language/Version**：延續既有（後端 Python 3.12+，FastAPI + SQLAlchemy 2.0 async + Alembic）。本功能不涉及前端，`apps/web` 無需變更。

**Primary Dependencies**：沿用既有 FastAPI/SQLAlchemy/Alembic 堆疊，**不新增任何第三方套件**。

**Storage**：PostgreSQL，需要 **1 個 Alembic migration**：
- `matches` 表新增 3 個欄位：`serving_team`、`team_a_reference_server_id`、`team_b_reference_server_id`（皆 nullable，比賽轉為 `in_progress` 前為 `NULL`）。
- 新增 1 個資料表 `score_serve_records`（每筆 `ScoreEvent` 對應 0 或 1 筆，`delta > 0` 才會有）。
詳見 data-model.md。

**Testing**：pytest + pytest-asyncio（單元測試：發球權轉換規則（同隊繼續發球 vs. side-out 換人）、單打/雙打站位公式邊界、`-1` 不建立紀錄且不改動發球狀態；契約測試：既有 `POST .../score` 端點回應形狀不變（本功能不改變任何既有回應欄位）；至少一條整合測試涵蓋「開賽 → 連續加分（含跨隊得分造成 side-out）→ 查詢資料庫確認每筆 `ScoreServeRecord` 各自正確且不被覆蓋」全流程）。

**Target Platform**：延續既有（Docker on AWS ECS，本地 `docker-compose`）。

**Project Type**：Web application（monorepo，本功能僅涉及 `apps/api`）。

**Performance Goals**：SC-003——加分動作因為多寫入一筆 `ScoreServeRecord`，MUST 與既有加分反應速度相比沒有使用者可感知的變慢；實作上與既有 `ScoreEvent` 寫入同一個資料庫交易，只多一次單筆 `INSERT`，無額外的網路往返或外部呼叫。此為非阻塞式品質關卡，以 tasks.md T018 的人工/程式碼審查驗證，不建置額外的效能量測基礎設施（比照既有 016 feature 對其效能目標的驗收慣例）。

**Constraints**：FR-004——`-1` MUST NOT 建立 `ScoreServeRecord`、MUST NOT 改動 `serving_team`/`reference_server` 欄位。FR-003——每筆紀錄 MUST 各自獨立、不可變（immutable），寫入後不再更新。FR-005——本次範圍不含任何新查看/顯示介面或新端點。

**Scale/Scope**：每場比賽的 `ScoreServeRecord` 筆數上限與既有 `ScoreEvent` 中「加分（`delta > 0`）」的筆數相同，由 `cap_score`（既有欄位，一般 ≤ 30）決定，數量級小。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | 新增 SQLAlchemy model（`ScoreServeRecord`）與 `Match` 新欄位皆為明確型別（`UUID`、`String(1)` 列舉），不使用 JSON/blob 欄位；`ruff`/`mypy --strict` blocking check 沿用既有 CI 設定。 | PASS |
| II. 測試優先 | 發球權轉換規則屬於原則 II 明列的「比分計算」核心領域邏輯之直接延伸，MUST 有單元測試涵蓋 side-out 判定、單打/雙打站位公式邊界、`-1` 排除邏輯；MUST 有至少一條整合測試涵蓋「開賽 → 加分 → 查詢紀錄」全流程。 | PASS（列入 tasks.md 強制項） |
| III. 即時性與資料一致性 | 新欄位/新表的寫入與既有 `ScoreEvent` 寫入在同一個資料庫交易內完成，維持「畫面即真相」的單一資料來源；本功能不新增任何即時廣播（Ably）事件，也不影響既有比分同步行為。與「比賽紀錄完整性一致性」段落（MatchResult/勝負判定）無關——本功能不改變任何比賽結束/捨棄的判定邏輯。 | PASS |
| IV. 權限與安全 | 不新增任何 API 端點（FR-005），沿用既有 `apply_score_delta()` 呼叫路徑既有的 `scoreboard_token`/`control_panel_token`/管理員授權驗證，零修改、零放寬。 | 不適用（無新增介面） |
| V. UX 一致性（破壞性操作二次確認） | 本功能全程為系統自動記錄，無任何使用者互動或破壞性操作。 | 不適用 |
| VI. 可維護性 | 發球狀態轉換與站位計算邏輯集中新增於既有 `apps/api/app/domains/schedule/service.py`（`apply_score_delta()` 所在模組），沿用既有 `create_match_with_participants()`／`pull_queued_match_for_court()` 作為僅有的兩個「比賽轉為進行中」掛鉤點，不新增跨模組相依。 | PASS |
| VII. 無障礙與行動裝置優先 | 本功能不涉及任何 UI 渲染。 | 不適用 |
| VIII. i18n 與時區 | 不新增任何顯示文字或錯誤代碼（本功能全自動，沒有會失敗的使用者輸入路徑）；`score_serve_records.created_at` 沿用既有 `TIMESTAMPTZ`／UTC 慣例。 | PASS |
| IX. 可攜性與可部署性 | 新增 1 個 Alembic migration，沿用既有 migration 執行流程與 CI/CD，不新增基礎設施、不新增第三方套件。 | PASS |
| X. 即時同步的可信來源 | 發球狀態與站位快照皆由後端在既有的伺服器端交易中計算並寫入資料庫，前端全程不參與計算也不寫入，維持伺服器為唯一可信來源。 | PASS |
| XI. 防機器人/防濫用 | 不新增任何「建立新資源」的公開端點。 | 不適用 |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/030-score-serve-record/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md         # Phase 1 output (/speckit-plan command)
├── contracts/
│   └── no-new-endpoints.md
└── tasks.md              # Phase 2 output (/speckit-tasks command — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
apps/api/
├── app/domains/schedule/
│   ├── models.py         # + Match.serving_team / team_a_reference_server_id / team_b_reference_server_id
│   │                     #   + ScoreServeRecord model
│   ├── service.py         # + _initialize_serve_state()（match 轉 in_progress 時呼叫，供
│   │                     #   create_match_with_participants() 與 pull_queued_match_for_court() 共用）
│   │                     # + _advance_serve_state_and_snapshot()（apply_score_delta() 的 delta>0
│   │                     #   分支內呼叫：判定 side-out、更新 serving_team/reference_server、
│   │                     #   計算站位快照、寫入 ScoreServeRecord）
│   └── (schemas.py 不變 — 本功能不新增任何對外回應欄位)
├── alembic/versions/
│   └── <new_rev>_score_serve_records.py   # Match 新欄位 + score_serve_records 新表
└── tests/
    ├── unit/domains/schedule/test_serve_state.py         # 發球權轉換規則、站位公式（單打/雙打）
    ├── unit/domains/schedule/test_apply_score_delta.py   # 既有檔案擴充：-1 不建立紀錄／不動發球狀態
    └── integration/test_score_serve_record_flow.py       # 開賽 → 連續加分（含 side-out）→ 查詢紀錄
```

**Structure Decision**：純後端延伸，集中在既有 `apps/api/app/domains/schedule/` 模組（`Match`/`ScoreEvent` 既有歸屬模組），不新增模組、不觸碰 `apps/web`。

## Complexity Tracking

*本 feature 無 Constitution Check 違反項目，此表格從略。*

## Post-Design Constitution Check

*Re-evaluated after Phase 1（`data-model.md`、`contracts/`、`quickstart.md`）產出。*

設計階段的關鍵決策——(1) 以「比賽等級持久化發球狀態 + 每次加分一筆
不可變快照」雙層架構取代逐次重播（research.md Decision 1），(2) 雙打
換人發球採「僅在拿回發球權時輪替」的簡化規則（research.md Decision
2），(3) 初始化掛鉤在既有 `create_match_with_participants()`／
`pull_queued_match_for_court()` 兩處、不新增狀態機（research.md
Decision 4），(4) `-1` 完全不觸碰發球狀態、不建立紀錄（research.md
Decision 5）——皆為在既有模組（`schedule/service.py`）內、既有交易邊界
內完成的資料模型延伸，未新增對外介面（`contracts/no-new-endpoints.md`
已確認）、未新增第三方依賴、未變更任何既有端點的請求/回應形狀，也未
觸碰前端。對照 Technical Context/Constitution Check 兩節的判定，Phase
1 設計沒有引入任何新的違反項目。**Gate 結果維持 PASS，無需新增
Complexity Tracking 項目。**

## Assumptions

- 「隊伍另一位球員」的判定（side-out 換人、單打站位公式的「另一格」）
  一律直接查詢當下的 `MatchParticipant`（`match_id` + `team`），不額外
  快取或另建索引——單場比賽每隊最多 2 位參賽者，查詢成本可忽略。
- `serving_team`／`reference_server` 三個新欄位與 `score_serve_records`
  新表的初始化、遞移、快照寫入邏輯，實作時集中在 1–2 個新的私有函式
  （`_initialize_serve_state()`／`_advance_serve_state_and_snapshot()`，
  見上方 Project Structure），供 `create_match_with_participants()`／
  `pull_queued_match_for_court()`／`apply_score_delta()` 呼叫；具體函式
  簽章與參數留待 tasks.md/實作階段決定，本 plan 僅定義其職責邊界。
- 本功能不處理「比賽被刪除場地/解散團等中止情境」對已寫入
  `score_serve_records` 的影響——沿用既有 `ON DELETE CASCADE` 慣例
  （`matches` 被刪除時，其 `score_serve_records` 隨之刪除，與既有
  `score_events`/`match_participants` 的既有刪除行為一致），不特別
  設計例外保留機制（spec Edge Cases 僅要求「已留下的紀錄不受比賽被
  捨棄影響」，捨棄≠刪除，`abandoned` 狀態不會觸發任何 `DELETE`）。
