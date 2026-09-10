# Implementation Plan: 團內即時排行榜（強化既有戰績頁）

**Branch**: `main`（本專案未使用 per-feature git branch，延續既有慣例）| **Date**: 2026-09-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/018-group-leaderboard/spec.md`，
交叉比對 `/specs/005-member-view`（既有 `build_group_standings()`、
`GroupStandingsResponse`、`group-member-view` 內既有的 standings 分頁）與
`/specs/012-realtime-notifications`（`RealtimeService`、`ReconnectRefetchService`
之既有共用即時基礎設施，本 feature 直接沿用、不修改）。

## Summary

團內任一現役成員目前只能透過既有「戰績」分頁看到逐輪勝敗矩陣，看不出
「同團的人互相比較」誰排第幾——本 feature 強化這個既有頁面（`GET
/groups/{group_id}/standings` 端點與 `standings.component`），在既有
回應中新增 `rank`／`total_wins`／`total_losses` 三個欄位（依勝場數排序、
並列名次跳號、次要排序依加入時間），並在既有「比賽完成」的唯一發布點
上多發一則 `standings.updated` 群組廣播事件，讓正在檢視戰績頁的使用者
在比賽結束後數秒內自動看到最新排名，不需要手動重新整理。全程不新增
資料表、不新增獨立畫面/路由、不新增第三方套件——完全是既有元件與既有
即時基礎設施的疊加式強化。

## Technical Context

**Language/Version**：延續既有（後端 Python 3.12+；前端 TypeScript /
Angular 20+）。

**Primary Dependencies**：沿用既有 FastAPI/SQLAlchemy 堆疊與 Angular，
**不新增套件**——即時廣播沿用既有 Ably 整合（`app/core/realtime.py` 的
`publish()`/`group_notifications_channel()`；前端既有 `RealtimeService`/
`ReconnectRefetchService`，`012-realtime-notifications` 已在用同一套）。

**Storage**：PostgreSQL，**不新增資料表、不需要新 migration**——`rank`/
`total_wins`/`total_losses` 刻意設計為每次查詢當下重新計算的衍生值
（research.md 前言），沿用既有 `Match`/`MatchParticipant`/`RosterEntry`
表的唯讀查詢，只多加一個 `RosterEntry.status == "active"` 過濾條件。

**Testing**：pytest + pytest-asyncio（後端：`build_group_standings()`
擴充後的排序/並列跳號/離團排除之單元測試，`standings.updated` 事件之
整合測試——涵蓋「一般排序」「並列名次」「離團成員排除但對手戰績不受
影響」「abandoned 比賽不觸發事件」四種情境，比照既有測試慣例，MUST
皆有覆蓋）。Vitest（前端：`standings.component` 新增的排序渲染、自己
所在列標示、即時更新訂閱、reconnect-refetch 行為）。

**Target Platform**：延續既有（Docker on AWS ECS，本地 `docker-compose`）。

**Project Type**：Web application（monorepo，延續既有 `apps/api` +
`apps/web` 結構）。

**Performance Goals**：SC-002——比賽被判定完成後 2 秒內，正在檢視戰績頁
的使用者看到名次更新；SC-001——使用者打開戰績頁後 5 秒內找到自己的
名次，人工抽測，非嚴格自動化效能測試。

**Constraints**：FR-001——MUST 強化既有戰績頁，MUST NOT 另外新增一個
獨立的排行榜畫面或路由。FR-010——MUST NOT 因本次強化而改變既有的存取
層級。FR-012——MUST NOT 新增「連線中斷」提示元件（與 007-live-scoreboard
之要求刻意不同，比照 012-realtime-notifications）。

**Scale/Scope**：單團現役成員人數與既有戰績頁的既有規模假設相同（既有
無分頁機制已隱含既有的規模上限），不需要額外的規模考量。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | `MemberStandingRow` 新增 3 個型別明確的欄位（`rank: int`／`total_wins: int`／`total_losses: int`），前端 `MemberStandingRow` TypeScript 介面同步更新；`ruff`/`mypy --strict` blocking check；前端 TypeScript strict mode。 | PASS |
| II. 測試優先 | 排序/並列名次跳號演算法（research.md #6）與離團成員排除邏輯屬於使用者可觀察的核心呈現邏輯，MUST 有單元測試覆蓋一般排序、並列、離團排除、abandoned 比賽不觸發事件等情境。 | PASS（列入 tasks.md 強制項） |
| III. 即時性與資料一致性 | `standings.updated` 事件的發布點與既有 `_publish_match_ended()` 綁在同一個「比賽完成」交易之後（research.md #1），沿用既有「先 commit 再 publish」模式，不引入新的中繼狀態。 | PASS |
| IV. 權限與安全 | 沿用既有 `resolve_active_roster_membership`，與既有戰績頁端點授權模式完全一致，未新增或放寬任何權限語意。 | PASS |
| V. UX 一致性（破壞性操作二次確認） | 本功能純唯讀、無任何破壞性操作。 | 不適用 |
| VI. 可維護性 | 排序/並列名次計算集中在 `build_group_standings()` 內一次算好（research.md #2），前端不重複實作排序邏輯；即時訂閱與斷線重連直接重用既有 `RealtimeService`/`ReconnectRefetchService`（research.md #4/#5），不新增重複的抽象層。 | PASS |
| VII. 無障礙與行動裝置優先 | 使用者自己所在列 MUST 以圖示/文字（而非純顏色）與其他列區隔（spec.md FR-011），比照既有 `status-badge` 圖示＋文字並用慣例。 | PASS（前端落實於 tasks.md 展開） |
| VIII. i18n 與時區 | 新增的「尚無比賽紀錄」等文字集中於語系檔，不寫死中文；不涉及時區相關資料。 | PASS |
| IX. 可攜性與可部署性 | 不新增任何基礎設施、不新增 migration、不新增前後端第三方套件（research.md 前言）。 | PASS |
| X. 即時同步的可信來源 | 排序/並列名次計算全部在後端 `build_group_standings()` 完成，前端純粹渲染伺服器回傳的 `rank` 欄位，MUST NOT 在前端重新計算排序（research.md #2）；`standings.updated` payload 刻意不帶排名結果，訂閱端 MUST 重新呼叫既有端點取得最新狀態（research.md #1）。 | PASS |
| XI. 防機器人/防濫用 | 既有端點沿用既有 `resolve_active_roster_membership` 保護，不建立任何新的公開資源，不在原則 XI 之 Turnstile 強制範圍內。 | PASS（明確排除項，非違反） |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/018-group-leaderboard/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/
│   ├── ably-events.md
│   └── standings-api.md
└── tasks.md             # Phase 2 output (/speckit-tasks command — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
apps/api/
├── app/domains/group/
│   ├── schemas.py       # MemberStandingRow + rank/total_wins/total_losses
│   ├── service.py       # build_group_standings() 擴充：現役過濾 + 排序 + 並列名次
│   └── router.py        # GET /{group_id}/standings 既有端點，回應形狀擴充（無新端點）
├── app/domains/schedule/
│   └── service.py       # _publish_match_ended() 新增 standings.updated 群組廣播
└── tests/
    ├── unit/domains/group/test_group_standings_ranking.py       # 新增
    └── integration/test_standings_realtime_flow.py              # 新增

apps/web/
├── src/app/core/api/
│   └── group-member-view.models.ts          # MemberStandingRow + rank/total_wins/total_losses
└── src/app/features/group-member-view/standings/
    ├── standings.component.ts               # + 自己所在列判斷、即時訂閱、reconnect-refetch
    ├── standings.component.html             # + rank 欄位、自己所在列標示
    ├── standings.component.scss             # + rank/自己列樣式
    └── standings.component.spec.ts          # 新增/擴充
```

**Structure Decision**：延續既有 monorepo 結構（`apps/api` + `apps/web`）。
後端邏輯全部落在既有 `group` domain（既有戰績頁端點同層）與既有
`schedule` domain（既有比賽完成發布點）；前端邏輯全部落在既有
`group-member-view/standings` 元件——不新增 domain、不新增 Angular
feature 模組、不新增路由（research.md 前言，spec.md FR-001）。

## Complexity Tracking

*Gate 無違反項目，本節無需填寫。*
