# Contract: 圖卡共用層（`apps/web/src/app/core/share-card/`）

**Feature**: 041-group-share-cards | 型別定義見 [data-model.md](../data-model.md) 第 2 節；決策依據見 [research.md](../research.md) Decision 1、2、4–6、8、10。

共用層**不得** import `core/match-share-card/`、`core/group-share-card/` 或任何 `features/`（憲章 VI）。它不認識任何圖卡的**模型**；唯一與圖卡種類有關的是 `ShareCardSource` 的三個值，只用來組出 `ref` 參數。以下是它對兩個圖卡模組與頁面公開的介面；實作細節交給 tasks 與實作階段。

---

## 1. 共用型別（`share-card-canvas.ts`、`share-card-option.ts`）

`share-card-canvas.ts` 放 canvas 介面與尺寸常數（`ShareCardCanvas`、`ShareCardText`、`ShareCardFonts`、`TranslatedText`、`ShareTheme`、`SharePalette`、`SHARE_CARD_WIDTH`／`HEIGHT`／`PADDING`）。

`share-card-option.ts` **只放型別、不 import 任何實作檔**，讓 footer、link、qr、actions、preview 都依賴它而不互相依賴（避免型別循環）。以下型別在 Phase 2 就定案，之後各 phase 不再改欄位：

```ts
type ShareCardSource = 'card-rank' | 'card-me' | 'card-match';

interface ShareCardLink {
  qrUrl: string;                    // `${origin}/?ref=${source}`
  displayUrl: string;               // host
}

interface QrMatrix {
  size: number;
  isDark(row: number, col: number): boolean;
}

interface PromoFooter {
  link: ShareCardLink;
  qr: QrMatrix | null;              // null：產生失敗、網址過長，或 US2 之前
  meta: string | null;              // actions 一律給 null；040 renderer 以 { ...env.footer, meta } 覆寫
}

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
| 種類切換 | `options.length === 1` 時**不顯示**；多個時以 `role="group"`（`aria-label` 為 `shareCard.kindLabel`）內的原生 `<button aria-pressed>` 呈現，切換後重新產圖並**保留當下配色**（FR-003、FR-004） |
| 配色 | 每次 `open()` 重設為亮色與第一個選項；切換後重新產圖（沿用 040 FR-024） |
| 下載／分享／複製 | 依 `ShareCardActions` 的能力偵測顯示或隱藏；分享從點擊事件同步發起、使用預先建立的 `File`（沿用 040 Decision 9） |
| 錯誤 | 使用者取消分享不顯示訊息；其他失敗顯示簡短提示並建議下載；產圖失敗顯示錯誤狀態、不提供下載、不關閉外殼 |
| 過期結果 | 每次產圖請求遞增世代編號；較舊的結果完成時直接丟棄 |
| 語言 | 語言切換後重新產圖（沿用 040 SC-008） |
| 關閉 | 釋放 object URL、把焦點還給開啟前的元素；Esc 關閉走同一條清理路徑 |
| 替代文字 | 預覽 `<img>` 的 `alt` 取自當下選項的 `altText`（FR-031） |

040 的 `ShareCardDialogComponent.open(detail, context)` 保留為門面：建立單一 `ShareCardOption`（`source: 'card-match'`）後呼叫外殼。比賽詳情 dialog 與四個呼叫端**不修改**。

## 3. 平台動作

```ts
class ShareCardActions {
  rasterize(option: ShareCardOption, theme: ShareTheme): Promise<Blob>;
  canShareFiles(file: File): boolean;
  share(file: File): Promise<'shared' | 'cancelled'>;   // 只送 { files: [file] }，不帶 title／text／url（Decision 8）；AbortError → 'cancelled'
  canCopyImage(): boolean;
  copyImage(blob: Blob): Promise<void>;
  download(blob: Blob, fileName: string): void;         // 1 秒後才 revoke（Safari）
  createObjectUrl(blob: Blob): string;
  revokeObjectUrl(url: string): void;
}

const SHARE_CARD_QR_LOADER: InjectionToken<() => Promise<QrCreate>>;
// 預設 () => import('qrcode').then((m) => m.create ?? m.default.create)；測試以替身取代
```

`rasterize()` 的責任：等 `document.fonts?.ready` → 讀取字型 CSS 變數 → `link = buildShareCardLink(window.location, option.source)` → 以 `SHARE_CARD_QR_LOADER` 取得 `create` 並 `toQrMatrix(link.qrUrl, create)`（任何失敗都降為 `null`，**不得**讓產圖失敗；US2 之前 `qr` 固定為 `null`）→ `env.footer = { link, qr, meta: null }` → 建立固定 1080×1350、不依裝置像素比縮放的 canvas → `option.draw(ctx, env)` → `toBlob('image/png')`。

測試方式：jsdom 沒有 canvas，`rasterize()` 的 spec 以 `vi.spyOn(document, 'createElement')` 在 `'canvas'` 時回傳假 canvas（`getContext` 回傳 `RecordingContext`、`toBlob` 直接回呼一個 PNG Blob）。

**不變式**：`share()` 傳給 `navigator.share` 的物件只有 `files` 一個鍵（以測試斷言）；`rasterize()` 在 `qrcode` 載入失敗時仍回傳可用的 Blob。

## 4. 連結與 QR

```ts
buildShareCardLink(
  location: { origin: string; host: string },
  source: ShareCardSource,
): ShareCardLink
// qrUrl = `${origin}/?ref=${source}`；displayUrl = host

toQrMatrix(url: string, create: QrCreate): QrMatrix | null
// create 由呼叫端注入；容錯等級固定 'M'；拋錯時回傳 null

qrLayout(size: number): { modulePx: number; offset: number } | null
// modulePx = 滿足 (size + 4) × px ≤ 240 的最大偶數；< 4 則回傳 null
```

**不變式**（皆列為 spec 測試項）：
- `qrUrl` 與 `displayUrl` 不含任何 ID；`ref` 值只會是三個 `ShareCardSource` 之一（FR-021）。
- `modulePx` 必為偶數（research Decision 5：縮圖 50% 後每模組仍為整數像素）。
- `size = 29` 或 `33` → `modulePx = 6`；`37`～`53` → `4`；`≥ 57` → `null`。一般網址為 33 模組。

## 5. 頁尾

```ts
drawPromoFooter(ctx: ShareCardCanvas, footer: PromoFooter, env: Omit<ShareCardRenderEnv, 'footer'>): void
```

Phase 2 期間 `drawPromoFooter()` 仍畫 040 的舊頁尾（分隔線、右側品牌、左側 `meta`），`link` 與 `qr` 不被繪製；US2 改為以下的導流頁尾。

**導流頁尾版面**（1080×1350；左右邊距 72；頁尾區 y = 1054～1294，高 240，下邊距 56）：

| 元素 | 位置與尺寸 | 約定 |
|---|---|---|
| 分隔線 | y = 1026，x = 72～1008，高 2 | `palette.divider` |
| QR 底板 | 左上角 (768, 1054)，240×240，圓角 16 | 顏色 `palette.qrPlate`（兩種色盤皆 `#ffffff`）；`qr === null` 或 `qrLayout()` 為 `null` 時整塊不畫 |
| QR 模組 | 底板內置中，每模組 `modulePx` 見方 | 顏色 `palette.qrModule`（兩種色盤皆 `#111827`），不反相 |
| 左側文字欄 | x = 72，右緣 ≤ 744（有 QR）或 ≤ 1008（無 QR） | 由 y = 1054 起依下表往下排；省略的行不佔空間；全部以 `truncateToWidth()` 限寬 |

| 行 | 字級 | 行高 | 內容 | 何時畫 |
|---|---|---|---|---|
| meta | 26px，`palette.textMuted` | 40 | `footer.meta` | 有值時 |
| 品牌 | bold 36px，`palette.text` | 48 | `shareCard.brand` | 一律 |
| 標語 | 28px，`palette.textMuted` | 48 | `shareCard.tagline` | 一律 |
| 可讀網址 | bold 32px，`palette.text` | 50 | `footer.link.displayUrl` | 一律 |
| 掃碼提示 | 24px，`palette.textMuted` | 32 | `shareCard.scanHint` | 有畫 QR 時 |

五行全畫時總高 218，最後一行下緣 1272 ≤ 1294。標語字級 28px 是為了讓英文標語（37 字元）在 672px 內不被截斷。

## 6. 排版

```ts
interface Block { height: number; minHeight?: number; draw(y: number, height: number): void }

stackBlocks(
  blocks: readonly Block[],
  area: { top: number; bottom: number; gap: number; minGap: number },
): void
```

規則（research Decision 6；全部以整數像素計算）：

1. **放得下**（區塊總高＋`gap` × 間距數 ≤ 可用高度）：不收縮；起點為 `top + Math.floor(剩餘 / 2)`，整組垂直置中。
2. **間距收縮**：間距改為 `max(minGap, Math.floor((可用 − 區塊總高) / 間距數))`；若因此放得下，所有區塊高度不變，剩餘像素同樣置中。
3. **區塊收縮**：間距為 `minGap` 仍不足時，由上而下依序收縮有 `minHeight` 的區塊，每個只收縮到「剛好放下」或其 `minHeight` 為止，第一個吃完額度後才輪到下一個；起點為 `top`。
4. **仍放不下**：由 `top` 開始往下排。各圖卡 renderer 的 spec 保證最壞情況不會走到這一步。

| 常數 | Phase 2（沿用 040） | US2 之後 |
|---|---|---|
| `SHARE_CARD_MIDDLE_TOP` | 230 | 210 |
| `SHARE_CARD_MIDDLE_BOTTOM` | 1174 | 996 |
| `SHARE_CARD_FOOTER_TOP` | 1246 | 1054 |
| `SHARE_CARD_BLOCK_GAP`／`SHARE_CARD_BLOCK_MIN_GAP` | 48／32 | 48／32 |

**不變式**：任何圖卡在其最壞情況輸入下，中段繪製（背景之後、頁尾之前）的下緣不得超過 `SHARE_CARD_MIDDLE_BOTTOM`。各 renderer spec 以 `RecordingContext.bottomEdge({ skipFirst: 1, skipLast: footerOpCount(…) })` 斷言（第 1 筆是整張畫布背景，最後 N 筆是頁尾）。

## 7. 040 renderer 的調整範圍（FR-022）

| 項目 | 是否改變 |
|---|---|
| `buildShareCardModel()`、`pickHighlights()` 及其 spec | **不變**（一行都不改） |
| 標題、隊伍、走勢、亮點各區塊的內容與先後順序 | 不變 |
| `renderShareCard()` 簽章 | 改為 `renderShareCard(ctx, model, env: ShareCardRenderEnv)` |
| 區塊堆疊 | 改用 `stackBlocks()`。US2 起走勢圖 `minHeight: 140`；亮點區塊 `minHeight` 為 `列數 × 52 + 48`（現行高度為 `列數 × 60 + 48`，48 是上下內距）；**隊伍區塊不收縮** |
| 頁尾 | 改用 `drawPromoFooter(ctx, { ...env.footer, meta }, env)`；`meta`（時長 · 平均每分耗時）仍由本 renderer 組出，時長相關測試留在 renderer spec |
| 檔名、替代文字、視角 | 不變 |

## 8. 語系 key

| 命名空間 | 內容 | 一致性測試 |
|---|---|---|
| `shareCard.*`（新增，共用） | `brand`、`tagline`、`scanHint`、`previewTitle`、`kindLabel`、`themeLabel`／`themeLight`／`themeDark`、`share`、`copy`、`copied`、`download`、`close`、`generating`、`generateError`、`shareError`、`copyError`、`dateFormat` | `core/share-card/share-card-i18n.spec.ts`（含 `dateFormat` 的值） |
| `matchShareCard.*`（縮減） | 只留比賽專屬：`openButton`、`kind`、`badge.*`、`round`、`duration`、`durationHours`、`avgPerPoint`、`altText`、`highlight.*` | 040 既有的 `share-card-i18n.spec.ts`（刪除其中 `dateFormat` 兩行） |

兩份語系檔（`zh-TW`、`en`）在上述命名空間的 key 集合必須完全相同。
