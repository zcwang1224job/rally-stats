# Tasks: 運動簡約風視覺改版與行動裝置操作優化

**Input**: Design documents from `/specs/008-sport-minimalist-ui/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md（皆已存在）

**Tests**: 依 `plan.md` Constitution Check（原則 II），本 feature 不觸及核心領域邏輯，測試優先原則不適用；主要驗證方式為 `quickstart.md` 之手動視覺走查（Phase 6），輔以少量自動化測試斷言「共用樣式 class 是否正確掛載」（非測量實際像素）。本檔案的測試任務屬選用性質的補強，非強制項。

**Organization**：依 spec.md 之 3 個 User Story（US1–US3，優先序 P1/P2/P3）分階段組織，每個 Story 皆可獨立驗證與交付。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行執行（不同檔案、無相依關係）
- **[Story]**: 對應 spec.md 的 US1–US3
- 每項任務皆附精確檔案路徑

## Path Conventions

沿用 `plan.md` Project Structure：全部變更皆位於 `apps/web/`。新增全域 `apps/web/src/styles/_tokens.scss`、`_base.scss`，由 `apps/web/src/styles.scss` 匯入；既有 25 個元件逐一新增 co-located `.component.scss`（目前皆不存在）。不新增 npm 套件依賴，不變更任何 `.component.ts` 業務邏輯（僅必要的最小呈現層狀態，見 research.md #5）。

---

## Phase 1: Setup

*本 feature 無新增 Setup 任務——monorepo、Angular CLI、lint 工具鏈已由 001 完整建立並沿用。*

---

## Phase 2: Foundational（Blocking Prerequisites）

**Purpose**：建立全域 design tokens 與共用基礎樣式，供全部 User Story 的元件樣式消費。

**⚠️ CRITICAL**：此階段完成前不可開始任何 User Story 任務。

- [X] T001 [P] 新增 `apps/web/src/styles/_tokens.scss`——色彩、字級、間距、觸控尺寸（`--touch-target-min: 44px`）之 CSS custom properties，以及斷點 SCSS 變數（`$breakpoint-tablet: 768px`、`$breakpoint-desktop: 1024px`）per data-model.md
- [X] T002 [P] 新增 `apps/web/src/styles/_base.scss`——共用基礎樣式類別 `.btn`/`.btn--danger`/`.card`/`.status-badge`/`.tap-target` per contracts/design-system.md
- [X] T003 修改 `apps/web/src/styles.scss`：`@use`/`@forward` 匯入 `_tokens.scss` 與 `_base.scss`；執行 `npm run build` 確認全域樣式可正確編譯且未超出 `angular.json` 既有 bundle 門檻 (depends on T001, T002)

**Checkpoint**：Foundation ready — User Story 任務可以開始。

---

## Phase 3: User Story 1 - 即時計分板與控制板的行動裝置操作 (Priority: P1) 🎯 MVP

**Goal**：計分板、單一場地控制板、全部場地控制板、管理頁內嵌控制板套用運動簡約風視覺語言，所有操作按鈕在手機/平板下皆有足夠觸控尺寸，比分維持可遠距離閱讀。

**Independent Test**：可獨立用手機瀏覽器開啟一個既有場地的控制板連結與計分板連結，實測按鈕可點擊區域大小、比分文字可視距離、平板橫向下的版面是否正常，無需依賴其他頁面改版。

### Tests for User Story 1

- [X] T004 [P] [US1] Test：擴充 `apps/web/src/app/features/control-panel/control-panel.component.spec.ts`，斷言計分（+1/-1）與提前結束按鈕皆套用 `.btn`／`.tap-target` 共用觸控 class

### Implementation for User Story 1

- [X] T005 [US1] 新增 `apps/web/src/app/features/scoreboard/scoreboard.component.scss`，並調整 `scoreboard.component.html` 套用 `--font-size-display`（大比分字級）、`.card`、`.status-badge`（連線狀態/即將登場提示）
- [X] T006 [US1] 新增 `apps/web/src/app/features/control-panel/control-panel.component.scss`，並調整 `control-panel.component.html`：+1/-1/提前結束按鈕套用 `.btn`，連線中斷提示套用 `.status-badge` (depends on T004)
- [X] T007 [P] [US1] 新增 `apps/web/src/app/features/control-panel/all-courts/all-courts-control-panel.component.scss` 與 `all-courts-court-block.component.scss`：套用相同視覺語言於多場地版面，場地區塊間有清楚卡片區隔
- [X] T008 [P] [US1] 新增 `apps/web/src/app/features/group-admin/schedule-management/court-control.component.scss`：管理頁內嵌控制板套用相同 `.btn` 觸控樣式，與 T006 視覺一致

**Checkpoint**：US1 完整可運作——計分板與全部控制板變體皆套用新視覺語言且觸控尺寸合規。

---

## Phase 4: User Story 2 - 加入團與一般成員視圖的行動裝置操作 (Priority: P2)

**Goal**：加入團流程與一般成員視圖（賽程/戰績/對戰紀錄/退出組團）之表單、按鈕、導覽在手機小螢幕上皆清楚易讀、方便點擊。

**Independent Test**：可獨立用手機開啟一個團的加入連結，走完密碼驗證、暱稱輸入、確認加入的完整流程，並開啟一般成員視圖的四個分頁，驗證表單與按鈕在手機尺寸下皆可正常操作，無需依賴管理頁或會員頁的改版。

### Tests for User Story 2

- [X] T009 [P] [US2] Test：擴充 `apps/web/src/app/features/group-member-view/group-member-view.component.spec.ts`，於手機視窗寬度模擬下斷言導覽容器套用對應的底部固定導覽響應式 class（不測量實際像素，僅驗證 class 掛載與既有 SC-001 之四項導覽文字仍完整存在）

### Implementation for User Story 2

- [X] T010 [US2] 新增 `apps/web/src/app/features/group-member-view/group-member-view.component.scss`，並調整 `group-member-view.component.html`：手機寬度（< `$breakpoint-tablet`）改為畫面底部固定導覽列，平板/桌面維持原有橫向排列於頁面上方（沿用既有 `activeTab`/`setTab()`，不新增元件狀態，見 research.md #4） (depends on T009)
- [X] T011 [P] [US2] 新增 `apps/web/src/app/features/group-member-view/member-schedule/member-schedule.component.scss`：場地區塊套用 `.card`，狀態提示套用 `.status-badge`
- [X] T012 [P] [US2] 新增 `apps/web/src/app/features/group-member-view/standings/standings.component.scss`：四狀態欄位套用 `.status-badge`（圖示化，延續 005 既有文字/符號雙重標示），手機寬度下表格本身可橫向捲動但不影響頁面其餘版面
- [X] T013 [P] [US2] 新增 `apps/web/src/app/features/group-member-view/match-records/match-records.component.scss`：列表項目套用 `.card`，分頁按鈕套用 `.btn`
- [X] T014 [P] [US2] 新增 `apps/web/src/app/features/group-member-view/leave-group/leave-group.component.scss`：退出按鈕套用 `.btn--danger`
- [X] T015 [P] [US2] 新增 `apps/web/src/app/features/group-join/join-flow/join-flow.component.scss`、`apps/web/src/app/features/group-join/group-list/group-list.component.scss`、`apps/web/src/app/features/group-join/group-join.component.scss`：加入流程三頁面之表單輸入框、清單項目、按鈕套用共用樣式，確保手機下無需橫向捲動或縮放

**Checkpoint**：US1–US2 皆可獨立運作。

---

## Phase 5: User Story 3 - 開團管理與會員頁面的行動裝置操作 (Priority: P3)

**Goal**：開團管理頁（團設定/場地管理/賽程輪替/踢除成員）與會員相關頁面（登入/好友/個人設定/跨團對戰紀錄）在手機與平板下皆可正常操作，功能區塊間有清楚視覺區隔。

**Independent Test**：可獨立用手機或平板開啟一個團的管理頁，測試建立場地、編輯團設定、踢除成員、Next Round 等管理操作，以及登入會員帳號後檢視好友列表、個人設定、跨團對戰紀錄，確認每個操作在小螢幕下皆可正常完成，無需依賴計分板或加入流程的改版。

### Implementation for User Story 3

*本 Story 無獨立自動化測試任務——`quickstart.md` 情境 3 之手動視覺走查（Phase 6）涵蓋驗證。*

- [X] T016 [US3] 新增 `apps/web/src/app/features/group-admin/admin-page/admin-page.component.scss`，並調整 `admin-page.component.html`：團設定、場地管理、賽程控制等區塊套用 `.card` 強化視覺區隔，避免手機捲動時誤判區塊歸屬
- [X] T017 [P] [US3] 新增 `apps/web/src/app/features/group-admin/court-management/court-list.component.scss` 與 `court-link-card.component.scss`
- [X] T018 [P] [US3] 新增 `apps/web/src/app/features/group-admin/create-group/create-group.component.scss` 與 `apps/web/src/app/features/group-admin/reauth/reauth.component.scss`：表單輸入框與送出按鈕套用共用樣式
- [X] T019 [P] [US3] 新增 `apps/web/src/app/features/group-admin/schedule-management/manual-assign.component.scss` 與 `partnership-settings.component.scss`
- [X] T020 [US3] 新增 `apps/web/src/app/features/group-admin/shared/confirm-dialog.component.scss`：全站共用二次確認彈窗套用 `.card`/`.btn` 樣式（原生 `<dialog>` 機制與既有確認流程不變，見 research.md #7）
- [X] T021 [P] [US3] 新增 `apps/web/src/app/features/group-admin/shared/turnstile-widget.component.scss`：確保 Turnstile widget 容器響應式、不因版面調整而溢出
- [X] T022 [P] [US3] 新增 `apps/web/src/app/features/member/member.component.scss`、`member/settings/settings.component.scss`、`member/match-history/match-history.component.scss`
- [X] T023 [P] [US3] 新增 `apps/web/src/app/features/auth/login/login.component.scss`、`register/register.component.scss`、`forgot-password/forgot-password.component.scss`、`reset-password/reset-password.component.scss`、`verify-email/verify-email.component.scss`：五個表單頁面套用統一表單樣式
- [X] T024 [US3] 新增 `apps/web/src/app/features/home/home.component.scss`

**Checkpoint**：US1–US3 全部皆可獨立運作，全站既有畫面皆已套用新視覺語言。

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**：跨 User Story 的收尾與驗證。

- [X] T025 [P] 依 `quickstart.md` 情境 1–3，於手機直向（375×667）、平板直向（768×1024）、平板橫向（1024×768）三種視窗尺寸下完整手動視覺走查
- [X] T026 [P] 執行 `npm run build`，確認 production bundle 與逐元件樣式門檻（`angular.json` 4kB 警告/8kB 錯誤）皆未超標
- [X] T027 [P] 執行 `npm run lint` 與 `npm test`，確認既有 001–007 前端測試（含可見文字斷言）與 lint 全數維持通過，未因樣式調整而產生迴歸
- [X] T028 i18n 檢查：確認本次改版若新增任何顯示文字（例如圖示 `aria-label`、底部導覽新增文案），皆已建立 `apps/web/src/assets/i18n/zh-TW.json` 對應 key，MUST NOT 寫死文字於樣板中（constitution 原則 VIII）
- [X] T029 [P] SC-004 視覺走查：對照改版前後畫面截圖，確認每一頁面既有功能入口（按鈕/連結/選單項目）數量與可達性與改版前一致，未因版面調整而遺漏任何既有功能

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：無任務，略過。
- **Foundational (Phase 2)**：design tokens + 共用基礎樣式；**封鎖**所有 User Story（US1–US3 之每個元件樣式皆消費此處建立的 tokens/class）。
- **User Stories (Phase 3–5)**：皆依賴 Foundational 完成，彼此無直接程式碼相依（各自處理獨立的元件集合）。
- **Polish (Phase 6)**：依賴所有欲交付的 User Story 完成。

### User Story Dependencies

- **US1（P1，MVP）**：Foundational 完成後即可開始，無其他 Story 相依。
- **US2（P2）**：Foundational 完成後即可開始，無其他 Story 相依。
- **US3（P3）**：Foundational 完成後即可開始，無其他 Story 相依。
- 三個 User Story 彼此觸及完全不同的元件集合，理論上可完全平行進行；建議仍依 P1→P2→P3 順序驗證交付，優先確保球場邊實際操作的計分板/控制板到位。

### Within Each User Story

- 若有 Tests 任務，MUST 先寫且先失敗，再進行 Implementation（惟本 feature 之測試任務為選用補強，非嚴格 TDD 強制項，見 plan.md Testing 段落）。
- 同一元件的 `.component.scss` 新增與對應 `.component.html` 調整視為同一任務（樣式與樣板調整密不可分，不強行拆分為兩個任務）。
- Story 完成（含 Checkpoint 驗證）後即可視資源進入下一優先序 Story，或並行處理（見上）。

### Parallel Opportunities

- Phase 2 之 T001（tokens）與 T002（base styles）可平行撰寫，T003 需等兩者皆完成後才能驗證匯入。
- 同一 User Story 內標記 `[P]` 的元件樣式任務可平行執行（不同檔案、無相依關係）。
- 若有多位開發者：Foundational 完成後，US1、US2、US3 可分別由不同開發者平行認領（彼此無直接程式碼相依）。

---

## Parallel Example: User Story 2

```bash
# 平行執行 US2 的元件樣式任務（Foundational 與 T009/T010 完成後）：
Task: "新增 member-schedule.component.scss in apps/web/src/app/features/group-member-view/member-schedule/member-schedule.component.scss"
Task: "新增 standings.component.scss in apps/web/src/app/features/group-member-view/standings/standings.component.scss"
Task: "新增 match-records.component.scss in apps/web/src/app/features/group-member-view/match-records/match-records.component.scss"
Task: "新增 leave-group.component.scss in apps/web/src/app/features/group-member-view/leave-group/leave-group.component.scss"
Task: "新增 join-flow/group-list/group-join 三個 .component.scss"
```

---

## Implementation Strategy

### MVP First（僅 User Story 1）

1. 完成 Phase 2：Foundational（design tokens + 共用基礎樣式）
2. 完成 Phase 3：User Story 1
3. **停下並驗證**：依 `quickstart.md` 情境 1，於三種視窗尺寸手動走查計分板/控制板
4. 若已可展示，即可視為「球場邊核心操作畫面」的運動簡約風改版完整交付

### Incremental Delivery

1. Foundational 完成 → design tokens 就緒
2. 加入 US1 → 獨立驗證（quickstart.md 情境 1）→ 計分板/控制板改版完整（MVP，直接影響比賽正確性的畫面優先到位）
3. 加入 US2 → 獨立驗證（quickstart.md 情境 2）→ 加入流程與一般成員視圖改版完整
4. 加入 US3 → 獨立驗證（quickstart.md 情境 3）→ 管理頁與會員頁面改版完整，全站視覺語言一致
5. 每個 Story 皆為既有畫面疊加新視覺呈現，不破壞先前 Story 已完成的樣式

### Parallel Team Strategy

多位開發者情境：

1. 團隊共同完成 Foundational（design tokens 命名與數值需先定案，避免後續大量元件重工）
2. Foundational 完成後：
   - 開發者 A：US1（計分板/控制板，MVP，優先度最高）
   - 開發者 B：US2（加入流程 + 一般成員視圖）
   - 開發者 C：US3（管理頁 + 會員頁面，元件數量最多）
3. 三者可完全平行進行，最後一起執行 Phase 6 的全站視覺走查與 SC-004 一致性確認

---

## Notes

- `[P]` 任務 = 不同檔案、無相依關係。
- `[Story]` 標籤將任務對應回 spec.md 的特定 User Story，供追溯。
- 本 feature 的每個「實作任務」本質上是「新增一個 `.component.scss` + 視需要微調對應 `.component.html` 的 class/結構」，不涉及 `.component.ts` 業務邏輯變更（唯一例外：T010 的底部導覽列樣板結構調整，但沿用既有 `activeTab`/`setTab()`，不新增狀態，見 research.md #5）。
- 表單類頁面（T018、T023）因結構高度相似，合併為單一任務處理多個檔案，避免不必要的任務數量膨脹；若實作時發現個別頁面需要差異化調整，可於執行時再拆分。
- 實作前先確認 T004/T009 的測試會失敗（若採 TDD），惟本 feature 測試任務為選用補強。
- 建議每完成一項任務或一組邏輯相關任務即 commit 一次。
- 可在任一 Checkpoint 停下獨立驗證該 Story，不需等待後續 Story 完成。
- 避免：在樣式調整任務中意外修改既有測試斷言所依賴的可見文字或 DOM 結構語意（僅可調整 class/樣式相關屬性）。
