# Tasks: 開團流程優化——合理預設值與自動預設場地

**Input**: Design documents from `/specs/021-group-creation-defaults/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md（皆已存在）

**Tests**: 依 `plan.md` Constitution Check（原則 II）之要求，團名預設值計算、自動建立球場、球場更名（含既有完全缺乏測試的 `rename_court()`／`PATCH /courts/{court_id}`）皆屬使用者可觀察的核心行為，MUST 有單元/契約/整合/前端測試覆蓋；本檔案的測試任務為強制項，非選用。

**Organization**：依 spec.md 之 3 個 User Story（US1/US2 皆為 P1，US3 為 P2）分階段組織。US1（最少輸入即可開團，含團名預設值）與 US2（自動建立預設場地）雖然是兩個獨立的使用者故事，但依 research.md #1/#2，兩者的核心邏輯是對既有 `create_group()` 同一個函式、同一段交易的連續修改（暱稱計算時機提前、團名預設值、自動建立球場皆緊鄰彼此），無法乾淨拆成互不相干的程式碼變更，因此歸類為 Foundational；US1 階段只需要在既有前端表單上疊加變更即可獨立驗證，US2 階段則是針對 Foundational 已經實作好的自動建站邏輯做端到端驗證，不需要額外的服務層新程式碼。US3（球場更名 UI）完全獨立於 Foundational 之外——後端更名能力早已存在且正確（research.md #3），只是從未被呼叫或測試過，可與 Foundational/US1/US2 平行開發。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行執行（不同檔案、無相依關係）
- **[Story]**: 對應 spec.md 的 US1–US3
- 每項任務皆附精確檔案路徑

## Path Conventions

沿用 `plan.md` Project Structure：`apps/api/`（FastAPI 後端）、`apps/web/`（Angular 20 前端）。monorepo 骨架已由 001 建立，本 feature 無新增 Setup 任務。

---

## Phase 1: Setup

*本 feature 無新增 Setup 任務——monorepo、CI、linting/型別檢查工具鏈已由 001 完整建立並沿用；不新增資料表，不需要新的 migration（research.md 前言）。*

---

## Phase 2: Foundational（Blocking Prerequisites）

**Purpose**：US1（團名/表單預設值）與 US2（自動建立預設場地）共用的 `create_group()` 核心變更——任一 User Story 皆無法在此階段完成前開始獨立驗證。

### Tests for Foundational（先寫、先失敗）

- [X] T001 [P] Unit test：更新既有 `test_blank_name_rejected`（`test_create_validation.py`）——此測試目前斷言「團名純空白會被拒絕」，本 feature 刻意反轉此行為，改為斷言：純空白／未提供的 `name` MUST 通過驗證並正規化為 `None`（不再拋出 `ValidationError`）；新增斷言：非空但超過 30 字的團名 MUST 仍被拒絕（既有規則不變）in `apps/api/tests/unit/domains/group/test_create_validation.py`
- [X] T002 [P] Unit test：新函式行為——`create_group()`——(a) 提供合法團名時 MUST 原樣使用；(b) 團名省略/空白且以會員身份建立時，MUST 自動帶入「{會員既有暱稱}的羽球團」；(c) 團名省略/空白且以訪客身份建立時，MUST 自動帶入「{本次填寫的建立者暱稱}的羽球團」；(d) 不論團名是否使用預設值，MUST 在同一次呼叫內自動建立恰好一筆名稱為「球場一」的現役球場；(e) 呼叫失敗時（例如 `GROUP_MEMBER_CAP_EXCEEDED`），MUST 沒有任何球場被建立（不留孤兒資料，FR-007）；(f) 自動建立球場後 MUST 對 `group_notifications_channel` 發布 `court.added` 事件，payload 含正確的 `court_id`／`name`（mock `publish`）in `apps/api/tests/unit/domains/group/test_create_group_defaults.py`（新增）
- [X] T003 [P] Contract test：`POST /groups`——團名省略、傳 `null`、傳純空白字串三種情境皆 MUST `201` 成功，且回應對應的團之後查詢 `name` MUST 為「{建立者暱稱}的羽球團」；緊接著以回應的 `admin_token` 呼叫既有 `GET /groups/{group_id}/courts`，MUST 看到一筆名為「球場一」的球場 per `contracts/group-and-court-api.md` in `apps/api/tests/contract/test_create_group.py`（擴充既有檔案）

### Implementation for Foundational

- [X] T004 [P] `CreateGroupRequest.name` 型別由 `str` 改為 `str | None = None`；`field_validator` 改為：`None` 或去除頭尾空白後為空字串時正規化為 `None`，非空時維持既有 1–30 字長度檢查（data-model.md）in `apps/api/app/domains/group/schemas.py` (depends on T001)
- [X] T005 `create_group()`——把既有「計算建立者暱稱」的時機提前到既有暱稱驗證檢查之後、組出 `Group(...)` 之前；`Group.name` 改為 `payload.name if payload.name else f"{resolved_nickname}{_DEFAULT_GROUP_NAME_SUFFIX}"`；新增模組常數 `_DEFAULT_GROUP_NAME_SUFFIX = "的羽球團"`、`_DEFAULT_COURT_NAME = "球場一"`；在既有 `session.add(roster_entry)` 之後、既有唯一一次 `await session.commit()` 之前，新增 `session.add(Court(group_id=group.id, name=_DEFAULT_COURT_NAME))`；commit 後 `await session.refresh(court)` 並對 `group_notifications_channel(str(group.id))` 發布既有 `court.added` 事件（data-model.md，research.md #1/#2）in `apps/api/app/domains/group/service.py` (depends on T002, T003, T004)

**Checkpoint**：Foundational 完成——團名預設值、表單初始值的後端支撐、自動建立預設場地皆已在後端就緒，User Story 的獨立驗證與前端渲染工作可以開始。

---

## Phase 3: User Story 1 - 最少輸入即可完成開團 (Priority: P1) 🎯 MVP（與 US2 並列）

**Goal**：使用者將「團名」欄位留空即可成功送出開團表單，系統自動帶入「{建立者暱稱}的羽球團」；比賽模式欄位的表單初始值為單打（人數上限/排程機制的既有初始值本來就已經是 4 人/公平輪替，不需改動）。

**Independent Test**：依 `quickstart.md` 情境 1、2——團名留空（含純空白）送出，驗證自動帶入預設團名；開啟表單查看比賽模式/人數上限/排程機制三欄位初始值已經是單打/4人/公平輪替。

### Implementation for User Story 1

- [X] T006 [P] [US1] 更新 i18n 字串：`createGroup.namePlaceholder` 調整為同時提示「留空將自動帶入預設團名」；移除已不再使用的 `createGroup.nameRequired`（research.md #5）in `apps/web/src/assets/i18n/zh-TW.json`
- [X] T007 [US1] `create-group.component.ts`：`name` 表單控制項移除 `Validators.required`（保留 `Validators.maxLength(30)`）；`match_mode` 表單初始值由 `'doubles'` 改為 `'singles'` in `apps/web/src/app/features/group-admin/create-group/create-group.component.ts` (depends on T005)
- [X] T008 [US1] `create-group.component.html`：移除既有「團名必填」錯誤訊息區塊（`form.controls.name.errors?.['required']`）；`namePlaceholder` 綁定沿用 T006 更新後的文案 in `apps/web/src/app/features/group-admin/create-group/create-group.component.html` (depends on T007, T006)
- [X] T009 [US1] Vitest：團名留空時表單本身 MUST 仍視為合法（其餘必填欄位皆已填妥時，`form.valid` 為 `true`）且送出時 MUST 把空字串原樣送給 `createGroup()`（不自行組出預設值，research.md #1）；表單初始值 MUST 分別為：比賽模式 `'singles'`、人數上限 `4`、排程機制 `'fair_rotation'`（quickstart.md 情境 2，`/speckit-analyze` G1——後兩者雖然是既有值、不需改動程式碼，仍 MUST 有明確斷言防止未來被無意間改壞）in `apps/web/src/app/features/group-admin/create-group/create-group.component.spec.ts` (depends on T008)

**Checkpoint**：US1 完整可運作——開團表單團名可留空、比賽模式初始值正確，MVP 之一。

---

## Phase 4: User Story 2 - 開團後立即有可用球場 (Priority: P1) 🎯 MVP（與 US1 並列）

**Goal**：團建立成功的同一個流程中，系統自動建立一筆名為「球場一」的球場，團長不需要額外手動新增；此球場與手動新增的球場能力完全相同；開團失敗時不留下孤兒球場。

**Independent Test**：依 `quickstart.md` 情境 3、4——開團後立即查詢球場列表，驗證已有「球場一」且可正常執行既有球場操作（如產生計分板連結）；讓開團請求刻意失敗，驗證沒有任何球場被建立。

### Implementation for User Story 2

- [X] T010 [US2] Integration test：透過真實 HTTP 完成一次開團（可搭配團名留空或自訂皆可），緊接著呼叫既有 `GET /groups/{group_id}/courts` MUST 看到恰好一筆名為「球場一」的球場；對這筆球場呼叫既有「重新產生計分板連結」端點 MUST 與對任何手動新增的球場一樣成功（FR-008）；另外以會必然失敗的請求（例如 Turnstile token 無效）嘗試開團，MUST 收到既有錯誤代碼且沒有任何球場因此被建立（quickstart.md 情境 3、4）in `apps/api/tests/integration/test_create_group_default_court_flow.py`（新增）(depends on T005)

**Checkpoint**：US1+US2 皆可獨立運作——「開團輸入更少」與「開團後立即可用」兩層價值疊加，構成完整優化後的開團流程（MVP）。

---

## Phase 5: User Story 3 - 團長可以幫球場重新命名 (Priority: P2)

**Goal**：團長能在既有球場管理畫面，將任一現役球場（含自動建立的「球場一」）重新命名；既有計分板/控制板連結不受影響；名稱重複時明確拒絕。

**Independent Test**：依 `quickstart.md` 情境 5——在球場管理畫面對任一球場觸發更名並輸入合法名稱，驗證列表立即顯示新名稱且既有連結不變；嘗試改成與同團另一現役球場相同的名稱，驗證被拒絕並提示。

### Implementation for User Story 3

- [X] T011 [P] [US3] Unit test：既有 `rename_court()`（`court/service.py:68`，先前完全沒有任何測試）——成功更名；更名為同團內另一現役球場已使用的名稱 MUST 拋出 `COURT_NAME_ALREADY_EXISTS`；對已刪除的球場更名 MUST 拋出 `COURT_DELETED`；更名為自己目前的名稱 MUST 視為合法操作成功（不誤判為重複，spec.md Edge Cases）in `apps/api/tests/unit/domains/court/test_rename_court.py`（新增）
- [X] T012 [P] [US3] Contract test：既有 `PATCH /courts/{court_id}`（先前完全沒有任何測試）——合法更名 `200`，回應 `name` 為新名稱，`scoreboard_token`／`control_panel_token` MUST 與更名前完全相同（research.md #3）；名稱重複 `409`／`COURT_NAME_ALREADY_EXISTS`；已刪除球場 `409`／`COURT_DELETED`；未帶 `admin_token` `401` per `contracts/group-and-court-api.md` in `apps/api/tests/contract/test_rename_court.py`（新增）
- [X] T013 [P] [US3] 新增 i18n 字串：`courtManagement.rename`（「重新命名」按鈕標籤）——確認/取消沿用既有 `common.confirm`／`common.cancel`，既有 `courtManagement.COURT_NAME_ALREADY_EXISTS`／`COURT_DELETED` 錯誤字串直接沿用 in `apps/web/src/assets/i18n/zh-TW.json`
- [X] T014 [US3] `court-list.component.ts`：新增「目前正在重新命名哪一筆球場」狀態與對應的表單控制項（沿用既有新增球場表單同一套 `Validators.required`／`Validators.maxLength(20)` 規則）；新增 `renameCourt()` 方法呼叫既有 `CourtManagementService.renameCourt()`，成功後 `load()` 重新整理列表，失敗時沿用既有 `errorKey` 呈現慣例（research.md #3）in `apps/web/src/app/features/group-admin/court-management/court-list.component.ts` (depends on T013)
- [X] T015 [US3] `court-list.component.html`：每筆球場列新增「重新命名」按鈕，點擊後該列切換為可編輯的文字輸入＋確認/取消；確認呼叫 `renameCourt()`，取消恢復原狀不呼叫任何 API in `apps/web/src/app/features/group-admin/court-management/court-list.component.html` (depends on T014)
- [X] T016 [P] [US3] `court-list.component.scss`：新增重新命名輸入列的樣式 in `apps/web/src/app/features/group-admin/court-management/court-list.component.scss`
- [X] T017 [US3] Vitest：點擊「重新命名」顯示輸入框；輸入合法新名稱送出後呼叫 `renameCourt()` 且清單重新整理顯示新名稱；`COURT_NAME_ALREADY_EXISTS` 時顯示明確錯誤訊息且清單不變；點擊取消 MUST NOT 呼叫任何 API、列表恢復原狀 in `apps/web/src/app/features/group-admin/court-management/court-list.component.spec.ts` (depends on T015, T016)

**Checkpoint**：US1–US3 全部皆可獨立運作——開團輸入更少、開團後立即可用、球場可重新命名彼此互不干擾。

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**：跨 User Story 的收尾與驗證。

- [X] T018 [P] 依 `quickstart.md` 全部 5 個情境人工驗證實際運作
- [X] T019 [P] Security review：確認 `PATCH /courts/{court_id}` 仍沿用既有 `_admin_court`（管理 PIN 驗證後的 admin_token）授權，未新增或放寬任何權限語意；確認自動建立球場的邏輯只發生在既有 `POST /groups` 既有的 Turnstile／人數上限等授權與驗證檢查皆已通過之後，未繞過任何既有防線
- [X] T020 [P] Accessibility review：確認 T015 新增的重新命名輸入框沿用既有「新增球場」表單同一套標籤/錯誤提示慣例，未引入新的無障礙疑慮
- [X] T021 補齊既有 docstring 完整性——`create_group()`（`group/service.py`）既有 docstring 只引用 001 spec 的 FR-001-012，補上對 021 新增 FR（FR-001、FR-006、FR-007）的引用；`rename_court()`（`court/service.py`）／`PATCH /courts/{court_id}`（`court/router.py`）既有 docstring 補充說明此路徑現在已由前端 UI 呼叫並有完整測試覆蓋（憲章原則 II 之強制項）in `apps/api/app/domains/group/service.py`、`apps/api/app/domains/court/service.py`、`apps/api/app/domains/court/router.py`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：無任務，略過。
- **Foundational (Phase 2)**：無其他依賴，但 BLOCKS US1、US2——US1 的表單依賴 `create_group()` 已支援團名留空；US2 的端到端驗證依賴 `create_group()` 已會自動建立球場。US3 不依賴 Foundational（research.md #3：更名後端能力早已獨立存在）。
- **User Stories (Phase 3–5)**：US1、US2 皆依賴 Foundational 完成，兩者並列 P1、共同構成本次優化後開團流程的 MVP；US3 可與 Foundational/US1/US2 平行開發，不需要等待。
- **Polish (Phase 6)**：依賴所有欲交付的 User Story 完成。

### User Story Dependencies

- **US1（P1，MVP 之一）**：依賴 Foundational（T001–T005）。
- **US2（P1，MVP 之一）**：依賴 Foundational（T005 的自動建站邏輯）；不依賴 US1 的前端變更。
- **US3（P2）**：不依賴 Foundational、US1 或 US2 之任何實作——後端更名能力已存在，純粹新增前端入口與測試。

### Within Each Phase

- Tests（Foundational 的 T001–T003；US2 的 T010；US3 的 T011–T012）MUST 先寫且先失敗，再進行對應 Implementation。
- schema → service 函式 → 前端表單邏輯 → 前端樣板 → 前端測試。
- 每個 Checkpoint 皆可停下獨立驗證，不需等待後續 Story 完成。

### Parallel Opportunities

- Foundational 的三個測試任務（T001–T003）可平行執行；T004（schema）依賴 T001 完成後才能進行，可與 T002/T003 平行。
- US1 的 T006（i18n）可先於 T007/T008 平行準備。
- US3 的 T011（後端單元測試）、T012（契約測試）、T013（i18n）三者互不相依，可完全平行執行，且可與 Foundational/US1/US2 同時進行；T016（樣式）可與 T014/T015 平行進行。

---

## Parallel Example: Foundational

```bash
# 平行執行 Foundational 的測試任務：
Task: "Unit test：團名驗證規則反轉（純空白改為接受） in apps/api/tests/unit/domains/group/test_create_validation.py"
Task: "Unit test：create_group() 團名預設值/自動建立球場/失敗不留孤兒資料 in apps/api/tests/unit/domains/group/test_create_group_defaults.py"
Task: "Contract test：POST /groups 團名留空情境 in apps/api/tests/contract/test_create_group.py"
```

## Parallel Example: User Story 3（可與其他所有階段平行）

```bash
Task: "Unit test：rename_court() in apps/api/tests/unit/domains/court/test_rename_court.py"
Task: "Contract test：PATCH /courts/{court_id} in apps/api/tests/contract/test_rename_court.py"
Task: "新增球場重新命名相關 zh-TW i18n 字串 in apps/web/src/assets/i18n/zh-TW.json"
```

---

## Implementation Strategy

### MVP First（User Story 1 + User Story 2，兩者並列）

1. 完成 Phase 2：Foundational（團名預設值、自動建站邏輯就緒）
2. 完成 Phase 3：User Story 1（開團表單最少輸入）
3. 完成 Phase 4：User Story 2（自動預設場地端到端驗證）
4. **停下並驗證**：依 `quickstart.md` 情境 1–4 獨立測試 US1+US2
5. 若已可展示，即可部署/demo（開團流程輸入更少、建完即可用）

### Incremental Delivery

1. 完成 Foundational → 後端就緒
2. 加入 US1 → 獨立測試 → Demo（團名可留空，MVP 之一！）
3. 加入 US2 → 獨立測試 → Demo（開團後立即有球場，MVP 之二！）
4. 加入 US3 → 獨立測試 → Demo（球場可重新命名，體驗加分）
5. 每個 Story 皆為既有功能疊加價值，不破壞先前 Story

### Parallel Team Strategy

多位開發者情境：

1. 開發者 A：Foundational（T001–T005）與 US2（T010，同一支邏輯的端到端驗證）
2. 開發者 B：待 T005 完成後接手 US1 前端（T006–T009）
3. 開發者 C：US3（T011–T017）——完全不依賴其他任何階段，可從一開始就平行進行

## Notes

- `[P]` 任務 = 不同檔案、無相依關係。
- `[Story]` 標籤將任務對應回 spec.md 的特定 User Story，供追溯；Foundational 任務無 Story 標籤，因 US1/US2 共用同一支後端函式的同一段變更。
- 團名預設值、自動建站規則 MUST 只在後端 `create_group()` 完成一次，前端 MUST NOT 自行組出預設團名字串（憲章原則 X，research.md #1）——實作與 code review 時請特別留意。
- 實作前先確認測試會失敗（TDD，呼應憲章原則 II）；T001 尤其要留意：這是在**修改一個既有測試的既有斷言方向**（從「拒絕」改為「接受」），不是單純新增，修改前務必確認目前該測試的既有行為與本次要反轉的方向一致。
- 建議每完成一項任務或一組邏輯相關任務即 commit 一次。
- 可在任一 Checkpoint 停下獨立驗證該 Story，不需等待後續 Story 完成。
- 避免：模糊任務描述、多任務同時修改同一檔案造成衝突、重新設計一套球場更名機制（既有 `rename_court()` 已經正確，只是缺測試與 UI 入口，研究文件已明確排除重新設計此機制，research.md #3）。
