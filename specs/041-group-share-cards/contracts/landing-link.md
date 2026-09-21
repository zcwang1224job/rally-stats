# Contract: 圖卡連結與首頁落點

**Feature**: 041-group-share-cards | 決策依據見 [research.md](../research.md) Decision 5、8、9。

這是本功能唯一「離開系統再回來」的介面：圖卡上的 QR／網址，以及它們指向的首頁。

---

## 1. 網址格式

| 項目 | 格式 | 範例 |
|---|---|---|
| QR 內容 | `<origin>/?ref=<source>` | `https://rallystats.example/?ref=card-rank` |
| 圖上的可讀網址 | `<host>` | `rallystats.example` |

- `<origin>`、`<host>` 取自產生圖卡當下的 `window.location`；開發與測試站產生的圖卡指向該站台本身，不另外設定。
- `<source>` 只有三個值：

| 值 | 圖卡 |
|---|---|
| `card-rank` | 團排行榜卡 |
| `card-me` | 我的本團成績卡 |
| `card-match` | 040 單場比賽圖卡 |

- 網址**不含**會員、團、比賽或任何可識別個人的資訊（FR-021）。
- 為了讓 QR 維持 version 4（33 模組、每模組 6px），正式站台的網域建議不超過 38 個字元；超過時 QR 會自動改用較小的模組，再超過則不畫 QR、只留可讀網址（FR-020）。

## 2. 首頁（`/`，不需登入）

| 情境 | 行為 |
|---|---|
| 任何人開啟 `/` | 顯示系統名稱、標語（`shareCard.tagline`，與圖卡頁尾同一個 key）、3 項功能重點、行動按鈕 |
| 未登入 | 主要按鈕 → `/auth/register`；次要按鈕 → `/auth/login` |
| 已登入 | 主要按鈕 → `/member`；不自動轉址 |
| 帶 `?ref=<任何值>` | 與不帶參數時完全相同。元件**不讀取**該參數：不儲存、不回顯、不帶進後續導覽（FR-025） |
| 帶其他未知參數 | 同上 |
| 360px 寬的手機直向 | 標語與主要按鈕在第一屏內（FR-024、US4 驗收情境 4） |

不新增守衛、轉址或後端呼叫；`/join/:token`、`/guest-access/:token`、`/scoreboard/:courtToken`、`/control/*` 等其他不需登入的路由不受影響（FR-026）。

## 3. 成效量測（本期不實作）

系統目前沒有流量分析工具。`ref` 參數會出現在網站伺服器／CDN 的存取紀錄中，日後導入分析工具時可直接依這三個值區分來源。前端在本期不對 `ref` 做任何處理，這一點由首頁的測試保護（帶參數與不帶參數的畫面相同）。

## 4. 系統分享的內容

`navigator.share()` 只傳 `{ files: [圖卡 PNG] }`，不帶 `title`、`text`、`url`（Decision 8）。因此上述網址只會以「圖上的 QR 與文字」這一種形式離開系統。
