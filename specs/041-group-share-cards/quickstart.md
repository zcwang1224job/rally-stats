# Quickstart: 驗證團分享圖卡與導流頁尾（041-group-share-cards）

**Plan**: [plan.md](./plan.md) | 契約：[contracts/](./contracts/) | 模型：[data-model.md](./data-model.md)

## 前置條件

- 本功能只改 `apps/web`；後端不需重啟或 migration。
- 在 worktree 中執行時，依專案慣例 `ln -s` 主 checkout 的 `apps/web/node_modules`。**注意**：本功能在 `package.json` 新增了 devDependency `@types/qrcode`（`qrcode` 本體已在 `node_modules`），第一次需在主 checkout 的 `apps/web` 執行一次 `npm install`。
- 實際畫面驗收需要本機 docker 的 Postgres（`infra-db-1`）與示範資料。

## 1. 自動化測試

```bash
cd apps/web
npx ng test --watch=false
npx ng lint
npx ng build          # 必須零警告（含 CommonJS 相依警告，見 research Decision 4）
```

**預期**：全部通過，並特別確認：

- `core/match-share-card/share-card-model.spec.ts`、`share-card-highlights.spec.ts` **沒有任何 diff** 且全綠（FR-022 的內容不變保證）。
- `leaderboard-card-model.spec.ts` 涵蓋 contracts/group-share-card.md 的 L1–L9；`my-stats-card-model.spec.ts` 涵蓋 M1–M6。
- 三個 renderer spec 都有「最壞情況不超出中段下緣」一例。
- `share-card-actions.service.spec.ts` 斷言 `navigator.share` 收到的物件只有 `files` 一個鍵。

後端不需跑測試（沒有任何後端 diff；可用 `git diff --stat origin/ut -- apps/api` 確認為空）。

## 2. 實際畫面驗收

用 `apps/api/scripts/seed_dashboard_demo.py` 在測試資料庫建立示範資料（含 40 人／1,000 場的大團與 demo 會員），以 worktree 的前後端（:8001／:4300）開啟，做法見專案的 worktree 測試慣例。示範資料的團缺 `is_creator` 名單列，需先執行慣例中的那一句 `UPDATE`。

| # | 步驟 | 預期結果（對應需求） |
|---|---|---|
| 1 | 「我的團」→ 進入 40 人的示範團 → 點標題旁的「分享圖卡」 | 2 秒內出現預覽，預設為排行榜卡；標題為「排行榜」（沒有「最終」）；顯示團名、日期、球員人數（US1、FR-006、FR-012、SC-001） |
| 2 | 對照頁面的團隊排名表 | 卡上前 6 列的名次、暱稱、勝負場數與頁面前 6 列逐一相同，順序相同（FR-007、FR-008、SC-003） |
| 3 | demo 會員不在前 6 名時 | 第 6 列下方有分隔，附上本人那一列與真實名次，並有「我」文字標籤；第 7 名以後的其他人都不在卡上（FR-010、SC-004） |
| 4 | 換一個本人在前 6 名內的團 | 本人那一列有「我」標籤，沒有額外附列（FR-010） |
| 5 | 切到「我的成績」 | 1 秒內更新；勝率、勝負、總場數與頁面「我的戰績」字面相同；名次／人數與排名表一致；走勢縮圖形狀與頁面走勢圖一致；對手為頁面對手清單的前 3 位、順序相同（US3、FR-014–FR-017） |
| 6 | 先切暗色，再切換圖卡種類 | 新圖卡維持暗色；下載得到的是當下種類＋暗色（FR-004、US3 驗收情境 6） |
| 7 | 在頁面下方的對戰紀錄輸入暱稱搜尋後，再開預覽 | 兩張圖卡內容與搜尋前完全相同（Edge Cases） |
| 8 | 進入一個本人 0 場出賽的團 | 預覽只有排行榜卡，沒有種類切換（FR-003、FR-013） |
| 9 | 進入一個沒有任何已完成比賽的團 | 頁面沒有「分享圖卡」按鈕（FR-001） |
| 10 | 用 SQL 把某位球員的暱稱改成 20 字、團名改成 40 字後重開 | 兩種配色、兩種語言下沒有文字重疊或超出邊界，QR 沒有被遮（SC-005） |
| 11 | 切換語言為 English 後重開預覽 | 圖卡與預覽上所有固定文字為英文；網址與 QR 不變（FR-030、SC-009） |
| 12 | 下載三種圖卡 × 兩種配色共 6 張 | 每張皆為 1080×1350；頁尾有品牌、標語、可讀網址、QR（FR-018） |
| 13 | **040 回歸**：「我的對戰紀錄」→ 一場雙打、紀錄完整、有 3 個亮點的比賽 →「分享圖卡」 | 隊伍、比分、徽章、走勢、3 個亮點、檔名皆與上線前相同；時長／每分耗時出現在頁尾左上；沒有任何內容壓到頁尾（FR-022、SC-007） |
| 14 | 依 `specs/040-match-share-card/quickstart.md` 第 2 節重跑 1–7 項 | 全部仍成立（頁尾相關敘述改為新頁尾）（SC-007） |

## 3. QR 掃描驗收（SC-006）

把第 2 節步驟 12 的 6 張圖傳到手機或顯示在另一個螢幕上：

| # | 步驟 | 預期 |
|---|---|---|
| 1 | 原尺寸顯示，用 iOS 相機、Android 相機、LINE 掃描器各掃一次 | 18 次全部成功，開啟首頁 |
| 2 | 縮成 540×675（例如把圖貼進 LINE 聊天後在聊天列表檢視、或用影像軟體縮圖）再各掃一次 | 18 次全部成功 |
| 3 | 在 LINE 聊天室中長按圖卡 → 辨識 QR | 成功開啟首頁 |
| 4 | 檢查開啟的網址 | 排行榜卡為 `?ref=card-rank`、我的成績卡為 `?ref=card-me`、單場圖卡為 `?ref=card-match`；沒有其他參數 |

自動化輔助（選用）：可沿用 research Decision 5 的做法，以腳本把 `toQrMatrix()` 的輸出縮圖 50% 後用解碼器驗證；這不是產品測試的一部分，只用來在調整頁尾尺寸時快速回歸。

## 4. 系統分享驗收

| # | 步驟 | 預期 |
|---|---|---|
| 1 | iOS Safari：預覽 →「分享」→ LINE | 聊天室收到的是圖卡圖片本身，沒有多出文字或連結訊息（research Decision 8） |
| 2 | Android Chrome：同上，另測 Instagram 限時動態 | 圖片正確帶入 |
| 3 | 桌機 Chrome：「複製圖片」後貼到 LINE 電腦版 | 出現同一張圖卡 |
| 4 | 在分享選單按取消 | 沒有錯誤訊息，預覽維持開啟 |

## 5. 首頁驗收（US4）

| # | 步驟 | 預期 |
|---|---|---|
| 1 | 未登入開啟 `/` | 系統名稱、標語、3 項功能重點、「開始使用」與「登入」按鈕；按下分別進入註冊與登入頁 |
| 2 | 開啟 `/?ref=card-rank`、`/?ref=<script>`、`/?foo=bar` | 畫面與第 1 步完全相同，沒有錯誤，參數沒有被顯示在畫面上（FR-025） |
| 3 | 已登入開啟 `/` | 主要按鈕進入 `/member`；沒有自動轉址 |
| 4 | 以 360×640 的視窗開啟 | 標語與主要按鈕不需捲動即可看見 |
| 5 | 開啟 `/join/<token>`、`/scoreboard/<token>` 等既有公開路由 | 行為與上線前相同（FR-026） |
| 6 | 找 5 位沒用過系統的人各看首頁 10 秒 | 至少 4 位能說出系統用途並指出開始使用的按鈕（SC-008） |
