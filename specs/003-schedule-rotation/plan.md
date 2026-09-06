# Implementation Plan: 賽程與輪替名單（Schedule & Roster Rotation）

**Branch**: `N/A (no git repository initialized)` | **Date**: 2026-09-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/003-schedule-rotation/spec.md`, cross-referenced against `/specs/architecture.md`（`matches`/`match_participants`/`pair_history`/`partnerships` DDL 已定案）、`/specs/001-create-manage-group/`（Group 的 `current_round_number`/`auto_next_round`、RosterEntry 的 `wait_count`/`status`/`joined_at` 皆已建立但未賦予語意）、`/specs/002-court-management/`（`AbandonCourtMatchesHook` 待串接）。

## Summary

系統依團設定的排程機制（公平輪替、固定搭檔循環賽、個人全混搭循環賽、手動安排）自動或半自動安排每個 Round 的上場名單與對戰組合。三種演算法機制皆採「兩階段」設計——階段一依等待輪數（或隊伍等待輪數 MAX）選出上場名單，階段二依配對次數最少的貪婪法決定分組；手動安排則完全由管理員逐場指定，不預先產生賽程表。管理員可隨時強制「Next Round」或開啟「Auto Next Round」讓賽程表消耗完畢後自動進入下一輪；零場地時兩者皆被拒絕。成員的加入/退出/踢除會即時調整賽程表但不觸發整輪重排。本 feature 新建 `matches`/`match_participants`/`pair_history`/`partnerships` 四張表與 `app/domains/schedule/` 模組，並串接 001 的解散捨棄比賽 hook 與 002 的刪除場地捨棄比賽 hook；比賽本身的計分/勝負判定（007 spec）與成員加入/主動退出的 HTTP 端點（004/005 spec）僅定義本 feature 對外暴露的 service 函式邊界，不在此實作。

## Technical Context

**Language/Version**：延續 001/002（後端 Python 3.12+；前端 TypeScript / Angular 20+）。

**Primary Dependencies**：沿用既有 FastAPI/SQLAlchemy/Alembic/Ably 堆疊，不新增套件；排點演算法純為應用層 Python 邏輯（無額外數值運算/圖論套件依賴——貪婪法足以滿足 spec Assumptions 之效能/正確性權衡）。

**Storage**：PostgreSQL，新增 `matches`、`match_participants`、`pair_history`、`partnerships` 四張表（DDL 見 data-model.md，`architecture.md` 已定案）。

**Testing**：pytest + pytest-asyncio。核心領域邏輯（兩階段排點演算法之階段一排序、階段二貪婪配對、Round 終態判定、零場地防呆、成員異動收斂、`AbandonMatchesHook`/`AbandonCourtMatchesHook` 串接）MUST 有單元測試；至少一條整合測試涵蓋「新增輪替名單成員 → 產生 Round → 完成/捨棄比賽 → 自動領取下一場 → Next Round」。演算法測試須包含 SC-002（累計上場次數差距 ≤1）之多輪模擬驗證。

**Target Platform**：延續 001/002。

**Project Type**：Web application（monorepo，延續既有結構）。

**Performance Goals**：Round 產生到各場地可計分 2 秒內完成（SC-001）；手動安排選人到開始計分 30 秒內（SC-003，UX 層級）。

**Constraints**：Next Round 採悲觀鎖（`SELECT ... FOR UPDATE NOWAIT`，見 research.md #8），與 001/002 慣用的樂觀鎖版本欄位不同——此為 `architecture.md` 既有端點註記之落實；`wait_count` 更新 MUST 採整批 SQL `UPDATE`，避免 N+1（research.md #9）；`PairHistory` 累加 MUST 於比賽建立當下即完成，不因終態為 `abandoned` 而回滾（research.md #5，呼應 FR-009）。

**Scale/Scope**：單團輪替名單規模預期數十人、場地數個位數；貪婪演算法之時間複雜度在此規模下無效能疑慮。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | Pydantic v2 schema 對應所有請求/回應；SQLAlchemy 2.0 型別化 `Match`/`MatchParticipant`/`PairHistory`/`Partnership` model；`ruff`/`mypy --strict` blocking check。 | PASS |
| II. 測試優先 | 排點演算法兩階段邏輯、Round 終態判定、零場地防呆、成員異動賽程收斂、悲觀鎖衝突偵測皆屬核心領域邏輯，MUST 有單元測試；至少一條整合測試涵蓋「產生 Round→完成/捨棄→自動領取→Next Round」全流程。 | PASS（列入 tasks.md 強制項） |
| III. 即時性與一致性 | 比賽設定於建立當下複製快照（沿用 001 既有機制）；`rotation.updated`/`match.nextRound` 皆於 DB 交易提交後才發布。 | PASS |
| IV. 權限與安全 | 本 feature 全部端點皆沿用 001 之 `require_admin`；手動安排選人介面之防呆（FR-013）為資料完整性而非權限控制，但同樣 MUST 同時存在前後端。 | PASS |
| V. UX 一致性 | 踢除成員二次確認（FR-037）；前端元件實作細節於 tasks.md 展開。 | PASS |
| VI. 可維護性 | 新建 `app/domains/schedule/` 獨立模組；對 001（`group/service.py` 之 FR-042 驗證、`group/router.py` 之 Partnership 副作用串接）與 002（`court/router.py` 之 abandon hook 串接）的觸碰範圍已於 research.md #2～4 明確界定，皆為既有檔案的新增程式碼，不變更既有函式簽章或既有測試涵蓋的行為。 | PASS |
| VIII. i18n 與時區 | 錯誤回應一律語意化代碼（`NO_COURTS_AVAILABLE`、`ROUND_GENERATION_IN_PROGRESS` 等）；`matches` 之 `created_at`/`started_at`/`ended_at` 皆用 `TIMESTAMPTZ`。 | PASS |
| IX. 可攜性 | 沿用既有 Docker/AWS 設計，不需額外基礎設施。 | PASS |
| X. 伺服器為單一事實來源 | 所有排點結果經 DB 交易提交後才發布 Ably 事件；控制板/計分板僅訂閱、不可 publish。 | PASS |
| XI. 防機器人 | 本 feature 無公開表單提交端點（全數需管理員驗證），不適用 Turnstile。 | PASS |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/003-schedule-rotation/
├── plan.md              # 本檔案
├── research.md          # Phase 0 產出
├── data-model.md         # Phase 1 產出
├── quickstart.md         # Phase 1 產出
├── contracts/             # Phase 1 產出
│   ├── schedule-api.md
│   └── ably-events.md
└── tasks.md               # /speckit-tasks 產出（本指令不建立）
```

### Source Code (repository root)

```text
apps/api/
├── app/
│   ├── domains/
│   │   ├── schedule/
│   │   │   ├── models.py        # Match, MatchParticipant, PairHistory, Partnership
│   │   │   ├── schemas.py       # Pydantic 請求/回應
│   │   │   ├── algorithms.py    # 兩階段排點：fair_rotation/fixed_partner/individual_mixed 共用邏輯
│   │   │   ├── service.py       # Round 生命週期、手動安排、成員異動、abandon hook 實作
│   │   │   └── router.py        # FastAPI router
│   │   ├── group/
│   │   │   ├── service.py       # 擴充：FR-042 驗證（create_group/edit_group）
│   │   │   └── router.py        # 擴充：disband 端點串接 abandon_group_matches；
│   │   │                          #   PATCH /{group_id} 端點串接 Partnership 副作用
│   │   └── court/
│   │       └── router.py        # 擴充：delete 端點串接 abandon_court_matches
│   └── ...                       # core/、scheduler/ 沿用既有，不變動
└── tests/
    ├── unit/domains/schedule/
    ├── contract/
    └── integration/

apps/web/
└── src/app/features/group-admin/
    ├── admin-page/                # 擴充：場地控制區塊改接真實排程資料（取代 002 US4 骨架）、
    │                                #   Next Round / Auto Next Round 控制項
    ├── schedule-management/
    │   ├── manual-assign.component.ts    # 手動安排選人介面
    │   └── partnership-settings.component.ts  # 搭檔設定區塊
    └── group-admin.service.ts        # 擴充：next-round/auto-next-round/partnerships/manual-assign/kick 呼叫
```

**Structure Decision**：新增 `app/domains/schedule` 作為本 feature 之核心模組（constitution 原則 VI）；對既有 `group`/`court` 模組的擴充範圍已於 research.md #2～4 明確界定為「新增，不變更既有行為」。前端沿用 `group-admin` 既有 feature 目錄結構，新增 `schedule-management` 子目錄容納本 feature 特有的手動安排與搭檔設定介面。

## Complexity Tracking

*本 feature 無 Constitution Check 違反項目，此表格從略。*

## Post-Design Constitution Check

*Re-evaluated after Phase 1（`data-model.md`、`contracts/`、`quickstart.md`）產出。*

設計階段的關鍵決策——(1) Round 產生與初次領取合併於同一交易（research.md #7）、(2) Next Round 採悲觀鎖而非樂觀版本欄位（research.md #8，落實 `architecture.md` 既有端點註記）、(3) `PairHistory`/`wait_count` 皆採「建立當下/整批 SQL 立即定案」而非延遲或逐筆處理（research.md #5, #9）——皆為在不違反任何 FR 的前提下確保正確性與效能的實作細節，未引入新的 Constitution 違反項目。與 001/002 的三處串接點（FR-042 驗證、Partnership 副作用、兩個 abandon hook）皆維持「新增程式碼、既有函式簽章不變」的原則，符合原則 VI 之模組邊界要求。**Gate 結果維持 PASS，無需新增 Complexity Tracking 項目。**

## Assumptions

- 比賽本身的計分、勝負判定、`MatchResult`／`winner_team` 寫入邏輯屬 007 spec 範圍；本 feature 僅提供 `advance_court_after_match_ends(session, match)` 供其呼叫，不實作 007 的 +1/-1／提前結束端點本身。
- 成員「主動加入」「主動退出」之 HTTP 端點分別屬 004、005 spec 範圍；本 feature 僅提供 `handle_member_joined`/`handle_member_left` service 函式供其呼叫，不在此提供對應 REST 端點（踢除除外——FR-037 明確將踢除歸屬本 feature，故 `DELETE /groups/{group_id}/members/{roster_entry_id}` 由本 feature 實作）。
- `GET /groups/{group_id}/schedule` 為本 feature admin 頁面專用之唯讀端點（含手動安排所需的「目前是否在場上」等管理視角欄位）；005 spec 未來可能定義自己的公開/會員視角唯讀賽程端點，兩者服務不同受眾，不互相取代，屆時由 005 的 plan 決定是否重用本端點或另建。
