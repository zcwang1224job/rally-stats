---

description: "Task list for 041-group-share-cards"
---

# Tasks: 團分享圖卡與導流頁尾（Group Share Cards）

**Input**: Design documents from `/specs/041-group-share-cards/`

**Prerequisites**: plan.md、spec.md、research.md、data-model.md、contracts/（`share-card-core.md`、`group-share-card.md`、`landing-link.md`）、quickstart.md

**Tests**: **必做**。Constitution II 要求核心規則的測試先於實作撰寫，plan.md 的 Testing 段也列了每個 spec 檔。每個 story 的測試任務 MUST 先完成，並確認它會失敗，才開始該 story 的實作任務。唯一的例外是 Phase 2 的「搬移」任務：那是行為不變的重構，保證來自既有 spec 不改動而維持全綠。

**Organization**: 依 spec.md 的 user story 分 phase。本功能**只改 `apps/web`**，後端零變動。Phase 2 把 040 的共用部分抽成 `core/share-card/`，完成且全綠後才進任何 story。US1（排行榜卡）是 MVP。

## Format: `[ID] [P?] [Story] Description`

- **[P]**：可平行執行（不同檔案、不依賴尚未完成的任務）
- **[Story]**：對應 spec.md 的 user story（US1～US4）
- 路徑皆為 repo 相對路徑；前端簡寫 `web/` = `apps/web/src/`

## 環境備註（worktree）

- 前端：`ln -s /Users/zcwang/projects/rally-stats/apps/web/node_modules apps/web/node_modules`，在 `apps/web` 執行 `npx ng test --watch=false`、`npx ng lint`、`npx ng build`。
- T001 會新增 devDependency `@types/qrcode`：worktree 的 `node_modules` 是指向主 checkout 的 symlink，所以 `npm install` 要在**主 checkout 的 `apps/web`** 以更新後的 `package.json`／`package-lock.json` 執行一次（`qrcode@1.5.4` 本體已經在 `node_modules` 裡）。
- 後端不需要跑測試；以 `git diff --stat origin/ut -- apps/api` 為空作為「後端零變動」的證據。
- `ng test` 既有的 1 個 unhandled error（`NG04002 … 'groups/reauth'`，來自 `admin-page.component.spec.ts`）與本功能無關。
- 共用術語：**有出賽** = `total_matches ≥ 1`；**本人列** = `final_standings` 中 `is_self === true` 的那一列；**中段** = 標題區與頁尾之間、由 `stackBlocks()` 排版的範圍。

---

## Phase 1: Setup（共用基礎）

**Purpose**：相依宣告、全部語系文字與測試 fixtures 一次到位，後續各 story 不必同時改同一批檔案。

- [ ] T001 在 `apps/web/package.json` 的 `dependencies` 加入 `"qrcode": "1.5.4"`（與 `angularx-qrcode@20.0.0` 鎖定的版本完全相同，research Decision 4），`devDependencies` 加入 `"@types/qrcode": "^1.5.5"`；在主 checkout 的 `apps/web` 執行 `npm install` 更新 `package-lock.json`，確認 lockfile 中 `node_modules/qrcode` 仍只有一份 1.5.4。
- [ ] T002 [P] 在 `web/assets/i18n/zh-TW.json` 與 `web/assets/i18n/en.json` **新增**三個命名空間（此時先不刪任何既有 key）：
  - `shareCard.*`：contracts/share-card-core.md §8 列出的全部 key。`brand`＝「Rally Stats」；`tagline`＝zh「計分・排點・戰績，打球一站搞定」／en「Score, schedule and track every game.」；`scanHint`＝zh「掃描 QR 碼開始使用」／en「Scan to get started」；`kindLabel`＝zh「圖卡種類」／en「Card type」；其餘（`previewTitle`、`themeLabel`、`themeLight`、`themeDark`、`share`、`copy`、`copied`、`download`、`close`、`generating`、`generateError`、`shareError`、`copyError`、`dateFormat`）**逐字複製**目前 `matchShareCard.*` 的同名值。
  - `groupShareCard.*`：contracts/group-share-card.md §4 列出的全部 key。zh 文案：`openButton`「分享圖卡」、`kind.leaderboard`「排行榜」、`kind.myStats`「我的成績」、`leaderboard.title`「排行榜」（**不得**含「最終」，FR-012）、`leaderboard.playerCount`「{count} 位球員」、`leaderboard.record`「{wins} 勝 {losses} 敗」、`selfTag`「我」、`myStats.title`「我的成績」、`myStats.record`「{wins} 勝 {losses} 敗・共 {matches} 場」、`myStats.standing`「第 {rank} 名／共 {count} 人」、`myStats.trendTitle`「各輪勝率」、`myStats.opponentsTitle`「最常交手」、`myStats.opponentRecord`「{wins} 勝 {losses} 敗」、`leaderboard.altText`（參數 `group`、`first`、`second`、`third`；人數不足時對應參數為空字串）、`myStats.altText`（參數 `group`、`winRate`、`wins`、`losses`）。en 對應翻譯，`selfTag`＝「YOU」。
  - `home.*`：保留既有 `home.title`，新增 `home.features.scoring.title／body`、`home.features.rotation.title／body`、`home.features.stats.title／body`、`home.cta.start`（zh「開始使用」）、`home.cta.login`（zh「登入」）、`home.cta.member`（zh「進入我的頁面」）。功能重點以使用者利益描述（FR-024），例如計分：「手機就是計分板，比分即時同步給全場」。
  - 同時新增 `web/app/core/group-share-card/group-share-card-i18n.spec.ts`：比照 `web/app/core/match-share-card/share-card-i18n.spec.ts` 的做法 import 兩份 JSON，斷言 `shareCard`、`groupShareCard`、`home` 三個命名空間在兩邊的 key 集合完全相同、每個值都是非空字串，且 zh 的 `groupShareCard.leaderboard.title` 不含「最終」、en 不含「final」（不分大小寫）。
- [ ] T003 [P] 建立測試輔助檔 `web/app/core/group-share-card/testing/history-fixtures.ts`：`makeStanding(overrides)` 產生合法的 `FinalStandingRow`（預設 `current_status: 'active'`、`is_self: false`、有出賽）；`makeStandings(count, options?)` 產生依名次排好的 N 列（支援指定第幾列為本人、哪些列並列、哪些列 0 場、哪些列為 `'left'`／`'kicked'`）；`makeHistory(overrides)` 產生合法的 `MemberGroupHistoryResponse`（預設 `group_name: '週三羽球團'`、8 位有出賽球員、本人為第 2 列、`my_stats` 為 6 勝 4 敗 `win_rate: 0.6`、3 輪 `round_win_rates`、4 筆已依場數排序的 `opponent_records`、`matches: []`）。不得使用 `any`。

---

## Phase 2: Foundational（阻擋所有 story 的前置工作）

**Purpose**：把 040 模組中與「比賽」無關的部分抽成 `core/share-card/`（research Decision 1、2），並抽出走勢圖的縱軸範圍純函式（Decision 11）。**這個 phase 對使用者沒有任何可見變化**：040 圖卡的畫面、檔名、按鈕行為都必須與現在完全相同。

**⚠️ CRITICAL**：這個 phase 完成且全綠之前，不得開始任何 story。整個 phase 期間，`web/app/core/match-share-card/share-card-model.ts`、`share-card-model.spec.ts`、`share-card-highlights.ts`、`share-card-highlights.spec.ts`、`testing/detail-fixtures.ts` **一行都不得修改**。

- [ ] T004 建立 `web/app/core/share-card/share-card-canvas.ts`：從 `web/app/core/match-share-card/share-card.models.ts` 搬入 `ShareCardCanvas`、`ShareCardText`、`ShareCardFonts`、`TranslatedText`、`ShareTheme`、`SharePalette`；從 `share-card-renderer.ts` 搬入 `SHARE_CARD_WIDTH`、`SHARE_CARD_HEIGHT`、`SHARE_CARD_PADDING`。`share-card.models.ts` 改為 `export type { … } from '../share-card/share-card-canvas'`，`share-card-renderer.ts` 改為 re-export 三個常數，使所有既有匯入路徑不必改。共用層**不得** import `match-share-card/`（contracts/share-card-core.md 開頭的依賴規則）。
- [ ] T005 [P] 把 `web/app/core/match-share-card/share-card-palette.ts` 與 `share-card-palette.spec.ts` 以 `git mv` 搬到 `web/app/core/share-card/`，只改 import 路徑；在舊位置留一個 `export { SHARE_PALETTES } from '../share-card/share-card-palette'` 的轉出檔，避免動到 040 其他檔案。
- [ ] T006 [P] 把 `web/app/core/match-share-card/testing/recording-context.ts` 以 `git mv` 搬到 `web/app/core/share-card/testing/recording-context.ts`，並新增方法 `bottomEdge(): number`——回傳所有已記錄繪製的最大下緣：文字取 `y + fontSize`（`textBaseline` 為 `'top'`），`recordedRects` 與 `recordedRoundRects` 取 `y + h`，`recordedArcs` 取 `y + radius`；可傳入 `{ above: number }` 只統計 `y < above` 的項目（用來排除頁尾）。更新 `share-card-renderer.spec.ts` 的 import 路徑（這是該檔在本 phase 唯一允許的變更）。
- [ ] T007 先寫 `web/app/core/share-card/share-card-drawing.spec.ts`：`truncateToWidth` 在放得下時原樣回傳、放不下時回傳最長前綴加「…」且量測寬度 ≤ 上限、對含 emoji／代理對的字串不會切在中間、上限小於「…」本身時回傳「…」。接著建立 `web/app/core/share-card/share-card-drawing.ts`，把 `share-card-renderer.ts` 的 `truncateToWidth`、`panel`、`pill`、`roundedFill` **原封不動**搬入並 export；renderer 改為 import，並保留 `export { truncateToWidth }` 供既有 spec 使用。
- [ ] T008 先寫 `web/app/core/share-card/share-card-layout.spec.ts`（contracts/share-card-core.md §6、data-model.md「Block 與排版」），以會記錄 `draw(y, height)` 引數的假 Block 驗證：
  - 放得下：不收縮；整組在 `top`～`bottom` 間垂直置中；相鄰區塊間距等於 `gap`；每個 Block 收到的 `height` 等於自己的 `height`。
  - 放不下：先把間距降到 `minGap`，若已足夠則所有 Block 高度不變。
  - 仍不足：由上而下依序收縮有 `minHeight` 的 Block，只收縮到「剛好放下」為止（第一個可收縮 Block 吃完額度後才輪到下一個）；沒有 `minHeight` 的 Block 永不收縮。
  - 全部收縮到下限仍不足：第一個 Block 的 y 等於 `top`，由上往下排。
  - 空陣列不拋錯；同樣輸入呼叫兩次，記錄的引數完全相同（SC-010）。
  
  接著建立 `web/app/core/share-card/share-card-layout.ts`：export `Block`、`stackBlocks(blocks, area)`，以及常數 `SHARE_CARD_MIDDLE_TOP = 230`、`SHARE_CARD_MIDDLE_BOTTOM = 1174`、`SHARE_CARD_BLOCK_GAP = 48`、`SHARE_CARD_BLOCK_MIN_GAP = 32`（**此時沿用 040 現值**，US2 才調整）。
- [ ] T009 先寫 `web/app/core/share-card/share-card-footer.spec.ts`（本 phase 只涵蓋現行頁尾）：以 `RecordingContext` 驗證畫出分隔線、右對齊的 `shareCard.brand`；`meta` 有值時在左側畫出且寬度不與品牌字樣重疊、為 `null` 時不畫。接著建立 `web/app/core/share-card/share-card-footer.ts`：export `PromoFooter`（本 phase 只有 `meta: string | null` 一個欄位）與 `drawPromoFooter(ctx, footer, env)`，內容為 `share-card-renderer.ts` 的 `drawFooter()` **原樣搬移**，差別只有：品牌字樣的 key 由 `matchShareCard.brand` 改為 `shareCard.brand`，時長／每分耗時文字改由呼叫端組好後以 `footer.meta` 傳入。
- [ ] T010 建立 `web/app/core/share-card/share-card-option.ts`：依 contracts/share-card-core.md §1 定義 `ShareCardSource`、`ShareCardRenderEnv`（本 phase 為 `{ palette; text; fonts }`，`footer` 欄位留到 T028 加入）、`ShareCardOption`。接著修改 `web/app/core/match-share-card/share-card-renderer.ts`：`renderShareCard()` 的區塊堆疊改呼叫 `stackBlocks()`（各 Block 都不給 `minHeight`，`draw` 忽略第二個引數），頁尾改呼叫 `drawPromoFooter()`，`meta` 由原本 `drawFooter()` 內組時長與每分耗時的邏輯產生（`durationText()` 留在本檔）。刪除本檔已搬走的私有函式與常數。`share-card-renderer.spec.ts` 除 T006 的 import 與假 `ShareCardText` 需認得 `shareCard.brand` 之外不得修改，且必須全綠——這是版面未變的證據。
- [ ] T011 先把 `web/app/core/match-share-card/share-card-actions.service.spec.ts` 以 `git mv` 搬到 `web/app/core/share-card/`，並依新介面調整：`rasterize(option, theme)` 會以 `SHARE_PALETTES[theme]`、翻譯函式、字型組出 `env` 後呼叫 `option.draw(ctx, env)` 恰好一次；新增一例斷言 `share(file)` 傳給 `navigator.share` 的物件**只有 `files` 一個鍵**（research Decision 8、contracts/landing-link.md §4）。確認失敗後，把 `share-card-actions.service.ts` 以 `git mv` 搬到 `web/app/core/share-card/` 並改為接受 `ShareCardOption`（不再 import `renderShareCard`）。其餘方法（`canShareFiles`、`canCopyImage`、`copyImage`、`download` 含 1 秒延遲 revoke、`createObjectUrl`、`revokeObjectUrl`）不變。
- [ ] T012 建立預覽外殼 `web/app/core/share-card/share-card-preview/share-card-preview.component.{ts,html,scss}`（selector `app-share-card-preview`）：把 `web/app/core/match-share-card/share-card-dialog/share-card-dialog.component.{ts,html,scss}` 的內容搬入，公開介面改為 `open(options: readonly ShareCardOption[])`／`close()`（contracts/share-card-core.md §2）；內部以 signal `selected` 記住目前選項（本 phase 固定為 `options[0]`，種類切換 UI 留到 US3）；`fileName` 與 `alt` 取自選項；範本中所有 `matchShareCard.*` key 改為對應的 `shareCard.*`。把 `share-card-dialog.component.spec.ts` 的既有案例（能力偵測顯示／隱藏按鈕、`AbortError` 不顯示錯誤、其他錯誤顯示提示、切換配色重新產圖、過期產圖結果被丟棄、關閉與 Esc 都會 revoke object URL 並歸還焦點）搬到 `share-card-preview.component.spec.ts`，改用假的 `ShareCardOption`；全綠後才進 T013。
- [ ] T013 把 040 的 dialog 改為門面：新增 `web/app/core/match-share-card/match-share-card-option.ts`，export `toMatchShareCardOption(model: ShareCardModel): ShareCardOption`（`source: 'card-match'`、`labelKey: 'matchShareCard.kind'`、`fileName`／`altText` 取自 model、`draw` 呼叫 `renderShareCard`），並在兩份語系檔新增 `matchShareCard.kind`（zh「單場比賽」／en「Match」）。`share-card-dialog.component.ts` 縮減為：範本只放一個 `<app-share-card-preview>`，`open(detail, context)` **簽章不變**，內部為 `preview.open([toMatchShareCardOption(buildShareCardModel(detail, context))])`。`share-card-dialog.component.spec.ts` 改寫為驗證委派（以正確的選項呼叫外殼、`source` 為 `card-match`、檔名與替代文字來自 model）。`web/app/core/match-record-detail/` 與四個呼叫端的原始檔與 spec **不得修改**。
- [ ] T014 [P] 從兩份語系檔的 `matchShareCard.*` 刪除已搬到 `shareCard.*` 的 key（`previewTitle`、`themeLabel`、`themeLight`、`themeDark`、`share`、`copy`、`copied`、`download`、`close`、`generating`、`generateError`、`shareError`、`copyError`、`brand`、`dateFormat`），保留 contracts/share-card-core.md §8 列為比賽專屬的 key。`share-card-renderer.ts` 的日期樣式 key 改用 `shareCard.dateFormat`。以 `grep -rn "matchShareCard\.\(previewTitle\|theme\|share\|copy\|copied\|download\|close\|generat\|brand\|dateFormat\)" apps/web/src` 確認沒有殘留引用。
- [ ] T015 [P] 先寫 `web/app/shared/line-chart/line-chart-scale.spec.ts`（research Decision 11；`shared/line-chart/` 目前沒有任何 spec，這份同時是現行行為的特性測試）：`kind: 'rate'` 時取資料最小／最大值並夾在 0～1；全部相同時上下各留 0.05（仍夾在 0～1）；`kind` 非 rate 時全平上下各留 0.5 且不夾；空陣列回傳 `{ min: 0, max: 1 }`；`null` 值被忽略；有傳 `bounds` 時直接採用。接著建立 `web/app/shared/line-chart/line-chart-scale.ts`，把 `line-chart.component.ts` 的 `range` 計算**原封不動**抽成 `computeLineChartRange(values, kind, bounds)`，另 export `normalizeToRange(value, range)`（回傳 0～1）；元件的 `range` 改為呼叫它。`web/app/shared/round-trend-chart/round-trend-chart.component.spec.ts` 不改動且全綠。
- [ ] T016 在 `apps/web` 執行 `npx ng test --watch=false`、`npx ng lint`、`npx ng build`，全部通過；並以 `git diff --stat origin/ut -- apps/web/src/app/core/match-share-card/share-card-model.ts apps/web/src/app/core/match-share-card/share-card-model.spec.ts apps/web/src/app/core/match-share-card/share-card-highlights.ts apps/web/src/app/core/match-share-card/share-card-highlights.spec.ts apps/web/src/app/core/match-record-detail apps/web/src/app/features apps/api` 輸出為空，作為「040 的規則、比賽詳情 dialog、四個呼叫端、後端皆未變動」的證據。Commit：「圖卡的預覽、分享與排版改為各種圖卡共用（單場比賽圖卡的畫面與操作不變）」。

**Checkpoint**：共用層就緒，040 行為不變且全綠，可以開始各 story。

---

## Phase 3: User Story 1 - 從團戰績頁產生「團排行榜卡」（Priority: P1）🎯 MVP

**Goal**：會員在「我的團」的團戰績頁按「分享圖卡」，看到排行榜卡預覽（團名、日期、球員人數、前 3 列頒獎台＋第 4～6 列、本人標示「我」、本人不在前 6 列時另附一列），並可下載／分享／複製 1080×1350 的 PNG。此時頁尾仍是 040 現行的品牌字樣頁尾，US2 才換成導流頁尾。

**Independent Test**：任選一個至少有 1 場已完成比賽的團 → 團戰績頁 →「分享圖卡」→ 卡上前 6 列的名次、暱稱、勝負場數與順序和頁面排名表逐一相同 →「下載圖片」得到 1080×1350 PNG（spec US1、quickstart 第 2 節步驟 1～4、8、9）。

### Tests for User Story 1 ⚠️（先寫，確認會失敗）

- [ ] T017 [P] [US1] 新增 `web/app/core/group-share-card/leaderboard-card-model.spec.ts`，逐條涵蓋 contracts/group-share-card.md 的 L1～L9：
  - L1：1／2／3／6／7／40 位有出賽球員時 `rows.length` 為 `min(N, 6)`；`rows` 的暱稱序列等於輸入濾掉 0 場後的前綴；另以一份**刻意不照勝場排序**的輸入驗證輸出順序仍與輸入相同（證明沒有排序）。
  - L2：名次 1、1、3 原樣保留；1、2、3、3、3、3、3（並列跨越第 6 列）取前 6 列且名次原樣。
  - L3：`podium` 只有前 3 列為 true；只有 2 位球員時兩列皆為 true。
  - L4：本人在第 2 列 → `selfRow === null` 且該列 `isSelf`；本人在第 9 列 → `selfRow` 為本人且 `rank` 為其真實名次；本人 0 場 → `selfRow === null`；名單中沒有本人列 → `selfRow === null`。
  - L5：第 7 列以後（非本人）的暱稱不出現在 `JSON.stringify(model)` 中。
  - L6：`JSON.stringify(model)` 不含 `current_status`、`roster_entry_id`、`'left'`、`'kicked'`，也不含任何輸入的 `roster_entry_id` 值。
  - L7：中間夾雜 0 場球員時，`playerCount` 為有出賽的列數，且 0 場球員不在 `rows`。
  - L8：`final_standings` 為空、或全員 0 場 → 回傳 `null`。
  - L9：同樣輸入呼叫兩次，結果深度相等。
  - 另驗證：`date` 等於 `context.createdAt`（為 `null` 時為 `null`）；`fileName` 為 `rally-stats-rank-YYYYMMDD-<安全團名>.png`（無日期時為 `nodate`；團名中的 `/ \ : * ? " < > |` 與空白被替換，長度上限 40）；`altText.key === 'groupShareCard.leaderboard.altText'` 且參數含團名與前 3 列暱稱（不足 3 列時為空字串）。
- [ ] T018 [P] [US1] 新增 `web/app/core/group-share-card/leaderboard-card-renderer.spec.ts`，使用 `RecordingContext` 與假的 `ShareCardText`（對 `shareCard.dateFormat` 回傳真實格式字串，其餘回傳 `key|JSON(params)`）：
  - 畫出團名、`groupShareCard.leaderboard.title`、格式化後的日期、`groupShareCard.leaderboard.playerCount`、每一列的名次數字、暱稱與 `groupShareCard.leaderboard.record`。
  - `date === null` 時不畫日期，副標其餘部分照常。
  - 本人列畫出 `groupShareCard.selfTag` **文字**（FR-010）；非本人列沒有。
  - 前 3 列各有一個獎牌圓（`recordedArcs`）且圓內有名次數字文字（FR-009）；第 4 列以後沒有獎牌圓——但名次 ≤ 3 的第 4 列（並列 1、2、3、3）仍有。
  - 有 `selfRow` 時畫出分隔符號與本人列，且本人列的 y 大於第 6 列；沒有時兩者都不畫。
  - 只有 1 位球員時只畫 1 列，沒有其他名次格（`recordedRoundRects` 數量與列數一致）。
  - 20 字暱稱與 40 字團名被截斷並以「…」結尾；所有文字的水平範圍（`RecordingContext.span`）都在左右邊距內；勝負場數欄的 x 不因暱稱長度改變（SC-005）。
  - 最壞情況（6 列＋`selfRow`）下 `bottomEdge({ above: SHARE_CARD_MIDDLE_BOTTOM + 1 })` ≤ `SHARE_CARD_MIDDLE_BOTTOM`（contracts/share-card-core.md §6 不變式）。
  - 亮色與暗色各跑一次，背景 `fillRect` 的顏色為對應色盤的 `background`。
- [ ] T019 [P] [US1] 新增 `web/app/core/group-share-card/group-share-cards.spec.ts`（US1 段落）：有出賽球員時 `availableGroupCards()` 的第一個選項 `source === 'card-rank'`、`labelKey === 'groupShareCard.kind.leaderboard'`、`fileName`／`altText` 來自排行榜模型；全員 0 場時回傳 `[]`；選項的 `draw` 以 `RecordingContext` 呼叫後會畫出團名。
- [ ] T020 [P] [US1] 擴充 `web/app/features/member/my-groups/group-history/group-history.component.spec.ts`：
  - 頁面載入成功且有可用圖卡時顯示 `groupShareCard.openButton` 按鈕；載入中、載入錯誤、或 `final_standings` 全員 0 場時**不顯示**（FR-001）。
  - 點擊按鈕後，以 `availableGroupCards()` 的結果呼叫 `ShareCardPreviewComponent.open()`（以替身外殼或 spy 驗證第一個選項 `source === 'card-rank'`）。
  - 初始化時呼叫一次 `FriendsService.getMyGroups()`；成功時選項的檔名含該團 `created_at` 的日期；`getMyGroups()` 失敗、或清單中沒有該團時，頁面**不進入錯誤狀態**、按鈕仍可用、檔名為 `nodate`（research Decision 7）。
  - 在對戰紀錄套用暱稱篩選並換頁後，再次開啟時傳給外殼的選項 `fileName` 與 `altText` 與篩選前相同（規格 Edge Cases）。

### Implementation for User Story 1

- [ ] T021 [US1] 建立 `web/app/core/group-share-card/group-share-card.models.ts`：依 data-model.md 第 3 節定義 `GroupShareCardContext`、`LeaderboardRow`、`LeaderboardCardModel`（`MyStatsCardModel` 留到 US3）。不得使用 `any`；不得包含 `current_status` 或任何 ID 欄位。
- [ ] T022 [US1] 實作 `web/app/core/group-share-card/leaderboard-card-model.ts`：`buildLeaderboardCardModel(history, context)`，只用 `filter`（`total_matches ≥ 1`）、`slice(0, 6)`、`find(is_self)`——**不得**呼叫 `sort`、不得重新計算或重新編號 `rank`（FR-008、憲章 X）。檔名的安全字元處理與日期格式化寫成本檔的私有小函式。讓 T017 全綠。
- [ ] T023 [US1] 實作 `web/app/core/group-share-card/leaderboard-card-renderer.ts`：`renderLeaderboardCard(ctx, model, env)`，結構為背景 → 標題區（團名；副標「排行榜 · 日期 · N 位球員」，日期用 `formatDate(model.date, env.text('shareCard.dateFormat'), 'en-US')`）→ `stackBlocks()` 排中段（頒獎台區塊：每列高 120，獎牌圓＋名次數字、暱稱粗體、勝負；一般列區塊：每列高 76；`selfRow` 區塊：分隔符號「⋯」＋一列）→ `drawPromoFooter(ctx, { meta: null }, env)`。獎牌一律用 `arc`＋數字文字繪製、不用 emoji（contracts/group-share-card.md §2）；獎牌依 `rank ≤ 3`，頒獎台樣式依 `podium`；「我」以 `pill` 底色＋文字呈現。顏色全部取自 `env.palette`，必要時在 `web/app/core/share-card/share-card-palette.ts` 新增 `medalGold`／`medalSilver`／`medalBronze`／`selfHighlight` 四個欄位（兩種色盤都要給值，並在 `share-card-palette.spec.ts` 補上文字對比 ≥ 4.5:1 的斷言）。讓 T018 全綠。
- [ ] T024 [US1] 實作 `web/app/core/group-share-card/group-share-cards.ts`：`availableGroupCards(history, context): ShareCardOption[]`，本階段只組排行榜選項。讓 T019 全綠。
- [ ] T025 [US1] 接線 `web/app/features/member/my-groups/group-history/group-history.component.{ts,html,scss}`（contracts/group-share-card.md §3）：新增 signal `createdAt`，初始化時訂閱 `friends.getMyGroups()`，以路由的 `groupId` 找出該團的 `created_at`，錯誤時維持 `null` 且不碰 `errorKey`；`shareOptions = computed(…)`；標題列加上原生 `<button type="button">`（`@if (shareOptions().length > 0)`），點擊呼叫 `preview().open(shareOptions())`；範本加入 `<app-share-card-preview>` 並在 `imports` 登記。既有的比賽詳情 dialog 與其 `shareContext` 不動。讓 T020 全綠。
- [ ] T026 [US1] 在 `apps/web` 執行 `npx ng test --watch=false`、`npx ng lint`、`npx ng build` 全部通過後 commit：「我的團的團戰績頁可以產生排行榜分享圖卡：前三名頒獎台、第 4–6 名，並標出自己」。

**Checkpoint**：MVP 可以單獨交付——排行榜卡可預覽、下載、分享、複製；頁尾仍為品牌字樣。

---

## Phase 4: User Story 2 - 圖卡頁尾帶網址與 QR 碼（Priority: P1）

**Goal**：所有圖卡（排行榜卡與 040 單場比賽圖卡；US3 的我的成績卡完成後自動套用）的頁尾改為品牌字樣＋標語＋可讀網址＋QR 碼；QR 指向 `<origin>/?ref=<card-rank|card-me|card-match>`。040 圖卡的內容不變，中段只在放不下時依固定規則收縮。

**Independent Test**：產生排行榜卡與 040 單場圖卡並下載 → 頁尾四個元素齊全 → 手機掃描（原尺寸與縮 50%）可開啟首頁且 `ref` 值正確 → 內容全滿的 040 圖卡沒有任何內容被省略或壓到頁尾（spec US2、quickstart 第 2 節步驟 12～14 與第 3 節）。

### Tests for User Story 2 ⚠️（先寫，確認會失敗）

- [ ] T027 [P] [US2] 新增 `web/app/core/share-card/share-card-link.spec.ts`（contracts/share-card-core.md §4、landing-link.md §1）：三種 `source` 各得到 `${origin}/?ref=${source}`；`displayUrl` 等於 `host`，不含 `http`、`/`、`?`；`origin` 含連接埠時照常帶入；輸出字串不含任何 UUID 樣式（以正規表示式斷言，FR-021）。
- [ ] T028 [P] [US2] 新增 `web/app/core/share-card/share-card-qr.spec.ts`：`qrLayout(33)` → `modulePx 6`；`qrLayout(29)` → `6`；`qrLayout(37)` → `4`；`qrLayout(53)` → `4`；`qrLayout(57)` → `null`；對 21～177 的每個合法尺寸，結果不是 `null` 時 `modulePx` 必為偶數、≥ 4，且 `(size + 4) × modulePx ≤ 240`、`offset` 使 QR 在 240 底板內置中（research Decision 5）。`toQrMatrix(url, create)`：以假的 `create` 回傳 `{ modules: { size, get } }` 時輸出的 `isDark(r, c)` 與其一致；`create` 拋錯時回傳 `null`；以**真的** `qrcode` 的 `create`（spec 內靜態 import）對同一網址呼叫兩次，矩陣完全相同，且 44 字元網址在等級 M 下 `size === 33`；確認傳給 `create` 的選項為 `{ errorCorrectionLevel: 'M' }`。
- [ ] T029 [P] [US2] 擴充 `web/app/core/share-card/share-card-footer.spec.ts`（contracts/share-card-core.md §5）：
  - 有 `qr` 時：畫出一個 240×240 的白色底板（`recordedRoundRects` 或 `recordedRects`，顏色為色盤的 `qrPlate`，亮暗兩種色盤皆為 `#ffffff`）；深色模組的 `fillRect` 數量等於矩陣中深色模組數，每個寬高等於 `modulePx`、顏色為 `qrModule`（兩種色盤相同的近黑色）、座標全部落在底板內。
  - 左側依序畫出 `meta`（有值時）、`shareCard.brand`、`shareCard.tagline`、`link.displayUrl`、`shareCard.scanHint`；所有左側文字的右緣 ≤ 底板左緣 − 24（SC-005）。
  - 200 字元的標語與 80 字元的 `displayUrl` 被截斷且仍不進入底板範圍。
  - `qr === null`：不畫底板與任何模組、不畫 `scanHint`，仍畫品牌、標語與 `displayUrl`，且文字可用寬度擴到整個內容寬。
  - `qrLayout()` 回傳 `null` 的超大矩陣：行為同 `qr === null`。
  - 頁尾所有繪製的 y 都 ≥ `SHARE_CARD_MIDDLE_BOTTOM`，且下緣 ≤ 1350 − 56。
- [ ] T030 [P] [US2] 擴充 `web/app/core/share-card/share-card-actions.service.spec.ts`：`rasterize()` 交給 `option.draw` 的 `env.footer.link` 為 `buildShareCardLink(window.location, option.source)` 的結果、`env.footer.qr` 為非 `null` 的矩陣；以注入的載入函式模擬 `qrcode` 動態載入失敗時，`rasterize()` **仍回傳 Blob** 且 `env.footer.qr === null`（contracts/share-card-core.md §3 不變式）；`env.footer.meta` 來自選項（見 T033）。
- [ ] T031 [P] [US2] 更新 `web/app/core/match-share-card/share-card-renderer.spec.ts`（FR-022 允許的範圍）：頁尾斷言改為「時長與每分耗時出現在頁尾的 `meta` 行、`shareCard.brand`／`tagline` 有畫出」；新增「內容全滿」一例——雙打、我方視角（有徽章）、走勢圖、3 個亮點——斷言：兩隊所有暱稱、雙方比分、徽章、走勢折線（`recordedPolylines` 2 條）、3 個亮點文字**全部都有畫**，且 `bottomEdge({ above: SHARE_CARD_MIDDLE_BOTTOM + 1 })` ≤ `SHARE_CARD_MIDDLE_BOTTOM`；新增「只有隊伍區塊」一例，斷言走勢與亮點未出現時隊伍區塊仍垂直置中（沒有觸發收縮）。
- [ ] T032 [P] [US2] 擴充 `web/app/core/group-share-card/leaderboard-card-renderer.spec.ts`：傳入含 `qr` 的 `env.footer` 時，最壞情況（6 列＋`selfRow`）仍不超出新的 `SHARE_CARD_MIDDLE_BOTTOM`；頁尾畫出 `displayUrl`。

### Implementation for User Story 2

- [ ] T033 [US2] 擴充型別：`web/app/core/share-card/share-card-footer.ts` 的 `PromoFooter` 加上 `link: ShareCardLink`、`qr: QrMatrix | null`；`web/app/core/share-card/share-card-option.ts` 的 `ShareCardRenderEnv` 加上 `footer: PromoFooter`，`ShareCardOption` 加上選填的 `footerMeta?(text: ShareCardText): string | null`（040 用它回傳時長／每分耗時，團圖卡不提供）。`web/app/core/share-card/share-card-palette.ts` 兩種色盤新增 `qrPlate: '#ffffff'`、`qrModule: '#111827'`（兩者對比遠高於 QR 所需）。
- [ ] T034 [P] [US2] 實作 `web/app/core/share-card/share-card-link.ts`：`buildShareCardLink(location, source)`。讓 T027 全綠。
- [ ] T035 [P] [US2] 實作 `web/app/core/share-card/share-card-qr.ts`：`QrMatrix`、`QrCreate` 型別（只描述用到的 `create(text, options) => { modules: { size; get(row, col) } }`，不把 `qrcode` 的型別外洩到模組外）、`toQrMatrix()`、`qrLayout()`、常數 `QR_PLATE_SIZE = 240`。讓 T028 全綠。
- [ ] T036 [US2] 改寫 `web/app/core/share-card/share-card-footer.ts` 的 `drawPromoFooter()` 為導流頁尾（contracts/share-card-core.md §5 的版面表）：頁尾高 240、下邊距 56、右側 240×240 圓角白底板＋逐模組 `fillRect`、左側文字欄。同時把 `web/app/core/share-card/share-card-layout.ts` 的 `SHARE_CARD_MIDDLE_TOP` 改為 210、`SHARE_CARD_MIDDLE_BOTTOM` 改為頁尾分隔線上方（約 996，依實際版面定值並在檔內以註解寫出算式，research Decision 6）。讓 T029、T032 全綠。
- [ ] T037 [US2] 修改 `web/app/core/share-card/share-card-actions.service.ts` 的 `rasterize()`：`buildShareCardLink(window.location, option.source)` → 以可注入的載入函式（預設 `() => import('qrcode')`）取得 `create`，任何例外都降為 `qr = null` → 組出 `env.footer`（`meta` 取自 `option.footerMeta?.(text) ?? null`）。執行 `npx ng build`；若出現 `qrcode` 的 CommonJS 相依警告，在 `apps/web/angular.json` 的 build options 加入 `"allowedCommonJsDependencies": ["qrcode"]`，build 必須零警告。讓 T030 全綠。
- [ ] T038 [US2] 修改 `web/app/core/match-share-card/share-card-renderer.ts` 與 `match-share-card-option.ts`（FR-022）：走勢區塊給 `minHeight: 140` 並依 `draw(y, height)` 收到的高度繪製；亮點區塊的 `minHeight` 以列高 52 計算，`draw` 依實際高度換算列高；隊伍區塊內兩隊之間的間距在區塊被收縮時由 48 降為 32（以隊伍區塊的 `minHeight` 表達）；時長／每分耗時改由選項的 `footerMeta` 提供，renderer 不再自己畫。**不得**修改 `share-card-model.ts`、`share-card-highlights.ts` 及其 spec。讓 T031 全綠。
- [ ] T039 [P] [US2] 更新 `specs/040-match-share-card/spec.md`：在 FR-006、US1 驗收情境 5 與 Assumptions「品牌字樣即足夠」三處各加一行註記「已由 041-group-share-cards FR-018 取代：圖卡頁尾現含網址與 QR 碼」，不改動原文。
- [ ] T040 [US2] 在 `apps/web` 執行 `npx ng test --watch=false`、`npx ng lint`、`npx ng build` 全部通過，並再次確認 T016 的 `git diff --stat`（model／highlights／比賽詳情 dialog／四個呼叫端／後端）為空後 commit：「所有分享圖卡的頁尾加上標語、網址與 QR 碼，掃描即可進入系統首頁」。

**Checkpoint**：US1＋US2 可以一起交付——圖卡有了導流能力；040 單場圖卡同步升級。

---

## Phase 5: User Story 3 - 「我的本團成績卡」與圖卡種類切換（Priority: P2）

**Goal**：有出賽的會員在同一個預覽中可切換到「我的成績」：大字勝率、勝負與總場數、團內名次、各輪勝率走勢縮圖（≥ 2 輪）、最常交手的前 3 位對手；切換種類時保留配色。

**Independent Test**：以有出賽的會員開啟預覽 → 切到「我的成績」→ 數字與頁面「我的戰績」區塊及排名表本人列一致、走勢形狀與頁面一致、對手為頁面清單前 3 位且順序相同 → 先切暗色再切種類，配色維持暗色（spec US3、quickstart 第 2 節步驟 5～8）。

### Tests for User Story 3 ⚠️（先寫，確認會失敗）

- [ ] T041 [P] [US3] 新增 `web/app/core/group-share-card/my-stats-card-model.spec.ts`，逐條涵蓋 contracts/group-share-card.md 的 M1～M6：
  - M1：`my_stats.total_matches === 0` → `null`。
  - M2：`winRate` 等於 `formatPercent(win_rate)`，以 0、0.6、0.666…、1 各驗一次。
  - M3：`standing` 為本人列的 `rank` 與有出賽人數；沒有本人列 → `standing === null` 且 `nickname === null`。
  - M4：0 或 1 輪 → `trend === null`；3 輪 → 3 個點，x 為 0／50／100，y 以 `computeLineChartRange(values, 'rate', null)` 與 `normalizeToRange` 換算後與手算值相同；各輪勝率全部相同時點落在中線（沿用「全平留 0.05」規則）。
  - M5：0 筆 → `[]`；1 筆 → 1 筆；5 筆 → 前 3 筆且順序與輸入相同；另以**刻意不照場數排序**的輸入驗證沒有重新排序；輸出不含 `win_rate`、`matches` 以外的推導欄位。
  - M6：`createdAt === null` → `date === null`。
  - 另驗證 `fileName` 為 `rally-stats-me-…png`、`altText.key === 'groupShareCard.myStats.altText'`、同樣輸入兩次深度相等、`JSON.stringify(model)` 不含任何 ID。
- [ ] T042 [P] [US3] 新增 `web/app/core/group-share-card/my-stats-card-renderer.spec.ts`：畫出團名、`groupShareCard.myStats.title`、日期、暱稱、大字勝率字串（字級為全卡最大）、`groupShareCard.myStats.record`、`groupShareCard.myStats.standing`、`groupShareCard.myStats.trendTitle` 與 1 條折線、`groupShareCard.myStats.opponentsTitle` 與每位對手的暱稱及 `opponentRecord`；`standing`／`trend`／`opponents`／`nickname`／`date` 各自缺漏時對應元素完全不畫、且沒有多出的 `recordedRoundRects`（無空框，FR-017）；20 字暱稱（本人與對手）被截斷不超界；最壞情況（全部區塊都有、3 位對手）下走勢區塊被收縮但 `bottomEdge` 不超過 `SHARE_CARD_MIDDLE_BOTTOM`；亮暗兩種色盤。
- [ ] T043 [P] [US3] 擴充 `web/app/core/group-share-card/group-share-cards.spec.ts`：本人有出賽 → 兩個選項、順序固定為 `card-rank`、`card-me`；本人 0 場 → 只有 `card-rank`；全員 0 場 → `[]`。
- [ ] T044 [P] [US3] 擴充 `web/app/core/share-card/share-card-preview/share-card-preview.component.spec.ts`（contracts/share-card-core.md §2）：1 個選項時不渲染種類切換；2 個選項時渲染 2 顆原生 `<button>`、文字為各自 `labelKey` 的翻譯、`aria-pressed` 反映選取狀態、外層有 `shareCard.kindLabel` 的群組標籤；點第二顆 → 以第二個選項重新 `rasterize`、`alt` 與下載檔名換成第二個選項；先選暗色再切種類 → `rasterize` 收到的 theme 仍為 `'dark'`（FR-004）；點已選取的那顆不重新產圖；重新 `open()` 後回到第一個選項與亮色；切換途中較舊的產圖結果被丟棄。
- [ ] T045 [P] [US3] 擴充 `web/app/features/member/my-groups/group-history/group-history.component.spec.ts`：本人有出賽時傳給外殼 2 個選項；本人 0 場但團內有比賽時 1 個。

### Implementation for User Story 3

- [ ] T046 [US3] 在 `web/app/core/group-share-card/group-share-card.models.ts` 加入 `MyStatsCardModel`（data-model.md 第 3 節），並實作 `web/app/core/group-share-card/my-stats-card-model.ts`：`buildMyStatsCardModel(history, context)`。`playerCount` 的定義與排行榜卡共用同一個小函式（從 `leaderboard-card-model.ts` export），不得各寫一份；對手只用 `slice(0, 3)`，**不得**排序或挑選（FR-016）。讓 T041 全綠。
- [ ] T047 [US3] 實作 `web/app/core/group-share-card/my-stats-card-renderer.ts`：`renderMyStatsCard(ctx, model, env)`，背景 → 標題區 → `stackBlocks()`（主視覺區塊：暱稱、大字勝率用 `env.fonts.score`、勝負總場數；名次膠囊；走勢區塊 `height 220`／`minHeight 140`，單一折線用 `palette.trendA`；對手區塊：小標＋最多 3 列）→ `drawPromoFooter(ctx, env.footer, env)`。缺漏的區塊不進入 `stackBlocks()`。讓 T042 全綠。
- [ ] T048 [US3] 擴充 `web/app/core/group-share-card/group-share-cards.ts`：加入我的成績選項（`source: 'card-me'`、`labelKey: 'groupShareCard.kind.myStats'`）。讓 T043、T045 全綠（`group-history` 元件本身不需再改，因為它只轉交 `availableGroupCards()` 的結果）。
- [ ] T049 [US3] 在 `web/app/core/share-card/share-card-preview/share-card-preview.component.{ts,html,scss}` 加上種類切換：`@if (options().length > 1)` 渲染 `role="group"`＋`aria-label` 的按鈕列，樣式比照既有的配色切換；`selectOption(option)` 在選項不同且狀態非 `idle` 時更新 `selected` 並重新 `generate()`，**不重設** `theme`；`open()` 重設為第一個選項與亮色。讓 T044 全綠。
- [ ] T050 [US3] 在 `apps/web` 執行 `npx ng test --watch=false`、`npx ng lint`、`npx ng build` 全部通過後 commit：「分享圖卡新增「我的成績」：勝率、名次、各輪走勢與最常交手的對手，可在預覽中切換圖卡種類」。

**Checkpoint**：兩種團圖卡都可用，並且都帶導流頁尾。

---

## Phase 6: User Story 4 - 掃 QR 進來的人看得懂、知道怎麼開始（Priority: P2）

**Goal**：首頁從一行標題擴充為最小可用的介紹頁：系統名稱、與圖卡頁尾相同的標語、3 項功能重點、行動按鈕；帶 `ref` 參數時畫面完全相同。

**Independent Test**：未登入開啟 `/`、`/?ref=card-rank`、`/?ref=<script>` → 畫面相同、無錯誤、參數未被顯示 → 按鈕進入註冊／登入；已登入時主要按鈕進入 `/member`；360px 寬不需捲動即可看到標語與主要按鈕（spec US4、quickstart 第 5 節）。

### Tests for User Story 4 ⚠️（先寫，確認會失敗）

- [ ] T051 [US4] 擴充 `web/app/features/home/home.component.spec.ts`（contracts/landing-link.md §2）：
  - 渲染 `home.title`、`shareCard.tagline`（與圖卡頁尾**同一個 key**）、3 個功能重點（各有標題與內文）。
  - `AuthService.loggedIn()` 為 false：主要連結的 `routerLink` 為 `/auth/register`、文字 `home.cta.start`；次要連結為 `/auth/login`、文字 `home.cta.login`；沒有 `/member` 連結。
  - 為 true：主要連結為 `/member`、文字 `home.cta.member`；沒有註冊／登入連結；**沒有**發生導覽（以 Router spy 斷言 `navigate`／`navigateByUrl` 未被呼叫，FR-026）。
  - 以 `provideRouter` 搭配 `?ref=card-rank`、`?ref=%3Cscript%3E`、`?foo=bar` 三種網址渲染：DOM 的 `textContent` 與不帶參數時完全相同，且不含 `card-rank` 或 `script` 字樣（FR-025）。
  - 元件類別不注入 `ActivatedRoute`（以原始碼層級的約定為準：spec 中不提供 `ActivatedRoute` 替身也能建立元件）。
  - 切換語言為 `en` 後文字隨之更新。

### Implementation for User Story 4

- [ ] T052 [US4] 實作 `web/app/features/home/home.component.{ts,html,scss}`：注入 `AuthService` 讀取 `loggedIn` signal；範本為 `<main>` 內的標題、標語、`<ul>` 功能重點（沿用既有的 `app-icon`，若無合適圖示則只用文字）、行動按鈕以 `<a routerLink>` 呈現並套用既有的按鈕樣式類別；**不讀取** query string。樣式以行動裝置優先：360×640 視窗下標題、標語、主要按鈕在第一屏內（功能重點可在下方），使用既有的設計 token，不新增顏色。讓 T051 全綠。
- [ ] T053 [US4] 在 `apps/web` 執行 `npx ng test --watch=false`、`npx ng lint`、`npx ng build` 全部通過後 commit：「首頁加上系統介紹與開始使用的按鈕，掃圖卡 QR 碼進來的人知道這是什麼」。

**Checkpoint**：四個 story 全部完成，導流路徑從圖卡到首頁完整接通。

---

## Phase 7: Polish & Cross-Cutting Concerns

- [ ] T054 依 quickstart.md 第 2 節做實際畫面驗收（worktree 前後端 :8001／:4300、`seed_dashboard_demo` 示範資料、先補 `is_creator` 的 `UPDATE`；驗收在跑任何會清空測試 DB 的 pytest 之前進行）：步驟 1～14 逐項確認，特別是步驟 3（本人不在前 6 名時的附列）、步驟 10（20 字暱稱／40 字團名）、步驟 13（內容全滿的 040 圖卡）。發現的視覺問題直接修正並補對應的 renderer 斷言。
- [ ] T055 [P] QR 驗收（quickstart.md 第 3 節、SC-006）：下載三種圖卡 × 兩種配色共 6 張；先以腳本回歸——用 `qrcode` 與任一解碼器對「原尺寸」與「縮 50%」各解一次，確認解得的網址與 `ref` 值正確（腳本放在 job 暫存目錄，不進 repo）；再以真機（iOS 相機、Android 相機、LINE 掃描器、LINE 聊天室長按辨識）各掃一輪。無法取得的裝置要在實作備註中明列為未驗證。
- [ ] T056 [P] 量測 SC-001：390×844 視窗、CPU 降速 4 倍，記錄「點分享圖卡 → 預覽出現」（含第一次動態載入 `qrcode`）與「切換種類／配色 → 新圖出現」的中位數，分別 ≤ 2 秒與 ≤ 1 秒；結果寫入實作備註。
- [ ] T057 [P] 系統分享驗收（quickstart.md 第 4 節）：桌機 Chrome 的「複製圖片」與「下載」實測；手機系統分享需要 HTTPS，無法在本機驗證時於實作備註明列，並確認 `share-card-actions.service.spec.ts` 的「只有 `files` 一個鍵」斷言存在且通過。
- [ ] T058 [P] 首頁驗收（quickstart.md 第 5 節步驟 1～5）；步驟 6（5 位新使用者的 10 秒測試，SC-008）需要真人，列為交付後由需求方執行。
- [ ] T059 最終檢查：`npx ng test --watch=false`、`npx ng lint`、`npx ng build` 全部通過且 build 零警告；`git diff --stat origin/ut -- apps/api` 為空；`grep -rn "sort(" apps/web/src/app/core/group-share-card --include=*.ts` 除 spec 的測試資料外沒有結果（FR-008 的最後防線）；`grep -rn "current_status\|roster_entry_id" apps/web/src/app/core/group-share-card --include=*.ts` 除 fixtures 與 spec 外沒有結果（FR-011、FR-021）。
- [ ] T060 在本檔最後補上「實作備註」區段（比照 040）：順序調整、偏離 contracts 之處與原因、實際畫面驗收額外修正的項目、未能在本機驗證的項目、SC-001 量測值；驗收腳本與截圖複製到主 checkout 的 `docs/041-group-share-cards-check/`（僅存在本機、不進 git）。Commit：「041 任務全部完成，補上實作備註與驗收結果」。

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup（Phase 1）**：無依賴。T001、T002、T003 可平行。
- **Foundational（Phase 2）**：依賴 Phase 1（T009、T012 需要 T002 的 `shareCard.*` key）。**阻擋所有 story。**
- **US1（Phase 3）**：依賴 Phase 2。
- **US2（Phase 4）**：依賴 Phase 2；T032 依賴 US1 的 T018／T023（排行榜 renderer 已存在）。若先做 US2 再做 US1，把 T032 移到 US1 之後即可。
- **US3（Phase 5）**：依賴 Phase 2 與 US1（`group-share-cards.ts`、`group-history` 接線、`playerCount` 共用函式）；建議在 US2 之後，renderer 直接使用新的中段範圍。
- **US4（Phase 6）**：只依賴 Phase 1 的 T002（`shareCard.tagline`、`home.*`）；可與 US1～US3 平行。
- **Polish（Phase 7）**：依賴所有 story。

### User Story Dependencies

| Story | 依賴 | 可否單獨交付 |
|---|---|---|
| US1 排行榜卡 | Foundational | ✅ MVP（頁尾為品牌字樣） |
| US2 導流頁尾 | Foundational（T032 需 US1） | ✅ 即使沒有 US1，也會升級 040 單場圖卡 |
| US3 我的成績卡＋切換 | US1 | ✅ 在 US1 之上 |
| US4 首頁 | T002 | ✅ 完全獨立 |

### Within Each User Story

- 測試任務先完成並確認失敗，才開始該 story 的實作任務。
- 純函式（model）→ renderer → 選項組裝 → 頁面接線。
- 每個 story 最後一個任務是「全套測試＋lint＋build」後 commit。

### Parallel Opportunities

- Phase 1：T001、T002、T003。
- Phase 2：T005、T006 可與 T004 之後的任務平行；T014、T015 與 T007～T013 無檔案衝突。T007→T008→T009→T010→T011→T012→T013 都會碰到 `share-card-renderer.ts` 或彼此的產物，須依序。
- US1：T017～T020 四個測試檔互不相干；T022、T023 在 T021 之後可平行（不同檔）。
- US2：T027～T032 六個測試任務可平行；T034、T035 可平行；T036→T037→T038 依序。T039 隨時可做。
- US3：T041～T045 可平行；T046、T049 可平行（不同模組）。
- US4 整個 phase 可與 US1～US3 平行。
- Polish：T055～T058 可平行。

---

## Parallel Example: User Story 1

```bash
# 四個測試檔一起寫（互不相干）：
Task: "T017 leaderboard-card-model.spec.ts（L1～L9）"
Task: "T018 leaderboard-card-renderer.spec.ts"
Task: "T019 group-share-cards.spec.ts（US1 段落）"
Task: "T020 group-history.component.spec.ts 擴充"

# T021 型別完成後：
Task: "T022 leaderboard-card-model.ts"
Task: "T023 leaderboard-card-renderer.ts"
```

## Parallel Example: User Story 2

```bash
# 六個測試任務一起寫：
Task: "T027 share-card-link.spec.ts"
Task: "T028 share-card-qr.spec.ts"
Task: "T029 share-card-footer.spec.ts 擴充"
Task: "T030 share-card-actions.service.spec.ts 擴充"
Task: "T031 share-card-renderer.spec.ts（040 內容全滿）"
Task: "T032 leaderboard-card-renderer.spec.ts 擴充"

# T033 型別完成後：
Task: "T034 share-card-link.ts"
Task: "T035 share-card-qr.ts"
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
- **040 的保護線**：`share-card-model.ts`、`share-card-highlights.ts` 與兩者的 spec、`testing/detail-fixtures.ts`、`core/match-record-detail/`、四個呼叫端，全程不得修改；T016、T040、T059 以 `git diff --stat` 驗證。
- **憲章 X 的保護線**：`core/group-share-card/` 內不得出現 `sort`、不得重算 `rank`、不得從對手戰績另行挑選；T017 的「刻意不照順序的輸入」與 T059 的 grep 共同把關。
- 所有顯示文字只能使用 T002 建立的 key；實作過程中若需要新增 key，兩份語系檔要同時補上，T002 的一致性測試會擋下漏加的情況。
- 系統分享只送圖片檔（research Decision 8）；任何人想加上 `text`／`url`，會被 T011 的「只有 `files` 一個鍵」斷言擋下，需先完成真機驗證並修訂 spec FR-023。
- 每完成一個 phase（Foundational 與各 story）就 commit 一次，commit 訊息使用繁體中文，並描述使用者看得到的變化；結尾附上 session 指定的 `Co-Authored-By` 行。
