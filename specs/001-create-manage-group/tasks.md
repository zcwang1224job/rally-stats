# Tasks: 開團與管理（Create & Manage Group）

**Input**: Design documents from `/specs/001-create-manage-group/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md（皆已存在）

**Tests**: 依 `plan.md` Constitution Check（原則 II），核心領域邏輯（PIN 驗證、`admin_token_version` 比對、自動解散判斷、樂觀鎖衝突偵測）MUST 有單元測試，且 MUST 有至少一條涵蓋「建立→重新驗證→編輯→解散」的整合測試——本檔案的測試任務為強制項，非選用。

**Organization**: 依 spec.md 之 6 個 User Story（US1–US6，依優先序 P1/P1/P2/P2/P2/P3）分階段組織，每個 Story 皆可獨立測試與交付。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行執行（不同檔案、無相依關係）
- **[Story]**: 對應 spec.md 的 US1–US6
- 每項任務皆附精確檔案路徑

## Path Conventions

沿用 `plan.md` Project Structure：`apps/api/`（FastAPI 後端）、`apps/web/`（Angular 20 前端）、`infra/`（Docker/部署設定）。

---

## Phase 1: Setup（Monorepo 初始化）

**Purpose**：本 feature 為專案第一個實作的 feature，需從零建立整個 monorepo 骨架（依 `specs/architecture.md` §5、§7 之建議順序）。

- [X] T001 Create monorepo skeleton directories `apps/api/`, `apps/web/`, `infra/` at repository root
- [X] T002 Initialize `apps/api` Python project with dependencies (fastapi, uvicorn[standard], sqlalchemy[asyncio], asyncpg, alembic, pydantic, pydantic-settings, passlib[bcrypt], pyjwt, cryptography, httpx, slowapi, apscheduler, ably) in `apps/api/requirements.txt` + `apps/api/pyproject.toml`
- [X] T003 [P] Initialize `apps/web` Angular 20 standalone workspace (`ng new --standalone --routing`) with `angularx-qrcode`, `ably`, `ngx-translate` dependencies in `apps/web/`
- [X] T004 [P] Configure Python linting/formatting (ruff + mypy strict) in `apps/api/pyproject.toml`
- [X] T005 [P] Configure Angular linting/formatting (ESLint + Prettier, `strict: true` in `tsconfig.json`) in `apps/web/`
- [X] T006 Create `infra/docker-compose.yml` (db/backend/frontend services) per `specs/architecture.md` §5
- [X] T007 [P] Create `apps/api/Dockerfile` (multi-stage `python:3.12-slim` + gunicorn/uvicorn worker) per `specs/architecture.md` §5
- [X] T008 [P] Create `apps/web/Dockerfile` + `apps/web/nginx.conf` (multi-stage node build + nginx, SPA fallback) per `specs/architecture.md` §5
- [X] T009 [P] Create `apps/api/.env.example` documenting required env vars (`DATABASE_URL`, `JWT_SECRET`, `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY`, `PASSWORD_ENCRYPTION_KEY`, `ABLY_API_KEY`)
- [X] T010 Initialize Alembic in `apps/api/alembic/` (`alembic init`, configure async `env.py` reading `DATABASE_URL`)

---

## Phase 2: Foundational（Blocking Prerequisites）

**Purpose**：本 feature 6 個 User Story 皆需依賴的資料庫 schema 與跨切面服務。

**⚠️ CRITICAL**：此階段完成前不可開始任何 User Story 任務。

- [X] T011 Create initial Alembic migration establishing full database schema (`system_config`, `members`, `email_verification_tokens`, `password_reset_tokens`, `friend_requests`, `groups`, `courts`, `roster_entries`, `partnerships`, `pair_history`, `matches`, `match_participants`) per `specs/architecture.md` §2.2, including `system_config` seed data (`max_group_members=200`, `default_timezone=Asia/Taipei`) per `data-model.md` §7, in `apps/api/alembic/versions/0001_initial_schema.py`
- [X] T012 [P] Configure async SQLAlchemy engine + session dependency in `apps/api/app/core/db.py`
- [X] T013 [P] Configure Pydantic Settings for environment/secrets loading in `apps/api/app/core/config.py`
- [X] T014 [P] Implement error-code response schema + global exception handlers (`{"error_code": ..., "detail": ...}`) in `apps/api/app/core/errors.py`
- [X] T015 [P] Implement Cloudflare Turnstile verification client (fail-closed, 4s timeout, per `research.md` #7) in `apps/api/app/core/turnstile.py`
- [X] T016 [P] Implement Ably REST publish wrapper in `apps/api/app/core/realtime.py`
- [X] T017 [P] Configure slowapi rate limiter in `apps/api/app/core/rate_limit.py`
- [X] T018 Assemble FastAPI app (router registration, middleware, exception handlers, CORS) in `apps/api/app/main.py` (depends on T012–T017)
- [X] T019 [P] Configure Angular root routing with 6 lazy-loaded feature route placeholders (首頁/開團/嘎團/會員/計分板/控制板) in `apps/web/src/app/app.routes.ts`
- [X] T020 [P] Implement Ably JS SDK wrapper (`RealtimeService`, connection-state Signal) in `apps/web/src/app/core/realtime/ably.service.ts`
- [X] T021 [P] Implement centralized API service base + HttpClient interceptor mapping error codes to i18n keys in `apps/web/src/app/core/api/`
- [X] T022 [P] Create zh-TW i18n translation file skeleton in `apps/web/src/assets/i18n/zh-TW.json`

**Checkpoint**：Foundation ready — User Story 任務可以開始。

---

## Phase 3: User Story 1 - 建立揪團場次並取得管理權限 (Priority: P1) 🎯 MVP

**Goal**：使用者（匿名或會員）填寫開團表單並通過 Turnstile 驗證後，系統建立團、自動加入開團者至輪替名單、產生組團編號與管理 PIN 碼。

**Independent Test**：完整填寫開團表單並送出，驗證團被建立、導向管理頁、顯示組團編號與 PIN 碼、開團者出現在輪替名單中。

### Tests for User Story 1

- [X] T023 [P] [US1] Unit test：開團表單驗證規則（團名長度、人數上限依比賽模式動態最小值、通關密碼長度、自訂比賽設定 FR-014 邏輯一致性）in `apps/api/tests/unit/domains/group/test_create_validation.py`
- [X] T024 [P] [US1] Contract test for `POST /groups` per `contracts/groups-api.md` in `apps/api/tests/contract/test_create_group.py`
- [X] T025 [US1] Integration test：建立團 → RosterEntry 自動產生（`is_creator=true`）→ 匿名者取得 Guest Session Token → `current_member_count=1` in `apps/api/tests/integration/test_group_creation_flow.py`

### Implementation for User Story 1

- [X] T026 [P] [US1] Create `Group` SQLAlchemy model（含 Match Scoring Settings、Admin Credential 欄位）in `apps/api/app/domains/group/models.py`
- [X] T027 [P] [US1] Create `RosterEntry` SQLAlchemy model in `apps/api/app/domains/roster/models.py`
- [X] T028 [P] [US1] Create minimal `Member` SQLAlchemy model stub（`id`, `nickname`，供 FK 引用；完整欄位由 006 spec 補齊）in `apps/api/app/domains/member/models.py`
- [X] T029 [P] [US1] Create minimal `Court` SQLAlchemy model stub（`id`, `group_id`, `deleted_at`，供解散流程查詢用；完整欄位由 002 spec 補齊）in `apps/api/app/domains/court/models.py`
- [X] T030 [P] [US1] Define Pydantic request/response schemas for `POST /groups` per `contracts/groups-api.md` in `apps/api/app/domains/group/schemas.py`
- [X] T031 [US1] Implement PIN 產生 + bcrypt 雜湊 helper in `apps/api/app/domains/group/security.py`
- [X] T032 [US1] Implement AES-256-GCM 通關密碼加解密 helper（per `research.md` #3）in `apps/api/app/domains/group/security.py`
- [X] T033 [US1] Implement `group_number` PostgreSQL SEQUENCE 整合（讀取 `nextval`）in `apps/api/app/domains/group/service.py`
- [X] T034 [US1] Implement `create_group` service（建立 Group、建立 creator RosterEntry、匿名核發 Guest Session Token、`current_member_count` 初始化為 1）in `apps/api/app/domains/group/service.py` (depends on T026–T033)
- [X] T035 [US1] Implement `POST /groups` router endpoint（含 Turnstile 驗證呼叫，驗證失敗回傳 `CAPTCHA_INVALID`/`CAPTCHA_EXPIRED`）in `apps/api/app/domains/group/router.py` (depends on T034, T015)
- [X] T036 [US1] Implement `GET /groups/{group_id}` public info endpoint per `contracts/groups-api.md` in `apps/api/app/domains/group/router.py`
- [X] T037 [P] [US1] Angular 開團表單元件（含 Turnstile widget wrapper、依 i18n 語系動態設定 `language`、全欄位透過語系 key 呼叫）in `apps/web/src/app/features/group-admin/create-group/`
- [X] T038 [US1] Angular `GroupAdminService`（集中式 API 呼叫層）in `apps/web/src/app/features/group-admin/group-admin.service.ts`

**Checkpoint**：US1 完整可運作——可獨立展示「填表 → 建團 → 顯示組團編號與 PIN 碼」。

---

## Phase 4: User Story 2 - 手動解散團 (Priority: P1)

**Goal**：管理員解散團後，所有連結/Token 立即失效、未收尾比賽轉為已捨棄、所有已連線畫面即時收到 `group.disbanded` 通知。

**Independent Test**：對一個已建立、已有進行中比賽的團觸發解散，驗證連結、計分板、管理頁、比賽狀態的最終行為。

### Tests for User Story 2

- [X] T039 [P] [US2] Unit test：解散後 `queued`/`in_progress` 比賽批次轉 `abandoned` 邏輯 in `apps/api/tests/unit/domains/group/test_disband.py`
- [X] T040 [P] [US2] Contract test for `POST /groups/{id}/disband` per `contracts/groups-api.md` in `apps/api/tests/contract/test_disband_group.py`
- [X] T041 [US2] Integration test：建立團 → 解散 → 驗證 `status=disbanded`、`GET /admin` 回傳 `read_only=true`、二次編輯被拒 in `apps/api/tests/integration/test_disband_flow.py`

### Implementation for User Story 2

- [X] T042 [US2] Implement `disband_group` service（更新 `status`、批次轉未收尾比賽為 `abandoned`、逐一發布 `group.disbanded` 至各場地頻道 + 團通知頻道，per `contracts/ably-events.md`）in `apps/api/app/domains/group/service.py` (depends on T026, T029, T016)
- [X] T043 [US2] Implement `POST /groups/{group_id}/disband` router endpoint in `apps/api/app/domains/group/router.py` (depends on T042, T044)
- [X] T044 [US2] Implement `admin_token` 驗證 dependency（含 `admin_token_version` 比對、`status=disbanded` 時回傳 `read_only=true`）in `apps/api/app/domains/group/security.py` (depends on T031)
- [X] T045 [P] [US2] Angular 管理頁解散按鈕 + 二次確認 dialog in `apps/web/src/app/features/group-admin/admin-page/`
- [X] T046 [P] [US2] Angular 訂閱 `group:{group_id}:notifications` 之 `group.disbanded` 事件並切換唯讀狀態 in `apps/web/src/app/features/group-admin/admin-page/`

**Checkpoint**：US1、US2 皆可獨立運作。

---

## Phase 5: User Story 3 - 以組團編號與管理 PIN 碼重新進入管理頁 (Priority: P2)

**Goal**：管理員透過組團編號＋PIN 碼重新驗證取得管理權限，具備防暴力破解機制。

**Independent Test**：用一組已知合法憑證與一組錯誤憑證分別測試，驗證前者能進入、後者被拒絕。

### Tests for User Story 3

- [X] T047 [P] [US3] Unit test：PIN 錯誤次數鎖定邏輯（10 次錯誤 → 鎖定 15 分鐘，per `research.md` #1）in `apps/api/tests/unit/domains/group/test_reauth_lockout.py`
- [X] T048 [P] [US3] Contract test for `POST /groups/reauth` per `contracts/groups-api.md` in `apps/api/tests/contract/test_reauth.py`

### Implementation for User Story 3

- [X] T049 [US3] Implement `reauth_admin` service（PIN 比對、失敗次數遞增、鎖定判斷、成功後核發 `admin_token`）in `apps/api/app/domains/group/service.py` (depends on T031, T044)
- [X] T050 [US3] Implement `POST /groups/reauth` router endpoint（套用 slowapi 速率限制）in `apps/api/app/domains/group/router.py` (depends on T049, T017)
- [X] T051 [P] [US3] Angular 重新驗證頁（組團編號 + PIN 碼輸入表單）in `apps/web/src/app/features/group-admin/reauth/`

**Checkpoint**：US1–US3 皆可獨立運作。

---

## Phase 6: User Story 4 - 管理頁編輯團設定 (Priority: P2)

**Goal**：管理員就地編輯團名、活動時間區間、比賽模式、比賽設定、通關密碼；修改僅影響尚未開始的新比賽。

**Independent Test**：在已建立且有進行中比賽的團上，個別修改各欄位，驗證進行中比賽維持原規則、新設定僅套用未來比賽。

### Tests for User Story 4

- [X] T052 [P] [US4] Unit test：比賽模式切換為雙打時人數上限連動檢查（FR-020）in `apps/api/tests/unit/domains/group/test_edit_validation.py`
- [X] T053 [P] [US4] Unit test：樂觀鎖版本衝突偵測（`base_settings_version` 不符時拒絕）in `apps/api/tests/unit/domains/group/test_optimistic_lock.py`
- [X] T054 [P] [US4] Contract test for `PATCH /groups/{id}` and `PATCH /groups/{id}/scoring-settings` per `contracts/groups-api.md` in `apps/api/tests/contract/test_edit_group.py`

### Implementation for User Story 4

- [X] T055 [US4] Implement `edit_group` service（團名/時間/比賽模式/人數上限/通關密碼編輯，含 FR-020 連動檢查與 `base_settings_version` 樂觀鎖）in `apps/api/app/domains/group/service.py` (depends on T034, T044)
- [X] T056 [US4] Implement `edit_scoring_settings` service（含 FR-014 自訂驗證邏輯、樂觀鎖）in `apps/api/app/domains/group/service.py`
- [X] T057 [US4] Implement `PATCH /groups/{group_id}` and `PATCH /groups/{group_id}/scoring-settings` router endpoints in `apps/api/app/domains/group/router.py` (depends on T055, T056)
- [X] T058 [US4] Implement `GET /groups/{group_id}/admin` endpoint（含通關密碼解密回傳明文，MUST 僅限已驗證管理頁）in `apps/api/app/domains/group/router.py` (depends on T032, T044)
- [X] T059 [P] [US4] Angular 管理頁就地編輯表單（團名/時間/比賽模式/比賽設定/通關密碼）in `apps/web/src/app/features/group-admin/admin-page/`

**Checkpoint**：US1–US4 皆可獨立運作。

---

## Phase 7: User Story 5 - 團閒置自動解散 (Priority: P2)

**Goal**：團持續 1 小時無寫入活動時自動解散，效果與手動解散完全相同。

**Independent Test**：讓一個團在無寫入操作下經過模擬的 1 小時，驗證自動進入已解散狀態；讓另一個團持續有活動，驗證不會被誤判。

### Tests for User Story 5

- [X] T060 [P] [US5] Unit test：`last_activity_at` 逾 1 小時判定邏輯 in `apps/api/tests/unit/scheduler/test_auto_disband.py`

### Implementation for User Story 5

- [X] T061 [US5] Implement APScheduler 週期任務（每分鐘掃描 `status='active' AND last_activity_at < now() - interval '1 hour'`，呼叫既有 `disband_group` service，per `research.md` #4）in `apps/api/app/scheduler/auto_disband.py` (depends on T042)
- [X] T062 [US5] 於 `create_group`／`edit_group`／`edit_scoring_settings`／`reauth_admin`（成功寫入操作）中補上 `last_activity_at = now()` 更新 in `apps/api/app/domains/group/service.py`
- [X] T063 [US5] 於 `apps/api/app/main.py` 啟動時註冊 APScheduler 任務 (depends on T061, T018)

**Checkpoint**：US1–US5 皆可獨立運作。

---

## Phase 8: User Story 6 - 主動重設管理 PIN 碼 (Priority: P3)

**Goal**：已驗證的管理員可主動重設 PIN 碼，舊 PIN 碼與舊 Token 立即全部失效，觸發者本人無縫取得新 Token 繼續操作。

**Independent Test**：在已進入管理頁的狀態下觸發重設，驗證新 PIN 碼可用、舊 PIN 碼與舊 Token 皆失效、觸發者不需重新登入。

### Tests for User Story 6

- [X] T064 [P] [US6] Unit test：`admin_token_version` 遞增後舊 Token 驗證失敗判斷 in `apps/api/tests/unit/domains/group/test_pin_regeneration.py`
- [X] T065 [P] [US6] Contract test for `POST /groups/{id}/regenerate-admin-pin` per `contracts/groups-api.md` in `apps/api/tests/contract/test_regenerate_pin.py`

### Implementation for User Story 6

- [X] T066 [US6] Implement `regenerate_admin_pin` service（新 PIN 產生、`admin_token_version += 1`、同步核發新 Token 給觸發者、樂觀鎖衝突偵測、發布 `link.regenerated`(`link_type: admin`) 至 `group:{group_id}:notifications`，per `contracts/ably-events.md`）in `apps/api/app/domains/group/service.py` (depends on T031, T044, T016)
- [X] T067 [US6] Implement `POST /groups/{group_id}/regenerate-admin-pin` router endpoint in `apps/api/app/domains/group/router.py` (depends on T066)
- [X] T068 [P] [US6] Angular 管理頁「重新產生 PIN 碼」按鈕 + 二次確認 dialog + 新 PIN 顯示畫面 in `apps/web/src/app/features/group-admin/admin-page/`

**Checkpoint**：US1–US6 全部皆可獨立運作。

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**：跨 User Story 的收尾與驗證。

- [X] T069 [P] Integration test：完整生命週期「建立 → 重新驗證 → 編輯 → 解散」in `apps/api/tests/integration/test_full_lifecycle.py`（constitution 原則 II 之強制整合測試要求）
- [X] T070 [P] 依 `quickstart.md` 全部 6 個情境手動驗證 apps/api 實際運作
- [X] T071 [P] 撰寫 `apps/api/README.md` 與 `apps/web/README.md` 本地開發環境啟動說明
- [X] T072 補齊 FastAPI router 之 `response_model`/docstring，供前端以 `ng-openapi-gen`/`openapi-typescript` 產生型別（呼應 constitution 原則 I）
- [X] T073 [P] Security review：確認通關密碼明文（`GET /groups/{id}/admin` 以外）MUST NOT 出現在任何未驗證端點回應（呼應 SC-009）

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：無相依，立即開始。
- **Foundational (Phase 2)**：依賴 Setup 完成；**封鎖**所有 User Story。
- **User Stories (Phase 3–8)**：皆依賴 Foundational 完成。
- **Polish (Phase 9)**：依賴所有欲交付的 User Story 完成。

### User Story Dependencies

- **US1（P1）**：Foundational 完成後即可開始，無其他 Story 相依。
- **US2–US6**：程式碼結構上皆獨立（各自的 service/router/前端元件互不耦合），但**實務上**皆操作「已存在的 Group 記錄」，而 US1 的 `POST /groups` 是唯一能透過 API 產生此記錄的途徑——因此建議依 P1→P1→P2→P2→P2→P3 順序（US1→US2→US3→US4→US5→US6）依序實作與驗證，US5（自動解散）額外依賴 US2 已完成的 `disband_group` service（直接呼叫，非重新實作）。

### Within Each User Story

- Tests MUST 先寫且先失敗，再進行 Implementation。
- Models → Services → Router endpoints → 前端整合。
- Story 完成（含 Checkpoint 驗證）才進入下一優先序 Story。

### Parallel Opportunities

- Phase 1、Phase 2 內標記 `[P]` 的任務可平行執行。
- 同一 User Story 內標記 `[P]` 的 Tests 可平行執行；不同檔案的 Models 可平行執行。
- 若有多位開發者：US3、US4、US6 三者的後端 service 邏輯彼此無直接程式碼相依（皆依賴 T044 的 `admin_token` dependency，但該項屬 US2 範圍、已於 Phase 4 完成），可由不同開發者平行認領。

---

## Parallel Example: User Story 1

```bash
# 平行執行 US1 的所有測試任務：
Task: "Unit test：開團表單驗證規則 in apps/api/tests/unit/domains/group/test_create_validation.py"
Task: "Contract test for POST /groups in apps/api/tests/contract/test_create_group.py"

# 平行執行 US1 的所有 Model 任務：
Task: "Create Group SQLAlchemy model in apps/api/app/domains/group/models.py"
Task: "Create RosterEntry SQLAlchemy model in apps/api/app/domains/roster/models.py"
Task: "Create minimal Member SQLAlchemy model stub in apps/api/app/domains/member/models.py"
Task: "Create minimal Court SQLAlchemy model stub in apps/api/app/domains/court/models.py"
```

---

## Implementation Strategy

### MVP First（僅 User Story 1）

1. 完成 Phase 1：Setup
2. 完成 Phase 2：Foundational（關鍵，封鎖所有 Story）
3. 完成 Phase 3：User Story 1
4. **停下並驗證**：獨立測試 US1（`quickstart.md` 情境 1）
5. 若已可展示，即可部署/demo

### Incremental Delivery

1. Setup + Foundational 完成 → 基礎就緒
2. 加入 US1 → 獨立測試 → Demo（MVP！）
3. 加入 US2 → 獨立測試 → Demo
4. 依序加入 US3 → US4 → US5 → US6，每個 Story 皆獨立測試後再交付
5. 每個 Story 皆為既有功能疊加價值，不破壞先前 Story

### Parallel Team Strategy

多位開發者情境：

1. 團隊共同完成 Setup + Foundational
2. Foundational 完成後：
   - 開發者 A：US1（建立團，MVP 核心）
   - 開發者 B：待 US1 的 T044（`admin_token` dependency）完成後，平行進行 US3（重新驗證）
   - 開發者 C：待 US2 的 `disband_group` service 完成後，平行進行 US5（自動解散，直接呼叫該 service）
3. US4、US6 可在 US2 完成（`admin_token` dependency 就緒）後由任一開發者平行認領

---

## Notes

- `[P]` 任務 = 不同檔案、無相依關係。
- `[Story]` 標籤將任務對應回 spec.md 的特定 User Story，供追溯。
- 每個 User Story 皆應可獨立完成與測試。
- 實作前先確認測試會失敗（TDD，呼應 constitution 原則 II）。
- 建議每完成一項任務或一組邏輯相關任務即 commit 一次。
- 可在任一 Checkpoint 停下獨立驗證該 Story，不需等待後續 Story 完成。
- 避免：模糊任務描述、多任務同時修改同一檔案造成衝突、破壞 Story 獨立性的跨 Story 相依。
