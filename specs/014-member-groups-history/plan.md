# Implementation Plan: 我的團完整參與紀錄與戰績（All My Groups — Participation History & Stats）

**Branch**: `main`（本專案未使用 per-feature git branch，延續既有慣例）| **Date**: 2026-09-07 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/014-member-groups-history/spec.md`，交叉比對 `/specs/006-member-friends/`（既有 `GET /members/me/groups`，僅列自建團的 FR-028/029）、`/specs/005-member-view/`（`build_group_match_records()`、`resolve_active_roster_membership()`——本 feature 唯一需要新增旁支授權判斷式、而非修改的既有函式）。

## Summary

「我的團」清單（`GET /members/me/groups`）擴充為顯示會員自己建立過 ∪
曾經加入過（不限現役／已離開／已被踢除）的所有團之聯集，每筆附帶
`is_creator`／`member_status` 兩個新欄位；既有的「忘記管理PIN碼」流程完全
不變，只是清單涵蓋範圍變大。點進任一團，新端點
`GET /members/me/groups/{group_id}/history` 回傳該團所有已完成比賽（重用
既有 `build_group_match_records()`，未修改）與自己在該團的個人戰績
（重用既有 `build_member_match_records()`，新增一個預設關閉的 `group_id`
篩選參數）。存取權限判斷式是全新的 `verify_ever_group_member()`——刻意
獨立於既有 `resolve_active_roster_membership()`（後者仍只服務現役成員的
即時操作端點），只要求「曾經是此團的正式成員」即可，落實 Clarifications
2026-09-07 定案的存取邊界。全程不新增資料表，不新增 migration。

## Technical Context

**Language/Version**：延續既有（後端 Python 3.12+；前端 TypeScript /
Angular 20+）。

**Primary Dependencies**：沿用既有 FastAPI/SQLAlchemy 堆疊，**不新增套件**。

**Storage**：PostgreSQL，**不新增資料表、不需要 migration**（research.md
#6）——純粹是既有 `groups`/`roster_entries`/`matches`/`match_participants`
表的唯讀查詢範圍擴充。

**Testing**：pytest + pytest-asyncio（後端：`verify_ever_group_member()`
的曾經／從未參與兩種邊界、`get_my_groups()` 的聯集去重與
`is_creator`/`member_status` 正確性、`build_member_match_records(group_id=)`
新參數的回歸測試——確保既有 `/members/me/match-records` 呼叫端零行為變動、
新端點的完整回應組裝——皆 MUST 有單元測試；至少一條整合測試涵蓋「加入→
打比賽→退出→仍可查看歷史」全流程）。Vitest（前端：「我的團」清單的身份／
狀態徽章渲染、點擊導向新頁面、新頁面的比賽清單與統計呈現）。

**Target Platform**：延續既有（Docker on AWS ECS，本地 `docker-compose`）。

**Project Type**：Web application（monorepo，延續既有 `apps/api` +
`apps/web` 結構）。

**Performance Goals**：SC-002——3 秒內看到比賽清單與個人統計，SHOULD 等級，
人工抽測，非 blocking gate。

**Constraints**：查看某團歷史的授權邊界 MUST 與「我的團」清單涵蓋範圍完全
一致（曾經是正式成員，Clarifications 2026-09-07/FR-006）；MUST NOT 影響
既有 `resolve_active_roster_membership()` 服務的任何現役限定端點的既有行為
（FR-007 隱含的「不破壞既有功能」要求）。

**Scale/Scope**：單一會員參與過的團數量、單一團的已完成比賽數量，皆比照
既有 `GET /members/me/groups`/`GET /groups/{id}/match-records` 的既有
Scale/Scope 假設（既有分頁機制已覆蓋比賽清單本身；「我的團」清單本身不
分頁，比照既有假設）。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | Pydantic v2 schema 對應所有回應（`MyGroupSummary` 擴充欄位、新增 `MemberGroupStatsResponse`/`MemberGroupHistoryResponse`）；`ruff`/`mypy --strict` blocking check；前端 TypeScript strict mode，直接重用既有 `MatchRecordSummary`/`GroupMatchRecordsResponse` 介面（零改動）。 | PASS |
| II. 測試優先 | 本功能非原則 II 明列的核心領域清單，但比照既有慣例，MUST 有單元測試涵蓋 `verify_ever_group_member()` 的曾經／從未參與邊界、`get_my_groups()` 聯集去重與最新狀態判斷、`build_member_match_records(group_id=)` 新參數對既有呼叫端零行為影響的回歸測試；至少一條整合測試涵蓋完整加入→打比賽→退出→仍可查看歷史流程。 | PASS（列入 tasks.md 強制項） |
| III. 即時性與資料一致性 | 本功能全程唯讀、無寫入操作，不涉及任何即時同步——不適用。 | 不適用 |
| IV. 權限與安全 | 新增的 `verify_ever_group_member()` 刻意獨立於既有 `resolve_active_roster_membership()`，不修改、不放寬後者的既有「現役」門檻（後者仍是退出組團等即時操作端點的授權依據）——避免不同信任層級的授權路徑互相混用（research.md #3）。新端點 `GET /members/me/groups/{group_id}/history` 對「從未參與過的團」一律拒絕（`GROUP_MEMBERSHIP_NEVER_HELD`，403），不因知道網址/團編號而洩漏歷史資料（Clarifications 2026-09-07）。 | PASS |
| V. UX 一致性（破壞性操作二次確認） | 本功能全程唯讀查詢，無任何寫入或破壞性操作。 | 不適用（無破壞性操作） |
| VI. 可維護性 | 重用既有 `build_group_match_records()`（未修改）與擴充後的 `build_member_match_records()`（新增預設關閉參數，零行為變動給既有呼叫端）——避免第三套「算勝敗場次」的重複邏輯（research.md #1、#2）；新授權判斷式獨立於既有函式，職責單一。 | PASS |
| VII. 無障礙與行動裝置優先 | 「我的團」清單新增的身份（團長/團員）與狀態（現役/已離開/已被踢除/已解散）徽章 MUST 圖示＋文字並用，比照既有 `status-badge` 慣例，不得僅以顏色區分。 | PASS（前端落實於 tasks.md 展開） |
| VIII. i18n 與時區 | 新增錯誤代碼 `GROUP_MEMBERSHIP_NEVER_HELD` 一律語意化代碼，前端依既有 `errors.<code>` 慣例對應語系檔；比賽時間欄位沿用既有 `MatchRecordSummary` 的 ISO 8601 UTC 格式，未新增任何時間欄位。 | PASS |
| IX. 可攜性與可部署性 | 不新增任何基礎設施、不新增 migration。 | PASS |
| X. 即時同步的可信來源 | 本功能不涉及 Ably 或任何即時廣播——不適用。 | 不適用 |
| XI. 防機器人/防濫用 | 本功能所有端點皆為既有 `require_member`/`require_verified_member`（已通過會員身份驗證的既有會話）保護下的唯讀查詢，不建立任何新資源，不在原則 XI 之 Turnstile 強制範圍內。 | PASS（明確排除項，非違反） |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/014-member-groups-history/
├── plan.md                    # 本檔案
├── research.md                # Phase 0 產出
├── data-model.md              # Phase 1 產出
├── quickstart.md              # Phase 1 產出
├── contracts/                 # Phase 1 產出
│   └── member-groups-history-api.md
└── tasks.md                   # /speckit-tasks 產出（本指令不建立）
```

### Source Code (repository root)

```text
apps/api/
├── app/
│   ├── domains/
│   │   ├── member/
│   │   │   ├── schemas.py               # 擴充：MyGroupSummary 新增
│   │   │   │                              is_creator/member_status；新增
│   │   │   │                              MemberGroupStatsResponse/
│   │   │   │                              MemberGroupHistoryResponse
│   │   │   ├── service.py               # 擴充：get_my_groups() 改為聯集
│   │   │   │                              查詢；build_member_match_records()
│   │   │   │                              新增 group_id 篩選參數；新增
│   │   │   │                              get_member_group_history()
│   │   │   └── router.py                # 新增：
│   │   │                                  GET /members/me/groups/{group_id}/history
│   │   └── group/
│   │       └── service.py               # 新增：
│   │                                      verify_ever_group_member()
│   │                                      （resolve_active_roster_membership()
│   │                                      旁邊，各自獨立）
│   └── (無新增 domain 模組、無新增資料表)
└── tests/
    ├── unit/domains/member/             # 擴充：get_my_groups 聯集測試、
    │                                      build_member_match_records(group_id=)
    │                                      回歸測試、get_member_group_history 測試
    ├── unit/domains/group/              # 擴充：verify_ever_group_member 測試
    ├── contract/
    │   └── test_member_groups_history_endpoints.py  # 新增
    └── integration/
        └── test_member_groups_history_flow.py       # 新增

apps/web/
└── src/app/
    ├── core/api/
    │   └── friend.models.ts             # 擴充：MyGroupSummary 新增
    │                                      is_creator/member_status；新增
    │                                      MemberGroupHistoryResponse 等
    └── features/
        ├── friends/
        │   └── friends.service.ts       # 擴充：新增 getMemberGroupHistory()
        └── member/
            └── my-groups/
                ├── my-groups.component.ts    # 擴充：身份/狀態徽章、
                │                              點擊列導向新路由
                ├── my-groups.component.html  # 擴充
                └── group-history/            # 新增 sub-feature 目錄
                    ├── group-history.component.ts
                    ├── group-history.component.html
                    └── group-history.component.scss
```

新增前端路由 `member/my-groups/:groupId`（`apps/web/src/app/app.routes.ts`）
→ `group-history.component.ts`。

**Structure Decision**：本 feature 不新增任何 domain 模組——完全是對既有
`member`/`group` 兩個模組的最小擴充（各自新增 1-2 個函式/欄位），符合
原則 VI 之最小變更原則；前端在既有 `member/my-groups` 底下新增一個
sub-feature 目錄，重用既有 `group-member-view` 的型別與呈現慣例，不重複
定義任何既有已存在的 TypeScript 介面。

## Complexity Tracking

*本 feature 無 Constitution Check 違反項目，此表格從略。*

## Post-Design Constitution Check

*Re-evaluated after Phase 1（`data-model.md`、`contracts/`、
`quickstart.md`）產出。*

設計階段的關鍵決策——(1) 重用 `build_group_match_records()` 而非另寫查詢
（research.md #1，延續原則 VI）、(2) 以「預設關閉的新參數」擴充
`build_member_match_records()` 而非複製一套勝敗計算邏輯（research.md #2，
同 013 feature `skip_password` 的既有先例）、(3) 新增獨立的
`verify_ever_group_member()` 而非放寬既有 `resolve_active_roster_
membership()` 的門檻（research.md #3，明確保護既有授權邊界，落實原則
IV）——皆為在不違反任何 FR 與既有 Constitution 判定的前提下確保正確性與
一致性的實作細節，未引入新的違反項目。對 `group`/`member` 兩個既有模組的
唯一觸碰是新增函式與新增預設關閉的參數，未修改其既有簽章的必要參數、既有
錯誤代碼語意或既有呼叫端的預設行為。**Gate 結果維持 PASS，無需新增
Complexity Tracking 項目。**

## Assumptions

- 「我的團」清單本身的排序沿用既有 `get_my_groups()` 之
  `Group.created_at.desc()` 慣例，本 plan 不特別定義新的排序規則。
- 「個人統計」是否需要更豐富的圖表呈現（比照既有跨團對戰紀錄頁的輪次
  勝率趨勢圖／對戰對象排行榜）留待 tasks.md/實作階段依 UI 複雜度決定——
  spec FR-005 僅要求「至少」總場次/勝/敗/勝率四個數字，本 plan 僅保證
  這個最低限度的資料在後端可取得。
- `MemberGroupHistoryResponse.matches` 的分頁沿用既有
  `_MATCH_RECORDS_PAGE_SIZE`（20 筆／頁）之既有慣例，不另外設計分頁大小。
