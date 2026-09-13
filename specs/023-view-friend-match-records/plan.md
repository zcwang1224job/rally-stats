# Implementation Plan: 好友戰績檢視入口

**Branch**: `main`（本專案未使用 per-feature git branch，延續既有慣例）| **Date**: 2026-09-14 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/023-view-friend-match-records/spec.md`，
交叉比對 `/specs/022-member-personal-settings`（既有
`GET /members/{member_id}/match-records`、
`GET /members/{member_id}/match-records/{match_id}` 兩支端點——好友戰績
檢視的授權矩陣、`MemberMatchRecordsResponse`/`MatchRecordDetailResponse`
回應形狀皆已在該 feature 完整實作並測試）、`/specs/016-match-score-timeline`
（既有純呈現元件 `MatchRecordDetailDialogComponent`——不注入任何 service，
呼叫端自行取資料餵入，本 feature 直接重用）、`/specs/006-member-friends`
（既有 `GET /friends`、`FriendSummary.member_id`）。

## Summary

022 已經把「好友檢視戰績」需要的**後端授權邏輯與資料形狀**完整做好——
`GET /members/{member_id}/match-records[/{match_id}]` 兩支端點已存在、已
測試，回應形狀與既有「我的戰績」端點完全相同（`MemberMatchRecordsResponse`
/`MatchRecordDetailResponse`），只是當時沒有任何前端畫面呼叫它們。本
feature 純粹是**前端**工作：

1. 好友列表每一列新增「檢視戰績」連結，導向新路由
   `/friends/:memberId/match-records`（沿用既有 `FriendSummary.member_id`，
   不需要後端任何改動）。
2. 新增一個路由層級元件，呼叫 022 既有端點，顯示對戰紀錄列表（新到舊、
   分頁）與彙總統計（總場次/勝/敗/勝率）——結構上是既有
   `match-history.component`（「我的戰績」頁）的精簡版：**不含**進階篩選
   表單、各輪勝率趨勢圖、對戰對象排行榜（spec.md Assumptions 已定案排除，
   research.md #1）。
3. 點擊任一場比賽時，重用既有 `MatchRecordDetailDialogComponent`（純呈現
   元件，本來就是設計成「呼叫端自己取資料餵入」，不需要為此新增任何
   dialog 元件）。
4. 當目標好友已關閉分享（`MATCH_RECORDS_PRIVATE`）、已非好友關係
   （`FRIENDSHIP_REQUIRED`）、或目標不存在（`MEMBER_NOT_FOUND`）時，頁面
   MUST 呈現既有錯誤碼→i18n key 機制轉譯出的明確文字，而非空白頁。

全程**不新增/修改任何後端程式碼、不新增 migration、不新增 API 端點**——
純粹是把 022 已經做好但沒有 UI 入口的能力接上畫面。

## Technical Context

**Language/Version**：延續既有（前端 TypeScript / Angular 20+）；本
feature 不涉及後端，Python/FastAPI 不變動。

**Primary Dependencies**：沿用既有 Angular 堆疊，**不新增套件**、**不
新增後端依賴**。

**Storage**：不涉及——不新增資料表、不需要 migration（022 已建立所有必要
欄位）。

**Testing**：Vitest（前端）：好友列表新增的「檢視戰績」連結渲染與
`routerLink` 正確性；新元件載入好友戰績（含分頁）、彙總統計顯示、點擊
單場比賽開啟既有 detail dialog、三種拒絕情境
（`FRIENDSHIP_REQUIRED`/`MATCH_RECORDS_PRIVATE`/`MEMBER_NOT_FOUND`）分別
顯示對應錯誤文字、空狀態（好友尚無對戰紀錄）。後端**不新增測試**——
022 既有的 `test_member_personal_settings.py`（contract）與
`test_personal_settings.py`（unit）已完整覆蓋這兩支端點的授權矩陣與資料
形狀，本 feature 純粹消費既有、已驗證正確的端點，重複測試後端行為沒有
增量價值。

**Target Platform**：延續既有（Docker on AWS ECS，本地 `docker-compose`）；
本 feature 僅需重建/重啟 `frontend` 容器。

**Project Type**：Web application（monorepo）；本 feature 僅觸及
`apps/web`。

**Performance Goals**：SC-001（2 秒內看到內容或明確提示）——比照既有
系列 feature 對這類「使用者體感時間」成功標準的處理慣例，人工抽測。

**Constraints**：FR-007/FR-008——資格檢查 MUST 以請求當下的伺服器判斷
為準，前端 MUST NOT 自行快取或推測「是否還有權限」，每次進入頁面/換頁
皆重新呼叫既有端點，忠實呈現伺服器當下的回應（含拒絕）。FR-011——
MUST NOT 新增任何通知邏輯。

**Scale/Scope**：不影響既有規模假設——沿用 022 既有端點的效能特性
（跨團彙總計算於後端進行，前端僅負責呈現）。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | 新元件的 TS 型別完全沿用既有 `MemberMatchRecordsResponse`/`MatchRecordDetailResponse`/`MemberMatchRecordSummary`（`group-member-view.models.ts`），不新增/修改任何型別定義；`tsc --strict`/ESLint 皆為 blocking check。 | PASS |
| II. 測試優先 | 新增的前端渲染/導覽/錯誤呈現邏輯屬於使用者可觀察行為，MUST 有 Vitest 覆蓋（列入 tasks.md 強制項）；後端授權矩陣已由 022 完整覆蓋，本 feature 不重複測試已驗證正確的後端行為。 | PASS |
| III. 即時性與資料一致性 | 本 feature 不涉及計分板/賽程即時狀態，不觸及 Ably；每次進入頁面/換頁皆重新呼叫伺服器（Constraints 段落），不使用前端快取的舊授權判斷結果。 | PASS |
| IV. 權限與安全 | 完全沿用 022 既有 `require_verified_member` + 好友關係 + 隱私設定三層授權，本 feature 不新增、不放寬、不重新實作任何權限判斷邏輯——前端只負責忠實呈現後端回應。 | PASS |
| V. UX 一致性（破壞性操作二次確認） | 「檢視戰績」為唯讀、非破壞性操作，不適用本原則。 | 不適用 |
| VI. 可維護性 | 直接重用既有 `MatchRecordDetailDialogComponent`（設計上本來就是給任何呼叫端重用的純呈現元件）與既有 `AuthService` 既有的 API 呼叫慣例（新增兩個方法，比照 `getMatchRecords()`/`getMatchRecordDetail()` 的既有寫法），不建立平行的一套邏輯。 | PASS |
| VII. 無障礙與行動裝置優先 | 新頁面沿用既有 `match-history`/`friend-list` 頁面的既有版面慣例（card、響應式、觸控目標），不引入新的互動模式。 | PASS |
| VIII. i18n 與時區 | 新增顯示文字集中於 `zh-TW.json`；新增錯誤碼（`FRIENDSHIP_REQUIRED`/`MATCH_RECORDS_PRIVATE`/`MEMBER_NOT_FOUND`）皆已在 022 註冊過對應 i18n key，本 feature 直接沿用，不重複定義；比賽時間顯示沿用既有 `MatchRecordDetailDialogComponent`/`match-history` 既有的時間呈現方式，不新增時區邏輯。 | PASS |
| IX. 可攜性與可部署性 | 不新增任何套件或基礎設施，僅前端程式碼變動。 | PASS |
| X. 即時同步的可信來源 | 「是否有權限查看」的判斷結果 MUST NOT 被前端快取延用——每次請求都重新呼叫既有端點，由後端當下判斷（FR-008，Constraints 段落）。 | PASS |
| XI. 防機器人/防濫用 | 本 feature 不新增任何公開/匿名端點，所有請求皆需登入會員身份，不在原則 XI 範疇內。 | PASS（不適用） |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/023-view-friend-match-records/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/
│   └── friend-match-records-ui.md
└── tasks.md             # Phase 2 output (/speckit-tasks command — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
apps/web/
├── src/app/app.routes.ts
│                         # + 'friends/:memberId/match-records' lazy route
├── src/app/features/friends/
│   ├── friend-list/
│   │   ├── friend-list.component.html
│   │   │                 # + 每列新增「檢視戰績」連結（routerLink，帶
│   │   │                 #   memberId + nickname query param，research.md #2）
│   │   └── friend-list.component.spec.ts
│   │                     # + routerLink 指向與 queryParams 正確性測試
│   └── friend-match-records/            # 新增
│       ├── friend-match-records.component.ts
│       │                 # 精簡版 match-history：載入
│       │                 #   AuthService.getFriendMatchRecords()、分頁、
│       │                 #   彙總統計卡片、點擊開啟既有
│       │                 #   MatchRecordDetailDialogComponent；三種拒絕
│       │                 #   錯誤碼→現成 i18n key 呈現
│       ├── friend-match-records.component.html
│       ├── friend-match-records.component.scss
│       └── friend-match-records.component.spec.ts
├── src/app/features/auth/auth.service.ts
│                         # + getFriendMatchRecords(memberId, page),
│                         #   getFriendMatchRecordDetail(memberId, matchId)
└── src/assets/i18n/zh-TW.json
                          # + friends.viewMatchRecords 等新增文字
                          #   （錯誤碼字串已在 022 註冊，沿用不重複）
```

**Structure Decision**：延續既有 `apps/web` feature-based 結構，新元件放在
`features/friends/friend-match-records/`（與既有 `friend-list`/
`friend-add`/`friend-requests` 同一層級，皆屬好友功能群組），不建立新的
頂層 feature 目錄。後端完全不變動，`apps/api` 沒有任何改動。

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

無違反項目，本表格從缺。
