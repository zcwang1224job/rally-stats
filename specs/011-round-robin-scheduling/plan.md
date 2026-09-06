# Implementation Plan: 循環賽賽程排程（Round-Robin Scheduling）

**Branch**: `main`（本專案單人維護，既有 003/005/010 等 feature 皆直接於 `main` 開發，未使用 per-feature git 分支） | **Date**: 2026-09-02 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/011-round-robin-scheduling/spec.md`，取代 `specs/003-schedule-rotation`（`apps/api/app/domains/schedule/service.py`、`algorithms.py`）現有的「一輪＝剛好填滿場地數的比賽」生成邏輯，並延伸 `specs/005-member-view`（`build_group_standings()` 之 Round 範圍計算）之相依假設。

## Summary

把 `fair_rotation`（單打情境）、`fixed_partner`、`individual_mixed` 三種演算法排程機制的 Round 生成邏輯，從「依 `wait_count` 篩選出恰好填滿場地數的一批人上場」改為「一次產生涵蓋目標配對組合（兩兩對戰或兩兩搭檔）的完整循環賽賽程」，全部以 `queued` 狀態寫入既有 `matches`/`match_participants` 表；場地空閒時延伸既有 `pull_queued_match_for_court`，新增「跳過任何參與者目前正在其他場地進行中」的可行性檢查後再領取。固定搭檔循環賽新增 `partner_source`（`manual`/`auto`）團層級設定，兩種來源切換時互不清除對方資料。單打與固定搭檔採「循環法（circle method）」一次性生成零重複賽程；個人混搭循環賽因搭檔覆蓋屬於已知無通用解的組合設計問題，採「多波次貪婪迴圈」重用既有 `stage2_pair_players`/`team_matchup_stage2` 兩個既有函式，直到搭檔覆蓋完成或連續無進展才停止。`wait_count`、`stage1_select_players`、`team_stage1_select` 停止在這三種機制的 Round 生成路徑上被呼叫（其「優先上場排序」用途被「全員每輪皆涵蓋」取代），但保留給既有手動安排模式使用，不刪除也不變更其行為。

## Technical Context

**Language/Version**：延續 003（後端 Python 3.12+；前端 TypeScript / Angular 20+），本 feature 不變更技術棧。

**Primary Dependencies**：沿用既有 FastAPI/SQLAlchemy/Alembic/Ably 堆疊，不新增套件；循環法排程與多波次貪婪迴圈皆為應用層 Python 邏輯，重用 `apps/api/app/domains/schedule/algorithms.py` 既有的 `stage2_pair_players`/`team_matchup_stage2`/`greedy_pair_by_cost`，僅新增排列組合的外層迴圈函式，不需額外數值運算/圖論套件。

**Storage**：PostgreSQL，沿用既有 `matches`/`match_participants`/`pair_history`/`partnerships` 四張表（無新表）；`groups` 表新增一個欄位 `partner_source`（詳見 data-model.md）。

**Testing**：pytest + pytest-asyncio，沿用 003 既有測試基礎設施。核心領域邏輯（單打/固定搭檔的循環法生成正確性——場次數與涵蓋率、個人混搭多波次貪婪迴圈之覆蓋率與停止條件、場地「跳過忙碌參與者」的領取邏輯、`partner_source` 切換的資料保留）MUST 有單元測試；至少一條整合測試涵蓋「產生完整循環賽賽程 → 多場地依序消耗 → Round 完成判定 → Next Round 清空重排」全流程。

**Target Platform**：延續既有（Docker/AWS ECS，見 architecture.md）。

**Performance Goals**：不新增效能承諾（見 spec.md FR-013/SC-006/Assumptions）——大規模情境（例如單打 200 人一輪 19,900 場次）只承諾配對邏輯正確，產生耗時與消耗耗時不設 SLA。一般規模（數十人、個位數場地，沿用 003 既有 Scale/Scope 假設）下，Round 產生 MUST 與 003 既有 SC-001 同等時間量級（2 秒內）完成寫入。

**Constraints**：Round 生成 MUST 延續 003 既有的悲觀鎖（`SELECT ... FOR UPDATE NOWAIT`）與「整批交易內一次產生＋首次領取」設計（research.md #7 沿用不變）；`PairHistory` 累加時機（建立當下即累加，不因 `abandoned` 回滾）與計數語意（同場比賽任兩人皆計一次，不區分隊友/對手）沿用 003 既有決議，本次不重新設計。

**Scale/Scope**：延續 003 既有假設（單團輪替名單規模預期數十人、場地數個位數）為「效能有保證」的範圍；上限人數（200 人）僅保證正確性，見 Performance Goals。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | `Group.partner_source` 以 SQLAlchemy `Enum`/`Mapped[str]` 型別化並於 Pydantic schema 對應；新增的排程演算法函式（circle method、多波次迴圈）皆為純函式並附型別註記，納入 `mypy --strict`。 | PASS |
| II. 測試優先 | 循環法生成正確性（場次數、涵蓋率、零重複）、多波次貪婪迴圈之覆蓋率與停止條件、場地跳過忙碌參與者的領取邏輯、`partner_source` 切換資料保留，皆屬核心領域邏輯，MUST 有單元測試；至少一條整合測試涵蓋完整流程。 | PASS（列入 tasks.md 強制項） |
| III. 即時性與一致性（含比賽紀錄完整性） | Next Round 清空剩餘 `queued`/`in_progress` 比賽一律轉 `abandoned`（沿用既有原則，MUST NOT 產生 MatchResult）；比賽設定於建立當下複製快照的既有機制不變。 | PASS |
| IV. 權限與安全 | 新增的 `partner_source` 切換端點沿用既有 `require_admin`，不引入新的權限層級。 | PASS |
| V. UX 一致性 | `partner_source` 切換非破壞性操作（資料保留、可逆），不要求二次確認；Next Round 既有二次確認流程不變。 | PASS |
| VI. 可維護性 | 排程生成邏輯集中於既有 `app/domains/schedule/algorithms.py`（純函式，新增外層迴圈）與 `service.py`（呼叫端），不新建模組、不變更既有模組邊界；`partner_source` 讀寫限縮在 `group`/`schedule` 兩模組既有的擴充範圍內。 | PASS |
| VIII. i18n 與時區 | 新增的錯誤情境（例如固定搭檔人數非偶數）沿用既有語意化錯誤代碼機制，不寫死中文字串。 | PASS |
| IX. 可攜性 | 無新增基礎設施或外部依賴。 | PASS |
| X. 伺服器為單一事實來源 | 排程生成結果仍於 DB 交易提交後才發布既有 `match.nextRound`/`rotation.updated` 事件，前端不變更事件訂閱模型。 | PASS |
| XI. 防機器人 | 本 feature 端點皆需管理員驗證，不適用 Turnstile。 | PASS |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/011-round-robin-scheduling/
├── plan.md              # 本檔案
├── research.md          # Phase 0 產出
├── data-model.md        # Phase 1 產出
├── quickstart.md        # Phase 1 產出
├── contracts/            # Phase 1 產出
│   └── schedule-api-amendments.md
├── checklists/
│   └── requirements.md
└── tasks.md              # /speckit-tasks 產出（本指令不建立）
```

### Source Code (repository root)

```text
apps/api/
├── app/
│   ├── domains/
│   │   ├── schedule/
│   │   │   ├── algorithms.py    # 擴充：round_robin_pairs()（循環法）、
│   │   │   │                    #   generate_partner_coverage_waves()（多波次貪婪迴圈）
│   │   │   ├── service.py       # 修改：_generate_fair_rotation_matches（單打分支）、
│   │   │   │                    #   _generate_fixed_partner_matches、individual_mixed
│   │   │   │                    #   dispatch 改呼叫新演算法；pull_queued_match_for_court
│   │   │   │                    #   加入「跳過忙碌參與者」條件
│   │   │   └── schemas.py       # 擴充：partner_source 相關請求/回應欄位
│   │   └── group/
│   │       ├── models.py        # 擴充：Group.partner_source 欄位
│   │       ├── service.py       # 擴充：partner_source 讀寫、切換時的驗證
│   │       └── router.py        # 擴充：PATCH /groups/{group_id}/partner-source
│   └── ...                       # 其餘沿用既有
├── alembic/versions/
│   └── xxxx_add_group_partner_source.py   # 新增 migration
└── tests/
    ├── unit/domains/schedule/
    │   ├── test_round_robin_singles.py         # 新增
    │   ├── test_round_robin_fixed_partner.py   # 新增
    │   ├── test_round_robin_individual_mixed.py # 新增
    │   └── test_pull_queued_match_conflict.py  # 新增（跳過忙碌參與者）
    ├── unit/domains/group/
    │   └── test_partner_source_toggle.py       # 新增
    ├── contract/
    │   └── test_partner_source.py               # 新增
    └── integration/
        └── test_round_robin_full_flow.py        # 新增

apps/web/
└── src/app/features/group-admin/
    ├── admin-page/                # 修改：wait_count badge 於演算法模式下不再顯示
    │                                #   （見 research.md #5），改顯示「目前正在比賽」/
    │                                #   （無其他上場排序資訊可顯示）
    └── schedule-management/
        └── partnership-settings.component.ts  # 擴充：新增「手動／自動配對」切換 UI
```

**Structure Decision**：完全在既有 `app/domains/schedule` 與 `app/domains/group` 模組內擴充，不新建模組（符合原則 VI）；前端沿用既有 `group-admin` 目錄結構，僅擴充既有元件，不新增子目錄。

## Complexity Tracking

*本 feature 無 Constitution Check 違反項目，此表格從略。*

## Post-Design Constitution Check

*Re-evaluated after Phase 1（`data-model.md`、`contracts/`、`quickstart.md`）產出。*

設計階段的關鍵決策——(1) 單打/固定搭檔採循環法一次性生成、個人混搭採多波次貪婪迴圈重用既有函式（research.md #1、#2）、(2) 場地領取比賽新增「跳過忙碌參與者」條件、以現有 `matches.status`／`match_participants` 查詢實作、不新增資料表（research.md #4）、(3) `Group.partner_source` 為單一新欄位、切換不觸發刪除既有 `Partnership` 資料（research.md #6）——皆為在既有四張表與既有模組邊界內完成，未引入新的 Constitution 違反項目。`wait_count` 停用於演算法模式路徑（research.md #5）為既有欄位語意的窄化而非破壞性變更，手動模式行為完全不受影響，符合原則 VI 之模組邊界與既有行為不變更的要求。**Gate 結果維持 PASS，無需新增 Complexity Tracking 項目。**

## Assumptions

- 003-schedule-rotation、005-member-view 兩份既有 spec 與其對應測試中「一輪＝場地數場比賽、不會有排隊中比賽可領取」的敘述與斷言，將隨本 feature 實作不再成立；哪些既有文件段落與測試需要改寫，留待 `/speckit-tasks` 階段列為明確任務逐一盤點，本 plan 不重複列舉。
- `PairHistory` 沿用既有「同場比賽任兩人皆計一次、不區分隊友與對手」的計數語意（003 research.md #5）；個人混搭循環賽的「搭檔覆蓋」判斷因此無法單純依賴 `PairHistory` 數值本身，需在生成過程中另外追蹤「本次 Round 生成中已形成過的隊友組合」集合（僅為生成階段的執行期狀態，不落地為新資料表，見 data-model.md）。
- 手動安排（`manual`）排程機制完全不在本次變動範圍內，`wait_count`/`apply_wait_count_updates`/`stage1_select_players`/`team_stage1_select` 對該模式的既有行為 MUST 維持不變。
