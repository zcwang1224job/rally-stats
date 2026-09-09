# Implementation Plan: 固定搭檔循環賽——手動配對後，剩餘未配對者自動隨機配對

**Branch**: `main`（本專案未使用 per-feature git branch，延續既有慣例）| **Date**: 2026-09-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/017-fixed-partner-autofill/spec.md`，交叉比對 `/specs/011-round-robin-scheduling/`（`Partnership`、`partner_source`、`_get_active_partnership_teams()`、`manual_partnership_reassign()`、既有搭檔設定畫面）與稍早的排點側別修復（`round_robin_pairs()` 的 `start_swapped` 參數，本 feature 直接沿用、不修改）。

## Summary

「固定搭檔」比賽模式、「手動配對」來源下，目前沒有正式搭檔的現役成員會
在產生賽程時被悄悄排除在外。本 feature 新增一個純運算端點
`POST /groups/{group_id}/partnerships/random-preview`，讓管理員可以在
搭檔設定畫面上主動預覽「剩下的人」會被怎麼隨機配對、並用既有「點兩人
互換」的操作方式調整——這份暫時配對全程留在前端，不寫入 `partnerships`
資料表。既有 `POST /groups/{group_id}/next-round` 新增一個可選的
`temporary_pairings` 請求欄位：若管理員預覽/調整過，直接採用該結果；
不論有沒有預覽過，只要產生賽程當下仍有未配對成員，後端 MUST 自動補齊
隨機配對，確保賽程一定涵蓋所有現役成員。「自動配對」模式完全不受影響。
全程不新增資料表、不新增第三方套件。

## Technical Context

**Language/Version**：延續既有（後端 Python 3.12+；前端 TypeScript /
Angular 20+）。

**Primary Dependencies**：沿用既有 FastAPI/SQLAlchemy 堆疊與 Angular，
**不新增套件**——隨機配對僅用 Python 標準庫 `random.shuffle`（既有
`_shuffle_round_match_order()` 已在用，`schedule/service.py`）。

**Storage**：PostgreSQL，**不新增資料表、不需要新 migration**——暫時配對
刻意設計為全程不落地（research.md #1），沿用既有 `partnerships`／
`roster_entries` 表的唯讀查詢。

**Testing**：pytest + pytest-asyncio（後端：新增
`random_pair_units()` 之隨機配對正確性/涵蓋完整性單元測試、
`preview_random_partner_pairing()` 的模式防呆與計算正確性、
`_generate_fixed_partner_matches()` 三段聯集邏輯之單元/整合測試——含
「完全沒手動配對」「部分配對」「全部配對」「暫時配對過期重新驗證」四種
情境，比照既有排點演算法之測試慣例，MUST 皆有覆蓋，憲章原則 II 明列
「輪替（排點）演算法」為核心領域邏輯，不可省略）。Vitest（前端：搭檔
設定畫面新增的預覽/調整互動、暫時配對與正式搭檔的視覺區隔）。

**Target Platform**：延續既有（Docker on AWS ECS，本地 `docker-compose`）。

**Project Type**：Web application（monorepo，延續既有 `apps/api` +
`apps/web` 結構）。

**Performance Goals**：SC-002——管理員完成想要的手動配對後，不需要為
每一位剩餘未配對成員逐一操作即可讓賽程涵蓋所有人，人工抽測，非嚴格
自動化效能測試。

**Constraints**：FR-004——暫時配對 MUST NOT 寫入 `partnerships` 資料表，
落地測試時 MUST 明確驗證正式搭檔清單不受污染（quickstart.md 情境 2/3
步驟）。FR-005——「自動配對」模式下新端點/新請求欄位 MUST 被拒絕/忽略，
既有呼叫端零行為變動。FR-007——賽程產生 MUST 直接採用驗證通過的
`temporary_pairings`，MUST NOT 另外重新隨機配對一次。

**Scale/Scope**：單團現役成員人數與既有「固定搭檔」機制的既有規模假設
相同（既有偶數人數檢查已覆蓋；未配對人數必為偶數，見 spec.md Edge
Cases），不需要分頁或額外的規模考量。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | 新增 Pydantic schema（`TemporaryPairing`、`TemporaryPairingsResponse`、`TemporaryPairingInput`、`NextRoundRequest`）涵蓋所有請求/回應欄位；`ruff`/`mypy --strict` blocking check；前端 TypeScript strict mode，新互動的型別直接對應後端 schema。 | PASS |
| II. 測試優先 | 本功能直接觸及憲章明列的核心領域邏輯「輪替（排點）演算法」，MUST 有單元測試覆蓋 `random_pair_units()` 之隨機配對正確性、`_generate_fixed_partner_matches()` 三段聯集（正式搭檔／驗證通過的暫時配對／自動補齊）邏輯之各種情境，以及至少一條整合測試涵蓋「部分手動配對→預覽調整→產生賽程」全流程。 | PASS（列入 tasks.md 強制項） |
| III. 即時性與資料一致性 | `temporary_pairings` 的驗證與採用，與「產生賽程」這個既有的、單一交易內完成的動作綁在一起（research.md #2），不引入任何跨請求的中繼狀態，維持「伺服器為唯一可信來源」與既有交易邊界一致；不涉及即時比分同步。 | PASS |
| IV. 權限與安全 | 新端點沿用既有 `require_admin`，與既有搭檔相關端點授權模式完全一致，未新增或放寬任何權限語意。 | PASS |
| V. UX 一致性（破壞性操作二次確認） | 隨機配對預覽本身可重複觸發、不具破壞性，不需要額外確認流程；「產生下一輪賽程」既有的確認對話框（既有既有行為）不變。 | 不適用（無新增破壞性操作） |
| VI. 可維護性 | 新增的 `random_pair_units()` 為獨立純函式，供預覽端點與賽程產生的自動補齊邏輯共用同一套隨機邏輯（research.md #3）；暫時配對狀態全程留在前端父子元件之間，不新增不必要的 service 層或資料表（research.md #1/#5）。 | PASS |
| VII. 無障礙與行動裝置優先 | 暫時配對 MUST 以圖示/文字（而非純顏色）與正式搭檔在畫面上明確區隔（spec.md FR-008，US2 驗收情境 1），比照既有 `status-badge` 圖示＋文字並用慣例。 | PASS（前端落實於 tasks.md 展開） |
| VIII. i18n 與時區 | 新增 `PARTNER_SOURCE_MISMATCH` 錯誤代碼，前端依既有 `errors.<code>` 慣例對應語系檔；新增的按鈕/暫時配對標示文字集中於語系檔，不寫死中文。 | PASS |
| IX. 可攜性與可部署性 | 不新增任何基礎設施、不新增 migration、不新增前後端第三方套件（research.md #1 明確拒絕新增暫存資料表/session 層）。 | PASS |
| X. 即時同步的可信來源 | `temporary_pairings` 的驗證與最終採用，全程在後端「產生下一輪賽程」這個既有的、單一伺服器端交易中完成，前端只負責組出請求內容，不繞過後端直接決定賽程結果（research.md #2）。 | PASS |
| XI. 防機器人/防濫用 | 新端點為既有 `require_admin` 保護下的操作，不建立任何新的公開資源，不在原則 XI 之 Turnstile 強制範圍內。 | PASS（明確排除項，非違反） |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/017-fixed-partner-autofill/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/
│   └── fixed-partner-autofill-api.md
└── tasks.md             # Phase 2 output (/speckit-tasks command — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
apps/api/
├── app/domains/schedule/
│   ├── algorithms.py    # + random_pair_units()（純函式，research.md #3）
│   ├── schemas.py        # + TemporaryPairing, TemporaryPairingsResponse,
│   │                      #   TemporaryPairingInput, NextRoundRequest
│   ├── service.py        # + preview_random_partner_pairing()
│   │                      #   generate_next_round() 新增可選參數 temporary_pairings
│   │                      #   _generate_fixed_partner_matches() 三段聯集邏輯擴充
│   └── router.py         # + POST /groups/{group_id}/partnerships/random-preview
│                          #   POST /groups/{group_id}/next-round 接受可選 body
└── tests/
    ├── unit/domains/schedule/test_random_pair_units.py           # 新增
    ├── unit/domains/schedule/test_fixed_partner_autofill.py      # 新增（三段聯集邏輯）
    ├── contract/test_partnerships_random_preview.py              # 新增
    └── integration/test_fixed_partner_autofill_flow.py           # 新增

apps/web/
└── src/app/features/group-admin/schedule-management/
    ├── schedule.models.ts              # + TemporaryPairing, TemporaryPairingsResponse
    ├── schedule.service.ts             # + previewRandomPairing()
    │                                    #   nextRound() 新增可選 temporaryPairings 參數
    ├── partnership-settings.component.ts/.html/.scss
    │                                    # + 「剩下的人隨機配對」操作、暫時配對呈現與調整互動、
    │                                    #   @Output() 往父層回報目前暫時配對狀態
    └── admin-page.component.ts/.html   # + 持有目前暫時配對狀態、confirmNextRound() 帶入
```

**Structure Decision**：延續既有 monorepo 結構（`apps/api` + `apps/web`）。
後端邏輯全部落在既有 `schedule` domain（與既有搭檔相關端點、排點演算法
同層），前端邏輯全部落在既有 `schedule-management` 功能區塊——不新增
domain、不新增 Angular feature 模組（research.md #5）。

## Complexity Tracking

*Gate 無違反項目，本節無需填寫。*
