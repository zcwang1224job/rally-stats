<!--
Sync Impact Report
- Version change: (template, unratified) → 1.0.0
- Rationale: Initial ratification. Template was fully unfilled (all bracket
  placeholders); this is not an amendment but the first concrete constitution,
  hence MAJOR version 1.0.0 per semantic versioning governance rules.
- Modified principles: N/A (initial adoption)
- Added sections:
  - Core Principles I–XI (code quality, test-first, real-time sync &
    consistency, auth & security, UX confirmation, modularity, accessibility
    & mobile-first, i18n & timezone architecture, portability/deployability,
    real-time source of truth, anti-abuse)
  - Section: 技術治理與品質關卡 (Technical Governance & Quality Gates)
  - Section: 未來規劃事項（明確排除於當前實作範圍）(Deferred Roadmap Items)
  - Governance (amendment procedure, versioning policy, compliance review)
- Removed sections: none (template placeholders only)
- Templates requiring updates:
  - ✅ .specify/templates/plan-template.md — generic "[Gates determined based
    on constitution file]" placeholder already defers to this file; no edit
    needed, but future /speckit-plan runs MUST enumerate the Constitution
    Check gates from the principles below.
  - ✅ .specify/templates/spec-template.md — no constitution-specific
    references to update; mandatory sections remain compatible.
  - ✅ .specify/templates/tasks-template.md — generic task categories remain
    compatible; task generation MUST add categories for i18n/locale files,
    accessibility checks, and abandoned-match handling where applicable.
  - ⚠ README.md / docs/quickstart.md — do not yet exist in this repository;
    create them during initial project scaffolding and ensure they reference
    the principles here (Docker parity, i18n key usage, env var handling).
- Follow-up TODOs: none — all placeholders resolved. Deferred product scope
  (data retention/account deletion, observability, DB backup/DR, migration
  execution strategy) is intentionally captured as a non-binding roadmap
  section rather than a TODO, per explicit user instruction.
-->

# Rally Stats（羽球揪團與即時計分系統）Constitution

## Core Principles

### I. 程式碼品質與型別安全（Code Quality & Type Safety）

前後端 TypeScript 專案 MUST 全面啟用 `strict` mode（`tsconfig.json` 中
`strict: true`），不得以 `any` 或型別斷言迴避型別檢查，除非有明確且經過
註解說明的例外理由。任何 Pull Request MUST 同時通過 lint 檢查與型別檢查
（`tsc --noEmit` 或等效流程）才可合併；CI pipeline MUST 將這兩項設為
merge 的必要關卡（blocking check），不可僅作為警告存在。

**Rationale**：即時計分系統的正確性高度仰賴型別一致性（例如比分、Round、
狀態列舉的型別），寬鬆的型別檢查會讓執行期錯誤流入正式環境，且不利多人
協作時及早發現介面不相容問題。

### II. 測試優先（Test-First for Core Domain Logic）

核心領域邏輯——開團、加入、輪替（排點）演算法、比分計算——MUST 具備單元
測試覆蓋，且測試 MUST 涵蓋正常路徑與邊界情境（例如：滿團、平手判定、
達到目標分數的自然結束條件）。關鍵使用者流程「開團 → 加入 → 排點 →
計分」MUST 具備至少一條端到端或整合測試，驗證跨模組串接的正確性。
新增或修改上述核心邏輯的 PR，若未附帶對應測試，MUST 視為未完成
（incomplete），不可合併。

**Rationale**：這些邏輯是系統信任的基礎——輪替演算法出錯會導致不公平的
上場順序，比分計算出錯會直接產生錯誤的戰績紀錄，且兩者都難以在正式環境
用肉眼即時發現。

### III. 即時性與資料一致性（Real-Time Sync & Consistency）

計分板（Scoreboard）與控制板（ControlPanel）MUST 透過即時通訊技術
（WebSocket 或同等技術，本專案採 Ably，見原則 X）同步狀態，端到端延遲
SHOULD 控制在 1 秒以內。系統 MUST NOT 允許計分板顯示的比分與控制板實際
操作的結果不同步。前端 MUST 明確呈現連線中斷狀態（例如「連線中斷」提示
UI），且 MUST NOT 讓使用者誤以為畫面上的舊分數仍是即時的。重新連線後，
前端 MUST 以伺服器回傳的最新狀態強制覆蓋畫面，MUST NOT 信任或繼續顯示
斷線期間累積的本地暫存分數/狀態。

**設定變更的時間一致性**：任何團級別設定（比賽設定、比賽模式、排程機制
等）的修改，MUST 只影響修改之後才開始的新活動（新比賽、新 Round），
MUST NOT 回溯影響已在進行中的活動。已在進行中的比賽/賽程 MUST 維持其
建立當下適用的設定不變；此保證 MUST 透過資料快照（snapshot，例如在建立
Match/Round 時複製當下設定值到該筆紀錄本身）落實，MUST NOT 以即時查詢
當前團設定的方式取代快照，以避免管理員事後修改設定意外改變進行中活動的
判定規則。

**比賽紀錄的完整性一致性**：只有透過「達到目標分數自然結束」的比賽，才
MUST 產生 MatchResult 並計入戰績與對戰紀錄。任何形式的強制中止或清空
——包含但不限於單場「提前結束」、Round 層級「Next Round」清空、刪除場地、
解散團——導致比賽尚未收尾的情況，一律 MUST 統一轉為「已捨棄
（abandoned）」狀態，MUST NOT 產生 MatchResult、MUST NOT 計入任何一方的
勝負統計。此為單一通用原則，適用於系統中所有會導致比賽提前終止的情境；
日後新增任何會中止比賽的功能時，MUST 沿用同一套「已捨棄不計入紀錄」的
處理方式，不得為個別情境各自發明例外規則。

**Rationale**：即時計分系統的核心價值就是「畫面即真相」——任何不同步、
陳舊快取或事後可回溯竄改的判定規則，都會直接破壞使用者對系統的信任；而
戰績紀錄一旦摻入未完賽的資料，將永久污染歷史統計且難以事後清理。

### IV. 權限與安全（Authorization & Security）

- 管理員權限 MUST 以「組團編號 + 管理 PIN 碼」驗證；PIN 碼 MUST NOT 明文
  儲存（MUST 雜湊），且此驗證 MUST 具備基本防暴力破解機制（例如錯誤次數
  限制/鎖定）。
- 有通關密碼的團，加入前 MUST 驗證密碼正確才能查看/加入賽程細節；此驗證
  MUST NOT 設錯誤次數限制或鎖定機制（已定案：通關密碼保護的是加入資格
  而非帳號安全，優先考量使用者體驗）。此驗證與管理 PIN 碼驗證屬不同安全
  等級，實作 MUST NOT 共用同一套機制或程式碼路徑。
- 會員密碼 MUST 單向雜湊儲存（不可還原）；Email MUST 驗證格式，且 MUST
  在系統內保持唯一。
- 會員帳號 MUST 完成 Email 驗證後才能使用任何功能：註冊後帳號預設為
  未驗證狀態，登入後僅能看到驗證提示畫面；開團、加入團、好友系統、對戰
  紀錄、個人設定等 MUST 全面鎖定直到完成信箱驗證為止。此限制 MUST NOT
  影響 Guest（訪客）身分的使用。
- 團的通關密碼 MUST 以可還原的加密方式儲存（而非雜湊），因為管理員需要
  在已驗證的管理頁隨時查看密碼明文以分享給新加入者；此明文查看功能 MUST
  僅限管理頁提供，MUST NOT 出現在任何無需驗證即可開啟的畫面上。
- 無需驗證即可開啟的畫面（單一場地控制板、全部場地控制板、計分板連結、
  QR Code）MUST NOT 提供任何管理員專屬操作（例如 Next Round、踢除成員、
  解散團、編輯排程機制等）；此類操作 MUST 僅存在於需通過組團編號 + 管理
  PIN 碼驗證的開團管理頁（含其內建的場地控制區塊）。日後新增任何控制板/
  計分板相關功能時，MUST 先判斷該功能是否具管理員專屬性質；若是，MUST
  只加在管理頁，MUST NOT 加在無需驗證的畫面上。
- 所有使用者輸入的自由文字內容（暱稱、團名、場地名稱等任何會顯示給其他
  使用者看的欄位）MUST 在前端顯示時做 HTML 逸出處理（escape），以防止
  XSS。此為單一通用原則，適用於系統中所有此類欄位，個別欄位規格 MUST NOT
  重複交代。
- 任何連結類 Token（計分板、單一場地控制板、全部場地控制板、加入連結）
  MUST 可由管理員單獨重新產生使舊連結失效，MUST NOT 要求以解散整個團的
  方式處理單一連結外洩疑慮。此為單一通用原則，適用於系統中所有此類連結。

**Rationale**：本系統同時存在高信任（管理員）與零門檻（Guest）兩種使用
情境，安全機制必須依情境分級設計，混用同一套機制會在其中一端造成過度
摩擦、在另一端造成防護不足。

### V. UX 一致性（Confirmation for Destructive Actions）

所有具破壞性或不可逆影響的互動元件（解散團、刪除場地、踢除成員等）
MUST 提供明確的二次確認流程，避免誤操作造成資料遺失。

**Rationale**：即時系統的操作往往由手機小螢幕上的手指快速點擊觸發，
單次點擊誤觸的機率遠高於桌面應用。

### VI. 可維護性（Modularity）

功能 MUST 以模組化方式拆分：開團模組、場地模組、賽程/輪替模組、團內
成員視圖與戰績模組、會員/好友模組、計分板/控制板模組。模組間 MUST 以
清楚定義的 API/介面溝通，MUST NOT 依賴跨模組的內部實作細節或共享可變
狀態。

**Rationale**：清楚的模組邊界讓輪替演算法、比分邏輯等核心規則可以獨立
測試與獨立演進，避免功能耦合導致的迴歸風險。

### VII. 無障礙與行動裝置優先（Accessibility & Mobile-First）

介面（尤其計分板）MUST 支援大螢幕投影與手機瀏覽，字體與對比 MUST 清晰
可辨識，比分 MUST 可遠距離閱讀。任何用於傳達狀態或分類的視覺元素（例如
需密碼/公開的鎖頭標示），MUST NOT 僅依賴顏色作為唯一區分依據，MUST 搭配
圖示形狀、文字標籤，或輔助文字（如 `aria-label`）等至少一種非色彩的區分
方式。此為單一通用原則，適用於系統中所有此類元素，個別欄位規格 MUST NOT
重複交代。

**Rationale**：計分板常在球場燈光、投影布幕、遠距離觀看等非理想條件下
使用，且必須確保色盲與視障使用者也能正確理解畫面資訊。

### VIII. 多語系與時區架構（i18n & Timezone Architecture）

**多語系**：初期僅上線繁體中文，但前後端建置時 MUST 採用 i18n 架構，
MUST NOT 將顯示文字寫死在元件/程式碼中。前端所有顯示文字 MUST 集中於
語系檔（key-value 對應）。後端所有回傳給前端的錯誤訊息/提示文字 MUST
回傳語意化的錯誤代碼（error code），MUST NOT 回傳寫死的中文句子；由前端
依語系檔轉換顯示。此架構 MUST 確保日後新增語言只需新增語系檔，不需要
更動元件邏輯或後端 API 合約。

**時區處理**：系統內時間分為兩類，處理原則不同，實作 MUST NOT 混用同一
套邏輯：

- **系統自動記錄的絕對時間戳**（例如最後活動時間、`created_at`、JWT
  過期時間、Email 驗證連結有效期、Turnstile 驗證時效）：資料庫欄位一律
  MUST 使用 `TIMESTAMPTZ`（而非 `TIMESTAMP`），內部儲存與運算永遠 MUST
  為 UTC；API MUST 回傳 ISO 8601 格式並帶時區資訊（例如
  `2026-08-31T10:00:00Z`）。所有時間差計算（例如「距離最後活動時間是否
  已超過 1 小時」）一律 MUST 以 UTC 相減，MUST 與顯示用時區設定完全脫鉤。
- **活動時間區間**（代表真實世界場地時間的欄位）：其本質是這場球敘實際
  發生的場地時間，不是使用者個人行程，因此 MUST NOT 依照「存 UTC、依
  觀看者裝置時區顯示」的一般網頁慣例處理——不論建立者或查看者的裝置時區
  為何，所有人看到的都 MUST 是同一個場地時間（例如「19:00–21:00」）。
  顯示與比對時一律 MUST 使用系統預設時區（SystemConfig 的
  `default_timezone` 參數，預設 `Asia/Taipei`），MUST NOT 呼叫瀏覽器/
  裝置的時區偵測。

**Rationale**：i18n 架構讓「語言」可以隨時切換，但「時區顯示邏輯」是
完全獨立於語言的另一件事，不會因為使用者切換語系而跟著改變；場地時間
若被誤用「裝置時區顯示」邏輯換算，會讓不同時區的使用者看到不一致、
甚至錯誤的比賽時間。日後若需擴展支援其他地區場地，僅需調整
`default_timezone`（或演變為每團可各自設定時區），架構上不需大幅更動。

### IX. 可攜性與可部署性（Portability & Deployability）

前後端服務皆 MUST 可透過 Docker 容器化執行，本地開發與正式環境（AWS）
MUST 使用相同的映像建置流程，避免環境落差。所有環境變數/密鑰 MUST NOT
寫死在程式碼中，MUST 透過環境變數或等效的外部設定機制注入。

**Rationale**：即時系統對環境一致性特別敏感（時區、連線設定、金鑰），
「在我電腦上可以跑」的落差在正式環境會直接反映為即時同步失效或安全
漏洞。

### X. 即時同步的可信來源（Server as Source of Truth）

所有會改變比分/賽程狀態的操作，一律 MUST 先經後端 API 驗證並寫入
資料庫，再由後端透過 Ably 廣播事件。前端（計分板/控制板）MUST 僅訂閱
事件，MUST NOT 繞過後端直接發布寫入事件。

**Rationale**：若前端可直接發布狀態變更事件，即無法保證伺服器端資料庫
與畫面顯示一致，且會讓比分/賽程狀態失去單一可信來源，破壞原則 III 的
一致性保證。

### XI. 防機器人/防濫用（Anti-Bot & Abuse Prevention）

對於「建立新資源」類型的公開端點（目前範圍：會員註冊、開團），前端
MUST 整合 Cloudflare Turnstile（Free 方案）取得驗證 token，後端於受理
請求前 MUST 呼叫 Cloudflare 驗證 API 確認該 token 有效，方可繼續執行
後續邏輯（建立帳號、建立團）；驗證失敗 MUST 明確提示錯誤並拒絕該次
請求。

「加入團」端點本次 MUST NOT 納入 CAPTCHA 驗證範圍（已定案，維持現行
設計，避免在 Guest 零門檻加入體驗上疊加摩擦），僅先以既有的人數上限、
通關密碼、1 小時自動解散等機制自然限縮濫用範圍。若未來偵測到「加入團」
端點有實際濫用情況，可能追加以下任一或多項進階方案（本次僅記錄可能
方向、不展開規格，待有實際需求時再另行 `/specify`）：

- 針對「加入團」端點另外整合 Turnstile（做法比照開團/註冊）。
- 依 IP 或 Guest Session Token 來源做速率限制（例如同一 IP 每分鐘最多
  加入 N 次）。
- 升級為 Cloudflare Turnstile 付費方案或改用具風險評分能力的服務。

此原則之技術實作細節（前端 widget 整合、後端驗證 API 呼叫、金鑰管理、
token 時效性處理）由對應功能的 `/plan` 規劃。

**Rationale**：註冊與開團會直接產生新資源（帳號、團），是機器人濫用的
主要目標；加入團雖然風險較低，但仍需保留漸進式加固的空間，不宜過度
設計提前引入未驗證需求的摩擦。

## 技術治理與品質關卡（Technical Governance & Quality Gates）

- 每個 Pull Request MUST 在合併前通過：lint 檢查、型別檢查（原則 I）、
  相關單元/整合測試（原則 II）。CI pipeline MUST 將以上三者設為
  blocking check。
- 涉及即時同步（原則 III、X）或權限/安全（原則 IV）的變更，MUST 在
  PR 描述中說明該變更如何維持「伺服器為唯一可信來源」與「管理員操作
  僅限管理頁」的邊界，供 review 時核對。
- 新增或修改任何顯示文字（前端）或錯誤訊息（後端）時，MUST 遵循原則
  VIII 的 i18n 架構（語系檔 key / error code），MUST NOT 引入寫死文字，
  作為 review checklist 的一部分。
- 每個 `/speckit-plan` 產出的 Constitution Check 段落 MUST 逐條對照本
  文件的核心原則（I–XI），列出該功能是否觸及、如何符合；若有偏離，
  MUST 記錄於該 plan 的 Complexity Tracking 表並附上理由。

## 未來規劃事項（明確排除於當前實作範圍）

以下事項為已記錄但**刻意延後**的方向，本次 `/specify` ~ `/implement`
範圍不涵蓋，不構成本憲章的強制性關卡（MUST）；待有實際需求時再另行
`/specify` 或 `/plan` 展開規格與實作設計。

- **資料保留與帳號刪除政策**：GDPR 式的個資保留/刪除機制，包含會員
  主動刪除帳號（Email、密碼雜湊、歷史對戰紀錄的刪除或匿名化）、已解散
  團的歷史資料保留期限與封存策略、Guest 資料的獨立保留政策，以及若有
  歐盟等地區使用者時的法規層級刪除流程。由於 Email、密碼雜湊皆屬個資，
  待專案有實際使用者或考慮正式對外營運時，SHOULD 優先補上此項規劃。
- **維運面待補項目**：
  - 可觀測性（Observability）：Ably 連線/斷線率、高頻 API（+1/-1）延遲
    分佈、1 小時自動解散排程任務的執行狀況與失敗率、Turnstile 驗證
    成功/失敗率等監控與錯誤追蹤（例如 Sentry、AWS CloudWatch）。
  - 資料庫備份與災難復原：Amazon RDS for PostgreSQL 的自動備份頻率、
    保留天數、Point-in-time Recovery（PITR）、跨可用區/區域備援策略，
    以及對應的 RPO/RTO 定義。
  - CI/CD 中 Alembic migration 的執行時機與失敗處理：正式環境部署到
    ECS 時 migration 的執行時機（部署前獨立步驟 or 容器啟動時自動
    執行）、失敗時的 rollback 策略、多個 ECS Task 同時啟動時避免
    migration 重複執行的機制。

## Governance

本憲章是本專案（羽球揪團與即時計分系統）所有開發實務的最高準則，優先於
個別功能規格、實作計畫或程式碼慣例。任何 `/speckit-plan` 或
`/speckit-tasks` 產出，若與本憲章原則衝突，MUST 在對應文件的
Complexity Tracking 或等效章節中明確記錄衝突原因與替代方案，並取得
專案負責人（本專案為單人維護，即開發者本人）確認後才可繼續。

**修訂程序**：任何人（含開發者本人）欲修改本憲章，MUST 透過
`/speckit-constitution` 重新執行本流程，明確列出變更內容、版本異動
理由，並同步檢查 `.specify/templates/` 下相依文件與既有 `/specs/*/plan.md`
是否需要對應更新。

**版本策略**（Semantic Versioning）：
- **MAJOR**：移除既有原則、或對既有原則做不相容的重新定義（例如放寬
  原則 III 的「伺服器為唯一可信來源」）。
- **MINOR**：新增原則或章節、或對既有原則做實質性擴充（例如新增一類
  端點的防濫用要求）。
- **PATCH**：純文字澄清、措辭修正、不影響規則語意的調整。

**合規審查**：每次 `/speckit-plan` MUST 執行 Constitution Check
（見上方「技術治理與品質關卡」）；每次程式碼審查（PR review）MUST 視為
合規檢查的一部分，審查者發現與本憲章牴觸之處 MUST 要求修正或於文件中
記錄合理例外，複雜度提升 MUST 有正當理由（Complexity Tracking）。

**Version**: 1.0.0 | **Ratified**: 2026-08-31 | **Last Amended**: 2026-08-31
</content>
</invoke>
