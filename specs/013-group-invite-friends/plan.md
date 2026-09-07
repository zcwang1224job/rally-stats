# Implementation Plan: 邀請好友加入組團（Invite Friends to Join a Group）

**Branch**: `main`（本專案未使用 per-feature git branch，延續 001-012 之既有慣例）| **Date**: 2026-09-07 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/013-group-invite-friends/spec.md`，交叉比對 `/specs/012-realtime-notifications/`（通知機制之 `type`+`source_id` 可擴充設計，本 feature 是它上線後第一個實際擴充案例）、`/specs/006-member-friends/`（好友關係、`unfriend()`）、`/specs/001-create-manage-group/`、`/specs/004-join-group/`（`join_group()`、`disband_group()`——本 feature 唯二需要擴充參數的既有核心函式）。

## Summary

團長於管理頁面的「邀請好友」區塊，從 `GET
/groups/{group_id}/invitable-friends` 取得自己完整的好友列表（每位附帶
邀請狀態），對尚未邀請/已在團內的好友送出邀請
（`POST /groups/{group_id}/invites`）——新增獨立的 `group_invite`
domain 模組承接 `GroupInvite` 四態狀態機（pending/accepted/
declined/invalidated），透過重用既有 `get_friendship_status()`（好友
關係判斷）與 `join_group()`（接受邀請的實際加入邏輯，新增
`skip_password` 參數以滿足 Clarifications Q1 之「受邀略過密碼」定案）
避免重複實作核心規則。受邀好友透過既有通知機制（012）即時收到
`type="group_invite"` 通知；接受時因額滿而失敗，會額外建立一則
`type="group_invite_capacity_full"` 通知給團長（Clarifications
Q2/FR-013），邀請本身狀態不變。好友關係解除或本團解散時，待回覆邀請
自動轉為 `invalidated`（Clarifications Q3/FR-014）——透過在
`unfriend()`/`disband_group()` 新增可選 hook 參數達成（比照既有
`AbandonMatchesHook` 模式），避免 `group`/`friend`/`group_invite` 三個
模組互相 import 形成循環。

## Technical Context

**Language/Version**：延續 001-012（後端 Python 3.12+；前端 TypeScript /
Angular 20+）。

**Primary Dependencies**：沿用既有 FastAPI/SQLAlchemy/Alembic、Ably
REST/JS SDK 堆疊，**不新增套件**。

**Storage**：PostgreSQL，新增 **1 張資料表** `group_invites`
（`group_id`/`inviter_member_id`/`invitee_member_id`/`status`/
`created_at`/`updated_at`，見 data-model.md），需要 **1 個 Alembic
migration**。不修改任何既有資料表結構（`GroupPublicResponse`/
`NotificationSummary` 的擴充皆是回應形狀層級，非資料表層級）。

**Testing**：pytest + pytest-asyncio（後端：`GroupInvite` 四態狀態機、
`join_group()` 之 `skip_password` 行為、額滿失敗不改變邀請狀態且通知
團長、好友關係解除/團解散觸發自動失效、唯一性約束、僅本人可查看/操作
之授權邊界——皆 MUST 有單元測試；至少一條整合測試涵蓋「送出邀請 →
即時通知 → 接受（略過密碼）→ 成為成員」全流程）。Vitest（前端：邀請
區塊之好友清單渲染、接受/拒絕互動、通知點擊導向）。

**Target Platform**：延續既有（Docker on AWS ECS，本地
`docker-compose`）。

**Project Type**：Web application（monorepo，延續既有 `apps/api` +
`apps/web` 結構）。

**Performance Goals**：SC-001/SC-006——2 秒內收到通知，SHOULD 等級，
比照既有 012 SC-001 之精神，非 blocking gate。

**Constraints**：邀請對象僅限團長既有好友關係（FR-002）；同一好友同團
同時至多一筆待回覆邀請（FR-003）；已在團內的好友不可再被邀請
（FR-004）；接受邀請 MUST 略過密碼驗證（FR-007，Clarifications Q1）；
匿名建團 MUST NOT 提供此功能（FR-012）；額滿失敗 MUST NOT 改變邀請
狀態、MUST 通知團長（FR-013）；好友關係解除 MUST 使待回覆邀請自動失效
（FR-014）。

**Scale/Scope**：單一團長的好友數量與邀請數量同數量級（小），比照
005/012 之既有 Scale/Scope 假設（全部載入 Python 處理，不需分頁/快取
層）。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | Pydantic v2 schema 對應所有請求/回應（`InvitableFriendSummary`/`GroupInviteDetailResponse`/`AcceptGroupInviteResponse` 等）；`ruff`/`mypy --strict` blocking check；前端 TypeScript strict mode，`invite_status`/`GroupInvite.status` 對應後端 Literal 聯合型別。 | PASS |
| II. 測試優先 | 邀請功能非原則 II 明列的核心領域清單，但比照 006/012 既有測試慣例，MUST 有單元測試涵蓋 `GroupInvite` 狀態機四態轉換、`join_group()` 之 `skip_password=True` 行為（含既有呼叫端 `skip_password` 預設 `False` 不受影響的回歸測試）、額滿失敗的「狀態不變+通知團長」組合行為、好友關係解除/團解散觸發自動失效、唯一性約束、僅本人可查看/操作之授權邊界；至少一條整合測試涵蓋完整送出→通知→接受流程。 | PASS（列入 tasks.md 強制項） |
| III. 即時性與資料一致性 | 完全沿用 012 既有即時通知基礎設施（頻道、事件、前端覆蓋式重新拉取邏輯），不新增任何即時同步機制；`GroupInvite` 寫入一律先落地資料庫交易，commit 後才透過既有 `publish()` wrapper 廣播（間接透過 `notification.service`）。SC-001/SC-006 之 2 秒目標為 SHOULD 等級、人工抽測，非 blocking gate。 | PASS |
| IV. 權限與安全 | 送出邀請/查看好友邀請狀態端點沿用既有 `require_admin`（PIN/管理 Token 驗證路徑，未新增或修改此驗證機制本身）；接受/拒絕/查看詳情端點沿用既有 `require_verified_member` + 明確驗證「是否為本人受邀」（不符一律 `GROUP_INVITE_NOT_FOUND`，不洩漏存在性，比照 `FRIEND_REQUEST_NOT_FOUND` 既有慣例）。**密碼略過為 spec 明確定案的產品決策**（Clarifications Q1），非安全疏漏——僅在「受邀者已通過好友關係 + 團長主動個別授權」此組合條件下生效，`join_group()` 其餘所有既有呼叫端（列表加入、加入連結、訪客重連）之 `skip_password` 預設維持 `False`，密碼保護對這些既有路徑完全不受影響。 | PASS |
| V. UX 一致性（破壞性操作二次確認） | 接受/拒絕邀請、送出邀請皆非資料遺失性質的破壞性操作（比照好友申請接受/拒絕之既有慣例，不需二次確認 dialog）。 | 不適用（無破壞性操作） |
| VI. 可維護性 | 新增獨立 `group_invite` domain 模組，讀取（不修改核心邏輯）`group`/`friend` 模組之既有服務函式；`join_group()` 新增預設關閉的 `skip_password` 參數（零行為變更給既有呼叫端）；`disband_group()`/`unfriend()` 新增可選 hook 參數（比照既有 `AbandonMatchesHook` 模式，research.md #2），避免三模組互相 import 形成循環，同時不需要把既有邏輯搬到共用底層模組而模糊職責歸屬。 | PASS |
| VII. 無障礙與行動裝置優先 | 邀請狀態（待回覆/已接受/已拒絕/已失效/已在團內）MUST NOT 僅以顏色區分，比照既有 `status-badge` 圖示+文字並用慣例；管理頁邀請區塊與受邀好友的接受/拒絕畫面皆沿用既有觸控目標尺寸規範。 | PASS（前端落實於 tasks.md 展開） |
| VIII. i18n 與時區 | 新增錯誤代碼（`GROUP_NOT_MEMBER_CREATED`/`NOT_FRIENDS`/`ALREADY_GROUP_MEMBER`/`INVITE_ALREADY_PENDING`/`GROUP_INVITE_NOT_FOUND`/`GROUP_INVITE_NOT_PENDING`）一律語意化代碼，前端依既有 `errors.<code>` 慣例對應語系檔；`created_at`/`updated_at` 一律 `TIMESTAMPTZ`（UTC），API 回傳 ISO 8601。 | PASS |
| IX. 可攜性與可部署性 | 沿用既有 Docker/AWS 設計與既有 Ably 帳號，不需額外基礎設施；新增的 1 個 Alembic migration 沿用既有 migration 執行流程。 | PASS |
| X. 即時同步的可信來源 | `GroupInvite` 的建立/狀態轉換一律先經後端服務層驗證並寫入資料庫，commit 後才（透過 `notification.service`）廣播事件；前端 MUST 僅訂閱既有頻道，未引入任何新的即時通訊基礎設施或前端直接發布事件的路徑。 | PASS |
| XI. 防機器人/防濫用 | `POST /groups/{group_id}/invites` 雖是「建立新資源」類型端點，但受兩層既有屏障保護——`require_admin`（已通過 PIN/管理 Token 驗證的既有會話）與「僅限已確立的好友關係」（雙方皆曾主動同意的互信關係，非任意會員可觸發），與 012 之好友申請通知建立同樣的既有推理一致，不在原則 XI 之 Turnstile 強制範圍內。 | PASS（明確排除項，非違反） |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/013-group-invite-friends/
├── plan.md                    # 本檔案
├── research.md                # Phase 0 產出
├── data-model.md              # Phase 1 產出
├── quickstart.md              # Phase 1 產出
├── contracts/                 # Phase 1 產出
│   ├── group-invite-api.md
│   ├── notification-api-additions.md
│   └── ably-events-additions.md
└── tasks.md                   # /speckit-tasks 產出（本指令不建立）
```

### Source Code (repository root)

```text
apps/api/
├── app/
│   ├── domains/
│   │   ├── group_invite/                # 新增模組
│   │   │   ├── __init__.py
│   │   │   ├── models.py                # GroupInvite
│   │   │   ├── schemas.py               # InvitableFriendSummary/InvitableFriendsResponse/
│   │   │   │                              SendGroupInviteRequest/SendGroupInviteResponse/
│   │   │   │                              GroupInviteDetailResponse/AcceptGroupInviteResponse/
│   │   │   │                              DeclineGroupInviteResponse
│   │   │   ├── service.py               # send_invite()、list_invitable_friends()、
│   │   │   │                              get_invite_detail()、accept_invite()、
│   │   │   │                              decline_invite()、
│   │   │   │                              invalidate_pending_invites_for_group()、
│   │   │   │                              invalidate_pending_invites_for_member_pair()
│   │   │   └── router.py                # 5 個端點（見 contracts/group-invite-api.md）
│   │   ├── group/
│   │   │   ├── schemas.py               # 擴充：GroupPublicResponse.created_by_member
│   │   │   ├── service.py               # 擴充：join_group() 新增 skip_password 參數；
│   │   │   │                              disband_group() 新增 invalidate_pending_invites
│   │   │   │                              hook 參數（research.md #2、#3）
│   │   │   └── router.py                # 擴充：_to_public() 填入新欄位；disband 端點
│   │   │                                  傳入 group_invite.service 之 hook 函式
│   │   ├── friend/
│   │   │   ├── service.py               # 擴充：unfriend() 新增 invalidate_pending_invites
│   │   │   │                              hook 參數
│   │   │   └── router.py                # 擴充：unfriend 端點傳入 hook 函式
│   │   └── notification/
│   │       ├── schemas.py               # 擴充：NotificationSummary.type、
│   │       │                              GroupInviteNotificationDetail
│   │       └── service.py               # 擴充：_build_notification_summaries() 新增
│   │                                      group_invite/group_invite_capacity_full 分支
│   └── scheduler/
│       └── auto_disband.py              # 擴充：sweep_idle_groups() 傳入 invalidate hook
├── alembic/versions/
│   └── <new_rev>_group_invite_table.py  # 新增：group_invites 表 + 2 個索引
└── tests/
    ├── unit/domains/group_invite/       # 新增
    ├── unit/domains/group/              # 擴充：skip_password、disband hook 相關測試
    ├── unit/domains/friend/             # 擴充：unfriend 觸發失效之測試
    ├── contract/
    │   └── test_group_invite_endpoints.py  # 新增
    └── integration/
        └── test_group_invite_flow.py       # 新增

apps/web/
└── src/app/
    ├── core/api/
    │   ├── group-invite.models.ts       # 新增
    │   └── notification.models.ts       # 擴充：type 聯合、group_invite 巢狀欄位
    └── features/
        ├── group-admin/
        │   ├── group-admin.models.ts    # 擴充：GroupPublic.created_by_member
        │   └── admin-page/
        │       ├── admin-page.component.ts    # 擴充：新增 'invites' AdminSection
        │       └── admin-page.component.html  # 擴充：好友清單 + 邀請狀態區塊
        └── group-invites/                     # 新增 feature 目錄（受邀好友視角）
            ├── group-invite.service.ts
            └── group-invite-detail/
                ├── group-invite-detail.component.ts
                ├── group-invite-detail.component.html
                └── group-invite-detail.component.scss
```

新增前端路由 `group-invites/:inviteId`（`apps/web/src/app/app.routes.ts`）
→ `group-invite-detail.component.ts`，供通知點擊導向（FR-005）。

**Structure Decision**：後端新增獨立 `group_invite` domain 模組，前端
新增 `features/group-invites` 目錄（受邀好友視角）並擴充既有
`group-admin/admin-page`（團長視角）；`group`/`friend`/`notification`
三個既有模組僅做最小擴充（各自新增 1-2 個參數/欄位），不修改其核心
業務邏輯或既有呼叫端行為，符合原則 VI 之模組邊界與最小變更原則。

## Complexity Tracking

*本 feature 無 Constitution Check 違反項目，此表格從略。*

## Post-Design Constitution Check

*Re-evaluated after Phase 1（`data-model.md`、`contracts/`、
`quickstart.md`）產出。*

設計階段的關鍵決策——(1) `join_group()` 新增預設 `False` 的
`skip_password` 參數而非另寫一份重複邏輯（research.md #3，延續原則 VI
之單一事實來源精神）、(2) `disband_group()`/`unfriend()` 以既有
`AbandonMatchesHook` 同款模式新增可選 hook 參數解決循環 import
（research.md #2，非新發明的架構模式）、(3)
`GroupInvite` 的 `invalidated` 狀態統一涵蓋「好友關係解除」與「團解散」
兩種觸發來源（research.md #5，減少狀態種類而非增加）、(4) 通知擴充
完全依照 012 當初設計時就承諾的「新增類型不需重新設計既有機制」
（research.md #7，兌現而非違反該承諾）——皆為在不違反任何 FR 與既有
Constitution 判定的前提下確保正確性與一致性的實作細節，未引入新的違反
項目。對 `group`/`friend` 兩個既有模組的唯一觸碰是新增參數與其對應的
最小邏輯分支，未修改其既有簽章的必要參數、既有錯誤代碼語意或既有呼叫端
的預設行為。**Gate 結果維持 PASS，無需新增 Complexity Tracking 項目。**

## Assumptions

- 管理頁面「邀請好友」區塊的確切版面位置（是否與既有「輪替名單」分頁
  並列、或獨立分頁）留待 tasks.md/實作階段依既有 `admin-page` 版面
  慣例決定，本 plan 僅定義其 API 邊界與資料模型。
- 受邀好友的「查看邀請詳情並接受/拒絕」畫面，比照既有
  `friend-requests` 頁面之簡單卡片版面慣例，不另外設計複雜互動，本 plan
  不預先定義具體 CSS/版面細節。
- `GROUP_DISBANDED` 錯誤代碼在 `POST /group-invites/{invite_id}/accept`
  的實際回應中理論上不會出現（因為團解散已透過 hook 讓邀請先轉為
  `invalidated`，接受請求會先命中 `GROUP_INVITE_NOT_PENDING`）——保留
  於契約文件中純屬防禦性文件記錄（例如未來若 hook 呼叫失敗的極端情況），
  不代表這是一條會被實際觸發的正常路徑。
- 好友列表數量與邀請歷史筆數的分頁需求留待 tasks.md 依實際資料量決定
  （比照 012/005 之 Scale/Scope 假設，初期不預期需要分頁）。
