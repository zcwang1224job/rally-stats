# Rally Stats — 系統架構與技術實作計畫（Project-Wide）

**Date**: 2026-08-31
**Status**: Draft
**Scope**: 涵蓋 `specs/001-create-manage-group` ~ `specs/007-live-scoreboard` 全部 7 份已定案功能規格；本文件為專案級技術實作計畫，非單一 feature 的 `plan.md`（依使用者於本次 `/speckit-plan` 執行時的選擇，見下方「與 feature specs 的對應關係」）。

**Input**: 使用者於本次 `/speckit-plan` 提供之完整技術棧與架構決策（Angular 20 + FastAPI + PostgreSQL + Ably + Docker/AWS），已定案項目直接採納，未定案的技術性空白由本文件依專案既有慣例（constitution、各 spec 之 Assumptions 段落）補齊並標註為 Decision。

## 與 Feature Specs 的對應關係

| Spec | 功能 | 本文件章節涉及範圍 |
|---|---|---|
| 001-create-manage-group | 開團與管理 | Group、Match Scoring Settings、Admin Credential、Roster Entry、Guest Session Token 核心欄位；開團/管理/解散/PIN 相關 API |
| 002-court-management | 場地管理 | Court、All-Courts Control Panel Token；場地 CRUD、連結重新產生 API；`court:{group_id}:{court_id}` 頻道設計 |
| 003-schedule-rotation | 賽程與輪替名單 | Match、PairHistory、Partnership；Round/賽程表相關 API；排點演算法之資料相依 |
| 004-join-group | 加入團 | 加入流程 API；Guest Session Token 生命週期；`current_member_count` 原子更新 |
| 005-member-view | 團內成員視圖 | 唯讀查詢 API（賽程/戰績/對戰紀錄）；退出組團 API |
| 006-member-friends | 會員與好友系統 | Member、EmailVerificationToken/PasswordResetToken、FriendRequest；認證、好友、忘記管理 PIN 碼 API |
| 007-live-scoreboard | 即時計分板與控制板 | 計分/提前結束 API 的原子操作設計；斷線重連；控制板權限邊界 |

---

## Constitution Check

*對照 `.specify/memory/constitution.md` 之核心原則 I–XI，逐條確認本架構的因應方式。*

| 原則 | 因應方式 |
|---|---|
| I. 型別安全 | 前端 `strict: true` TypeScript；後端 Pydantic v2 + SQLAlchemy 2.0 型別化 ORM 模型；OpenAPI schema 作為前後端型別對齊的單一事實來源（見「專案結構」）。 |
| II. 測試優先 | 核心領域邏輯（排點演算法、比分原子操作、Guest Token 生命週期）於 `apps/api/tests/unit` 建立單元測試；「開團→加入→排點→計分」建立至少一條整合測試（見各模組實作順序章節的驗收標準）。 |
| III. 即時性與一致性 | 全數比分/賽程寫入皆先落地 PostgreSQL 交易，成功後才由後端發布 Ably 事件（見「資料庫為單一事實來源」小節）；斷線提示與強制覆蓋行為見 007 spec、本文件 API 章節之心跳端點設計。 |
| IV. 權限與安全 | 管理 PIN 碼雜湊、通關密碼可還原加密、會員密碼 bcrypt 雜湊，三者使用不同機制且不共用程式碼路徑（見「認證與憑證」小節）。 |
| V. UX 一致性 | 解散團、刪除場地、踢除成員、解除好友、重新產生連結等破壞性操作，前端 MUST 二次確認；已於各 spec 定義，本文件不重複列出。 |
| VI. 可維護性 | 後端依領域拆分 `app/domains/{group,court,schedule,member,friend,scoring}`，模組間僅透過 service 層介面溝通（見「後端專案結構」）。 |
| VII. 無障礙 | 密碼狀態鎖頭圖示需搭配文字標籤/`aria-label`，已於 004 spec 定義；前端元件庫選型（Angular Material 或 Tailwind）皆需支援此模式。 |
| VIII. i18n 與時區 | 前端一律透過語系 key 呼叫文字；後端一律回傳語意化錯誤代碼；絕對時間戳用 `TIMESTAMPTZ`，活動時間區間用不含時區之 `TIME`（見「資料庫 ER 設計」）。 |
| IX. 可攜性 | 前後端皆容器化，本地 `docker-compose` 與正式 AWS 環境共用同一組映像建置流程（見「Docker 化」與「AWS 部署」）。 |
| X. 伺服器為單一事實來源 | 所有 Ably Token 僅授予 `subscribe`（除後端本身持有的伺服器端 API Key 外），前端 MUST NOT 具備 `publish` 權限；已於本文件 API/Ably 章節逐一標註。 |
| XI. 防機器人 | Turnstile 僅套用於註冊與開團兩端點，採 fail-closed；見「認證與憑證」小節。 |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

---

## 1. 系統架構圖（文字描述）

```
┌─────────────────────────┐         ┌──────────────────────────────┐
│   使用者瀏覽器 (SPA)      │         │        Cloudflare              │
│  Angular 20 (Standalone) │────────▶│   Turnstile siteverify API     │
│  - Signals + RxJS        │  (後端  └──────────────────────────────┘
│  - Ably JS SDK (訂閱)     │   同步呼叫)
└───────────┬──────────────┘
            │ HTTPS (REST, HttpClient)      │ Ably Realtime (WSS，
            │                                 │  前端持 Token 訂閱)
            ▼                                 ▼
┌─────────────────────────────────────────────────────────────┐
│                Application Load Balancer (ALB)                │
│   /api/*  → backend target group    /*  → frontend target group│
└───────────┬───────────────────────────────┬───────────────────┘
            ▼                                 ▼
┌───────────────────────────┐      ┌──────────────────────────┐
│  ECS Fargate: backend      │      │ ECS Fargate: frontend      │
│  FastAPI + Uvicorn workers │      │ Nginx (Angular dist 靜態檔) │
│  - SQLAlchemy 2.0 async    │      │ 或改用 S3 + CloudFront      │
│  - Ably REST SDK (發布)     │      └──────────────────────────┘
└──────┬──────────┬──────────┘
       │          │
       ▼          ▼
┌────────────┐  ┌────────────────────┐
│ Amazon RDS │  │   Ably (SaaS)        │
│ PostgreSQL │  │  - court:{gid}:{cid}  │
└────────────┘  │  - group:{gid}:notifications │
                 └────────────────────┘

支援服務（皆由 ECS Task 透過 Secrets Manager 注入環境變數存取）：
- AWS Secrets Manager：DB 連線字串、JWT 簽章密鑰、Ably API Key、
  Turnstile secret key、通關密碼加密金鑰（AES-256-GCM）
- Amazon ECR：前後端容器映像倉庫
- GitHub Actions：CI（lint/型別檢查/測試）→ build image → push ECR
  → 更新 ECS Service（強制重新部署或 CodeDeploy blue/green）
```

**關鍵資料流原則**（呼應 constitution 原則 X）：所有寫入操作（+1/-1、Next Round、踢除成員、連結重新產生……）皆為「瀏覽器 → ALB → FastAPI → PostgreSQL 交易 → FastAPI 以伺服器端 Ably API Key 發布事件 → Ably → 訂閱端瀏覽器」的單向流程；瀏覽器持有的 Ably Token 一律不具 `publish` 權限，僅能 `subscribe`。

---

## 2. 資料庫 ER 設計

### 2.1 設計決策摘要

- **Match 與 MatchResult 合併為單一 `matches` 資料表**：比賽本身（Match）與比賽結果（MatchResult）在讀寫時機上高度重疊（狀態轉為 `completed` 的瞬間即產生結果），拆成兩張表需要交易內同步寫入兩處、徒增複雜度。改以 `matches.winner_team`（nullable）欄位承載結果——僅當 `status = 'completed'` 時填入，`abandoned`/`queued`/`in_progress` 皆為 NULL；戰績/對戰紀錄查詢一律加上 `WHERE status = 'completed'` 篩選。此決策不改變任何 spec 定義的可觀察行為。
- **Match Scoring Settings 內嵌於 `groups` 表**：屬於 1:1、必然存在的團級別設定，不獨立成表；`matches` 建立當下複製三個數值到自身欄位（快照），落實 constitution 原則 III 的快照要求。
- **Guest Session Token 內嵌於 `roster_entries` 表**：與 Player 記錄一對一綁定，獨立成表僅增加 JOIN 成本，改以 `roster_entries.guest_session_token`（nullable、唯一）欄位承載。
- **`wait_count` 以 nullable INTEGER 表示「無限大」**：`NULL` 代表尚未上過場（優先度最高，排序時視為大於任何非 NULL 值）；首次上場後寫入 `0`。
- **所有內部主鍵採 UUID**（`gen_random_uuid()`），唯二例外：`groups.group_number`（PostgreSQL `SEQUENCE`，見下方）與 `members.user_number`（應用層產生的 8 碼隨機字串，非主鍵、僅唯一索引），兩者皆為刻意設計的「可分享識別碼」而非內部主鍵。

### 2.2 資料表定義

```sql
-- ══════════ 系統參數 ══════════
CREATE TABLE system_config (
    key         VARCHAR(64) PRIMARY KEY,
    value       TEXT NOT NULL,
    description TEXT
);
-- 初始資料：('max_group_members', '200'), ('default_timezone', 'Asia/Taipei')

-- ══════════ 會員（006） ══════════
CREATE TABLE members (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email               VARCHAR(255) NOT NULL,       -- 已正規化為小寫
    password_hash       VARCHAR(255) NOT NULL,       -- bcrypt
    nickname            VARCHAR(20),                  -- NULL = 尚未完成首次設定
    user_number         VARCHAR(8) NOT NULL,          -- 8 碼隨機英數，原始大小寫保留顯示
    verification_status VARCHAR(16) NOT NULL DEFAULT 'unverified', -- unverified | verified
    token_version       INT NOT NULL DEFAULT 0,       -- JWT 失效機制
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_members_email ON members (email);
CREATE UNIQUE INDEX ux_members_user_number_ci ON members (LOWER(user_number)); -- 大小寫不敏感唯一性/比對

CREATE TABLE email_verification_tokens (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    member_id  UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    token      UUID NOT NULL DEFAULT gen_random_uuid(),
    expires_at TIMESTAMPTZ NOT NULL,   -- 建立時間 + 24 小時
    used_at    TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_evt_token ON email_verification_tokens (token);

CREATE TABLE password_reset_tokens (
    id         UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    member_id  UUID NOT NULL REFERENCES members(id) ON DELETE CASCADE,
    token      UUID NOT NULL DEFAULT gen_random_uuid(),
    expires_at TIMESTAMPTZ NOT NULL,
    used_at    TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_prt_token ON password_reset_tokens (token);

CREATE TABLE friend_requests (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    requester_id UUID NOT NULL REFERENCES members(id),
    addressee_id UUID NOT NULL REFERENCES members(id),
    status       VARCHAR(16) NOT NULL DEFAULT 'pending', -- pending | accepted | rejected | unfriended
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (requester_id <> addressee_id)
);
-- 同一組使用者任何時刻最多一筆 pending（不分方向）：
CREATE UNIQUE INDEX ux_friend_requests_pending_pair
    ON friend_requests (LEAST(requester_id, addressee_id), GREATEST(requester_id, addressee_id))
    WHERE status = 'pending';

-- ══════════ 團（001） ══════════
CREATE SEQUENCE group_number_seq START WITH 100000 INCREMENT BY 1;

CREATE TABLE groups (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_number              BIGINT NOT NULL DEFAULT nextval('group_number_seq'),
    name                      VARCHAR(30) NOT NULL,
    password_ciphertext       BYTEA,               -- AES-256-GCM，NULL = 無通關密碼
    password_nonce            BYTEA,
    max_members               INT NOT NULL,
    match_mode                VARCHAR(8) NOT NULL,  -- singles | doubles
    scheduling_mechanism      VARCHAR(16) NOT NULL, -- fair_rotation | fixed_partner | individual_mixed | manual
    activity_time_start       TIME,                 -- 無時區，場地時間本身
    activity_time_end         TIME,
    current_member_count      INT NOT NULL DEFAULT 1,
    status                    VARCHAR(16) NOT NULL DEFAULT 'active', -- active | disbanded
    last_activity_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_by_member_id      UUID REFERENCES members(id), -- NULL = 匿名建立

    admin_pin_hash            VARCHAR(255) NOT NULL,
    admin_failed_attempts      INT NOT NULL DEFAULT 0,      -- PIN 驗證防暴力破解
    admin_locked_until         TIMESTAMPTZ,

    current_round_number      INT NOT NULL DEFAULT 1,
    auto_next_round            BOOLEAN NOT NULL DEFAULT false,

    join_link_token            UUID NOT NULL DEFAULT gen_random_uuid(),
    all_courts_control_panel_token UUID NOT NULL DEFAULT gen_random_uuid(),

    -- 併發控制版本欄位（各自獨立，見 spec 001/002/006 已定案的拆分規則）
    base_settings_version       INT NOT NULL DEFAULT 0,   -- 一般編輯（樂觀鎖）
    join_link_version            INT NOT NULL DEFAULT 0,   -- 樂觀鎖
    all_courts_link_version      INT NOT NULL DEFAULT 0,   -- 樂觀鎖
    admin_token_version          INT NOT NULL DEFAULT 0,   -- PIN 重設（忘記/主動）

    -- 比賽設定快照來源（Match Scoring Settings，附屬於 Group）
    scoring_mode                VARCHAR(8) NOT NULL DEFAULT '21pt', -- 21pt | 15pt | custom
    target_score                 INT NOT NULL DEFAULT 21,
    deuce_threshold               INT NOT NULL DEFAULT 20,
    cap_score                     INT NOT NULL DEFAULT 30
);
CREATE UNIQUE INDEX ux_groups_group_number ON groups (group_number);
CREATE UNIQUE INDEX ux_groups_join_link_token ON groups (join_link_token);
CREATE UNIQUE INDEX ux_groups_all_courts_token ON groups (all_courts_control_panel_token);
CREATE INDEX ix_groups_created_by ON groups (created_by_member_id) WHERE status = 'active';
CREATE INDEX ix_groups_status_last_activity ON groups (status, last_activity_at); -- 1 小時無活動掃描用

-- ══════════ 場地（002） ══════════
CREATE TABLE courts (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id                  UUID NOT NULL REFERENCES groups(id),
    name                      VARCHAR(20) NOT NULL,
    scoreboard_token           UUID NOT NULL DEFAULT gen_random_uuid(),
    control_panel_token        UUID NOT NULL DEFAULT gen_random_uuid(),
    scoreboard_link_version     INT NOT NULL DEFAULT 0,  -- 樂觀鎖，各自獨立
    control_panel_link_version  INT NOT NULL DEFAULT 0,  -- 樂觀鎖，各自獨立
    deleted_at                 TIMESTAMPTZ,               -- 軟刪除
    created_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX ux_courts_scoreboard_token ON courts (scoreboard_token);
CREATE UNIQUE INDEX ux_courts_control_panel_token ON courts (control_panel_token);
-- 同團「目前有效」場地名稱唯一（排除已軟刪除）：
CREATE UNIQUE INDEX ux_courts_group_name_active ON courts (group_id, name) WHERE deleted_at IS NULL;

-- ══════════ 輪替名單 / Player（001, 003, 004, 006） ══════════
CREATE TABLE roster_entries (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id             UUID NOT NULL REFERENCES groups(id),
    member_id            UUID REFERENCES members(id),  -- NULL = Guest
    nickname             VARCHAR(20) NOT NULL,          -- 快照值（會員暱稱變更不回溯）
    status               VARCHAR(16) NOT NULL DEFAULT 'active', -- active | left | kicked
    is_creator           BOOLEAN NOT NULL DEFAULT false,
    joined_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    wait_count           INT,                            -- NULL = 無限大（尚未上場）
    guest_session_token   VARCHAR(64) UNIQUE              -- 隨機字串，僅 Guest 有值
);
CREATE INDEX ix_roster_group_status ON roster_entries (group_id, status);
CREATE INDEX ix_roster_member ON roster_entries (member_id) WHERE member_id IS NOT NULL;

-- ══════════ 固定搭檔（003） ══════════
CREATE TABLE partnerships (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id     UUID NOT NULL REFERENCES groups(id),
    player_a_id  UUID NOT NULL REFERENCES roster_entries(id),
    player_b_id  UUID NOT NULL REFERENCES roster_entries(id),
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (player_a_id <> player_b_id)
);
CREATE UNIQUE INDEX ux_partnership_player_a ON partnerships (player_a_id);
CREATE UNIQUE INDEX ux_partnership_player_b ON partnerships (player_b_id);

-- ══════════ 配對紀錄（003） ══════════
CREATE TABLE pair_history (
    group_id    UUID NOT NULL REFERENCES groups(id),
    player_lo_id UUID NOT NULL REFERENCES roster_entries(id), -- 較小 UUID 排前，避免 (A,B)/(B,A) 重複列
    player_hi_id UUID NOT NULL REFERENCES roster_entries(id),
    pair_count   INT NOT NULL DEFAULT 0,
    PRIMARY KEY (group_id, player_lo_id, player_hi_id)
);

-- ══════════ 比賽（Match + MatchResult 合併，003/007） ══════════
CREATE TABLE matches (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    group_id         UUID NOT NULL REFERENCES groups(id),
    court_id         UUID REFERENCES courts(id),  -- 手動安排建立時即綁定；演算法模式排隊中時可為 NULL
    round_number     INT NOT NULL,
    status           VARCHAR(16) NOT NULL DEFAULT 'queued', -- queued | in_progress | completed | abandoned
    score_a          INT NOT NULL DEFAULT 0,
    score_b          INT NOT NULL DEFAULT 0,
    winner_team      VARCHAR(1),                   -- 'A' | 'B'，僅 completed 時填入
    -- 比賽設定快照（建立當下複製自 groups，不隨後續團設定變更回溯）
    target_score      INT NOT NULL,
    deuce_threshold    INT NOT NULL,
    cap_score          INT NOT NULL,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    started_at        TIMESTAMPTZ,
    ended_at          TIMESTAMPTZ
);
CREATE INDEX ix_matches_group_round ON matches (group_id, round_number);
CREATE INDEX ix_matches_court_status ON matches (court_id, status);
-- 同一場地同時最多一筆 in_progress（併發控制，見手動安排唯一性檢查）：
CREATE UNIQUE INDEX ux_matches_court_in_progress ON matches (court_id) WHERE status = 'in_progress';

CREATE TABLE match_participants (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    match_id         UUID NOT NULL REFERENCES matches(id) ON DELETE CASCADE,
    roster_entry_id  UUID NOT NULL REFERENCES roster_entries(id),
    team             VARCHAR(1) NOT NULL -- 'A' | 'B'
);
CREATE INDEX ix_match_participants_match ON match_participants (match_id);
CREATE INDEX ix_match_participants_roster ON match_participants (roster_entry_id);
```

### 2.3 實體關係摘要

```
system_config (獨立參數表)

members 1───* roster_entries (member_id, 可為 NULL=Guest)
members 1───* email_verification_tokens
members 1───* password_reset_tokens
members *───* members  (透過 friend_requests，方向性關係)
members 1───* groups (created_by_member_id, 可為 NULL=匿名建團)

groups 1───* courts
groups 1───* roster_entries
groups 1───* partnerships
groups 1───* pair_history
groups 1───* matches

courts 1───* matches (court_id, 可為 NULL)

matches 1───* match_participants *───1 roster_entries

partnerships: roster_entries 1───1 partnerships.player_a_id
              roster_entries 1───1 partnerships.player_b_id
```

---

## 3. API 端點清單

### 3.1 REST 端點

> 錯誤回應一律回傳語意化錯誤代碼（例如 `GROUP_PASSWORD_INCORRECT`、`GROUP_FULL`、`GROUP_DISBANDED`、`CAPTCHA_EXPIRED`、`CAPTCHA_INVALID`），不回傳寫死中文字串。

**認證與會員（006）**

| Method | Path | 說明 | 備註 |
|---|---|---|---|
| POST | `/auth/register` | 會員註冊 | Turnstile 驗證（fail-closed） |
| POST | `/auth/login` | 登入，換發 access/refresh token | |
| POST | `/auth/refresh` | 換發新 access token | |
| GET | `/auth/verify-email/{token}` | Email 驗證 | |
| POST | `/auth/resend-verification` | 重新發送驗證信 | 需登入；1 分鐘速率限制 |
| POST | `/auth/forgot-password` | 送出忘記密碼信 | 依 IP / 目標 Email 速率限制 |
| POST | `/auth/reset-password/{token}` | 重設密碼 | 成功後所有裝置 session 失效 + 標記已驗證 |
| GET | `/members/me` | 取得自己的會員資訊（含使用者編號） | |
| PATCH | `/members/me/nickname` | 修改暱稱 | |
| PATCH | `/members/me/password` | 修改密碼 | 需驗證目前密碼；成功後除本裝置外 session 失效 |
| GET | `/members/me/groups` | 自己建立過的所有團（含已解散） | 供忘記管理 PIN 碼列表 |
| GET | `/members/me/match-history` | 跨團對戰紀錄與彙總統計 | |
| GET | `/members/search?user_number=` | 依使用者編號搜尋會員 | 速率限制；排除未驗證帳號 |
| GET | `/friends` | 好友列表（分頁、依暱稱/使用者編號篩選） | |
| POST | `/friends/requests` | 發送好友邀請 | body: `addressee_user_number` |
| GET | `/friends/requests/incoming` | 待自己回覆的邀請清單 | |
| POST | `/friends/requests/{id}/accept` | 接受邀請 | |
| POST | `/friends/requests/{id}/reject` | 拒絕邀請 | |
| DELETE | `/friends/{friend_request_id}` | 解除好友 | 二次確認於前端 |

**團（001）**

| Method | Path | 說明 | 備註 |
|---|---|---|---|
| GET | `/groups` | 開團列表（搜尋場地名稱/ID、時間區間篩選、分頁） | |
| POST | `/groups` | 建立團 | Turnstile 驗證（fail-closed） |
| GET | `/groups/{group_id}` | 團的公開資訊（供加入前預覽） | |
| POST | `/groups/{group_id}/verify-password` | 驗證通關密碼 | 無次數限制 |
| POST | `/groups/reauth` | 組團編號 + PIN 碼 → 管理 Token | 防暴力破解速率限制 |
| GET | `/groups/{group_id}/admin` | 管理頁資料（需管理 Token） | |
| PATCH | `/groups/{group_id}` | 編輯團名/時間/比賽模式/排程機制/密碼 | 樂觀鎖 `base_settings_version` |
| PATCH | `/groups/{group_id}/scoring-settings` | 編輯比賽設定 | 樂觀鎖 `base_settings_version` |
| POST | `/groups/{group_id}/disband` | 解散團 | 二次確認；觸發 `group.disbanded` 廣播 |
| POST | `/groups/{group_id}/regenerate-join-link` | 重新產生加入連結 | 樂觀鎖 `join_link_version` |
| POST | `/groups/{group_id}/regenerate-all-courts-link` | 重新產生全部場地控制板連結 | 樂觀鎖 `all_courts_link_version` |
| POST | `/groups/{group_id}/regenerate-admin-pin` | 主動重設管理 PIN 碼 | 樂觀鎖 `admin_token_version`；廣播 `link.regenerated`(admin) |
| POST | `/groups/{group_id}/forgot-admin-pin` | 忘記管理 PIN 碼（會員限定） | 驗證 `created_by_member_id`；同上廣播機制 |
| GET | `/groups/{group_id}/link-status?type=all-courts` | 全部場地控制板心跳檢查 | 每 5 分鐘輪詢；一併檢查解散狀態 |
| DELETE | `/groups/{group_id}/members/{roster_entry_id}` | 踢除成員 | |

**加入（004）**

| Method | Path | 說明 |
|---|---|---|
| GET | `/join/{join_link_token}` | 解析加入連結，回傳團預覽/錯誤狀態 |
| POST | `/groups/{group_id}/join` | 送出加入請求（密碼 + 暱稱，或已登入會員） | 原子性 `current_member_count` 檢查 |

**場地（002）**

| Method | Path | 說明 | 備註 |
|---|---|---|---|
| POST | `/groups/{group_id}/courts` | 新增場地 | |
| PATCH | `/courts/{court_id}` | 重新命名場地 | 樂觀鎖 `version` |
| DELETE | `/courts/{court_id}` | 軟刪除場地 | 有進行中比賽時提示；轉為 abandoned |
| POST | `/courts/{court_id}/regenerate-scoreboard-link` | 重新產生計分板連結 | 樂觀鎖 `scoreboard_link_version`；需檢查 `deleted_at` |
| POST | `/courts/{court_id}/regenerate-control-panel-link` | 重新產生控制板連結 | 樂觀鎖 `control_panel_link_version`；需檢查 `deleted_at` |
| GET | `/courts/{court_id}/link-status` | 場地層級心跳檢查 | 每 5 分鐘輪詢；一併檢查解散狀態 |
| GET | `/courts/{court_id}/public` | 計分板/控制板畫面初始化資料 | 依 token 解析，無需登入 |

**賽程與排點（003）**

| Method | Path | 說明 | 備註 |
|---|---|---|---|
| POST | `/groups/{group_id}/next-round` | 手動 Next Round | 悲觀鎖 + `lock_timeout` |
| PATCH | `/groups/{group_id}/auto-next-round` | 切換 Auto Next Round | |
| GET | `/groups/{group_id}/partnerships` | 搭檔設定列表 | 固定搭檔循環賽模式 |
| PATCH | `/groups/{group_id}/partnerships` | 手動調整搭檔 | |
| POST | `/courts/{court_id}/manual-assign` | 手動安排：選人建立比賽 | 唯一性檢查（同場地僅一筆 in_progress） |

**即時計分（007）**

| Method | Path | 說明 | 備註 |
|---|---|---|---|
| POST | `/matches/{match_id}/score` | +1 / -1 | body: `{side, delta}`；單句原子 `UPDATE ... WHERE status='in_progress'` |
| POST | `/matches/{match_id}/end-early` | 提前結束 | 冪等；同上原子防呆 |

**團內成員視圖（005）**

| Method | Path | 說明 |
|---|---|---|
| GET | `/groups/{group_id}/schedule` | 唯讀賽程（目前 Round、進行中比賽、排隊中預告） |
| GET | `/groups/{group_id}/standings` | 逐輪勝負戰績（勝/敗/未上場/已離開） |
| GET | `/groups/{group_id}/match-history` | 本團對戰紀錄列表 |
| POST | `/groups/{group_id}/leave` | 主動退出組團 |

### 3.2 Ably 頻道與事件

**頻道命名**

| 頻道 | 涵蓋範圍 |
|---|---|
| `court:{group_id}:{court_id}` | 單一場地（計分板 Token、控制板 Token 訂閱） |
| `group:{group_id}:notifications` | 團層級（全部場地控制板 Token、管理 Token 訂閱） |

**Token capability 對照**

| Token 類型 | Subscribe | Publish |
|---|---|---|
| 計分板 Token | `court:{group_id}:{court_id}` | 無 |
| 單一場地控制板 Token | `court:{group_id}:{court_id}` + `group:{group_id}:notifications` | 無 |
| 全部場地控制板 Token | `court:{group_id}:*` + `group:{group_id}:notifications` | 無 |
| 管理 Token | `court:{group_id}:*` + `group:{group_id}:notifications` | 無 |

**事件清單**

| 事件 | 觸發時機 | 廣播頻道 | Payload 重點 |
|---|---|---|---|
| `score.updated` | +1/-1 成功 | `court:{group_id}:{court_id}` | `match_id, score_a, score_b` |
| `match.ended` | 自然達標或提前結束 | `court:{group_id}:{court_id}` | `match_id, status, winner_team` |
| `rotation.updated` | 場地領取新比賽（自動或手動安排） | `court:{group_id}:{court_id}` | `match_id, round_number, participants` |
| `match.nextRound` | Next Round / Auto Next Round | 逐一 `court:{group_id}:{court_id}`（受影響場地） | `round_number` |
| `member.joined` / `member.left` | 加入/退出/被踢除 | `group:{group_id}:notifications` | `roster_entry_id, nickname` |
| `link.regenerated` | 連結重新產生 | 依 link_type：場地層級→`court:{group_id}:{court_id}`；團層級/管理→`group:{group_id}:notifications` | `link_type, court_id?/group_id?` |
| `group.disbanded` | 解散團（手動或自動） | 逐一 `court:{group_id}:{court_id}` **並** `group:{group_id}:notifications` | 無需 payload |

---

## 4. 前端頁面/路由對應

依 UI 稿「首頁 / 開團 / 嘎團 / 會員 / 計分板 / 控制板」六大分類，Angular Router 規劃為 6 個 lazy-loaded feature route：

```
/                                       → 首頁（Home feature）
/groups/new                             → 開團表單（Group-Admin feature）
/groups/:groupId/admin                  → 管理頁（場地設定/搭檔設定/場地控制/賽程設定 tabs）
/groups/reauth                          → 組團編號 + PIN 碼 重新驗證

/join                                   → 開團列表 / 搜尋（Group-Join feature）
/join/:joinLinkToken                    → 透過連結/QR 進入加入流程
/groups/:groupId/join                   → 從列表點擊加入
/groups/:groupId                        → 一般成員視圖（賽程/戰績/對戰紀錄/退出組團 sub-routes）
  ├─ /schedule
  ├─ /standings
  ├─ /match-history
  └─ （退出組團為 modal action，非獨立路由）

/auth/register                          → 會員註冊（Member feature）
/auth/verify-email/:token               → Email 驗證結果
/auth/login
/auth/forgot-password
/auth/reset-password/:token
/member                                  → 會員資訊頁（登出/對戰紀錄/好友/個人設定/使用者編號入口）
/member/settings                         → 個人設定（暱稱/密碼）
/member/groups                           → 我建立的團（含忘記管理 PIN 碼入口）
/member/friends                          → 好友列表 + 搜尋
/member/friends/requests                 → 回覆好友申請
/member/match-history                    → 跨團對戰紀錄

/scoreboard/:courtToken                  → 計分板（Scoreboard feature，公開唯讀）

/control/:courtToken                     → 單一場地控制板（Control-Panel feature）
/control/all/:allCourtsToken             → 全部場地控制板
```

**共用元件**：連結失效提示、斷線提示、二次確認 dialog、QR Code 顯示（`angularx-qrcode`）、Turnstile widget wrapper（依當前 i18n 語系動態設定 `language`）。

**狀態管理**：各 feature 內以 Signals 承載畫面狀態；Ably 事件經由集中式 `RealtimeService`（RxJS `Observable` 包裝 Ably SDK callback）轉發，各元件以 `toSignal()` 訂閱；斷線/重連狀態亦為一個共用 Signal，供各即時頁面共同讀取以顯示「連線中斷」提示。

---

## 5. Docker 化細節

**前端 `apps/web/Dockerfile`**（多階段建置）

```dockerfile
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build -- --configuration production

FROM nginx:1.27-alpine
COPY --from=build /app/dist/web/browser /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
```

`nginx.conf` 重點：`try_files $uri $uri/ /index.html;`（SPA fallback）、gzip 靜態資源、`Cache-Control` 長效快取 hashed assets。

**後端 `apps/api/Dockerfile`**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
RUN useradd -m appuser
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
USER appuser
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=3s CMD curl -f http://localhost:8000/health || exit 1
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "-w", "2", "-b", "0.0.0.0:8000"]
```

**`infra/docker-compose.yml`**（本地開發）

```yaml
services:
  db:
    image: postgres:16
    environment:
      POSTGRES_DB: rally_stats
      POSTGRES_USER: rally
      POSTGRES_PASSWORD: rally_dev
    ports: ["5432:5432"]
    volumes: ["pgdata:/var/lib/postgresql/data"]

  backend:
    build: ../apps/api
    env_file: ../apps/api/.env
    environment:
      DATABASE_URL: postgresql+asyncpg://rally:rally_dev@db:5432/rally_stats
    depends_on: [db]
    ports: ["8000:8000"]
    volumes: ["../apps/api:/app"]  # 開發時支援 hot reload

  frontend:
    build: ../apps/web
    ports: ["4200:80"]
    depends_on: [backend]

volumes:
  pgdata:
```

`apps/api/.env`（本地開發，範例鍵值，正式環境改由 Secrets Manager 注入）：`JWT_SECRET`、`TURNSTILE_SECRET_KEY`（測試金鑰）、`PASSWORD_ENCRYPTION_KEY`、`ABLY_API_KEY`。

---

## 6. AWS 部署架構

- **ECR**：`rally-stats/web`、`rally-stats/api` 兩個 repository；CI 建置後以 commit SHA 為 tag 推送。
- **ECS Fargate**：`rally-stats` cluster 下兩個 Service（`web-service`、`api-service`），各自獨立 Task Definition；`api-service` 的 Task Definition 透過 `secrets` 區塊以 `valueFrom` 引用 Secrets Manager ARN 注入 `DATABASE_URL`、`JWT_SECRET`、`TURNSTILE_SECRET_KEY`、`PASSWORD_ENCRYPTION_KEY`、`ABLY_API_KEY`。
- **RDS for PostgreSQL**：獨立於 ECS 的私有子網路，Security Group 僅允許 `api-service` 所在子網路的入站連線；備份/PITR/DR 策略依 constitution 第 13 條列為未來項目，本次不展開。
- **Application Load Balancer**：兩個 Target Group（`web-tg` 443/80、`api-tg` 8000），依 Host-based routing（`app.` vs `api.` 子網域）或 Path-based routing（`/api/*`）導流；健康檢查分別打 `/` 與 `/health`。
- **（可選）S3 + CloudFront**：若前端改採靜態託管而非容器化，Angular build 產物上傳 S3，CloudFront 提供 CDN 快取與 HTTPS；此時 ALB 僅需保留 `api-tg`。
- **Secrets Manager**：集中管理上述所有機密值；IAM Task Role 僅授予讀取專屬於本專案 Secret 路徑的最小權限。
- **CI/CD（GitHub Actions）**：
  1. Push/PR 觸發 lint + 型別檢查 + 單元/整合測試（constitution 原則 I、II 之 blocking check）。
  2. Merge 到 `main` 後建置兩個 Docker image、推送 ECR。
  3. 呼叫 `aws ecs update-service --force-new-deployment`（或改用 CodeDeploy blue/green，視後續需求）更新對應 Service。
  4. Alembic migration 於 CI/CD 中的執行時機與失敗處理，依 constitution 第 13 條列為未來項目，本次不展開（初期以手動於部署前執行 `alembic upgrade head` 因應）。

---

## 7. 模組實作順序建議與相依關係

### 7.1 相依關係圖（文字描述）

```
0. 基礎建設（DB schema、Docker、CI 骨架、SystemConfig）
        │
        ▼
1. 會員帳號核心（006 之註冊/登入/JWT，暫不含好友系統與 Email 驗證 UX 細節）
   —— 提供 Member 身分與 JWT middleware，供後續「已登入會員」分支使用
        │
        ▼
2. 開團與管理核心（001）—— Group、Admin Credential、Match Scoring Settings
   —— 匿名 + 會員雙路徑皆可建團；管理頁基本編輯/解散/PIN 驗證
        │
        ├──────────────┐
        ▼              ▼
3. 場地管理（002）   4a. 加入團（004，部分）
   —— 依賴 Group        —— 可與場地管理平行開發，
                            但完整加入流程需等賽程模組
        │
        ▼
5. 賽程與輪替名單（003）
   —— 依賴 Group（比賽設定快照、排程機制設定）+ Court
        │
        ▼
6. 即時計分板與控制板（007）
   —— 依賴 Court（連結）+ Match（003 之狀態機）
   —— 完成後即形成「開團→加入→排點→計分」的最小可行閉環（MVP）
        │
        ├──────────────┐
        ▼              ▼
7. 加入團（004，完整）  8. 團內成員視圖（005）
   —— 依賴 003 的           —— 依賴 003 的 Match/MatchResult
      RosterEntry              狀態機、001 的 Group
        │
        ▼
9. 會員與好友系統（006，完整功能）
   —— Email 驗證完整 UX、好友系統、忘記管理 PIN 碼
   —— 忘記管理 PIN 碼依賴 001 已完成的 admin_token_version 機制
```

### 7.2 建議實作順序與各階段驗收標準

1. **基礎建設**：`docker-compose` 可啟動 db/backend/frontend；Alembic 初始 migration 建立全部資料表（見第 2 章）；CI 跑通 lint + 型別檢查。
2. **會員帳號核心**（006 子集）：`POST /auth/register`（含 Turnstile）、`POST /auth/login`、JWT middleware、`token_version` 失效機制。**驗收**：可註冊、登入、修改密碼使其他裝置登出。
3. **開團與管理核心**（001）：建團（匿名/會員雙路徑）、管理頁基本編輯、PIN 驗證與防暴力破解、解散團、`admin_token_version` 機制。**驗收**：001 spec 之 US1、US2、US3 acceptance scenarios 通過。
4. **場地管理**（002）：場地 CRUD（軟刪除）、連結產生/重新產生、全部場地控制板 Token 授權。**驗收**：002 spec 之 US1、US2 通過。
5. **賽程與輪替名單**（003）：公平輪替演算法（階段一/階段二）、Round/賽程表生命週期、Next Round（悲觀鎖）。**驗收**：003 spec 之 US1、US3 通過（可先以最簡單的公平輪替機制驗證，其餘三種排程機制可視為後續增量）。
6. **即時計分板與控制板**（007）：+1/-1 原子操作、自動判定勝負、提前結束（含 FR-006a 原子防呆）、Ably 事件發布與訂閱、斷線重連。**驗收**：007 spec 全部 P1 使用者故事通過——此時已具備可展示的端到端 MVP（開團 → 建場地 → 排點 → 計分）。
7. **加入團完整流程**（004）：開團列表、QR/連結加入、Guest Session Token 生命週期、`current_member_count` 原子檢查。**驗收**：004 spec 之 US1、US2、US3 通過。
8. **團內成員視圖**（005）：唯讀賽程、逐輪戰績（四狀態）、對戰紀錄、退出組團。**驗收**：005 spec 之 US1、US2、US3 通過。
9. **會員與好友系統完整功能**（006 其餘）：Email 驗證完整流程與速率限制、好友搜尋/邀請/解除、忘記管理 PIN 碼（依賴步驟 3 的 `admin_token_version`）。**驗收**：006 spec 全部使用者故事通過。
10. **固定搭檔循環賽 / 個人全混搭循環賽 排程機制**（003 增量）：可視為步驟 5 的後續增量獨立排入時程，因其邏輯建立在公平輪替階段一/階段二之上，屬於錦上添花但非 MVP 阻斷項。
11. **AWS 部署**：待步驟 2–6（MVP 閉環）完成後即可著手建立 ECS/RDS/ALB 環境並串接 CI/CD，不需等待全部 7 個 spec 完工。

**排序理由**：步驟 2–6 構成產品最小可行閉環（沒有場地與賽程就無法展示核心的即時計分價值），優先排在最前；步驟 7–9 是圍繞此閉環的重要但非阻斷性增量（加入流程可先以「管理員手動在資料庫插入測試資料」代替，用於前期開發驗證），故排在閉環完成之後；AWS 部署不必等到全部功能完工才開始，愈早建立部署管線愈能及早發現容器化/環境設定問題。
