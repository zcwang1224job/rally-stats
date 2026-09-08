# Implementation Plan: 團長手動新增訪客入團

**Branch**: `main` (no dedicated feature branch — no `before_specify` git hook configured in this repo; work lands directly via reviewed commits per existing session convention) | **Date**: 2026-09-08 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/015-manual-add-guest/spec.md`

## Summary

團長（已持有 `admin_token`）能在管理頁的花名冊區塊，手動輸入暱稱把一位訪客
直接加進該團的輪替名單（US1），並在新增成功後立即取得一組可轉交給該訪客的
個人查看連結／QR code（US2）。

技術做法的核心是**重用**，不是新寫一套平行邏輯：後端新增的
`POST /groups/{group_id}/members` 端點，在通過 `require_admin` 驗證、確認
`group_id` 與 token 相符後，直接呼叫既有的 `group.service.join_group(...,
member=None, skip_password=True)`——這正是 013-group-invite-friends 為
「邀請連結免密碼」新增的同一個 `skip_password` 參數，本功能是它的第二個
呼叫方，語意天然吻合（「管理員的授權」和「邀請本身的授權」一樣，都足以
取代「知道密碼」這件事）。這讓人數上限檢查、已解散團擋下、暱稱驗證、
`RosterEntry` 建立、排點掛勾（`handle_member_joined`）、即時通知
（`member.joined`）全部原封不動繼承，後端幾乎零新增業務邏輯。

US2 的「個人查看連結」同樣是重用：後端回應直接沿用既有
`JoinGroupResponse`（已包含 `guest_session_token`），前端只需新增一個路由
`guest-access/:token`，呼叫**既有**的 `GroupJoinService.resolveGuestSession()`
（目前只用於「同瀏覽器復原 session」，本功能是它的第一個「跨裝置」用法）
解析出 `group_id`，再呼叫既有的 `setGuestSessionToken()` 寫入
localStorage，導向既有的 `/groups/:groupId/member-view`——不需要任何新的
後端查詢端點。

## Technical Context

**Language/Version**: Python 3.12（後端，FastAPI + SQLAlchemy async）／
TypeScript 5.x, strict mode（前端，Angular 20 standalone components + signals）

**Primary Dependencies**: FastAPI、SQLAlchemy（async）、Pydantic v2、
Alembic（後端，皆為既有依賴，本功能不新增套件）；Angular 20、
`@ngx-translate`、`angularx-qrcode`（前端，皆為既有依賴，QR 顯示直接重用
`QRCodeComponent`，如 `court-link-card.component.ts`/`admin-page.component.ts`
既有的 join-link QR 用法）

**Storage**: PostgreSQL（既有 `roster_entries` 資料表，本功能不新增欄位、
不新增資料表——`member_id IS NULL` 早已是訪客的既有語意）

**Testing**: pytest（後端 unit/contract/integration，既有 `tests/`
目錄結構）；Vitest via `ng test`（前端）

**Target Platform**: Web（既有 Docker 容器化後端 + Angular SPA，部署至
AWS；本功能不涉及任何 infra 變更）

**Project Type**: Web application（既有 monorepo：`apps/api` + `apps/web`）

**Performance Goals**: 與既有花名冊管理端點（例如踢人）同等級——單次請求
在正常網路狀況下應於 1 秒內完成，無特殊效能目標（spec SC-001 的「30 秒內
完成新增」是人為操作時間的量測，非 API 延遲 SLA）

**Constraints**: MUST 重用 `group.service.join_group()` 作為唯一的訪客
建立邏輯來源，MUST NOT 另寫一套平行的「建立訪客名冊項目」邏輯（憲章原則
VI，可維護性/模組化）；MUST 沿用既有 `require_admin` 驗證機制與
`group_id`／token 交叉比對（憲章原則 IV）

**Scale/Scope**: 單一團內的管理員動作，人數規模受既有 `max_members`
限制（既有系統設計目標為單團數十人量級），本功能不改變此規模假設

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 是否觸及 | 檢查結果 |
|---|---|---|
| I. 程式碼品質與型別安全 | 是——新增後端 Pydantic schema、前端 TS 元件/服務方法 | PASS：沿用既有 strict TS/mypy 設定，無新工具鏈需求 |
| II. 測試優先 | 是——碰觸開團/加入/輪替核心領域邏輯 | PASS（需落實）：計畫在 `/speckit-tasks` 中為新端點補上單元測試（正常新增、額滿擋下、已解散團擋下、連續新增多位）與至少一條「新增後出現在輪替名單」的整合測試，呼應原則 II 的端到端要求 |
| III. 即時性與資料一致性 | 是——新增訪客會觸發 `member.joined` 廣播 | PASS：直接重用 `join_group()` 內既有的 `publish()` 呼叫，不新增平行的廣播邏輯，不涉及進行中比賽/Round 的設定快照問題 |
| IV. 權限與安全 | 是——新端點需要管理員權限 | PASS：沿用 `require_admin`（回傳 `Group` ORM 物件）+ 比照 `kick_member` 的 `group.id != group_id` 交叉比對（`ADMIN_TOKEN_INVALID`），不新增驗證機制、不與訪客加入密碼機制混用同一程式碼路徑（`skip_password=True` 讓管理員動作完全略過密碼檢查，語意上與 013 的邀請連結一致：管理員身份本身就是授權來源）。**連結類 Token 备註**：本功能重用既有 `guest_session_token`（004-join-group 既有機制）產生訪客的個人查看連結；該 token 目前是否已具備「管理員可單獨重新產生使舊連結失效」的能力，是 004 既有範圍的既有事實，本功能未改變其屬性、也未新增新的 token 類型，故不在本 plan 範圍內補強或視為新違規 |
| V. UX 一致性（破壞性動作確認） | 否——新增是可逆、非破壞性動作 | N/A：不需要二次確認流程（與「踢人」不同） |
| VI. 可維護性 | 是——核心設計决策 | PASS：新端點是 `join_group()` 的薄包裝（router 層直接呼叫既有 service 函式），不重複人數上限/暱稱驗證/已解散團判斷等既有邏輯 |
| VII. 無障礙與行動裝置優先 | 是——新增表單與分享連結 UI | PASS：沿用既有表單/QR 元件與樣式慣例，無新的僅靠顏色區分的視覺元素 |
| VIII. 多語系與時區架構 | 是——新增 UI 文字與可能的新錯誤碼 | PASS（需落實）：所有新增顯示文字須進 `zh-TW.json`；後端優先重用既有錯誤碼（`GROUP_FULL`、`GROUP_DISBANDED`、`NICKNAME_REQUIRED_FOR_GUEST`、`ADMIN_TOKEN_INVALID`），research.md 已確認皆可原樣重用，不新增錯誤碼 |
| IX. 可攜性與可部署性 | 否 | N/A：無 infra 變更 |
| X. 即時同步的可信來源 | 是 | PASS：新增動作本身就是一次後端驗證後的寫入 + 後端廣播，前端不繞過後端直接發佈事件 |
| XI. 防機器人/防濫用 | 否——本端點為管理員已驗證後的動作，非公開建立資源端點 | N/A：Turnstile 範圍明確限定「會員註冊、開團」，管理員已通過 `admin_token` 驗證的動作不屬此範圍，比照 `kick_member` 現行做法（無 Turnstile） |

無違反項目，Complexity Tracking 表格留空。

## Project Structure

### Documentation (this feature)

```text
specs/015-manual-add-guest/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/           # Phase 1 output (/speckit-plan command)
│   └── manual-add-guest-api.md
└── tasks.md             # Phase 2 output (/speckit-tasks command - NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
apps/api/app/domains/group/
├── router.py     # 新增 POST /groups/{group_id}/members（沿用 require_admin）
├── service.py    # 不修改 join_group() 本身；新增端點直接呼叫既有函式
└── schemas.py    # 新增 AddGuestRequest；回應沿用既有 JoinGroupResponse

apps/api/tests/
├── contract/
│   └── test_add_guest_endpoint.py   # 新增：請求/回應形狀、正常新增、
│                                     # 額滿/已解散/暱稱驗證/權限錯誤、連續新增
└── integration/
    └── test_add_guest_flow.py       # 新增：新增後出現在輪替名單、被正常排點、
                                      # 可被踢出、guest_session_token 可換回身份

apps/web/src/app/features/
├── group-admin/admin-page/
│   ├── admin-page.component.ts      # 花名冊區塊新增「新增訪客」表單 + 分享連結顯示
│   └── admin-page.component.html
├── group-admin/schedule-management/
│   └── schedule.service.ts          # 新增 addGuest(groupId, nickname) 方法
└── group-join/
    ├── guest-access/                # 新增：GuestAccessComponent（新路由進入點）
    │   ├── guest-access.component.ts
    │   └── guest-access.component.spec.ts
    └── group-join.service.ts        # 不修改——resolveGuestSession()/setGuestSessionToken() 已存在，直接重用

apps/web/src/app/app.routes.ts       # 新增 'guest-access/:token' 路由
apps/web/src/assets/i18n/zh-TW.json  # 新增表單/分享連結相關文字
```

**Structure Decision**: 後端新端點放在 `group/` domain（與既有
`POST /groups/{group_id}/join` 同一個 router/service 檔案），因為它就是
`join_group()` 的另一個呼叫方，不需要跨 domain 呼叫（不像 `kick_member`
放在 `schedule/` domain）。前端新增的分享連結進入點沿用 `group-join/`
feature 目錄（與既有 `join/:token` 進入點同一個 feature，共用
`GroupJoinService`），管理頁 UI 變更則直接加在既有 `admin-page` 元件的花名冊
區塊，不新增獨立元件檔案（維持現行「單一 admin-page + section 切換」的
既有結構）。
