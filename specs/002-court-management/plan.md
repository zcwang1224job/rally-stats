# Implementation Plan: 場地管理（Court Management）

**Branch**: `N/A (no git repository initialized)` | **Date**: 2026-09-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/002-court-management/spec.md`, cross-referenced against `/specs/architecture.md`（專案共用 schema/API/Ably 決策）與 `/specs/001-create-manage-group/`（本 feature 依賴之 Group 實體與既有領域模組模式）。

## Summary

管理員可在團內新增/刪除場地，每個場地各自擁有獨立的計分板連結與控制板連結（含 QR Code）；另有團層級的「全部場地控制板」連結供單人操作所有場地。所有連結（含 001 已定義的加入連結）皆可個別重新產生，重新產生後透過 Ably 事件（`link.regenerated`，含 `link_type` 區分）+ 5 分鐘心跳備援雙層機制通知舊連結持有者。場地刪除採軟刪除，保留歷史對戰紀錄的參照完整性；若刪除時場地有未收尾比賽，該比賽轉為已捨棄（此步驟以可延後串接的 hook 呈現，實際 Match 查詢邏輯屬 003 spec 範圍）。本 feature 不涵蓋比賽本身的計分、排點、手動安排選人邏輯（見 Assumptions）——「全部場地控制板」與「管理頁內建場地控制區塊」兩個使用者故事，本 feature 僅建立其連結/身分解析/即時同步基礎設施，實際評分/安排操作留待 003（賽程）、007（即時計分板）完工後串接。

## Technical Context

**Language/Version**：後端 Python 3.12+；前端 TypeScript（Angular 20+，Standalone Components）—— 延續 001 已建立的 monorepo 與工具鏈，不新增技術選型。

**Primary Dependencies**：沿用 001 已安裝之 FastAPI、Pydantic v2、SQLAlchemy 2.0（async）+ Alembic、Ably REST/JS SDK；前端新增消費（非新增套件）`angularx-qrcode`（001 已安裝但尚未使用，見 research.md #6）。

**Storage**：PostgreSQL，延續 001 已建立的 `courts` 資料表（本 feature 補齊其完整欄位，見 data-model.md §7 之 migration）。

**Testing**：後端 pytest + pytest-asyncio（核心領域邏輯——名稱唯一性判斷、軟刪除排除查詢、連結重新產生之刪除優先檢查、各自獨立版本欄位之衝突偵測——MUST 有單元測試；至少一條整合測試涵蓋「新增場地→重新產生連結→刪除場地」）；前端 Vitest（延續 001 決策）。

**Target Platform**：延續 001（Docker/AWS ECS Fargate；瀏覽器桌面與行動裝置）。

**Project Type**：Web application（monorepo，延續 001 結構）。

**Performance Goals**：新增場地至連結可用 10 秒內完成（SC-001，UX 層級）；三個操作入口（全部場地控制板／單一場地控制板／管理頁場地控制區塊）之間的同步約 1 秒內完成（SC-002，本 feature 僅涵蓋其中「場地清單新增/刪除即時反映」，實際比分同步屬 007 範圍）；連結重新產生後在線使用者約 1 秒內收到失效提示、離線者 5 分鐘內或重連時得知（SC-003）。

**Constraints**：場地層級與團層級連結之心跳檢查 MUST 使用彼此獨立的端點（FR-034）；重新產生場地層級連結前 MUST 優先檢查 `deleted_at`，優先於版本衝突檢查（FR-028）；場地刪除的併發衝突（管理員 A 刪除、管理員 B 幾乎同時重新產生同一場地連結）MUST 讓刪除一旦生效即優先拒絕後續請求（US5 情境 7）——透過「刪除檢查優先於版本比對」的执行順序自然達成，不需額外鎖機制。

**Scale/Scope**：場地數量不設系統上限（FR-037），實務規模為個位數至十位數量級（spec Assumptions）。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | Pydantic v2 schema 對應所有請求/回應；SQLAlchemy 2.0 型別化 `Court` model；`ruff`/`mypy --strict` 與前端 `tsc --noEmit` 為 CI blocking check。 | PASS |
| II. 測試優先 | 名稱唯一性（含軟刪除排除）、連結重新產生之刪除優先檢查、各自獨立版本欄位衝突偵測屬核心領域邏輯，MUST 有單元測試；至少一條整合測試涵蓋「新增→重新產生連結→刪除」。 | PASS（列入 tasks.md 強制項） |
| III. 即時性與一致性 | `link.regenerated` 事件於 DB 交易提交後才發布，非前端直接寫入；場地清單心跳查詢（`GET /courts/by-token/{token}`）一併回傳 `deleted`/`group_disbanded` 最新狀態，不快取。 | PASS |
| IV. 權限與安全 | 場地 CRUD 與所有重新產生端點皆沿用 001 之 `require_admin`（`admin_token_version` 比對）；全部場地控制板 by-token 端點刻意不回傳其他場地的個別連結 Token，避免權限範圍外洩（見 contracts/courts-api.md）。 | PASS |
| V. UX 一致性 | 刪除場地、重新產生連結皆為前端二次確認流程，元件實作細節於 tasks.md 展開。 | PASS |
| VI. 可維護性 | 場地實體邏輯獨立為 `app/domains/court/`；join-link/all-courts-link 之重新產生操作雖由本 feature 之驗收標準驅動，程式碼位置留在擁有 `groups` 表的 `app/domains/group/`（見 research.md #1），不跨模組直接寫入他人擁有的資料表。 | PASS |
| VIII. i18n 與時區 | 錯誤回應一律語意化代碼（`COURT_NAME_ALREADY_EXISTS`、`COURT_DELETED`、`LINK_NOT_FOUND` 等）；`created_at`/`deleted_at` 用 `TIMESTAMPTZ`。 | PASS |
| IX. 可攜性 | 沿用 001 已建立的 Docker/AWS 設計，不需額外基礎設施調整。 | PASS |
| X. 伺服器為單一事實來源 | 計分板/控制板/全部場地控制板皆僅訂閱 Ably、不可 publish；所有連結重新產生經 REST API 落地 DB 後才由後端發布事件（加入連結除外，依 FR-033 不發布事件，由後端於加入請求當下即時驗證）。 | PASS |
| XI. 防機器人 | 本 feature 無公開表單提交端點（新增/刪除/重新產生皆需管理員驗證）；by-token 之公開讀取端點為唯讀查詢，無濫用風險，不需 Turnstile（比照 spec Assumptions：不設額外 rate limit，風險與其他既有管理頁寫入操作相同）。 | PASS |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/002-court-management/
├── plan.md              # 本檔案
├── research.md          # Phase 0 產出
├── data-model.md         # Phase 1 產出
├── quickstart.md         # Phase 1 產出
├── contracts/             # Phase 1 產出
│   ├── courts-api.md
│   └── ably-events.md
└── tasks.md               # /speckit-tasks 產出（本指令不建立）
```

### Source Code (repository root)

```text
apps/api/
├── app/
│   ├── domains/
│   │   ├── court/
│   │   │   ├── models.py        # SQLAlchemy: Court（補齊完整欄位，取代 001 之 stub）
│   │   │   ├── schemas.py       # Pydantic 請求/回應
│   │   │   ├── service.py       # 新增/重新命名/軟刪除/連結重新產生/by-token 解析邏輯
│   │   │   └── router.py        # FastAPI router
│   │   └── group/
│   │       ├── service.py       # 擴充：regenerate_join_link、regenerate_all_courts_link
│   │       └── router.py        # 擴充：對應端點 + by-all-courts-token 解析
│   └── ...                       # core/、scheduler/、system_config/ 沿用 001，不變動
└── tests/
    ├── unit/domains/court/
    ├── contract/
    └── integration/

apps/web/
├── src/app/features/
│   ├── group-admin/
│   │   └── admin-page/            # 擴充：「場地設定」區塊（新增/刪除/連結列表）、
│   │                                #   「場地控制」區塊骨架（US4，見 Assumptions）
│   └── control-panel/               # 擴充：全部場地控制板畫面骨架（US3，見 Assumptions）
│       └── all-courts/
└── src/app/features/group-admin/court-management/
    ├── court-list.component.ts      # 場地清單 + 新增表單
    ├── court-link-card.component.ts # 單一場地的計分板/控制板連結卡片（QR + 複製 + 重新產生）
    └── court-management.service.ts  # 集中式 API 呼叫層
```

**Structure Decision**：延續 `architecture.md` 既定的 `apps/web` + `apps/api` monorepo 結構；`Court` 實體邏輯獨立為 `app/domains/court`（constitution 原則 VI），`join-link`/`all-courts-link` 之操作因涉及 `groups` 表的資料寫入，程式碼留在 001 已建立的 `app/domains/group` 內（見 research.md #1）——本 feature 對 `group` 模組的變動僅限「新增」，不修改既有 001 行為。

## Complexity Tracking

*本 feature 無 Constitution Check 違反項目，此表格從略。*

## Post-Design Constitution Check

*Re-evaluated after Phase 1（`data-model.md`、`contracts/`、`quickstart.md`）產出。*

設計階段的兩項關鍵決策——(1) 場地重新命名不設專屬版本欄位而改用資料庫唯一索引作為並發防呆（research.md #5）、(2) 場地層級連結初始化與心跳合併為單一 by-token 端點（research.md #4）——皆為在不違反任何 FR 的前提下縮減實作面積的簡化決策，未引入新的 Constitution 違反項目。`AbandonCourtMatchesHook` 延續 001 已驗證可行的「延後串接」模式（原則 VI 模組邊界），`all-courts` by-token 端點刻意不回傳個別場地連結 Token（原則 IV 權限最小化）。**Gate 結果維持 PASS，無需新增 Complexity Tracking 項目。**

## Assumptions

- 「全部場地控制板」（US3）與「管理頁內建場地控制區塊」（US4）之實際 +1/-1、提前結束、手動安排選人操作，依賴尚未存在的 Match（003 spec）與即時計分（007 spec）領域邏輯；本 feature 僅建立這兩個畫面的連結/身分解析/即時同步基礎設施與空狀態畫面骨架，不實作假的計分/選人邏輯（見 research.md #3）。
- 場地刪除時「是否有進行中比賽」之判斷（FR-010 的確認彈窗警示文案分支）在 003 spec 完工前恆為「否」（`AbandonCourtMatchesHook` no-op），前端於此之前顯示不含比賽狀態細節的通用刪除確認文案；待 003 完工後串接真正的 Match 查詢即可自動使此分支生效，不需重新設計本 feature 的刪除流程。
- 依 001 spec FR-032（「團解散後...MUST NOT 可進行任何寫入操作，含新增/刪除場地」），本 feature 之場地新增/刪除/連結重新產生端點於團已解散時 MUST 回傳 `GROUP_DISBANDED`——此為 001 既有規則的直接套用，非本 feature 新增的臆測行為。
