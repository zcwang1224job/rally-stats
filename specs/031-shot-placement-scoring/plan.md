# Implementation Plan: 落點詳細計分模式

**Branch**: `031-detailed-scoring-mode`（本 feature 使用者要求另開 per-feature 分支，非既有「延續 main」慣例——見下方 Assumptions） | **Date**: 2026-09-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/031-shot-placement-scoring/spec.md`，交叉比對 `/apps/api/app/domains/schedule/service.py`（`apply_score_delta()`——本 feature 唯一的比分寫入掛鉤點）、`/apps/api/app/domains/group/{models,service,router,schemas}.py`（`scoreboard_scoring_enabled` 的既有「團級別即時切換」實作，本 feature 的 `detailed_scoring_enabled` 團設定原樣比照）、`/apps/web/src/app/features/{scoreboard,control-panel,control-panel/all-courts}/*`（既有三處各自獨立的 +1/-1 按鈕實作，本 feature 需要一個共用元件讓三者共同改用）。

## Summary

新增一個團層級可切換的「詳細計分模式」：開啟後，該團之後建立的比賽會用「球場示意圖點落點 → 選球員 → 確認」取代既有 +1 按鈕；確認送出時以自由座標（浮點數 x/y，允許代表出界的邊界外數值）與所選球員（決定得分隊伍）呼叫新的 `/score-detailed` 端點，內部呼叫既有 `apply_score_delta()`（`delta=+1`）後，額外寫入一筆與同一個 `ScoreEvent` 一對一對應、不可變的 `ShotPlacementRecord`。既有「修正比分（-1）」端點不變——`apply_score_delta()` 的 `delta<0` 分支新增「順手刪除該隊最後一筆 `ShotPlacementRecord`（若存在）」的行為，對簡易模式比賽是無操作的 no-op，對詳細模式比賽則同時完成 FR-007 的收回。設定粒度、快照時機比照既有 `scoreboard_scoring_enabled`／`target_score` 兩種既有前例（依 Clarifications 2026-09-16 決議）。前端需要一個新的共用元件（球場圖點選 + 選球員的互動流程），供計分板、控制板、全場地控制板三處既有計分介面共同呼叫，避免三份重複實作。

## Technical Context

**Language/Version**：延續既有（後端 Python 3.12+，FastAPI + SQLAlchemy 2.0 async + Alembic；前端 Angular 20 + TypeScript strict mode）。本功能同時涉及前後端——與 029/030 純後端延伸不同。

**Primary Dependencies**：沿用既有 FastAPI/SQLAlchemy/Alembic（後端）與既有 Angular standalone components/signals（前端）堆疊，**不新增任何第三方套件**——球場示意圖以既有專案慣用的 CSS/SVG inline 技巧繪製（比照計分板既有球場線條/球網的純 CSS 做法，見 `scoreboard.component.scss` 現有實作），不需圖表/繪圖函式庫。

**Storage**：PostgreSQL，需要 **1 個 Alembic migration**：
- `groups` 表新增 1 個欄位：`detailed_scoring_enabled`（bool，`NOT NULL DEFAULT false`）。
- `matches` 表新增 1 個欄位：`detailed_scoring_enabled`（bool，`NOT NULL`，比賽建立當下由 `group.detailed_scoring_enabled` 快照而來；既有資料列以 `server_default=false` 回填）。
- 新增 1 個資料表 `shot_placement_records`（每筆詳細模式下的 `ScoreEvent`〔`delta > 0`〕對應 0 或 1 筆；簡易模式比賽永遠 0 筆）。
詳見 data-model.md。

**Testing**：
- 後端：pytest + pytest-asyncio（單元測試：`apply_score_delta()` 在有/無 `shot_placement` 參數下的行為、`delta<0` 刪除最後一筆記錄且對簡易模式無操作、`roster_entry_id` 不屬於該場比賽時的驗證錯誤、`match.detailed_scoring_enabled=false` 時呼叫 `/score-detailed` 的拒絕錯誤；契約測試：新舊 `/score`、新 `/score-detailed`、`PATCH .../detailed-scoring` 的回應形狀；至少一條整合測試涵蓋「團開啟詳細模式 → 開新比賽 → 標落點加分（含 side-out 情境）→ 查詢 `shot_placement_records` → 修正比分收回最後一筆」全流程）。
- 前端：Vitest（新共用元件的互動狀態機——選落點/選球員/確認前可重選/確認送出；三個既有計分畫面改用新元件後的既有測試需同步更新選擇器，比照本次會話稍早處理計分板 UI 重構時的模式）。

**Target Platform**：延續既有（Docker on AWS ECS，本地 `docker-compose`；瀏覽器：與既有計分板/控制板相同的行動裝置優先支援範圍）。

**Project Type**：Web application（monorepo，本功能同時涉及 `apps/api` 與 `apps/web`）。

**Performance Goals**：SC-001——計分員在詳細模式下完成一次加分（點落點、選球員、確認）中位數時間 10 秒以內；此為 UI 互動流暢度目標，非後端效能目標，`/score-detailed` 端點本身沿用 `apply_score_delta()` 既有「同一交易內完成」的寫入模式，不新增額外的網路往返（比照 030 SC-003 的既有驗收慣例，不建置額外效能量測基礎設施）。

**Constraints**：FR-003（確認前的暫時選擇不落地，純前端狀態，未呼叫 API 前不產生任何後端副作用）。FR-004（球員清單 MUST 限定該場比賽實際參賽者，後端 `roster_entry_id` 驗證作為最終防線，不能只靠前端過濾）。FR-006（`matches.detailed_scoring_enabled` 為快照欄位，變更團設定 MUST NOT 回溯影響進行中比賽）。FR-010（座標允許代表出界的邊界外數值，後端驗證範圍需寬鬆到能涵蓋合理的出界誤差，而非嚴格鎖在 `[0,1]`——見 research.md Decision 1）。

**Scale/Scope**：每場詳細模式比賽的 `shot_placement_records` 筆數上限與該場比賽「加分（`delta > 0`）」事件數相同，由既有 `cap_score` 決定（一般 ≤ 30），數量級小。前端改動範圍涵蓋三個既有計分畫面（計分板、控制板、全場地控制板）+ 1 個團管理設定頁新增開關，範圍明顯大於 029/030 純後端延伸。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | 新增 SQLAlchemy model（`ShotPlacementRecord`）、`Group`/`Match` 新欄位皆為明確型別（`Float`、`Boolean`）；前端新共用元件與 `CourtControlService.scoreDetailed()` 全程 TypeScript strict mode，`ruff`/`mypy --strict`/`tsc --noEmit`/`ng lint` blocking check 沿用既有 CI 設定。 | PASS |
| II. 測試優先 | 落點/球員記錄與修正比分的收回邏輯屬於原則 II 明列的「比分計算」核心領域邏輯之直接延伸，MUST 有單元測試涵蓋：`roster_entry_id` 驗證、`detailed_scoring_enabled` 守門、`delta<0` 刪除最後一筆記錄；MUST 有至少一條整合測試涵蓋「開啟詳細模式 → 開賽 → 標落點加分 → 修正比分收回」全流程。 | PASS（列入 tasks.md 強制項） |
| III. 即時性與資料一致性 | 新表寫入與既有 `ScoreEvent` 寫入在同一個資料庫交易內完成；`matches.detailed_scoring_enabled` 於比賽建立當下快照，變更團設定 MUST NOT 回溯影響進行中比賽（比照既有 `target_score` 快照慣例，呼應 FR-006／Constitution III「設定變更的時間一致性」）。比賽被捨棄（abandoned）時已寫入的落點紀錄 MUST 不受影響（FR-009，比照既有比賽紀錄完整性原則）。 | PASS |
| IV. 權限與安全 | 新增的 `/score-detailed` 端點（token 版 + admin 版）完全比照既有 `/score` 端點的權限驗證路徑（`_can_score_by_token`／`require_admin`），零新增權限模型；`roster_entry_id` 是否屬於該場比賽由後端驗證，不能只靠前端球員清單過濾（FR-004，呼應原則 X）。團設定切換端點 `PATCH .../detailed-scoring` 完全比照既有 `PATCH .../scoreboard-scoring` 的管理員限定存取。 | PASS |
| V. UX 一致性（破壞性操作二次確認） | 標錯落點/選錯球員的收回動作沿用既有「修正比分（-1）」既有互動，不是本功能新增的破壞性操作，不需要新的二次確認流程。 | 不適用 |
| VI. 可維護性 | 新增的球場圖點選＋選球員互動封裝成單一共用 Angular 元件，供計分板/控制板/全場地控制板三處既有計分介面共同呼叫，避免三份重複邏輯（呼應原則 VI，見 research.md Decision 2）；後端沿用既有 `apply_score_delta()` 單一比分寫入入口，新增可選參數而非另立一套平行的比分計算邏輯。 | PASS |
| VII. 無障礙與行動裝置優先 | 落點點選介面本質上是空間互動，難以完全脫離視覺；但「選球員」步驟以文字列表呈現（沿用既有球員選擇 UI 模式），不僅靠落點座標本身傳達得分歸屬（FR-002/Assumptions：得分歸屬完全由選球員決定，座標僅描述性）。畫面 MUST 沿用計分板/控制板既有的行動裝置優先字體與觸控目標尺寸慣例。 | PASS |
| VIII. i18n 與時區 | 新增顯示文字（球場圖操作提示、選球員清單、團設定頁新開關的文案）MUST 全數放入既有語系檔（`zh-TW.json`/`en.json`），不寫死文字；後端新增錯誤代碼（例如 `PARTICIPANT_NOT_IN_MATCH`、`DETAILED_SCORING_NOT_ENABLED`）MUST 回傳語意化代碼，不回傳寫死中文句子；`shot_placement_records.created_at` 沿用既有 `TIMESTAMPTZ`／UTC 慣例。 | PASS |
| IX. 可攜性與可部署性 | 新增 1 個 Alembic migration，沿用既有 migration 執行流程與 CI/CD，不新增基礎設施、不新增第三方套件（球場圖純 CSS 繪製，比照計分板既有做法）。 | PASS |
| X. 即時同步的可信來源 | 得分歸屬（哪隊加分）與落點紀錄的寫入全部在後端 `apply_score_delta()` 既有交易內完成，前端全程不參與計算也不直接寫入資料庫；`roster_entry_id` 合法性由後端驗證，不信任前端傳來的落點座標之外的任何隱含判斷。 | PASS |
| XI. 防機器人/防濫用 | 不新增任何「建立新資源」類型的公開端點（`/score-detailed` 是既有計分動作的變體，非帳號/團等資源建立）。 | 不適用 |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/031-shot-placement-scoring/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/
│   ├── score-detailed-api.md
│   └── group-detailed-scoring-toggle.md
└── tasks.md              # Phase 2 output (/speckit-tasks command — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
apps/api/
├── app/domains/group/
│   ├── models.py          # + Group.detailed_scoring_enabled
│   ├── service.py         # + set_detailed_scoring()（比照 set_scoreboard_scoring() 的
│   │                       #   「即時切換 + 逐場地廣播」模式）
│   ├── schemas.py          # + DetailedScoringRequest / DetailedScoringResponse
│   │                       # + AdminGroupResponse.detailed_scoring_enabled
│   └── router.py           # + PATCH /{group_id}/detailed-scoring
├── app/domains/schedule/
│   ├── models.py          # + Match.detailed_scoring_enabled（快照欄位）
│   │                       # + ShotPlacementRecord model
│   ├── service.py          # + create_match_with_participants()：新增
│   │                       #   detailed_scoring_enabled=group.detailed_scoring_enabled 快照
│   │                       # + apply_score_delta()：新增可選 shot_placement 參數
│   │                       #   （delta>0 寫入 ShotPlacementRecord；delta<0 刪除該隊
│   │                       #   最後一筆，no-op 於簡易模式）
│   │                       # + apply_detailed_score()（新函式：驗證 roster_entry_id
│   │                       #   屬於該場比賽、驗證 match.detailed_scoring_enabled，
│   │                       #   換算 side 後呼叫 apply_score_delta()）
│   ├── schemas.py          # + ScoreDetailedRequest
│   │                       # + MatchLiveDetail.detailed_scoring_enabled
│   └── router.py           # + POST .../matches/{match_id}/score-detailed（token 版 + admin 版）
├── alembic/versions/
│   └── <new_rev>_shot_placement_records.py   # Group/Match 新欄位 + shot_placement_records 新表
└── tests/
    ├── unit/domains/schedule/test_shot_placement.py       # roster_entry_id 驗證、
    │                                                        #   detailed_scoring_enabled 守門、
    │                                                        #   delta<0 刪除最後一筆
    ├── unit/domains/schedule/test_apply_score_delta.py     # 既有檔案擴充：shot_placement
    │                                                        #   參數的寫入/刪除行為
    ├── unit/domains/group/test_detailed_scoring.py          # set_detailed_scoring() 即時切換
    ├── integration/test_shot_placement_flow.py              # 開啟詳細模式 → 開賽 → 標落點
    │                                                        #   加分 → 查詢紀錄 → 修正比分收回
    └── contract/test_score_detailed_endpoint.py              # 新端點回應形狀、錯誤代碼

apps/web/
└── src/app/
    ├── core/api/
    │   ├── court-control.service.ts        # + scoreDetailed()
    │   └── court-live-state.models.ts       # + MatchLiveDetail.detailedScoringEnabled
    ├── features/
    │   ├── shot-placement/                  # 新增：共用元件
    │   │   ├── shot-placement-picker.component.ts
    │   │   ├── shot-placement-picker.component.html
    │   │   ├── shot-placement-picker.component.scss
    │   │   └── shot-placement-picker.component.spec.ts
    │   ├── scoreboard/
    │   │   ├── scoreboard.component.ts      # +1 按鈕改為依 detailedScoringEnabled
    │   │   │                                 #   條件式改叫 shot-placement-picker
    │   │   └── scoreboard.component.html
    │   ├── control-panel/
    │   │   ├── control-panel.component.ts   # 同上
    │   │   └── control-panel.component.html
    │   └── control-panel/all-courts/
    │       ├── all-courts-court-block.component.ts   # 同上
    │       └── all-courts-court-block.component.html
    └── features/group-admin/admin-page/
        ├── admin-page.component.ts          # + 詳細計分模式開關（比照既有
        │                                     #   scoreboard_scoring_enabled 開關 UI）
        └── admin-page.component.html
```

**Structure Decision**：前後端都涉及，後端集中在既有 `apps/api/app/domains/{group,schedule}/` 兩個既有模組（沿用既有 `Group`/`Match`/`ScoreEvent` 的既有歸屬），不新增後端模組；前端新增 1 個共用元件模組（`features/shot-placement/`），供三個既有計分畫面共同呼叫，不在三處各自重複實作互動邏輯（呼應原則 VI）。

## Complexity Tracking

*本 feature 無 Constitution Check 違反項目，此表格從略。*

## Post-Design Constitution Check

*Re-evaluated after Phase 1（`data-model.md`、`contracts/`、`quickstart.md`）產出。*

設計階段的關鍵決策——(1) 座標系統定義為涵蓋合理出界誤差的寬鬆範圍而非嚴格 `[0,1]`（research.md Decision 1），(2) 前端以單一共用元件供三處既有計分畫面呼叫，不重複實作（research.md Decision 2），(3) `apply_score_delta()` 新增可選參數而非另立平行的比分寫入路徑（research.md Decision 3），(4) 「修正比分」沿用既有 `/score` 端點、不新增獨立的 undo 端點（research.md Decision 4），(5) 團設定切換完全比照 `scoreboard_scoring_enabled` 既有模式（research.md Decision 5），(6) 快照時機比照 `target_score` 既有模式、僅在 `create_match_with_participants()` 一處設定（research.md Decision 6）——皆為在既有模組內、既有交易邊界內完成的延伸，未引入新的第三方依賴、未變更任何既有端點既有欄位的既有語意（`/score`、`/state` 回應皆為新增欄位而非修改既有欄位）。對照 Technical Context/Constitution Check 兩節的判定，Phase 1 設計沒有引入任何新的違反項目。**Gate 結果維持 PASS，無需新增 Complexity Tracking 項目。**

## Assumptions

- 本 feature 的 git 分支策略：使用者在 `/speckit-specify` 之前明確要求另開 per-feature 分支
  （`031-detailed-scoring-mode`），與 030 plan.md 記載的「本專案未使用 per-feature git
  branch」既有慣例不同——視為使用者對本次 feature 的明確指示，優先於舊有慣例記載，不視為
  衝突需要記錄於 Complexity Tracking（純流程決定，非架構/程式碼複雜度）。
- 球場示意圖在三個既有計分畫面（計分板、控制板、全場地控制板）中的視覺呈現細節（尺寸、
  是否即時顯示 029 的站位資訊疊加在同一張圖上）留待 tasks.md/實作階段依各畫面既有版面
  微調，本 plan 僅要求三者共用同一個互動元件與同一套資料模型。
- `shot_placement_records` 沿用既有 `score_serve_records`（030）的刪除慣例：`matches`/
  `score_events` 被刪除時（既有 `ON DELETE CASCADE`），對應的落點紀錄隨之刪除；比賽被
  捨棄（`abandoned`，非刪除）不觸發任何 `DELETE`，故已留存的紀錄不受影響（呼應 spec FR-009）。
- 落點/球員紀錄目前不提供任何專屬查詢端點或畫面（比照 spec Assumptions 與 030 前例），
  資料寫入後僅存在於資料庫，供未來另行規劃的分析功能取用；本次不新增任何讀取 API。
