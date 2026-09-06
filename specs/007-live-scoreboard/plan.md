# Implementation Plan: 即時計分板與控制板（Live Scoreboard & Control Panel）

**Branch**: `N/A (no git repository initialized)` | **Date**: 2026-09-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/007-live-scoreboard/spec.md`，交叉比對 `/specs/architecture.md`（Match/MatchResult 合併決策已定案）、`/specs/001-create-manage-group/`（比賽設定三欄位定義、驗證規則）、`/specs/002-court-management/`（`Court.scoreboard_token`/`control_panel_token`、`RealtimeService`/`LinkHeartbeatService` 斷線重連基礎設施）、`/specs/003-schedule-rotation/`（`Match` 模型、`advance_court_after_match_ends`／`check_round_complete_and_maybe_auto_advance` 兩個明確為 007 預留的 hook、`rotation.updated`／`match.nextRound` Ably 事件）。

## Summary

計分員在控制板（單一場地或全部場地模式）對進行中的比賽按 +1/-1；後端以
單一原子 `UPDATE ... WHERE status = 'in_progress' [AND score > 0]` 達成
「不可為負分」「已終態比賽不可再寫入」兩項防呆，命中後在同一交易內依
團的比賽設定快照判定是否達標，達標則轉為 `completed` 並寫入
`winner_team`；「提前結束」以同樣的原子防呆轉為 `abandoned`（不寫入
`winner_team`，即「不產生 MatchResult」）。任一終態轉換後，依序呼叫 003
已預留的 `advance_court_after_match_ends`（演算法排程機制自動領取賽程表
下一場比賽，手動模式為 no-op）與
`check_round_complete_and_maybe_auto_advance`（Auto Next Round），並發布
新增的 `match.scoreUpdated`/`match.ended` 事件（重用 003 既有的
`rotation.updated`/`match.nextRound`）。控制板寫入端點僅接受
`control_panel_token`（不接受 `scoreboard_token`），管理頁「場地控制」
區塊則透過既有的管理員 PIN 驗證路徑呼叫同一組服務函式。計分板/控制板/
管理頁三者共用同一套斷線重連邏輯——觀察既有 `RealtimeService
.connectionState`，重新連線後強制以新增的 `GET .../state` 端點回應
覆蓋本地畫面。本 feature 不新增資料表、不需要 Alembic migration。

## Technical Context

**Language/Version**：延續 001-004、006（後端 Python 3.12+；前端
TypeScript / Angular 20+）。

**Primary Dependencies**：沿用既有 FastAPI/SQLAlchemy/Alembic、Ably
REST/JS SDK 堆疊，不新增套件。

**Storage**：PostgreSQL，**不新增資料表/欄位**（research.md #1）——
`matches` 表既有欄位已完整涵蓋本 feature 所需的比分/狀態/快照設定。

**Testing**：pytest + pytest-asyncio。核心領域邏輯（+1/-1 原子防呆之
真實併發測試——比照 004 之 `test_join_capacity_concurrency.py` 模式、
達標判定公式之邊界情境、提前結束之捨棄規則、`match_id`/`court_id`
授權邊界、`control_panel_token` vs `scoreboard_token` 之寫入端點拒絕）
MUST 有單元測試；至少一條整合測試涵蓋「+1/-1 → 自然達標 → 自動領取
下一場 → 延遲請求 no-op」全流程（呼應情境 2）。前端 Vitest 涵蓋
斷線重連之強制覆蓋邏輯（`connectionState` 轉換觸發 state 重新拉取）。

**Target Platform**：延續 001-004、006。

**Project Type**：Web application（monorepo，延續既有結構）。

**Performance Goals**：SC-001——+1/-1 操作後同一場地之計分板/控制板/
管理頁場地控制區塊，約 1 秒內同步反映最新比分（Ably 端到端延遲，SHOULD
等級，非 blocking gate，quickstart.md 情境 1 人工抽測）。

**Constraints**：+1/-1 與提前結束之邊界防呆 MUST 於同一句資料庫原子
`UPDATE ... WHERE` 內達成（FR-007，research.md #5），達標判定/hook 呼叫
可在同一交易內以額外語句完成，但 MUST NOT 拆成「先查詢再判斷」的應用層
邏輯覆蓋掉原子語句本身的防呆責任；控制板寫入端點 MUST NOT 接受
`scoreboard_token`（research.md #3）；控制板（兩種模式）MUST NOT 提供
Next Round 操作入口（FR-014）。

**Scale/Scope**：+1/-1 為系統中最高頻的寫入操作（單場比賽可能對應數十次
點擊），效能上僅需單一索引式 `UPDATE ... WHERE id = :match_id`（主鍵
查找），不需額外索引或快取層。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | Pydantic v2 schema 對應所有請求/回應（`ScoreMutationResult`/`CourtLiveState` 等）；`ruff`/`mypy --strict` blocking check；前端 TypeScript strict mode，`side`/`delta` 等聯合型別對應後端 Literal。 | PASS |
| II. 測試優先 | +1/-1 原子防呆（真實併發測試）、達標判定公式、提前結束捨棄規則、`match_id`/token 授權邊界皆屬核心領域邏輯，MUST 有單元測試；至少一條整合測試涵蓋完整計分流程。 | PASS（列入 tasks.md 強制項） |
| III. 即時性與一致性 | 本 feature 是本原則的主要實作對象——SC-001 之 1 秒同步、FR-021~025 之斷線重連強制覆蓋、FR-006/006a 之「已終態比賽不可再寫入」防呆、比賽設定快照（沿用 003/001 已建立的快照機制，本 feature 只讀不重新快照）、捨棄比賽不產生 MatchResult（research.md #1）皆直接對應本原則之具體條文。 | PASS |
| IV. 權限與安全 | 控制板寫入端點 MUST 僅接受 `control_panel_token`（research.md #3，本 feature 對既有 002 兩連結分離設計的延伸落實）；管理頁場地控制區塊之操作 MUST 透過既有管理員 PIN session 驗證路徑（`_admin_court` 模式），MUST NOT 與公開 token 驗證共用同一段程式碼路徑（僅共用其後的業務邏輯服務函式，research.md #10，兩者性質不同：前者是認證機制、後者是業務規則，原則 IV 之「MUST NOT 共用同一套機制」指前者）；控制板（兩種模式）MUST NOT 提供 Next Round 入口（FR-014，SC-004）。 | PASS |
| V. UX 一致性 | 「提前結束」為破壞性操作（捨棄比賽），MUST 有二次確認流程（FR-008），前端落實於 tasks.md 展開；後端不需額外確認 token（quickstart.md 情境 3 說明）。 | PASS |
| VI. 可維護性 | 擴充既有 `schedule` 模組（新增 `apply_score_delta`/`end_match_early`/`peek_next_queued_match`），不新建獨立模組；管理頁與公開控制板共用同一組服務函式而非各自實作（research.md #10），對 003 的唯一觸碰為呼叫其已明確預留的兩個 hook（`advance_court_after_match_ends`/`check_round_complete_and_maybe_auto_advance`），不修改其簽章。 | PASS |
| VII. 無障礙 | 計分板比分 MUST 大字體顯示（FR-016）；Round 編號 MUST 與比分有明確視覺區隔（非僅字體大小差異，MUST 搭配文字標籤，FR-017，呼應原則 VII 之「MUST NOT 僅依賴單一視覺元素」精神）；斷線提示 MUST 同時有圖示與文字（非僅顏色變化）。 | PASS（前端落實於 tasks.md 展開） |
| VIII. i18n 與時區 | 錯誤回應一律語意化代碼（`LINK_NOT_FOUND`、`MATCH_NOT_FOUND`、`VALIDATION_ERROR`）；「等待管理員安排下一場」等提示文字集中於語系檔，不寫死於元件。 | PASS |
| IX. 可攜性 | 沿用既有 Docker/AWS 設計，不需額外基礎設施。 | PASS |
| X. 伺服器為單一事實來源 | 所有比分/狀態變更一律先經後端原子 SQL 驗證並寫入資料庫，commit 後才透過既有 `publish()` wrapper 廣播 Ably 事件（research.md #5、#7）；前端 MUST 僅訂閱事件，本 feature 未引入任何前端直接發布 Ably 事件的路徑。 | PASS |
| XI. 防機器人 | 本 feature 之端點皆非「建立新資源」類型（比分變更/比賽終結，非註冊/開團），不在原則 XI 之 Turnstile 強制範圍內；濫用風險已由 token 本身的不可猜測性（UUID）與既有場地/團生命週期機制自然限縮。 | PASS（明確排除項，非違反） |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/007-live-scoreboard/
├── plan.md                    # 本檔案
├── research.md                # Phase 0 產出
├── data-model.md              # Phase 1 產出
├── quickstart.md              # Phase 1 產出
├── contracts/                 # Phase 1 產出
│   ├── scoring-api.md
│   └── ably-events.md
└── tasks.md                   # /speckit-tasks 產出（本指令不建立）
```

### Source Code (repository root)

```text
apps/api/
├── app/
│   └── domains/
│       └── schedule/
│           ├── schemas.py     # 擴充：CourtLiveState/MatchLiveDetail/NextUpPreview/
│           │                    #   ScoreMutationResult/ScoreRequest；MatchSummary 補
│           │                    #   score_a/score_b；CourtScheduleStatus 補 next_up
│           ├── service.py     # 擴充：apply_score_delta()、end_match_early()、
│           │                    #   peek_next_queued_match()、_match_wins()（達標判定
│           │                    #   公式，research.md #2）、court_live_state()；呼叫既有
│           │                    #   advance_court_after_match_ends/
│           │                    #   check_round_complete_and_maybe_auto_advance
│           └── router.py      # 擴充：GET /courts/by-token/{token}/state、
│                                #   POST /courts/by-token/{token}/matches/{match_id}/score、
│                                #   POST /courts/by-token/{token}/matches/{match_id}/end、
│                                #   GET /groups/by-all-courts-token/{token}/state、
│                                #   POST /groups/by-all-courts-token/{token}/courts/{court_id}/
│                                #     matches/{match_id}/score｜end、
│                                #   POST /groups/{group_id}/courts/{court_id}/matches/{match_id}/
│                                #     score｜end（管理員版本，_admin_court 模式）
└── tests/
    ├── unit/domains/schedule/  # 擴充：本 feature 之新測試檔案
    ├── contract/
    └── integration/

apps/web/
└── src/app/
    ├── core/
    │   ├── api/
    │   │   └── court-live-state.models.ts   # 新增：CourtLiveState 等回應型別
    │   └── realtime/
    │       └── reconnect-refetch.service.ts # 新增：共用斷線重連強制覆蓋邏輯（research.md #8）
    └── features/
        ├── scoreboard/           # 擴充既有骨架：串接 state 端點 + match.scoreUpdated/
        │                            match.ended 訂閱 + 斷線重連
        ├── control-panel/        # 擴充既有骨架：+1/-1/提前結束操作 + 二次確認 UI
        │   └── all-courts/       # 擴充既有骨架：多場地版本
        └── group-admin/
            └── schedule-management/  # 擴充：管理頁場地控制區塊（比照 manual-assign
                                        #   既有元件模式，新增比分操作 UI）
```

**Structure Decision**：擴充既有 `app/domains/schedule` 模組（不新建
獨立的 `scoring`/`match` 模組——比分本來就是 `Match` 實體的一部分，
003 已將其模型定義於此模組，符合原則 VI 之模組邊界）；前端沿用 002
已建立的 `features/scoreboard`/`features/control-panel` 骨架目錄，本
feature 補上實際的比分操作/顯示邏輯，並擴充 `group-admin/schedule-
management` 既有目錄補上場地控制區塊。

## Complexity Tracking

*本 feature 無 Constitution Check 違反項目，此表格從略。*

## Post-Design Constitution Check

*Re-evaluated after Phase 1（`data-model.md`、`contracts/`、
`quickstart.md`）產出。*

設計階段的關鍵決策——(1) 達標判定公式不需讀取 `deuce_threshold`
（research.md #2，以 001 既有兩組預設值交叉驗證，非新引入的業務規則，
僅是既有規則的數學化簡）、(2) 控制板寫入端點僅接受
`control_panel_token`（research.md #3，落實 002 既有兩連結分離設計
之權限邊界，而非放寬或改變它）、(3) 管理頁與公開控制板共用服務函式但
不共用認證路徑（research.md #10，明確區分「業務邏輯共用」與原則 IV
禁止的「認證機制共用」兩個不同層級）、(4) 不新增資料表（research.md
#1，重用 architecture.md 既有的 Match/MatchResult 合併決策）——皆為在
不違反任何 FR 與既有 Constitution 判定的前提下確保正確性的實作細節，
未引入新的違反項目。對既有模組的擴充完全透過 003 已明確預留的兩個 hook
（`advance_court_after_match_ends`/`check_round_complete_and_maybe_auto
_advance`）銜接，未修改其簽章或既有行為，符合原則 VI。**Gate 結果維持
PASS，無需新增 Complexity Tracking 項目。**

## Assumptions

- 「即將登場」預告（`next_up`）與「場地目前比賽」（`current_match`）
  皆以 `MatchParticipant`/`ParticipantSummary` 呈現球員暱稱，不包含
  戰績/歷史對戰等衍生資訊（屬 005 spec 範圍）。
- 管理頁場地控制區塊之 UI 呈現方式（例如是否與既有 `manual-assign`
  區塊整合在同一頁面段落）留待 tasks.md/實作階段依既有 `admin-page`
  版面決定，本 plan 僅定義其 API 邊界。
- 「提前結束」確認彈窗沿用專案既有的二次確認 UX 慣例（`group-admin/
  shared/confirm-dialog.component.ts`，001/002/003 已建立並重複使用），
  本 feature 不新建獨立的確認元件。
