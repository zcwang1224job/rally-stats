# Tasks: 固定搭檔循環賽——手動配對後，剩餘未配對者自動隨機配對

**Input**: Design documents from `/specs/017-fixed-partner-autofill/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md（皆已存在）

**Tests**: 依 `plan.md` Constitution Check（原則 II）之要求，本功能直接觸及憲章明列的核心領域邏輯「輪替（排點）演算法」，`random_pair_units()` 之隨機配對正確性、`_generate_fixed_partner_matches()` 三段聯集邏輯（正式搭檔／驗證通過的暫時配對／自動補齊）之各種情境，皆 MUST 有單元/契約測試；至少一條整合測試涵蓋「部分手動配對 → 預覽調整 → 產生賽程」全流程——本檔案的測試任務為強制項，非選用。

**Organization**：依 spec.md 之 3 個 User Story（US1–US3，優先序 P1/P2/P3）分階段組織。US1 的核心行為（「不觸發任何新操作，賽程仍會自動補齊」）與 US2 的核心行為（「驗證並直接採用預覽/調整過的暫時配對」）是**同一支** `_generate_fixed_partner_matches()` 函式擴充後的兩個分支，無法乾淨拆成兩個各自獨立的程式碼變更，因此歸類為 Foundational；US1 階段只需要一條端到端驗證即可證明其獨立可用（不需要任何前端改動——「產生下一輪賽程」既有按鈕完全不變，`temporary_pairings` 省略即為空陣列）。US2 階段才是本功能真正新增前端介面與新端點的部分。US3 為回歸驗證，可與 Foundational 完成後立即開始，不依賴 US1/US2。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行執行（不同檔案、無相依關係）
- **[Story]**: 對應 spec.md 的 US1–US3
- 每項任務皆附精確檔案路徑

## Path Conventions

沿用 `plan.md` Project Structure：`apps/api/`（FastAPI 後端）、`apps/web/`（Angular 20 前端）。monorepo 骨架已由 001 建立，本 feature 無新增 Setup 任務。

---

## Phase 1: Setup

*本 feature 無新增 Setup 任務——monorepo、CI、linting/型別檢查工具鏈已由 001 完整建立並沿用；不新增資料表，不需要新的 migration（research.md #1）。*

---

## Phase 2: Foundational（Blocking Prerequisites）

**Purpose**：US1（自動補齊）與 US2（驗證並採用預覽結果）共用的核心排點邏輯與 API 骨架——任一 User Story 皆無法在此階段完成前開始獨立驗證。

### Tests for Foundational（先寫、先失敗）

- [X] T001 [P] Unit test：`random_pair_units()`——涵蓋完整性（每個輸入的 unit 剛好出現一次）、偶數輸入正確兩兩配對、多次呼叫結果不保證相同（隨機性存在）in `apps/api/tests/unit/domains/schedule/test_random_pair_units.py`
- [X] T002 [P] Unit test：`_generate_fixed_partner_matches()` 三段聯集邏輯——(a) 未傳入 `temporary_pairings` 時，自動把所有未配對現役成員隨機配對補齊；(b) 傳入的 `temporary_pairings` 若雙方皆為目前確實未配對的現役成員，MUST 直接採用、MUST NOT 重新隨機配；(c) 傳入的 `temporary_pairings` 中有一方已有正式搭檔/不再現役時，該組 MUST 被捨棄、且該名成員 MUST 被納入自動補齊；(d) 正式搭檔 MUST NOT 被任何 `temporary_pairings` 或自動補齊邏輯更動；(e) `partner_source == "auto"` 時，`temporary_pairings` 不論傳什麼皆 MUST 被忽略、行為與既有自動配對邏輯一致；(f) 傳入的 `temporary_pairings` 中同一位成員出現在超過一組配對裡時，所有包含該重複成員的組合 MUST 全部視為無效並捨棄，該成員 MUST 被納入自動補齊、MUST NOT 被同時排進兩個不同隊伍（FR-003）in `apps/api/tests/unit/domains/schedule/test_fixed_partner_autofill.py`
- [X] T003 [P] Contract test for `POST /groups/{group_id}/next-round` 新增的可選 `temporary_pairings` 欄位——省略欄位時行為與擴充前完全一致（回歸測試）；帶入有效/部分過期的 `temporary_pairings` 時的回應與既有錯誤碼皆不受影響 per `contracts/fixed-partner-autofill-api.md` in `apps/api/tests/contract/test_next_round_temporary_pairings.py`

### Implementation for Foundational

- [X] T004 [P] 新增 `random_pair_units(units)` 純函式（`random.shuffle` 後兩兩配對）in `apps/api/app/domains/schedule/algorithms.py`
- [X] T005 [P] 新增 `TemporaryPairing`／`TemporaryPairingsResponse`／`TemporaryPairingInput`／`NextRoundRequest` schemas in `apps/api/app/domains/schedule/schemas.py`
- [X] T006 擴充 `_generate_fixed_partner_matches()`——「手動配對」模式下新增三段聯集邏輯（既有正式搭檔 + 驗證通過的 `temporary_pairings` + 對剩餘未配對者呼叫 `random_pair_units()` 自動補齊）；驗證 `temporary_pairings` 時 MUST 偵測同一成員在清單中出現超過一次的情形，並將所有包含該重複成員的組合一律視為無效、改交由自動補齊處理（FR-003）；`partner_source == "auto"` 時完全略過此邏輯、沿用既有分支 in `apps/api/app/domains/schedule/service.py` (depends on T004, T005)
- [X] T007 擴充 `generate_next_round()` 簽章，新增可選參數 `temporary_pairings: list[tuple[uuid.UUID, uuid.UUID]] | None = None`，往下傳給 `_generate_fixed_partner_matches()`；其餘排點機制的既有呼叫端零行為變動 in `apps/api/app/domains/schedule/service.py` (depends on T006)
- [X] T008 擴充 `POST /groups/{group_id}/next-round` router 端點，接受可選的 `NextRoundRequest` body（預設空陣列，省略即維持既有行為）in `apps/api/app/domains/schedule/router.py` (depends on T007)

**Checkpoint**：Foundational 完成——「沒有預覽也能自動補齊」與「預覽結果會被直接採用、過期部分會被重新驗證」兩條核心邏輯皆已在後端就緒，User Story 的獨立驗證與前端工作可以開始。

---

## Phase 3: User Story 1 - 沒被手動配對到的人不再被排除在賽程外 (Priority: P1) 🎯 MVP

**Goal**：管理員完全不需要使用任何本功能新增的操作，只要現役人數為偶數，直接產生賽程時系統就會自動把剩下沒配對的人隨機配對補齊，賽程涵蓋所有現役成員。

**Independent Test**：依 `quickstart.md` 情境 1、2——(a) 完全沒手動配對直接產生賽程；(b) 部分手動配對後直接產生賽程（不使用預覽）。兩者賽程皆 MUST 涵蓋所有現役成員，且既有正式搭檔 MUST NOT 被更動。

### Implementation for User Story 1

- [X] T009 [US1] Integration test：(a) 完全沒手動配對，直接產生賽程，全員涵蓋（quickstart.md 情境 1）；(b) 部分手動配對（P0+P1、P2+P3）+ 直接產生賽程（不帶 `temporary_pairings`），剩下的人（P4~P7）自動配對補齊、賽程涵蓋全部 8 人、且事後查詢 `GET .../partnerships` 正式搭檔清單不受污染（quickstart.md 情境 2）in `apps/api/tests/integration/test_fixed_partner_autofill_flow.py` (depends on T006, T007, T008)

**Checkpoint**：US1 完整可運作——即使管理員完全不知道有「預覽」這個新功能，賽程也一定涵蓋所有現役成員，現有「產生下一輪賽程」操作方式不變。

---

## Phase 4: User Story 2 - 產生賽程前，可以預覽並調整這次要用的隨機配對結果 (Priority: P2)

**Goal**：搭檔設定畫面新增「剩下的人隨機配對」操作，管理員可以在產生賽程前預覽結果、用既有「點兩人互換」的操作方式調整，調整後的結果會被賽程產生流程直接採用而不會重新隨機配。

**Independent Test**：依 `quickstart.md` 情境 3——預覽、調整、產生賽程，賽程 MUST 使用調整後的組合；事後查詢正式搭檔清單 MUST 看不到這組暫時配對。

### Implementation for User Story 2

- [X] T010 [P] [US2] Unit test：`preview_random_partner_pairing()`——模式防呆（`scheduling_mechanism != "fixed_partner"` → `SCHEDULING_MECHANISM_MISMATCH`；`partner_source != "manual"` → `PARTNER_SOURCE_MISMATCH`）、正確算出目前未配對現役成員的隨機配對、無未配對成員時回傳空清單 in `apps/api/tests/unit/domains/schedule/test_preview_random_partner_pairing.py`
- [X] T011 [P] [US2] Contract test for `POST /groups/{group_id}/partnerships/random-preview` per `contracts/fixed-partner-autofill-api.md` in `apps/api/tests/contract/test_partnerships_random_preview.py`
- [X] T012 [US2] 實作 `preview_random_partner_pairing(session, group)`——模式防呆 + 計算目前未配對現役成員 + 呼叫 `random_pair_units()` + 組裝含暱稱的回應 in `apps/api/app/domains/schedule/service.py` (depends on T004, T005)
- [X] T013 [US2] 實作 `POST /groups/{group_id}/partnerships/random-preview` router 端點（`require_admin`）in `apps/api/app/domains/schedule/router.py` (depends on T012)
- [X] T014 [P] [US2] 新增前端 `TemporaryPairing`／`TemporaryPairingsResponse` TypeScript 介面 in `apps/web/src/app/features/group-admin/schedule-management/schedule.models.ts`
- [X] T015 [US2] `schedule.service.ts` 新增 `previewRandomPairing(groupId)`；`nextRound()` 新增可選 `temporaryPairings` 參數 in `apps/web/src/app/features/group-admin/schedule-management/schedule.service.ts` (depends on T014)
- [X] T016 [US2] `partnership-settings.component.ts`/`.html`/`.scss`——新增「剩下的人隨機配對」按鈕（僅 `partner_source === 'manual'` 且有未配對成員時顯示）；暫時配對呈現時 MUST 以圖示/文字（非純顏色）與正式搭檔區隔（FR-008，憲章原則 VII）；用既有「點兩人互換」互動方式在**本機**（不呼叫後端）調整暫時配對，選取對象 MUST 限制在「目前這份暫時配對所涵蓋的成員」之間，MUST NOT 允許選取任何已有正式搭檔的成員（FR-006）；新增 `@Output()` 每次暫時配對變動即往父層回報目前完整清單 in `apps/web/src/app/features/group-admin/schedule-management/partnership-settings.component.ts` + `.html` + `.scss` (depends on T015)
- [X] T017 [US2] `admin-page.component.ts`/`.html`——接收 `partnership-settings` 回報的暫時配對狀態並持有；`confirmNextRound()` 呼叫 `scheduleService.nextRound()` 時一併帶上目前的暫時配對 in `apps/web/src/app/features/group-admin/admin-page/admin-page.component.ts` + `.html` (depends on T016)
- [X] T018 [P] [US2] 新增「剩下的人隨機配對」按鈕文字、暫時配對標示（圖示＋文字）、`PARTNER_SOURCE_MISMATCH` 錯誤訊息之 zh-TW i18n 字串 in `apps/web/src/assets/i18n/zh-TW.json`
- [X] T019 [US2] Vitest：點擊「剩下的人隨機配對」後正確呈現暫時配對清單；點選兩位暫時配對中的成員能在本機互換；嘗試點選已有正式搭檔的成員 MUST 無法被選入暫時配對互換（FR-006）；暫時配對的渲染屬性（圖示/文字）與正式搭檔可區分、非僅靠顏色；驗證 SC-003——「預覽 + 視需要調整 + 產生賽程」的操作步驟數 MUST 不超過對剩餘成員逐一手動指定正式搭檔所需的步驟數 in `apps/web/src/app/features/group-admin/schedule-management/partnership-settings.component.spec.ts` (depends on T016)
- [X] T020 [US2] Integration test：預覽 → 前端調整 → 產生賽程，MUST 使用調整後的組合而非重新隨機配（quickstart.md 情境 3）；以及「預覽後、產生賽程前有人被配成新的正式搭檔」的暫時配對過期重新驗證情境（quickstart.md 情境 6）in `apps/api/tests/integration/test_fixed_partner_autofill_flow.py` (depends on T006, T007, T008, T012, T013)

**Checkpoint**：US1+US2 皆可獨立運作——「一定不會漏人」與「可預覽、可掌控」兩層價值逐步疊加。

---

## Phase 5: User Story 3 - 「自動配對」模式不受影響 (Priority: P3)

**Goal**：確認本功能新增的一切行為，在 `partner_source == "auto"` 時完全不生效，既有體驗零改動。

**Independent Test**：依 `quickstart.md` 情境 5——`partner_source == "auto"` 時呼叫新端點被拒絕，`next-round` 行為與既有邏輯一致。

### Implementation for User Story 3

- [X] T021 [US3] Integration test：`partner_source == "auto"` 時呼叫 `random-preview` 回傳 `409 PARTNER_SOURCE_MISMATCH`；呼叫 `next-round`（不論是否帶 `temporary_pairings`）賽程配對結果 MUST 與擴充前既有自動配對邏輯 100% 一致（quickstart.md 情境 5）in `apps/api/tests/integration/test_fixed_partner_autofill_flow.py` (depends on T006, T007, T008, T012, T013)
- [X] T022 [P] [US3] Vitest：`partner_source === 'auto'` 時，搭檔設定畫面 MUST NOT 顯示「剩下的人隨機配對」按鈕 in `apps/web/src/app/features/group-admin/schedule-management/partnership-settings.component.spec.ts` (depends on T016)

**Checkpoint**：US1–US3 全部皆可獨立運作——自動補齊、預覽調整、既有自動配對模式互不干擾。

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**：跨 User Story 的收尾與驗證。

- [X] T023 [P] 依 `quickstart.md` 全部 6 個情境人工驗證實際運作；額外人工驗證 SC-003——比較「使用預覽+調整」與「對剩餘成員逐一手動指定正式搭檔」兩種操作路徑所需的步驟數，確認前者不多於後者
- [X] T024 [P] Security review：確認新端點沿用既有 `require_admin`，未新增或放寬任何權限語意；確認伺服器端對 `temporary_pairings` 的重新驗證邏輯（T006）無法被用來把非現役、或已有正式搭檔的成員硬塞進賽程
- [X] T025 [P] Accessibility review：確認 T016 的暫時配對視覺區隔符合憲章原則 VII（非純顏色，圖示/文字並用）
- [X] T026 補齊新端點/新欄位之 `response_model`/docstring 完整性（憲章原則 II 之強制項）

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：無任務，略過。
- **Foundational (Phase 2)**：無其他依賴，但 BLOCKS 所有 User Story——US1/US2 依賴的是同一支 `_generate_fixed_partner_matches()` 函式的兩個分支，US3 的回歸驗證也需要這支函式已擴充完成才能驗證「auto 模式不受影響」。
- **User Stories (Phase 3–5)**：皆依賴 Foundational 完成；US1 只需一條整合測試即可獨立驗證交付（不依賴 US2/US3）；US2 依賴 Foundational 但不依賴 US1（可平行開發）；US3 依賴 Foundational，可在 Foundational 完成後立即開始，不需要等 US1/US2。
- **Polish (Phase 6)**：依賴所有欲交付的 User Story 完成。

### User Story Dependencies

- **US1（P1，MVP）**：依賴 Foundational；不需要任何前端改動——「產生下一輪賽程」既有操作方式不變，只需一條後端整合測試證明賽程一定涵蓋所有現役成員。
- **US2（P2）**：依賴 Foundational 提供的 `preview_random_partner_pairing()` 所需的共用元件（`random_pair_units()`、schemas）；前端新增的按鈕/互動/狀態回報彼此依序疊加（T014→T015→T016→T017）。
- **US3（P3）**：依賴 Foundational（後端回歸驗證）與 T016（前端「按鈕不該出現」的驗證對象）。

### Within Each Phase

- Tests（Foundational 的 T001–T003）MUST 先寫且先失敗，再進行 Implementation。
- 純函式／schemas → service 函式 → router endpoints → 前端 service/型別 → 前端元件 → 前端測試。
- 每個 Checkpoint 皆可停下獨立驗證，不需等待後續 Story 完成。

### Parallel Opportunities

- Foundational 的三個測試任務（T001–T003）可平行執行；T004（純函式）與 T005（schemas）互不相依，可平行。
- US2 的 T010/T011（測試）可平行；T014（TS 介面）可與後端 T012/T013 平行進行。
- US2 完成、US3 開始後，T021（後端回歸整合測試）與 T022（前端按鈕不出現的 Vitest）可平行執行。

---

## Parallel Example: Foundational

```bash
# 平行執行 Foundational 的所有測試任務：
Task: "Unit test：random_pair_units() 涵蓋完整性 in apps/api/tests/unit/domains/schedule/test_random_pair_units.py"
Task: "Unit test：_generate_fixed_partner_matches() 三段聯集邏輯 in apps/api/tests/unit/domains/schedule/test_fixed_partner_autofill.py"
Task: "Contract test for POST /groups/{group_id}/next-round 新增欄位 in apps/api/tests/contract/test_next_round_temporary_pairings.py"
```

## Parallel Example: User Story 2

```bash
# US2 的測試任務可平行執行：
Task: "Unit test：preview_random_partner_pairing() 模式防呆與計算正確性 in apps/api/tests/unit/domains/schedule/test_preview_random_partner_pairing.py"
Task: "Contract test for POST /groups/{group_id}/partnerships/random-preview in apps/api/tests/contract/test_partnerships_random_preview.py"
```

---

## Implementation Strategy

### MVP First（僅 User Story 1）

1. 完成 Phase 2：Foundational（後端三段聯集邏輯就緒）
2. 完成 Phase 3：User Story 1
3. **停下並驗證**：獨立測試 US1（`quickstart.md` 情境 1、2）
4. 若已可展示，即可部署/demo（不需要任何前端改動，管理員產生賽程時就不會再有人被漏掉）

### Incremental Delivery

1. 完成 Foundational → 後端就緒
2. 加入 US1 → 獨立測試 → Demo（不會再有人被漏掉，MVP！）
3. 加入 US2 → 獨立測試 → Demo（管理員可以預覽、掌控隨機配對結果，核心可用性提升）
4. 加入 US3 → 獨立測試 → Demo（確認既有「自動配對」模式的使用者完全無感）
5. 每個 Story 皆為既有功能疊加價值，不破壞先前 Story

### Parallel Team Strategy

多位開發者情境：

1. 開發者 A：Foundational（T001–T008）與 US1（T009）
2. 開發者 B：待 Foundational 完成後接手 US2 後端部分（T010–T013）
3. 開發者 C：待 T014/T015 就緒後接手 US2 前端部分（T016–T019），US3 的 T022 建議由同一人接續完成（同一元件檔案）

## Notes

- `[P]` 任務 = 不同檔案、無相依關係。
- `[Story]` 標籤將任務對應回 spec.md 的特定 User Story，供追溯；Foundational 任務無 Story 標籤，因 US1/US2 共用同一支後端函式的兩個分支。
- 暫時配對全程 MUST NOT 寫入 `partnerships` 資料表（FR-004）——實作與 code review 時請特別留意，T006 的三段聯集邏輯 MUST 只在記憶體中組出賽程用的隊伍清單，不可對 `Partnership` 資料表做任何寫入。
- 實作前先確認測試會失敗（TDD，呼應憲章原則 II）。
- 建議每完成一項任務或一組邏輯相關任務即 commit 一次。
- 可在任一 Checkpoint 停下獨立驗證該 Story，不需等待後續 Story 完成。
- 避免：模糊任務描述、多任務同時修改同一檔案造成衝突、把暫時配對的調整動作誤接到既有 `PATCH /groups/{group_id}/partnerships`（那會把暫時配對寫成正式搭檔，違反 FR-004）。
