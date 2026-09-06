# 正式環境上線注意事項（Production Readiness Notes）

本文件彙整「從本地開發環境要走到正式對外上線」還需要處理的設定與已知缺口。技術棧與 AWS 架構決策本身已定案於 `specs/architecture.md`（尤其第 6 節「AWS 部署架構」），本文件不重複那份文件的決策內容，只聚焦在**實際要改的設定值、要在 AWS 主控台做的操作、以及尚未實作的維運項目**，供上線前逐項核對。

## 目錄

1. [寄送真實 Email（驗證信／忘記密碼信）](#1-寄送真實-email驗證信忘記密碼信)
2. [AWS 部署所需的環境變數／Secrets 總覽](#2-aws-部署所需的環境變數secrets-總覽)
3. [尚未實作的維運項目（已知缺口）](#3-尚未實作的維運項目已知缺口)
4. [上線前檢查清單](#4-上線前檢查清單)

---

## 1. 寄送真實 Email（驗證信／忘記密碼信）

### 現況

會員註冊驗證信、忘記密碼信的**程式碼本身已經是真實整合**（不是假的/待實作的骨架），實作在 `apps/api/app/core/email.py`：

- `LoggingEmailSender`：**目前預設**使用這個——不會真的寄信，只會把收件人、主旨、內文寫進後端的應用程式日誌（`docker compose logs backend`）。
- `SesEmailSender`：透過 `boto3` 呼叫 Amazon SES 的 `send_email` API，真的會寄出信件。

要用哪一種，由 `apps/api/app/core/config.py` 的 `email_backend` 設定值決定（`"log"` 或 `"ses"`），對應環境變數 `EMAIL_BACKEND`。**目前 `apps/api/.env.example` 完全沒有列出 email 相關變數，且 `email_backend` 預設值是 `"log"`**——這代表任何一個直接照 `docs/local-development.md` 設定起來的環境，寄信功能永遠只會寫 log，不會真的送出去。

觸發寄信的三個地方（皆已呼叫 `send_email()`，不需要改程式碼）：
- 註冊 → 驗證信：`apps/api/app/domains/member/service.py`（`register()` → `_issue_verification_token_and_email()`）
- 重寄驗證信：同檔案 `resend_verification()`（有 60 秒冷卻）
- 忘記密碼：同檔案 `forgot_password()`

### 要改的設定值

在要收到真實信件的環境（本機測試或正式環境）的 `.env`／Secrets 中設定：

```bash
EMAIL_BACKEND=ses
SES_REGION=us-east-1          # 依實際使用的 AWS region 調整
SES_FROM_ADDRESS=no-reply@yourdomain.com   # 必須是已在 SES 驗證過的地址或網域
```

### AWS 那一側要做的事（主控台操作，不是程式碼）

1. **驗證寄件身分**：到 Amazon SES 主控台驗證 `SES_FROM_ADDRESS` 使用的 Email 地址或整個網域（網域驗證需要加 DNS 記錄，之後任何 `@該網域` 的地址都能寄）。沒驗證過的寄件地址，SES 會直接拒絕請求。
2. **Sandbox 模式的限制**：新建立的 SES 帳號預設在 Sandbox 模式，**只能寄給也驗證過的收件地址**。
   - 只是自己測試（例如想確認驗證信真的能收到）：把測試用的收件信箱也加進 SES 驗證清單即可，不需要離開 Sandbox。
   - 要能寄給任何使用者（正式上線）：需要在 SES 主控台申請「Request production access」，說明用途（交易型通知信：帳號驗證、密碼重設），審核通過後才能寄給未驗證的任意地址。
3. **IAM 權限**：呼叫端（本機或 ECS）需要一組具備 `ses:SendEmail`（建議加 `ses:SendRawEmail` 以防未來改寄 HTML 信）權限的身分。
   - **正式環境（ECS）**：MUST 透過 ECS Task Role 授權，不要把 AWS 金鑰塞進環境變數或 Secrets Manager——`architecture.md` 既有的「IAM Task Role 僅授予讀取本專案 Secret 路徑的最小權限」原則，同樣適用於這裡：Task Role 額外掛一條僅限 `ses:SendEmail`（可用 SES identity ARN 限縮 resource）的 policy 即可，不需要額外的長期憑證。
   - **本機測試**：`boto3` 會依序找 `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` 環境變數、或 `~/.aws/credentials`（`aws configure` 設定過的話）。本機測試建議用一組僅有 `ses:SendEmail` 權限的 IAM 使用者金鑰，不要用帳號的長期管理員金鑰。

### 目前架構文件遺漏的地方

`specs/architecture.md` 第 6 節「AWS 部署架構」列出的 Secrets Manager 清單（`DATABASE_URL`、`JWT_SECRET`、`TURNSTILE_SECRET_KEY`、`PASSWORD_ENCRYPTION_KEY`、`ABLY_API_KEY`）是在 email 功能（006-member-friends）決定採用 SES 之前寫的，**沒有包含 `EMAIL_BACKEND`／`SES_REGION`／`SES_FROM_ADDRESS`**。正式部署時，ECS Task Definition 的環境變數／Secrets 區塊要一併補上這三個值（`SES_REGION`/`SES_FROM_ADDRESS` 非機密，可直接寫在 Task Definition 的 `environment`，不需要進 Secrets Manager；`EMAIL_BACKEND=ses` 同理）。

---

## 2. AWS 部署所需的環境變數／Secrets 總覽

彙整 `apps/api/app/core/config.py` 目前定義的所有設定值，標註哪些是機密（要進 Secrets Manager）、哪些是一般環境變數即可：

| 變數 | 機密？ | 說明 |
|---|---|---|
| `DATABASE_URL` | 是 | RDS PostgreSQL 連線字串 |
| `JWT_SECRET` | 是 | 管理權杖／會員權杖簽章密鑰 |
| `TURNSTILE_SITE_KEY` | 否 | 前端用，可公開 |
| `TURNSTILE_SECRET_KEY` | 是 | 後端驗證用 |
| `PASSWORD_ENCRYPTION_KEY` | 是 | 團密碼可還原加密用（AES-256-GCM，32 bytes base64） |
| `ABLY_API_KEY` | 是 | 伺服器端發布即時事件用 |
| `CORS_ALLOWED_ORIGINS` | 否 | 預設 `http://localhost:4200`，正式環境需改為實際網域 |
| `FRONTEND_BASE_URL` | 否 | 用來組驗證信/重設信裡的連結，正式環境需改為實際網域 |
| `EMAIL_BACKEND` | 否 | 正式環境需設為 `ses`（見第 1 節） |
| `SES_REGION` | 否 | 見第 1 節 |
| `SES_FROM_ADDRESS` | 否 | 見第 1 節，需先在 SES 完成驗證 |
| `ADMIN_PIN_MAX_ATTEMPTS`、`ADMIN_PIN_LOCKOUT_MINUTES`、`ADMIN_TOKEN_TTL_HOURS`、`AUTO_DISBAND_IDLE_MINUTES`、`TURNSTILE_TIMEOUT_SECONDS`、`MEMBER_ACCESS_TOKEN_TTL_MINUTES`、`MEMBER_REFRESH_TOKEN_TTL_DAYS` | 否 | 皆有合理預設值，正式環境通常不需要覆寫 |

### 寫在 Secrets Manager 裡的值，後端程式碼需要修改嗎？

**不用改。**

後端本來就是用 `pydantic-settings`（`apps/api/app/core/config.py`）從**環境變數**讀取所有設定值，本地開發時額外從 `.env` 檔案讀，正式環境則完全靠環境變數——程式碼裡沒有、也不需要任何直接呼叫 AWS SDK 讀取 Secrets Manager 的邏輯（已確認整個 `apps/api/app/` 目錄底下沒有任何 `boto3` 的 `secretsmanager` API 呼叫）。

真正接起 Secrets Manager 的地方是 **ECS Task Definition**，不是程式碼：在 Task Definition 的 `secrets` 區塊（注意不是 `environment` 區塊）用 `valueFrom` 指向 Secrets Manager 的 ARN。這是 AWS 自己做的事——容器啟動前，ECS 會先去 Secrets Manager 撈值，**注入成一般的環境變數**再啟動應用程式。所以從 Python 程式的角度看，它看到的就是普通的環境變數，跟本地開發時讀 `.env` 完全一樣，程式碼分辨不出這個值是「寫死在 Task Definition」還是「從 Secrets Manager 撈來的」。這正是 `specs/architecture.md` 第 6 節原本定案的做法（"皆由 ECS Task 透過 Secrets Manager 注入環境變數存取"）。

**唯一要注意的地方**：Secrets Manager 裡存的 Secret 名稱不用跟環境變數名稱一樣（那是 Secret 自己的識別名），但 **Task Definition 裡 `secrets` 陣列每一項的 `name` 欄位，必須跟上方表格中的變數名稱完全對上**（例如 `JWT_SECRET`、`DATABASE_URL`）。這是部署設定要對齊的地方，不是程式碼要改的地方——設定錯了，應用程式啟動時 `pydantic-settings` 會因為缺少必填欄位直接報錯，容易發現。

---

## 3. 尚未實作的維運項目（已知缺口）

以下項目在 `.specify/memory/constitution.md`「未來規劃事項（明確排除於當前實作範圍）」章節已有更詳細的說明，這裡只列重點、標註為上線前應優先處理：

- **資料保留與帳號刪除政策**：目前沒有會員刪除帳號、GDPR 式個資刪除/匿名化的機制。若會員的 Email、密碼雜湊需要遵循歐盟等地區法規，**MUST 在正式對外營運前補上**。
- **可觀測性（Observability）**：目前沒有接 Sentry / CloudWatch 等監控與錯誤追蹤。至少建議在上線前補上：Ably 連線/斷線率、計分 API（+1/-1）延遲、1 小時自動解散排程任務的執行狀況、Turnstile 驗證成功/失敗率、**以及本文件新增的 SES 寄信成功/失敗率**（`SesEmailSender` 目前寄信失敗只會記錄 log、不會讓呼叫端的請求失敗，若沒有監控，寄信持續失敗也不會有人發現）。
- **資料庫備份與災難復原**：RDS 的自動備份頻率、保留天數、PITR、跨 AZ/區域備援策略、對應的 RPO/RTO，目前皆未定義。
- **CI/CD 中 Alembic migration 的執行時機與失敗處理**：部署到 ECS 時 migration 要在部署前獨立執行、還是容器啟動時自動跑；失敗時的 rollback 策略；多個 ECS Task 同時啟動時避免 migration 重複執行的機制——皆待補。

---

## 4. 上線前檢查清單

- [ ] `EMAIL_BACKEND=ses`、`SES_REGION`、`SES_FROM_ADDRESS` 已設定（見第 1 節）
- [ ] SES 寄件地址／網域已完成驗證
- [ ] SES 已離開 Sandbox（若需要寄給任意使用者）
- [ ] ECS Task Role 已授予 `ses:SendEmail` 權限
- [ ] `FRONTEND_BASE_URL`、`CORS_ALLOWED_ORIGINS` 已改為正式網域（而非 `localhost`）
- [ ] Secrets Manager 已建立所有機密值（見第 2 節表格），ECS Task Definition 正確引用
- [ ] 已決定資料保留/帳號刪除政策（或明確記錄為「暫緩，待有實際使用者/法規要求時處理」）
- [ ] 已接上至少基本的錯誤追蹤/監控（Observability）
- [ ] RDS 備份策略已設定並記錄 RPO/RTO
- [ ] CI/CD 的 migration 執行策略已定案並測試過（含多 Task 同時啟動的情境）
