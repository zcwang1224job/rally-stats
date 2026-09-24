# Implementation Plan: 對戰紀錄衍生統計（發球得分率、比分走勢、每分耗時、落點分布）

**Branch**: `feature/match-record-serve-stats` | **Date**: 2026-09-17 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/033-match-record-derived-stats/spec.md`，交叉比對 `/apps/api/app/domains/group/service.py`（`build_match_record_detail()`——四個對戰紀錄詳細端點的唯一共用組裝入口）、`/apps/api/app/domains/schedule/service.py`（`_advance_serve_state_and_snapshot()`／`apply_score_delta()`——發球快照與 `-1` 修正的實際寫入語意）、`/apps/api/app/domains/schedule/models.py`（`ScoreEvent`／`ScoreServeRecord`／`ShotPlacementRecord`）、`/apps/web/src/app/core/match-record-detail/`（四個入口共用的比賽詳情彈窗）、`/apps/web/src/app/core/court-diagram/`（032 抽出的唯讀球場示意圖）。

## Summary

在既有「比賽詳情」回應（`MatchRecordDetailResponse`）新增四個唯讀欄位——`serve_stats`、`momentum_stats`、`tempo_stats`、`landing_distribution`——全部於查看當下由既有的 `score_events`、`score_serve_records`、`shot_placement_records` 推導，**不新增資料表、欄位、migration、端點或寫入路徑**。計算邏輯放在新的純函式模組 `group/match_stats.py`（不碰資料庫，可窮舉測試），`build_match_record_detail()` 只多一次 `score_serve_records` 查詢並負責轉接；四個端點共用該函式，故自動全數套用。

本功能最關鍵的設計依據是一項對既有資料語意的查證：發球快照是在**得分並完成換發球之後**寫入的，因此某一分的發球者必須取自**前一個有效得分**的快照，且每場第一分的發球方無從還原（research.md Decision 3/4）。`-1` 修正以「逐隊堆疊撤銷」還原出最終仍成立的得分序列，四類統計都建立在這個序列上（Decision 2）。

前端新增一個呈現元件 `MatchDerivedStatsComponent`，以四個原生 `<details>` 區塊掛在既有彈窗內；落點分布重用 `CourtDiagramComponent`，為其新增多標記輸入（圓形＝得分、菱形＝失分）。

## Technical Context

**Language/Version**：延續既有（後端 Python 3.12+，FastAPI + SQLAlchemy 2.0 async；前端 Angular 20 + TypeScript strict mode）。

**Primary Dependencies**：沿用既有堆疊，**不新增任何第三方套件**。

**Storage**：PostgreSQL，**不需要任何 Alembic migration**。唯讀存取 `score_events`（007）、`score_serve_records`（030）、`shot_placement_records`（031/032）、`match_participants`／`roster_entries`。新增的唯一查詢以 `score_serve_records.match_id`（既有索引）為條件。

**Testing**：
- 後端：pytest。`tests/unit/domains/group/test_match_stats.py`（新）——純函式，不需資料庫，涵蓋有效得分判定（一般撤銷、連續撤銷、亂序撤銷、與最終比分對不上）、發球歸屬（第一分排除、side-out、快照比分不一致、缺快照、單打／雙打接發球者）、走勢（連續得分同長取最早、平手不算易手、0 分隊伍）、耗時（第一分自開賽起算、修正區間排除、無可計入分）、落點彙整。`tests/unit/domains/group/test_match_record_detail.py`（擴充）——經資料庫的整合式單元測試，驗證查詢與轉接。`tests/contract/test_group_match_record_detail.py`／`test_member_match_record_detail.py`（擴充）——回應形狀。
- 前端：Vitest。`match-derived-stats.component.spec.ts`（新）——四區塊各自的有資料／無資料狀態、`excluded_points` 說明、單打不顯示球員層級、球員切換與得失分顯示切換。`court-diagram.component.spec.ts`（擴充）——多標記輸入、界外座標不裁切、既有單點行為不變。`match-record-detail-dialog.component.spec.ts`（擴充）——子元件有被掛上。

**Target Platform**：延續既有（Docker on AWS ECS；行動裝置優先的瀏覽器支援範圍）。

**Project Type**：Web application（monorepo，同時涉及 `apps/api` 與 `apps/web`，範圍侷限於「查看比賽詳情」這一條唯讀路徑）。

**Performance Goals**：比賽詳情載入時間不因本功能明顯劣化（SC-006）。新增一次以索引欄位為條件的查詢＋對單場事件（一般 ≤ 60 筆）的數次線性走訪，不需分頁或快取。

**Constraints**：唯讀，MUST NOT 改動計分寫入路徑或任何已儲存資料（FR-008）；無資料時 MUST 回傳 `null`／空陣列由前端顯示提示，MUST NOT 回傳全零結構（FR-003）；既有回應欄位與既有四個端點的授權判斷完全不變（FR-006）；新增文字全數進語系檔（FR-007）。

**Scale/Scope**：後端 1 個新模組＋1 個既有函式擴充＋schemas；前端 1 個新元件＋1 個既有共用元件擴充＋彈窗掛載＋兩份語系檔。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | 新增的 Pydantic schema 與純函式 dataclass 皆為明確型別，`mypy --strict` 通過；前端新 interface 於 strict mode 下定義，無 `any`。`ruff`／`mypy`／`tsc --noEmit`／`ng lint` 沿用既有 blocking check。 | PASS |
| II. 測試優先 | 本功能是「比分計算」核心邏輯的讀取延伸，且規則細緻（撤銷語意、發球歸屬）。純函式模組 MUST 有完整單元測試並**先於實作撰寫**；回應形狀 MUST 有契約測試。 | PASS（列入 tasks.md 強制項） |
| III. 即時性與資料一致性 | 不新增寫入路徑。只查詢已完成（`completed`）比賽，已捨棄比賽依既有 `_completed_matches_query()` 本就排除，不會有未完賽資料混入統計。 | PASS |
| IV. 權限與安全 | 不新增端點，四個既有端點的授權判斷式不變。新欄位中的球員識別與暱稱全部來自該回應原本就回傳的 `team_a`／`team_b`，未擴大揭露範圍。暱稱經既有 `<app-nickname>` 呈現（既有逸出機制）。 | PASS |
| V. 破壞性操作二次確認 | 純呈現，無破壞性操作。 | 不適用 |
| VI. 可維護性 | 計算獨立成純函式模組，與查詢／組裝分離；前端四區塊獨立成子元件；球場繪製仍只有 `CourtDiagramComponent` 一份。 | PASS |
| VII. 無障礙與行動裝置優先 | 得分／失分標記以**形狀**（圓／菱形）＋文字圖例區分，不只靠顏色（FR-024）；區塊收合用原生 `<details>`（內建鍵盤與語意）；球員切換鈕帶 `aria-pressed`；百分比同時附次數文字。手機上預設只展開第一個新區塊（FR-009）。 | PASS |
| VIII. i18n 與時區 | 新增文字全數放入 `zh-TW.json`／`en.json`；後端不回傳任何顯示用句子。耗時為 UTC 時間戳相減的時間差，與顯示時區無關，不涉及場地時間規則。 | PASS |
| IX. 可攜性與可部署性 | 無 migration、無新套件、無新環境變數。 | PASS |
| X. 伺服器為可信來源 | 不涉及寫入或廣播。統計規則只存在於後端一處，前端不自行推導。 | PASS |
| XI. 防濫用 | 不新增「建立新資源」端點。 | 不適用 |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

**Post-design re-check（Phase 1 完成後）**：data-model.md 與 contracts/ 確認仍無新資料表、無新端點、無新授權分支；回應只新增四個具預設值的欄位，既有呼叫端零行為變動。Gate 結果維持 PASS。

## Project Structure

### Documentation (this feature)

```text
specs/033-match-record-derived-stats/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── match-record-detail-api.md   # Phase 1 output
├── checklists/
│   └── requirements.md  # /speckit-specify output
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
apps/api/
├── app/domains/group/
│   ├── match_stats.py          # 新增：純函式＋輸入/輸出 dataclass（不 import ORM、不碰 session）
│   ├── schemas.py              # 擴充：ServeStats / MomentumStats / TempoStats / PlayerLandingDistribution…；
│   │                           #       MatchRecordDetailResponse 新增四個欄位
│   └── service.py              # 擴充：build_match_record_detail() 多查 ScoreServeRecord、呼叫 match_stats
└── tests/
    ├── unit/domains/group/
    │   ├── test_match_stats.py            # 新增：純函式單元測試（無資料庫）
    │   └── test_match_record_detail.py    # 擴充：經資料庫的查詢＋轉接
    └── contract/
        ├── test_group_match_record_detail.py    # 擴充：回應形狀
        └── test_member_match_record_detail.py   # 擴充：回應形狀

apps/web/src/
├── app/core/
│   ├── api/group-member-view.models.ts            # 擴充：新回應欄位的 interface
│   ├── court-diagram/
│   │   ├── court-diagram.component.{ts,html,scss} # 擴充：選用的 markers 輸入（圓＝得分、菱形＝失分）
│   │   └── court-diagram.component.spec.ts        # 擴充
│   └── match-record-detail/
│       ├── match-derived-stats/                   # 新增：四區塊呈現元件
│       │   ├── match-derived-stats.component.{ts,html,scss}
│       │   └── match-derived-stats.component.spec.ts
│       ├── match-record-detail-dialog.component.{ts,html}   # 擴充：掛上子元件
│       └── match-record-detail-dialog.component.spec.ts     # 擴充
└── assets/i18n/{zh-TW,en}.json                    # 擴充：matchRecordDetail.derived.* 文字
```

**Structure Decision**：沿用既有 monorepo 的 `apps/api`（domain 分層）與 `apps/web`（`core/` 共用元件）配置。後端新增的檔案只有一個純函式模組，放在擁有 `build_match_record_detail()` 的 `group` domain 內；它只接受純資料輸入，因此不構成對 `schedule` domain 內部實作的依賴（Constitution VI）——讀取 `schedule` 的 ORM model 這件事仍只發生在既有的 `group/service.py`，與 032 現況相同。

## Complexity Tracking

無違反項目，本節不適用。
