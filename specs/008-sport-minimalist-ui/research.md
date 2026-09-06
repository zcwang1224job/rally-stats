# Research: 運動簡約風視覺改版與行動裝置操作優化

## #1 樣式技術選型：手刻 SCSS design tokens，不引入新樣式框架

**Decision**：新增 `apps/web/src/styles/_tokens.scss`（CSS custom properties 形式的
design tokens：色彩、字級、間距、觸控尺寸、斷點）與 `_base.scss`（共用基礎
樣式：按鈕、卡片、表單控制項、`<dialog>` 樣式），由全域 `styles.scss`
`@use` 匯入；既有元件逐一新增 co-located `.component.scss`，透過
`var(--token-name)` 消費全域 tokens。不安裝 Tailwind CSS、Angular
Material，或任何其他 CSS 框架/元件庫。

**Rationale**：專案目前完全沒有任何樣式（`styles.scss`/`app.scss` 皆為
空白模板，`package.json` 無任何 CSS 框架依賴，`angular.json` 之
schematics 已預設新元件用 `style: scss`）——這是從零建立第一層視覺系統，
不是「migrate 掉舊框架」的情境。引入 Tailwind/Material 等框架會是這個純
前端專案迄今唯一的重量級建置期依賴，且與現有「手刻 Angular standalone
components，無框架」的既有慣例不一致，屬於超出本次需求（「設計運動簡約
風」本質是色彩/字級/間距/圖示的一致視覺語言，不需要框架的 utility class
或元件庫）的額外複雜度。手刻 SCSS + CSS custom properties 已足夠表達一套
一致的 design tokens，且維持每元件樣式檔案在 `angular.json` 既有 4kB/8kB
budget 門檻內。

**Alternatives considered**：
- Tailwind CSS（透過 npm + PostCSS 整合進 Angular build）——已否決，需要
  新增建置期工具鏈（PostCSS 設定、`tailwind.config`），且本專案至今無任何
  utility-class CSS 慣例，貿然引入屬於超出需求的架構變更。
- Angular Material——已否決，Material 本身自帶特定視覺語言（Material
  Design），與「運動簡約風」這個自訂視覺方向衝突，且會引入整套元件庫的
  bundle 成本，與現有手刻 standalone components 的架構不符。

## #2 響應式斷點：768px（平板）與 1024px（平板橫向/桌面）

**Decision**：採兩個中斷點的 mobile-first 策略——基準（無 media query）
適用於手機（約 360–767px 寬）；`@media (min-width: 768px)` 適用於平板
直向；`@media (min-width: 1024px)` 適用於平板橫向與桌面。三層斷點皆定義為
`_tokens.scss` 中的 SCSS 變數（`$breakpoint-tablet: 768px`、
`$breakpoint-desktop: 1024px`），供各元件樣式檔案的 media query 統一
引用，避免各處寫死不同數字。

**Rationale**：768px／1024px 是業界（Bootstrap、Material Design 等）最
廣泛採用、開發者最熟悉的斷點慣例，spec.md Assumptions 已明確「實際中斷點
數值留待 `/speckit-plan` 決定」，採用業界慣例值可直接對應 spec 的手機
（360–430px）／平板（768–1024px）尺寸定義，不需要為此另建自訂研究。

**Alternatives considered**：逐元件自訂斷點——已否決，會導致不同頁面在
相近視窗寬度下切版時機不一致，違反 FR-001「統一視覺語言」之一致性要求。

## #3 觸控可點擊區域最小尺寸：44×44 CSS px（WCAG 2.5.5）

**Decision**：`_tokens.scss` 定義 `--touch-target-min: 44px`；`_base.scss`
提供一個共用的 `.btn`／`.tap-target` 基礎樣式類別，確保套用此類別的
可互動元素 `min-width`/`min-height` 皆不小於此值（並保留足夠的
外部 `margin`/`gap` 避免相鄰元素間距過近）。既有元件模板中所有按鈕、
連結型按鈕、確認彈窗按鈕，於重新套版時 MUST 套用此共用類別。

**Rationale**：WCAG 2.5.5（Target Size，AA 等級建議值）是可觸控介面尺寸
最廣泛引用的業界標準，spec.md Assumptions 已明確採此標準作為驗收基準
（SC-002）。以共用 CSS class 而非逐元件手動設定像素值的方式落實，確保
一致性且降低後續新增元件時遺漏此規則的風險。

**Alternatives considered**：逐元件手動指定 padding/尺寸——已否決，容易
在多達 25 個元件的改版範圍中出現不一致或遺漏，不符合 FR-002 對「每一個
可互動元件」的全面要求。

## #4 手機下的導覽模式：`group-member-view` 改為底部固定導覽列；`admin-page` 維持卷動式但改善區塊視覺區隔

**Decision**：
- `group-member-view.component`（賽程/戰績/對戰紀錄/退出組團四項導覽，
  目前為純文字按鈕橫向排列）在手機寬度下（< 768px）改為畫面底部固定的
  導覽列（bottom navigation bar），觸控範圍大、不佔用內容垂直空間；
  平板/桌面寬度下維持原有橫向排列於頁面上方。
- `admin-page.component`（管理頁，本質是單頁多區塊由上而下排列，非
  真正的分頁切換元件）手機下維持現有的垂直卷動結構，僅透過樣式加強各
  功能區塊（團設定/場地管理/賽程控制/輪替名單）之間的視覺區隔（卡片式
  分隔、區塊標題），不新增分頁切換邏輯或元件狀態，避免非必要的 TypeScript
  變更。

**Rationale**：`group-member-view` 的四個導覽項目本質是彼此獨立的視圖
切換（tab 語意），底部導覽列是行動裝置上這類切換最常見、觸控體驗最好的
慣例模式，且不需要新增選單開合的元件狀態（底部導覽列本身恆常顯示）。
`admin-page` 則不是 tab 結構，而是一次性把所有管理功能垂直排列在同一
頁面（透過卷動瀏覽），沒有「目前選中哪一項」的狀態需要管理，因此不需要
改變其資訊架構，只需要透過樣式讓卷動瀏覽在小螢幕下更容易分辨區塊邊界，
符合 FR-003（不破版）與 FR-007（清楚可觸控導覽，此處體現為清楚的區塊
可視性而非分頁點擊)。

**Alternatives considered**：把 `admin-page` 也改為真正的分頁切換
（每次只顯示一個功能區塊）——已否決，這需要新增元件狀態與對應的
TypeScript 邏輯變更，超出 FR-008「本次改版僅限視覺呈現與版面配置」的
範圍界定，且管理頁面本身內容量對手機捲動而言尚在合理範圍，不需要犧牲
「一次看到所有設定項」的既有資訊架構優勢。

## #5 既有元件之 TypeScript 邏輯原則上不變更，僅新增必要的最小狀態

**Decision**：本次改版之預設做法是「只加樣式檔案與調整樣板結構
（HTML/`@if`/`@for` 排版），不動 `.component.ts`」；僅在下列情況允許
新增最小必要的元件狀態：(a) 若某元件因應響應式導覽需要「目前選中哪個
項目」以外的全新互動狀態（例如平板/手機下可收合的次要資訊區塊），
且該狀態純粹是呈現層開關，不影響任何既有業務邏輯輸出或 API 呼叫。

**Rationale**：直接對應 FR-008「本次改版 MUST NOT 變更任何既有頁面之
底層業務邏輯、API 合約、或既有規格已定義之功能行為」——明確界定「樣板
結構調整」與「必要的純呈現層開關狀態」皆屬合理範圍，但引入任何影響資料
流向、API 呼叫時機、或既有測試斷言之業務行為的 TypeScript 變更皆超出
範圍。

**Alternatives considered**：無——此為 FR-008 之直接推論，非設計決策。

## #6 既有「不可僅靠顏色區分」規則之延續方式

**Decision**：延續 005-member-view 已建立的模式——狀態文字前綴/搭配符號
（例如「⏏ 已離開」、「－ 未上場」）搭配獨立的 `data-status` 屬性供樣式
掛鉤；新視覺風格僅重新設計顏色本身與符號的視覺呈現（例如改用更符合
「運動簡約風」的圖示或底線樣式），不移除既有的文字/符號雙重標示機制。
控制板/計分板之連線中斷提示（`role="status"` + 文字）、場地需密碼/公開
標示等既有模式比照辦理。

**Rationale**：直接對應 FR-005 與 constitution 原則 VII 之既有規則，
005-member-view 已建立的「文字標籤 + 非純色彩區分」模式已驗證可行，
延續此模式可將改版風險侷限在「顏色/字體/圖示的視覺呈現」，不需要重新
設計每個狀態指示器的資訊架構。

**Alternatives considered**：無——此為既有已定案原則的延續，非新決策。

## #7 既有 `<dialog>` 二次確認元件之處理方式

**Decision**：`ConfirmDialogComponent`（`group-admin/shared/confirm-dialog.component.ts`，
使用瀏覽器原生 `<dialog>` 元素 + `showModal()`）之底層機制不變（原生
`<dialog>` 已內建焦點鎖定、ESC 關閉、背景不可互動等無障礙特性），本次
改版僅新增其樣式檔案（圓角、間距、按鈕之運動簡約風格、觸控尺寸），
確認/取消按鈕之文案、觸發時機、`confirmed` output 事件皆不變。

**Rationale**：直接對應 FR-006「MUST 保留原有的確認流程與資訊揭露內容」
與 constitution 原則 V；原生 `<dialog>` 元素已提供良好的無障礙基礎，
沒有理由更換底層機制，只需要重新設計其視覺樣式。

**Alternatives considered**：改用自訂 overlay/modal 元件取代原生
`<dialog>`——已否決，會引入不必要的焦點管理/ESC 處理等重新實作成本，且
超出「僅視覺呈現與版面配置調整」的範圍界定（FR-008）。

## #8 圖示方案：內嵌 SVG，不安裝 icon 套件

**Decision**：「運動簡約風」所需的圖示（例如底部導覽列圖示、狀態圖示）
採用內嵌於 Angular 樣板中的 inline `<svg>`（手繪或取用開源、MIT 授權
icon set 如 Feather Icons／Heroicons 之個別 SVG path，逐一複製所需圖示
的 SVG 標記到樣板中），不安裝任何 icon 字型或 npm icon 套件。

**Rationale**：本次改版所需圖示數量有限（底部導覽 4 項、少數狀態圖示），
inline SVG 可讓瀏覽器直接以向量渲染、支援 `currentColor` 隨文字顏色變化、
不需要額外的網路請求或字型載入，且不新增 `package.json` 依賴（呼應
research.md #1 之「不引入新框架/套件」決策）。

**Alternatives considered**：安裝 icon 字型套件（例如 Font Awesome）或
SVG icon npm 套件——已否決，圖示需求量不足以證成新增一整包套件依賴的
bundle 成本，個別複製所需 SVG 已足夠且更輕量。
