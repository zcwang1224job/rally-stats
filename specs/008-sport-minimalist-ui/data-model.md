# Data Model: 運動簡約風視覺改版與行動裝置操作優化

本 feature 不涉及任何資料庫 schema 或後端資料模型變更（FR-008）。此處的
「資料模型」是本 feature 實際引入的結構化內容——全域 design tokens——其
命名、型別與預設值，作為所有既有元件樣式共同消費的單一事實來源。

## Design Tokens（`apps/web/src/styles/_tokens.scss`）

### 色彩（CSS custom properties）

| Token | 用途 | 說明 |
|---|---|---|
| `--color-brand-primary` | 主要品牌色（按鈕、連結、強調文字） | 運動簡約風之高對比主色，具體色票由實作階段依視覺設計定案 |
| `--color-brand-accent` | 次要強調色（例如「勝」狀態、成功提示） | 需與 primary 有足夠對比但不搶主色風采 |
| `--color-danger` | 危險/警示操作（解散團、踢除、退出組團按鈕） | 延續既有破壞性操作需明確視覺警示之慣例 |
| `--color-surface` | 卡片/區塊背景 | |
| `--color-surface-alt` | 次要背景（例如表格交錯列、次要卡片） | |
| `--color-text-primary` | 主要文字色 | 需與 `--color-surface` 達到 WCAG AA 對比 |
| `--color-text-muted` | 次要/輔助文字色 | 例如「未上場」狀態文字、輔助說明 |
| `--color-border` | 邊框/分隔線 | |

### 字級（Type scale）

| Token | 用途 |
|---|---|
| `--font-size-display` | 計分板大比分數字（延續既有「可遠距離閱讀」需求，FR-004） |
| `--font-size-heading` | 頁面/區塊標題 |
| `--font-size-body` | 一般內文 |
| `--font-size-caption` | 輔助說明文字（例如時間戳記、次要標籤） |

### 間距（Spacing scale）

| Token | 用途 |
|---|---|
| `--space-xs` / `--space-sm` / `--space-md` / `--space-lg` / `--space-xl` | 統一的內外距階梯，取代逐元件手寫像素值 |

### 觸控與斷點

| Token | 值 | 說明 |
|---|---|---|
| `--touch-target-min` | `44px` | WCAG 2.5.5，套用於 `.btn`/`.tap-target` 共用類別（research.md #3） |
| `$breakpoint-tablet`（SCSS 變數，非 CSS custom property） | `768px` | `@media (min-width: 768px)` 觸發點（research.md #2） |
| `$breakpoint-desktop`（SCSS 變數） | `1024px` | `@media (min-width: 1024px)` 觸發點 |

## 共用基礎樣式類別（`apps/web/src/styles/_base.scss`）

| 類別 | 用途 |
|---|---|
| `.btn` | 標準按鈕（套用 `--touch-target-min`、`--color-brand-primary`、圓角、字重） |
| `.btn--danger` | 破壞性操作按鈕（套用 `--color-danger`） |
| `.card` | 卡片式區塊容器（`--color-surface`、圓角、陰影极简化） |
| `.status-badge` | 狀態標示（搭配文字 + 圖示，MUST NOT 僅靠 `.status-badge--*` 修飾類別的顏色本身區分，見 research.md #6） |
| `.tap-target` | 非 `<button>` 元素（例如可點擊的 `<a>`、自訂導覽項目）套用相同觸控尺寸保證 |
| `.form` | 表單頁面（加入流程、開團、登入/註冊等）之 label/input 統一版面，input 套用 `--touch-target-min` |

## 既有實體（本 feature 不變更，僅視覺呈現受影響）

本 feature 讀取但不修改以下既有前端資料結構（皆為既有 TypeScript
interface/model，定義權屬各自來源的 spec）：

- `ScheduleResponse`、`GroupStandingsResponse`、`GroupMatchRecordsResponse`
  等既有 API 回應型別（005-member-view、007-live-scoreboard 等）——樣板
  呈現方式改變，型別本身不變。
- `RoundStatus`（`won`/`lost`/`did_not_play`/`left`）——狀態列舉本身不變，
  僅其視覺呈現（顏色/圖示）依 design tokens 重新設計。
