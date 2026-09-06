# Implementation Plan: 開團與管理（Create & Manage Group）

**Branch**: `N/A (no git repository initialized)` | **Date**: 2026-08-31 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-create-manage-group/spec.md`, cross-referenced against the project-wide `/specs/architecture.md` (shared schema/API/Ably decisions established across all 7 specs).

## Summary

管理員可建立揪團場次（匿名或會員身分皆可），系統核發唯一組團編號與雜湊儲存的 6 碼管理 PIN 碼；管理員可透過組團編號＋PIN 碼重新驗證進入管理頁編輯團設定（團名、時間、比賽模式、比賽設定、通關密碼）、主動重設 PIN 碼、或解散團。團持續 1 小時無寫入活動時自動解散，效果與手動解散相同。技術做法：後端以 FastAPI 提供 REST API、PostgreSQL 儲存團與其版本化憑證欄位、Ably 廣播解散事件與心跳備援、Cloudflare Turnstile 防機器人；前端以 Angular Signals 管理管理頁狀態。本功能不涵蓋場地、賽程、計分、加入流程、會員系統本身的實作（見 Assumptions），僅定義與這些周邊功能的資料/事件邊界。

## Technical Context

**Language/Version**: 後端 Python 3.12+；前端 TypeScript（Angular 20+，Standalone Components）

**Primary Dependencies**: FastAPI, Pydantic v2, SQLAlchemy 2.0（async）+ Alembic, passlib[bcrypt], PyJWT, `cryptography`（AES-256-GCM，通關密碼可還原加密）, Ably REST SDK（後端）/ Ably JS SDK（前端）, slowapi（PIN 重新驗證與 Turnstile 端點的速率限制）, httpx（呼叫 Cloudflare `siteverify`）, APScheduler（1 小時無活動自動解散排程）；前端 Angular Signals + RxJS, Angular HttpClient, ngx-translate（或 `@angular/localize`）

**Storage**: PostgreSQL（本地 `docker-compose`；正式環境 Amazon RDS for PostgreSQL）

**Testing**: 後端 pytest + pytest-asyncio（依 constitution 原則 II，核心領域邏輯——PIN 驗證、版本化併發控制、自動解散判斷——需單元測試覆蓋；「建立團→重新驗證→編輯→解散」需至少一條整合測試）；前端 Vitest（見 research.md 決策，取代 Angular CLI 預設的 Karma/Jasmine）

**Target Platform**: Linux 容器（Docker，AWS ECS Fargate）；瀏覽器（桌面與行動裝置）

**Project Type**: Web application（monorepo：`apps/web` 前端 + `apps/api` 後端，見 `architecture.md` 專案結構）

**Performance Goals**: 解散事件廣播後連線中畫面 ~1 秒內反映（SC-004）；PIN 重新驗證 30 秒內完成（SC-008）；開團流程 3 分鐘內完成（SC-001，UX 層級而非系統效能指標）

**Constraints**: Cloudflare Turnstile 呼叫逾時 3–5 秒、fail-closed；PIN 驗證防暴力破解（見 research.md 決策的具體門檻值）；管理 Token 需攜帶 `admin_token_version` 供即時失效比對；「重設 PIN 碼」「連結重新產生」類操作採樂觀鎖（HTTP 409 衝突回應）

**Scale/Scope**: 單一 AWS 區域部署；`group_number` 為不設上限的遞增序號（`BIGINT`）；初期預期規模為業餘揪團活動等級（數百筆同時進行中的團），非高流量 SaaS 等級

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | Pydantic v2 schema 對應所有請求/回應（含 group create/edit/disband）；SQLAlchemy 2.0 型別化 ORM model；CI blocking check（lint + `mypy`/`tsc --noEmit`）。 | PASS |
| II. 測試優先 | PIN 驗證、`admin_token_version` 比對、1 小時自動解散判斷、樂觀鎖衝突偵測皆屬核心領域邏輯，MUST 有單元測試；至少一條整合測試涵蓋「建立→重新驗證→編輯→解散」。 | PASS（列入 tasks.md 強制項） |
| III. 即時性與一致性 | 比賽設定修改透過快照（`matches.target_score` 等欄位建立時複製）落實，MUST NOT 即時查詢；解散事件經 DB 交易後才發布 Ably，非前端直接寫入。 | PASS |
| IV. 權限與安全 | 管理 PIN 碼 bcrypt 雜湊 + 防暴力破解；通關密碼 AES-256-GCM 可還原加密，與 PIN 雜湊機制不共用程式碼路徑；通關密碼明文查看僅限已驗證管理頁 API。 | PASS |
| V. UX 一致性 | 解散團、重設 PIN 碼皆為前端二次確認流程；本 plan 不涉及前端元件實作細節，於 tasks.md 展開。 | PASS |
| VIII. i18n 與時區 | 錯誤回應一律語意化代碼（`GROUP_PASSWORD_INCORRECT` 等）；`last_activity_at`/`created_at` 用 `TIMESTAMPTZ`；活動時間區間用不含時區 `TIME`。 | PASS |
| IX. 可攜性 | 沿用 `architecture.md` 之 Docker/AWS 設計，本 feature 不需額外基礎設施調整。 | PASS |
| X. 伺服器為單一事實來源 | 管理頁與計分板皆訂閱 Ably、不可 publish；所有寫入經 REST API 落地 DB 後才由後端發布事件。 | PASS |
| XI. 防機器人 | 開團端點整合 Turnstile，fail-closed；重新驗證/重設 PIN 碼端點使用速率限制而非 Turnstile（PIN 本身已具備防暴力破解機制，二者防護目的不同不可混用）。 | PASS |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/001-create-manage-group/
├── plan.md              # 本檔案
├── research.md          # Phase 0 產出
├── data-model.md         # Phase 1 產出
├── quickstart.md         # Phase 1 產出
├── contracts/             # Phase 1 產出
│   ├── groups-api.md
│   └── ably-events.md
└── tasks.md               # /speckit-tasks 產出（本指令不建立）
```

### Source Code (repository root)

```text
apps/api/
├── app/
│   ├── main.py
│   ├── domains/
│   │   └── group/
│   │       ├── models.py        # SQLAlchemy: Group（含 Match Scoring Settings、Admin Credential 欄位）
│   │       ├── schemas.py       # Pydantic 請求/回應
│   │       ├── service.py       # 建立/編輯/解散/PIN 重設/重新驗證邏輯
│   │       ├── router.py        # FastAPI router
│   │       └── security.py      # PIN 雜湊、通關密碼 AES-GCM 加解密、admin token 簽發/驗證
│   ├── core/
│   │   ├── config.py             # 環境變數、Secrets 讀取
│   │   ├── turnstile.py          # Cloudflare siteverify 呼叫（fail-closed）
│   │   ├── realtime.py           # Ably REST SDK wrapper（發布事件）
│   │   └── rate_limit.py         # slowapi 設定（PIN 驗證、重設 PIN 碼端點）
│   ├── scheduler/
│   │   └── auto_disband.py       # APScheduler 週期任務：掃描 `last_activity_at` 逾 1 小時的團
│   └── system_config/
│       └── service.py             # 讀取 `max_group_members` 等參數
└── tests/
    ├── unit/domains/group/
    └── integration/test_group_lifecycle.py

apps/web/
├── src/app/features/group-admin/
│   ├── create-group/              # 開團表單（含 Turnstile widget）
│   ├── admin-page/                 # 就地編輯、解散、重設 PIN 碼
│   ├── reauth/                     # 組團編號 + PIN 碼 重新驗證
│   └── group-admin.service.ts      # 集中式 API service 層
└── src/app/core/realtime/
    └── ably.service.ts              # Ably JS SDK wrapper（訂閱 `group:{group_id}:notifications`）
```

**Structure Decision**：延續 `architecture.md` 既定的 `apps/web` + `apps/api` monorepo 結構；後端依 constitution 原則 VI（模組化）將本 feature 獨立為 `app/domains/group`，與其他 feature（場地、賽程、會員）以 service 層介面溝通，不共享 ORM session 以外的內部實作細節。

## Complexity Tracking

*本 feature 無 Constitution Check 違反項目，此表格從略。*

## Post-Design Constitution Check

*Re-evaluated after Phase 1（`data-model.md`、`contracts/`、`quickstart.md`）產出。*

設計階段未引入任何新的違反項目：資料模型的版本欄位拆分（`base_settings_version`/`admin_token_version`/`join_link_version`/`all_courts_link_version`）進一步落實原則 X 與 spec FR-028 之「互不相關面向獨立版本追蹤」；API contract 之錯誤代碼設計符合原則 VIII；`quickstart.md` 情境 2、4 驗證了防暴力破解與憑證失效機制符合原則 IV。**Gate 結果維持 PASS，無需新增 Complexity Tracking 項目。**
