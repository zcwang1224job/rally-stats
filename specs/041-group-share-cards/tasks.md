---

description: "Task list for 041-group-share-cards"
---

# Tasks: 團分享圖卡與導流頁尾（Group Share Cards）

**Input**: Design documents from `/specs/041-group-share-cards/`

**Prerequisites**: plan.md、spec.md、research.md、data-model.md、contracts/（`share-card-core.md`、`group-share-card.md`、`landing-link.md`）、quickstart.md

**Tests**: **必做**。Constitution II 要求核心規則的測試先於實作撰寫，plan.md 的 Testing 段也列了每個 spec 檔。每個 story 的測試任務 MUST 先完成，並確認它會失敗，才開始該 story 的實作任務。唯一的例外是 Phase 2 的「搬移」任務：那是行為不變的重構，保證來自既有 spec 在「允許變更清單」之外不改動而維持全綠。

**Organization**: 依 spec.md 的 user story 分 phase。本功能**只改 `apps/web`**，後端零變動。Phase 2 把 040 的共用部分抽成 `core/share-card/`，並一次定好最終的共用型別（`PromoFooter`、`ShareCardRenderEnv` 從 Phase 2 起就是最終形狀），完成且全綠後才進任何 story。US1（排行榜卡）是 MVP。

## Format: `[ID] [P?] [Story] Description`

- **[P]**：可平行執行（不同檔案、不依賴尚未完成的任務）
- **[Story]**：對應 spec.md 的 user story（US1～US4）
- 路徑皆為 repo 相對路徑；前端簡寫 `web/` = `apps/web/src/`
- 任務描述結尾的（FR-…／SC-…）標出它實作或驗證的需求

## 環境備註（worktree）

- 前端：`ln -s /Users/zcwang/projects/rally-stats/apps/web/node_modules apps/web/node_modules`，在 `apps/web` 執行 `npx ng test --watch=false`、`npx ng lint`、`npx ng build`。
- T001 會新增 devDependency `@types/qrcode`：worktree 的 `node_modules` 是指向主 checkout 的 symlink，所以 `npm install` 要在**主 checkout 的 `apps/web`** 以更新後的 `package.json`／`package-lock.json` 執行一次（`qrcode@1.5.4` 本體已經在 `node_modules` 裡）。
- 後端不需要跑測試；以 `git diff --stat origin/ut...HEAD -- apps/api` 為空作為「後端零變動」的證據。
- `ng test` 既有的 1 個 unhandled error（`NG04002 … 'groups/reauth'`，來自 `admin-page.component.spec.ts`）與本功能無關。
- 測試資料的時間戳一律用 UTC 中午（例如 `2026-09-16T04:00:00Z`），避免檔名與日期的斷言受 CI 時區影響。

## 術語對照

| 本文用語 | 程式名稱 | 說明 |
|---|---|---|
| 共用層 | `core/share-card/` | 不認識任何圖卡的**模型**；只以 `ShareCardSource` 的三個值區分來源 |
| 導流頁尾 | `PromoFooter`、`drawPromoFooter()` | 品牌＋標語＋可讀網址＋QR；Phase 2 期間仍畫 040 的舊頁尾 |
| 預覽外殼 | `ShareCardPreviewComponent`（`app-share-card-preview`） | 原 040 的 dialog 內容搬過來後的共用元件 |
| 040 門面 | `ShareCardDialogComponent.open(detail, context)` | 介面不變，內部委派給預覽外殼 |
| 團戰績頁 | `features/member/my-groups/group-history/` | 「我的團」點進某一團的頁面 |
| 排行榜卡 | `leaderboard-card-*`；來源 `card-rank`；檔名 `rally-stats-rank-…` | spec 的「團排行榜卡」 |
| 我的成績卡 | `my-stats-card-*`；來源 `card-me`；檔名 `rally-stats-me-…` | spec 的「我的本團成績卡」 |
| 活動日期 | `GroupShareCardContext.createdAt` | 團的建立時間（research Decision 7） |
| 有出賽 | `total_matches ≥ 1` | |
| 本人列 | `final_standings` 中 `is_self === true` 的列 | |
| 中段 | `SHARE_CARD_MIDDLE_TOP`～`SHARE_CARD_MIDDLE_BOTTOM` | 標題區與頁尾之間、由 `stackBlocks()` 排版的範圍 |

## 版面常數（contracts/share-card-core.md §5、§6 為準）

| 常數 | Phase 2（沿用 040） | US2 之後 |
|---|---|---|
| `SHARE_CARD_MIDDLE_TOP` | 230 | 210 |
| `SHARE_CARD_MIDDLE_BOTTOM` | 1174 | 996 |
| `SHARE_CARD_FOOTER_TOP` | 1246 | 1054（＝1350 − 56 − 240） |
| 頁尾分隔線 y | 1214 | 1026 |
| `SHARE_CARD_BLOCK_GAP`／`_MIN_GAP` | 48／32 | 48／32 |

---

## Phase 1: Setup（共用基礎）

**Purpose**：相依宣告、全部語系文字與測試 fixtures 一次到位，後續各 story 不必同時改同一批檔案。

- [X] T001 在 `apps/web/package.json` 的 `dependencies` 加入 `"qrcode": "1.5.4"`（與 `angularx-qrcode@20.0.0` 鎖定的版本完全相同，research Decision 4），`devDependencies` 加入 `"@types/qrcode": "^1.5.5"`；在主 checkout 的 `apps/web` 執行 `npm install` 更新 `package-lock.json`，確認 lockfile 中 `node_modules/qrcode` 仍只有一份 1.5.4。
- [X] T002 [P] 在 `web/assets/i18n/zh-TW.json` 與 `web/assets/i18n/en.json` **新增**三個命名空間（此時先不刪任何既有 key；刪除在 T013）：
  - `shareCard.*`：contracts/share-card-core.md §8 列出的全部 key。`brand`＝「Rally Stats」；`tagline`＝zh「計分・排點・戰績，打球一站搞定」／en「Score, schedule and track every game.」；`scanHint`＝zh「掃描 QR 碼開始使用」／en「Scan to get started」；`kindLabel`＝zh「圖卡種類」／en「Card type」；其餘（`previewTitle`、`themeLabel`、`themeLight`、`themeDark`、`share`、`copy`、`copied`、`download`、`close`、`generating`、`generateError`、`shareError`、`copyError`、`dateFormat`）**逐字複製**目前 `matchShareCard.*` 的同名值。
  - `groupShareCard.*`：contracts/group-share-card.md §4 列出的全部 key。zh 文案：`openButton`「分享圖卡」、`kind.leaderboard`「排行榜」、`kind.myStats`「我的成績」、`leaderboard.title`「排行榜」（**不得**含「最終」，FR-012）、`leaderboard.playerCount`「{count} 位球員」、`leaderboard.record`「{wins} 勝 {losses} 敗」、`leaderboard.altText1`「{group} 排行榜：第 {rank1} 名 {name1}」、`leaderboard.altText2`（加上「、第 {rank2} 名 {name2}」）、`leaderboard.altText3`（再加上第 3 位）、`selfTag`「我」、`myStats.title`「我的成績」、`myStats.record`「{wins} 勝 {losses} 敗・共 {matches} 場」、`myStats.standing`「第 {rank} 名／共 {count} 人」、`myStats.trendTitle`「各輪勝率」、`myStats.opponentsTitle`「最常交手」、`myStats.opponentRecord`「{wins} 勝 {losses} 敗」、`myStats.altText`「{group} 我的成績：勝率 {winRate}，{wins} 勝 {losses} 敗」。en 對應翻譯，`selfTag`＝「YOU」。名次一律用參數帶入，文案中不得寫死「第 1／2／3 名」（FR-008、FR-031）。
  - `home.*`：保留既有 `home.title`，新增 `home.features.scoring.title／body`、`home.features.rotation.title／body`、`home.features.stats.title／body`、`home.cta.start`（zh「開始使用」）、`home.cta.login`（zh「登入」）、`home.cta.member`（zh「進入我的頁面」）。功能重點以使用者利益描述（FR-024），例如計分：「手機就是計分板，比分即時同步給全場」。
- [X] T003 [P] 新增兩份語系一致性測試（比照 `web/app/core/match-share-card/share-card-i18n.spec.ts` 的做法 import 兩份 JSON）（FR-030、SC-009）：
  - `web/app/core/share-card/share-card-i18n.spec.ts`：`shareCard` 命名空間兩邊 key 集合完全相同、每個值非空；`dateFormat` 為 zh `yyyy/M/d`、en `MMM d, yyyy`；zh 的 `tagline` 長度 ≤ 16 字。
  - `web/app/core/group-share-card/group-share-card-i18n.spec.ts`：`groupShareCard` 命名空間兩邊 key 集合完全相同、每個值非空；zh 的 `leaderboard.title` 不含「最終」、en 不含「final」（不分大小寫）（FR-012）；`altText1～3` 的文案都以 `{rankN}` 參數帶入名次。
- [X] T004 [P] 建立測試輔助檔 `web/app/core/group-share-card/testing/history-fixtures.ts`：`makeStanding(overrides)` 產生合法的 `FinalStandingRow`（預設 `current_status: 'active'`、`is_self: false`、有出賽）；`makeStandings(count, options?)` 產生依名次排好的 N 列（支援指定第幾列為本人、哪些列並列、哪些列 0 場、哪些列為 `'left'`／`'kicked'`）；`makeHistory(overrides)` 產生合法的 `MemberGroupHistoryResponse`（預設 `group_name: '週三羽球團'`、8 位有出賽球員、本人為第 2 列、`my_stats` 為 6 勝 4 敗 `win_rate: 0.6`、3 輪 `round_win_rates`、4 筆已依場數排序的 `opponent_records`、`matches: []`）；`CREATED_AT = '2026-09-16T04:00:00Z'`。不得使用 `any`。

---

## Phase 2: Foundational（阻擋所有 story 的前置工作）

**Purpose**：把 040 模組中與「比賽」無關的部分抽成 `core/share-card/`（research Decision 1、2），並一次定好最終的共用型別。**這個 phase 對使用者沒有任何可見變化**：040 圖卡的畫面、檔名、按鈕行為都必須與現在完全相同。

**⚠️ CRITICAL**：這個 phase 完成且全綠之前，不得開始任何 story。

**040 保護線（整個 041 期間都適用）**：以下檔案**一行都不得修改**——`web/app/core/match-share-card/share-card-model.ts`、`share-card-model.spec.ts`、`share-card-highlights.ts`、`share-card-highlights.spec.ts`、`testing/detail-fixtures.ts`、`web/app/core/match-record-detail/` 整個目錄、以及三個未被本功能觸及的呼叫端 `web/app/features/member/match-history/`、`web/app/features/friends/friend-match-records/`、`web/app/features/group-member-view/`。第四個呼叫端 `group-history` 在 US1 會**新增**程式，但既有的比賽詳情 dialog 與其 `shareContext` 不得修改。

**`share-card-renderer.spec.ts` 在 Phase 2 允許的變更（僅此四項，其餘不得改）**：
1. import 路徑（`RecordingContext`、`SHARE_PALETTES` 搬家）。
2. `fakeText()` 認得 `shareCard.dateFormat`（取代 `matchShareCard.dateFormat`），並能處理 `shareCard.*` 前綴。
3. `draw()` 輔助函式改用新簽章 `renderShareCard(ctx, model, env)`，`env` 以 `testFooter()`（T006）與既有色盤、字型組成。
4. 移除已搬到 `share-card-drawing.spec.ts` 的 `truncateToWidth` 案例（T007）。

- [X] T005 建立 `web/app/core/share-card/share-card-canvas.ts`：從 `web/app/core/match-share-card/share-card.models.ts` 搬入 `ShareCardCanvas`、`ShareCardText`、`ShareCardFonts`、`TranslatedText`、`ShareTheme`、`SharePalette`；從 `share-card-renderer.ts` 搬入 `SHARE_CARD_WIDTH`、`SHARE_CARD_HEIGHT`、`SHARE_CARD_PADDING`。接著建立 `web/app/core/share-card/share-card-option.ts`，**只放型別、不 import 任何實作檔**（避免與 footer／link／qr 形成循環，contracts/share-card-core.md §1）：`ShareCardSource`、`ShareCardLink`、`QrMatrix`、`PromoFooter { link: ShareCardLink; qr: QrMatrix | null; meta: string | null }`、`ShareCardRenderEnv { palette; text; fonts; footer: PromoFooter }`、`ShareCardOption`。這些就是最終形狀，後續 phase 不再改欄位。`share-card.models.ts` 改為 `export type { … } from '../share-card/share-card-canvas'`，`share-card-renderer.ts` 改為 re-export 三個常數，使所有既有匯入路徑不必改。共用層**不得** import `match-share-card/` 或 `group-share-card/`。
- [X] T006 [P] 搬移測試工具並擴充：
  - `web/app/core/match-share-card/share-card-palette.ts` 與 `share-card-palette.spec.ts` 以 `git mv` 搬到 `web/app/core/share-card/`，只改 import 路徑；舊位置留 `export { SHARE_PALETTES } from '../share-card/share-card-palette'` 的轉出檔。
  - `web/app/core/match-share-card/testing/recording-context.ts` 以 `git mv` 搬到 `web/app/core/share-card/testing/recording-context.ts`，並擴充：(a) 以單一有序陣列 `ops` 記錄每一筆 `fillText`／`fillRect`／`roundRect`／`arc`，每筆含 `top` 與 `bottom`（文字依 `textBaseline: 'top'` 取 `y`～`y + fontSize`；矩形取 `y`～`y + h`；圓取 `y − radius`～`y + radius`）；(b) `recordedRoundRects` 每筆加記當下的 `fillStyle` 為 `color`；(c) `opCount()`；(d) `bottomEdge({ skipFirst = 0, skipLast = 0 })` 回傳 `ops.slice(skipFirst, ops.length − skipLast)` 的最大 `bottom`。
- [X] T007 先寫 `web/app/core/share-card/share-card-drawing.spec.ts`：把 `share-card-renderer.spec.ts` 裡的 `truncateToWidth` 案例搬過來（允許變更第 4 項），並補上：放得下時原樣回傳、放不下時回傳最長前綴加「…」且量測寬度 ≤ 上限、對含 emoji／代理對的字串不會切在中間、上限小於「…」本身時回傳「…」。接著建立 `web/app/core/share-card/share-card-drawing.ts`，把 `share-card-renderer.ts` 的 `truncateToWidth`、`panel`、`pill`、`roundedFill` **原封不動**搬入並 export；renderer 改為 import。
- [X] T008 先寫 `web/app/core/share-card/share-card-layout.spec.ts`（contracts/share-card-core.md §6），以會記錄 `draw(y, height)` 引數的假 Block 驗證：
  - 放得下（總高含 48 間距 ≤ 可用高度）：不收縮；整組在 `top`～`bottom` 間垂直置中，起點為 `top + Math.floor(剩餘 / 2)`；相鄰間距 48；每個 Block 收到的 `height` 等於自己的 `height`。
  - 放不下：間距改為 `max(32, Math.floor((可用 − 區塊總高) / 間距數))`；若因此放得下，所有 Block 高度不變，剩餘像素（< 間距數）以同樣方式置中。
  - 間距 32 仍不足：由上而下依序收縮有 `minHeight` 的 Block，每個只收縮到「剛好放下」或其 `minHeight` 為止（第一個可收縮 Block 吃完額度後才輪到下一個）；收縮後的高度為整數；沒有 `minHeight` 的 Block 永不收縮；此時起點為 `top`、沒有剩餘空間。
  - 全部收縮到下限仍不足：第一個 Block 的 y 等於 `top`，由上往下排。
  - 只有 1 個 Block、空陣列：不拋錯。同樣輸入呼叫兩次，記錄的引數完全相同（SC-010）。
  
  接著建立 `web/app/core/share-card/share-card-layout.ts`：export `Block`、`stackBlocks(blocks, area)`，以及「版面常數」表中 Phase 2 欄的 `SHARE_CARD_MIDDLE_TOP`、`SHARE_CARD_MIDDLE_BOTTOM`、`SHARE_CARD_FOOTER_TOP`、`SHARE_CARD_BLOCK_GAP`、`SHARE_CARD_BLOCK_MIN_GAP`（**此時沿用 040 現值**，US2 才調整）。
- [X] T009 先寫 `web/app/core/share-card/share-card-footer.spec.ts`（本 phase 只涵蓋 040 現行頁尾）：以 `RecordingContext` 驗證畫出分隔線與右對齊的 `shareCard.brand`；`footer.meta` 有值時在左側畫出、寬度不與品牌字樣重疊，為 `null` 時不畫；`footer.link` 與 `footer.qr` 在本 phase 不被繪製。接著建立 `web/app/core/share-card/share-card-footer.ts`：`drawPromoFooter(ctx, footer: PromoFooter, env: Omit<ShareCardRenderEnv, 'footer'>)`，內容為 `share-card-renderer.ts` 的 `drawFooter()` **原樣搬移**，差別只有品牌字樣的 key 改為 `shareCard.brand`、左側文字改由 `footer.meta` 傳入。最後新增 `web/app/core/share-card/testing/footer-ops.ts`（需要本任務的 `drawPromoFooter()`，所以放在這裡而不是 T006）：`testFooter(overrides?)` 回傳固定的 `PromoFooter`（`link: { qrUrl: 'https://rallystats.test/?ref=card-match', displayUrl: 'rallystats.test' }`、`qr: null`、`meta: null`）；`footerOpCount(footer, env)` 以一個新的 `RecordingContext` 呼叫 `drawPromoFooter()` 後回傳 `opCount()`。各 renderer spec 以 `ctx.bottomEdge({ skipFirst: 1, skipLast: footerOpCount(…) })` 取得「背景之後、頁尾之前」的中段下緣（第 1 筆一律是整張畫布的背景）。
- [X] T010 [P] 先寫 `web/app/core/share-card/share-card-link.spec.ts`（contracts/share-card-core.md §4、landing-link.md §1）：三種 `source` 各得到 `${origin}/?ref=${source}`；`displayUrl` 等於 `host`，不含 `http`、`/`、`?`；`origin` 含連接埠時照常帶入；輸出字串不含任何 UUID 樣式（以正規表示式斷言）（FR-019、FR-021）。接著建立 `web/app/core/share-card/share-card-link.ts`：`buildShareCardLink(location, source)`。本 phase 就建立，是為了讓 `PromoFooter.link` 從一開始就是必填（contracts §1）；頁尾到 US2 才把它畫出來。
- [X] T011 修改 `web/app/core/match-share-card/share-card-renderer.ts`：簽章改為 `renderShareCard(ctx, model, env: ShareCardRenderEnv)`；區塊堆疊改呼叫 `stackBlocks()`（本 phase 各 Block 都不給 `minHeight`，`draw` 忽略第二個引數）；頁尾改呼叫 `drawPromoFooter(ctx, { ...env.footer, meta }, env)`，其中 `meta` 由原本 `drawFooter()` 內組時長與每分耗時的邏輯產生（`durationText()` 留在本檔，research Decision 6、contracts §7）；日期樣式 key 改為 `shareCard.dateFormat`；刪除本檔已搬走的私有函式與常數。`share-card-renderer.spec.ts` 只做「允許的變更」清單中的四項，且必須全綠——這是版面未變的證據。040 的時長、小時制、每分耗時三個既有案例保留在本 spec，不搬移。
- [X] T012 搬移分享動作、建立預覽外殼、改造 040 門面。三者互相依賴，**合併為一個任務**，只在最後一步要求全綠（中間步驟因型別不一致而編譯失敗是預期的）：
  1. **先寫測試**：把 `web/app/core/match-share-card/share-card-actions.service.spec.ts` 以 `git mv` 搬到 `web/app/core/share-card/`，既有 8 例全數保留，並新增：`rasterize(option, theme)` 以 `SHARE_PALETTES[theme]`、翻譯函式、字型與 `footer`（本 phase 為 `{ link: buildShareCardLink(window.location, option.source), qr: null, meta: null }`）組出 `env` 後呼叫 `option.draw(ctx, env)` 恰好一次；`share(file)` 傳給 `navigator.share` 的物件**只有 `files` 一個鍵**（research Decision 8、FR-023）。`rasterize` 的測試以 `vi.spyOn(document, 'createElement')` 在 `'canvas'` 時回傳假 canvas `{ width, height, getContext: () => recordingContext, toBlob: (cb) => cb(new Blob(['x'], { type: 'image/png' })) }`（jsdom 沒有 canvas；`document.fonts` 在 jsdom 不存在，既有的 `?.` 已處理）。
  2. **再寫測試**：新增 `web/app/core/share-card/share-card-preview/share-card-preview.component.spec.ts`，把 `share-card-dialog.component.spec.ts` 中與比賽無關的 15 例逐例搬入並改用假的 `ShareCardOption`：以亮色產圖並以替代文字顯示圖片；產圖中顯示 generating 狀態；一律提供下載且檔名來自選項；產圖失敗時顯示錯誤、不提供下載；關閉時釋放圖片 URL；切換語言後重新產圖（040 SC-008）；預設亮色且以 pressed 按鈕呈現；切到暗色會重繪、換預覽並下載暗色圖；重選同一配色不做事；下次開啟回到亮色；裝置不能分享圖片時隱藏分享；分享使用預先建立的檔案、點擊時不重繪；使用者取消分享時不顯示訊息；分享失敗時建議下載；不能複製時隱藏、可以時複製 PNG；複製失敗時建議下載。另加一例：過期的產圖結果被丟棄。
  3. **實作**：`web/app/core/match-share-card/share-card-actions.service.ts` 以 `git mv` 搬到 `web/app/core/share-card/`，`rasterize` 改為接受 `ShareCardOption`（不再 import `renderShareCard`）；其餘方法（`canShareFiles`、`share`——維持 `Promise<'shared' | 'cancelled'>`、`canCopyImage`、`copyImage`、`download` 含 1 秒延遲 revoke、`createObjectUrl`、`revokeObjectUrl`）不變。
  4. **實作**：建立 `web/app/core/share-card/share-card-preview/share-card-preview.component.{ts,html,scss}`，把 040 dialog 的內容搬入；公開介面 `open(options: readonly ShareCardOption[])`／`close()`（contracts §2）；內部以 signal `selected` 記住目前選項（本 phase 固定為 `options[0]`，種類切換 UI 留到 US3）；`fileName` 與 `alt` 取自選項；範本中所有 `matchShareCard.*` key 改為對應的 `shareCard.*`。
  5. **實作 040 門面**：新增 `web/app/core/match-share-card/match-share-card-option.ts`，export `toMatchShareCardOption(model): ShareCardOption`（`source: 'card-match'`、`labelKey: 'matchShareCard.kind'`、`fileName`／`altText` 取自 model、`draw` 呼叫 `renderShareCard(ctx, model, env)`），並在兩份語系檔新增 `matchShareCard.kind`（zh「單場比賽」／en「Match」）。`share-card-dialog.component.ts` 縮減為範本只放一個 `<app-share-card-preview>`，`open(detail, context)` **簽章不變**，內部為 `preview.open([toMatchShareCardOption(buildShareCardModel(detail, context))])`。
  6. **改寫門面測試**：`share-card-dialog.component.spec.ts` 只保留比賽專屬的 3 例——以正確的單一選項呼叫外殼（`source` 為 `card-match`、檔名與替代文字來自 model）、不提供視角切換（040 FR-017a）、關閉後外層比賽詳情 dialog 仍開啟且焦點回到觸發按鈕（040 FR-003）——並新增 `web/app/core/match-share-card/match-share-card-option.spec.ts`：`source`、`labelKey`、`fileName`、`altText` 正確，`draw` 會畫出比分。
  7. 在 `apps/web` 執行 `npx ng test --watch=false`，全部通過才算完成。
- [X] T013 （T012 完成後，**不可平行**）從兩份語系檔的 `matchShareCard.*` 刪除已搬到 `shareCard.*` 的 key（`previewTitle`、`themeLabel`、`themeLight`、`themeDark`、`share`、`copy`、`copied`、`download`、`close`、`generating`、`generateError`、`shareError`、`copyError`、`brand`、`dateFormat`），保留 contracts/share-card-core.md §8 列為比賽專屬的 key。同時修改 `web/app/core/match-share-card/share-card-i18n.spec.ts`：刪除 `dateFormat` 的兩行斷言（已由 T003 的 `share-card-i18n.spec.ts` 接手），其餘斷言不變。以 `grep -rn "matchShareCard\.\(previewTitle\|theme\|share\b\|copy\|copied\|download\|close\|generat\|brand\|dateFormat\)" apps/web/src` 確認沒有殘留引用。
- [X] T014 在 `apps/web` 執行 `npx ng test --watch=false`、`npx ng lint`、`npx ng build`，全部通過；並執行 `git diff --stat origin/ut...HEAD -- apps/api apps/web/src/app/core/match-share-card/share-card-model.ts apps/web/src/app/core/match-share-card/share-card-model.spec.ts apps/web/src/app/core/match-share-card/share-card-highlights.ts apps/web/src/app/core/match-share-card/share-card-highlights.spec.ts apps/web/src/app/core/match-share-card/testing/detail-fixtures.ts apps/web/src/app/core/match-record-detail apps/web/src/app/features/member/match-history apps/web/src/app/features/friends/friend-match-records apps/web/src/app/features/group-member-view apps/web/src/app/features/member/my-groups`，輸出必須為空（本 phase 連 `group-history` 都還沒碰）。Commit：「圖卡的預覽、分享與排版改為各種圖卡共用（單場比賽圖卡的畫面與操作不變）」。

**Checkpoint**：共用層就緒、共用型別已是最終形狀，040 行為不變且全綠，可以開始各 story。

---

## Phase 3: User Story 1 - 從團戰績頁產生「團排行榜卡」（Priority: P1）🎯 MVP

**Goal**：會員在「我的團」的團戰績頁按「分享圖卡」，看到排行榜卡預覽（團名、日期、球員人數、前 3 列頒獎台＋第 4～6 列、本人標示「我」、本人不在前 6 列時另附一列），並可下載／分享／複製 1080×1350 的 PNG。此時頁尾仍是 040 現行的品牌字樣頁尾，US2 才換成導流頁尾。

**Independent Test**：任選一個至少有 1 場已完成比賽的團 → 團戰績頁 →「分享圖卡」→ 卡上各列與「頁面排名表濾掉未出賽者後的前 6 列」逐一相同（名次、暱稱、勝負場數、順序）→「下載圖片」得到 1080×1350 PNG（spec US1、quickstart 第 2 節步驟 1～4、8、9）。

### Tests for User Story 1 ⚠️（先寫，確認會失敗）

- [ ] T015 [P] [US1] 新增 `web/app/core/group-share-card/leaderboard-card-model.spec.ts`，逐條涵蓋 contracts/group-share-card.md 的 L1～L10（FR-005～FR-011、FR-021、FR-031、FR-032、SC-003、SC-004、SC-010）：
  - L1：1／2／3／6／7／40 位有出賽球員時 `rows.length` 為 `min(N, 6)`；`rows` 的暱稱序列等於輸入濾掉 0 場後的前綴；另以一份**刻意不照勝場排序**的輸入驗證輸出順序仍與輸入相同（證明沒有排序）；0 場球員夾在有出賽球員之間時被跳過、不影響其後列的相對順序。
  - L2：名次 1、1、3 原樣保留；1、2、3、3、3、3、3（並列跨越第 6 列）取前 6 列且名次原樣。
  - L3：`podium` 只有前 3 列為 true；只有 2 位球員時兩列皆為 true。
  - L4：本人在第 2 列 → `selfRow === null` 且該列 `isSelf`；本人在第 9 列 → `selfRow` 為本人且 `rank` 為其真實名次；本人 0 場 → `selfRow === null`；名單中沒有本人列 → `selfRow === null`。
  - L5：第 7 列以後（非本人）的暱稱不出現在 `JSON.stringify(model)` 中。
  - L6：`JSON.stringify(model)` 不含 `current_status`、`roster_entry_id`、`'left'`、`'kicked'`，也不含任何輸入的 `roster_entry_id` 值。
  - L7：中間夾雜 0 場球員時，`playerCount` 為有出賽的列數。
  - L8：`final_standings` 為空、或全員 0 場 → 回傳 `null`。
  - L9：同樣輸入呼叫兩次，結果深度相等。
  - L10：替代文字——3 列以上用 `altText3`、2 列 `altText2`、1 列 `altText1`；`rank1～3` 參數等於前 3 列的伺服器名次（並列 1、1、3 時為 `1`、`1`、`3`）；`name1～3` 為暱稱；`group` 為團名；不會出現空字串參數。
  - 另驗證：`date` 等於 `context.createdAt`（為 `null` 時為 `null`）；`fileName` 為 `rally-stats-rank-YYYYMMDD-<安全團名>.png`（無日期時為 `nodate`；團名中的 `/ \ : * ? " < > |` 與空白被替換為 `-`，長度上限 40）。
- [ ] T016 [P] [US1] 新增 `web/app/core/group-share-card/leaderboard-card-renderer.spec.ts`，使用 `RecordingContext`、`testFooter()` 與假的 `ShareCardText`（對 `shareCard.dateFormat` 回傳真實格式字串，其餘回傳 `key|JSON(params)`）（FR-006、FR-007、FR-009、FR-010、FR-012、SC-005）：
  - 畫出團名、`groupShareCard.leaderboard.title`、格式化後的日期、`groupShareCard.leaderboard.playerCount`、每一列的名次數字、暱稱與 `groupShareCard.leaderboard.record`。
  - `date === null` 時不畫日期，副標其餘部分照常。
  - 本人列畫出 `groupShareCard.selfTag` **文字**；非本人列沒有。
  - 來賓與 `current_status` 為 `'left'`／`'kicked'` 的球員，暱稱與一般球員一樣照常畫出，沒有任何狀態字樣（FR-011、FR-029）。
  - 名次 ≤ 3 的列各有一個獎牌圓（`recordedArcs`）且圓內有名次數字文字，顏色取自 T019 的獎牌色；名次 > 3 的列沒有獎牌圓。並列 1、2、3、3 時第 4 列（名次 3）也有獎牌圓，但它不是頒獎台列。
  - 有 `selfRow` 時畫出分隔符號與本人列，且本人列的 y 大於第 6 列；沒有時兩者都不畫。
  - 只有 1 位球員時只畫 1 列；`recordedRoundRects` 的數量與實際的列底色、「我」膠囊數量一致（沒有空的名次格）。
  - 20 字暱稱與 40 字團名被截斷並以「…」結尾；所有文字的水平範圍（`RecordingContext.span`）都在左右邊距內；勝負場數欄的 x 不因暱稱長度改變。
  - 最壞情況（6 列＋`selfRow`）：`ctx.bottomEdge({ skipFirst: 1, skipLast: footerOpCount(…) })` ≤ `SHARE_CARD_MIDDLE_BOTTOM`。
  - 最後一次繪製呼叫 `drawPromoFooter`：頁尾的品牌字樣有畫出。
  - 亮色與暗色各跑一次，背景 `fillRect` 的顏色為對應色盤的 `background`。
- [ ] T017 [P] [US1] 新增 `web/app/core/group-share-card/group-share-cards.spec.ts`（US1 段落）：有出賽球員時 `availableGroupCards()` 的第一個選項 `source === 'card-rank'`、`labelKey === 'groupShareCard.kind.leaderboard'`、`fileName`／`altText` 來自排行榜模型；全員 0 場時回傳 `[]`；選項的 `draw` 以 `RecordingContext` 呼叫後會畫出團名（FR-001、FR-005）。
- [ ] T018 [P] [US1] 擴充 `web/app/features/member/my-groups/group-history/group-history.component.spec.ts`（FR-001、FR-002、FR-028、Edge Cases）：
  - 頁面載入成功且有可用圖卡時顯示 `groupShareCard.openButton` 按鈕；載入中、載入錯誤、或 `final_standings` 全員 0 場時**不顯示**。
  - 點擊按鈕後，以 `availableGroupCards()` 的結果呼叫 `ShareCardPreviewComponent.open()`（以替身外殼或 spy 驗證第一個選項 `source === 'card-rank'`）。
  - 初始化時呼叫一次 `FriendsService.getMyGroups()`；成功時選項的檔名含該團 `created_at` 的日期；`getMyGroups()` 失敗、或清單中沒有該團時，頁面**不進入錯誤狀態**、按鈕仍可用、檔名為 `nodate`（research Decision 7）。
  - 在對戰紀錄套用暱稱篩選並換到第 2 頁後，再次開啟時傳給外殼的選項 `fileName` 與 `altText` 與篩選前相同。
  - 開啟再關閉預覽後，對戰紀錄的篩選表單值與目前頁碼維持不變、`getMemberGroupHistory()` 沒有被再次呼叫（FR-002）。

### Implementation for User Story 1

- [ ] T019 [US1] 建立 `web/app/core/group-share-card/group-share-card.models.ts`：依 data-model.md 第 3 節定義 `GroupShareCardContext`、`LeaderboardRow`、`LeaderboardCardModel`（`MyStatsCardModel` 留到 US3）。不得使用 `any`；不得包含 `current_status` 或任何 ID 欄位。同時建立 `web/app/core/group-share-card/group-share-card-palette.ts`（獎牌色是排行榜專用，不放進共用色盤）：`MEDAL_COLORS = { 1: '#FCD34D', 2: '#D1D5DB', 3: '#F4B183' }`、`MEDAL_TEXT = '#111827'`，兩種配色相同；並新增 `group-share-card-palette.spec.ts` 斷言三個獎牌底色與 `MEDAL_TEXT` 的對比皆 ≥ 4.5:1（沿用 `share-card-palette.spec.ts` 的亮度公式）（FR-009、憲章 VII）。
- [ ] T020 [US1] 實作 `web/app/core/group-share-card/leaderboard-card-model.ts`：`buildLeaderboardCardModel(history, context)`，另 export `countPlayers(standings)`（有出賽的列數，US3 共用）。只用 `filter`（`total_matches ≥ 1`）、`slice(0, 6)`、`find(is_self)`——**不得**呼叫 `sort`、不得重新計算或重新編號 `rank`（FR-008、憲章 X）。檔名的安全字元處理與日期格式化寫成本檔的私有小函式。讓 T015 全綠。
- [ ] T021 [US1] 實作 `web/app/core/group-share-card/leaderboard-card-renderer.ts`：`renderLeaderboardCard(ctx, model, env)`，結構為背景 → 標題區（團名 bold 44px 於 y=72；副標「排行榜 · 日期 · N 位球員」30px 於 y=136，日期用 `formatDate(model.date, env.text('shareCard.dateFormat'), 'en-US')`）→ `stackBlocks()` 排中段 → `drawPromoFooter(ctx, env.footer, env)`。中段區塊（contracts/group-share-card.md §2 尺寸表）：頒獎台區塊每列 120（列與列之間不另加間距）、一般列區塊每列 76、本人附列區塊 116（分隔符號「⋯」40＋一列 76）；三個區塊都不給 `minHeight`。獎牌一律用 `arc`＋數字文字繪製、不用 emoji，顏色取自 `MEDAL_COLORS`／`MEDAL_TEXT`；獎牌依 `rank ≤ 3`，頒獎台的大字級與列高依 `podium`；本人列以 `palette.panel` 為列底色，「我」以 `pill`（`palette.badgeBackground`）＋文字（`palette.badgeText`）呈現。讓 T016 全綠。
- [ ] T022 [US1] 實作 `web/app/core/group-share-card/group-share-cards.ts`：`availableGroupCards(history, context): ShareCardOption[]`，本階段只組排行榜選項。讓 T017 全綠。
- [ ] T023 [US1] 接線 `web/app/features/member/my-groups/group-history/group-history.component.{ts,html,scss}`（contracts/group-share-card.md §3）：新增 signal `createdAt`，初始化時訂閱 `friends.getMyGroups()`，以路由的 `groupId` 找出該團的 `created_at`，錯誤時維持 `null` 且不碰 `errorKey`；`shareOptions = computed(…)`；標題列加上原生 `<button type="button">`（`@if (shareOptions().length > 0)`），點擊呼叫 `preview().open(shareOptions())`；範本加入 `<app-share-card-preview>` 並在 `imports` 登記。既有的比賽詳情 dialog 與其 `shareContext` 不動。讓 T018 全綠。
- [ ] T024 [US1] 在 `apps/web` 執行 `npx ng test --watch=false`、`npx ng lint`、`npx ng build` 全部通過；重跑 T014 的 `git diff --stat` 指令，但把最後一個路徑 `…/member/my-groups` 換成 `…/member/my-groups/my-groups.component.ts`，輸出必須為空。Commit：「我的團的團戰績頁可以產生排行榜分享圖卡：前三名頒獎台、第 4–6 名，並標出自己」。

**Checkpoint**：MVP 可以單獨交付——排行榜卡可預覽、下載、分享、複製；頁尾仍為品牌字樣。

---

## Phase 4: User Story 2 - 圖卡頁尾帶網址與 QR 碼（Priority: P1）

**Goal**：所有圖卡（排行榜卡與 040 單場比賽圖卡；US3 的我的成績卡完成後自動套用）的頁尾改為品牌字樣＋標語＋可讀網址＋QR 碼；QR 指向 `<origin>/?ref=<card-rank|card-me|card-match>`。040 圖卡的內容不變，中段只在放不下時依固定規則收縮。

**Independent Test**：產生排行榜卡與 040 單場圖卡並下載 → 頁尾四個元素齊全 → 手機掃描（原尺寸與縮 50%）可開啟首頁且 `ref` 值正確 → 內容全滿的 040 圖卡沒有任何內容被省略或壓到頁尾（spec US2、quickstart 第 2 節步驟 12～14 與第 3 節）。

因為 `PromoFooter` 與 `ShareCardRenderEnv` 在 Phase 2 就是最終形狀，本 phase 不改任何型別；排行榜 renderer 在 T021 已呼叫 `drawPromoFooter(ctx, env.footer, env)`，頁尾改版後自動套用，不需改檔。

### Tests for User Story 2 ⚠️（先寫，確認會失敗）

- [ ] T025 [P] [US2] 新增 `web/app/core/share-card/share-card-qr.spec.ts`（FR-020、research Decision 5）：`qrLayout(33)` → `modulePx 6`；`qrLayout(29)` → `6`；`qrLayout(37)` → `4`；`qrLayout(53)` → `4`；`qrLayout(57)` → `null`；對 21～177 的每個合法尺寸，結果不是 `null` 時 `modulePx` 必為偶數、≥ 4，且 `(size + 4) × modulePx ≤ 240`、`offset` 使 QR 在 240 底板內置中。`toQrMatrix(url, create)`：以假的 `create` 回傳 `{ modules: { size, get } }` 時輸出的 `isDark(r, c)` 與其一致；`create` 拋錯時回傳 `null`；確認傳給 `create` 的選項為 `{ errorCorrectionLevel: 'M' }`；以**真的** `qrcode` 的 `create`（spec 內靜態 import）對同一網址呼叫兩次，矩陣完全相同，且 44 字元網址在等級 M 下 `size === 33`。
- [ ] T026 [P] [US2] 改寫 `web/app/core/share-card/share-card-footer.spec.ts` 為導流頁尾（contracts/share-card-core.md §5 版面表）（FR-018、FR-020、SC-005）：
  - 有 `qr` 時：畫出一個 240×240、左上角 (768, 1054) 的底板，`recordedRoundRects` 中該筆的 `color` 為 `#ffffff`（亮暗兩種色盤皆同）；深色模組的 `fillRect` 數量等於矩陣中深色模組數，每個寬高等於 `modulePx`、顏色為 `#111827`（兩種色盤相同），座標全部落在底板內。
  - 左側依序畫出 `meta`（有值時）、`shareCard.brand`、`shareCard.tagline`、`link.displayUrl`、`shareCard.scanHint`，y 依 contracts §5 的行高表往下排、省略的行不佔空間；所有左側文字的右緣 ≤ 744（底板左緣 − 24）。
  - 200 字元的標語與 80 字元的 `displayUrl` 被截斷且右緣仍 ≤ 744。
  - `qr === null`：不畫底板與任何模組、不畫 `scanHint`，仍畫品牌、標語與 `displayUrl`，且文字可用寬度擴到 936（整個內容寬）。
  - `qrLayout()` 回傳 `null` 的超大矩陣：行為同 `qr === null`。
  - 頁尾所有繪製的 top ≥ 1026（分隔線），bottom ≤ 1294（1350 − 56）。
- [ ] T027 [P] [US2] 擴充 `web/app/core/share-card/share-card-actions.service.spec.ts`（FR-019、FR-020）：`rasterize()` 交給 `option.draw` 的 `env.footer.qr` 在載入函式成功時為非 `null` 的矩陣；以 `SHARE_CARD_QR_LOADER`（InjectionToken）提供會拋錯或回傳 rejected promise 的替身時，`rasterize()` **仍回傳 Blob** 且 `env.footer.qr === null`（contracts/share-card-core.md §3 不變式）；`env.footer.link.qrUrl` 的 `ref` 等於 `option.source`。
- [ ] T028 [P] [US2] 擴充 `web/app/core/match-share-card/share-card-renderer.spec.ts`（FR-022 允許的範圍、SC-007）：頁尾斷言改為「時長與每分耗時出現在頁尾的 `meta` 行、`shareCard.brand`／`tagline` 有畫出」；新增以下案例，每一例都斷言兩隊所有暱稱、雙方比分、徽章、走勢折線、亮點文字**全部都有畫**，且 `bottomEdge({ skipFirst: 1, skipLast: footerOpCount(…) })` ≤ `SHARE_CARD_MIDDLE_BOTTOM`：
  - 內容全滿（雙打、我方視角有徽章、走勢圖、3 個亮點）：走勢 140、亮點列高 53（research Decision 6 實算表）。
  - 單打全滿（走勢圖＋3 個亮點）：走勢 146、亮點列高 60。
  - 雙打＋走勢圖＋2 個亮點：走勢 180。
  - 雙打＋走勢圖＋1 個亮點：間距 32、所有區塊高度不變（走勢 240）。
  - 只有隊伍區塊、隊伍＋走勢、隊伍＋3 個亮點（無走勢）：間距維持 48、沒有任何收縮、整組垂直置中。
- [ ] T029 [P] [US2] 擴充 `web/app/core/group-share-card/leaderboard-card-renderer.spec.ts`：頁尾改版後，最壞情況（6 列＋`selfRow`）仍不超出新的 `SHARE_CARD_MIDDLE_BOTTOM`，且三個區塊高度不變（只有間距可能縮小）；頁尾畫出 `displayUrl`（FR-018）。

### Implementation for User Story 2

- [ ] T030 [P] [US2] 實作 `web/app/core/share-card/share-card-qr.ts`：`QrCreate` 型別（只描述用到的 `create(text, options) => { modules: { size; get(row, col) } }`，不把 `qrcode` 的型別外洩到模組外）、`toQrMatrix()`、`qrLayout()`、常數 `QR_PLATE_SIZE = 240`。讓 T025 全綠。
- [ ] T031 [US2] 改寫 `web/app/core/share-card/share-card-footer.ts` 的 `drawPromoFooter()` 為導流頁尾（contracts/share-card-core.md §5 版面表）；同時把 `web/app/core/share-card/share-card-layout.ts` 的常數改為「版面常數」表 US2 欄的值（`SHARE_CARD_MIDDLE_TOP = 210`、`SHARE_CARD_MIDDLE_BOTTOM = 996`、`SHARE_CARD_FOOTER_TOP = 1054`），並在檔內以註解寫出算式（research Decision 6）；兩種色盤在 `web/app/core/share-card/share-card-palette.ts` 新增 `qrPlate: '#ffffff'`、`qrModule: '#111827'`。讓 T026、T029 全綠。
- [ ] T032 [US2] 修改 `web/app/core/share-card/share-card-actions.service.ts` 的 `rasterize()`：新增 `SHARE_CARD_QR_LOADER` InjectionToken（預設 `() => import('qrcode').then((m) => m.create ?? m.default.create)`）；`buildShareCardLink(window.location, option.source)` → 以 loader 取得 `create` → `toQrMatrix(link.qrUrl, create)`，任何例外都降為 `qr = null` → `env.footer = { link, qr, meta: null }`。執行 `npx ng build`；若出現 `qrcode` 的 CommonJS 相依警告，在 `apps/web/angular.json` 的 build options 加入 `"allowedCommonJsDependencies": ["qrcode"]`，build 必須零警告。讓 T027 全綠。
- [ ] T033 [US2] 修改 `web/app/core/match-share-card/share-card-renderer.ts`（FR-022、research Decision 6）：走勢區塊給 `minHeight: 140` 並依 `draw(y, height)` 收到的高度繪製；亮點區塊的 `minHeight` 為 `列數 × 52 + 48`（現行高度 `列數 × 60 + 48`，48 為上下內距），`draw` 依實際高度以 `Math.floor((height − 48) / 列數)` 換算列高；**隊伍區塊不給 `minHeight`、永不收縮**。**不得**修改 `share-card-model.ts`、`share-card-highlights.ts` 及其 spec。讓 T028 全綠。
- [ ] T034 [P] [US2] 更新 `specs/040-match-share-card/spec.md`：在 FR-006、US1 驗收情境 5 與 Assumptions「品牌字樣即足夠」三處各加一行註記「已由 041-group-share-cards FR-018 取代：圖卡頁尾現含網址與 QR 碼」，不改動原文。
- [ ] T035 [US2] 在 `apps/web` 執行 `npx ng test --watch=false`、`npx ng lint`、`npx ng build` 全部通過；重跑 T024 的 `git diff --stat` 指令，輸出必須為空。Commit：「所有分享圖卡的頁尾加上標語、網址與 QR 碼，掃描即可進入系統首頁」。

**Checkpoint**：US1＋US2 可以一起交付——圖卡有了導流能力；040 單場圖卡同步升級。

---

## Phase 5: User Story 3 - 「我的本團成績卡」與圖卡種類切換（Priority: P2）

**Goal**：有出賽的會員在同一個預覽中可切換到「我的成績」：大字勝率、勝負與總場數、團內名次、各輪勝率走勢縮圖（≥ 2 輪）、最常交手的前 3 位對手；切換種類時保留配色。

**Independent Test**：以有出賽的會員開啟預覽 → 切到「我的成績」→ 數字與頁面「我的戰績」區塊及排名表本人列一致、走勢形狀與頁面一致（同為 0～100% 固定縱軸）、對手為頁面清單前 3 位且順序相同 → 先切暗色再切種類，配色維持暗色（spec US3、quickstart 第 2 節步驟 5～8）。

### Tests for User Story 3 ⚠️（先寫，確認會失敗）

- [ ] T036 [P] [US3] 新增 `web/app/core/group-share-card/my-stats-card-model.spec.ts`，逐條涵蓋 contracts/group-share-card.md 的 M1～M6（FR-013～FR-017、FR-021、FR-031、FR-032、SC-003、SC-010）：
  - M1：`my_stats.total_matches === 0` → `null`。
  - M2：`winRate` 等於 `formatPercent(win_rate)`，以 0、0.6、0.666…、1 各驗一次。
  - M3：`standing` 為本人列的 `rank` 與 `countPlayers()`；沒有本人列 → `standing === null` 且 `nickname === null`。
  - M4（FR-015）：0 或 1 輪 → `trend === null`；3 輪、勝率 0.5／1／0 → 3 個點，`x` 為 0／50／100，`y` 為 `(1 − win_rate) × 100` 即 50／0／100（固定 0～100% 縱軸，與頁面的 `round-trend-chart` 相同）；各輪勝率全部 0.6 時所有點的 `y` 都是 40。
  - M5：0 筆 → `[]`；1 筆 → 1 筆；5 筆 → 前 3 筆且順序與輸入相同；另以**刻意不照場數排序**的輸入驗證沒有重新排序；每筆只有 `nickname`、`wins`、`losses`。
  - M6：`createdAt === null` → `date === null`。
  - 另驗證 `fileName` 為 `rally-stats-me-…png`、`altText.key === 'groupShareCard.myStats.altText'` 且參數齊全、同樣輸入兩次深度相等、`JSON.stringify(model)` 不含任何 ID。
- [ ] T037 [P] [US3] 新增 `web/app/core/group-share-card/my-stats-card-renderer.spec.ts`（FR-014～FR-018、SC-005）：
  - 畫出團名、`groupShareCard.myStats.title`、日期、暱稱、大字勝率字串（字級為全卡最大）、`groupShareCard.myStats.record`、`groupShareCard.myStats.standing`、`groupShareCard.myStats.trendTitle` 與 1 條折線、`groupShareCard.myStats.opponentsTitle` 與每位對手的暱稱及 `opponentRecord`。
  - `standing`／`trend`／`opponents`／`nickname`／`date` 各自缺漏時對應元素完全不畫、且沒有多出的 `recordedRoundRects`（無空框，FR-017）。
  - 20 字暱稱（本人與對手）被截斷不超界。
  - 最壞情況（全部區塊都有、3 位對手）：依 contracts/group-share-card.md §2 的尺寸表，走勢區塊被收縮（高度 < 220 且 ≥ 140），且 `bottomEdge({ skipFirst: 1, skipLast: footerOpCount(…) })` ≤ `SHARE_CARD_MIDDLE_BOTTOM`；只有 1 位對手時走勢不被收縮。
  - 頁尾畫出 `shareCard.brand` 與 `displayUrl`（FR-018）。
  - 亮暗兩種色盤。
- [ ] T038 [P] [US3] 擴充 `web/app/core/group-share-card/group-share-cards.spec.ts`：本人有出賽 → 兩個選項、順序固定為 `card-rank`、`card-me`；本人 0 場 → 只有 `card-rank`；全員 0 場 → `[]`（FR-003、FR-013）。
- [ ] T039 [P] [US3] 擴充 `web/app/core/share-card/share-card-preview/share-card-preview.component.spec.ts`（contracts/share-card-core.md §2、FR-003、FR-004）：1 個選項時不渲染種類切換；2 個選項時渲染 2 顆原生 `<button>`、文字為各自 `labelKey` 的翻譯、`aria-pressed` 反映選取狀態、外層 `role="group"` 且有 `shareCard.kindLabel` 的標籤；點第二顆 → 以第二個選項重新 `rasterize`、`alt` 與下載檔名換成第二個選項；先選暗色再切種類 → `rasterize` 收到的 theme 仍為 `'dark'`；點已選取的那顆不重新產圖；重新 `open()` 後回到第一個選項與亮色；切換途中較舊的產圖結果被丟棄。
- [ ] T040 [P] [US3] 擴充 `web/app/features/member/my-groups/group-history/group-history.component.spec.ts`：本人有出賽時傳給外殼 2 個選項；本人 0 場但團內有比賽時 1 個。

### Implementation for User Story 3

- [ ] T041 [US3] 在 `web/app/core/group-share-card/group-share-card.models.ts` 加入 `MyStatsCardModel`（data-model.md 第 3 節），並實作 `web/app/core/group-share-card/my-stats-card-model.ts`：`buildMyStatsCardModel(history, context)`。`playerCount` 使用 T020 export 的 `countPlayers()`，不得另寫一份；走勢 `y = (1 − win_rate) × 100`；對手只用 `slice(0, 3)`，**不得**排序或挑選（FR-016）。讓 T036 全綠。
- [ ] T042 [US3] 實作 `web/app/core/group-share-card/my-stats-card-renderer.ts`：`renderMyStatsCard(ctx, model, env)`，背景 → 標題區（同排行榜卡）→ `stackBlocks()` → `drawPromoFooter(ctx, env.footer, env)`。中段區塊與尺寸依 contracts/group-share-card.md §2：主視覺 232（暱稱 40px 行高 52、勝率 `env.fonts.score` 140px 行高 150、勝負總場數 30px 行高 30）、名次膠囊 56、走勢 `height 220`／`minHeight 140`（含 30px 小標，單一折線用 `palette.trendA`，縱軸固定 0～100%）、對手區塊 `40 + 列數 × 56`。缺漏的區塊不進入 `stackBlocks()`。讓 T037 全綠。
- [ ] T043 [US3] 擴充 `web/app/core/group-share-card/group-share-cards.ts`：加入我的成績選項（`source: 'card-me'`、`labelKey: 'groupShareCard.kind.myStats'`）。讓 T038、T040 全綠（`group-history` 元件本身不需再改，因為它只轉交 `availableGroupCards()` 的結果）。
- [ ] T044 [US3] 在 `web/app/core/share-card/share-card-preview/share-card-preview.component.{ts,html,scss}` 加上種類切換：`@if (options().length > 1)` 渲染 `role="group"`＋`aria-label` 的按鈕列，樣式比照既有的配色切換；`selectOption(option)` 在選項不同且狀態非 `idle` 時更新 `selected` 並重新 `generate()`，**不重設** `theme`；`open()` 重設為第一個選項與亮色。讓 T039 全綠。
- [ ] T045 [US3] 在 `apps/web` 執行 `npx ng test --watch=false`、`npx ng lint`、`npx ng build` 全部通過；重跑 T024 的 `git diff --stat` 指令，輸出必須為空。Commit：「分享圖卡新增「我的成績」：勝率、名次、各輪走勢與最常交手的對手，可在預覽中切換圖卡種類」。

**Checkpoint**：兩種團圖卡都可用，並且都帶導流頁尾。

---

## Phase 6: User Story 4 - 掃 QR 進來的人看得懂、知道怎麼開始（Priority: P2）

**Goal**：首頁從一行標題擴充為最小可用的介紹頁：系統名稱、與圖卡頁尾相同的標語、3 項功能重點、行動按鈕；帶 `ref` 參數時畫面完全相同。

**Independent Test**：未登入開啟 `/`、`/?ref=card-rank`、`/?ref=<script>` → 畫面相同、無錯誤、參數未被顯示 → 按鈕進入註冊／登入；已登入時主要按鈕進入 `/member`；360px 寬不需捲動即可看到標語與主要按鈕（spec US4、quickstart 第 5 節）。

### Tests for User Story 4 ⚠️（先寫，確認會失敗）

- [ ] T046 [US4] 擴充 `web/app/features/home/home.component.spec.ts`（contracts/landing-link.md §2、FR-024～FR-026、FR-030）：
  - 渲染 `home.title`、`shareCard.tagline`（與圖卡頁尾**同一個 key**）、3 個功能重點（各有標題與內文）。
  - `AuthService.loggedIn()` 為 false：主要連結的 `href` 為 `/auth/register`、文字 `home.cta.start`；次要連結為 `/auth/login`、文字 `home.cta.login`；沒有 `/member` 連結。
  - 為 true：主要連結為 `/member`、文字 `home.cta.member`；沒有註冊／登入連結；Router 的 `navigate`／`navigateByUrl` **沒有**被呼叫（不自動轉址，FR-026）。
  - 以 `RouterTestingHarness` 分別導覽到 `/`、`/?ref=card-rank`、`/?ref=%3Cscript%3E`、`/?foo=bar`：四次渲染出的 `textContent` 完全相同，且不含 `card-rank` 或 `script` 字樣（FR-025）。
  - 兩份語系檔的 `home` 命名空間 key 集合完全相同、每個值非空。
  - 切換語言為 `en` 後文字隨之更新。

### Implementation for User Story 4

- [ ] T047 [US4] 實作 `web/app/features/home/home.component.{ts,html,scss}`：注入 `AuthService` 讀取 `loggedIn` signal；範本為 `<main>` 內的標題、標語、`<ul>` 功能重點（沿用既有的 `app-icon`，若無合適圖示則只用文字）、行動按鈕以 `<a routerLink>` 呈現並套用既有的按鈕樣式類別；**不注入 `ActivatedRoute`、不讀取 query string**。樣式以行動裝置優先：360×640 視窗下標題、標語、主要按鈕在第一屏內（功能重點可在下方），使用既有的設計 token，不新增顏色。讓 T046 全綠。
- [ ] T048 [US4] 在 `apps/web` 執行 `npx ng test --watch=false`、`npx ng lint`、`npx ng build` 全部通過；以 `grep -n "ActivatedRoute\|queryParam" apps/web/src/app/features/home/home.component.ts` 確認沒有結果。Commit：「首頁加上系統介紹與開始使用的按鈕，掃圖卡 QR 碼進來的人知道這是什麼」。

**Checkpoint**：四個 story 全部完成，導流路徑從圖卡到首頁完整接通。

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T049 依 quickstart.md 第 2 節做實際畫面驗收（worktree 前後端 :8001／:4300、`seed_dashboard_demo` 示範資料、先補 `is_creator` 的 `UPDATE`；驗收在跑任何會清空測試 DB 的 pytest 之前進行）。**先以 SQL 準備 SC-003 的 8 種狀況**：在示範團中製造並列名次、1 位 0 場球員夾在排名中間、1 位 `current_status = 'left'` 的球員、1 位未綁定會員的來賓；另建 1／2／3 人的小團各一。步驟 1～14 逐項確認，特別是步驟 3（本人不在前 6 名時的附列）、步驟 10（20 字暱稱／40 字團名）、步驟 13（內容全滿的 040 圖卡）。發現的視覺問題直接修正並補對應的 renderer 斷言（SC-003、SC-004、SC-005、SC-007）。
- [ ] T050 [P] QR 驗收（quickstart.md 第 3 節、SC-006）：下載三種圖卡 × 兩種配色共 6 張；先以腳本回歸——用 `qrcode` 與任一解碼器對「原尺寸」與「縮 50%」各解一次，確認解得的網址與 `ref` 值正確（腳本放在 job 暫存目錄，不進 repo）；再以真機（iOS 相機、Android 相機、LINE 掃描器、LINE 聊天室長按辨識）各掃一輪。無法取得的裝置要在實作備註中明列為未驗證。
- [ ] T051 [P] 量測 SC-001：390×844 視窗、CPU 降速 4 倍，記錄「點分享圖卡 → 預覽出現」（含第一次動態載入 `qrcode`）與「切換種類／配色 → 新圖出現」的中位數，分別 ≤ 2 秒與 ≤ 1 秒；同時計算從團戰績頁到分享或下載完成的點擊數 ≤ 3（SC-002）；結果寫入實作備註。
- [ ] T052 [P] 系統分享驗收（quickstart.md 第 4 節）：桌機 Chrome 的「複製圖片」與「下載」實測；手機系統分享需要 HTTPS，無法在本機驗證時於實作備註明列，並確認 T012 的「只有 `files` 一個鍵」斷言存在且通過（FR-023）。
- [ ] T053 [P] 首頁驗收（quickstart.md 第 5 節步驟 1～5，含 360×640 視窗截圖）；步驟 6（5 位新使用者的 10 秒測試，SC-008）需要真人，列為交付後由需求方執行。語言切換驗收（SC-009）：切換為 English 後重開三種圖卡與首頁，確認沒有殘留中文固定文字。
- [ ] T054 最終檢查：`npx ng test --watch=false`、`npx ng lint`、`npx ng build` 全部通過且 build 零警告；重跑 T024 的 `git diff --stat` 指令（040 保護線、後端）輸出為空；`grep -rn "sort(" apps/web/src/app/core/group-share-card --include=*.ts` 除 spec 外沒有結果（FR-008）；`grep -rn "current_status\|roster_entry_id" apps/web/src/app/core/group-share-card --include=*.ts` 除 fixtures 與 spec 外沒有結果（FR-011、FR-021）；`grep -rln "HttpClient\|ApiClient\|localStorage" apps/web/src/app/core/share-card apps/web/src/app/core/group-share-card` 沒有結果（圖卡不上傳、不儲存、不發請求，FR-027、FR-028、FR-033）。
- [ ] T055 在本檔最後補上「實作備註」區段（比照 040）：順序調整、偏離 contracts 之處與原因、實際畫面驗收額外修正的項目、未能在本機驗證的項目、SC-001／SC-002 量測值；驗收腳本與截圖複製到主 checkout 的 `docs/041-group-share-cards-check/`（僅存在本機、不進 git）。Commit：「041 任務全部完成，補上實作備註與驗收結果」。

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup（Phase 1）**：無依賴。T001～T004 可平行。
- **Foundational（Phase 2）**：依賴 Phase 1（T009、T012 需要 T002 的 `shareCard.*` key）。**阻擋所有 story。**
- **US1（Phase 3）**：依賴 Phase 2。
- **US2（Phase 4）**：依賴 Phase 2；T029 依賴 US1 的 T016／T021（排行榜 renderer 已存在）。若先做 US2 再做 US1，把 T029 移到 US1 之後即可。
- **US3（Phase 5）**：依賴 Phase 2 與 US1（`group-share-cards.ts`、`group-history` 接線、`countPlayers()`）；建議在 US2 之後，renderer 直接使用新的中段範圍。
- **US4（Phase 6）**：只依賴 Phase 1 的 T002（`shareCard.tagline`、`home.*`）；可與 US1～US3 平行。
- **Polish（Phase 7）**：依賴所有 story。

### User Story Dependencies

| Story | 依賴 | 可否單獨交付 |
|---|---|---|
| US1 排行榜卡 | Foundational | ✅ MVP（頁尾為品牌字樣） |
| US2 導流頁尾 | Foundational（T029 需 US1） | ✅ 即使沒有 US1，也會升級 040 單場圖卡 |
| US3 我的成績卡＋切換 | US1 | ✅ 在 US1 之上 |
| US4 首頁 | T002 | ✅ 完全獨立 |

### Within Each User Story

- 測試任務先完成並確認失敗，才開始該 story 的實作任務。
- 純函式（model）→ renderer → 選項組裝 → 頁面接線。
- 每個 story 最後一個任務是「全套測試＋lint＋build＋040 保護線檢查」後 commit。

### Parallel Opportunities

- Phase 1：T001～T004。
- Phase 2：T006 與 T010 可與 T005 之後的其他任務平行。T007→T008→T009→T011 都會碰 `share-card-renderer.ts` 或其產物，須依序；T012 在 T011 之後；T013 在 T012 之後（刪除的 key 在 T012 完成前仍被舊 dialog 範本使用）。
- US1：T015～T018 四個測試檔互不相干；T020、T021 在 T019 之後可平行（不同檔）。
- US2：T025～T029 五個測試任務可平行；T030 與 T034 隨時可做；T031→T032→T033 依序。
- US3：T036～T040 可平行；T041 與 T044 可平行（不同模組）。
- US4 整個 phase 可與 US1～US3 平行。
- Polish：T050～T053 可平行。

---

## Parallel Example: User Story 1

```bash
# 四個測試檔一起寫（互不相干）：
Task: "T015 leaderboard-card-model.spec.ts（L1～L10）"
Task: "T016 leaderboard-card-renderer.spec.ts"
Task: "T017 group-share-cards.spec.ts（US1 段落）"
Task: "T018 group-history.component.spec.ts 擴充"

# T019 型別與獎牌色完成後：
Task: "T020 leaderboard-card-model.ts"
Task: "T021 leaderboard-card-renderer.ts"
```

## Parallel Example: User Story 2

```bash
# 五個測試任務一起寫：
Task: "T025 share-card-qr.spec.ts"
Task: "T026 share-card-footer.spec.ts 改寫"
Task: "T027 share-card-actions.service.spec.ts 擴充"
Task: "T028 share-card-renderer.spec.ts（040 各種滿版情境）"
Task: "T029 leaderboard-card-renderer.spec.ts 擴充"

# 隨時可做：
Task: "T030 share-card-qr.ts"
Task: "T034 040 spec 加註"
```

---

## Implementation Strategy

### MVP First（只做 User Story 1）

1. Phase 1 → Phase 2（確認 040 行為不變且全綠）。
2. Phase 3（US1）。
3. **停下來驗證**：團戰績頁可產生、下載排行榜卡，內容與頁面排名表一致。此時已可交付，只是圖卡還沒有導流能力。

### Incremental Delivery

1. Setup＋Foundational → 共用層就緒（使用者無感）。
2. ＋US1 → 排行榜卡（MVP）。
3. ＋US2 → 所有圖卡有 QR／網址（本功能的宣傳目的自此成立；建議 US1、US2 一起上線）。
4. ＋US4 → 首頁接得住掃進來的人（建議與 US2 同一批上線，否則 QR 指向的仍是一行標題）。
5. ＋US3 → 我的成績卡與種類切換。
6. Polish → 實際畫面、QR、效能驗收與實作備註。

---

## Notes

- [P] 任務 = 不同檔案、沒有未完成的依賴。
- [Story] 標籤用來追溯到 spec 的 user story。
- **後端零變動**；不新增 migration、端點或環境變數。唯一的相依變動是 T001（`qrcode` 由間接改為直接相依、加 `@types/qrcode`）。
- **040 保護線**：見 Phase 2 開頭的清單；T014、T024、T035、T045、T054 以同一個 `git diff --stat origin/ut...HEAD` 指令驗證（T024 之後排除 `group-history`，因為 US1 會在該處新增程式）。
- **憲章 X 的保護線**：`core/group-share-card/` 內不得出現 `sort`、不得重算 `rank`、不得從對手戰績另行挑選；T015／T036 的「刻意不照順序的輸入」與 T054 的 grep 共同把關。
- 所有顯示文字只能使用 T002 建立的 key；實作過程中若需要新增 key，兩份語系檔要同時補上，T003 的一致性測試會擋下漏加的情況。
- 系統分享只送圖片檔（research Decision 8）；任何人想加上 `text`／`url`，會被 T012 的「只有 `files` 一個鍵」斷言擋下，需先完成真機驗證並修訂 spec FR-023。
- 每完成一個 phase（Foundational 與各 story）就 commit 一次，commit 訊息使用繁體中文，並描述使用者看得到的變化；結尾附上 session 指定的 `Co-Authored-By` 行。
- 2026-09-21 `/speckit-analyze` 後修訂：依分析報告重排 Phase 2（共用型別一次定案、分享動作／預覽外殼／040 門面合併為 T012、語系 key 刪除移到 T013 且不可平行）、修正測試工具（`bottomEdge` 排除背景與頁尾）、改用固定 0～100% 的走勢縱軸（刪除原 T015 的縱軸函式抽取）、040 隊伍區塊不收縮、補齊尺寸與顏色定值、替代文字帶名次、FR-002／SC-002／SC-003／SC-009 補上驗證任務。任務數由 60 調整為 55。
