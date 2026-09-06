# Implementation Plan: 運動簡約風視覺改版與行動裝置操作優化

**Branch**: `main` | **Date**: 2026-09-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/008-sport-minimalist-ui/spec.md`，交叉比對現有全部 7 份規格（001–007）之既有前端元件（`apps/web/src/app/features/*`），以及 `.specify/memory/constitution.md` 原則 VII（無障礙與行動裝置優先）之既有基準。

## Summary

對 `apps/web` 現有全部畫面（開團與管理、場地管理、賽程與輪替、加入團、團內成員視圖、會員與好友、即時計分板與控制板）套用統一的「運動簡約風」視覺語言，並確保手機/平板下所有互動元件皆有足夠觸控尺寸、版面不破版。目前專案**完全沒有任何既有樣式**（`styles.scss`/`app.scss` 皆為空白，無任何元件有 `.component.scss`），因此本次是從零建立第一層視覺系統，而非覆蓋既有樣式——技術路徑為新增一組全域 SCSS design tokens（顏色、字級、間距、觸控尺寸、斷點）與共用基礎樣式，逐一為既有元件新增 co-located `.component.scss` 套用之。不新增任何 npm 樣式框架依賴，不變動任何元件的 TypeScript 業務邏輯、API 呼叫或既有測試斷言的可見文字內容（僅版面與樣式）。

## Technical Context

**Language/Version**：延續 001–007（前端 TypeScript 5.9 / Angular 20 standalone components + Signals）；本 feature 純前端變更，不涉及後端 Python/FastAPI。

**Primary Dependencies**：沿用既有 `@ngx-translate/core`、`ably`、`angularx-qrcode`；**不新增任何 npm 套件**——樣式採手刻 SCSS design tokens（見 research.md #1），圖示採內嵌 SVG（見 research.md #8），皆不需額外相依套件。

**Storage**：N/A（本 feature 不涉及任何資料庫схema或資料模型變更，FR-008 明文排除）。

**Testing**：Vitest（既有）。核心領域邏輯測試優先原則（constitution 原則 II）不適用於本 feature——本次變更為純視覺呈現，無新增業務邏輯；驗證方式為 quickstart.md 之手動視覺走查（多種視窗尺寸），輔以少量自動化測試斷言「共用元件的樣式契約」（例如按鈕元素套用了達到觸控最小尺寸的共用 class，而非逐一測量像素）。既有測試（001–007 之全部單元/契約/整合測試）之可見文字斷言 MUST 全數維持通過，不因樣式調整而變動。

**Target Platform**：現代行動裝置瀏覽器（iOS Safari、Android Chrome）為主要目標；平板瀏覽器（iPadOS Safari、Android 平板 Chrome）同為主要目標；桌面瀏覽器需維持既有可用性但非本次驗收重點（FR-009）。

**Project Type**：Web application（monorepo，延續既有結構，本 feature 僅觸及 `apps/web/`）。

**Performance Goals**：沿用既有 `angular.json` production 建置門檻（初始 bundle 500kB 警告/1MB 錯誤、單一元件樣式 4kB 警告/8kB 錯誤）；新增的 design tokens partial 與逐元件樣式 MUST NOT 使既有門檻被超過。

**Constraints**：觸控可點擊區域最小尺寸 44×44 CSS px（WCAG 2.5.5，research.md #3）；響應式斷點採 768px（平板起）與 1024px（平板橫向/桌面起）兩個中斷點（research.md #2）；FR-008/FR-009 明文排除任何業務邏輯、API 合約、資料模型變更，且桌面既有可用性 MUST NOT 因本次改版而劣化。

**Scale/Scope**：涵蓋 `apps/web/src/app/features` 下現有全部 8 個功能目錄（`home`/`group-admin`/`group-join`/`member`/`scoreboard`/`control-panel`/`group-member-view`/`auth`）共約 25 個既有元件；新增 1 份全域 design tokens SCSS partial + 1 份共用基礎樣式 partial，逐一為既有元件新增 co-located `.component.scss`（目前皆不存在）。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | 不新增/修改任何 TypeScript 業務邏輯；SCSS 樣式本身不受 `strict` mode 檢查範圍，但既有 `ng lint`/`ng build` 仍為合併前 blocking check，樣式調整後 MUST 通過。 | PASS |
| II. 測試優先 | 本 feature 不觸及「開團、加入、輪替演算法、比分計算」等核心領域邏輯，構成原則 II 之強制測試範圍外的純視覺變更；既有測試之可見文字斷言 MUST 全數維持通過（見 Testing 段落）。 | PASS（明確排除項，非違反） |
| III. 即時性與一致性 | 不變動任何 Ably 事件、`build_schedule_snapshot()`、MatchResult 產生規則；純樣式調整不影響資料一致性保證。 | PASS |
| IV. 權限與安全 | 不新增/移除任何頁面的操作入口，僅重新設計視覺與版面；FR-002/006 明文要求既有二次確認流程與管理員專屬操作邊界 MUST 原樣保留，行動裝置版導覽（見 research.md #4）MUST NOT 意外讓管理員專屬功能出現在一般成員視圖等非管理頁面。 | PASS |
| V. UX 一致性（二次確認） | FR-006 明文要求所有既有二次確認彈窗（解散團、踢除成員、退出組團、提前結束等）之流程與資訊揭露內容 MUST 保留，僅套用新視覺樣式（見 research.md #7，`<dialog>` 原生機制不變）。 | PASS |
| VI. 可維護性 | 新增之 design tokens/基礎樣式集中於獨立的全域 SCSS partial，供各功能模組元件引用，不引入跨模組的業務邏輯耦合；各元件仍以各自 co-located 樣式檔案維護。 | PASS |
| VII. 無障礙與行動裝置優先 | 本 feature 是此原則的直接落實與擴大：FR-002（觸控尺寸）、FR-003（響應式版面）、FR-004（計分板可遠距離閱讀延續）、FR-005（狀態不可僅靠顏色）、FR-007（行動裝置導覽）皆直接對應此原則之既有與擴充要求。 | PASS（本 feature 之核心目的） |
| VIII. i18n 與時區 | 本 feature 若因應行動裝置導覽新增任何顯示文字（例如底部導覽列標籤），MUST 依既有慣例新增至 `src/assets/i18n/zh-TW.json`，MUST NOT 寫死文字於樣板中；不涉及時區相關欄位。 | PASS（列入 tasks.md 落實項） |
| IX. 可攜性 | 不涉及 Docker/AWS 部署設定變更。 | PASS（不適用） |
| X. 伺服器為單一事實來源 | 不新增/修改任何前端直接發布即時事件的邏輯；純樣板/樣式調整。 | PASS（不適用） |
| XI. 防機器人 | 不涉及任何「建立新資源」端點。 | PASS（不適用） |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/008-sport-minimalist-ui/
├── plan.md                    # 本檔案
├── research.md                # Phase 0 產出
├── data-model.md              # Phase 1 產出（本 feature 之「資料模型」為 design tokens 結構）
├── contracts/                 # Phase 1 產出
│   └── design-system.md       # design tokens 命名/數值、共用元件之樣式契約
└── quickstart.md              # Phase 1 產出
```

### Source Code (repository root)

```text
apps/web/
├── src/
│   ├── styles.scss                    # 擴充：@import 全域 design tokens + 基礎樣式 partial
│   └── styles/                        # 新增目錄
│       ├── _tokens.scss               # 新增：色彩/字級/間距/觸控尺寸/斷點 CSS custom properties
│       └── _base.scss                 # 新增：共用基礎樣式（按鈕、卡片、表單、confirm-dialog 樣式）
└── src/app/features/
    ├── home/                          # 逐一新增 co-located .component.scss（目前皆不存在）
    ├── auth/{login,register,forgot-password,reset-password,verify-email}/
    ├── group-admin/{admin-page,court-management,create-group,reauth,schedule-management,shared}/
    ├── group-join/{group-list,join-flow}/
    ├── group-member-view/{member-schedule,standings,match-records,leave-group}/
    ├── member/{settings,match-history}/
    ├── scoreboard/
    └── control-panel/{all-courts}/
```

**Structure Decision**：新增 `apps/web/src/styles/_tokens.scss`（design tokens）與
`_base.scss`（共用基礎樣式），由 `styles.scss`（全域，現為空白）`@use` 匯入；
既有 25 個元件逐一新增 co-located `.component.scss`（Angular schematic 預設
`style: scss`，符合既有 `angular.json` 設定，只是過去未被使用）。不新增
npm 套件依賴（research.md #1、#8），不建立獨立的樣式函式庫模組——design
tokens 本身即是本 feature 對外的「共用介面」，記錄於
`contracts/design-system.md`。

## Complexity Tracking

*本 feature 無 Constitution Check 違反項目，此表格從略。*

## Post-Design Constitution Check

*Re-evaluated after Phase 1（`data-model.md`、`contracts/`、
`quickstart.md`）產出。*

設計階段的關鍵決策——(1) 不引入任何新 CSS 框架/元件庫，全數以手刻 SCSS
design tokens 落實（research.md #1，維持既有「無框架」架構慣例）、
(2) `group-member-view` 之底部導覽列僅為既有 `activeTab`/`setTab()` 的
樣式呈現調整，未新增元件狀態（research.md #4）、(3) `ConfirmDialogComponent`
原生 `<dialog>` 機制與既有二次確認流程完全不變，僅新增樣式（research.md
#7）——皆確認未引入任何違反 constitution 原則 I–XI 之設計，亦未新增任何
FR-008 範圍外的業務邏輯或 API 變更。**Gate 結果維持 PASS，無需新增
Complexity Tracking 項目。**
