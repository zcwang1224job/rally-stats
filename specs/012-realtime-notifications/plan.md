# Implementation Plan: 即時通知功能（Real-Time Notifications）

**Branch**: `main`（本專案未使用 per-feature git branch，延續 001-011 之既有慣例，皆直接於 `main` 上開發）| **Date**: 2026-09-07 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/012-realtime-notifications/spec.md`，交叉比對 `/specs/architecture.md` §3.2（Ably 頻道/事件既有設計）、`/specs/006-member-friends/`（`Member`/`FriendRequest` 模型、`friend/service.py` 之 `create_friend_request()`——本 feature 唯一的通知建立觸發點）、`/specs/007-live-scoreboard/`（`publish()`/`ReconnectRefetchService` 等既有即時同步基礎設施之重用對象）。

## Summary

會員 B 收到會員 A 的好友申請時，`friend/service.py` 的
`create_friend_request()` 在同一個資料庫交易內，額外建立一筆新增的
`Notification` 列（`type="friend_request"`, `source_id=friend_request.id`），
commit 成功後透過既有的 `publish()` wrapper 向新增的
`member:{B的member_id}:notifications` 頻道廣播精簡的
`notification.created` 事件。前端新增的 `NotificationService` 於登入後
訂閱該頻道；收到事件（或既有 `ReconnectRefetchService` 偵測到斷線重連）
時一律呼叫新增的 `GET /notifications/unread-count` 端點以伺服器回應
覆蓋本地未讀角標——不做本地樂觀計數，呼應憲章原則 III「重連後 MUST
強制覆蓋畫面」之既有精神。通知內容（申請人暱稱等）一律即時查詢
`FriendRequest`/`Member`，不做快照，天然滿足「已在其他管道處理過的
申請，通知仍呈現最新狀態」之 Assumption。通知本身不可個別刪除
（FR-012），僅有已讀/未讀兩種狀態，且僅在會員實際點擊/開啟時才轉為
已讀（FR-013，非開啟列表就自動已讀）。資料結構以 `type` + `source_id`
（無 DB 層 FK，多型參照）承載擴充性——未來新增「邀請入團」等通知類型
時，僅需在服務層/schema 新增對應分支，不需重新設計 `notifications`
表結構或既有的列表/未讀計數機制（FR-011）。

## Technical Context

**Language/Version**：延續 001-011（後端 Python 3.12+；前端 TypeScript /
Angular 20+）。

**Primary Dependencies**：沿用既有 FastAPI/SQLAlchemy/Alembic、Ably
REST/JS SDK 堆疊，**不新增套件**（research.md #1、#2——前端解析
`member_id` 改用既有 `GET /members/me` + localStorage 快取，不引入
`jwt-decode`）。

**Storage**：PostgreSQL，新增 **1 張資料表** `notifications`
（`member_id`/`type`/`source_id`/`read_at`/`created_at`，見
data-model.md），需要 **1 個 Alembic migration**。不修改任何既有表。

**Testing**：pytest + pytest-asyncio（後端：核心邏輯——僅通知實際
接收者 FR-009、已讀狀態原子轉換 FR-007/013、`type`+`source_id`+
`member_id` 唯一約束——MUST 有單元測試；至少一條整合測試涵蓋「送出好友
申請 → 通知建立 → Ably 事件廣播 → 列表可見 → 標記已讀」全流程）。
Vitest（前端：`NotificationService` 之未讀角標更新邏輯、
`notification.created` 事件與斷線重連皆觸發相同的覆蓋式重新拉取）。

**Target Platform**：延續既有（Docker on AWS ECS，本地
`docker-compose`）。

**Project Type**：Web application（monorepo，延續既有 `apps/api` +
`apps/web` 結構）。

**Performance Goals**：SC-001——會員在線時，2 秒內於畫面看到通知（Ably
端到端延遲，SHOULD 等級，非 blocking gate，quickstart.md 情境 1 人工
抽測，比照 007 SC-001 之既有精神）。

**Constraints**：通知資料結構（`type` + `source_id`）MUST 可擴充未來
其他通知類型而不需重新設計既有列表/未讀計數機制（FR-011，
research.md #5）；MUST NOT 提供個別刪除通知的功能（FR-012）；開啟
通知列表 MUST NOT 自動將可見項目標示為已讀（FR-013）；未讀數量指標
超過 99 則時 MUST 封頂顯示「99+」（FR-006，前端呈現邏輯，後端一律回傳
精確值）；通知端點 MUST 僅回傳/操作當前登入會員自己的資料（FR-009）。

**Scale/Scope**：單一會員的通知量與其好友申請量同數量級（小），比照
005 `match-history` 之既有 Scale/Scope 假設；本次唯一的通知來源事件為
好友申請（好友申請本身已受 006 既有規則保護，非高頻/大量寫入路徑）。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | Pydantic v2 schema 對應所有請求/回應（`NotificationSummary`/`FriendRequestNotificationDetail`/`UnreadCountResponse` 等）；`ruff`/`mypy --strict` blocking check；前端 TypeScript strict mode，`type` 欄位對應後端 Literal，新增的 `notification.models.ts` 型別與後端 schema 一一對應。 | PASS |
| II. 測試優先 | 通知非原則 II 明列的核心領域清單（開團/輪替/計分），但比照 006 好友系統之既有測試慣例，MUST 有單元測試涵蓋通知建立時機（好友申請成立必建立一筆）、僅通知實際接收者（FR-009）、已讀狀態轉換之原子防呆（FR-007/013、重複標記已讀為 no-op）、`type`+`source_id`+`member_id` 唯一約束等邊界情境；至少一條整合測試涵蓋「送出好友申請 → 通知建立 → 事件廣播 → 列表可見」全流程，依技術治理章節之一般測試要求辦理。 | PASS（列入 tasks.md 強制項） |
| III. 即時性與資料一致性 | 通知與其觸發的好友申請於同一資料庫交易內原子建立（research.md #4），commit 後才透過既有 `publish()` wrapper 廣播（憲章原則 X 之既定流程）；前端收到 `notification.created` 事件或偵測到斷線重連時，一律以伺服器回應**覆蓋**本地未讀數量，不做本地樂觀遞增（research.md #3、#6），呼應本原則「重新連線後 MUST 以伺服器回傳的最新狀態強制覆蓋畫面」之既有條文；SC-001 之 2 秒目標為 SHOULD 等級、人工抽測，非 blocking gate。 | PASS |
| IV. 權限與安全 | 通知端點一律透過既有 `require_verified_member` dependency（比照好友系統既有規則，FR-010）；標記已讀端點 MUST 驗證通知的 `member_id` 等於當前登入會員，不符一律回傳 `NOTIFICATION_NOT_FOUND`（比照 `respond_friend_request` 之「非本人視同不存在」既有慣例，不洩漏他人通知是否存在，FR-009）；新增的 `member:{member_id}:notifications` Ably 頻道沿用既有「頻道名稱不可枚舉即為存取邊界」安全模型（`member_id` 為 UUID），不需修改既有 `/realtime/ably-token` 端點的 capability 範圍（research.md #1）。 | PASS |
| V. UX 一致性（破壞性操作二次確認） | 本 feature 不含刪除/解散等破壞性操作（FR-012 明確不提供逐筆刪除）；「全部標示已讀」非資料遺失性質的操作，不需二次確認流程。 | 不適用（無破壞性操作） |
| VI. 可維護性 | 新增獨立 `notification` domain 模組（不塞進 `friend` 模組，research.md #4），符合原則 VI 之模組邊界——`friend` 模組對 `notification` 模組僅有「建立好友申請後呼叫一個函式」的單向依賴，`notification` 模組僅在 schema 組裝時匯入 `friend.schemas.FriendSummary`（比照既有跨模組 schema 重用慣例，例如 `member/service.py` 既有匯入 `group/schemas.py`），不依賴其內部實作細節。 | PASS |
| VII. 無障礙與行動裝置優先 | 已讀/未讀狀態 MUST NOT 僅以顏色區分，比照既有 `status-badge` 慣例（圖示/文字並用，tasks.md 展開）；未讀數量角標 MUST 搭配 `aria-label` 說明數量，非僅視覺角標。 | PASS（前端落實於 tasks.md 展開） |
| VIII. i18n 與時區 | 所有錯誤一律語意化代碼（新增 `NOTIFICATION_NOT_FOUND`）；通知列表/角標之顯示文字集中於語系檔，不寫死於元件；`created_at`/`read_at` 一律 `TIMESTAMPTZ`（UTC），API 回傳 ISO 8601 帶時區資訊，前端沿用既有 `DatePipe` 顯示慣例。 | PASS |
| IX. 可攜性與可部署性 | 沿用既有 Docker/AWS 設計與既有 Ably 帳號，不需額外基礎設施；新增的 1 個 Alembic migration 沿用既有 migration 執行流程。 | PASS |
| X. 即時同步的可信來源 | 通知一律由後端於好友申請建立的同一交易內寫入資料庫，commit 後才透過既有 `publish()` wrapper 廣播 `notification.created` 事件；前端 MUST 僅訂閱，沿用既有未經修改的 subscribe-only wildcard token，未引入任何前端直接發布事件的路徑。 | PASS |
| XI. 防機器人/防濫用 | 通知本身不是可由使用者直接觸發建立的公開端點——建立永遠是既有 `POST /friends/requests`（已受 006 登入+已驗證會員身分保護）的副作用；通知端點（列表/未讀數量/標記已讀）皆為讀取或狀態轉換，非「建立新資源」類型，不在原則 XI 之 Turnstile 強制範圍內。 | PASS（明確排除項，非違反） |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/012-realtime-notifications/
├── plan.md                    # 本檔案
├── research.md                # Phase 0 產出
├── data-model.md              # Phase 1 產出
├── quickstart.md              # Phase 1 產出
├── contracts/                 # Phase 1 產出
│   ├── notification-api.md
│   └── ably-events.md
└── tasks.md                   # /speckit-tasks 產出（本指令不建立）
```

### Source Code (repository root)

```text
apps/api/
├── app/
│   ├── core/
│   │   └── realtime.py            # 擴充：新增 member_notifications_channel() helper
│   └── domains/
│       ├── notification/          # 新增模組
│       │   ├── __init__.py
│       │   ├── models.py          # Notification
│       │   ├── schemas.py         # NotificationSummary/FriendRequestNotificationDetail/
│       │   │                        NotificationListResponse/UnreadCountResponse/
│       │   │                        MarkAllReadResponse
│       │   ├── service.py         # create_friend_request_notification()（friend 模組呼叫）、
│       │   │                        publish_notification_created()、list_notifications()、
│       │   │                        get_unread_count()、mark_notification_read()、
│       │   │                        mark_all_read()
│       │   └── router.py          # GET /notifications、GET /notifications/unread-count、
│       │                            POST /notifications/{id}/read、
│       │                            POST /notifications/read-all
│       └── friend/
│           └── service.py         # 擴充：create_friend_request() 於同一交易呼叫
│                                     notification.service.create_friend_request_notification()，
│                                     commit 後呼叫 publish_notification_created()
├── alembic/versions/
│   └── <new_rev>_notification_table.py  # 新增：notifications 表 + 3 個索引/約束
└── tests/
    ├── unit/domains/notification/       # 新增：test_create_notification.py、
    │                                       test_unread_count.py、test_mark_read.py、
    │                                       test_notification_scoping.py（FR-009）
    ├── contract/
    │   └── test_notification_endpoints.py  # 新增
    └── integration/
        └── test_friend_request_notification_flow.py  # 新增

apps/web/
└── src/app/
    ├── core/
    │   └── api/
    │       └── notification.models.ts     # 新增：NotificationSummary 等回應型別
    ├── features/
    │   ├── auth/
    │   │   └── auth.service.ts            # 擴充：快取/清除 member_id（research.md #2）
    │   └── notifications/                  # 新增 feature 目錄
    │       ├── notification.service.ts     # API client + Ably 訂閱 + unreadCount signal
    │       ├── notification-bell/
    │       │   └── notification-bell.component.ts   # nav-shell 內嵌角標，導向 /notifications
    │       └── notification-list/
    │           └── notification-list.component.ts   # 通知列表頁（US2/US3）
    └── core/
        └── nav-shell/
            └── nav-shell.component.ts      # 擴充：建構子呼叫 NotificationService.init()，
                                               內嵌 notification-bell
```

新增前端路由 `notifications`（`apps/web/src/app/app.routes.ts`，比照
既有 `friends` 之頂層路由慣例，非 `member/notifications`）→
`notification-list.component.ts`。

**Structure Decision**：後端新增獨立 `notification` domain 模組（不擴充
`friend` 模組，research.md #4），前端新增 `features/notifications`
目錄，兩者規模皆比照既有 `friend`/`friends` 模組；`friend/service.py`
對 `notification` 模組僅有單向呼叫依賴，符合原則 VI 之模組邊界。
`nav-shell`（既有全域元件）與 `auth.service.ts`（既有 service）僅做
最小擴充（分別是內嵌角標子元件、新增一個 localStorage 快取欄位），不
新建平行的認證/導覽機制。

## Complexity Tracking

*本 feature 無 Constitution Check 違反項目，此表格從略。*

## Post-Design Constitution Check

*Re-evaluated after Phase 1（`data-model.md`、`contracts/`、
`quickstart.md`）產出。*

設計階段的關鍵決策——(1) `notifications` 表以 `type` + `source_id`
承載擴充性、不對 `source_id` 建 FK（research.md #5，多型參照的必然
取捨，非放寬任何既有資料完整性保證，`friend_requests` 本身的完整性
約束不受影響）、(2) 通知內容一律即時查詢、不快照（research.md #5，
延續 `friend` 模組自己既有的 `list_incoming_requests()` 慣例，非新
引入的資料一致性規則）、(3) Ably 頻道沿用既有未修改的 wildcard
subscribe-only token（research.md #1，未擴大也未縮小既有 token 的
能力範圍）、(4) 前端未讀數量一律以伺服器回應覆蓋、不做本地樂觀計數
（research.md #3，直接對應憲章原則 III 既有條文，非新規則）——皆為在
不違反任何 FR 與既有 Constitution 判定的前提下確保正確性的實作細節，
未引入新的違反項目。對 `friend` 模組的唯一觸碰是在
`create_friend_request()` 內新增兩行呼叫（建立通知、發布事件），未
修改其既有簽章、錯誤代碼或業務規則。**Gate 結果維持 PASS，無需新增
Complexity Tracking 項目。**

## Assumptions

- 通知列表頁點擊 `type="friend_request"` 的通知時，一律導向既有的
  `/friends/requests` 頁面（該頁本來就列出全部待處理的收到申請），不
  額外實作「深連結並高亮特定一筆」的機制——spec 的 FR-007/US3 僅要求
  「導向可處理的畫面」，未要求特定列高亮，MVP 範圍不含此項。
- `NotificationService.init()` 的呼叫時機（`nav-shell` 建構子，
  `loggedIn()` 為真時）與登出時的取消訂閱時機，留待 tasks.md/實作階段
  依既有 `nav-shell` 生命週期慣例決定，本 plan 僅定義其職責邊界與
  API/事件邊界。
- 「99+」封頂顯示與已讀/未讀之視覺樣式（圖示/顏色搭配），比照專案既有
  `status-badge`/`--success`/`--danger` 樣式慣例，留待 tasks.md 展開
  具體元件樣式，本 plan 不預先定義 CSS 細節。
- 未來「邀請入團」通知類型上線時，會另行 `/speckit-specify` 展開該
  功能本身的規格；本 feature 僅確保 `notifications` 表結構
  （`type`/`source_id`）與服務層職責邊界不需要因此重新設計
  （FR-011，research.md #5）。
