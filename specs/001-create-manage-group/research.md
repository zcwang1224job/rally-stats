# Phase 0 Research: 開團與管理

本文件解析 `plan.md` Technical Context 中留待決策的技術性空白（spec 本身已將這些細節列為 Assumptions，明確交由 `/speckit-plan` 決定，見 spec.md 之 Assumptions 段落）。

## 1. 管理 PIN 碼防暴力破解的具體門檻值

- **Decision**: 同一組團編號，PIN 驗證錯誤達 10 次後鎖定該組團編號 15 分鐘（期間內即使輸入正確 PIN 碼也拒絕，回應 `GROUP_ADMIN_LOCKED`，並附帶剩餘鎖定秒數）；鎖定期滿後錯誤計數歸零重新起算。
- **Rationale**：6 碼純數字 PIN 共 100 萬種組合，10 次錯誤即鎖定 15 分鐘，將暴力破解在合理時間內窮舉的可行性降至可忽略；15 分鐘足以讓誤觸發者（例如真正的管理員打錯字）短暫等待後重試，不需要人工介入解鎖。
- **Alternatives considered**：
  - 永久鎖定需人工解鎖——過度嚴苛，管理員本人打錯字風險高，且本系統無客服人工解鎖流程。
  - 遞增式延遲（exponential backoff，如每次錯誤延遲加倍）——實作複雜度較高，對於「同一組團編號」這種低價值目標（不像會員帳號可能被用於多處）不成比例，改用固定鎖定期更單純。
- **實作對應**：`groups.admin_failed_attempts`、`groups.admin_locked_until` 欄位（見 data-model.md）；`POST /groups/reauth` 端點內以資料庫交易同時檢查與遞增。

## 2. 管理 Token 格式與有效期限

- **Decision**: 採用 JWT（`PyJWT`），payload 含 `group_id`、`admin_token_version`、`exp`；有效期限 4 小時。
- **Rationale**：JWT 為無狀態驗證，符合 constitution 原則 X 對後端驗證效率的要求；`admin_token_version` 隨 Token 一併簽發，驗證時與資料庫目前版本比對即可達成「重設 PIN 碼後舊 Token 立即失效」（見 spec FR-026、FR-027），不需額外維護黑名單。4 小時已遠長於一般揪團活動時長，且實際上限進一步受「1 小時無活動自動解散」機制限制（團解散後任何 Token 皆無法再寫入）。
- **Alternatives considered**：
  - 短效期（如 15 分鐘）+ refresh token——管理頁操作情境不需要如會員系統一樣的高安全敏感度，額外的 refresh 流程徒增複雜度且與 spec 的「憑證版本號」失效機制重疊。
  - Session-based（存於後端 session store）——違背無狀態 API 設計，且需額外的 session 儲存基礎設施（如 Redis），與現有 PostgreSQL-only 的資料層決策不一致。

## 3. 通關密碼可還原加密的實作方式

- **Decision**: 使用 Python `cryptography` 套件之 `AESGCM`（AES-256-GCM）；加密金鑰（32 bytes）存於 AWS Secrets Manager（正式環境）/ `.env`（本地開發）之 `PASSWORD_ENCRYPTION_KEY`；密文格式為 `nonce (12 bytes) || ciphertext || tag`，以 `BYTEA` 儲存於 `groups.password_ciphertext`。
- **Rationale**: `cryptography` 為 Python 生態圈最廣泛使用、通過安全稽核的加密函式庫；AES-256-GCM 提供認證加密（AEAD），可偵測密文竄改，優於純 CBC 模式。
- **Alternatives considered**：
  - Fernet（`cryptography.fernet`）——底層亦為 AES，但格式較不透明且內建時間戳記，對本情境（僅需加解密、無需內建過期）不必要；直接使用 `AESGCM` 更貼近需求且效能較佳。

## 4. 1 小時無活動自動解散的排程機制

- **Decision**: 使用 `APScheduler`（`AsyncIOScheduler`），於 FastAPI app 啟動時註冊一個每分鐘執行一次的週期任務，查詢 `status = 'active' AND last_activity_at < now() - interval '1 hour'` 的團並逐一觸發解散流程（與手動解散共用同一段 service 邏輯）。
- **Rationale**: 現階段規模（單一 ECS Fargate 後端 Service，非多副本高流量場景）不需要獨立的訊息佇列或分散式排程系統；`APScheduler` 為 in-process 方案，部署與維運成本最低，符合 constitution 對「未來進階功能」（可觀測性、複雜排程基礎設施）的刻意延後範圍。
- **已知限制與因應**：若後端 Service 未來水平擴展為多個 Task，多個 Task 各自的 APScheduler 實例會重複掃描同一批已逾時的團；因解散操作本身已具備冪等性（`status` 欄位轉換 + 樂觀鎖），重複觸發不會造成資料錯誤，僅會有微量重工，可接受。若日後擴展為多 Task 部署，建議改用資料庫層級的 advisory lock 或遷移至獨立的排程 Task（此為未來優化項，非本次必要條件）。
- **Alternatives considered**：
  - AWS EventBridge Scheduler 呼叫內部端點——需額外的 IAM 與網路設定，對 MVP 階段不成比例；APScheduler 已足夠。
  - Celery + Redis——引入額外基礎設施（訊息佇列、broker），與專案「維持系統單純」的一貫設計精神不符。

## 5. 前端測試框架選型

- **Decision**: 採用 Vitest 取代 Angular CLI 傳統預設的 Karma + Jasmine。
- **Rationale**: Angular 官方自 v17 起提供 Vitest 作為實驗性/選用測試執行器整合；Vitest 啟動速度顯著快於 Karma（無需啟動真實瀏覽器）、與 Vite 生態系整合度高，社群趨勢亦逐漸從 Karma 遷移；本專案為全新專案，無既有 Karma 測試資產需要遷移，適合直接採用較新方案。
- **Alternatives considered**：
  - 維持 Karma + Jasmine（Angular CLI 傳統預設）——穩定但啟動較慢、Karma 專案本身已進入維護模式（Angular 官方文件已標註其未來可能移除）；不建議新專案採用。
  - Jest——另一主流選項，但與 Angular 官方近期整合方向（Vitest）不一致，選用 Vitest 較符合官方長期路線。

## 6. Rate Limiting 函式庫選型

- **Decision**: 使用 `slowapi`（基於 `limits` 套件，FastAPI 中介軟體形式）。
- **Rationale**: 與 FastAPI 生態系整合度高（裝飾器語法 `@limiter.limit(...)`），支援以 IP 或自訂 key（如組團編號）為限制依據，滿足 PIN 重新驗證端點「依組團編號」鎖定、以及本專案其他 spec（006 會員系統）之 Email/IP 速率限制需求，可跨 feature 重複使用同一套機制。
- **Alternatives considered**：
  - 手動實作（Redis/DB 計數器）——現階段無 Redis 基礎設施，若改用 DB 計數器則等同於本 feature 已規劃的 `admin_failed_attempts` 欄位機制，`slowapi` 僅用於「頻率」而非「累積失敗次數鎖定」這類語意不同的限制（例如 Turnstile 驗證端點本身的呼叫頻率），兩者互補、不衝突。

## 7. Cloudflare Turnstile 呼叫的錯誤處理細節

- **Decision**: `httpx.AsyncClient` 呼叫 `siteverify`，逾時設為 4 秒；捕捉 `httpx.TimeoutException`、非 2xx 回應、或回應 JSON 缺少 `success: true` 時，一律回傳 `CAPTCHA_INVALID`（或 token 已使用/過期時回傳 `CAPTCHA_EXPIRED`），HTTP 狀態碼 400，MUST NOT 建立團（fail-closed，已於 spec FR-007、architecture.md 定案）。
- **Rationale**：4 秒界於 spec Assumptions 所述「3~5 秒」建議區間中點，兼顧使用者等待體驗與外部服務異常時的及早失敗。
- **Alternatives considered**：無（此為 spec 與 architecture.md 已明確指定 fail-closed 原則下的單純落地實作，不存在其他合理替代方案）。

---

**NEEDS CLARIFICATION 解決狀態**：`plan.md` Technical Context 未遺留任何 `NEEDS CLARIFICATION` 標記；上述 7 項研究涵蓋 spec.md Assumptions 段落中明確列為「留待後續規劃階段決定」的所有技術性空白。
