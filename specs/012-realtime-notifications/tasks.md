# Tasks: 即時通知功能（Real-Time Notifications）

**Input**: Design documents from `/specs/012-realtime-notifications/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md（皆已存在）

**Tests**: 依 `plan.md` Constitution Check（原則 II 與技術治理章節之一般測試要求），核心邏輯（僅通知實際接收者 FR-009、已讀狀態之原子轉換 FR-007/013、`type`+`source_id`+`member_id` 唯一約束、通知建立與好友申請同一交易原子完成）MUST 有單元測試，且 MUST 有至少一條涵蓋「送出好友申請 → 通知建立 → 事件廣播 → 列表可見」的整合測試——本檔案的測試任務為強制項，非選用。

**Organization**：依 spec.md 之 3 個 User Story（US1–US3，優先序 P1/P2/P3）分階段組織，每個 Story 皆可獨立測試與交付。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行執行（不同檔案、無相依關係）
- **[Story]**: 對應 spec.md 的 US1–US3
- 每項任務皆附精確檔案路徑

## Path Conventions

沿用 `plan.md` Project Structure：`apps/api/`（FastAPI 後端）、`apps/web/`（Angular 20 前端）。monorepo 骨架已由 001 建立，本 feature 無新增 Setup 任務。

---

## Phase 1: Setup

*本 feature 無新增 Setup 任務——monorepo、CI、linting/型別檢查工具鏈已由 001 完整建立並沿用。*

---

## Phase 2: Foundational（Blocking Prerequisites）

**Purpose**：本 feature 3 個 User Story 皆依賴的資料表、模型/schema 骨架、Ably 頻道 helper、前端 `member_id` 解析基礎設施。

**⚠️ CRITICAL**：此階段完成前不可開始任何 User Story 任務。

- [X] T001 Create Alembic migration：CREATE `notifications` 表（`member_id`/`type`/`source_id`/`read_at`/`created_at`）+ `ix_notifications_member_created`/`ix_notifications_member_unread`（partial）/`uq_notifications_type_source_member` per `data-model.md` in `apps/api/alembic/versions/`
- [X] T002 [P] Create `Notification` model（新增 `apps/api/app/domains/notification/__init__.py`）in `apps/api/app/domains/notification/models.py`
- [X] T003 [P] Define Pydantic schemas skeleton（`NotificationSummary`/`FriendRequestNotificationDetail`/`NotificationListResponse`/`UnreadCountResponse`/`MarkAllReadResponse`，`FriendRequestNotificationDetail.requester` 重用 `app.domains.friend.schemas.FriendSummary`）per `data-model.md` in `apps/api/app/domains/notification/schemas.py`
- [X] T004 [P] Add `member_notifications_channel(member_id)` helper（比照既有 `court_channel()`/`group_notifications_channel()` 命名慣例）in `apps/api/app/core/realtime.py`
- [X] T005 [P] Define TypeScript models mirroring 上述 schema in `apps/web/src/app/core/api/notification.models.ts`
- [X] T006 [P] 擴充 `AuthService`——新增 localStorage 快取欄位（比照既有 `ACCESS_TOKEN_KEY`/`REFRESH_TOKEN_KEY` 慣例）儲存/讀取/清除 `member_id`：`login()`/`getMe()` 成功時寫入，`logout()`/`clearTokens()` 時清除，新增 `getCachedMemberId(): string | null`（research.md #2）in `apps/web/src/app/features/auth/auth.service.ts`

**Checkpoint**：Foundation ready — User Story 任務可以開始。

---

## Phase 3: User Story 1 - 即時收到好友申請通知 (Priority: P1) 🎯 MVP

**Goal**：會員 A 對會員 B 送出好友申請時，系統為 B 建立一則通知；B 在線時 2 秒內於畫面看到未讀角標更新（不需重新整理）；B 離線時，通知保留、下次登入以未讀狀態呈現。

**Independent Test**：由會員 A 對正在使用系統的會員 B 送出好友申請，驗證 B 能在數秒內、無需重新整理頁面看到未讀角標 +1；另驗證 B 離線期間收到的申請，下次登入後仍正確反映為未讀。

### Tests for User Story 1

- [X] T007 [P] [US1] Unit test：送出好友申請後，恰好建立一筆 `Notification`（`type="friend_request"`、`source_id=friend_request.id`、`member_id=addressee_id`）in `apps/api/tests/unit/domains/notification/test_create_notification.py`
- [X] T008 [P] [US1] Unit test：`uq_notifications_type_source_member` 約束——同一來源事件對同一會員重複呼叫建立函式時拒絕/不重複建立 in `apps/api/tests/unit/domains/notification/test_create_notification.py`
- [X] T009 [P] [US1] Unit test：僅通知實際接收者——申請人（requester）與第三方會員皆查詢不到這則通知（FR-009）in `apps/api/tests/unit/domains/notification/test_notification_scoping.py`
- [X] T010 [US1] Integration test：`POST /friends/requests` 成功 → 同一交易內建立通知 → commit 後發布 `notification.created` 至 `member:{addressee}:notifications` → `GET /notifications/unread-count` 立即反映 +1 in `apps/api/tests/integration/test_friend_request_notification_flow.py`
- [X] T011 [P] [US1] Vitest：`NotificationService` 收到 `notification.created` 事件時，呼叫 unread-count 端點並以回應**覆蓋**本地 `unreadCount`（非本地樂觀遞增）in `apps/web/src/app/features/notifications/notification.service.spec.ts`
- [X] T012 [P] [US1] Vitest：`NotificationService` 訂閱既有 `ReconnectRefetchService.onReconnect()`，觸發與上述相同的覆蓋式重新拉取 in `apps/web/src/app/features/notifications/notification.service.spec.ts`

### Implementation for User Story 1

- [X] T013 [US1] Implement `create_friend_request_notification(session, friend_request)`（僅 `session.add()`，不自行 commit，供呼叫端納入同一交易）in `apps/api/app/domains/notification/service.py` (depends on T002, T003)
- [X] T014 [US1] Implement `publish_notification_created(notification)`（呼叫既有 `app.core.realtime.publish()` + T004 之頻道 helper）in `apps/api/app/domains/notification/service.py` (depends on T004, T013)
- [X] T015 [US1] 擴充 `create_friend_request()`——`session.add(friend_request)` 後、`commit()` 前呼叫 T013；commit 成功後呼叫 T014 in `apps/api/app/domains/friend/service.py` (depends on T013, T014)
- [X] T016 [US1] Implement `get_unread_count(session, member_id)`（`SELECT COUNT(*) ... WHERE member_id=:id AND read_at IS NULL`，命中 T001 之 partial index）in `apps/api/app/domains/notification/service.py` (depends on T002)
- [X] T017 [US1] Implement `GET /notifications/unread-count` router endpoint（`require_verified_member`，FR-010）in `apps/api/app/domains/notification/router.py` (depends on T016)
- [X] T018 [US1] Register notification router in `apps/api/app/main.py` (depends on T017)
- [X] T019 [P] [US1] Angular：建立 `notification.service.ts`——`unreadCount` signal、`init()`（解析 `member_id` 見 T006 → 初始呼叫 unread-count → 訂閱 `member:{id}:notifications` 之 `notification.created` → 訂閱 `ReconnectRefetchService.onReconnect()`，兩者皆觸發覆蓋式重新拉取，research.md #3）in `apps/web/src/app/features/notifications/notification.service.ts` (depends on T005, T006)
- [X] T020 [P] [US1] Angular：建立 `notification-bell.component.ts`/`.html`——顯示 `unreadCount()`（超過 99 封頂顯示「99+」，FR-006）、`aria-label` 說明數量（憲章原則 VII）、點擊導向 `/notifications` in `apps/web/src/app/features/notifications/notification-bell/`
- [X] T021 [US1] 擴充 `nav-shell.component.ts` 建構子——`loggedIn()` 為真時呼叫 `NotificationService.init()`；`nav-shell.component.html` 內嵌 `notification-bell` in `apps/web/src/app/core/nav-shell/nav-shell.component.ts`, `apps/web/src/app/core/nav-shell/nav-shell.component.html` (depends on T019, T020)

**Checkpoint**：US1 完整可運作——好友申請即時觸發通知、未讀角標即時更新、離線期間收到的通知下次登入仍正確呈現為未讀。

---

## Phase 4: User Story 2 - 查看與管理通知列表 (Priority: P2)

**Goal**：會員能開啟通知列表，依時間新到舊看到全部通知並分辨已讀/未讀；能一次將所有通知標示為已讀。

**Independent Test**：讓某會員累積數則通知（含已讀與未讀），開啟通知列表驗證排序與已讀/未讀狀態正確；使用「全部標示已讀」後未讀數量歸零。

### Tests for User Story 2

- [X] T022 [P] [US2] Unit test：`list_notifications()` 依 `created_at` 新到舊排序，`read` 欄位正確反映 `read_at` 是否為 `NULL`（FR-004/005）in `apps/api/tests/unit/domains/notification/test_list_notifications.py`
- [X] T023 [P] [US2] Unit test：`list_notifications()` 本身（純查詢）MUST NOT 改變任何一則的 `read_at`（FR-013）in `apps/api/tests/unit/domains/notification/test_list_notifications.py`
- [X] T024 [P] [US2] Unit test：`mark_all_read()` 將所有未讀轉為已讀並回傳 `marked_count`；已無未讀時重複呼叫回傳 `0`（FR-008，冪等）in `apps/api/tests/unit/domains/notification/test_mark_read.py`
- [X] T025 [P] [US2] Contract test for `GET /notifications` per `contracts/notification-api.md` in `apps/api/tests/contract/test_notification_endpoints.py`
- [X] T026 [P] [US2] Contract test for `POST /notifications/read-all` per `contracts/notification-api.md` in `apps/api/tests/contract/test_notification_endpoints.py`

### Implementation for User Story 2

- [X] T027 [US2] Implement `list_notifications(session, member_id, page)`——分頁查詢 + 批次查詢對應 `FriendRequest`/`Member`（requester）組裝 `friend_request` 欄位，比照 `list_incoming_requests()` 既有批次查詢慣例 in `apps/api/app/domains/notification/service.py` (depends on T002, T003)
- [X] T028 [US2] Implement `mark_all_read(session, member_id)`——`UPDATE notifications SET read_at = now() WHERE member_id = :id AND read_at IS NULL`，回傳 `rowcount` in `apps/api/app/domains/notification/service.py` (depends on T002)
- [X] T029 [US2] Implement `GET /notifications` router endpoint in `apps/api/app/domains/notification/router.py` (depends on T027)
- [X] T030 [US2] Implement `POST /notifications/read-all` router endpoint in `apps/api/app/domains/notification/router.py` (depends on T028)
- [X] T031 [P] [US2] Angular：擴充 `notification.service.ts`——`list(page)`/`markAllRead()` 方法，成功後以回應更新 `unreadCount` in `apps/web/src/app/features/notifications/notification.service.ts` (depends on T019)
- [X] T032 [P] [US2] Angular：建立 `notification-list.component.ts`/`.html`——通知列表（已讀/未讀狀態圖示+文字並用，非僅顏色，憲章原則 VII）、「全部標示已讀」按鈕、分頁（比照既有 `match-history`/`friend-list` 分頁元件慣例）in `apps/web/src/app/features/notifications/notification-list/`
- [X] T033 [US2] 新增路由 `notifications` → `notification-list.component.ts`（比照既有 `friends` 頂層路由慣例，非 `member/notifications`）in `apps/web/src/app/app.routes.ts` (depends on T032)
- [X] T034 [P] [US2] i18n：新增 `nav.notifications`/`notifications.*` 系列語系鍵值 in `apps/web/src/assets/i18n/zh-TW.json`

**Checkpoint**：US1–US2 皆可獨立運作——通知列表可瀏覽全部歷史、已讀/未讀正確、全部標示已讀正常運作。

---

## Phase 5: User Story 3 - 點擊通知直接前往相關內容 (Priority: P3)

**Goal**：會員點擊一則未讀的好友申請通知時，該則轉為已讀，並直接導向可查看/處理該筆好友申請的畫面。

**Independent Test**：點擊一則未讀的好友申請通知，驗證系統直接導向 `/friends/requests`，且該通知同時轉為已讀。

### Tests for User Story 3

- [X] T035 [P] [US3] Unit test：`mark_notification_read()`——首次呼叫將 `read_at` 從 `NULL` 轉為時間戳，重複呼叫維持已讀且不報錯（冪等）；`member_id` 不符時拒絕（`NOTIFICATION_NOT_FOUND`，不洩漏是否存在）in `apps/api/tests/unit/domains/notification/test_mark_read.py`
- [X] T036 [P] [US3] Contract test for `POST /notifications/{notification_id}/read`（含非本人通知回傳 404）per `contracts/notification-api.md` in `apps/api/tests/contract/test_notification_endpoints.py`

### Implementation for User Story 3

- [X] T037 [US3] Implement `mark_notification_read(session, member_id, notification_id)`——先查詢確認該筆通知存在且 `member_id` 相符（不符/不存在一律 `NOTIFICATION_NOT_FOUND`），再以 `UPDATE ... WHERE id=:id AND read_at IS NULL` 完成已讀轉換（`rowcount=0` 代表已經是已讀，非錯誤）in `apps/api/app/domains/notification/service.py` (depends on T002)
- [X] T038 [US3] Implement `POST /notifications/{notification_id}/read` router endpoint；於 `apps/web/src/assets/i18n/zh-TW.json` 的 `errors` 區塊新增 `NOTIFICATION_NOT_FOUND` 對應鍵值 in `apps/api/app/domains/notification/router.py` (depends on T037)
- [X] T039 [P] [US3] Angular：`notification-list.component.ts` 點擊事件——呼叫 `markRead(id)`，成功後依 `type` 導向對應畫面（`"friend_request"` → `/friends/requests`）in `apps/web/src/app/features/notifications/notification-list/notification-list.component.ts` (depends on T031, T032)

**Checkpoint**：US1–US3 全部皆可獨立運作——通知從建立、即時提示、列表瀏覽、到點擊導向處理，完整閉環。

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**：跨 User Story 的收尾與驗證。

- [X] T040 [P] 依 `quickstart.md` 全部 4 個情境 + 2 個 Edge Case 人工驗證實際運作（含情境 1 之 2 秒內同步人工抽測）
- [X] T041 [P] Security review：確認通知端點皆套用 `require_verified_member`（FR-010）；`NOTIFICATION_NOT_FOUND` 不洩漏他人通知是否存在（T037/T038）；`member:{member_id}:notifications` 頻道沿用既有未修改的 wildcard subscribe-only token，未擴大 Ably token 能力範圍（research.md #1）
- [X] T042 [P] Accessibility review：已讀/未讀狀態 MUST NOT 僅靠顏色區分（憲章原則 VII）；未讀角標 MUST 有 `aria-label` 說明數量，非僅視覺角標（FR-006）
- [X] T043 補齊本 feature 新增之 FastAPI router 端點（`apps/api/app/domains/notification/router.py`）之 `response_model`/docstring
- [X] T044 [P] Integration test：完整生命週期「送出好友申請 → 通知建立 → 事件廣播 → 列表顯示 → 點擊標記已讀並導向 → 全部標示已讀」in `apps/api/tests/integration/test_friend_request_notification_flow.py`（延伸 T010 之測試檔案，補齊 US2/US3 涵蓋的部分；憲章原則 II 之強制整合測試要求）

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：無任務，略過。
- **Foundational (Phase 2)**：`notifications` 表 + 前後端 schema 骨架 + `member_id` 快取基礎設施；**封鎖**所有 User Story。
- **User Stories (Phase 3–5)**：皆依賴 Foundational 完成。
- **Polish (Phase 6)**：依賴所有欲交付的 User Story 完成。

### User Story Dependencies

- **US1（P1，MVP）**：Foundational 完成後即可開始，無其他 Story 相依；建立通知建立/發布流程（T013/T014）與 `NotificationService`（T019）供 US2/US3 擴充重用。
- **US2（P2）**：僅依賴 Foundational 之 `Notification` 模型/schema——`list_notifications()`/`mark_all_read()`（T027/T028）在程式碼層級不呼叫 US1 之建立/發布邏輯，僅讀取同一張表（資料相依，非程式碼相依）；前端擴充 US1 已建立的 `notification.service.ts`（T019）。
- **US3（P3）**：`mark_notification_read()`（T037）為獨立程式碼，不依賴 US1/US2 之服務函式；但前端整合（T039）依賴 US2 之 `notification-list.component.ts`（T032）已存在才能加上點擊行為。
- 建議依 P1→P2→P3 順序（US1→US2→US3）依序實作與驗證。

### Within Each User Story

- Tests MUST 先寫且先失敗，再進行 Implementation。
- Service（含跨模組串接、既有 `publish()` 重用）→ Router endpoints → 前端整合。
- Story 完成（含 Checkpoint 驗證）才進入下一優先序 Story。

### Parallel Opportunities

- Phase 2 之 T002–T006 皆可平行執行（不同檔案，僅 T001 之 migration 需先於 T002 前置——實務上 model 定義與 migration 撰寫常同時進行，但 model 匯入需等資料表存在才能通過測試）。
- 同一 User Story 內標記 `[P]` 的 Tests 可平行執行。
- 若有多位開發者：US1 完成後，US2 可立即平行認領（僅依賴 Foundational）；US3 建議在 US2 的 `notification-list.component.ts`（T032）就緒後再認領前端整合任務（T039），後端部分（T037/T038）可與 US2 同時平行進行。

---

## Parallel Example: User Story 1

```bash
# 平行執行 US1 的所有測試任務：
Task: "Unit test：送出好友申請後恰好建立一筆 Notification in apps/api/tests/unit/domains/notification/test_create_notification.py"
Task: "Unit test：uq_notifications_type_source_member 約束 in apps/api/tests/unit/domains/notification/test_create_notification.py"
Task: "Unit test：僅通知實際接收者 in apps/api/tests/unit/domains/notification/test_notification_scoping.py"
Task: "Vitest：notification.created 事件觸發覆蓋式重新拉取 in apps/web/src/app/features/notifications/notification.service.spec.ts"
Task: "Vitest：斷線重連觸發相同的覆蓋式重新拉取 in apps/web/src/app/features/notifications/notification.service.spec.ts"
```

---

## Implementation Strategy

### MVP First（僅 User Story 1）

1. 完成 Phase 2：Foundational（資料表 + schema 骨架 + `member_id` 快取）
2. 完成 Phase 3：User Story 1
3. **停下並驗證**：獨立測試 US1（`quickstart.md` 情境 1）
4. 若已可展示，即可部署/demo（「好友申請 → 即時通知 → 未讀角標」MVP 閉環至此完整）

### Incremental Delivery

1. Foundational 完成 → schema/資料表就緒
2. 加入 US1 → 獨立測試 → Demo（MVP：好友申請即時通知完整閉環！）
3. 加入 US2 → 獨立測試 → Demo（通知列表可回顧完整歷史）
4. 加入 US3 → 獨立測試 → Demo（點擊通知直接處理，完整使用者體驗閉環）
5. 每個 Story 皆為既有功能疊加價值，不破壞先前 Story

### Parallel Team Strategy

多位開發者情境：

1. 團隊共同完成 Foundational
2. Foundational 完成後：
   - 開發者 A：US1（通知建立與即時提示，MVP）
   - 開發者 B：待 US1 的 `Notification` 模型/schema 就緒後（Foundational 完成即可，不需等 US1 完整完成），平行進行 US2（通知列表，程式碼層級無相依）
3. US3 建議在 US2 的 `notification-list.component.ts` 就緒後認領——後端部分可提早與 US2 平行進行

---

## Notes

- `[P]` 任務 = 不同檔案、無相依關係。
- `[Story]` 標籤將任務對應回 spec.md 的特定 User Story，供追溯。
- US2/US3 之核心邏輯與 US1 各自獨立（不同函式、不同查詢），僅共用同一張 `notifications` 表與同一個 `NotificationService`，避免誤判為需要重新設計。
- 實作前先確認測試會失敗（TDD，呼應 constitution 原則 II）。
- 建議每完成一項任務或一組邏輯相關任務即 commit 一次。
- 可在任一 Checkpoint 停下獨立驗證該 Story，不需等待後續 Story 完成。
- 避免：模糊任務描述、多任務同時修改同一檔案造成衝突、破壞 Story 獨立性的跨 Story 相依。
