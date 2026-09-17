# Implementation Plan: 得分方式紀錄（主動得分 vs. 對手失誤）

**Branch**: `feature/point-ending-type` | **Date**: 2026-09-18 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/035-point-ending-type/spec.md`，交叉比對 `/apps/api/app/domains/schedule/service.py`（`attach_shot_placement()`——三支補記端點唯一共用的寫入路徑；`_remove_last_shot_placement_record()`——`-1` 的收回）、`/apps/api/app/domains/schedule/models.py`（`ShotPlacementRecord`）、`/apps/api/alembic/versions/`（目前 head `d0c14187b0e3`）、`/apps/api/app/domains/group/match_stats.py` 與 `service.py`（033／034 的純函式推導與轉接）、`/apps/api/app/domains/member/player_dashboard.py`（034 的指標機制）、`/apps/web/src/app/features/shot-placement/`（三個入口共用的選擇畫面，已具備界內外／半場／發球失誤判定）、`/apps/web/src/app/core/match-record-detail/`、`/apps/web/src/app/core/player-dashboard/`。

## Summary

為詳細計分的每一分新增一個**選填**的「得分方式」（`winner`／`out`／`net`／`serve_fault`／`other_error`），並把它回饋到單場詳情與 034 的儀表板。

1. **儲存**：`shot_placement_records` 多一個可空欄位 `ending_type`——一支只含 `add_column` 的 migration。它與落點、球員同住一列，所以「確認時寫入一次、`-1` 時隨整列收回」由既有程式**不需修改**就成立。
2. **計分當下**：選擇畫面**已經**依官方規則判定落點，因此界外 → 自動帶入「對手出界」、發球失誤區 → 自動帶入「發球失誤」，零額外點擊；只有「界內落在失分方半場」有兩種解讀（打死 vs. 掛網），不自動帶入，計分員點一下。選項隨落點收斂；計分員親手選過的不被覆蓋，除非新落點使它自相矛盾。後端只存最終值，並擋下兩種與落點矛盾的組合。
3. **單場詳情**：新純函式 `match_stats.ending_stats()` 把每位球員的得分拆成「主動得分／對手失誤得分／未記錄」、失分拆成「被主動得分／自己失誤／未記錄」，外加隊伍摘要與失誤組成。
4. **儀表板**：在 034 的 `_METRICS` 多加 5 筆「每場 (分子, 分母)」貢獻——`aggregate()` 本體不動，對比／進步判定／趨勢／依據場數全部自動套用；另加一個失誤組成。

不新增端點、不新增權限、不回填舊比賽、不廣播。

## Technical Context

**Language/Version**：延續既有（後端 Python 3.12+，FastAPI + SQLAlchemy 2.0 async；前端 Angular 20 + TypeScript strict mode）。

**Primary Dependencies**：沿用既有堆疊，**不新增任何第三方套件**。

**Storage**：PostgreSQL。**需要一支 Alembic migration**：`shot_placement_records` 新增 `ending_type String(16) NULL`（`down_revision = 'd0c14187b0e3'`；`upgrade`／`downgrade` 各一行）。無新索引——讀取沿用既有的 `match_id` 索引與 034 的批次載入。既有列全為 NULL＝未記錄，不回填。

**Testing**：
- 後端：pytest。
  - `tests/unit/domains/schedule/test_shot_placement.py`（擴充）——五種值各自寫入、`null`／省略、只帶 `ending_type`、值域外、`winner`＋界外與 `out`＋界內被拒（單打較窄邊線的邊界各一）、`net`／`serve_fault`／`other_error` 不受落點限制、沒有落點不檢查、簡易模式仍被拒、既有錯誤的判定順序不變。
  - `tests/unit/domains/schedule/test_apply_score_delta.py`（擴充）——`-1` 後該列（含 `ending_type`）消失。
  - `tests/unit/domains/group/test_match_stats.py`（擴充，無資料庫）——`ending_stats`：歸屬（主動得分→得分球員、失誤→失分球員）、缺球員只進隊伍層級、各組相加等於 `player_landings()` 的總數、`errors_by_type` 加總、`recorded_points`、被撤銷的分不計、全場無紀錄 → `None`。
  - `tests/unit/domains/member/test_player_dashboard.py`（擴充，無資料庫）——`build_sample` 的 `ending`（FR-020 的納入條件）、5 項指標的分子分母與 `matches_used`、分母只含已記錄的分數、`winner_error_ratio` 失誤為 0 → `value None`、`errors_per_match` 下降判為 improved、`error_breakdown` 的 `all`／`recent`／`None`、指標總數 23 且前 18 項順序不變。
  - `tests/unit/domains/group/test_match_record_detail.py`、`tests/unit/domains/member/test_member_match_dashboard.py`（擴充，經資料庫）——`detail` 的「五欄全空才算空」、`ending_stats` 組裝、單一比賽的儀表板 vs. 該場 `ending_stats` 一致（FR-024）、查詢次數不變。
  - `tests/contract/`：`test_shot_placement_endpoint.py`、`test_group_match_record_detail.py`、`test_member_match_record_detail.py`、`test_member_match_dashboard_endpoint.py`（擴充）。
  - Migration：`alembic upgrade head` → `downgrade -1` → `upgrade head` 可逆（quickstart）。
- 前端：Vitest。`shot-placement-picker.component.spec.ts`（擴充）——自動帶入兩種、界內失分方半場不帶入、選項停用、親手選擇優先、矛盾時清除、點同一個取消、`confirmed` 帶出 `endingType`、窄螢幕下 chip 列位於落點分頁且不新增分頁。三個掛載點的 spec——多傳一格。`match-ending-stats.component.spec.ts`（新）、`match-record-detail-dialog.component.spec.ts`（逐點標籤）、`player-dashboard.component.spec.ts`／`dashboard-fixtures.ts`（新群組、23 項、失誤組成）。

**Target Platform**：延續既有（Docker on AWS ECS；行動裝置優先）。

**Project Type**：Web application（monorepo，`apps/api` 與 `apps/web`）。

**Performance Goals**：計分節奏不受影響——加分本身不等待補記請求（032 既有設計），補記請求只多一個欄位；連記 10 分的時間增幅 ≤ 10%（SC-002）。儀表板沿用 034 的批次載入，**不新增查詢**；300 場仍 < 3 秒（SC-010）。

**Constraints**：得分方式選填，MUST NOT 阻擋確認（FR-005）；簡易計分與所有既有比賽的畫面與資料不變（FR-004、FR-025）；既有三支補記端點、三支詳情端點、兩支儀表板端點的路徑／授權／既有欄位不變；032 的 `player_stats` contract 不變；新文字全數進語系檔；統計規則只存在於後端。

**Scale/Scope**：後端 1 支 migration＋1 個 model 欄位＋1 個 service 函式擴充＋2 個純函式模組擴充＋schemas；前端 1 個既有元件擴充（選擇器）＋3 個掛載點各一行＋1 個新元件＋詳情與儀表板的小擴充＋兩份語系檔。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | `EndingType` 在後端為 `Literal`、前端為字串聯集；儀表板的 `GROUP_OF` 是 exhaustive `Record`，新 key 漏掉分組即編譯失敗。`mypy --strict`／`tsc --noEmit`／lint 沿用既有 blocking check。 | PASS |
| II. 測試優先 | 觸及「比分計算」的周邊（補記寫入、`-1` 收回）與兩個純函式模組。純函式與寫入驗證的測試 MUST **先於實作**撰寫；三支補記端點、詳情、儀表板 MUST 有契約測試；`-1` 一併收回 MUST 有測試。 | PASS（列入 tasks.md 強制項） |
| III. 即時性與資料一致性 | 加分仍是既有的立即 +1，本功能不改變比分寫入與廣播；不新增廣播內容。統計只計 `completed` 比賽的有效得分；不回溯影響任何既有比賽（不回填）。設定快照原則不涉及——本功能沒有新設定。 | PASS |
| IV. 權限與安全 | 不新增端點；三支補記端點的授權判斷不變——得分方式與落點同屬「補記細節」，**不是**管理員專屬操作，出現在無需驗證的計分板／控制板上與既有的落點、球員選擇一致。儀表板沿用 `require_verified_member`；好友檢視沿用 `_resolve_viewable_member()`。新回應欄位不含任何新的識別資訊。 | PASS |
| V. 破壞性操作二次確認 | 無新的破壞性操作；`-1` 沿用既有流程。 | 不適用 |
| VI. 可維護性 | 規則（`match_stats.ending_stats`）、視角與彙總（`player_dashboard`）、寫入驗證（`schedule/service`）各在原本的模組；得分方式與落點同列儲存，不產生第二條需要同步的生命週期。前端三個掛載點只透傳。 | PASS |
| VII. 無障礙與行動裝置優先 | 主動得分／失誤以**圖示＋文字**區分，不只靠顏色；選項為原生按鈕並帶 `aria-pressed`，停用選項帶 `aria-disabled` 與說明；自動帶入的結果以文字標示「已依落點帶入」；chip 列放在既有落點分頁內，不把確認按鈕推出畫面（SC-011）。 | PASS |
| VIII. i18n 與時區 | 新文字全數放入 `zh-TW.json`／`en.json`；後端只回傳 `ending_type` 代碼與錯誤代碼，不回傳句子。不涉及新的時間處理。 | PASS |
| IX. 可攜性與可部署性 | 一支可逆的 `add_column` migration（可空、無預設值、不鎖表重寫）；無新套件、無新環境變數。部署順序：migration 先於新版後端——新版後端寫入該欄位，舊版前端不送該欄位亦相容。 | PASS |
| X. 伺服器為可信來源 | 得分方式經後端驗證（值域＋與落點的矛盾）後才寫入；自動帶入只是前端的互動預設值，最終存什麼以請求為準。統計與進步判定只在後端。 | PASS |
| XI. 防濫用 | 不新增「建立新資源」端點。 | 不適用 |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

**Post-design re-check（Phase 1 完成後）**：data-model.md 與 contracts/ 確認——唯一的儲存變更是一個可空欄位；無新端點、無新授權分支；三組既有回應各自只新增具預設值的欄位，032／033／034 的既有 contract 零變動。設計期間另有兩處回頭修正規格：(1) 選擇畫面實際只掛在三個入口（管理頁的場地控制沒有掛），FR-013 已更正；(2) 「親手選過的不被落點覆蓋」與「不保存矛盾的組合」相衝突，已在 FR-009 明訂例外並新增 FR-009a（選項隨落點收斂）。Gate 結果維持 PASS。

## Project Structure

### Documentation (this feature)

```text
specs/035-point-ending-type/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── shot-placement-api.md           # 三支補記端點新增 ending_type
│   ├── match-record-detail-api.md      # 逐點明細與 ending_stats
│   └── member-match-dashboard-api.md   # 5 項新指標與 error_breakdown
├── checklists/
│   └── requirements.md  # /speckit-specify output
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
apps/api/
├── alembic/versions/
│   └── <rev>_shot_placement_ending_type.py   # 新增：add_column / drop_column
├── app/domains/schedule/
│   ├── models.py        # 擴充：ShotPlacementRecord.ending_type
│   ├── schemas.py       # 擴充：EndingType、RecordShotPlacementRequest.ending_type
│   ├── service.py       # 擴充：attach_shot_placement(ending_type=…) 與兩條矛盾檢查
│   └── router.py        # 擴充：兩支端點透傳
├── app/domains/group/
│   ├── router.py        # 擴充：all-courts token 端點透傳
│   ├── match_stats.py   # 擴充：Placement.ending、ending_stats() 與結果 dataclass
│   ├── schemas.py       # 擴充：ShotPlacementSummary.ending_type、EndingStats…、
│   │                    #       MatchRecordDetailResponse.ending_stats
│   └── service.py       # 擴充：_to_placements() 帶出 ending、「五欄全空」、組裝 ending_stats
├── app/domains/member/
│   ├── player_dashboard.py  # 擴充：EndingSample、5 筆 _METRICS、error_breakdown
│   ├── schemas.py           # 擴充：DashboardErrorBreakdown、回應欄位
│   └── service.py           # 擴充：_dashboard_sample() 多傳 ending_stats 結果
├── scripts/seed_dashboard_demo.py            # 擴充：示範資料帶入得分方式
└── tests/                                     # 見 Technical Context

apps/web/src/
├── app/features/shot-placement/
│   └── shot-placement-picker.component.{ts,html,scss,spec.ts}  # 擴充：chip 列、自動帶入、收斂
├── app/features/{scoreboard,control-panel,control-panel/all-courts}/   # 擴充：透傳 endingType
├── app/core/api/
│   ├── court-control.service.ts        # 擴充：兩個方法多一個參數
│   ├── group-member-view.models.ts     # 擴充
│   └── player-dashboard.models.ts      # 擴充：5 個 key、error_breakdown
├── app/core/match-record-detail/
│   ├── match-ending-stats/             # 新增：隊伍摘要＋球員拆分（重用 _derived-blocks.scss）
│   ├── match-derived-stats/            # 擴充：掛上第六個 <details>
│   └── match-record-detail-dialog.*    # 擴充：逐點清單的得分方式標籤
├── app/core/player-dashboard/          # 擴充：新群組 ending、失誤組成、fixtures
└── assets/i18n/{zh-TW,en}.json         # 擴充
```

**Structure Decision**：沿用既有 monorepo 配置，沒有新的模組邊界。寫入屬 `schedule` domain（它擁有 `ShotPlacementRecord` 與補記端點）；單場推導屬 `group`（擁有 `match_stats` 與詳情組裝）；個人視角與跨場彙總屬 `member`——與 033／034 的分工完全一致，import 方向不變（`member` → `group`；`group` 唯讀 `schedule` 的 model）。

**建議實作順序**（供 `/speckit-tasks` 參考）：migration＋model＋寫入驗證（US1 後端）→ 選擇器與三個掛載點（US1 前端）→ `ending_stats()`＋詳情回應＋新元件與逐點標籤（US2）→ 5 項指標＋失誤組成＋儀表板新群組（US3）。US1 完成即可開始累積資料，即使 US2／US3 尚未上線也不會白記。

## Complexity Tracking

無違反項目，本節不適用。
