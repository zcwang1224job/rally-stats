# Implementation Plan: 從對戰紀錄／即時戰況頁面加好友

**Branch**: `main`（本專案未使用 per-feature git branch，延續既有慣例）| **Date**: 2026-09-14 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/026-match-record-friend-invite/spec.md`，
交叉比對 `/specs/006-member-friends`（既有好友邀請狀態機、`GET /friends`、
`POST /friends/requests`、`get_friendship_status()`）、
`/specs/022-member-personal-settings`（既有隱私設定 `allow_search`/
`share_match_records_with_friends` 欄位與 `PrivacySettingsRequest`/
`PrivacySettingsResponse` 的既定模式）、`/specs/023-view-friend-match-records`
（既有 `MemberMatchRecordsResponse`）、`/specs/003-schedule-rotation`與
`/specs/007-live-scoreboard`（`ParticipantSummary`/`ScheduleResponse`/
`CourtLiveState` 既有資料流）。

## Summary

本 feature 在四個既有畫面（跨團對戰紀錄、團內對戰紀錄、團內成員視圖賽程頁
新增的輪替名單、開團管理頁輪替名單分頁）的參與者/團員名字旁新增「加好友」
入口，並新增一項獨立隱私開關。核心技術挑戰不是新功能本身（好友邀請機制
完全沿用 006），而是**`ParticipantSummary` 這個型別在後端被四個以上呼叫
點共用，其中兩個（`_match_participants_payload()`／`court_live_state()`）
是無需登入的公開計分板／控制板端點與 Ably 廣播payload 的資料來源**——研究
後確認：只要新增的 `member_id` 欄位只在既有、皆需登入驗證的查詢路徑中
填入，公開路徑保持完全不變（`member_id` 恆為 `None`），即可在不重構共用
型別的前提下安全達成 FR-013 的邊界。

**實作後調整（2026-09-14）**：US2 的入口落點由「僅目前進行中比賽的參與者」
改為「輪替名單中所有現役團員」（見 spec.md Clarifications「實作後調整」
段落、FR-011/FR-016）。對應地，安全落點也從 `ParticipantSummary`（會被
`_match_participants_payload()`/`court_live_state()` 公開端點共用）搬移到
`RosterScheduleStatus`（同樣是 `build_schedule_snapshot()` 產出的
`ScheduleResponse` 的一個欄位，但只餵給團內成員視圖賽程頁與管理頁兩個需
登入/管理員權杖驗證的路徑，從未被任何公開端點或 Ably payload 消費）——
`member_id` 只在 `build_schedule_snapshot()` 建構 `roster` 列表時填入
`RosterScheduleStatus.member_id`，`current_match`/`next_up` 底下的
`ParticipantSummary.member_id` 維持恆為 `None`（不再是本 feature 填入的
對象）。`_build_match_record_summaries()`（團內對戰紀錄）與
`_build_member_match_record_summaries()`（跨團對戰紀錄）兩處 US1 用的
`ParticipantSummary.member_id` 填入邏輯不受此調整影響，維持原設計。詳見
research.md 頂部附註。

其餘技術決策（見 research.md）：新增一支批次查詢端點取得多位參與者的好友
關係狀態＋新隱私設定資格（避免逐列 N+1）；新增一支「以 member_id 直接發送
邀請」端點（沿用 `create_friend_request()` 既有核心邏輯，僅將尋址方式從
`user_number` 改為 `member_id`，並疊加新隱私開關檢查）；新增一個共用前端
元件 `AddFriendButtonComponent`（支援文字/圖示兩種樣式，`iconStyle`
input），在四個整合點重複使用，避免四處各自實作一套幾乎相同的按鈕/標籤
邏輯。

## Technical Context

**Language/Version**：延續既有（後端 Python 3.12 + FastAPI；前端
TypeScript / Angular 20+）。

**Primary Dependencies**：沿用既有堆疊（SQLAlchemy 2.x async ORM、Alembic
migration、Pydantic v2；前端 RxJS、ngx-translate）。**不新增任何套件**。

**Storage**：PostgreSQL（既有）。新增一個 migration：`members` 表新增
`allow_friend_invite_from_match_pages BOOLEAN NOT NULL DEFAULT true` 欄位
（FR-006/007，直接沿用 `allow_search`/`share_match_records_with_friends`
兩欄位的既有型別與預設值慣例）。不新增資料表——好友邀請沿用既有
`friend_requests` 表，不需要任何 schema 變更即可支援本功能（唯一差異只是
「用什麼欄位定位對方」，見 research.md #3）。

**Testing**：pytest（後端）：新 migration 的欄位存在性、
`PATCH /members/me/privacy-settings` 新欄位讀寫、新增的
`POST /friends/requests/by-member` 端點（成功建立、Guest/非會員目標拒絕、
新隱私開關關閉時拒絕、重複發送防呆、送出當下重新驗證即時狀態）、新增的
批次好友關係狀態查詢端點、`build_schedule_snapshot()` 的 `roster` 列表
填入 `RosterScheduleStatus.member_id`、`_build_match_record_summaries()`／
`build_member_match_records()` 兩處填入 `ParticipantSummary.member_id`
（US1）的正確性、以及**明確驗證 `_match_participants_payload()`／
`court_live_state()`／`build_round_matches_list()`，以及
`build_schedule_snapshot()` 回應中 `current_match`/`next_up` 底下的
`ParticipantSummary.member_id` 恆為 `None`**（回歸測試，確保 `member_id`
未意外外洩至公開端點與 Ably 廣播 payload，也未出現在場地比分／預告顯示
區塊）。Vitest（前端）：新增的 `AddFriendButtonComponent`（三態渲染：可
加好友按鈕／既有關係狀態標籤／完全不顯示；支援 `iconStyle` 圖示樣式）、
四個整合點的模板正確傳入 `memberId` 且自己與 Guest 一律不顯示、輪替名單
因團員加入/離開而異動後入口正確更新（FR-012）。

**Target Platform**：延續既有（Docker on AWS ECS，本地 `docker-compose`）；
本 feature 需重建/重啟 `api` 與 `frontend` 兩個容器（前者因新 migration 與
新端點，後者因新元件與新 i18n 字串）。

**Project Type**：Web application（monorepo）；本 feature 同時觸及
`apps/api` 與 `apps/web`。

**Performance Goals**：SC-001（3 次點擊內送出邀請）、SC-004（輪替名單因
團員加入/離開而異動後 1 秒內更新入口對應對象）——後者直接沿用既有 Ably
`rotation.updated`／`member.joined` 事件重新拉取 `ScheduleResponse` 的既有
機制，不新增額外的即時通道。

**Constraints**：FR-010／US3 情境 4——送出邀請的當下 MUST 由後端重新驗證
即時資格（登入會員身分、目標當下隱私設定、雙方當下關係狀態），前端顯示的
按鈕/標籤狀態僅為 UI 提示，MUST NOT 被視為授權依據。FR-013——新增的
`member_id` 欄位與「加好友」能力 MUST NOT 出現在任何無需登入即可存取的
端點回應或 Ably 廣播 payload 中（見 Summary、research.md #1）。

**Scale/Scope**：批次好友關係狀態查詢一次最多對應一頁列表可見的參與者
人數（通常個位數到數十），比照既有 `list_friends()`「單一會員好友數量小到
可以在 Python 端過濾」的既有規模假設，不需要分頁或額外索引。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | 新增/擴充的 Pydantic schema（`member_id: str \| None`、新批次查詢/新增邀請端點的 request/response）與對應 TS 介面皆完整定型，不使用 `any`；`tsc --strict`/ESLint、mypy/ruff 皆為既有 blocking check，不新增例外。 | PASS |
| II. 測試優先 | 新增的核心邏輯（送出邀請的即時資格重新驗證、`member_id` 只在三個授權路徑出現、公開路徑不變）屬於安全邊界，MUST 有對應單元/contract 測試（見 tasks.md）；純前端渲染邏輯（按鈕/標籤三態）MUST 有 Vitest 覆蓋。 | PASS |
| III. 即時性與資料一致性 | FR-012 的「換場後入口同步更新」直接沿用既有 Ably 事件驅動的 `ScheduleResponse` 重新拉取機制，不新增新的即時通道、不繞過既有「伺服器為唯一可信來源」流程。 | PASS |
| IV. 權限與安全 | 新增端點皆掛在既有 `require_verified_member`（一般成員／跨團對戰紀錄／團內對戰紀錄／賽程頁）或 `require_admin`（管理頁場地控制區塊）依賴上，不新增獨立的權限判斷邏輯；本原則明訂「無需驗證即可開啟的畫面 MUST NOT 提供管理員專屬操作」——本 feature 進一步收斂：無需驗證的公開頁面（計分板/控制板/Ably 廣播）MUST NOT 攜帶 `member_id` 或任何加好友能力，見 Summary #1、research.md #1（此為本原則精神的延伸應用，非既有條文字面涵蓋，已於此明確記錄因應方式）。 | PASS |
| V. UX 一致性（破壞性操作二次確認） | 送出好友邀請為可逆、非破壞性操作（沿用 006 既有「拒絕後可重新發送」設計），不適用本原則；關閉隱私開關同樣非破壞性（可隨時再開啟）。 | 不適用 |
| VI. 可維護性 | 新增共用前端元件 `AddFriendButtonComponent`（含 `iconStyle` input 支援兩種樣式），四個整合點（match-history／group-member-view/match-records／member-schedule 的輪替名單區塊／admin-page 的輪替名單分頁）皆呼叫同一元件，不各自重複實作；後端新增邏輯集中於 `friend` 與 `member` 兩個既有 domain，不建立新 domain、不跨 domain 直接存取彼此的 ORM model（透過既有 `get_friendship_status()` 等既有函式呼叫）。 | PASS |
| VII. 無障礙與行動裝置優先 | 新按鈕/標籤沿用既有 `friend-add`/`friend-list` 頁面的既有觸控目標與版面慣例（SC-005），不引入新的互動模式或僅靠顏色區分狀態的設計。 | PASS |
| VIII. i18n 與時區 | 新增顯示文字（按鈕文字、隱私設定新選項的 label/hint）集中於 `zh-TW.json`/`en.json`；新增錯誤碼（例如 `INVITE_VIA_MATCH_PAGES_NOT_ALLOWED`）比照既有錯誤碼慣例加入根層級 `errors` 物件，由前端 `error-interceptor`/`ApiError` 既有機制轉譯，不回傳寫死中文句子。既有 `FRIEND_REQUEST_ALREADY_PENDING`/`ALREADY_FRIENDS`/`CANNOT_FRIEND_SELF`/`MEMBER_NOT_FOUND` 等錯誤碼與 i18n key 直接重用（research.md #3）。本 feature 不涉及任何時間欄位新增。 | PASS |
| IX. 可攜性與可部署性 | 不新增套件或基礎設施，僅新增一個 Alembic migration（既有 CI/CD 部署流程已涵蓋 migration 執行）。 | PASS |
| X. 即時同步的可信來源 | FR-010——送出邀請請求 MUST 由後端在寫入當下重新查詢會員驗證狀態、目標隱私設定、雙方關係狀態，MUST NOT 信任前端頁面載入當下快取的判斷結果；此判斷邏輯與既有 `create_friend_request()` 完全相同的「後端當下查詢、不快取」模式。 | PASS |
| XI. 防機器人/防濫用 | 本 feature 新增的兩個端點皆需登入會員身分（`require_verified_member`／`require_admin`），不在原則 XI 現行範圍（會員註冊、開團）內的公開匿名端點之列——與既有 `POST /friends/requests`（006）同樣需要登入會員身分才能建立 `FriendRequest`，同一既有先例已確立此類「需登入才能建立的資源」不需 Turnstile；沿用既有好友邀請機制既有的重複發送防呆作為濫用防護。 | PASS（不適用 Turnstile） |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/026-match-record-friend-invite/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/
│   ├── friend-invite-from-pages-api.md
│   └── privacy-setting-extension-api.md
└── tasks.md             # Phase 2 output (/speckit-tasks command — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
apps/api/
├── alembic/versions/
│   └── <rev>_member_allow_friend_invite_from_match_pages.py
│                         # 新增：members.allow_friend_invite_from_match_pages
│                         #   BOOLEAN NOT NULL DEFAULT true
├── app/domains/member/
│   ├── models.py         # + Member.allow_friend_invite_from_match_pages
│   ├── schemas.py         # + PrivacySettingsRequest/Response 新欄位；
│   │                         #   + MemberPublicResponse 新欄位
│   ├── service.py         # + update_privacy_settings() 支援新欄位
│   └── router.py          # PATCH /members/me/privacy-settings 讀寫新欄位
├── app/domains/friend/
│   ├── schemas.py         # + FriendRequestCreateByMemberId、
│   │                         #   + InviteCandidateStatus/InviteCandidatesRequest/
│   │                         #   InviteCandidatesResponse
│   ├── service.py         # + create_friend_request_by_member_id()（重構
│   │                         #   create_friend_request() 抽出共用核心）；
│   │                         #   + get_invite_candidates_status()（批次查詢）
│   └── router.py          # + POST /friends/requests/by-member
│                         #   + POST /friends/invite-candidates
├── app/domains/schedule/
│   └── service.py         # build_schedule_snapshot() 建構 roster 列表的
│                         #   區塊 + 帶出 RosterEntry.member_id，餵入
│                         #   RosterScheduleStatus.member_id（實作後調整，
│                         #   見 research.md 頂部附註；current_match/next_up
│                         #   底下的 ParticipantSummary.member_id 維持
│                         #   None，_match_participants_payload()/
│                         #   court_live_state() 亦刻意不變動）
├── app/domains/schedule/schemas.py
│                         # RosterScheduleStatus + member_id: str | None = None
│                         #   （ParticipantSummary.member_id 僅由下方兩個
│                         #   對戰紀錄建構函式填入，見 data-model.md §2）
└── app/domains/group/
    └── service.py         # _build_match_record_summaries() 同步帶出
                         #   member_id（跨團版本在 member/service.py 對應函式
                         #   比照辦理）

apps/web/src/app/
├── shared/add-friend-button/          # 新增：共用元件
│   ├── add-friend-button.component.ts
│   │                         # Input: memberId, iconStyle, nickname; 內部
│   │                         #   呼叫批次查詢/送出邀請，三態渲染（按鈕/
│   │                         #   狀態標籤/不顯示），iconStyle 決定圖示或
│   │                         #   文字按鈕樣式（FR-016）
│   ├── add-friend-button.component.html
│   ├── add-friend-button.component.scss
│   └── add-friend-button.component.spec.ts
├── features/friends/friends.service.ts
│                         # + sendFriendRequestByMemberId(memberId)
│                         #   + getInviteCandidatesStatus(memberIds)
├── features/member/settings/          # 隱私設定分區新增一個開關（沿用既有
│                         #   allow_search/share_match_records_with_friends
│                         #   toggle 版面）
├── features/member/match-history/match-history.component.html
│                         # 每筆對戰紀錄的參與者名字旁 + <app-add-friend-button>
├── features/group-member-view/match-records/match-records.component.html
│                         # 同上（團內範圍）
├── features/group-member-view/member-schedule/
│   ├── member-schedule.component.html
│   │                         # 新增輪替名單區塊：每位現役團員名字旁
│   │                         #   + <app-add-friend-button [iconStyle]="true">
│   │                         #   （不含「新增訪客」等管理員專屬操作）
│   └── member-schedule.component.ts
│                         # loadInviteCandidates() 依 response.roster 批次
│                         #   查詢（原依 courts[].current_match 已移除）
└── features/group-admin/
    ├── schedule-management/
    │   ├── schedule.models.ts
    │   │                     # RosterScheduleStatus + member_id?: string | null
    │   │                     #   （ParticipantSummary 上的 member_id 欄位
    │   │                     #   保留供對戰紀錄頁使用，court-control 元件
    │   │                     #   本身完全恢復原狀，不再顯示加好友入口）
    │   └── court-control.component.html/.ts
    │                         # 恢復為 feature 前狀態，不含加好友相關程式碼
    └── admin-page/
        └── admin-page.component.html/.ts
                         # 輪替名單分頁：每位現役團員名字旁
                         #   + <app-add-friend-button [iconStyle]="true">

apps/web/src/assets/i18n/{zh-TW,en}.json
                         # + friends.addFromMatchButton/addFromMatchButtonAriaLabel
                         #   等新增文字；
                         #   + settings.privacy.allowMatchPageInviteLabel/Hint；
                         #   + errors.INVITE_VIA_MATCH_PAGES_NOT_ALLOWED
```

**Structure Decision**：後端變更集中於 `friend`／`member`／`schedule`／
`group` 四個既有 domain，不新增 domain；`friend` domain 新增兩支端點沿用
既有 service 層抽出共用邏輯的模式（比照 013 的 hook 模式）。前端新增一個
`shared/add-friend-button/` 元件，被四個既有 feature 目錄下的模板重用（其
中兩個——member-schedule 與 admin-page 的輪替名單——以 `iconStyle`/
`nickname` input 呼叫同一元件的圖示樣式分支），不在各 feature 目錄下各自
複製一份幾乎相同的邏輯——直接呼應 Constitution Check 原則 VI。

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

無違反項目，本表格從缺。
