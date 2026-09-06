# Phase 0 Research: 會員與好友系統

## 1. 決議：`app/domains/member/` 由既有 stub 擴充，新增 `app/domains/friend/` 獨立模組

**Decision**：`members` 表與 `Member` model 已由 001 建立最小 stub（僅 `id`/`nickname`/`created_at`，供 `groups.created_by_member_id`、`roster_entries.member_id` 的 FK 參照）。本 feature 以 **ALTER TABLE** 方式為既有 `members` 表新增 `email`/`password_hash`/`user_number`/`verification_status`/`token_version` 五個欄位（而非 DROP 重建），並在 `app/domains/member/` 下新增 `security.py`（密碼雜湊、JWT 簽發/驗證、使用者編號產生）、擴充 `models.py`/`schemas.py`/`service.py`/`router.py`，涵蓋註冊、登入、Email 驗證、忘記/修改密碼、個人設定、使用者編號搜尋。好友關聯（`FriendRequest`）雖然外鍵指向 `members`，但關注點（邀請/接受/拒絕/解除的狀態機）與會員帳號本身（認證、個人資料）截然不同，故另建 `app/domains/friend/` 模組，僅透過 `member_id` 讀取 `members` 表既有欄位（暱稱、驗證狀態），不重新定義或搬移其擁有權。

**Rationale**：呼應 constitution 原則 VI；`members` 表已存在且有既有 FK 依賴（001/003 皆已讀寫 `member_id`/`nickname`），ALTER 而非重建可保留既有資料與遷移歷史。好友系統與會員帳號本身是兩個不同的業務關注點（帳號安全 vs. 社交關係），拆分為兩個模組使兩者可獨立測試/演進，避免 `member/service.py` 因好友邏輯而膨脹。

## 2. 決議：會員 JWT 沿用 001 之 `admin_token` 模式，擴充為 access + refresh 雙 token

**Decision**：`app/domains/member/security.py` 比照 `app/domains/group/security.py` 既有的 `issue_admin_token`/`decode_admin_token`/`require_admin` 三段式設計（`pyjwt` HS256、payload 內帶版本號、`require_*` 為 FastAPI dependency），但依 `architecture.md` §3.1 既有端點清單（`POST /auth/login` 換發 access/refresh、`POST /auth/refresh` 換發新 access token）擴充為雙 token：

- **Access token**：短效期（設定值 `member_access_token_ttl_minutes`，預設 60 分鐘），payload 含 `member_id`、`token_version`、`type: "access"`；一般 API 呼叫使用 `Authorization: Bearer <access_token>`。
- **Refresh token**：長效期（設定值 `member_refresh_token_ttl_days`，預設 30 天），payload 含 `member_id`、`token_version`、`type: "refresh"`；僅 `POST /auth/refresh` 接受，換發新 access token（不換發新 refresh token，維持原 refresh token 效期不變，簡化實作、避免無限滑動續期）。
- 兩者皆於驗證時比對 `payload["token_version"] == members.token_version`（純無狀態設計，不另建 session/refresh-token 黑名單資料表）；`token_version += 1`（修改密碼、忘記密碼重設）會同時使兩種 token 一併失效，滿足 FR-015/FR-026「其他裝置 session 失效」之要求——「保留本裝置」（FR-026）的實作方式是：執行修改密碼的當下，後端立即為「本次請求所用的 token」重新核發一組新 token（新 `token_version` 值），前端以此覆蓋本地儲存，其餘裝置仍持舊 `token_version` 因而失效。

**Rationale**：與既有 `admin_token`/`admin_token_version` 機制精神一致（無狀態、版本號比對），複用已驗證可行的模式，不需新增 session store 或 Redis 等額外基礎設施；`architecture.md` 已明確定案 access+refresh 雙 token 端點形狀，本決議僅補完其內部一致的失效機制設計。

## 3. 決議：密碼雜湊於 `member` 模組獨立定義 `CryptContext`，不重用 `group/security.py` 之私有物件

**Decision**：`app/domains/member/security.py` 自行建立 `CryptContext(schemes=["bcrypt"], deprecated="auto")`（與 `group/security.py` 內部同名物件設定相同，但為獨立實例），提供 `hash_password`/`verify_password`。

**Rationale**：`group/security.py` 的 `_pwd_context` 為模組內部私有變數（底線前綴），跨模組直接 import 私有物件違反 constitution 原則 VI 之模組邊界（不得依賴其他模組的內部實作細節）；兩者的雜湊需求（bcrypt、無特殊參數）恰好相同純屬巧合，非共用同一套「密碼規則」的理由——會員密碼與管理 PIN 碼是完全不同的安全性質（見 constitution 原則 IV），維持程式碼路徑分離同時也避免未來兩者規則各自演化時互相牽動。

## 4. 決議：Turnstile 驗證直接重用 `app/core/turnstile.py`

**Decision**：`POST /auth/register` 直接呼叫既有的 `app/core/turnstile.py` 之 `verify_turnstile_token(token, remote_ip)`，不新增任何 Turnstile 相關程式碼。

**Rationale**：`app/core/turnstile.py` 原始檔案註解已明確預告「Only the 'register' and 'create group' endpoints call this」——001 建立此共用模組時即已將本 feature 的重用情境納入設計，屬於 `app/core/` 下刻意設計給多個 domain 共用的基礎設施，非重複實作。

## 5. 決議：Email 寄送採 Amazon SES（透過 `boto3`），以 `EmailSender` 介面隔離外部依賴

**Decision**：新增 `app/core/email.py`，定義最小介面（`async def send_email(to: str, subject: str, body: str) -> None`）與兩種實作：`SesEmailSender`（透過 `boto3` 呼叫 SES `send_email` API，正式環境使用）、`LoggingEmailSender`（僅將收件人/主旨/內文寫入應用程式日誌，不實際寄送，本地開發與測試預設使用）。以設定值 `email_backend: Literal["ses", "log"] = "log"` 選擇實作，正式環境（AWS 部署）透過環境變數切換為 `"ses"`。寄送失敗（SES API 呼叫異常）MUST 僅記錄錯誤、MUST NOT 讓呼叫端的請求（註冊、忘記密碼）失敗——帳號/重設請求本身已透過資料庫交易確立為成功，寄信是「盡力而為」的通知動作，此與 constitution 原則 X（`publish()`／Ably 事件發布之相同失敗容忍哲學）一致；使用者可透過「重新發送驗證信」（FR-011）或重新觸發忘記密碼流程復原。

**Rationale**：`specs/architecture.md` 之 AWS 部署章節已確立 ECS/RDS/Secrets Manager 皆屬 AWS 生態，SES 為同生態系最直接的寄信方案，不需引入第三方寄信商（Mailgun/SendGrid）額外的金鑰管理與網路依賴；`spec.md` Assumptions 明確將寄信商選型留待本次 `/speckit-plan` 決定。介面抽象化的理由與 `app/core/realtime.py` 的 `publish()` 完全相同——集中唯一對外 I/O 出口、本地測試不需真實外部服務即可驗證業務邏輯（驗證信/重設信內容經 `LoggingEmailSender` 可在測試斷言中直接檢查）。

## 6. 決議：帳號相關速率限制依「範圍」選擇機制——IP 範圍沿用既有 slowapi，帳號範圍改用 DB 時間戳比對

**Decision**：
- **FR-002a（登入）**、**FR-013a（忘記密碼觸發）**、**FR-020（使用者編號搜尋）**：範圍皆為「per-IP」，直接沿用 `app/core/rate_limit.py` 既有的 `@limiter.limit("N/minute")` 裝飾器模式（與 `/groups/reauth` 相同的 per-IP 機制），不新增基礎設施。FR-002a 明確排除帳號鎖定（見 spec Clarifications 2026-09-01），故不比照 `admin_locked_until` 的帳號層級鎖定模式，僅 per-IP 節流。
- **FR-011（重新發送驗證信）**：範圍明確限定「同一帳號」，且此端點本身即需登入（`require_member`），slowapi 預設 `key_func=get_remote_address` 為 per-IP，不直接符合「同一帳號」語意（同一帳號換裝置/換網路即可繞過）。改為在 `member/service.py` 內比對 `members` 表新增的 `last_verification_sent_at` 欄位（或改查 `email_verification_tokens` 該會員最新一筆 `created_at`）距今是否 < 60 秒，比照 `group/service.py` 既有的 `admin_locked_until` 時間戳比對模式處理，未新增 slowapi 額外設定。

**Rationale**：IP 範圍的限制與 001 既有的 `/groups/reauth` 端點性質相同（防護目標是任意來源的暴力嘗試），直接複用零額外成本；帳號範圍的限制若誤用 IP-based 機制會產生語意落差（多裝置繞過），DB 時間戳比對與既有 `admin_locked_until` 模式一致，維持程式碼風格統一而不需引入 slowapi 的自訂 `key_func`（需額外解碼 JWT 才能取得 `member_id`，反而更複雜）。

## 7. 決議：`FriendRequest` 單表狀態機、`Group.forgot-admin-pin` 為跨模組串接（router 層）

**Decision**：`friend_requests` 表結構、`pending → accepted/rejected`、`accepted → unfriended` 狀態機、部分唯一索引（同一組使用者任何時刻最多一筆 `pending`，不分方向）皆依 `architecture.md` §2.2 既有 DDL 原樣採用，不重新設計。`POST /groups/{group_id}/forgot-admin-pin`（FR-028~033）為橫跨 `member` 與 `group` 兩個模組的端點——比照 003 之 research.md #2/#4「router 層串接」慣例，端點本體置於 `group/router.py`（因為它本質是「重設 `groups.admin_pin_hash`／`admin_token_version`」，與既有 `regenerate-admin-pin` 端點高度相似，複用 `group/service.py` 既有的 PIN 重設核心邏輯），但依賴 `member/security.py` 之 `require_member` dependency 驗證登入狀態，並額外比對 `group.created_by_member_id == member.id`（否則 `ADMIN_TOKEN_INVALID` 等級的 403）；成功後複用既有的 `link.regenerated`（`link_type: "admin"`）廣播（002 已建立），不新增新的 Ably 事件類型。

**Rationale**：`FriendRequest` 的狀態機設計已由 `spec.md` Assumptions 段落明確定案並留給 plan 僅決定「欄位與索引設計」，`architecture.md` 已完整给出，無需二次設計。`forgot-admin-pin` 與「主動重設管理 PIN 碼」在效果上完全相同（FR-032a 明文要求沿用相同廣播機制），刻意複用 `group` 模組既有邏輯可避免兩套重設 PIN 碼程式碼路徑產生行為分歧的風險；此端點放在 `group/router.py` 而非 `member/router.py`，因為它修改的資料實體（`groups` 表欄位）屬於 `group` 模組所有權範圍，僅驗證關卡（登入 + 建立者比對）需要跨模組讀取 `member` 資訊，符合「router 層知道呼叫前後差異／可跨模組協調」的既有慣例。

## 8. 決議：使用者編號產生規則與碰撞重試

**Decision**：`user_number` 為 8 碼隨機英數字，字元集排除易混淆字元（`0/O/1/I/l`），實際字元集採 `23456789ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz`（52 碼，排除 `0 O 1 I l`）；產生時使用 `secrets.choice` 逐碼隨機，寫入 `members` 前先查詢 `LOWER(user_number)` 是否已存在（對應 `ux_members_user_number_ci` 唯一索引），碰撞則重新產生（迴圈上限 10 次，理論碰撞率極低，超過上限視為系統異常直接拋出 500，不特別處理——`spec.md` Edge Cases 已明定「不需額外告警或人工介入」，此為程式層級的最終保險而非常態路徑）。

**Rationale**：字元集選擇符合 FR-018 之可讀性要求（避免視覺混淆字元）；「先查詢再寫入」而非「直接嘗試 INSERT 並捕捉唯一鍵衝突」是因為需要同時滿足「產生」與「顯示」的即時性（註冊流程需立即拿到最終編號用於後續畫面），若改用 INSERT 衝突重試會需要在同一交易內多次 INSERT/ROLLBACK，比先查詢後寫入更複雜且無效能優勢（此表寫入頻率低，一次查詢成本可忽略）。

## 9. 決議：密碼複雜度採業界最低標準——至少 8 碼、至少 1 個字母 + 1 個數字

**Decision**：`CreateMemberRequest`/`ResetPasswordRequest`/`ChangePasswordRequest` 之 Pydantic 驗證規則：密碼長度 ≥ 8 碼，MUST 至少包含 1 個英文字母與 1 個數字（不強制大小寫混合、不強制特殊符號），前後端皆須驗證（比照 constitution 原則 VIII 之一致性慣例）。

**Rationale**：`spec.md` Assumptions 明確留待 plan 決定，僅要求「業界常見的最低安全標準」；8 碼＋字母＋數字為 OWASP 建議的最低門檻起點，不過度增加使用者輸入摩擦（比照 constitution 原則 XI 對「加入團」刻意不過度設計摩擦的精神，密碼規則同樣不追求企業級強制輪換/特殊符號等高摩擦規則）。

## 10. 決議：`FR-024`（暱稱快照）不需新的 schema 變更，僅為既有欄位的行為邊界確認

**Decision**：`roster_entries.nickname` 自 001 建立以來即為獨立欄位（非透過 `member_id` 即時查詢 `members.nickname` 的計算值），本 feature 對 `PATCH /members/me/nickname` 的實作僅更新 `members.nickname` 本身，不對任何既有 `roster_entries` 列做連動更新——此為現有 schema 設計自動滿足的行為，非本 feature 需新增的程式碼。「Player 記錄於建立當下複製會員當時暱稱」之寫入時機（FR-024 前半段）屬於 004 spec（加入流程）的職責邊界，本 feature 僅確保 `member.nickname` 修改本身不會意外回溯影響既有 `roster_entries`（已自動成立）。

**Rationale**：避免誤將 FR-024 誤讀為本 feature 需要新增觸發器/連動更新邏輯——實際上「不連動」才是正確行為，且此不連動性完全來自現有 schema 的欄位獨立性，本決議僅是明確記錄此邊界供未來 004 spec 的 plan 參照，避免重複確認。
