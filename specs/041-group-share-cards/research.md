# Research: 團分享圖卡與導流頁尾（041-group-share-cards）

**Plan**: [plan.md](./plan.md) | **Spec**: [spec.md](./spec.md)

040 的 research Decision 1–12（Canvas 產圖、三層純函式、`RecordingContext`、色盤與對比、原生 `<dialog>`、分享須在手勢內發起、日期樣式用語系字串）全部沿用，這裡不重述；以下只記錄本功能新增或改變的決定。Technical Context 中沒有遺留的 NEEDS CLARIFICATION。

---

## Decision 1：把 040 模組拆成「共用層＋兩個圖卡模組」，040 對外介面不變

**Decision**：新增 `core/share-card/` 放與圖卡種類無關的東西；`core/match-share-card/` 與新的 `core/group-share-card/` 都只依賴它。`ShareCardDialogComponent.open(detail, context)` 保留為 040 的門面，內部改為建立一個 `ShareCardOption` 後交給共用的預覽外殼，因此比賽詳情 dialog 與四個呼叫端零修改。`share-card.models.ts` 對搬走的共用型別做 re-export，既有匯入路徑不必改。

**Rationale**：040 的 dialog 直接吃 `MatchRecordDetailResponse`、`rasterize()` 直接呼叫 `renderShareCard()`、`drawFooter()` 是 renderer 的私有函式——三處都把「比賽」寫死。第二種圖卡出現的當下就是抽共用層的正確時機（不是更早，也不能更晚）：再複製一份 dialog 與 actions，會讓分享／複製／下載的平台相容處理（iOS 手勢限制、Safari 的 revoke 延遲）分岔成兩份。保留門面則把 040 的回歸風險壓到最低（FR-022）。

**Alternatives considered**：
- *新圖卡直接加進 `match-share-card/`*：模組名稱與型別（`ShareCardModel` 綁比賽）都會變成謊言，第二期再加獎項卡時更難拆。
- *讓四個呼叫端改用新外殼*：沒有使用者價值，只增加回歸面。

## Decision 2：預覽外殼以「選項清單」為輸入，圖卡種類以 `draw(ctx, env)` 封裝

**Decision**：外殼的輸入是 `ShareCardOption[]`（`source`、`labelKey`、`fileName`、`altText`、`draw`）。`ShareCardActions.rasterize(option, theme)` 負責準備 `env`（色盤、翻譯函式、字型、`PromoFooter`）後呼叫 `option.draw(ctx, env)`。只有一個選項時不顯示種類切換（FR-003）。

**Rationale**：外殼不需要認識任何圖卡的模型，新增種類（第二期的獎項卡）只是多回傳一個選項。`draw` 仍是純函式（輸入 canvas 介面與 env），可用 `RecordingContext` 測試；外殼用替身 `ShareCardActions` 測試，兩邊都不需要真的 canvas。頁尾所需的 QR 由 actions 準備好放進 `env`，renderer 不碰非同步與 DOM。

**Alternatives considered**：
- *外殼接受可辨識聯集的 model，再 switch 到對應 renderer*：共用層會反向依賴兩個圖卡模組，違反憲章 VI。
- *每種圖卡一個 dialog 元件*：種類切換變成 dialog 之間的切換，配色狀態無法自然保留（FR-004）。

## Decision 3：兩張新圖卡的規則全部放在 `build*Model()` 純函式

**Decision**：`buildLeaderboardCardModel()` 與 `buildMyStatsCardModel()` 回傳模型或 `null`（不可用）；`availableGroupCards()` 依固定順序組出選項。規則：
- 排行榜：先濾掉 `total_matches = 0`，**不重新排序**，取前 6 列；前 3 **列**為頒獎台樣式；本人有出賽且不在前 6 列時另附 `selfRow`；`playerCount` 為濾後列數；不讀 `current_status`。
- 名次數字一律用 `rank` 原值。獎牌圖示依「名次 ≤ 3」決定，頒獎台樣式依「列的位置」決定——並列（1、1、3 或 1、2、3、3）時兩者各自正確，且不需要前端判斷並列。
- 我的成績：`total_matches = 0` → `null`；勝率用 `formatPercent`；名次與人數取自 `is_self` 列；走勢需 ≥ 2 輪；對手取 `opponent_records` 前 3 筆且順序不變。

**Rationale**：憲章 X 與 FR-008／FR-016 要求前端不得重算名次或重新推導統計。上述規則只有「過濾、切片、找出 `is_self`」，都是呈現層的選取。已對照伺服器實作確認前提成立：`build_group_final_standings()` 回傳已依標準競賽名次排序、且涵蓋 0 場者；`matchups.py` 的對手戰績依交手場數排序。把規則集中在純函式，才能在 spec 裡窮舉 SC-003 列出的 8 種狀況。

**Alternatives considered**：
- *依 `total_wins` 自行排序或自行編名次*：直接違反憲章 X，並列規則也會與頁面不一致。
- *並列跨越第 6 列時全部顯示*：列數不固定，版面無法保證；規格 Edge Cases 已定為「依既有順序取前 6」。
- *在前端從對手戰績挑「最難纏對手」*：屬於重新推導，且低樣本保護（036 的 `low_sample`）在這份資料裡沒有；已與需求方確認延到第二期由伺服器提供。

## Decision 4：QR 碼用 `qrcode` 套件取模組矩陣，自己用 `fillRect` 畫

**Decision**：在 `ShareCardActions` 內以動態 `import('qrcode')` 取得 `create(url, { errorCorrectionLevel: 'M' })`，把結果轉成自家的 `QrMatrix { size, isDark(row, col) }` 交給 renderer；`drawPromoFooter()` 以 `fillRect` 逐模組繪製。`qrcode@1.5.4` 宣告為 `apps/web` 的直接相依，加 `@types/qrcode`（dev）。產生失敗時 `qr = null`，頁尾省略 QR、保留網址，圖卡照常產出。

**Rationale**：
- 已實測 `qrcode@1.5.4`（目前 `node_modules` 裡的版本）：`QRCode.create()` 回傳 `{ modules: { size, data: Uint8Array, get(row, col) }, version, … }`，不需要 DOM 或 canvas，正好是純資料。
- `angularx-qrcode` 只輸出 `<qrcode>` DOM 元素（內部是 canvas／img／svg）。要畫進圖卡就得先把元件掛到畫面上、等它非同步畫完、再 `drawImage`——多一層時序問題，也無法用 `RecordingContext` 驗證。
- 該套件本來就是 `angularx-qrcode@20.0.0` 鎖定的相依（同為 1.5.4），宣告為直接相依不會讓打包結果多一份；不宣告而直接 import 間接相依，會在對方升級時無預警壞掉。
- 動態 `import()`：團戰績頁與比賽詳情都不該為了一個可能不會被按的按鈕多載 25KB；載入時間計入 SC-001 的 2 秒。`qrcode` 是 CommonJS；`angular.json` 目前沒有 `allowedCommonJsDependencies` 清單，若 `ng build` 因應用程式碼直接 import 而出現 CommonJS 警告，就把 `qrcode` 加進該清單（build 必須維持零警告）。
- renderer 拿到的是 `QrMatrix`，維持純函式，測試可用手寫的小矩陣驗證「深色模組才畫、位置正確、畫在白色底板內」。

**Alternatives considered**：
- *自己實作 QR 編碼*：Reed–Solomon 與遮罩選擇不值得自己維護。
- *先用 `angularx-qrcode` 轉成 data URL 再 `drawImage`*：會依裝置像素比縮放、邊緣被平滑化，無法保證「每模組為整數像素」（見 Decision 5）。
- *改用其他 QR 套件*：新增執行期相依，違反 040 以來「不新增第三方套件」的方向，且沒有好處。

## Decision 5：QR 規格——容錯等級 M、每模組 6px、240×240 白色底板、`ref` 值盡量短

**Decision**：
- 容錯等級 **M**；每模組像素取滿足 `(模組數 + 4) × px ≤ 240` 的**最大偶數**，下限 4px，低於下限則不畫 QR。一般網址（≤ 62 位元組）為 version 4＝33 模組 → 6px → QR 本體 198px，置中於 240×240 的白色圓角底板。
- 兩種配色一律「白底板＋近黑模組」，不隨色盤反相。
- `ref` 值定為 `card-rank`、`card-me`、`card-match`；網址形式 `<origin>/?ref=<值>`。可讀網址只顯示 `host`。

**Rationale（實測）**：以 `qrcode` 產生矩陣、依圖卡方式畫成點陣、用面積平均縮圖、加上振幅 ±28 的雜訊（模擬聊天軟體的壓縮）、嵌進深色背景，再用 jsQR 解碼，每組 10 次：

| 每模組 px | 縮 50%（→px） | 解碼 | 縮 40%（→px） | 解碼 |
|---|---|---|---|---|
| 4 | 2.0 | 10/10 | 1.6 | 3–10/10 |
| 5 | **2.5** | **8–10/10** | 2.0 | 10/10 |
| 6 | 3.0 | 10/10 | 2.4 | 7–10/10 |

關鍵不是「越大越好」，而是**縮圖後每模組要落在整數像素**：5px 縮一半變 2.5px，模組邊界落在像素中間產生灰階，解碼率反而低於 4px。FR-020／SC-006 明定的情境正是縮 50%，所以取偶數；6px 比 4px 多一層餘裕（縮 50% 後 3px，手機相機對著螢幕掃也夠大），而 4px 在縮 40% 時會掉到 3/10。等級 L 與 M 在這個網址長度下同為 version 4、模組數相同，M 沒有尺寸成本，故取 M。留白用 2 模組加上底板餘白即可：6px 時每邊實際留白 21px（3.5 模組），而且亮色配色下底板外也是淺色。

version 4-M 的位元組容量為 62：`https://`(8) ＋ host ＋ `/?ref=card-match`(16) → host 可到 38 字元，足夠一般網域；若用原先設想的 `card-leaderboard` 只剩 32。區網測試網址（如 `http://192.168.1.23:4200`）也在 version 4 內。超長網址會升到 version 5 以上（37＋模組）→ 4px；再長則不畫 QR。

在 LINE 與 iOS 相簿裡，實際最常見的路徑是「長按圖片 → 辨識 QR」，由圖片像素直接解碼，與上述實驗條件一致；真機掃描仍列入 quickstart 的人工驗收（SC-006）。

**Alternatives considered**：
- *依色盤反相（暗色卡用淺色模組）*：反相 QR 在部分掃描器無法辨識。
- *容錯等級 H*：升到 version 5–6，同樣底板下每模組只剩 4px，得不償失；螢幕上的圖片沒有實體污損問題。
- *QR 內放 logo*：需要更高容錯、更大尺寸，與有限的頁尾空間衝突。

## Decision 6：中段排版改為可收縮的 `stackBlocks()`，040 圖卡跟著套用

**Decision**：把 040 renderer 內「區塊堆疊並垂直置中」的邏輯抽成共用的 `stackBlocks()`，並加入收縮規則：放得下 → 行為與現在完全相同；放不下 → 依序 (1) 區塊間距 48→32，(2) 有 `minHeight` 的區塊由上而下收縮（040 的走勢圖 240→140；亮點列高 60→52；我的成績卡的走勢圖同理）。頁尾固定高度 240、下邊距 56。040 的「比賽時長 · 平均每分耗時」改為頁尾左上方的 `meta` 行。spec FR-022 同步放寬（見 plan.md「規格修訂」）。

**Rationale（實算）**：040 的中段目前是 y=230→1174，共 944px。最壞情況（雙打、我方視角有徽章、走勢圖、3 個亮點）＝隊伍 176＋48＋150，走勢 240，亮點 228，區塊間距 96 → **938px**，只剩 6px。新頁尾佔 240px：頁尾頂 1350−56−240＝1054、分隔線 1026、中段下緣約 996 → 可用 766px。套用收縮後最壞情況＝隊伍 176＋32＋150＝358、走勢 140、亮點 3×52＋48＝204、間距 64 → **766px**，剛好放下；實作時把中段上緣由 230 調到 210（標題區實際只到 y=166）再多 20px 餘裕。沒有走勢圖或亮點不足 3 個的圖卡（多數情況）完全不會觸發收縮，看起來與現在一樣。

「只在放不下時才收縮、且順序固定」讓結果可預測、可測試：renderer spec 以 `RecordingContext` 斷言最壞情況下沒有任何繪製的 y 超過中段下緣。

**Alternatives considered**：
- *QR 放在右上角標題區*：標題區只有約 158px 高，240px 的 QR 會壓到隊伍區的比分欄。
- *QR 縮到 4px／模組（底板約 164px）*：省 76px，仍需收縮，卻犧牲 Decision 5 的餘裕。
- *040 圖卡在內容全滿時丟掉第 3 個亮點*：改變了內容，比改變間距更違反 FR-022。
- *把圖卡加高*：4:5（1080×1350）是規格定的輸出，也是 IG／LINE 的最佳比例。

## Decision 7：活動日期在團戰績頁以一次非阻塞的 `getMyGroups()` 取得

**Decision**：`GroupHistoryComponent` 初始化時，除了既有的 `getMemberGroupHistory()`，另外發一次 `getMyGroups()`，從中找出該團的 `created_at` 存成 signal；失敗或找不到就是 `null`，圖卡省略日期（規格 Edge Cases）。這個請求不影響頁面既有的載入與錯誤狀態。日期格式沿用 040：以語系檔的樣式字串呼叫 `formatDate`，時區為裝置時區。

**Rationale**：`MemberGroupHistoryResponse` 沒有任何日期欄位，而規格明定本期不改後端。`GET /members/me/groups` 是會員已有權限的既有端點，回應輕量。初始化時就取，開啟預覽時不必再等（SC-001）。

**Alternatives considered**：
- *在 history 回應加 `created_at`*：最乾淨，但屬於後端變動；第二期新增獎項端點時一併處理，屆時移除這次多出來的請求。
- *由團清單頁用路由 state 傳入*：直接開啟網址或重新整理時會遺失，仍需後備請求，兩條路徑反而更複雜。
- *用對戰紀錄第一頁的 `started_at`*：會隨分頁與篩選改變，違反「篩選不影響圖卡」。

## Decision 8：系統分享只送圖片檔，不附 `title`／`text`／`url`

**Decision**：`navigator.share({ files: [png] })`，與 040 現行行為相同。FR-023 的「SHOULD 附上文字與網址」在本期**不啟用**，走該條的但書（會導致不送圖片時 MUST 只分享圖片）。導流完全由圖上的 QR 與可讀網址負責。

**Rationale**（以瀏覽器原始碼與公開回報為據）：
- **iOS**（WebKit `WKShareSheet.mm`）：`text`、`url`、檔案會被拆成**多個分享項目，順序為文字 → 連結 → 檔案**，圖片排最後。已有回報：Facebook、LinkedIn 只收到網址；WhatsApp 在帶 `title` 時只送出文字、沒有圖片；MDN 的 issue 也記載「iOS 上只有在唯一屬性是 `files` 時才可靠」。
- **Android**（Chromium `ShareHelper`）：單一 `ACTION_SEND`，檔案固定在 `EXTRA_STREAM`，附文字不會讓圖片消失；但文字是否被目標 App 採用並不一致（Instagram 不讀 `EXTRA_TEXT`），收益很小。
- **LINE 與 Instagram（本功能的主要目標）在兩個平台上都找不到任何一手測試**。硬條件是「圖片一定要送到」，在沒有證據的情況下不能拿主要管道去賭。
- `navigator.canShare()` 只反映瀏覽器支援與否，無法預知目標 App 會丟掉哪一部分，所以也無法用特性偵測來決定。

**後續**（不在本期任務內）：真機驗證 iOS 17+／Android 上 LINE、Instagram（限動／貼文／私訊）對 `{ files, text }` 的行為；若確認安全，可只在 Android 啟用「`files` ＋把網址寫在 `text` 內」。另一個低風險做法是分享前把文字與網址複製到剪貼簿，但會覆蓋使用者的剪貼簿，本期不做。

**Alternatives considered**：
- *依平台分流（Android 附文字、iOS 不附）*：多一條只能靠真機驗證的路徑，而收益（部分 App 多一行說明文字）不足以支撐；留待後續。
- *三者都附、讓目標 App 自行取用*：在 iOS 上有實際丟圖的回報，直接違反 FR-023。

## Decision 9：首頁做成靜態介紹頁；`ref` 參數不讀取

**Decision**：`HomeComponent` 擴充為：系統名稱、標語（與圖卡頁尾共用同一個語系 key）、3 項功能重點（計分與即時計分板、排點輪轉、個人與團戰績）、主要行動按鈕。未登入 → 主要按鈕到 `/auth/register`、次要到 `/auth/login`；已登入 → 主要按鈕到 `/member`。元件**不讀取** `ref` 參數——「忽略」就是最安全的處理（FR-025）。

**Rationale**：目前首頁只有 `<h1>Rally Stats</h1>`，QR 指過去等於撲空（spec US4）。系統沒有任何流量分析工具，`ref` 在本期的唯一作用是出現在伺服器／CDN 的存取紀錄裡，供日後回溯；前端不需要、也不應該對它做任何事。登入狀態沿用 `AuthService` 既有的 signal，不新增守衛或轉址，因此其他不需登入的入口（`/join`、`/guest-access`、`/scoreboard`、`/control`）不受影響（FR-026）。

**標語初版**：zh-TW「計分・排點・戰績，打球一站搞定」（15 字）；en「Score, schedule and track every game.」。放在 `shareCard.tagline`，頁尾與首頁共用，改一處兩邊同步。

**Alternatives considered**：
- *依 `ref` 顯示不同的歡迎文案*：沒有資料支持哪種文案有效，且多一個需要驗證輸入的面。
- *已登入者直接轉址到 `/member`*：改變既有行為（FR-026），而且從圖卡掃進來的既有會員看到介紹頁也無害。

## Decision 10：語系 key 的分工

**Decision**：`shareCard.*` 放共用文字（品牌、標語、掃碼提示、預覽外殼的按鈕與訊息、配色名稱、圖卡種類標籤）；`matchShareCard.*` 只留比賽專屬（徽章、亮點、輪次、時長、替代文字）；新增 `groupShareCard.*`（排行榜與我的成績的標題、標籤、「我」、人數、名次、對手、替代文字）與 `home.*`。040 已存在於 `matchShareCard.*` 的預覽按鈕 key 搬到 `shareCard.*`，並以既有的「兩份語系檔 key 一致」測試擴大涵蓋三個命名空間。

**Rationale**：共用外殼若繼續使用 `matchShareCard.share` 這類 key，名稱就與用途不符；搬移只是重新命名，由 key 一致性測試與外殼 spec 保護。

**Alternatives considered**：*共用外殼沿用 `matchShareCard.*`*：省一次搬移，但之後每個新圖卡都得去「比賽」的命名空間找按鈕文字。

## Decision 11：各輪走勢縮圖沿用頁面走勢圖的縱軸範圍

**Decision**：把 `LineChartComponent` 內計算縱軸範圍的邏輯（`rate` 類型：取資料最小／最大值、夾在 0–1、全平時上下各留 0.05）抽成 `shared/line-chart/line-chart-scale.ts` 的純函式，元件與 `buildMyStatsCardModel()` 共用。

**Rationale**：FR-015 要求縮圖形狀與頁面一致；頁面的走勢圖是自動範圍而非固定 0–100%，若圖卡自行用 0–1 畫，同一份資料會得到明顯較扁的線。做法與 040 Decision 4（抽出 `score-trend.ts`）相同。`LineChartComponent` 目前沒有自己的 spec，因此新函式的 spec 要先以現行行為寫成特性測試，再搬移程式；使用它的 `round-trend-chart` 既有 spec 不改動且維持全綠。

**Alternatives considered**：*圖卡固定用 0–100%*：實作最簡單，但與頁面形狀不一致，違反 FR-015。
