# Implementation Plan: 團分享圖卡與導流頁尾（Group Share Cards）

**Branch**: `feature/group-share-cards` | **Date**: 2026-09-21 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/041-group-share-cards/spec.md`，交叉比對以下檔案：`/apps/web/src/app/core/match-share-card/`（040 的整個模組，本功能要從中抽出共用層）、`/apps/web/src/app/features/member/my-groups/group-history/`（入口所在的團戰績頁）、`/apps/web/src/app/features/friends/friends.service.ts`（`getMemberGroupHistory()`、`getMyGroups()`）、`/apps/web/src/app/core/api/friend.models.ts` 與 `group-member-view.models.ts`（`MemberGroupHistoryResponse`、`FinalStandingRow`、`MemberGroupStatsResponse`、`MyGroupSummary`）、`/apps/web/src/app/shared/line-chart/` 與 `shared/round-trend-chart/`（各輪走勢圖的縱軸範圍邏輯）、`/apps/web/src/app/features/home/`（目前只有一行標題的首頁）、`/apps/api/app/domains/group/service.py` 的 `build_group_final_standings()` 與 `/apps/api/app/domains/member/matchups.py`（確認排名與對手戰績的伺服器端排序，僅閱讀、不修改）。

## Summary

在「我的團」的團戰績頁加上「分享圖卡」按鈕，開啟與 040 相同操作方式的預覽視窗，可切換兩種新圖卡：**團排行榜卡**（前 6 名＋會員本人）與**我的本團成績卡**。同時把**所有圖卡的頁尾**（含 040 已上線的單場比賽圖卡）換成導流頁尾：品牌字樣、標語、可讀網址、QR 碼，QR 指向不需登入的首頁並帶 `ref=card-<種類>`；並把首頁從一行標題擴充為最小可用的介紹頁（標語、3 項功能重點、行動按鈕）。

**後端零變動**：不新增端點、不改 schema、不需 migration。兩張新圖卡的資料全部來自團戰績頁已經取得的 `MemberGroupHistoryResponse`；活動日期來自既有的 `GET /members/me/groups`（`created_at`）。

前端分四塊（research Decision 1–3）：

1. **共用層 `core/share-card/`**：把 040 模組裡與「比賽」無關的部分搬出來——canvas 介面與尺寸常數、色盤、文字截斷與圓角繪製、`ShareCardActions`、預覽 dialog 外殼、測試用 `RecordingContext`——再新增三個純函式模組：區塊堆疊排版（`stackBlocks`，含可收縮規則）、導流頁尾（`drawPromoFooter`）、QR 矩陣（`toQrMatrix`／`qrLayout`）。
2. **`core/group-share-card/`**：兩張新圖卡各一組 `build*Model()` 純函式＋ renderer，加上 `availableGroupCards()` 決定當下哪些圖卡可用。所有「對不對」的判斷（只取前 6 列、排除 0 場球員、附上本人那一列、名次照伺服器、哪些區塊省略）都落在純函式上、測試先行。
3. **040 模組改為共用層的使用者**：`renderShareCard()` 改用共用的排版與頁尾；`ShareCardDialogComponent.open(detail, context)` 的對外介面不變，四個呼叫端與比賽詳情 dialog 完全不用改。
4. **首頁 `features/home/`**：標語、功能重點、行動按鈕；帶 `ref` 參數的網址照常顯示。

QR 碼以既有相依 `angularx-qrcode` 的底層套件 `qrcode@1.5.4` 產生模組矩陣，再用 `fillRect` 畫上 canvas（Decision 4）；該套件改宣告為直接相依並以動態 `import()` 載入，只有在開啟預覽時才下載。每模組 6px、容錯等級 M、白色底板 240×240——這組數字來自實測（Decision 5）：縮圖 50% 後每模組剛好 3px，加雜訊後解碼 10/10。

240px 的 QR 讓頁尾比 040 現在的頁尾高出約 150px，而 040 圖卡在「雙打＋走勢圖＋3 個亮點」全滿時中段只剩 6px 餘裕，所以**中段排版必須能收縮**（Decision 6）：區塊間距 48→32、走勢圖高度 240→最低 140、亮點列高 60→52，依固定順序只在放不下時才收縮。這代表 spec FR-022「040 版面不變」需要放寬為「內容、順序、挑選規則不變；間距與走勢圖高度可為容納頁尾而收縮」，已同步修訂 spec（見下方「規格修訂」）。

## 規格修訂（本次規劃帶出）

| 位置 | 原文 | 修訂 | 原因 |
|---|---|---|---|
| spec US2 驗收情境 5、FR-022、SC-007 | 040 圖卡「除頁尾外…版面 MUST 與上線前完全相同」 | 內容、區塊順序、亮點挑選、視角、檔名、替代文字不變；**區塊間距、走勢圖高度與亮點列高可為容納頁尾而依固定規則收縮** | Decision 6：全滿的 040 圖卡中段需 938px，現有空間 944px；加入 240px QR 後可用空間約 766–786px，不收縮就會壓到頁尾 |
| spec FR-019 | 來源參數「區分圖卡種類」 | 明定三個值：`card-rank`、`card-me`、`card-match` | Decision 5：參數越短，站台網域可用長度越長（QR 維持 version 4） |
| spec FR-020 | 縮小至 540×675 仍可掃描 | 不變，補充「網址過長導致每模組低於 4px 時，省略 QR 碼、保留可讀網址」 | Decision 5：開發／區網環境的長網址不應讓產圖失敗 |
| spec US2 驗收情境 6、FR-023 | 系統分享 SHOULD 附上文字與網址，會丟圖時才只分享圖片 | 本期 MUST 只分享圖片檔，不附 `title`／`text`／`url` | Decision 8：iOS 會把文字、連結、檔案拆成多個分享項目且圖片排最後，已有 App 只收到連結或文字的回報；LINE／Instagram 查無一手測試，不能拿主要管道去賭 |

上述修訂連同需求方已確認的三項結論，都記錄在 spec 的 Clarifications 區段。

## Technical Context

**Language/Version**：沿用既有技術，前端 Angular 20.3 + TypeScript strict mode。後端（Python 3.12／FastAPI）**不修改**。

**Primary Dependencies**：沿用既有技術堆疊。唯一的相依變動：`qrcode@1.5.4` 由「`angularx-qrcode` 的間接相依」改宣告為 `apps/web/package.json` 的**直接相依**（版本與 `angularx-qrcode@20.0.0` 鎖定的完全相同，不新增任何執行期套件、打包結果中也不會出現第二份），另加一個只在開發期使用的 devDependency `@types/qrcode`。其餘使用瀏覽器原生 Canvas 2D、`toBlob`、Web Share API Level 2、Async Clipboard API、`document.fonts.ready`，以及既有的 `@ngx-translate/core`、Angular `formatDate`、`formatPercent`（`core/match-record-detail/ratio-format.ts`）。

**Storage**：不涉及。不需要 Alembic migration，不新增查詢。

**Testing**：前端 Vitest（`@angular/build:unit-test`），全部測試先行：
- `core/share-card/`（新增／搬移）：
  - `share-card-layout.spec.ts`：`stackBlocks` 放得下時置中且不收縮；放不下時依「間距→可收縮區塊→列高」順序收縮；收縮到下限仍放不下時的行為（由上往下排、不重疊頁尾）；確定性。
  - `share-card-footer.spec.ts`：以 `RecordingContext` 驗證品牌、標語、可讀網址、QR 模組都有畫；`qr: null` 時不畫 QR 但仍畫網址；`meta` 行有無；兩種色盤下 QR 一律深色模組畫在白色底板上；長標語與長網址經截斷、不進入 QR 底板範圍。
  - `share-card-qr.spec.ts`：`qrLayout` 選出「最大、偶數、不小於 4」的模組像素；超出底板時回傳 `null`；`toQrMatrix` 對同一網址輸出固定矩陣；拋錯時回傳 `null`。
  - `share-card-link.spec.ts`：三種來源各自的 `ref` 值；可讀網址不含通訊協定與參數；不含任何 ID。
  - `share-card-actions.service.spec.ts`（搬移＋擴充）：`rasterize` 接受繪製函式；`share` 傳給 `navigator.share` 的物件只有 `files` 一個鍵（Decision 8）；`qrcode` 載入失敗時 `rasterize` 仍產出圖片（頁尾無 QR）。
  - `share-card-preview/share-card-preview.component.spec.ts`（由 040 的 dialog spec 搬移＋擴充）：單一選項時不顯示種類切換；多選項時切換會重新產圖並保留配色；其餘沿用 040 既有案例（能力偵測、`AbortError`、錯誤提示、關閉時 revoke、焦點歸還）。
  - `share-card-palette.spec.ts`、`testing/recording-context.ts`：搬移。
- `core/group-share-card/`（新增）：
  - `leaderboard-card-model.spec.ts`：1／2／3／6／7 人以上；0 場球員被排除且不計入人數；本人在前 6 內／外／0 場／不在名單；並列名次（1、1、3）原樣保留；並列跨越第 6 列時依伺服器順序取前 6；不輸出離團狀態；全員 0 場回傳 `null`；確定性；檔名與替代文字。
  - `my-stats-card-model.spec.ts`：0 場回傳 `null`；勝率字串等於 `formatPercent`；名次區塊在找不到本人列時省略；1 輪省略走勢、2 輪以上輸出走勢點；對手 0／1／3／5 位只取前 3 且順序不變；日期缺漏時省略。
  - `leaderboard-card-renderer.spec.ts`、`my-stats-card-renderer.spec.ts`：該畫的都有畫、省略的沒畫、20 字暱稱與 40 字團名經截斷、沒有任何繪製超出中段下緣、「我」標示為文字、獎牌含名次數字、兩種色盤。
  - `group-share-cards.spec.ts`：`availableGroupCards()` 在各種資料下回傳的選項集合與順序。
  - `group-share-card-i18n.spec.ts`：`shareCard.*`、`groupShareCard.*` 兩份語系檔 key 一致。
- 040 回歸：`share-card-model.spec.ts`、`share-card-highlights.spec.ts` **一行都不改、維持全綠**（內容與挑選規則不變的證明）；`share-card-renderer.spec.ts` 只更新頁尾與座標相關斷言，並新增「全滿圖卡不超出中段下緣」一例；`share-card-dialog.component.spec.ts` 改為驗證委派給預覽外殼。四個呼叫端與比賽詳情 dialog 的 spec 不動。
- `shared/line-chart/line-chart-scale.spec.ts`（新增）：抽出的縱軸範圍純函式；`line-chart.component.spec.ts` 維持全綠作為重構不變的保證。
- `features/member/my-groups/group-history/group-history.component.spec.ts`（擴充）：按鈕在載入中／錯誤／無可用圖卡時不出現；點擊後以正確的選項開啟預覽；`getMyGroups()` 失敗時日期為 `null` 但圖卡仍可用；對戰紀錄篩選不影響圖卡輸入。
- `features/home/home.component.spec.ts`（擴充）：未登入／已登入的行動按鈕去向；帶 `?ref=card-rank` 與未知 `ref` 時照常顯示；兩種語言。

後端測試不新增、不修改。

**Target Platform**：沿用既有部署方式（Docker on AWS ECS）。以行動裝置瀏覽器為主：iOS Safari 15+、Android Chrome 可用系統分享；桌機提供下載與複製圖片。

**Project Type**：Web application（monorepo，本功能只改 `apps/web`）。

**Performance Goals**：點「分享圖卡」到預覽出現 ≤ 2 秒、切換圖卡種類或配色 ≤ 1 秒（SC-001）。Canvas 繪製加 PNG 編碼通常數十到數百毫秒；QR 矩陣最多 37×37 模組；`qrcode` 以動態 `import()` 載入（約 25KB），只在第一次開啟預覽時下載一次，計入 2 秒預算。

**Constraints**：輸出固定 1080×1350；QR 每模組為偶數像素且 ≥ 4（Decision 5）；分享須在使用者手勢內同步發起，因此 Blob／File 預先產生（沿用 040 Decision 9）；名次與排序不得在前端重算（FR-008、憲章 X）；圖卡與 QR 不含任何 ID（FR-021）；不顯示離團狀態（FR-011）；新增文字全部進語系檔（FR-030）；040 的內容與挑選規則不得改變（FR-022）。

**Scale/Scope**：後端 0 檔。前端：新增 `core/share-card/`（約 9 個原始檔，其中 5 個由 040 搬移）與 `core/group-share-card/`（6 個原始檔）；修改 040 模組 4 個檔、`shared/line-chart/` 抽 1 個純函式、`group-history` 元件、`home` 元件、2 份語系檔、`package.json`。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | 新圖卡模型、`ShareCardOption`、`PromoFooter`、`QrMatrix` 皆為明確型別，沒有 `any`；`qrcode` 以 `@types/qrcode` 取得型別，對外只暴露自家的 `QrMatrix` 介面。`tsc --noEmit`、`ng lint` 沿用既有 blocking check。 | PASS |
| II. 測試優先 | 「只取前 6 列／排除 0 場／附上本人／名次原樣／區塊省略」與排版收縮規則是本功能的核心規則，純函式 spec **先於實作撰寫**並窮舉邊界；040 的 model／highlights spec 原封不動作為回歸保證。 | PASS（列為 tasks.md 強制項） |
| III. 即時性與資料一致性 | 沒有寫入路徑。圖卡使用頁面當下已載入的同一份回應，因此圖卡與頁面必然一致；不另外輪詢或快取。 | PASS |
| IV. 權限與安全 | 不新增端點，授權邊界不變（FR-028）。暱稱與團名以 `fillText` 繪製（純文字，無 XSS 面）。QR 與網址只含站台首頁與圖卡種類，不含任何 ID（FR-021）。首頁對 `ref` 參數不讀取、不儲存、不回顯（FR-025），沒有注入面。圖卡在裝置上產生，系統不保存、不上傳。 | PASS |
| V. 破壞性操作二次確認 | 沒有破壞性操作。 | 不適用 |
| VI. 可維護性 | 依賴方向單向：`core/share-card/` 不認識任何圖卡種類；`match-share-card/` 與 `group-share-card/` 只依賴共用層，彼此不相依；feature 頁面只依賴各自的圖卡模組。規則、繪製、平台能力三者分離（沿用 040）。 | PASS |
| VII. 無障礙與行動裝置優先 | 「我」與名次以文字／數字呈現，不只靠顏色（FR-009、FR-010）；色盤對比沿用 040 已驗證的 ≥ 4.5:1；預覽 `<img>` 有替代文字（FR-031）；圖卡種類切換用原生 `<button>` 加 `aria-pressed`；首頁在 360px 寬不需捲動即可看到標語與行動按鈕。 | PASS |
| VIII. i18n 與時區 | 新文字進 `shareCard.*`（共用）、`groupShareCard.*`、`home.*`，`zh-TW`／`en` 同步，並有 key 一致性測試。活動日期為 `created_at`（絕對時間戳），依裝置時區格式化，日期樣式沿用 040 的語系字串做法。後端沒有新增任何顯示文字。 | PASS |
| IX. 可攜性與可部署性 | 沒有 migration、新環境變數或新字型。`qrcode` 只是把既有間接相依宣告為直接相依（同版本），容器映像內容不變；站台網址取自 `window.location.origin`，不需設定。 | PASS |
| X. 伺服器為可信來源 | 名次、排序、勝敗場數、勝率、對手順序全部直接採用伺服器回傳值；前端只做「取前 N 列、過濾 0 場、挑出 `is_self`」這類呈現層的選取，不重新排名、不重新計算任何統計（FR-008、FR-016）。「最難纏對手」因伺服器未提供而不在本期出現。 | PASS |
| XI. 防濫用 | 沒有新增「建立新資源」的端點；首頁仍為靜態內容。 | 不適用 |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

**Post-design re-check（Phase 1 完成後）**：data-model.md 與 contracts/ 確認：沒有任何後端變動；`core/share-card/` 的公開介面不含任何比賽或團的型別；040 對外介面（`ShareCardDialogComponent.open(detail, context)`、`ShareCardContext`）不變，四個呼叫端零修改；QR／連結的組成在單一純函式內，且有測試保證不含 ID。Gate 結果維持 PASS。

## Project Structure

### Documentation (this feature)

```text
specs/041-group-share-cards/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── share-card-core.md        # Phase 1：共用層的公開介面（選項、頁尾、QR、排版、預覽外殼）
│   ├── group-share-card.md       # Phase 1：兩張新圖卡的模型規則與頁面接線
│   └── landing-link.md           # Phase 1：QR／可讀網址／ref 參數與首頁的約定
├── checklists/
│   └── requirements.md  # /speckit-specify output
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
apps/web/
├── package.json                                   # 擴充：dependencies 加 qrcode@1.5.4；devDependencies 加 @types/qrcode
└── src/
    ├── app/core/
    │   ├── share-card/                            # 新增：所有圖卡共用
    │   │   ├── share-card-canvas.ts               # 由 040 搬移：ShareCardCanvas／Text／Fonts／TranslatedText、尺寸常數
    │   │   ├── share-card-palette.ts (+ .spec.ts) # 由 040 搬移；加 QR 底板／模組色
    │   │   ├── share-card-drawing.ts (+ .spec.ts) # 由 040 搬移：truncateToWidth、panel、pill、roundedFill
    │   │   ├── share-card-layout.ts (+ .spec.ts)  # 新增：Block、stackBlocks()（含收縮規則）、中段上下緣常數
    │   │   ├── share-card-link.ts (+ .spec.ts)    # 新增：buildShareCardLink()、ShareCardSource
    │   │   ├── share-card-qr.ts (+ .spec.ts)      # 新增：QrMatrix、toQrMatrix()、qrLayout()
    │   │   ├── share-card-footer.ts (+ .spec.ts)  # 新增：PromoFooter、drawPromoFooter()
    │   │   ├── share-card-option.ts               # 新增：ShareCardOption、ShareCardRenderEnv
    │   │   ├── share-card-actions.service.ts (+ .spec.ts)   # 由 040 搬移＋改為接受 ShareCardOption、動態載入 qrcode 組出頁尾
    │   │   ├── share-card-preview/                # 由 040 的 dialog 搬移＋圖卡種類切換
    │   │   │   ├── share-card-preview.component.{ts,html,scss}
    │   │   │   └── share-card-preview.component.spec.ts
    │   │   └── testing/recording-context.ts       # 由 040 搬移
    │   ├── match-share-card/                      # 修改：成為共用層的使用者
    │   │   ├── share-card.models.ts               # 修改：共用型別改由 ../share-card 匯入並轉出；比賽專屬型別留下
    │   │   ├── share-card-model.ts、share-card-highlights.ts   # 不動（spec 也不動）
    │   │   ├── share-card-renderer.ts (+ .spec.ts)# 修改：改用 stackBlocks＋drawPromoFooter；時長／每分耗時改為頁尾的 meta 行
    │   │   ├── match-share-card-option.ts         # 新增：把 model 包成 ShareCardOption（source = card-match）
    │   │   ├── share-card-dialog/                 # 修改：open(detail, context) 介面不變，內部委派給預覽外殼
    │   │   └── testing/detail-fixtures.ts         # 不動
    │   └── group-share-card/                      # 新增
    │       ├── group-share-card.models.ts
    │       ├── leaderboard-card-model.ts (+ .spec.ts)
    │       ├── leaderboard-card-renderer.ts (+ .spec.ts)
    │       ├── my-stats-card-model.ts (+ .spec.ts)
    │       ├── my-stats-card-renderer.ts (+ .spec.ts)
    │       ├── group-share-cards.ts (+ .spec.ts)  # availableGroupCards()
    │       ├── group-share-card-i18n.spec.ts
    │       └── testing/history-fixtures.ts
    ├── app/shared/line-chart/
    │   ├── line-chart-scale.ts (+ .spec.ts)       # 新增：從元件抽出的縱軸範圍純函式
    │   └── line-chart.component.ts                # 修改：改用 line-chart-scale
    ├── app/features/
    │   ├── member/my-groups/group-history/group-history.component.{ts,html,scss,spec.ts}   # 擴充：分享按鈕、預覽外殼、getMyGroups() 取日期
    │   └── home/home.component.{ts,html,scss,spec.ts}                                       # 擴充：介紹頁
    └── assets/i18n/{zh-TW,en}.json                # 擴充：shareCard.*、groupShareCard.*、home.*；預覽按鈕的 key 由 matchShareCard.* 移到 shareCard.*

apps/api/                                          # 不修改
```

**Structure Decision**：沿用既有 monorepo 配置，本功能只動 `apps/web`。共用層放在 `core/share-card/`，與 `core/match-share-card/`、新的 `core/group-share-card/` 並列；三者的依賴方向為「兩個圖卡模組 → 共用層」，共用層不反向依賴（憲章 VI）。`core/` 是跨 feature 共用元件的既有位置（`match-record-detail/`、`court-diagram/`、`nickname/`），而團圖卡第二期會再從 `features/group-member-view/` 進入，因此不放在 `features/member/` 底下。

## Complexity Tracking

無違反項目，本節不適用。
