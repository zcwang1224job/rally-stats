# Tasks: 場地管理（Court Management）

**Input**: Design documents from `/specs/002-court-management/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md（皆已存在）

**Tests**: 依 `plan.md` Constitution Check（原則 II），核心領域邏輯（場地名稱唯一性判斷、軟刪除排除查詢、連結重新產生之刪除優先檢查、各自獨立版本欄位之衝突偵測）MUST 有單元測試，且 MUST 有至少一條涵蓋「新增場地→重新產生連結→刪除場地」的整合測試——本檔案的測試任務為強制項，非選用。

**Organization**: 依 spec.md 之 5 個 User Story（US1–US5，依優先序 P1/P1/P1/P2/P2）分階段組織，每個 Story 皆可獨立測試與交付。US4（管理頁內建場地控制區塊）之實際計分/手動安排操作依賴尚未存在的 003/007 spec，本階段僅交付其畫面骨架（見 plan.md Assumptions）。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行執行（不同檔案、無相依關係）
- **[Story]**: 對應 spec.md 的 US1–US5
- 每項任務皆附精確檔案路徑

## Path Conventions

沿用 `plan.md` Project Structure：`apps/api/`（FastAPI 後端）、`apps/web/`（Angular 20 前端）。monorepo 骨架與工具鏈已由 001 建立，本 feature 無新增 Setup 任務。

---

## Phase 1: Setup

*本 feature 無新增 Setup 任務——monorepo、CI、linting/型別檢查工具鏈已由 001 完整建立並沿用。*

---

## Phase 2: Foundational（Blocking Prerequisites）

**Purpose**：本 feature 5 個 User Story 皆需依賴的 `Court` 完整資料模型與 router 骨架。

**⚠️ CRITICAL**：此階段完成前不可開始任何 User Story 任務。

- [X] T001 Create Alembic migration extending `courts` table（新增 `name`, `scoreboard_token`, `control_panel_token`, `scoreboard_link_version`, `control_panel_link_version`, `created_at` 六欄位 + 三個索引，per `data-model.md` §7）in `apps/api/alembic/versions/`
- [X] T002 [P] Extend `Court` SQLAlchemy model to full field set（取代 001 之 stub）in `apps/api/app/domains/court/models.py`
- [X] T003 [P] Define Court Pydantic request/response schemas（`CreateCourtRequest`, `RenameCourtRequest`, `RegenerateLinkRequest`, `CourtResponse`, `CourtListResponse`）per `contracts/courts-api.md` in `apps/api/app/domains/court/schemas.py`
- [X] T004 Create `apps/api/app/domains/court/service.py` + `apps/api/app/domains/court/router.py`（空 `APIRouter`）並註冊於 `apps/api/app/main.py`（本階段之後各 User Story 逐一填入端點）

**Checkpoint**：Foundation ready — User Story 任務可以開始。

---

## Phase 3: User Story 1 - 新增場地並取得專屬連結 (Priority: P1) 🎯 MVP

**Goal**：管理員在場地設定區塊輸入場地名稱並確認新增，系統立即建立場地並產生獨立的計分板連結與控制板連結（含 QR Code）。

**Independent Test**：在一個已存在的團上新增一個場地，驗證場地出現在場地清單、計分板/控制板連結與 QR Code 立即可用、場地計數即時更新。

### Tests for User Story 1

- [X] T005 [P] [US1] Unit test：場地名稱驗證規則（必填、trim、≤20 字、同團「目前有效」範圍內唯一、允許沿用已刪除場地舊名稱）in `apps/api/tests/unit/domains/court/test_create_validation.py`
- [X] T006 [P] [US1] Contract test for `POST /groups/{group_id}/courts` and `GET /groups/{group_id}/courts` per `contracts/courts-api.md` in `apps/api/tests/contract/test_create_court.py`
- [X] T007 [US1] Integration test：新增場地 → 場地清單標題即時反映數量 → 計分板/控制板連結與版本欄位皆為初始值 in `apps/api/tests/integration/test_court_creation_flow.py`

### Implementation for User Story 1

- [X] T008 [US1] Implement `create_court` service（名稱驗證、「目前有效」範圍唯一性檢查、Token 產生、`GROUP_DISBANDED` 檢查，per 001 spec FR-032）in `apps/api/app/domains/court/service.py` (depends on T002, T003)
- [X] T009 [US1] Implement `list_active_courts` service（排除 `deleted_at`，依 `created_at` 排序，回傳 `active_court_count`）in `apps/api/app/domains/court/service.py`
- [X] T010 [US1] Implement `POST /groups/{group_id}/courts` and `GET /groups/{group_id}/courts` router endpoints in `apps/api/app/domains/court/router.py` (depends on T008, T009, T004)
- [X] T011 [P] [US1] Angular `CourtManagementService`（集中式 API 呼叫層）in `apps/web/src/app/features/group-admin/court-management/court-management.service.ts`
- [X] T012 [P] [US1] Angular 場地清單元件（新增表單、即時場地數量標題「場地 (N)」）in `apps/web/src/app/features/group-admin/court-management/court-list.component.ts`
- [X] T013 [P] [US1] Angular 場地連結卡片元件（QR Code + 一鍵複製，計分板/控制板連結）in `apps/web/src/app/features/group-admin/court-management/court-link-card.component.ts`

**Checkpoint**：US1 完整可運作——可獨立展示「新增場地 → 取得計分板/控制板連結與 QR Code」。

---

## Phase 4: User Story 2 - 刪除場地並妥善收斂未收尾比賽 (Priority: P1)

**Goal**：管理員刪除場地後，該場地與其連結立即失效；若刪除的是最後一個場地仍允許刪除。

**Independent Test**：對團內最後一個場地觸發刪除，驗證確認彈窗提示內容、連結失效、場地計數變化、名稱可被新場地沿用。

### Tests for User Story 2

- [X] T014 [P] [US2] Unit test：軟刪除排除「目前有效」查詢、已刪除場地名稱可被新場地沿用 in `apps/api/tests/unit/domains/court/test_delete_court.py`
- [X] T015 [P] [US2] Contract test for `DELETE /courts/{court_id}` per `contracts/courts-api.md` in `apps/api/tests/contract/test_delete_court.py`
- [X] T016 [US2] Integration test：刪除場地 → 連結立即失效（`by-token` 回傳 `LINK_NOT_FOUND`）→ 場地計數減少 → 名稱可被新場地沿用 in `apps/api/tests/integration/test_court_deletion_flow.py`

### Implementation for User Story 2

- [X] T017 [US2] Implement `delete_court` service（軟刪除、接受可選 `AbandonCourtMatchesHook` 參數、預設 no-op，per `research.md` #2）in `apps/api/app/domains/court/service.py` (depends on T008)
- [X] T018 [US2] Implement `DELETE /courts/{court_id}` router endpoint in `apps/api/app/domains/court/router.py` (depends on T017)
- [X] T019 [P] [US2] Angular 場地刪除按鈕 + 二次確認 dialog（含最後一個場地之額外提示文案）in `apps/web/src/app/features/group-admin/court-management/court-list.component.ts`

**Checkpoint**：US1–US2 皆可獨立運作。

---

## Phase 5: User Story 3 - 全部場地控制板：一人操作全部場地 (Priority: P1)

**Goal**：任何持有「全部場地控制板」連結的人，可在單一畫面上看到團內所有目前有效場地。

**Independent Test**：在一個已有多個場地的團上開啟全部場地控制板連結，驗證所有場地同時顯示；新增或刪除場地後，畫面即時反映而不需重新產生連結。

### Tests for User Story 3

- [X] T020 [P] [US3] Unit test：`by-all-courts-token` 解析（場地清單排除已刪除、團已解散時回傳對應狀態）in `apps/api/tests/unit/domains/group/test_all_courts_link.py`
- [X] T021 [P] [US3] Contract test for `GET /groups/by-all-courts-token/{token}` per `contracts/courts-api.md` in `apps/api/tests/contract/test_all_courts_bootstrap.py`
- [X] T022 [US3] Integration test：建立 2 個場地 → 全部場地控制板初始化取得清單 → 刪除 1 個場地 → 清單即時反映 in `apps/api/tests/integration/test_all_courts_panel_flow.py`

### Implementation for User Story 3

- [X] T023 [US3] Implement `get_group_by_all_courts_token` service（回傳團狀態、目前有效場地清單，不含個別場地連結 Token）in `apps/api/app/domains/group/service.py`
- [X] T024 [US3] Implement `GET /groups/by-all-courts-token/{token}` router endpoint in `apps/api/app/domains/group/router.py` (depends on T023)
- [X] T025 [P] [US3] Angular 全部場地控制板畫面骨架（依場地清單顯示各場地區塊，空狀態「尚無進行中比賽」；實際計分操作留待 007 spec 串接，見 `plan.md` Assumptions）in `apps/web/src/app/features/control-panel/all-courts/all-courts-control-panel.component.ts`
- [X] T026 [P] [US3] Angular 訂閱 `group:{group_id}:notifications`，場地新增/刪除即時反映於全部場地控制板畫面 in `apps/web/src/app/features/control-panel/all-courts/all-courts-control-panel.component.ts`

**Checkpoint**：US1–US3 皆可獨立運作。

---

## Phase 6: User Story 4 - 管理頁內建場地控制區塊 (Priority: P2)

**Goal**：管理員可在管理頁內直接看到各場地目前狀況，不需切換分頁。

**Independent Test**：於已驗證進入管理頁的狀態下，於場地控制區塊看到團內每個場地。**本階段之實際 +1/-1、提前結束、手動安排操作依賴尚未存在的 Match 領域邏輯（003/007 spec），本階段僅交付畫面骨架與空狀態，見 `plan.md` Assumptions。**

本故事無新增後端端點（重用 US1 之 `GET /groups/{group_id}/courts`）。

### Implementation for User Story 4

- [X] T027 [P] [US4] Angular 管理頁「場地控制」區塊骨架（列出各場地目前狀態，空狀態「尚無進行中比賽」；實際計分/手動安排操作留待 003/007 spec 串接）in `apps/web/src/app/features/group-admin/admin-page/admin-page.component.ts`

**Checkpoint**：US1–US4 皆可獨立運作（US4 之實際計分/安排操作待後續 spec 完工後才具備完整驗收條件）。

---

## Phase 7: User Story 5 - 重新產生連結並即時通知舊連結失效 (Priority: P2)

**Goal**：管理員可個別針對四種連結（場地計分板/控制板、團層級加入連結/全部場地控制板）觸發重新產生，正在使用舊連結的畫面近乎即時收到專屬失效提示。

**Independent Test**：對一個場地的控制板連結觸發重新產生，同時保持一個舊連結畫面開著，驗證舊畫面收到專屬失效提示、新連結可正常使用。

### Tests for User Story 5

- [X] T028 [P] [US5] Unit test：重新產生場地層級連結前優先檢查 `deleted_at`，優先於版本衝突檢查（FR-028）in `apps/api/tests/unit/domains/court/test_link_regeneration.py`
- [X] T029 [P] [US5] Unit test：計分板連結版本與控制板連結版本彼此獨立，不因無關變更誤判衝突（FR-036）in `apps/api/tests/unit/domains/court/test_link_regeneration.py`
- [X] T030 [P] [US5] Unit test：加入連結重新產生 MUST NOT 發布即時事件（FR-033）in `apps/api/tests/unit/domains/group/test_join_link_regeneration.py`
- [X] T031 [P] [US5] Contract test for `POST /courts/{court_id}/regenerate-scoreboard-link` and `regenerate-control-panel-link` per `contracts/courts-api.md` in `apps/api/tests/contract/test_regenerate_court_links.py`
- [X] T032 [P] [US5] Contract test for `POST /groups/{group_id}/regenerate-join-link` and `regenerate-all-courts-link` per `contracts/courts-api.md` in `apps/api/tests/contract/test_regenerate_group_links.py`
- [X] T033 [P] [US5] Contract test for `GET /courts/by-token/{token}` per `contracts/courts-api.md` in `apps/api/tests/contract/test_court_by_token.py`

### Implementation for User Story 5

- [X] T034 [US5] Implement `regenerate_scoreboard_link` and `regenerate_control_panel_link` services（`deleted_at` 優先檢查、樂觀鎖、發布 `link.regenerated` 至 `court:{group_id}:{court_id}`，per `contracts/ably-events.md`）in `apps/api/app/domains/court/service.py` (depends on T017)
- [X] T035 [US5] Implement `get_court_by_token` service（依 token 命中 `scoreboard_token` 或 `control_panel_token`，回傳 `link_type`/版本/`deleted`/`group_disbanded`）in `apps/api/app/domains/court/service.py`
- [X] T036 [US5] Implement `POST /courts/{court_id}/regenerate-scoreboard-link`, `regenerate-control-panel-link`, and `GET /courts/by-token/{token}` router endpoints in `apps/api/app/domains/court/router.py` (depends on T034, T035)
- [X] T037 [US5] Implement `regenerate_join_link` service（樂觀鎖、MUST NOT 發布事件，per FR-033）in `apps/api/app/domains/group/service.py`
- [X] T038 [US5] Implement `regenerate_all_courts_link` service（樂觀鎖、發布 `link.regenerated`(`link_type: all_courts`) 至 `group:{group_id}:notifications`）in `apps/api/app/domains/group/service.py`
- [X] T039 [US5] Implement `POST /groups/{group_id}/regenerate-join-link` and `regenerate-all-courts-link` router endpoints in `apps/api/app/domains/group/router.py` (depends on T037, T038)
- [X] T040 [P] [US5] Angular 連結重新產生按鈕 + 二次確認 dialog（四種連結類型：場地計分板/控制板、團層級加入連結/全部場地控制板）in `apps/web/src/app/features/group-admin/court-management/court-link-card.component.ts`
- [X] T041 [P] [US5] Angular 訂閱場地層級與團層級 `link.regenerated` 事件，依 `link_type` 比對後顯示與斷線提示明確區隔的專屬失效提示 in `apps/web/src/app/features/scoreboard/`, `apps/web/src/app/features/control-panel/`
- [X] T042 [P] [US5] Angular 心跳檢查機制（場地層級 `GET /courts/by-token/{token}`、團層級 `GET /groups/by-all-courts-token/{token}` 各自獨立輪詢，5 分鐘週期，per FR-034）in `apps/web/src/app/core/api/link-heartbeat.service.ts`

**Checkpoint**：US1–US5 皆可獨立運作。

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**：跨 User Story 的收尾與驗證。

- [X] T043 [P] Integration test：完整流程「新增場地 → 重新產生連結 → 刪除場地」in `apps/api/tests/integration/test_court_lifecycle.py`（constitution 原則 II 之強制整合測試要求）
- [X] T044 [P] 依 `quickstart.md` 全部 5 個情境手動驗證 apps/api 實際運作
- [X] T045 補齊本 feature 新增之 FastAPI router 端點（`court`、`group` 兩模組）之 `response_model`/docstring，供前端型別產生工具使用（呼應 constitution 原則 I，比照 001 之 T072）
- [X] T046 [P] Security review：確認 `GET /groups/by-all-courts-token/{token}` 回應 MUST NOT 洩漏個別場地的 `scoreboard_token`/`control_panel_token`（呼應 `contracts/courts-api.md` 之權限邊界設計）

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：無任務，略過。
- **Foundational (Phase 2)**：依賴 001 已建立之基礎設施；**封鎖**所有 User Story。
- **User Stories (Phase 3–7)**：皆依賴 Foundational 完成。
- **Polish (Phase 8)**：依賴所有欲交付的 User Story 完成。

### User Story Dependencies

- **US1（P1）**：Foundational 完成後即可開始，無其他 Story 相依。
- **US2（P1）**：依賴 US1 之 `create_court`/場地 Model 存在（實務上需先有場地才能刪除），程式碼結構上僅相依 T008。
- **US3（P1）**：依賴 US1 之場地清單查詢邏輯（`list_active_courts` 的排除規則），但透過獨立的 `group` 模組端點實作，無直接程式碼相依。
- **US4（P2）**：完全重用 US1 之 `GET /groups/{group_id}/courts`，無新增後端相依；僅為前端疊加。
- **US5（P2）**：依賴 US1（場地/版本欄位存在）與 US2（`delete_court` 之 `deleted_at` 供刪除優先檢查引用）。
- 建議依 P1→P1→P1→P2→P2 順序（US1→US2→US3→US4→US5）依序實作與驗證。

### Within Each User Story

- Tests MUST 先寫且先失敗，再進行 Implementation。
- Models（Foundational 已完成）→ Services → Router endpoints → 前端整合。
- Story 完成（含 Checkpoint 驗證）才進入下一優先序 Story。

### Parallel Opportunities

- Phase 2 內標記 `[P]` 的任務可平行執行。
- 同一 User Story 內標記 `[P]` 的 Tests 可平行執行。
- 若有多位開發者：US1 完成後，US2、US3 可由不同開發者平行認領（皆僅依賴 US1 的場地建立邏輯，彼此無直接程式碼相依）；US4 可在 US1 完成後隨時由任一開發者認領（純前端）。

---

## Parallel Example: User Story 1

```bash
# 平行執行 US1 的所有測試任務：
Task: "Unit test：場地名稱驗證規則 in apps/api/tests/unit/domains/court/test_create_validation.py"
Task: "Contract test for POST/GET courts in apps/api/tests/contract/test_create_court.py"

# 平行執行 US1 的前端任務：
Task: "Angular CourtManagementService in apps/web/src/app/features/group-admin/court-management/court-management.service.ts"
Task: "Angular 場地清單元件 in apps/web/src/app/features/group-admin/court-management/court-list.component.ts"
Task: "Angular 場地連結卡片元件 in apps/web/src/app/features/group-admin/court-management/court-link-card.component.ts"
```

---

## Implementation Strategy

### MVP First（僅 User Story 1）

1. 完成 Phase 2：Foundational（關鍵，封鎖所有 Story）
2. 完成 Phase 3：User Story 1
3. **停下並驗證**：獨立測試 US1（`quickstart.md` 情境 1）
4. 若已可展示，即可部署/demo

### Incremental Delivery

1. Foundational 完成 → 基礎就緒
2. 加入 US1 → 獨立測試 → Demo（MVP！）
3. 加入 US2 → 獨立測試 → Demo
4. 依序加入 US3 → US4 → US5，每個 Story 皆獨立測試後再交付
5. 每個 Story 皆為既有功能疊加價值，不破壞先前 Story

### Parallel Team Strategy

多位開發者情境：

1. 團隊共同完成 Foundational
2. Foundational 完成後：
   - 開發者 A：US1（新增場地，MVP 核心）
   - 開發者 B：待 US1 的場地建立邏輯就緒後，平行進行 US3（全部場地控制板）
   - 開發者 C：待 US1 完成後，平行進行 US2（刪除場地）
3. US4（純前端骨架）可在 US1 完成後由任一開發者隨時認領
4. US5（連結重新產生）建議於 US1、US2 皆完成後再開始，因其重用兩者已建立的 service 邏輯

---

## Notes

- `[P]` 任務 = 不同檔案、無相依關係。
- `[Story]` 標籤將任務對應回 spec.md 的特定 User Story，供追溯。
- 每個 User Story 皆應可獨立完成與測試；US4 之完整驗收需待 003/007 spec 完工（見 `plan.md` Assumptions）。
- 實作前先確認測試會失敗（TDD，呼應 constitution 原則 II）。
- 建議每完成一項任務或一組邏輯相關任務即 commit 一次。
- 可在任一 Checkpoint 停下獨立驗證該 Story，不需等待後續 Story 完成。
- 避免：模糊任務描述、多任務同時修改同一檔案造成衝突、破壞 Story 獨立性的跨 Story 相依。
