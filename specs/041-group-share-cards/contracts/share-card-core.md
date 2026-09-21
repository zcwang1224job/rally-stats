# Contract: 圖卡共用層（`apps/web/src/app/core/share-card/`）

**Feature**: 041-group-share-cards | 型別定義見 [data-model.md](../data-model.md) 第 2 節；決策依據見 [research.md](../research.md) Decision 1、2、4–6、8、10。

共用層**不得** import `core/match-share-card/`、`core/group-share-card/` 或任何 `features/`（憲章 VI）。以下是它對兩個圖卡模組與頁面公開的介面；實作細節交給 tasks 與實作階段。

---

## 1. 圖卡選項（圖卡模組 → 共用層）

```ts
type ShareCardSource = 'card-rank' | 'card-me' | 'card-match';

interface ShareCardRenderEnv {
  palette: SharePalette;
  text: ShareCardText;              // (key, params) => string
  fonts: ShareCardFonts;
  footer: PromoFooter;              // 由 ShareCardActions 準備好，renderer 只負責畫
}

interface ShareCardOption {
  source: ShareCardSource;
  labelKey: string;                 // 種類切換按鈕的語系 key
  fileName: string;
  altText: TranslatedText;
  draw(ctx: ShareCardCanvas, env: ShareCardRenderEnv): void;   // 純函式、同步
}
```

**不變式**：`draw` 不得碰 DOM、不得非同步、不得讀取翻譯服務以外的全域狀態；同樣的輸入必須產生同樣的繪製序列（SC-010）。

## 2. 預覽外殼

`ShareCardPreviewComponent`（selector `app-share-card-preview`）：

```ts
open(options: readonly ShareCardOption[]): void   // options.length ≥ 1；第一個為預設選取
close(): void
```

| 行為 | 約定 |
|---|---|
| 種類切換 | `options.length === 1` 時**不顯示**；多個時以原生 `<button aria-pressed>` 呈現，切換後重新產圖並**保留當下配色**（FR-003、FR-004） |
| 配色 | 每次 `open()` 重設為亮色；切換後重新產圖（沿用 040 FR-024） |
| 下載／分享／複製 | 依 `ShareCardActions` 的能力偵測顯示或隱藏；分享從點擊事件同步發起、使用預先建立的 `File`（沿用 040 Decision 9） |
| 錯誤 | 使用者取消分享（`AbortError`）不顯示訊息；其他失敗顯示簡短提示並建議下載；產圖失敗顯示錯誤狀態、不關閉外殼 |
| 過期結果 | 每次產圖請求遞增世代編號；較舊的結果完成時直接丟棄 |
| 關閉 | 釋放 object URL、把焦點還給開啟前的元素；Esc 關閉走同一條清理路徑 |
| 替代文字 | 預覽 `<img>` 的 `alt` 取自當下選項的 `altText`（FR-031） |

040 的 `ShareCardDialogComponent.open(detail, context)` 保留為門面：建立單一 `ShareCardOption`（`source: 'card-match'`）後呼叫外殼。比賽詳情 dialog 與四個呼叫端**不修改**。

## 3. 平台動作

```ts
class ShareCardActions {
  rasterize(option: ShareCardOption, theme: ShareTheme): Promise<Blob>;
  canShareFiles(file: File): boolean;
  share(file: File): Promise<void>;          // 只送 { files: [file] }，不帶 title／text／url（Decision 8）
  canCopyImage(): boolean;
  copyImage(blob: Blob): Promise<void>;
  download(blob: Blob, fileName: string): void;
  createObjectUrl(blob: Blob): string;
  revokeObjectUrl(url: string): void;
}
```

`rasterize()` 的責任：等 `document.fonts.ready` → 讀取字型 CSS 變數 → `buildShareCardLink(location, option.source)` → 動態載入 `qrcode` 產生 `QrMatrix`（任何失敗都降為 `null`，**不得**讓產圖失敗）→ 建立固定 1080×1350、不依裝置像素比縮放的 canvas → `option.draw(ctx, env)` → `toBlob('image/png')`。

**不變式**：`share()` 的參數物件只有 `files` 一個鍵（以測試斷言）；`rasterize()` 在 `qrcode` 載入失敗時仍回傳可用的 Blob。

## 4. 連結與 QR

```ts
buildShareCardLink(
  location: { origin: string; host: string },
  source: ShareCardSource,
): ShareCardLink
// qrUrl = `${origin}/?ref=${source}`；displayUrl = host

toQrMatrix(url: string, create: QrCreate): QrMatrix | null
// create 由呼叫端注入（正式環境為動態載入的 qrcode.create），容錯等級固定 'M'；拋錯時回傳 null

qrLayout(size: number): { modulePx: number; offset: number } | null
// modulePx = 滿足 (size + 4) × px ≤ 240 的最大偶數；< 4 則回傳 null
```

**不變式**（皆列為 spec 測試項）：
- `qrUrl` 與 `displayUrl` 不含任何 ID；`ref` 值只會是三個 `ShareCardSource` 之一（FR-021）。
- `modulePx` 必為偶數（research Decision 5：縮圖 50% 後每模組仍為整數像素）。
- `size = 33` → `modulePx = 6`；`size = 37` → `4`；`size ≥ 57` → `null`。

## 5. 頁尾

```ts
interface PromoFooter {
  link: ShareCardLink;
  qr: QrMatrix | null;
  meta: string | null;
}

drawPromoFooter(ctx: ShareCardCanvas, footer: PromoFooter, env: Omit<ShareCardRenderEnv, 'footer'>): void
```

版面（1080×1350、左右邊距 72、下邊距 56、頁尾高 240）：

| 元素 | 位置 | 約定 |
|---|---|---|
| 分隔線 | 頁尾上方 | 沿用 040 的 `palette.divider` |
| QR 底板 | 右側 240×240 | **一律白底、近黑模組**，兩種配色相同、不反相；`qr === null` 時整塊不畫，左側文字可用到全寬 |
| `meta` | 左側第一行 | 有值才畫（040：比賽時長 · 平均每分耗時） |
| 品牌字樣 | 左側 | `shareCard.brand`，粗體 |
| 標語 | 左側 | `shareCard.tagline` |
| 可讀網址 | 左側 | `link.displayUrl`，粗體，方便手動輸入 |
| 掃碼提示 | 左側最下 | `shareCard.scanHint`；`qr === null` 時不畫 |

所有左側文字以 `truncateToWidth()` 限制寬度，**不得**畫進 QR 底板範圍（SC-005）。

## 6. 排版

```ts
interface Block { height: number; minHeight?: number; draw(y: number, height: number): void }

stackBlocks(
  blocks: readonly Block[],
  area: { top: number; bottom: number; gap: number; minGap: number },
): void
```

規則（research Decision 6）：放得下 → 垂直置中、不收縮；放不下 → 先把間距降到 `minGap`，再由上而下把有 `minHeight` 的區塊收縮到剛好放下；仍放不下 → 由 `top` 往下排。共用常數 `SHARE_CARD_MIDDLE_TOP`、`SHARE_CARD_MIDDLE_BOTTOM` 由本模組匯出，三種圖卡共用同一個中段範圍。

**不變式**：任何圖卡在其最壞情況輸入下，`draw` 的繪製範圍不得超過 `SHARE_CARD_MIDDLE_BOTTOM`（各 renderer spec 以 `RecordingContext` 斷言）。

## 7. 040 renderer 的調整範圍（FR-022）

| 項目 | 是否改變 |
|---|---|
| `buildShareCardModel()`、`pickHighlights()` 及其 spec | **不變**（一行都不改） |
| 標題、隊伍、走勢、亮點各區塊的內容與先後順序 | 不變 |
| 區塊堆疊 | 改用 `stackBlocks()`；走勢圖 `minHeight: 140`、亮點區塊以列高 60→52 表達 `minHeight` |
| 頁尾 | 改用 `drawPromoFooter()`；時長／每分耗時改由 `meta` 帶入 |
| 檔名、替代文字、視角 | 不變 |

## 8. 語系 key

| 命名空間 | 內容 |
|---|---|
| `shareCard.*`（新增，共用） | `brand`、`tagline`、`scanHint`、`previewTitle`、`kindLabel`、`themeLabel`／`themeLight`／`themeDark`、`share`、`copy`、`copied`、`download`、`close`、`generating`、`generateError`、`shareError`、`copyError`、`dateFormat` |
| `matchShareCard.*`（縮減） | 只留比賽專屬：`openButton`、`kind`、`badge.*`、`round`、`duration`、`durationHours`、`avgPerPoint`、`altText`、`highlight.*` |

兩份語系檔（`zh-TW`、`en`）在上述命名空間的 key 集合必須完全相同（以測試斷言）。
