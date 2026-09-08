---

description: "Task list for 015-manual-add-guest"

---

# Tasks: 團長手動新增訪客入團

**Input**: Design documents from `/specs/015-manual-add-guest/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/manual-add-guest-api.md, quickstart.md

**Tests**: Included — the feature spec/plan commit to unit/contract/integration coverage (constitution 原則 II), so test tasks are mandatory here, not optional.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2)

## Path Conventions

Web app monorepo per plan.md: `apps/api/` (FastAPI backend), `apps/web/` (Angular frontend).

---

## Phase 1: Setup

**Purpose**: Baseline sanity check before touching any code — this is a small additive feature with **no new dependencies** (plan.md Technical Context confirms all libraries already exist in both apps).

- [X] T001 Confirm a clean baseline: run `pytest` in `apps/api` and `ng build && ng test --watch=false && ng lint` in `apps/web`; both MUST pass before starting, so any later failure is attributable to this feature's changes

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: The one piece both user stories' backend work depends on.

**⚠️ CRITICAL**: T002 MUST land before any US1 backend task.

- [X] T002 [P] Add `AddGuestRequest` schema (`nickname: str`) to `apps/api/app/domains/group/schemas.py`, next to the existing `JoinGroupRequest`/`JoinGroupResponse` (per data-model.md — deliberately no `password` field)

**Checkpoint**: Schema in place — US1 backend implementation can begin.

---

## Phase 3: User Story 1 - 團長手動新增一位訪客加入輪替名單 (Priority: P1) 🎯 MVP

**Goal**: 團長在管理介面輸入暱稱，一鍵把訪客加進該團的輪替名單，行為與自行
加入的訪客完全一致（人數上限、已解散團擋下、暱稱驗證、排點掛勾、即時
通知全部沿用既有 `join_group()`）。

**Independent Test**: 對一個有名額的團呼叫新端點新增一位訪客，該訪客立即
出現在輪替名單並可被排入下一場比賽（quickstart.md 情境 1）。

### Tests for User Story 1 ⚠️

> **Write these tests FIRST, ensure they FAIL before implementation (T005)**

- [X] T003 [P] [US1] Contract test for `POST /groups/{group_id}/members` in `apps/api/tests/contract/test_add_guest_endpoint.py` — covers: 成功新增（201，回應含 `guest_session_token`、`created_new=true`）、連續新增兩位不同暱稱皆成功、暱稱與既有成員重複仍成功、空白/超長暱稱 → `400 NICKNAME_REQUIRED_FOR_GUEST`、已達 `max_members` → `409 GROUP_FULL`、已解散團 → `409 GROUP_DISBANDED`、`group_id` 與 token 不符 → `401 ADMIN_TOKEN_INVALID`
- [X] T004 [P] [US1] Integration test in `apps/api/tests/integration/test_add_guest_flow.py` — 新增訪客後：(a) 出現在 `GET /groups/{group_id}/schedule` 的花名冊中且 `status="active"`、`wait_count is None`；(b) 能被既有排點/指派邏輯排入下一場比賽；(c) 能被既有 `DELETE /groups/{group_id}/members/{roster_entry_id}` 踢出，行為與踢除自行加入的訪客一致

### Implementation for User Story 1

- [X] T005 [US1] Implement `POST /groups/{group_id}/members` in `apps/api/app/domains/group/router.py`: `Depends(require_admin)` → `Group`；若 `group.id != group_id` 則 `raise ApiError("ADMIN_TOKEN_INVALID", status_code=401)`（比照 `schedule/router.py` 的 `kick_member`）；否則呼叫 `service.join_group(session, group, member=None, password=None, nickname=payload.nickname, skip_password=True)`，用回傳的 `(roster_entry, created_new)` 組出 `JoinGroupResponse`（依賴 T002；完成後 T003、T004 應轉為通過）
- [X] T006 [US1] Add `addGuest(groupId: string, nickname: string): Observable<JoinGroupResponse>` to `apps/web/src/app/features/group-admin/schedule-management/schedule.service.ts` — `this.api.post<JoinGroupResponse>(\`/groups/${groupId}/members\`, { nickname }, this.authHeader(groupId))`，鏡射既有 `kickMember()` 的寫法
- [X] T007 [US1] Add「新增訪客」表單（暱稱輸入框 + 送出按鈕）到 `apps/web/src/app/features/group-admin/admin-page/admin-page.component.ts`/`.html` 的花名冊（roster）區塊：送出呼叫 T006 的 `addGuest()`；成功後清空輸入框並保持焦點以支援連續新增（FR-009）；失敗時透過既有 `error.i18nKey` 模式顯示對應錯誤（額滿/已解散/暱稱不合法/管理權限失效）（依賴 T006）
- [X] T008 [P] [US1] Add i18n keys for the add-guest form（表單標題、暱稱輸入提示、送出按鈕文字）到 `apps/web/src/assets/i18n/zh-TW.json`（既有 `errors.GROUP_FULL`/`errors.GROUP_DISBANDED`/`errors.NICKNAME_REQUIRED_FOR_GUEST`/`errors.ADMIN_TOKEN_INVALID` 已存在，不需新增錯誤文字，僅需新增表單本身的 UI 文字）
- [X] T009 [US1] Extend `apps/web/src/app/features/group-admin/admin-page/admin-page.component.spec.ts`：mock `ScheduleService.addGuest`，測試成功後表單清空、連續新增、以及四種錯誤各自顯示正確的 i18n key（依賴 T007）

**Checkpoint**：此時 US1 應可獨立運作與測試（跑一次 quickstart.md 情境 1）。

---

## Phase 4: User Story 2 - 團長取得新增訪客的個人查看連結 (Priority: P2)

**Goal**: 新增訪客成功後，團長能立即取得一組可轉交給該訪客的連結／QR
code，讓對方用自己的裝置查看賽況，體驗對等於自行加入的訪客。

**Independent Test**: 用 US1 已建立的訪客的 `guest_session_token` 組出
`/guest-access/:token` 連結，用另一支裝置開啟後直接看到該訪客本人的賽況
（quickstart.md 情境 2）。

### Tests for User Story 2 ⚠️

> **Write these tests FIRST, ensure they FAIL before implementation (T011)**

- [X] T010 [P] [US2] Spec for `GuestAccessComponent` in `apps/web/src/app/features/group-join/guest-access/guest-access.component.spec.ts` — mock `GroupJoinService`：合法 token → 呼叫 `resolveGuestSession()` 成功後呼叫 `setGuestSessionToken()`/`setActiveGuestGroupId()` 並導向 `/groups/:groupId/member-view`；無效/已失效 token → 顯示錯誤畫面、不導頁（鏡射 `group-join.component.spec.ts` 既有測試風格）

### Implementation for User Story 2

- [X] T011 [US2] Implement `GuestAccessComponent`（`.ts` + 最小 `.html`）於 `apps/web/src/app/features/group-join/guest-access/guest-access.component.ts`：建構子讀取路徑參數 `token` → `GroupJoinService.resolveGuestSession(token)` → 成功則 `setGuestSessionToken(group_id, token)` + `setActiveGuestGroupId(group_id)` + `router.navigate(['/groups', group_id, 'member-view'])`；失敗則顯示錯誤狀態（完全鏡射 `apps/web/src/app/features/group-join/group-join.component.ts` 的 token-resolve-then-redirect 結構，讓 T010 轉為通過）
- [X] T012 [US2] Register route `guest-access/:token`（`data: { navShell: false }`，lazy-loaded，緊鄰既有 `join/:token` 路由）於 `apps/web/src/app/app.routes.ts`（依賴 T011）
- [X] T013 [US2] Add share-link／QR 面板到 `admin-page.component` 花名冊區塊：新增訪客成功（T007 的 handler）後立即顯示，內容為 `${window.location.origin}/guest-access/${guest_session_token}`，重用既有 `QRCodeComponent` 與 `copyTextToClipboard`（沿用 `court-link-card.component.ts`／既有 join-link 區塊的既有寫法）——`apps/web/src/app/features/group-admin/admin-page/admin-page.component.ts`/`.html`（依賴 T007、T012）
- [X] T014 [P] [US2] Add i18n keys for the share-link panel（面板標題、複製按鈕、已複製提示、QR code 替代文字）到 `apps/web/src/assets/i18n/zh-TW.json`
- [X] T015 [US2] Extend `admin-page.component.spec.ts`：新增訪客成功後應顯示分享面板且連結內容正確（依賴 T013）

**Checkpoint**：US1 + US2 皆可獨立運作與測試（quickstart.md 情境 1 + 2）。

---

## Phase 5: Polish & Cross-Cutting Concerns

- [X] T016 Run `ruff check app` and `mypy app` in `apps/api`；修正任何問題
- [X] T017 Run full backend `pytest` suite in `apps/api`；確認無既有測試回歸（比對本 session 既有的 629 通過基準線）
- [X] T018 Run `ng lint`、`ng build`、`ng test --watch=false` in `apps/web`；確認無既有測試回歸
- [X] T019 手動執行 quickstart.md 情境 1～3（含情境 3 的「後續功能一視同仁」驗證：踢人／排點／統計皆不需修改即可涵蓋手動新增的訪客），視需要透過 Docker + curl/瀏覽器實測

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：無前置依賴，立即可做。
- **Foundational (Phase 2)**：依賴 Setup 完成——BLOCKS 所有 User Story 的後端任務。
- **User Story 1 (Phase 3)**：依賴 Foundational 完成；不依賴 US2。
- **User Story 2 (Phase 4)**：依賴 Foundational 完成；T013（分享面板）額外依賴 US1 的 T007（新增訪客表單需已存在才能掛分享面板），T012（路由需已存在）。除此之外 US2 的其餘任務（T010、T011）可與 US1 平行進行。
- **Polish (Phase 5)**：依賴所有已完成的 User Story。

### Within Each User Story

- 測試先寫、先失敗，再實作（T003/T004 先於 T005；T010 先於 T011）。
- Schema/service 層先於 endpoint；endpoint 先於前端呼叫方；前端 service 方法先於元件 UI；元件 UI 先於對應的元件測試擴充。

### Parallel Opportunities

- T003 與 T004 可平行（不同檔案）。
- T008（US1 i18n）可與 T005～T007 平行（不同檔案）。
- T010（US2 測試）可與 US1 的任何任務平行進行——US2 的元件邏輯本身不依賴 US1 是否完成，只有「分享面板要掛在哪裡」（T013）需要等 T007。
- T014（US2 i18n）可與 T011～T012 平行。

---

## Parallel Example: User Story 1

```bash
# Launch both US1 tests together (different files, both should fail first):
Task: "Contract test for POST /groups/{group_id}/members in apps/api/tests/contract/test_add_guest_endpoint.py"
Task: "Integration test for add-guest flow in apps/api/tests/integration/test_add_guest_flow.py"

# T008 (i18n) can run alongside T005-T007 (backend/frontend implementation):
Task: "Add i18n keys for the add-guest form in apps/web/src/assets/i18n/zh-TW.json"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 → Phase 2 → Phase 3（US1）。
2. **STOP and VALIDATE**：quickstart.md 情境 1 全數通過。
3. 此時即可上線——團長已能手動新增訪客並讓對方參與輪替，即使還沒有
   分享連結功能（US2 是純加值，不阻塞 US1 的可用性）。

### Incremental Delivery

1. Setup + Foundational → 基礎就緒。
2. 加入 US1 → 獨立驗證 → 可視為 MVP 完成並部署。
3. 加入 US2 → 獨立驗證（quickstart.md 情境 2）→ 部署。
4. Polish（Phase 5）確保兩個 story 疊加後整體無回歸。

---

## Notes

- 本功能刻意讓後端幾乎零新增邏輯（見 research.md #1）——`join_group()`
  本身不需要也不應該被修改；若實作過程中發現需要修改 `join_group()` 才能
  完成 T005，代表設計假設有誤，應先回頭確認 research.md 的決策是否仍然
  成立，而不是直接動手改動這個被多處既有流程依賴的共用函式。
- T005 完成後，US1 的所有錯誤情境（額滿、已解散、暱稱驗證、併發搶名額）
  理論上不需要額外程式碼即可通過 T003 的對應測試案例——如果某個錯誤情境
  測試失敗，先確認是否正確傳遞了 `skip_password=True`／`member=None`，
  而不是急著在新端點裡另外寫判斷式。
- Commit after each task or logical group（依本 session 既有慣例，僅在
  使用者明確要求 `commit it` 時才建立 commit）。
