# Implementation Plan: 我的團最終團隊排名

**Branch**: `main`（本專案未使用 per-feature git branch，延續既有慣例）| **Date**: 2026-09-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/019-group-final-standings/spec.md`，
交叉比對 `/specs/014-member-groups-history`（既有 `GET
/members/me/groups/{group_id}/history`、`MemberGroupHistoryResponse`、
`group-history.component`）與 `/specs/018-group-leaderboard`（既有
`build_group_standings()` 的排序/並列名次演算法，本 feature 重用同一套
規則但涵蓋範圍不同，見 research.md #1）。

## Summary

會員從「我的團」點進一個團的歷史頁面時，目前只看得到自己的個人統計與一份
全團比賽清單，看不到「全團排名」——018-group-leaderboard 已經強化過的排行
榜，只有目前仍是現役成員、且持有現役 session（會員 token／訪客 token）的人
才看得到，一旦離開、被踢除，或整個團解散，就再也看不到。本 feature 在既有
`GET /members/me/groups/{group_id}/history` 回應中新增 `final_standings`
欄位，重用 018 已定義的「依勝場數排序＋並列名次跳號＋加入時間為次要排序」
演算法（抽出共用函式，不重寫一份），但涵蓋範圍改為「該團所有曾參與者」
（含已離開／被踢除／訪客，同一位會員的多筆歷史 `RosterEntry` 依
`member_id` 合併為一列），呈現在既有 `group-history.component` 頁面上
新增的一個區塊；自己所在列由伺服器直接算好 `is_self` 欄位（此頁面走會員
JWT 登入，無法比照既有即時戰績頁「前端比對 roster session」的做法）。
全程不新增資料表、不新增獨立畫面/路由、不新增即時廣播、不新增第三方套件。

## Technical Context

**Language/Version**：延續既有（後端 Python 3.12+；前端 TypeScript /
Angular 20+）。

**Primary Dependencies**：沿用既有 FastAPI/SQLAlchemy 堆疊與 Angular，
**不新增套件**。

**Storage**：PostgreSQL，**不新增資料表、不需要新 migration**——
`final_standings` 與 018 的 `rank`/`total_wins`/`total_losses` 一樣，是
每次呼叫端點當下重新計算的衍生值，沿用既有 `Match`/`MatchParticipant`/
`RosterEntry` 表的唯讀查詢。

**Testing**：pytest + pytest-asyncio（後端：新函式 `build_group_final_standings()`
的單元測試——涵蓋「一般排序」「並列名次」「含已離開/被踢除/訪客」「已捨棄
比賽不計入」「固定搭檔以個人為單位」「完全無比賽的空狀態」「同一會員多次
退出又重新加入，合併為一列且統計加總全部期間」「`is_self` 正確標示查看者
自己那一列」八種情境；擴充既有 `test_member_group_history.py`（unit）、
`test_member_groups_history_endpoints.py`（contract）、
`test_member_groups_history_flow.py`（integration）驗證 `final_standings`
欄位與既有 `my_stats`/`matches` 並存、存取權限不變）。Vitest（前端：
`group-history.component` 新增區塊的排序渲染、`is_self` 標示、尚無比賽
紀錄文字、已離開/已被踢除標籤）。

**Target Platform**：延續既有（Docker on AWS ECS，本地 `docker-compose`）。

**Project Type**：Web application（monorepo，延續既有 `apps/api` +
`apps/web` 結構）。

**Performance Goals**：SC-001——會員點進任一團的歷史頁面後 3 秒內看到最終
團隊排名（與既有頁面載入時間屬同一數量級，新增查詢為單次唯讀彙總，非
逐輪迭代）。

**Constraints**：FR-001——MUST 疊加在既有「我的團」歷史頁面/端點，MUST NOT
新增獨立畫面/路由。FR-010——存取權限 MUST 沿用既有 `verify_ever_group_member`，
MUST NOT 採用即時戰績頁「僅限現役」的較嚴格規則。FR-012——MUST NOT 新增
即時推播機制，快照式呈現即可。

**Scale/Scope**：單團「曾參與者」總數（含歷史上已離開/被踢除者）可能略多
於現役人數，但仍在既有「我的團」/戰績頁的既有規模假設內（無分頁機制的
既有前提維持不變，spec.md Assumptions）。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | 新增 `FinalStandingRow`（`group/schemas.py`）與對應 TypeScript 介面（`group-member-view.models.ts`），欄位型別明確（`rank: int`／`total_matches: int`／`total_wins: int`／`total_losses: int`／`current_status: Literal[...]`／`is_self: bool`）；`ruff`/`mypy --strict`/前端 strict mode 皆為 blocking check。 | PASS |
| II. 測試優先 | 排序/並列名次跳號、涵蓋範圍（含離團/訪客）、已捨棄比賽排除、固定搭檔個人單位計算，皆屬使用者可觀察的核心呈現邏輯，MUST 有單元測試覆蓋（research.md #1，列入 tasks.md 強制項）。 | PASS |
| III. 即時性與資料一致性 | 不涉及即時廣播；已捨棄（abandoned）比賽 MUST NOT 計入任何人的最終戰績，沿用既有 `_completed_matches_query()`（僅 `status == "completed"`）的既定過濾規則，未新增例外。 | PASS |
| IV. 權限與安全 | 沿用既有 `verify_ever_group_member`，與既有「我的團」歷史頁面端點授權模式完全一致，未新增或放寬任何權限語意（research.md #4）。 | PASS |
| V. UX 一致性（破壞性操作二次確認） | 本功能純唯讀、無任何破壞性操作。 | 不適用 |
| VI. 可維護性 | 排序/並列名次演算法抽出為共用函式 `_assign_standard_competition_ranks()`，供既有 `build_group_standings()`（018）與本 feature 新增的 `build_group_final_standings()` 共用，不重寫第二份排名邏輯（research.md #2）。 | PASS |
| VII. 無障礙與行動裝置優先 | 自己所在列（由伺服器算好的 `is_self`）MUST 以圖示/文字（而非純顏色）與其他列區隔（spec.md FR-011），沿用既有 `status-badge` 圖示＋文字並用慣例；已離開/已被踢除標籤同樣圖示＋文字並用。 | PASS |
| VIII. i18n 與時區 | 新增文字（區塊標題、「已被踢除」標籤等）集中於語系檔，重用既有 `groupMemberView.standings.*` 系列 key，缺口處新增 key（research.md #5）；不涉及時區相關資料。 | PASS |
| IX. 可攜性與可部署性 | 不新增任何基礎設施、不新增 migration、不新增前後端第三方套件。 | PASS |
| X. 即時同步的可信來源 | 排序/名次計算，以及「這是不是我自己」（`is_self`）皆全部在後端 `build_group_final_standings()` 完成，前端純粹渲染伺服器回傳的欄位，MUST NOT 在前端重新計算排序或自行比對任何 ID（research.md #4）。 | PASS |
| XI. 防機器人/防濫用 | 既有端點沿用既有 `require_member` + `verify_ever_group_member` 保護，不建立任何新的公開資源，不在原則 XI 之 Turnstile 強制範圍內。 | PASS（明確排除項，非違反） |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/019-group-final-standings/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/
│   └── final-standings-api.md
└── tasks.md             # Phase 2 output (/speckit-tasks command — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
apps/api/
├── app/domains/group/
│   ├── schemas.py       # + FinalStandingRow
│   └── service.py       # + build_group_final_standings()；抽出共用
│                         #   _assign_standard_competition_ranks()，
│                         #   build_group_standings() 改為呼叫它（無行為變更）
├── app/domains/member/
│   ├── schemas.py       # MemberGroupHistoryResponse + final_standings 欄位
│   └── service.py       # get_member_group_history() 呼叫 build_group_final_standings()
└── tests/
    ├── unit/domains/group/test_group_final_standings.py       # 新增
    ├── unit/domains/member/test_member_group_history.py       # 擴充
    ├── contract/test_member_groups_history_endpoints.py       # 擴充
    └── integration/test_member_groups_history_flow.py         # 擴充

apps/web/
├── src/app/core/api/
│   ├── group-member-view.models.ts   # + FinalStandingRow
│   └── friend.models.ts              # MemberGroupHistoryResponse + final_standings
├── src/app/features/member/my-groups/group-history/
│   ├── group-history.component.ts    # + 最終團隊排名區塊之渲染邏輯、自己所在列判斷
│   ├── group-history.component.html  # + 最終團隊排名表格
│   ├── group-history.component.scss  # + 對應樣式
│   └── group-history.component.spec.ts
└── src/assets/i18n/zh-TW.json         # + 缺口 i18n key（research.md #5）
```

**Structure Decision**：延續既有 monorepo 結構（`apps/api` + `apps/web`）。
後端邏輯集中在既有 `group` domain（新函式與既有 `build_group_standings()`
同層、共用同一個排名演算法）與既有 `member` domain（既有「我的團」歷史
端點回應擴充）；前端邏輯全部落在既有 `member/my-groups/group-history`
元件——不新增 domain、不新增 Angular feature 模組、不新增路由（spec.md
FR-001）。

## Complexity Tracking

*Gate 無違反項目，本節無需填寫。*
