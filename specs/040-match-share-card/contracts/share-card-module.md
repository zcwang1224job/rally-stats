# Contract: 前端分享圖卡模組（`apps/web/src/app/core/match-share-card/`）

**Feature**: 040-match-share-card | 型別定義見 [data-model.md](../data-model.md) B 節。

本文件定義模組對外的介面，以及它與比賽詳情 dialog、四個呼叫端之間的約定。實作細節交給 tasks 與實作階段。

---

## 1. 比賽詳情 dialog 的新輸入

`MatchRecordDetailDialogComponent`（`core/match-record-detail/`）：

| 輸入 | 型別 | 預設 | 行為 |
|---|---|---|---|
| `shareContext` | `ShareCardContext \| null` | `null` | 為 null 時**不顯示**「分享圖卡」按鈕。不為 null 且 `detail()` 已載入（非 loading、非 loadError）時，按鈕可以點擊（FR-001）。 |

按鈕按下 → 開啟 `ShareCardDialogComponent`，並傳入 `detail()` 與 `shareContext()`。詳情 dialog 本身保持開啟（FR-003）。

## 2. 呼叫端的義務

| 呼叫端 | `groupName` 來源 | `perspective` |
|---|---|---|
| `features/member/match-history` | 被點開那一列的 `group_name` | `{ kind: 'mine', myTeam: row.won ? row.winner_team : other(row.winner_team) }` |
| `features/friends/friend-match-records` | 被點開那一列的 `group_name` | `{ kind: 'neutral' }` |
| `features/group-member-view/match-records` | 新輸入 `groupName`，由 `group-member-view` 傳入 `g.name` | `{ kind: 'neutral' }` |
| `features/member/my-groups/group-history` | 頁面資料的 `group_name` | `{ kind: 'neutral' }` |

呼叫端在 `openDetail()` 時一併設定 context；關閉 dialog 或改開另一場比賽時，context 必須跟著換，不能沿用上一場的。

## 3. 純函式（無 DOM、無翻譯）

```ts
buildScoreTrendPoints(detail: MatchRecordDetailResponse): ScoreTrendPoint[] | null
// core/match-record-detail/score-trend.ts；詳情 dialog 與圖卡共用（research Decision 4）

pickHighlights(detail: MatchRecordDetailResponse, protagonist: 'A' | 'B'): Highlight[]
// 0–3 個；不完整紀錄時為 []；確定性（FR-011～FR-015，research Decision 7）

highlightThreshold(targetScore: number, ratio: number): number
// max(2, floor(targetScore × ratio))

buildShareCardModel(detail: MatchRecordDetailResponse, context: ShareCardContext): ShareCardModel
```

**不變式**（皆列為 spec 測試項）：
- `model.teams[0]` 為主角隊，且對每一隊而言，`team`、`score`、`nicknames` 都取自同一個原始隊伍（FR-019）。
- `record_completeness !== 'complete'` ⇒ `trend === null`、`highlights.length === 0`、`averagePointSeconds === null`。
- 同樣的輸入 ⇒ 深度相等的輸出（SC-007）。

## 4. 繪製

```ts
renderShareCard(
  ctx: ShareCardCanvas,            // CanvasRenderingContext2D 的子集介面，測試以 RecordingContext 實作
  model: ShareCardModel,
  palette: SharePalette,
  text: ShareCardText,             // (key, params) => string，正式環境包 TranslateService.instant
  fonts: { base: string; score: string },
): void
```

- 畫布固定 1080×1350，不乘 DPR（FR-004）。
- 值為 null 或空的元素不繪製，下方區塊往上遞補，不留空框（FR-009）。
- 暱稱以 `measureText` 截斷並加上「…」，確保不超出分配的寬度（Edge Case、SC-005）。
- 不繪製任何 QR 碼或網址（FR-006），只在頁尾畫品牌字樣 `Rally Stats`。

## 5. 平台能力（`ShareCardActions`，可注入替換）

| 方法 | 回傳 | 說明 |
|---|---|---|
| `rasterize(model, palette)` | `Promise<Blob>` | 建立離屏 canvas，`await document.fonts.ready` 後繪製，再 `toBlob('image/png')` |
| `canShareFiles(file)` | `boolean` | `navigator.canShare?.({ files: [file] }) === true` |
| `share(file)` | `Promise<'shared' \| 'cancelled'>` | `AbortError` 回傳 `'cancelled'`，其他錯誤則拋出 |
| `canCopyImage()` | `boolean` | `isSecureContext && 'ClipboardItem' in window && !!navigator.clipboard?.write` |
| `copyImage(blob)` | `Promise<void>` | `navigator.clipboard.write([new ClipboardItem({ 'image/png': blob })])` |
| `download(blob, fileName)` | `void` | object URL 加上 `<a download>`，觸發後立即 revoke |

## 6. 預覽 dialog（`ShareCardDialogComponent`）

| 輸入／方法 | 說明 |
|---|---|
| `open(detail, context)` | 建立模型，以預設的 `'light'` 配色產生 Blob，顯示 `<img [src]="objectUrl" [alt]="altText">` |
| 配色切換（亮／暗，`aria-pressed`） | 重新產生 Blob；之後的下載、分享、複製都使用新的 Blob（FR-024） |
| 「分享」 | 只在 `canShareFiles` 為 true 時顯示（FR-021） |
| 「複製圖片」 | 只在 `canCopyImage` 為 true 時顯示，成功後顯示已複製提示（FR-022） |
| 「下載圖片」 | 一律顯示（FR-020） |
| 錯誤 | 產生失敗：顯示錯誤，只提供「關閉」。分享或複製失敗：顯示提示並建議下載。取消分享：不顯示任何訊息（FR-023） |
| 關閉 | revoke object URL，焦點回到「分享圖卡」按鈕 |

## 7. 語系 key（`matchShareCard.*`，zh-TW 與 en 必須同時存在）

`openButton`、`previewTitle`、`themeLight`、`themeDark`、`share`、`copy`、`copied`、`download`、`close`、`generating`、`generateError`、`shareError`、`copyError`、`badge.win`、`badge.victory`、`badge.defeat`、`round`、`duration`、`durationHours`、`avgPerPoint`、`brand`、`altText`、`highlight.{comeback,matchPointsSaved,deuceWin,run,winnerRate,leadChanges,bigMargin}`。
