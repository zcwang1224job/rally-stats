# Tasks: 邀請好友加入組團（Invite Friends to Join a Group）

**Input**: Design documents from `/specs/013-group-invite-friends/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md（皆已存在）

**Tests**: 依 `plan.md` Constitution Check（原則 II 與技術治理章節之一般測試要求），核心邏輯（`GroupInvite` 四態狀態機、`join_group()` 之 `skip_password` 行為、額滿失敗之「狀態不變+通知團長」組合行為、好友關係解除/團解散觸發自動失效、唯一性約束、僅本人可查看/操作之授權邊界）MUST 有單元測試，且 MUST 有至少一條涵蓋「送出邀請 → 通知 → 接受」的整合測試——本檔案的測試任務為強制項，非選用。

**Organization**：依 spec.md 之 3 個 User Story（US1–US3，優先序 P1/P2/P3）分階段組織。US2 依賴 US1 已建立的 `GroupInvite`/通知（獨立測試時需先用 US1 的服務函式建立一筆邀請）；US3 依賴 US1（唯一性/清單）與 US2（`accept_invite()`——額滿通知是在該函式內新增的分支）；三者皆可獨立驗證其新增的行為，但程式碼上有先後累加關係（比照 007 之 US1→US2→US3 依賴模式）。

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

**Purpose**：本 feature 3 個 User Story 皆依賴的資料表、模型/schema 骨架、既有回應形狀的擴充欄位。

**⚠️ CRITICAL**：此階段完成前不可開始任何 User Story 任務。

- [X] T001 Create Alembic migration：CREATE `group_invites` 表（`group_id`/`inviter_member_id`/`invitee_member_id`/`status`/`created_at`/`updated_at`）+ `ux_group_invites_pending_invitee`（partial unique）/`ix_group_invites_group_invitee_created` per `data-model.md` in `apps/api/alembic/versions/`
- [X] T002 [P] Create `GroupInvite` model（新增 `apps/api/app/domains/group_invite/__init__.py`）in `apps/api/app/domains/group_invite/models.py`
- [X] T003 [P] Define Pydantic schemas skeleton（`InvitableFriendSummary`/`InvitableFriendsResponse`/`SendGroupInviteRequest`/`SendGroupInviteResponse`/`GroupInviteDetailResponse`/`AcceptGroupInviteResponse`/`DeclineGroupInviteResponse`）per `data-model.md` in `apps/api/app/domains/group_invite/schemas.py`
- [X] T004 [P] 擴充 `GroupPublicResponse` 新增 `created_by_member: bool` in `apps/api/app/domains/group/schemas.py`；於既有 `_to_public()` 填入 `group.created_by_member_id is not None` in `apps/api/app/domains/group/router.py`
- [X] T005 [P] 擴充通知 schema——`NotificationSummary.type` 加入 `"group_invite"`/`"group_invite_capacity_full"`，新增 `GroupInviteNotificationDetail`（`invite_id`/`group_id`/`group_name`/`status`/`inviter`/`invitee`，後兩者重用 `FriendSummary`）與 `NotificationSummary.group_invite` 欄位 in `apps/api/app/domains/notification/schemas.py`
- [X] T006 [P] Define TypeScript models mirroring `group_invite` schemas in `apps/web/src/app/core/api/group-invite.models.ts`
- [X] T007 [P] 擴充 `apps/web/src/app/core/api/notification.models.ts`——`NotificationType` 聯合型別、`GroupInviteNotificationDetail`、`NotificationSummary.group_invite` 欄位
- [X] T008 [P] 擴充 `apps/web/src/app/features/group-admin/group-admin.models.ts`——`GroupPublic.created_by_member: boolean`

**Checkpoint**：Foundation ready — User Story 任務可以開始。

---

## Phase 3: User Story 1 - 團長從好友列表發送邀請 (Priority: P1) 🎯 MVP

**Goal**：團長於管理頁面查看自己完整的好友列表（附帶每位好友的邀請狀態），對尚未邀請、也還不是本團成員的好友送出邀請；重複發送、對已在團內的好友發送皆被擋下。

**Independent Test**：團長於管理頁面的邀請區塊選擇一位好友並送出邀請，驗證系統成功記錄這筆邀請、受邀好友收到通知，且不會重複發送給同一位仍在等待回覆的好友。

### Tests for User Story 1

- [X] T009 [P] [US1] Unit test：`send_invite()` 對已確立好友關係、尚未加入本團、無待處理邀請的對象，成功建立一筆 `pending` 的 `GroupInvite` 並建立對應通知 in `apps/api/tests/unit/domains/group_invite/test_send_invite.py`
- [X] T010 [P] [US1] Unit test：`send_invite()` 拒絕邀請非好友關係的會員（`NOT_FRIENDS`）in `apps/api/tests/unit/domains/group_invite/test_send_invite.py`
- [X] T011 [P] [US1] Unit test：`send_invite()` 拒絕對同一位好友重複發送仍待回覆的邀請（`INVITE_ALREADY_PENDING`，FR-003）in `apps/api/tests/unit/domains/group_invite/test_send_invite.py`
- [X] T012 [P] [US1] Unit test：`send_invite()` 拒絕邀請已是本團現有成員的好友（`ALREADY_GROUP_MEMBER`，FR-004）in `apps/api/tests/unit/domains/group_invite/test_send_invite.py`
- [X] T013 [P] [US1] Unit test：`send_invite()` 對非會員建立（匿名建團）的團拒絕發送（`GROUP_NOT_MEMBER_CREATED`，FR-012）in `apps/api/tests/unit/domains/group_invite/test_send_invite.py`
- [X] T014 [P] [US1] Unit test：`list_invitable_friends()` 回傳團長完整好友列表，`invite_status` 正確反映 `not_invited`/`pending`/`already_member`（含 `already_member` 優先於底層邀請歷史，research.md #8）in `apps/api/tests/unit/domains/group_invite/test_list_invitable_friends.py`
- [X] T015 [P] [US1] Contract test for `GET /groups/{group_id}/invitable-friends` per `contracts/group-invite-api.md` in `apps/api/tests/contract/test_group_invite_endpoints.py`
- [X] T016 [P] [US1] Contract test for `POST /groups/{group_id}/invites`（含全部錯誤代碼）per `contracts/group-invite-api.md` in `apps/api/tests/contract/test_group_invite_endpoints.py`

### Implementation for User Story 1

- [X] T017 [US1] Implement `send_invite(session, group, inviter_member_id, invitee_member_id)`——依序檢查 `group.created_by_member_id`/好友關係（重用 `friend.service.get_friendship_status`）/已在團內（查 `RosterEntry`）/唯一性，建立 `GroupInvite` 並呼叫 `notification.service` 建立+發布 `type="group_invite"` 通知 in `apps/api/app/domains/group_invite/service.py` (depends on T002, T003)
- [X] T018 [US1] Implement `list_invitable_friends(session, group)`——重用 `friend.service.list_friends` 之好友查詢邏輯，逐一組裝 `invite_status`（research.md #8）in `apps/api/app/domains/group_invite/service.py`
- [X] T019 [US1] Implement `POST /groups/{group_id}/invites` router endpoint（`require_admin`）in `apps/api/app/domains/group_invite/router.py` (depends on T017)
- [X] T020 [US1] Implement `GET /groups/{group_id}/invitable-friends` router endpoint（`require_admin`）in `apps/api/app/domains/group_invite/router.py` (depends on T018)
- [X] T021 [US1] Register `group_invite` router in `apps/api/app/main.py` (depends on T019, T020)
- [X] T022 [US1] 擴充 `_build_notification_summaries()` 新增 `type="group_invite"` 分支——即時查詢 `GroupInvite`+`Group`+`Member`（邀請人/受邀人）組裝 `GroupInviteNotificationDetail` in `apps/api/app/domains/notification/service.py` (depends on T005)
- [X] T023 [P] [US1] Angular：擴充 `group-admin.service.ts` 新增 `listInvitableFriends()`/`sendInvite()` API 呼叫 in `apps/web/src/app/features/group-admin/group-admin.service.ts` (depends on T006)
- [X] T024 [US1] Angular：`admin-page.component.ts` 新增 `'invites'` `AdminSection`，`group.created_by_member` 為真時載入 `listInvitableFriends()` in `apps/web/src/app/features/group-admin/admin-page/admin-page.component.ts` (depends on T023)
- [X] T025 [US1] Angular：`admin-page.component.html` 新增邀請好友分頁——好友清單（暱稱+使用者編號+狀態徽章+送出邀請按鈕，`not_invited` 才可點擊），僅 `group.created_by_member` 為真時顯示分頁本身（FR-012）in `apps/web/src/app/features/group-admin/admin-page/admin-page.component.html` (depends on T024)

**Checkpoint**：US1 完整可運作——團長可從好友列表送出邀請，受邀好友即時收到通知，重複/已在團內的好友皆正確擋下。

---

## Phase 4: User Story 2 - 好友接受或拒絕邀請 (Priority: P2)

**Goal**：受邀好友點擊通知，查看邀請詳情，選擇接受（略過通關密碼直接加入）或拒絕。

**Independent Test**：受邀好友收到邀請通知後，分別測試「接受」使其成為該團成員（即使該團設有密碼），以及「拒絕」使邀請結束但不加入，兩條路徑互不影響。

### Tests for User Story 2

- [X] T026 [P] [US2] Unit test：`join_group()` 新增的 `skip_password=True` 略過密碼驗證直接成功；`skip_password` 預設 `False` 時既有呼叫端行為不變（回歸測試）in `apps/api/tests/unit/domains/group/test_join_skip_password.py`
- [X] T027 [P] [US2] Unit test：`get_invite_detail()` 回傳即時狀態；非受邀人本人查看時拒絕（`GROUP_INVITE_NOT_FOUND`，不洩漏存在性）in `apps/api/tests/unit/domains/group_invite/test_invite_detail.py`
- [X] T028 [P] [US2] Unit test：`accept_invite()` 成功路徑——呼叫 `join_group(skip_password=True)` 建立 `RosterEntry`、`GroupInvite` 轉為 `accepted`，即使該團設有密碼也不需密碼（Clarifications Q1）in `apps/api/tests/unit/domains/group_invite/test_accept_invite.py`
- [X] T029 [P] [US2] Unit test：`accept_invite()` 對非 `pending` 狀態的邀請拒絕（`GROUP_INVITE_NOT_PENDING`）；非受邀人本人操作時拒絕（`GROUP_INVITE_NOT_FOUND`）in `apps/api/tests/unit/domains/group_invite/test_accept_invite.py`
- [X] T030 [P] [US2] Unit test：`decline_invite()` 將 `pending` 邀請轉為 `declined`；對非 `pending`/非本人操作拒絕 in `apps/api/tests/unit/domains/group_invite/test_decline_invite.py`
- [X] T031 [P] [US2] Contract test for `GET /group-invites/{invite_id}` per `contracts/group-invite-api.md` in `apps/api/tests/contract/test_group_invite_endpoints.py`
- [X] T032 [P] [US2] Contract test for `POST /group-invites/{invite_id}/accept`（含密碼略過、人數上限、一人一團等錯誤代碼）per `contracts/group-invite-api.md` in `apps/api/tests/contract/test_group_invite_endpoints.py`
- [X] T033 [P] [US2] Contract test for `POST /group-invites/{invite_id}/decline` per `contracts/group-invite-api.md` in `apps/api/tests/contract/test_group_invite_endpoints.py`
- [X] T034 [US2] Integration test：送出邀請 → 受邀好友收到通知 → 查看詳情 → 接受（略過密碼）→ 成為正式成員；另測拒絕路徑不加入 in `apps/api/tests/integration/test_group_invite_flow.py`

### Implementation for User Story 2

- [X] T035 [US2] 擴充 `join_group()` 新增 keyword-only `skip_password: bool = False` 參數，密碼驗證改為 `if not skip_password and not verify_password(...)`（research.md #3）in `apps/api/app/domains/group/service.py` (depends on T026)
- [X] T036 [US2] Implement `get_invite_detail(session, member_id, invite_id)` in `apps/api/app/domains/group_invite/service.py` (depends on T002, T003)
- [X] T037 [US2] Implement `accept_invite(session, member_id, invite_id)`——驗證受邀人本人與 `pending` 狀態後呼叫 `join_group(..., skip_password=True)`，成功則將 `GroupInvite` 轉為 `accepted` in `apps/api/app/domains/group_invite/service.py` (depends on T035, T036)
- [X] T038 [US2] Implement `decline_invite(session, member_id, invite_id)` in `apps/api/app/domains/group_invite/service.py`
- [X] T039 [US2] Implement `GET /group-invites/{invite_id}` router endpoint（`require_verified_member`）in `apps/api/app/domains/group_invite/router.py` (depends on T036)
- [X] T040 [US2] Implement `POST /group-invites/{invite_id}/accept` router endpoint in `apps/api/app/domains/group_invite/router.py` (depends on T037)
- [X] T041 [US2] Implement `POST /group-invites/{invite_id}/decline` router endpoint in `apps/api/app/domains/group_invite/router.py` (depends on T038)
- [X] T042 [P] [US2] Angular：建立 `group-invite.service.ts`——`getDetail()`/`accept()`/`decline()` API 呼叫 in `apps/web/src/app/features/group-invites/group-invite.service.ts` (depends on T006)
- [X] T043 [P] [US2] Angular：建立 `group-invite-detail.component.ts`/`.html`/`.scss`——顯示團名/邀請人，接受/拒絕按鈕（無二次確認，比照好友申請既有慣例）in `apps/web/src/app/features/group-invites/group-invite-detail/` (depends on T042)
- [X] T044 [US2] 新增路由 `group-invites/:inviteId` → `group-invite-detail.component.ts` in `apps/web/src/app/app.routes.ts` (depends on T043)
- [X] T045 [US2] 擴充 `notification-list.component.ts` 的 `open()`——`type === 'group_invite'` 時導向 `/group-invites/:inviteId` in `apps/web/src/app/features/notifications/notification-list/notification-list.component.ts` (depends on T044)

**Checkpoint**：US1–US2 皆可獨立運作——邀請送出、通知、查看詳情、接受（略過密碼）/拒絕全流程完整。

---

## Phase 5: User Story 3 - 團長查看已發送邀請的狀態 (Priority: P3)

**Goal**：團長於管理頁面看到每位受邀好友的最新邀請狀態（含額滿失敗即時通知、好友關係解除/團解散導致的自動失效），拒絕不永久封鎖再次邀請。

**Independent Test**：團長對三位好友分別送出邀請，其中一位接受、一位拒絕、一位因額滿而接受失敗，驗證管理頁面正確顯示對應狀態且團長收到額滿失敗的通知；另測好友關係解除後該筆邀請自動失效。

### Tests for User Story 3

- [X] T046 [P] [US3] Unit test：`accept_invite()` 因 `GROUP_FULL` 失敗時，`GroupInvite` 狀態維持 `pending`（不轉為其他終態），且建立一則 `type="group_invite_capacity_full"` 通知給團長（FR-013，Clarifications Q2）in `apps/api/tests/unit/domains/group_invite/test_accept_invite.py`
- [X] T047 [P] [US3] Unit test：`invalidate_pending_invites_for_member_pair()`——將指定會員配對間所有 `pending` 的 `GroupInvite` 轉為 `invalidated`，不影響已是終態的邀請 in `apps/api/tests/unit/domains/group_invite/test_invalidation.py`
- [X] T048 [P] [US3] Unit test：`invalidate_pending_invites_for_group()`——將指定團的所有 `pending` 的 `GroupInvite` 轉為 `invalidated` in `apps/api/tests/unit/domains/group_invite/test_invalidation.py`
- [X] T049 [P] [US3] Unit test：`list_invitable_friends()` 於好友先前 `declined` 後被重新邀請時，正確反映最新一筆為 `pending`（FR-008，好友歷史不永久封鎖再邀）in `apps/api/tests/unit/domains/group_invite/test_list_invitable_friends.py`
- [X] T050 [US3] Integration test：對已額滿的團送出邀請、受邀好友接受失敗 → 團長即時收到通知 → 邀請狀態列表仍顯示待回覆 in `apps/api/tests/integration/test_group_invite_flow.py`
- [X] T051 [US3] Integration test：待回覆邀請期間解除好友關係（`DELETE /friends/{friend_request_id}`）→ 該筆邀請自動失效 → 後續接受失敗（`GROUP_INVITE_NOT_PENDING`）in `apps/api/tests/integration/test_group_invite_flow.py`
- [X] T052 [US3] Integration test：待回覆邀請期間團被解散（`POST /groups/{group_id}/disband`）→ 該筆邀請自動失效 in `apps/api/tests/integration/test_group_invite_flow.py`

### Implementation for User Story 3

- [X] T053 [US3] 擴充 `accept_invite()`——`join_group()` 拋出 `GROUP_FULL` 時攔截，建立+發布 `group_invite_capacity_full` 通知給 `inviter_member_id`，`GroupInvite` 狀態不變，重新拋出原錯誤（research.md #4）in `apps/api/app/domains/group_invite/service.py` (depends on T037)
- [X] T054 [US3] Implement `invalidate_pending_invites_for_member_pair(session, member_a, member_b)` in `apps/api/app/domains/group_invite/service.py`
- [X] T055 [US3] Implement `invalidate_pending_invites_for_group(session, group_id)` in `apps/api/app/domains/group_invite/service.py`
- [X] T056 [US3] 擴充 `disband_group()` 新增 `invalidate_pending_invites: InvalidatePendingInvitesHook | None = None` 參數，於既有邏輯內同一交易呼叫（research.md #2）in `apps/api/app/domains/group/service.py` (depends on T055)
- [X] T057 [US3] 擴充 `unfriend()` 新增 `invalidate_pending_invites: InvalidatePendingInvitesForPairHook | None = None` 參數 in `apps/api/app/domains/friend/service.py` (depends on T054)
- [X] T058 [US3] `group/router.py` 的 `disband` 端點 import 並傳入 `group_invite.service.invalidate_pending_invites_for_group` in `apps/api/app/domains/group/router.py` (depends on T056)
- [X] T059 [US3] `friend/router.py` 的 unfriend 端點 import 並傳入 `group_invite.service.invalidate_pending_invites_for_member_pair` in `apps/api/app/domains/friend/router.py` (depends on T057)
- [X] T060 [US3] `scheduler/auto_disband.py` 的 `sweep_idle_groups()` 傳入同一個 hook，涵蓋自動閒置解散路徑 in `apps/api/app/scheduler/auto_disband.py` (depends on T056)
- [X] T061 [US3] 擴充 `_build_notification_summaries()` 新增 `type="group_invite_capacity_full"` 分支（重用 T022 已建立的 `GroupInvite` 查詢邏輯）in `apps/api/app/domains/notification/service.py` (depends on T022, T053)
- [X] T062 [P] [US3] Angular：`notification-list.component.ts` 顯示 `group_invite_capacity_full` 類型的通知文案，點擊導向管理頁邀請分頁（而非受邀好友的接受/拒絕畫面）in `apps/web/src/app/features/notifications/notification-list/notification-list.component.ts` (depends on T045)
- [X] T063 [P] [US3] Angular：`admin-page.component.html` 邀請分頁的狀態徽章區分 `declined`/`invalidated`/`already_member`（圖示+文字並用，非僅顏色，憲章原則 VII）in `apps/web/src/app/features/group-admin/admin-page/admin-page.component.html` (depends on T025)

**Checkpoint**：US1–US3 全部皆可獨立運作——邀請的完整生命週期（送出/接受/拒絕/額滿失敗通知/自動失效）與可視性皆完整。

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**：跨 User Story 的收尾與驗證。

- [X] T064 [P] 依 `quickstart.md` 全部 5 個情境 + 2 個 Edge Case 人工驗證實際運作
- [X] T065 [P] Security review：確認 `POST/GET /groups/{group_id}/invites`、`GET .../invitable-friends` 皆套用 `require_admin`；`GET/POST /group-invites/{id}/*` 皆套用 `require_verified_member` 且驗證操作者為受邀人本人；`GROUP_INVITE_NOT_FOUND` 不洩漏他人邀請是否存在；`join_group()` 的 `skip_password=True` 僅 `accept_invite()` 這一個呼叫端使用，其餘既有呼叫端仍為預設 `False`
- [X] T066 [P] Accessibility review：邀請狀態徽章（待回覆/已接受/已拒絕/已失效/已在團內）MUST NOT 僅靠顏色區分（憲章原則 VII）
- [X] T067 補齊本 feature 新增之 FastAPI router 端點（`apps/api/app/domains/group_invite/router.py`）之 `response_model`/docstring
- [X] T068 [P] Integration test：完整生命週期回歸「送出邀請 → 拒絕 → 重新送出 → 接受」證明拒絕不永久封鎖再邀（FR-008）in `apps/api/tests/integration/test_group_invite_flow.py`（憲章原則 II 之強制整合測試要求）

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：無任務，略過。
- **Foundational (Phase 2)**：`group_invites` 表 + 前後端 schema 骨架 + 既有回應形狀擴充欄位；**封鎖**所有 User Story。
- **User Stories (Phase 3–5)**：US1 依賴 Foundational；US2 依賴 US1（需要已存在的 `GroupInvite`/通知才能測試接受/拒絕，且 US2 建立的 `accept_invite()`/`decline_invite()` 是 US3 唯一會擴充的既有函式）；US3 依賴 US1（唯一性/清單顯示）與 US2（`accept_invite()`）。
- **Polish (Phase 6)**：依賴所有欲交付的 User Story 完成。

### User Story Dependencies

- **US1（P1，MVP）**：Foundational 完成後即可開始，無其他 Story 相依；建立 `send_invite()`/`list_invitable_friends()`（T017/T018）與管理頁邀請分頁骨架，供 US3 直接擴充狀態顯示。
- **US2（P2）**：依賴 US1 的 `GroupInvite` 建立流程才能有邀請可供接受/拒絕（資料相依）；新增 `join_group()` 之 `skip_password` 參數（T035）與 `accept_invite()`/`decline_invite()`（T037/T038）——後者是 US3 額滿通知（T053）與失效檢查唯一會擴充的既有函式（程式碼相依）。
- **US3（P3）**：直接擴充 US2 的 `accept_invite()`（T053）；`invalidate_pending_invites_for_*`（T054/T055）與其 hook 是新函式，但接回既有 `disband_group()`/`unfriend()`（T056/T057）；前端擴充 US1 的邀請分頁（T063）與 US2 的通知點擊邏輯（T062）。
- 建議依 P1→P2→P3 順序（US1→US2→US3）依序實作與驗證。

### Within Each User Story

- Tests MUST 先寫且先失敗，再進行 Implementation。
- Service（含跨模組串接、既有函式擴充）→ Router endpoints → 前端整合。
- Story 完成（含 Checkpoint 驗證）才進入下一優先序 Story。

### Parallel Opportunities

- Phase 2 之 T002–T008 皆可平行執行（不同檔案，僅需等待 T001 的 migration 讓 `GroupInvite` 模型可實際對應到資料表才能通過測試）。
- 同一 User Story 內標記 `[P]` 的 Tests 可平行執行。
- 若有多位開發者：US1 完成後，US2 的後端部分（T035–T041）可立即認領；US3 的 `invalidate_pending_invites_for_*`（T054/T055，不依賴 US2）可與 US2 平行進行，但 T053（額滿通知）須等 US2 的 `accept_invite()`（T037）就緒後才能動工。

---

## Parallel Example: User Story 1

```bash
# 平行執行 US1 的所有測試任務：
Task: "Unit test：send_invite() 成功路徑 in apps/api/tests/unit/domains/group_invite/test_send_invite.py"
Task: "Unit test：send_invite() 拒絕非好友 in apps/api/tests/unit/domains/group_invite/test_send_invite.py"
Task: "Unit test：send_invite() 拒絕重複待回覆邀請 in apps/api/tests/unit/domains/group_invite/test_send_invite.py"
Task: "Unit test：send_invite() 拒絕已在團內好友 in apps/api/tests/unit/domains/group_invite/test_send_invite.py"
Task: "Unit test：send_invite() 拒絕匿名建團 in apps/api/tests/unit/domains/group_invite/test_send_invite.py"
Task: "Unit test：list_invitable_friends() 狀態組裝 in apps/api/tests/unit/domains/group_invite/test_list_invitable_friends.py"
Task: "Contract test for GET /groups/{group_id}/invitable-friends in apps/api/tests/contract/test_group_invite_endpoints.py"
Task: "Contract test for POST /groups/{group_id}/invites in apps/api/tests/contract/test_group_invite_endpoints.py"
```

---

## Implementation Strategy

### MVP First（僅 User Story 1）

1. 完成 Phase 2：Foundational
2. 完成 Phase 3：User Story 1
3. **停下並驗證**：獨立測試 US1（`quickstart.md` 情境 1）
4. 若已可展示，即可部署/demo（「團長從好友列表送出邀請 + 好友即時收到通知」MVP 閉環至此完整——接受/拒絕仍待 US2）

### Incremental Delivery

1. Foundational 完成 → 資料表/schema 就緒
2. 加入 US1 → 獨立測試 → Demo（送出邀請 + 即時通知完整）
3. 加入 US2 → 獨立測試 → Demo（接受/拒絕完整，核心使用者價值閉環到位）
4. 加入 US3 → 獨立測試 → Demo（額滿通知、自動失效、可視性完整）
5. 每個 Story 皆為既有功能疊加價值，不破壞先前 Story

### Parallel Team Strategy

多位開發者情境：

1. 團隊共同完成 Foundational
2. Foundational 完成後：
   - 開發者 A：US1（送出邀請，MVP）
   - 開發者 B：待 US1 的 `GroupInvite` 建立流程就緒後，平行進行 US2（接受/拒絕）
3. US3 建議在 US2 的 `accept_invite()`（T037）就緒後認領——額滿通知（T053）直接擴充該函式；`invalidate_pending_invites_for_*`（T054/T055）本身不依賴 US2，可提早由第三位開發者平行進行

---

## Notes

- `[P]` 任務 = 不同檔案、無相依關係。
- `[Story]` 標籤將任務對應回 spec.md 的特定 User Story，供追溯。
- US2/US3 對既有 `join_group()`/`disband_group()`/`unfriend()` 的擴充皆是新增「預設不變更既有行為」的參數，任何既有呼叫端的既有測試 MUST 持續通過（回歸測試見 T026）。
- 實作前先確認測試會失敗（TDD，呼應 constitution 原則 II）。
- 建議每完成一項任務或一組邏輯相關任務即 commit 一次。
- 可在任一 Checkpoint 停下獨立驗證該 Story，不需等待後續 Story 完成。
- 避免：模糊任務描述、多任務同時修改同一檔案造成衝突、破壞既有呼叫端行為的非預設參數變更。
