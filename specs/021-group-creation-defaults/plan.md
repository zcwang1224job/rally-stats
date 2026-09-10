# Implementation Plan: 開團流程優化——合理預設值與自動預設場地

**Branch**: `main`（本專案未使用 per-feature git branch，延續既有慣例）| **Date**: 2026-09-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/021-group-creation-defaults/spec.md`，
交叉比對 `/specs/001-create-manage-group`（既有 `create_group()`、
`CreateGroupRequest`）與 `/specs/002-court-management`（既有
`PATCH /courts/{court_id}` 更名端點、`rename_court()`、`CourtManagementService
.renameCourt()`——本 feature 沿用其既有機制，補上前端入口與測試覆蓋）。

## Summary

開團表單目前「團名」為必填、比賽模式初始值是雙打；建團完成後團內完全沒有
球場，團長必須自己先手動新增一個才能開始排點/計分；球場更名的後端能力
（`PATCH /courts/{court_id}`）與對應的前端 service 方法其實都已經存在，
只是從未被任何畫面呼叫過，也從未被任何測試覆蓋過。本 feature：

1. 讓「團名」欄位可留空，留空時由後端依建立者暱稱自動組成預設團名
   「{暱稱}的羽球團」；比賽模式表單初始值由雙打改為單打（人數上限/
   排程機制的表單初始值本來就已經是 4 人/公平輪替，不需改動）。
2. 在既有 `create_group()` 的同一個交易內，額外建立一筆名為「球場一」
   的球場，與團的建立/失敗共享同一個原子性。
3. 在既有球場管理畫面補上「重新命名」的操作入口，串接既有已存在但從未
   使用過的更名端點；順帶補齊這條路徑原本完全缺少的單元/契約測試。

全程不新增資料表、不需要新的 migration、不新增第三方套件。

## Technical Context

**Language/Version**：延續既有（後端 Python 3.12+；前端 TypeScript /
Angular 20+）。

**Primary Dependencies**：沿用既有 FastAPI/SQLAlchemy 堆疊與 Angular，
**不新增套件**——球場自動建立沿用既有 `Court` model 與既有
`group_notifications_channel`/`publish()` 即時廣播基礎設施（沿用
`create_court()` 既有發布的 `court.added` 事件形狀）。

**Storage**：PostgreSQL，**不新增資料表、不需要新 migration**——團名
預設值是請求驗證/服務層的衍生邏輯；自動建立的球場沿用既有 `Court` 表
schema（含既有 `ux_courts_group_name_active` 部分唯一索引），不新增
欄位。

**Testing**：pytest + pytest-asyncio（後端：`CreateGroupRequest.name`
留空/純空白時的驗證行為單元測試——**既有 `test_blank_name_rejected`
的斷言方向本身被反轉**（純空白由「拒絕」改為「接受並正規化為
`None`」，而非單純新增測試，需特別留意修改時機）；`create_group()`
自動帶入預設團名、
自動建立「球場一」、失敗時不留下孤兒球場之單元測試；契約測試涵蓋
`POST /groups` 團名留空情境。**`rename_court()` 與
`PATCH /courts/{court_id}` 目前完全沒有任何既有測試**——本 feature 一併
補上單元測試（含 `COURT_NAME_ALREADY_EXISTS`／`COURT_DELETED`／同名可
成功更新自己等情境）與契約測試）。Vitest（前端：`create-group.component`
團名留空可送出、比賽模式初始值為單打；`court-list.component` 新增的
重新命名操作——成功、名稱重複錯誤、取消）。

**Target Platform**：延續既有（Docker on AWS ECS，本地 `docker-compose`）。

**Project Type**：Web application（monorepo，延續既有 `apps/api` +
`apps/web` 結構）。

**Performance Goals**：SC-001——使用者只填必要欄位、完全不觸碰團名與
進階選項，15 秒內完成建團，人工抽測，非嚴格自動化效能測試（比照既有
系列 feature 對這類「使用者體感時間」成功標準的處理慣例）。

**Constraints**：FR-007——球場建立 MUST 與團建立同一個交易，開團失敗時
MUST NOT 留下孤兒球場。FR-008——自動建立的「球場一」MUST NOT 有任何
特殊限制，與手動新增球場的既有能力/生命週期完全一致。FR-010——更名
MUST NOT 影響既有計分板/控制板連結（沿用既有 `rename_court()` 本來就
只更新 `name` 欄位的既定行為，不涉及 token 欄位）。

**Scale/Scope**：不影響既有規模假設——每團固定只多一筆球場資料，更名
操作頻率與既有新增/刪除球場同一數量級。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | `CreateGroupRequest.name` 型別由 `str` 改為 `str \| None`，對應前端表單型別調整；不新增其他型別；`ruff`/`mypy --strict`/前端 strict mode 皆為 blocking check。 | PASS |
| II. 測試優先 | 團名預設值計算、自動建立球場、球場更名（含既有完全缺乏測試的 `rename_court()`／`PATCH /courts/{court_id}`）皆屬使用者可觀察的核心行為，MUST 有單元/契約/前端測試覆蓋（列入 tasks.md 強制項）。 | PASS |
| III. 即時性與資料一致性 | 自動建立的球場沿用既有 `court.added` 即時事件發布時機與 payload 形狀（research.md #2），與手動新增球場的既有行為一致，不引入新的中繼狀態。 | PASS |
| IV. 權限與安全 | 球場更名沿用既有 `_admin_court`（管理 PIN 驗證後的 admin_token）授權，未新增或放寬任何權限語意；自動建立球場發生在既有 `create_group()` 交易內，不涉及額外的權限判斷。 | PASS |
| V. UX 一致性（破壞性操作二次確認） | 更名為非破壞性、可逆操作（沿用既有「重新命名」語意，隨時可再次更名回原名），比照既有新增球場流程不需二次確認；不適用本原則的破壞性操作範疇。 | 不適用 |
| VI. 可維護性 | 自動建立球場直接沿用既有 `Court` model 與既有 `court.added` 事件 payload 形狀，不另外設計一套平行的建立邏輯；前端重新命名沿用既有 `CourtManagementService.renameCourt()`（已存在，未被使用），不新增重複的 API 呼叫邏輯。 | PASS |
| VII. 無障礙與行動裝置優先 | 重新命名操作為標準表單輸入＋按鈕，沿用既有新增球場表單的既有輸入/驗證/錯誤提示樣式慣例，不引入新的互動模式。 | PASS |
| VIII. i18n 與時區 | 新增文字（團名留空提示、重新命名按鈕/表單文字）集中於語系檔；`COURT_NAME_ALREADY_EXISTS`／`COURT_DELETED`／`COURT_NOT_FOUND` 既有錯誤碼字串直接沿用；`createGroup.nameRequired` 因欄位不再必填而不再使用，予以移除而非保留成孤兒字串。不涉及時區相關資料。 | PASS |
| IX. 可攜性與可部署性 | 不新增任何基礎設施、不新增 migration、不新增前後端第三方套件。 | PASS |
| X. 即時同步的可信來源 | 預設團名的組成規則、自動建立球場的時機與名稱，全部由後端 `create_group()` 決定；前端 MUST NOT 自行組出預設團名字串再送出（避免前後端算出不同結果），只單純把「留空」原樣送給後端由其決定最終團名。 | PASS |
| XI. 防機器人/防濫用 | 沿用既有 `POST /groups` 既有的 Turnstile 驗證（既有 FR-001 範疇），本 feature 未變更此端點的防濫用機制本身，不在新增範圍內。 | PASS（沿用既有，非新增） |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/021-group-creation-defaults/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/
│   └── group-and-court-api.md
└── tasks.md             # Phase 2 output (/speckit-tasks command — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
apps/api/
├── app/domains/group/
│   ├── schemas.py       # CreateGroupRequest.name: str | None = None，
│   │                     # 驗證器改為允許留空/純空白（視同未提供）
│   └── service.py       # create_group()：計算建立者暱稱的時機提前，
│                         # 留空時組出預設團名；同一交易內新增一筆
│                         # Court(name="球場一")，commit 後發布既有
│                         # court.added 事件
├── app/domains/court/
│   └── (router.py/service.py/schemas.py 皆不變——既有更名端點/邏輯
│    直接沿用，僅新增測試)
└── tests/
    ├── unit/domains/group/
    │   ├── test_create_validation.py                        # 擴充（既有——
    │   │   # test_blank_name_rejected 既有斷言方向反轉：純空白
    │   │   # 由「拒絕」改為「接受並正規化為 None」）
    │   └── test_create_group_defaults.py                    # 新增
    ├── unit/domains/court/test_rename_court.py              # 新增
    ├── contract/
    │   ├── test_create_group.py                              # 擴充（既有）
    │   └── test_rename_court.py                              # 新增
    └── integration/test_create_group_default_court_flow.py  # 新增

apps/web/
├── src/app/features/group-admin/
│   ├── create-group/
│   │   ├── create-group.component.ts    # name 移除 Validators.required；
│   │   │                                  # match_mode 初始值 doubles→singles
│   │   ├── create-group.component.html  # 移除「必填」錯誤訊息區塊，
│   │   │                                  # placeholder 提示留空預設行為
│   │   └── create-group.component.spec.ts
│   └── court-management/
│       ├── court-list.component.ts       # + 重新命名狀態與方法
│       ├── court-list.component.html     # + 重新命名操作入口
│       ├── court-list.component.scss     # + 對應樣式
│       └── court-list.component.spec.ts
└── src/assets/i18n/zh-TW.json             # + 重新命名文案／團名留空提示，
                                            # 移除已不再使用的 nameRequired
```

**Structure Decision**：延續既有 monorepo 結構（`apps/api` + `apps/web`）。
後端邏輯集中在既有 `group` domain（團名預設值、自動建立球場皆發生在
既有 `create_group()` 交易內）；`court` domain 本身的更名邏輯完全不變，
只新增測試。前端邏輯落在既有 `create-group`／`court-management` 兩個
既有元件——不新增 domain、不新增 Angular feature 模組、不新增路由。

## Complexity Tracking

*Gate 無違反項目，本節無需填寫。*
