---

description: "Task list for 040-match-share-card"
---

# Tasks: 單場比賽分享圖卡（Match Share Card）

**Input**: Design documents from `/specs/040-match-share-card/`

**Prerequisites**: plan.md、spec.md、research.md、data-model.md、contracts/（`match-record-detail-api.md`、`share-card-module.md`）、quickstart.md

**Tests**: **必做**。Constitution II 要求核心規則的測試先於實作撰寫，plan.md 的 Testing 段也列了每個 spec 檔。每個 story 的測試任務 MUST 先完成，並確認它會失敗，才開始該 story 的實作任務。

**Organization**: 依 spec.md 的 user story 分 phase。US1 只動前端，是 MVP；後端 `target_score` 只有亮點會用到，放在 US2。

## Format: `[ID] [P?] [Story] Description`

- **[P]**：可平行執行（不同檔案、不依賴尚未完成的任務）
- **[Story]**：對應 spec.md 的 user story（US1～US5）
- 路徑皆為 repo 相對路徑；前端簡寫 `web/` = `apps/web/src/`，後端簡寫 `api/` = `apps/api/`

## 環境備註（worktree）

- 前端：`ln -s /Users/zcwang/projects/rally-stats/apps/web/node_modules apps/web/node_modules`，在 `apps/web` 執行 `npx ng test --watch=false`、`npx ng lint`、`npx ng build`。
- 後端：`export PATH=/Users/zcwang/projects/rally-stats/apps/api/.venv/bin:$PATH`，在 `apps/api` 執行 `python -m pytest …`（測試 DB `rally_stats_test`）。
- 共用常數與術語：「主角隊」＝中立視角的勝方，或我方視角的我方；`th(r) = max(3, floor(T × r))`，T = `target_score`（research Decision 7）。

---

## Phase 1: Setup（共用基礎）

**Purpose**：建立模組骨架、測試輔助工具與全部語系文字，讓後續各 story 不必同時改同一批檔案。

- [X] T001 建立 `web/app/core/match-share-card/share-card.models.ts`，依 data-model.md B 節與 contracts/share-card-module.md §3–§4 定義型別：`ShareCardContext`（`groupName`、`perspective: { kind: 'neutral' } | { kind: 'mine'; myTeam: 'A' | 'B' }`）、`CardTeam`（`team`、`nicknames`、`score`、`isWinner`、`badge: 'win' | 'victory' | 'defeat' | null`）、`Highlight`（以 `kind` 區分的七種聯集，參數見 data-model.md 的 Highlight 表）、`ShareCardModel`（全部欄位，含 `trend: ScoreTrendPoint[] | null`、`highlights`、`durationSeconds`、`averagePointSeconds`、`fileName`、`altText: { key; params }`）、`ShareTheme = 'light' | 'dark'`、`SharePalette`（背景、主要文字、次要文字、分隔線、A／B 隊色、徽章底色與文字色、走勢線 A／B）、`ShareCardText = (key: string, params?: Record<string, string | number>) => string`，以及 `ShareCardCanvas`（renderer 用到的 `CanvasRenderingContext2D` 子集：`fillStyle`、`strokeStyle`、`lineWidth`、`font`、`textAlign`、`textBaseline`、`fillRect`、`fillText`、`measureText`、`beginPath`、`moveTo`、`lineTo`、`stroke`、`arc`、`fill`、`roundRect`、`save`、`restore`）。`ScoreTrendPoint` 先以 `import type` 指向 T005 會建立的 `web/app/core/match-record-detail/score-trend.ts`；T005 完成前可以暫時在本檔定義同形介面，T005 時再改為 re-export。不得使用 `any`。
- [X] T002 [P] 建立測試輔助檔 `web/app/core/match-share-card/testing/detail-fixtures.ts`：`makeDetail(overrides)` 產生合法的 `MatchRecordDetailResponse`，預設為 21 分制雙打、A 隊 21:17 勝、`record_completeness: 'complete'`、所有 stats 為 null 或 []；另提供 `makeSingles()`、`makePartial()`、`makeNone()`，以及 `withMomentum`、`withClutch`、`withEnding`、`withTempo` 等小工具，方便組出各亮點的邊界情境。`target_score` 此時尚未存在於型別中，先不放；T031 加入型別時再補上預設值 21。
- [X] T003 [P] 建立 `web/app/core/match-share-card/testing/recording-context.ts`：`RecordingContext` 實作 `ShareCardCanvas`，每次 `fillText` 都記錄 `{ text, x, y, font, fillStyle, maxWidthUsed }`，`stroke` 記錄折線點數；`measureText(text)` 回傳 `{ width: [...text].length × 字級 × 0.6 }`，字級從目前 `font` 字串解析出來。對外提供 `texts()`、`findText(substr)`、`polylines()`。
- [X] T004 [P] 在 `web/assets/i18n/zh-TW.json` 與 `web/assets/i18n/en.json` 新增 `matchShareCard` 命名空間，放入 contracts/share-card-module.md §7 列出的**全部** key（按鈕、提示、徽章、`dateFormat`（Angular 日期格式字串：zh-TW 為 `yyyy/M/d`，en 為 `MMM d, yyyy`）、`round`（「第 {round} 輪」／「Round {round}」）、`duration`（「比賽時長 {minutes} 分 {seconds} 秒」）、`durationHours`、`avgPerPoint`（「平均每分 {seconds} 秒」）、`brand`（「Rally Stats」）、`altText`（含 `{first}`、`{firstScore}`、`{second}`、`{secondScore}`、`{winner}` 參數）、七個 `highlight.*`，文案見 data-model.md 的 Highlight 表）。同時新增 `web/app/core/match-share-card/share-card-i18n.spec.ts`：比照 `web/app/core/player-insights/player-insights.component.spec.ts` 的做法 import 兩份 JSON，斷言兩邊的 `matchShareCard` key 集合完全相同，且每個值都是非空字串。

---

## Phase 2: Foundational（阻擋所有 story 的前置工作）

**Purpose**：把走勢點計算從詳情 dialog 抽成共用純函式（research Decision 4）。US1 和 US2 都會改詳情 dialog，所以這個重構要先做完。

**⚠️ CRITICAL**：這個 phase 完成前，不得開始任何 story 的實作。

- [X] T005 先寫 `web/app/core/match-record-detail/score-trend.spec.ts`：`buildScoreTrendPoints(detail)` 在 events 為空時回傳 null；complete 時在最前面補上 (0, 0:0) 原點；partial 時不補原點；`-1` 事件照常成為一個點；x 為 `elapsed / maxElapsed × 100`（maxElapsed 至少 1）；yA、yB 為 `100 − score / maxScore × 100`，maxScore 為 `max(score_a, score_b, 1)`。接著建立 `web/app/core/match-record-detail/score-trend.ts`：把 `web/app/core/match-record-detail/match-record-detail-dialog.component.ts` 中的 `ChartPoint` 介面（更名為 `ScoreTrendPoint`，欄位不變）以及 `chartPoints` 的計算原封不動搬過去，export `buildScoreTrendPoints`。dialog 的 `chartPoints` 改為 `computed(() => { const d = this.detail(); return d ? buildScoreTrendPoints(d) : null; })`。`share-card.models.ts` 改為從這個檔案 re-export `ScoreTrendPoint`。
- [X] T006 在 `apps/web` 執行 `npx ng test --watch=false`，確認 `match-record-detail-dialog.component.spec.ts` 既有的測試一個都沒改動就全數通過，這是重構行為不變的證據。

**Checkpoint**：走勢計算只有一份，可以開始各 story。

---

## Phase 3: User Story 1 - 產生並儲存單場比賽圖卡（Priority: P1）🎯 MVP

**Goal**：任何能開啟比賽詳情的人，都可以按「分享圖卡」看到中立視角的圖卡預覽（團名、日期、輪次、雙方暱稱、比分、勝方徽章、時長、品牌），並下載 1080×1350 的 PNG。

**Independent Test**：從任一入口開啟一場已完成比賽 →「分享圖卡」→ 預覽內容與詳情一致 →「下載圖片」得到 1080×1350 PNG，檔名 `rally-stats-YYYYMMDD-x-y.png`（spec US1、quickstart 步驟 3、8）。

### Tests for User Story 1 ⚠️（先寫，確認會失敗）

- [X] T007 [P] [US1] 新增 `web/app/core/match-share-card/share-card-model.spec.ts`（基本段落）：
  - 中立視角下 `teams[0]` 為勝方，A 勝與 B 勝各一例。
  - `teams[0].badge === 'win'`，`teams[1].badge === null`。
  - 對每一隊，`team`、`score`、`nicknames` 來自同一個原始隊伍（FR-019，B 勝時特別驗證）。
  - 單打每隊 1 個暱稱、雙打 2 個，順序與詳情相同。
  - `durationSeconds` 為 `ended_at − started_at`；任一為 null 或結果為負時為 null。
  - `fileName` 格式為 `rally-stats-YYYYMMDD-{teams[0].score}-{teams[1].score}.png`，日期依裝置時區（測試以固定的 `started_at`，並用 `formatDate` 算出預期值）。
  - `altText.key === 'matchShareCard.altText'`，參數齊全。
  - `groupName`、`roundNumber`、`startedAt` 原樣帶入。
  - 同樣的輸入呼叫兩次，結果深度相等（SC-007）。
- [X] T008 [P] [US1] 新增 `web/app/core/match-share-card/share-card-renderer.spec.ts`（基本段落），使用 `RecordingContext` 與假的 `ShareCardText`：對 `matchShareCard.dateFormat` 回傳真實的格式字串（依測試情境為 zh-TW 的 `yyyy/M/d` 或 en 的 `MMM d, yyyy`），其餘 key 回傳 `key|JSON(params)`：
  - 畫出團名、日期、`matchShareCard.round`、每個暱稱、雙方比分、`matchShareCard.badge.win`、`matchShareCard.brand`。
  - 所有 `fillText` 的 x 加上實際寬度不超過 1080 − 左右邊距。
  - 20 字雙打暱稱被截斷並以「…」結尾，寬度不超過分配寬度（SC-005）。
  - 沒有任何文字含 `http`、`www`、`://`（FR-006）。不檢查 `/`，因為 zh-TW 日期本身含 `/`。
  - `durationSeconds` 為 null 時不畫 duration。
  - **日期格式化不會拋錯**（`/speckit-analyze` U1）：以 zh-TW 格式字串繪製時畫出 `2026/9/21` 這類純數字日期；以 en 格式字串繪製時畫出 `Sep 21, 2026`。兩種情況都在 Angular 預設、未註冊 zh-TW locale data 的測試環境下執行，不得拋出例外。
- [X] T009 [P] [US1] 新增 `web/app/core/match-share-card/share-card-dialog/share-card-dialog.component.spec.ts`，以替身 `ShareCardActions` 提供（`rasterize` 回傳假 Blob，`download` 為 spy）：
  - `open(detail, context)` 後，以 `'light'` 呼叫 `rasterize`。
  - 產生中顯示 `generating`；完成後 `<img>` 的 `src` 為 object URL，`alt` 為翻譯後的 altText。
  - 「下載圖片」一律顯示，按下後呼叫 `download(blob, model.fileName)`。
  - `rasterize` reject 時顯示 `generateError`，且不顯示下載按鈕。
  - 關閉時呼叫 `URL.revokeObjectURL`。
  - **關閉預覽後回到詳情**（FR-003，`/speckit-analyze` G2）：以測試宿主把本元件放在一個已 `open` 的外層 `<dialog>` 內，並由一顆觸發按鈕開啟預覽；關閉預覽後，外層 dialog 的 `open` 仍為 true，`document.activeElement` 為那顆觸發按鈕。
  - **切換語言後重開預覽會使用新語言**（SC-008，`/speckit-analyze` G5）：先以 zh-TW `open` 一次並關閉，再 `TranslateService.use('en')` 後重新 `open`。替身 `rasterize` 第二次收到的文字提供者（或它呼叫 `TranslateService.instant` 的結果）對 `matchShareCard.brand`、`matchShareCard.badge.win` 等 key 回傳的是 en 文案；`<img>` 的 alt 也是英文。若 `rasterize` 的簽章不直接帶文字提供者，改為斷言 `rasterize` 內部讀取文字的時點在 `open` 之後（例如在替身中呼叫注入的 `TranslateService.instant` 並記錄結果）。
- [X] T010 [P] [US1] 擴充 `web/app/core/match-record-detail/match-record-detail-dialog.component.spec.ts`：
  - `shareContext` 為 null 時沒有「分享圖卡」按鈕。
  - 有 context，但 `loading()` 或 `loadError()` 為 true 時，按鈕不存在或 disabled。
  - detail 已載入且有 context 時，點按鈕會以 `(detail, context)` 呼叫子元件 `ShareCardDialogComponent.open`（以 `viewChild` 替身或 spy 驗證）。
- [X] T011 [P] [US1] 擴充四個呼叫端與父元件的 spec：
  - `web/app/features/member/match-history/match-history.component.spec.ts`、`web/app/features/friends/friend-match-records/friend-match-records.component.spec.ts`：點開某一列後，dialog 收到 `{ groupName: 該列的 group_name, perspective: { kind: 'neutral' } }`（match-history 在 US3 會改成 mine）。
  - `web/app/features/group-member-view/match-records/match-records.component.spec.ts`：以新輸入 `groupName` 組成 context。
  - `web/app/features/group-member-view/group-member-view.component.spec.ts`：把 `g.name` 傳給 `<app-match-records>`。
  - `web/app/features/member/my-groups/group-history/group-history.component.spec.ts`：用頁面資料的 `group_name`。

### Implementation for User Story 1

- [X] T012 [US1] 建立 `web/app/core/match-share-card/share-card-model.ts`，export `buildShareCardModel(detail, context)`：
  - 本 story 只實作中立路徑：勝方在前、徽章、暱稱、比分、時長、`fileName`（`formatDate(started_at, 'yyyyMMdd', 'en-US')`，不傳時區參數即為裝置時區）、altText。
  - `trend: null`、`highlights: []`、`averagePointSeconds: null` 先固定，由 US2 補上。
  - `perspective.kind === 'mine'` 在 US3 實作之前先當作 neutral 處理。
  - 不得注入任何 service，也不得呼叫翻譯。
- [X] T013 [P] [US1] 建立 `web/app/core/match-share-card/share-card-palette.ts`，export `SHARE_PALETTES: Record<ShareTheme, SharePalette>`，本 story 先填 `light`：背景 `#ffffff` 系、主要文字接近黑、A 隊色 `#b3335f`、B 隊色 `#35519e`（與 `web/styles/_tokens.scss` 的 `--color-team-a-bg`／`--color-team-b-bg` 相同）。`dark` 先指向 light，US5 再補上。
- [X] T014 [US1] 建立 `web/app/core/match-share-card/share-card-renderer.ts`，export `renderShareCard(ctx, model, palette, text, fonts)`，以及內部的 `truncateToWidth(ctx, text, maxWidth)`（二分搜尋截斷並加上「…」）。
  - 固定 1080×1350，左右邊距 72，**以 y 游標由上往下排版**，遇到 null 或空的元素就跳過，不保留空間（FR-009）。
  - 各區塊依序為：
    1. 頁首：團名（粗體 44px）、日期 · 第 N 輪（30px 次要文字）。
    2. 兩隊區塊：每隊左側為隊色直條加暱稱（雙打兩行，44px），右側為比分（`fonts.score`，160px，勝方加粗），比分下方為徽章膠囊（文字加底色，FR-029）。兩隊之間有分隔線。
    3. 走勢區（US2）。
    4. 亮點區（US2）。
    5. 頁尾：左側為時長 · 平均每分（30px），右側為 `brand`。
  - 日期以 `formatDate(model.startedAt, text('matchShareCard.dateFormat'), 'en-US')` 格式化：語言差異只來自語系檔的格式字串，locale **固定為 `'en-US'`**，不得傳入 `'zh-TW'`（本 app 未註冊 zh-TW locale data，傳入會拋錯，見 research Decision 8）。`renderShareCard` 的簽章不增加 locale 參數。
  - 畫面上 MUST NOT 出現 QR 碼或任何網址（FR-006）。
- [X] T015 [US1] 建立 `web/app/core/match-share-card/share-card-actions.service.ts`（`@Injectable({ providedIn: 'root' })`，類別 `ShareCardActions`）：
  - `rasterize(model, theme)`：`await document.fonts.ready`，從 `getComputedStyle(document.documentElement)` 讀取 `--font-family-base` 與 `--font-family-score`，建立 1080×1350 的 canvas（不乘 DPR），以 `TranslateService.instant` 包成 `ShareCardText`，呼叫 `renderShareCard`，最後 `toBlob('image/png')`。
  - `download(blob, fileName)`：object URL 加上臨時 `<a download>`，click 後立即 revoke。
  - 分享與複製在 US4 加入。
- [X] T016 [US1] 建立 `web/app/core/match-share-card/share-card-dialog/share-card-dialog.component.{ts,html,scss}`：
  - 元件為原生 `<dialog>`，以 `showModal()` 開啟；對外提供 `open(detail: MatchRecordDetailResponse, context: ShareCardContext)`。
  - 以 signals 管理 `model`、`theme`（預設 `'light'`）、`blob`、`objectUrl`、`status: 'generating' | 'ready' | 'error'`、`message`。
  - 預覽以 `<img>` 等比縮放到 dialog 寬度，`alt` 經 `TranslatePipe` 以 `model.altText` 產生（FR-028）。
  - 下載按鈕、關閉按鈕（沿用既有 `.dialog`／`.dialog__close` 樣式）。
  - 關閉時 revoke object URL，焦點回到觸發按鈕（FR-003）。
  - 所有文字走 `matchShareCard.*` key。
- [X] T017 [US1] 修改 `web/app/core/match-record-detail/match-record-detail-dialog.component.{ts,html,scss}`：
  - 新增 `readonly shareContext = input<ShareCardContext | null>(null)`。
  - 在 `basic-info` 區塊附近加上「分享圖卡」按鈕（`matchShareCard.openButton`），只在 `shareContext()` 不為 null 且 detail 已載入時顯示並可點擊（FR-001）。
  - 在模板中掛上 `<app-share-card-dialog #shareDialog />`，按鈕呼叫 `shareDialog.open(detail, shareContext)`。
  - 維持 dialog「不注入 API service」的原則。
- [X] T018 [P] [US1] 修改 `web/app/features/member/match-history/match-history.component.{ts,html}`：`openDetail` 改為接收被點開的整列（或以 matchId 從目前的列資料查出），設定 `shareContext` signal 為 `{ groupName: row.group_name, perspective: { kind: 'neutral' } }`，並綁定到 `<app-match-record-detail-dialog [shareContext]>`。改開另一場比賽時要換成新的 context。
- [X] T019 [P] [US1] 修改 `web/app/features/friends/friend-match-records/friend-match-records.component.{ts,html}`：做法同 T018，視角固定為 neutral。
- [X] T020 [P] [US1] 修改 `web/app/features/group-member-view/match-records/match-records.component.{ts,html}`，新增 `readonly groupName = input.required<string>()`，並組成 neutral context 綁定到 dialog；同時修改 `web/app/features/group-member-view/group-member-view.component.html`，傳入 `[groupName]="g.name"`。
- [X] T021 [P] [US1] 修改 `web/app/features/member/my-groups/group-history/group-history.component.{ts,html}`：以頁面資料的 `group_name` 組成 neutral context，綁定到 dialog。
- [X] T022 [US1] 在 `apps/web` 執行 `npx ng test --watch=false` 與 `npx ng lint`，確認 T007～T011 全部轉綠。

**Checkpoint**：MVP 可以單獨交付，四個入口都能產生並下載中立視角的圖卡。

---

## Phase 4: User Story 2 - 走勢縮圖、亮點與比賽節奏（Priority: P2）

**Goal**：逐分紀錄完整的比賽，圖卡加上走勢縮圖、依分制換算門檻挑出的 0～3 個亮點，以及平均每分耗時；紀錄不完整時整塊省略。

**Independent Test**：開啟一場紀錄完整、有逆轉或長連續得分的比賽，走勢形狀與詳情一致，亮點數字與詳情的統計區塊一致；partial 比賽沒有走勢、亮點與平均每分（quickstart 步驟 1、4、5、6）。

### Tests for User Story 2 ⚠️（先寫，確認會失敗）

- [X] T023 [P] [US2] 擴充 `api/tests/contract/test_group_match_record_detail.py`：回應含 `target_score`，型別為 int，等於該場 `Match.target_score`。
- [X] T024 [P] [US2] 擴充 `api/tests/contract/test_member_match_record_detail.py`：同上；另加一例，建立 11 分制的比賽並完賽，再把該團的 `target_score` 改為 21，`GET /members/me/match-records/{id}` 仍回傳 11（FR-012a）。
- [X] T025 [P] [US2] 擴充 `api/tests/unit/domains/member/test_personal_settings.py`：好友詳情端點 `GET /members/{member_id}/match-records/{match_id}` 的回應含正確的 `target_score`。
- [X] T026 [P] [US2] 新增 `web/app/core/match-share-card/share-card-highlights.spec.ts`（這是本功能最關鍵的測試，逐項對照 research Decision 7）：
  - `highlightThreshold`：21 分制為 3／5／10，15 分制為 3／3／7，11 分制為 3／3／5，T=5 時三者皆為下限 3。
  - 七個候選各有「剛好達標會出現」與「差 1 不出現」兩例，以 21 分制測試。
  - 11 分制時，連得 3 分會出現、連得 2 分不出現（下限 3）。
  - #2 `saved = 0` 不出現；#3 `deuce` 為 null 不出現。
  - #5：涵蓋率 79% 不出現、80% 出現；主動得分 50% 出現、49% 不出現；`ending_stats` 為 null（簡易模式）時略過，而且不影響其他候選（FR-014）；主角隊得 0 分時不出現。
  - #5 的 `percent` 等於 `formatPercent(winners / score)`（引用 `web/app/core/match-record-detail/ratio-format.ts`）。
  - #6 易手 3 次才出現。
  - 優先順序：7 個候選全部成立時只回傳 #1、#2、#3。
  - `record_completeness` 為 partial 或 none 時回傳 `[]`，即使 stats 不是 null（FR-011）。
  - 同樣的輸入呼叫兩次，結果深度相等（FR-015）。
  - 主角隊為落敗方時，#1、#3、#7 不出現，但 #2、#4、#5、#6 可以出現（FR-013）。
- [X] T027 [P] [US2] 擴充 `web/app/core/match-share-card/share-card-model.spec.ts`：
  - complete 時 `trend` 深度等於 `buildScoreTrendPoints(detail)`；partial 或 none 時 `trend === null`、`highlights` 為 `[]`、`averagePointSeconds === null`（FR-007、FR-009）。
  - `averagePointSeconds === tempo_stats.average_seconds`（FR-008、FR-010）。
  - 中立視角下 `pickHighlights` 以勝方為主角隊。
- [X] T028 [P] [US2] 擴充 `web/app/core/match-share-card/share-card-renderer.spec.ts`：
  - 有 `trend` 時畫出兩條折線，點數等於 trend 長度；沒有時不畫任何折線。
  - 每個 highlight 以 `matchShareCard.highlight.{kind}` 與正確參數畫出；`highlights` 為 `[]` 時亮點區完全不畫，頁尾 y 座標往上移（與有亮點時相比）。
  - `averagePointSeconds` 為 null 時不畫 `avgPerPoint`。

### Implementation for User Story 2

- [X] T029 [US2] 在 `api/app/domains/group/schemas.py` 的 `MatchRecordDetailResponse` 加上 `target_score: int`，並附註解，說明它是 `Match.target_score` 的快照投影（040 FR-012a），不是團目前的設定。
- [X] T030 [US2] 在 `api/app/domains/group/service.py` 的 `build_match_record_detail()` 回傳處加上 `target_score=match.target_score`，不增加任何查詢。執行 T023～T025 確認轉綠，並跑 `ruff check` 與 `mypy`。
- [X] T031 [P] [US2] 在 `web/app/core/api/group-member-view.models.ts` 的 `MatchRecordDetailResponse` 加上 `target_score: number`（附註解，同 T029），並在 `web/app/core/match-share-card/testing/detail-fixtures.ts` 補上預設值 21。搜尋 `web/app` 下所有手寫 `MatchRecordDetailResponse` 物件的既有 spec，逐一補上這個欄位，讓 `tsc` 通過。
- [X] T032 [US2] 建立 `web/app/core/match-share-card/share-card-highlights.ts`，export `highlightThreshold(targetScore, ratio)` 與 `pickHighlights(detail, protagonist)`：依 research Decision 7 的表格與順序逐項判斷，取前 3 個。#5 使用 `formatPercent`。record 不完整時直接回傳 `[]`。檔頭註解說明門檻比例與 spec FR-012 的對應。
- [X] T033 [US2] 更新 `web/app/core/match-share-card/share-card-model.ts`：complete 時填入 `trend = buildScoreTrendPoints(detail)`、`highlights = pickHighlights(detail, 主角隊)`、`averagePointSeconds = detail.tempo_stats?.average_seconds ?? null`；非 complete 時分別為 null、`[]`、null。
- [X] T034 [US2] 更新 `web/app/core/match-share-card/share-card-renderer.ts`：
  - **走勢區**：高約 220px，淡色背景。以 `ScoreTrendPoint` 的百分比座標換算到區塊內，用 A、B 隊的走勢線色各畫一條折線，並在起點與終點加上端點圓點。
  - **亮點區**：最多 3 列膠囊，每列有圖示圓點與敘述文字（36px），敘述經 `text('matchShareCard.highlight.' + kind, params)` 取得，過長時截斷。
  - **頁尾**：補上 `avgPerPoint`。
  - 所有區塊沿用 y 游標，遇到空的就跳過。
- [X] T035 [US2] 在 `apps/web` 執行 `npx ng test --watch=false`、`npx ng lint`、`npx ng build`，確認 T026～T028 以及既有 spec 全部通過。

**Checkpoint**：US1 加上 US2 可以一起交付，圖卡有「精彩在哪」的內容。

---

## Phase 5: User Story 3 - 我方視角與中立視角（Priority: P2）

**Goal**：從「我的對戰紀錄」開啟時，我方在前，徽章為勝利或落敗，亮點以我方為主角隊；其他入口維持中立。

**Independent Test**：同一場比賽分別從「我的對戰紀錄」與「團內對戰紀錄」開啟圖卡，比較視角差異；再開一場我方落敗的比賽，確認亮點只描述我方（quickstart 步驟 1～3）。

### Tests for User Story 3 ⚠️（先寫，確認會失敗）

- [X] T036 [P] [US3] 擴充 `web/app/core/match-share-card/share-card-model.spec.ts`（mine 段落）：
  - `myTeam = 'B'` 且 B 落敗時：`teams[0].team === 'B'`、`badge === 'defeat'`，`teams[1].badge === null`，比分與暱稱的對應正確（FR-019）。
  - `myTeam` 獲勝時 `badge === 'victory'`。
  - `pickHighlights` 以 `myTeam` 為主角隊：我方落敗時會出現「化解賽末點」，但不會出現逆轉勝。
  - `fileName` 以我方分數在前。
  - 中立視角永遠不會出現 `victory` 或 `defeat`（FR-017）。
- [X] T037 [P] [US3] 修改 `web/app/features/member/match-history/match-history.component.spec.ts` 的 context 斷言：`won: true` 且 `winner_team: 'A'` 時為 `{ kind: 'mine', myTeam: 'A' }`；`won: false` 且 `winner_team: 'A'` 時為 `myTeam: 'B'`。
- [X] T038 [P] [US3] 擴充 `web/app/core/match-share-card/share-card-renderer.spec.ts`：`badge: 'victory'` 時畫出 `matchShareCard.badge.victory`，`'defeat'` 時畫出 `…badge.defeat`；徽章一律有文字，不只靠底色（FR-029）。

### Implementation for User Story 3

- [X] T039 [US3] 更新 `web/app/core/match-share-card/share-card-model.ts`，實作 mine 路徑：主角隊為 `myTeam`，`teams[0]` 為我方，徽章為 `victory` 或 `defeat`，對手為 null；`pickHighlights` 的主角隊改為 `myTeam`。mine 路徑沒有「無法判定我方」的情況，因為型別已保證 `myTeam` 存在；FR-018 的退回由呼叫端負責，見 T040。
- [X] T040 [US3] 修改 `web/app/features/member/match-history/match-history.component.ts`：context 改為 `{ kind: 'mine', myTeam: row.won ? row.winner_team : (row.winner_team === 'A' ? 'B' : 'A') }`。如果找不到被點開的那一列（理論上不會發生），改給 `{ kind: 'neutral' }`（FR-018），並加上註解。
- [X] T041 [US3] 確認 `web/app/core/match-share-card/share-card-renderer.ts` 的徽章繪製已支援三種文字，未支援就補上；我方視角的 `teams[0]` 區塊以較深的底色或加粗外框強調（FR-016）。執行 `npx ng test --watch=false`。

**Checkpoint**：視角規則與 clarify Q2 一致。

---

## Phase 6: User Story 4 - 直接分享到 LINE／IG（Priority: P3）

**Goal**：支援的裝置可以用系統分享選單分享圖片檔，桌機可以複製圖片；取消分享時不報錯。

**Independent Test**：HTTPS 環境的手機按「分享」選 LINE，收到的是圖片檔；桌機 localhost「複製圖片」後貼上；以 http 的 LAN 開啟時，複製按鈕隱藏（quickstart 步驟 10～12）。

### Tests for User Story 4 ⚠️（先寫，確認會失敗）

- [X] T042 [P] [US4] 新增 `web/app/core/match-share-card/share-card-actions.service.spec.ts`，以 `vi.stubGlobal` 或 `Object.defineProperty` 替換 `navigator`、`window` 的相關 API：
  - `canShareFiles` 只在 `navigator.canShare({ files })` 回傳 true 時為 true；API 不存在時為 false。
  - `share` 遇到 `DOMException('…', 'AbortError')` 時回傳 `'cancelled'`，其他錯誤會拋出。
  - `canCopyImage` 在 `isSecureContext` 為 false、`ClipboardItem` 不存在或 `clipboard.write` 不存在時為 false。
  - `copyImage` 以 `{ 'image/png': blob }` 呼叫 `clipboard.write`。
- [X] T043 [P] [US4] 擴充 `web/app/core/match-share-card/share-card-dialog/share-card-dialog.component.spec.ts`：
  - 「分享」只在 `canShareFiles` 為 true 時顯示；按下時以**已快取的 Blob** 包成的 File 同步呼叫 `share`，在呼叫之前沒有任何 await（research Decision 9，可用 spy 驗證按下當下 `rasterize` 沒有被再次呼叫）。
  - `share` 回傳 `'cancelled'` 時不顯示任何訊息（FR-023）。
  - `share` 拋錯時顯示 `shareError`，並提示可以改用下載。
  - 「複製圖片」只在 `canCopyImage` 為 true 時顯示，成功後顯示 `copied`，失敗時顯示 `copyError`（FR-022）。

### Implementation for User Story 4

- [X] T044 [US4] 在 `web/app/core/match-share-card/share-card-actions.service.ts` 加上 `canShareFiles(file)`、`share(file)`、`canCopyImage()`、`copyImage(blob)`，規格見 contracts/share-card-module.md §5。檔頭註解說明為什麼這裡使用 `navigator.share`，而 `web/app/core/line-share.ts` 刻意不用：LINE it! 只能分享網址，圖片檔只能透過 Web Share Level 2 送出。另外說明圖片複製沒有 `execCommand` 退路，這一點和 `web/app/core/clipboard.ts` 不同。
- [X] T045 [US4] 更新 `web/app/core/match-share-card/share-card-dialog/share-card-dialog.component.{ts,html}`：
  - Blob 產生後建立 `File([blob], model.fileName, { type: 'image/png' })` 並快取，同時算好 `canShare` 與 `canCopy` 兩個 signal。
  - 加上「分享」與「複製圖片」按鈕，按下時同步使用快取的 File 或 Blob。
  - 各種提示以 `role="status"` 區塊呈現。
  - 執行 `npx ng test --watch=false`。

**Checkpoint**：分享流程在不支援的環境下會自然降級為下載。

---

## Phase 7: User Story 5 - 亮色／暗色樣式（Priority: P3）

**Goal**：預覽中可以切換亮色與暗色，之後的輸出使用當下選取的配色，兩種配色的文字都清楚可讀。

**Independent Test**：切換成暗色後，預覽立即更新；下載、分享、複製的圖片都是暗色（quickstart 步驟 9）。

### Tests for User Story 5 ⚠️（先寫，確認會失敗）

- [X] T046 [P] [US5] 新增 `web/app/core/match-share-card/share-card-palette.spec.ts`：實作 WCAG 相對亮度與對比度計算，斷言 `light` 和 `dark` 兩組色盤中，主要文字、次要文字、徽章文字對各自背景的對比度都 ≥ 4.5，A 隊色與 B 隊色對背景的對比度 ≥ 3（圖形元素）（research Decision 10）。
- [X] T047 [P] [US5] 擴充 `web/app/core/match-share-card/share-card-dialog/share-card-dialog.component.spec.ts`：
  - 預設 `aria-pressed` 為 light。
  - 切到 dark 時以 `'dark'` 重新呼叫 `rasterize`，舊的 object URL 被 revoke，新的 Blob 取代快取。
  - 之後的「下載圖片」使用新的 Blob（FR-024）。
  - 重新開啟預覽時回到 light（Assumption：不記憶配色）。

### Implementation for User Story 5

- [X] T048 [US5] 在 `web/app/core/match-share-card/share-card-palette.ts` 補上 `dark` 色盤：深色背景（例如 `#121418`），提亮兩隊的隊色與走勢線色，讓 T046 通過。
- [X] T049 [US5] 在 `web/app/core/match-share-card/share-card-dialog/share-card-dialog.component.{ts,html,scss}` 加上亮色／暗色切換（兩顆 `aria-pressed` 按鈕，文字為 `themeLight`、`themeDark`）：切換時重新 rasterize 並替換 Blob 與 URL，產生期間暫時停用輸出按鈕。執行 `npx ng test --watch=false`。

**Checkpoint**：五個 story 全部完成。

---

## Phase 8: Polish & Cross-Cutting Concerns

- [ ] T050 [P] 後端：在 `apps/api` 執行 `ruff check .`、`mypy app`，以及 T023～T025 三個測試檔。
- [ ] T051 [P] 前端：在 `apps/web` 執行 `npx ng test --watch=false`、`npx ng lint`、`npx ng build`。已知 `admin-page.component.spec.ts` 的 NG04002 unhandled error 是既有問題，與本功能無關。
- [ ] T052 依 `specs/040-match-share-card/quickstart.md` 第 2 節做實際畫面驗收：worktree 後端開在 :8001，連 `rally_stats_test`；前端開在 :4300；以 `apps/api/scripts/seed_dashboard_demo.py` 建立示範資料；用 playwright-core 對步驟 1～9、13、14 截圖，並逐張檢查排版（特別是步驟 7 的長暱稱、步驟 4 的降級版面）。步驟 12（手機系統分享）需要 HTTPS 環境，無法在本機自動化，列為交付時請使用者驗證的項目。
  - **SC-001 量測**（`/speckit-analyze` G1）：在同一支 playwright 腳本中，以 CDP `Emulation.setCPUThrottlingRate({ rate: 4 })` 模擬一般手機，並設定 390×844 的 viewport。記錄從點擊「分享圖卡」到預覽 `<img>` 觸發 `load` 事件的時間，分別測一場雙打完整紀錄（有走勢與亮點）的比賽，以及一場 partial 紀錄的比賽，各跑 5 次取中位數。兩者都 MUST ≤ 2000 ms；超過時先檢查 `document.fonts.ready` 與 `toBlob` 各自的耗時再優化。把量測結果寫進交付報告。
- [ ] T053 在背景執行完整的後端測試套件（`python -m pytest -rf > <job tmp>/pytest-full.txt`，約 20 分鐘），確認沒有回歸。必須在同一回合內等它跑完，才能移除 worktree。
- [ ] T054 對照 spec.md 的 FR-001～FR-029（含 FR-006a、FR-012a、FR-017a）與 SC-001～SC-008，逐條確認都有對應的任務或測試；有遺漏就補上任務。

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup（Phase 1）**：沒有前置依賴。T002～T004 可以和 T001 同時進行（T002、T003 會 import T001 的型別，實作上建議 T001 先完成）。
- **Foundational（Phase 2）**：依賴 Setup；阻擋所有 story，因為 US1 與 US2 都會改詳情 dialog。
- **US1（Phase 3）**：依賴 Foundational。MVP。
- **US2（Phase 4）**：依賴 US1 的 model、renderer 骨架（T012、T014）。後端的 T023～T025、T029、T030 可以在 US1 期間提前平行進行。
- **US3（Phase 5）**：依賴 US1（T012、T018）；會用到 US2 的 `pickHighlights` 來驗證我方主角隊。若 US2 尚未完成，T036 關於亮點的斷言要等 US2 完成後再加。
- **US4（Phase 6）**：依賴 US1 的 actions service 與預覽 dialog（T015、T016），與 US2、US3 無關。
- **US5（Phase 7）**：依賴 US1 的 palette 與 dialog（T013、T016），與 US2～US4 無關。
- **Polish（Phase 8）**：依賴所有要交付的 story。

### User Story Dependencies

```text
Setup → Foundational → US1 ─┬─> US2 ──> US3
                            ├─> US4
                            └─> US5
（後端 T023–T025/T029/T030 可在 US1 期間平行）
```

### Within Each User Story

- 先寫測試並確認會失敗，再實作。
- model、highlights（純函式）→ renderer → actions service → dialog 元件 → 呼叫端串接。
- 每個 story 結束時跑一次 `ng test`，當作 checkpoint。

### Parallel Opportunities

- Phase 1：T002、T003、T004。
- US1 測試：T007～T011 全部可以平行；實作：T013 可與 T012 平行，T018～T021 四個呼叫端可以平行。
- US2 測試：T023～T028 全部可以平行（後端三個檔案、前端三個檔案）；T031 可與 T029、T030 平行。
- US3 測試：T036～T038；US4 測試：T042、T043；US5 測試：T046、T047。
- US4 與 US5 在 US1 完成後可以同時進行。

---

## Parallel Example: User Story 1

```bash
# 測試先行（全部為不同檔案）：
Task: "T007 share-card-model.spec.ts 基本段落"
Task: "T008 share-card-renderer.spec.ts 基本段落"
Task: "T009 share-card-dialog.component.spec.ts"
Task: "T010 match-record-detail-dialog.component.spec.ts 擴充"
Task: "T011 四個呼叫端 spec 擴充"

# model 與 palette 完成後，四個呼叫端串接可以平行：
Task: "T018 match-history"
Task: "T019 friend-match-records"
Task: "T020 group-member-view/match-records"
Task: "T021 my-groups/group-history"
```

## Parallel Example: User Story 2

```bash
Task: "T023 api/tests/contract/test_group_match_record_detail.py"
Task: "T024 api/tests/contract/test_member_match_record_detail.py"
Task: "T025 api/tests/unit/domains/member/test_personal_settings.py"
Task: "T026 share-card-highlights.spec.ts"
Task: "T027 share-card-model.spec.ts 擴充"
Task: "T028 share-card-renderer.spec.ts 擴充"
```

---

## Implementation Strategy

### MVP First（只做 User Story 1）

1. Phase 1 Setup → Phase 2 Foundational（走勢抽取，確認既有 spec 全綠）。
2. Phase 3 US1：中立視角的基本圖卡加下載，四個入口都有按鈕。
3. **停下來驗證**：quickstart 步驟 3、8，確認可以單獨交付。

### Incremental Delivery

1. US1 → 可以分享比分圖（MVP）。
2. US2 → 加上走勢與亮點，是讓人想分享的關鍵；也是唯一需要動後端的 story。
3. US3 → 我的戰報視角。
4. US4 → 手機一鍵分享或複製圖片。
5. US5 → 暗色配色。
6. Polish → 實際畫面驗收與完整回歸測試。

每一步都可以推到 `feature/match-share-card`，讓使用者在主 checkout 拉下來測試。

---

## Notes

- [P] 任務 = 不同檔案、沒有未完成的依賴。
- [Story] 標籤用來追溯到 spec 的 user story。
- 不新增任何第三方套件、migration 或端點（plan.md Constraints）。
- 所有顯示文字只能使用 T004 建立的 `matchShareCard.*` key；實作過程中若需要新增 key，兩份語系檔要同時補上，T004 的一致性測試會擋下漏加的情況。
- 每完成一個 story 就 commit 一次，commit 訊息使用繁體中文，並描述使用者看得到的變化。
