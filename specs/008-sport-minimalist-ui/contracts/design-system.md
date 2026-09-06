# Design System Contract: 運動簡約風視覺改版

本 feature 沒有後端 API 端點變更，此處記錄的「契約」是本 feature 對外
提供、供全部既有與未來元件消費的**前端樣式介面**——其他元件的樣式檔案
MUST 透過這裡列出的 token 名稱與共用類別使用本次改版建立的視覺系統，
MUST NOT 在個別元件中寫死顏色/字級/間距數值或重新定義相同語意的 token。

## Design Tokens 介面

所有 token 定義於 `apps/web/src/styles/_tokens.scss`，透過全域
`:root { ... }` 的 CSS custom properties 曝露（斷點除外，見下）。完整
token 清單與用途見 `data-model.md`。消費端使用方式：

```scss
// 元件的 co-located .component.scss
.my-button {
  min-height: var(--touch-target-min);
  background: var(--color-brand-primary);
  padding: var(--space-sm) var(--space-md);
}
```

斷點為 SCSS 變數（非 CSS custom property，因 media query 不支援
`var()`），透過 `@use '../../../styles/tokens' as tokens;` 匯入後以
`tokens.$breakpoint-tablet` 引用：

```scss
@use '../../../../styles/tokens' as tokens;

.my-component {
  // mobile-first 基準樣式

  @media (min-width: tokens.$breakpoint-tablet) {
    // 平板起的樣式覆寫
  }
}
```

## 共用基礎樣式類別介面

定義於 `apps/web/src/styles/_base.scss`，各元件樣板直接套用 class 名稱
（不需要 `@use`，因為 `_base.scss` 產出的是全域 class，非 SCSS mixin）：

| Class | 套用時機 | 保證 |
|---|---|---|
| `.btn` | 所有標準操作按鈕 | `min-width`/`min-height` ≥ `--touch-target-min`；套用 `--color-brand-primary` |
| `.btn--danger` | 破壞性操作按鈕（解散、踢除、退出、提前結束等） | 額外套用 `--color-danger`，與 `.btn` 疊加使用 |
| `.card` | 內容區塊容器 | 統一圓角、陰影、`--color-surface` 背景 |
| `.status-badge` | 任何需要標示狀態的文字（勝/敗/未上場/已離開、連線狀態等） | MUST 搭配子元素或 `::before` 圖示/符號，MUST NOT 只靠 `.status-badge--*` 修飾類別改變顏色 |
| `.tap-target` | 非 `<button>` 但需可點擊的元素（例如自訂導覽項目、卡片式連結） | 同 `.btn` 之觸控尺寸保證，不含按鈕預設外觀 |
| `.form` | 任何表單頁面之外層容器 | 內部 `label`/`input`/`select` 自動套用統一間距與 `--touch-target-min` 高度，無需逐頁重寫 |

## 既有共用元件之樣式契約（行為不變，僅新增樣式）

| 元件 | 契約承諾 |
|---|---|
| `ConfirmDialogComponent`（`group-admin/shared/confirm-dialog.component.ts`） | `open()`/`cancel()`/`confirm()` 方法簽章與 `confirmed` output 事件不變；新增 `.component.scss` 套用 `.card`/`.btn` 之視覺樣式，原生 `<dialog>` 機制不變（research.md #7） |
| `GroupMemberViewComponent`（`group-member-view/group-member-view.component.ts`） | 現有 `activeTab`/`setTab()` 邏輯不變；手機寬度下導覽渲染為底部固定導覽列（研究 #4），平板/桌面維持原有版面 |

## 新增的行動裝置導覽元件（僅 `group-member-view`）

本 feature 為 `group-member-view` 新增一個底部導覽列的樣板結構（沿用既有
`GroupMemberViewComponent` 之 `activeTab`/`setTab()`，僅新增 CSS 使其在
手機寬度下改為固定於畫面底部、加大觸控範圍，不新增獨立元件或 TypeScript
狀態）。
