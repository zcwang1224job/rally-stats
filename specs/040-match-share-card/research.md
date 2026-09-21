# Research: 單場比賽分享圖卡（040-match-share-card）

**Date**: 2026-09-21 | **Spec**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

本文件記錄 Phase 0 的每一項技術決策。查證依據為 `ut`（551a086）之上的現有程式碼；引用路徑皆為 repo 相對路徑。

---

## Decision 1：圖卡在前端以 Canvas 2D 自行繪製

**Decision**：在瀏覽器以 `<canvas>`（1080×1350，固定像素、不乘 DPR）呼叫 Canvas 2D API 逐項繪製，最後以 `canvas.toBlob('image/png')` 產出圖片。**不新增任何第三方套件。**

**Rationale**：
- 輸出尺寸是規格（FR-004／SC-006），Canvas 以固定像素畫布作畫，與裝置 DPR、視窗寬度、使用者縮放完全脫鉤；DOM 截圖類做法的輸出會隨這些因素漂移。
- 圖卡內容全部是「文字＋幾何圖形＋一條折線」，Canvas 2D 原生即可完成，不需要 CSS 排版能力。
- 專案慣例是不為單一功能引入相依套件（033 起多份 plan 皆以此為 PASS 依據）。
- 繪製流程可以拆成「純資料轉換（可窮舉測試）→ 薄繪製層」，符合 Constitution II。

**Alternatives considered**：
- **html2canvas／html-to-image（DOM 截圖）**：開發快（直接用 CSS 排版），但 iOS Safari 對 SVG `foreignObject` 與字型嵌入的支援不穩，常見空白字或字型跑掉；輸出尺寸受 DPR 影響；多一個相依套件。拒絕。
- **後端產圖（Pillow）**：輸出最穩定，也能順便做 og:image，但後端目前沒有影像相依套件，Docker 映像需額外塞 CJK 字型（Noto 系列 10MB 以上），且違反 spec 的「不新增端點」。本期沒有公開比賽頁，og:image 用不到。拒絕，留待日後公開頁功能再評估。
- **SVG 字串 → `<img>` → canvas**：可用宣告式寫法排版，但 SVG 內的文字寬度無法預先量測，暱稱截斷（Edge Case「超長暱稱」、SC-005）難以做對。拒絕。

---

## Decision 2：三層拆分──模型轉換、版面量測、繪製

**Decision**：前端新增 `apps/web/src/app/core/match-share-card/`，分成三層：

1. `share-card-model.ts`（純函式）：`buildShareCardModel(detail, context) → ShareCardModel`。負責視角、隊伍排序、勝負標示、時長、平均每分耗時、走勢點，以及呼叫亮點挑選。**不碰 DOM、不碰翻譯**，輸出只含資料與翻譯 key＋參數。
2. `share-card-highlights.ts`（純函式）：`pickHighlights(detail, protagonist, perspective) → Highlight[]`，實作 FR-012～FR-015。
3. `share-card-renderer.ts`：`renderShareCard(ctx, model, palette, translate)`。只負責量測文字（`ctx.measureText`）、截斷、排版與繪製。

**Rationale**：規格中所有「對不對」的判定（亮點門檻、視角、降級、數字一致性）都落在第 1、2 層，可以用 Vitest 窮舉，不需要 canvas。第 3 層只剩「畫在哪裡」，以一個記錄呼叫的假 context 做煙霧測試即可。

**Alternatives considered**：把亮點規則放進後端，由 API 回傳挑好的亮點。規則屬於呈現邏輯（挑哪幾個、怎麼措辭、依視角而異），而且需要知道入口視角，後端並不知道；放後端只會讓 API 多一個呈現用欄位。拒絕。

---

## Decision 3：測試環境沒有 canvas，繪製層以假 context 測試

**Decision**：Vitest 測試環境（Angular `@angular/build:unit-test`＋jsdom）的 `HTMLCanvasElement.getContext()` 會回傳 `null`。因此：
- 第 1、2 層以純資料窮舉測試（主要覆蓋面）。
- 第 3 層以 `RecordingContext`（實作 renderer 用到的 `CanvasRenderingContext2D` 子集，記錄 `fillText` 內容，`measureText` 以「字元數 × 固定寬」模擬）測試：該畫的文字有畫、被省略的元素（走勢、亮點、平均每分耗時）沒畫、長暱稱經過截斷、寬度不超過邊界。
- 預覽元件測試以注入的 `ShareCardRasterizer` 替身產生假 Blob，驗證分享、複製、下載按鈕的顯示條件與錯誤處理。

**Alternatives considered**：安裝 `canvas`（node-canvas）讓 jsdom 真的能畫圖。這是原生編譯套件，會拖慢 CI、增加跨平台安裝問題。拒絕。像素級比對改以 quickstart.md 的人工驗收步驟處理。

---

## Decision 4：比分走勢點抽成共用純函式

**Decision**：把 `MatchRecordDetailDialogComponent.chartPoints()` 目前的計算（完整紀錄時補 (0, 0:0) 原點、partial 不補、`-1` 事件照常成為一個點）抽成 `core/match-record-detail/score-trend.ts` 的 `buildScoreTrendPoints(detail)`，由詳情 dialog 與分享圖卡共用。

**Rationale**：FR-007 要求圖卡走勢「形狀與詳情趨勢圖一致」。最可靠的保證是同一份計算，而不是兩份需要各自維護、還得靠測試對齊的程式碼。

**Alternatives considered**：圖卡自行重算走勢點。兩處規則（原點、partial 處理）日後可能分歧。拒絕。這項抽取屬於重構，詳情 dialog 既有的 spec 會作為行為不變的保險。

---

## Decision 5：視角與團名由呼叫端傳入詳情 dialog

**Decision**：`MatchRecordDetailDialogComponent` 新增一個選用輸入 `shareContext: ShareCardContext | null`：

```ts
type ShareCardContext = {
  groupName: string;
  perspective: { kind: 'neutral' } | { kind: 'mine'; myTeam: 'A' | 'B' };
};
```

- 會員個人跨團對戰紀錄（`features/member/match-history`）：從被點開的那一列 `MemberMatchRecordSummary` 推出 `myTeam = won ? winner_team : 對面`，團名取 `group_name`。
- 好友的對戰紀錄（`features/friends/friend-match-records`）：列上有 `group_name`，視角固定中立。
- 某團對戰紀錄（`features/group-member-view/match-records`）：團名由父元件 `group-member-view`（已有 `g.name`）以新輸入 `groupName` 傳入，視角中立。
- 「我的團」團歷史戰績（`features/member/my-groups/group-history`）：頁面資料已有 `group_name`，視角中立。
- `shareContext` 為 `null`（呼叫端尚未提供）時，「分享圖卡」按鈕不顯示。

四個呼叫端的 `openDetail(matchId)` 改為同時記住被點開那一列的資料（或於開啟時組好 context）。

**Rationale**：
- 詳情 dialog 在 016 的設計就是「純呈現，不注入任何 API service」，由呼叫端餵資料。視角與團名同樣是呼叫端才知道的上下文，沿用同一模式。
- 用列上的 `won`＋`winner_team` 推 `myTeam`，不必比對 `participant.member_id` 與登入者 id，也避開 026 註記的「member_id 只在部分 builder 投影」。

**Alternatives considered**：
- 在 dialog 裡注入 `AuthService`，以登入會員 id 比對 `team_a`／`team_b` 的 `member_id` 來判斷我方。違反 clarify Q2（視角只看入口），也破壞 dialog 的純呈現設計。拒絕。
- 在 API 回傳 `group_name`。需要改兩個後端 builder，而四個呼叫端手上其實都已經有團名。拒絕。

---

## Decision 6：新增 `target_score` 到比賽詳情回應

**Decision**：`MatchRecordDetailResponse`（`apps/api/app/domains/group/schemas.py`）新增必填欄位 `target_score: int`，值取自 `Match.target_score`（比賽建立時快照的分制，`apps/api/app/domains/schedule/models.py`）。由唯一的組裝入口 `build_match_record_detail()`（`apps/api/app/domains/group/service.py`）填入，因此三個詳情端點自動全部帶上：

- `GET /groups/{group_id}/match-records/{match_id}`（某團對戰紀錄，現役成員／訪客）
- `GET /members/me/match-records/{match_id}`（我的對戰紀錄，以及「我的團」團歷史戰績：兩者都經 `AuthService.getMatchRecordDetail()`，走「曾是成員」的授權）
- `GET /members/{member_id}/match-records/{match_id}`（好友的對戰紀錄）

**Rationale**：clarify Q3 決定門檻依分制換算（FR-012a）。`Match.target_score` 是 Constitution III 要求的快照欄位，團設定事後修改不會影響它，剛好符合 FR-012a 的「MUST NOT 使用團目前的設定」。這個欄位只是既有、非敏感資料的唯讀投影，不改授權。

**Alternatives considered**：
- 由 `clutch_stats.endgame_from` 反推（`target - 3`）。只有紀錄完整且分制夠大時才有值，語意也不直接，太脆弱。拒絕。
- 做成選填（`int | None`）。每一場 completed 比賽都有非空的 `target_score`（欄位為 `nullable=False`），選填只會讓前端多處理一個不存在的狀態。拒絕。

---

## Decision 7：亮點挑選的資料對應

**Decision**：主角隊 `P`：中立視角為 `winner_team`，我方視角為 `myTeam`。門檻 `th(r) = max(3, floor(T × r))`，T = `target_score`。候選依優先順序：

| # | 候選 | 條件（全部來自既有欄位） | 顯示數字 |
|---|---|---|---|
| 1 | 逆轉勝 | `clutch_stats.comeback` 非 null、`comeback.winner == P`、`max_deficit ≥ th(0.15)` | `max_deficit` |
| 2 | 化解賽末點 | `clutch_stats.match_points[P].saved ≥ 1`（`saved` 為 P 化解的**對手**賽末點數，見 `group/match_stats.py`） | `saved` |
| 3 | 延長賽勝出 | `clutch_stats.deuce` 非 null、`winner_team == P` | 最終比分（P 在前） |
| 4 | 連續得分 | `momentum_stats.longest_runs[P].length ≥ th(0.25)` | `length` |
| 5 | 主動得分率 | `ending_stats` 非 null、`recorded_points / total_points ≥ 0.8`、`P 的分數 > 0`、`teams[P].winners / P 的分數 ≥ 0.5` | `formatPercent(winners / P 的分數)` |
| 6 | 拉鋸戰 | `momentum_stats.lead_changes.length ≥ 3` | 次數 |
| 7 | 大比分勝出 | `winner_team == P`、`|score_a − score_b| ≥ th(0.5)` | 分差 |

- 我方落敗時，#1、#3、#7 的條件本身就要求 `P` 獲勝，自然不成立，FR-013 不需要特例。
- 逐分紀錄不完整時，上述 stats 全部是 null 或 []（033 FR-004 的既有保證），所有候選自然不成立；模型層仍以 `record_completeness !== 'complete'` 直接回傳 `[]`，作為明確的防線（FR-011）。
- 取前 3 個，順序固定，所以結果是確定性的（FR-015）。
- #5 的百分比與詳情頁 035 區塊的「主動得分 N 分／總得分」同源，用同一個 `formatPercent`，確保四捨五入一致（FR-010）。

**Rationale**：每一項都直接讀取詳情已經顯示的欄位，不重新推導（FR-010），規則本身也一眼就能對照 spec。

---

## Decision 8：日期與時長的呈現

**Decision**：
- 日期：以 `started_at` 經 Angular `formatDate(startedAt, 格式, 'en-US')` 依**裝置時區**格式化（不傳時區參數即為裝置時區），與既有 `shared/match-card` 以 `date` pipe 顯示比賽時間的慣例一致。**語言差異由格式字串決定，不由 locale 決定**：格式字串放在語系 key `matchShareCard.dateFormat`，zh-TW 為 `yyyy/M/d`，en 為 `MMM d, yyyy`。locale 一律固定為 `'en-US'`。
  - **為什麼不傳 `'zh-TW'` 當 locale**（`/speckit-analyze` U1）：本 app 從未呼叫 `registerLocaleData`，`LOCALE_ID` 維持 Angular 預設的 `en-US`。`formatDate(…, 'zh-TW')` 會在執行時拋出「Missing locale data」，中文介面產圖就會失敗。既有畫面（`match-card` 的 `'M/d HH:mm'`、`dashboard-trend-chart` 注入的 `LOCALE_ID`）都用純數字格式或預設 locale 避開這個問題，圖卡沿用同一做法。為了一張圖卡而註冊 zh-TW locale data 並改動全站 `LOCALE_ID`，影響範圍過大，所以不採用。
  - zh-TW 的格式 `yyyy/M/d` 只含數字，`en-US` locale 也能正確輸出；en 的 `MMM` 月份縮寫本來就是 `en-US` 的資料。
- 比賽時長：`ended_at − started_at`（UTC 相減），格式為「N 分 N 秒」，超過 1 小時為「N 小時 N 分」。任一時間為 null 時省略（Edge Case）。
- 平均每分耗時：直接使用 `tempo_stats.average_seconds`（與詳情 033 區塊同源），null 時省略。

**Rationale**：Constitution VIII 把時間分成兩類。`started_at` 是「系統自動記錄的絕對時間戳」，不是「活動時間區間」（場地時段），所以不受「一律用 `default_timezone`」的限制。而且全站既有的比賽時間顯示都用裝置時區，圖卡如果改用別的時區，同一場比賽在列表和圖卡上會顯示不同日期。

---

## Decision 9：分享、複製、下載的瀏覽器能力判斷

**Decision**：
- **預先產生 Blob**：預覽開啟、切換配色後立刻 `toBlob()` 並快取。按鈕按下時直接使用快取的 Blob，確保 `navigator.share()`／`clipboard.write()` 是在使用者手勢（transient activation）內同步發起；iOS Safari 對手勢內 await 很嚴格。
- **分享**：`navigator.canShare?.({ files: [file] })` 為 true 才顯示按鈕（FR-021）。`share()` 拋出 `AbortError` 視為使用者取消，不顯示錯誤（FR-023），其他錯誤顯示提示並建議下載。
- **複製圖片**：`window.isSecureContext && 'ClipboardItem' in window && navigator.clipboard?.write` 皆成立才顯示（FR-022）。圖片複製沒有 `execCommand` 退路，這一點和既有的 `core/clipboard.ts`（純文字，有退路）不同，所以在 LAN 上以 http 測試時按鈕會隱藏，這是預期行為。
- **下載**：以 object URL＋`<a download>` 觸發。檔名為 `rally-stats-YYYYMMDD-{我方或勝方分數}-{對方分數}.png`（FR-020）。object URL 在預覽關閉時 `revokeObjectURL`。
- 這三個操作包成可注入的 `ShareCardActions` service，讓預覽元件測試可以替換。

**Rationale**：`core/line-share.ts` 的註解刻意不用 `navigator.share`，但那是針對「分享連結」：LINE it! 只能送網址，不能送圖片檔。圖片要進 LINE／IG，唯一的網頁途徑就是 Web Share Level 2 的 files 分享，兩者並不矛盾。實作時要在程式碼註解中寫明這個差異。

---

## Decision 10：配色、字型與無障礙

**Decision**：
- 圖卡自帶兩組色盤（`share-card-palette.ts`）：亮色以站內既有 token 為基底（隊伍色 `--color-team-a-bg #b3335f`／`--color-team-b-bg #35519e`）；暗色使用深底，並提亮兩隊色以維持對比。所有文字與背景組合的對比度 ≥ 4.5:1，作為實作時的檢查項。站內目前沒有暗色主題，圖卡的暗色只屬於圖卡本身。
- 勝方標示＝文字徽章（中立：「勝」／「WIN」；我方：「勝利／落敗」、「Victory／Defeat」）＋字重加粗，不只靠顏色（FR-029）。
- 字型：從 `getComputedStyle(document.documentElement)` 讀取 `--font-family-base`／`--font-family-score` 的值，套用到 `ctx.font`；繪製前 `await document.fonts.ready`。站內沒有自帶 web font，一律使用系統字型，所以沒有字型載入時序的問題。
- 預覽以 `<img [src]=objectUrl [alt]=...>` 呈現產出的 PNG，而不是直接顯示 canvas。這樣預覽的內容就是實際產出的檔案（SC-006），alt 文字由模型組成（「A 隊 王小明、陳大華 21 比 17 勝 B 隊 …」）（FR-028）。

---

## Decision 11：預覽的 UI 型態

**Decision**：新增 `ShareCardDialogComponent`，一個原生 `<dialog>`，以 `showModal()` 疊在比賽詳情 dialog 之上。原生 dialog 的 top layer 支援堆疊，關閉後焦點回到觸發按鈕，詳情 dialog 維持開啟（FR-003）。產生失敗時在預覽內顯示錯誤，不影響詳情（Edge Case）。

**Alternatives considered**：直接在詳情 dialog 內切換成「圖卡模式」。會讓詳情 dialog 多一套狀態機，關閉預覽時也得還原捲動位置。拒絕。

---

## Decision 12：語系

**Decision**：新增 `matchShareCard.*` 命名空間，包括按鈕、預覽標題、配色切換、分享／複製／下載、各種提示、七種亮點敘述（含 ICU 風格參數）、勝負徽章、時長格式、alt 文字模板，同時放進 `zh-TW.json` 與 `en.json`。canvas 上的文字在繪製前以 `TranslateService.instant()` 取得，所以切換語言後重新開啟預覽即為新語言（Edge Case「語言切換」）。語系檔兩邊的 key 集合必須相同，這一點要列為測試項。
