# Implementation Plan: 關鍵分表現與跨場個人技術儀表板

**Branch**: `feature/clutch-points-player-dashboard` | **Date**: 2026-09-17 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/034-clutch-points-player-dashboard/spec.md`，交叉比對 `/apps/api/app/domains/group/match_stats.py`（033 的純函式推導模組——`effective_points()`／`serve_stats()`／`momentum_stats()`／`landing_distribution()`）、`/apps/api/app/domains/group/service.py`（`build_match_record_detail()`／`_build_derived_stats()`——ORM → 純函式輸入的轉接）、`/apps/api/app/domains/member/service.py`（`build_member_match_records()`——篩選與彙總；`_resolve_viewable_member()`——好友檢視資格）、`/apps/api/app/domains/schedule/service.py`（`match_wins()`、`end_match_early()`——獲勝條件與 completed／abandoned 的產生路徑）、`/apps/api/app/domains/schedule/models.py`（`Match` 的賽制快照、三張逐分資料表的索引）、`/apps/web/src/app/core/match-record-detail/`、`/apps/web/src/app/core/court-diagram/`、`/apps/web/src/app/features/member/match-history/`、`/apps/web/src/app/features/friends/friend-match-records/`。

## Summary

兩件事，全部於查看當下由既有紀錄推導，**不新增資料表、欄位、索引、migration、寫入路徑或權限**：

1. **單場關鍵分**（US1）：`match_stats.py` 新增第五個純函式 `clutch_stats(points, target_score, cap_score)`，由 033 既有的有效得分序列＋該場比賽自己的賽制快照，推導局末階段、平分延長、賽末點（握有／兌現／化解）、依開打前比分狀態分組的得分率；逆轉摘要直接取自 033 的 `max_leads`。比賽詳情回應新增一個欄位 `clutch_stats`，三個既有端點（四個 UI 入口）自動全數套用。
2. **跨場儀表板**（US2–US5）：兩個新的唯讀端點（本人／好友），篩選參數與既有 `match-records` 完全相同。後端把「篩選後的完整比賽集合」自 `build_member_match_records()` 抽出共用；逐分資料以 3 次批次 `IN` 查詢載入；**單場詳情與儀表板共用同一組轉接函式與同一組純函式**，使「同一場比賽在兩處數字一致」由建構保證。新的純函式模組 `member/player_dashboard.py` 負責視角轉換（含落點旋轉 180° 的正規化）與彙總（總和相除、最近 10 場對比、進步判定、5 場移動趨勢）。

查證過程修正了規格的一處錯誤前提：`completed` 只會由自然達標產生，提前結束一律 `abandoned`（Constitution III），因此「已完成但未出現賽末點」的狀態不存在（research.md Decision 3）。

前端新增一個共用的 `PlayerDashboardComponent`（掛在個人對戰紀錄頁與好友戰績頁）與一個 `MatchClutchStatsComponent`（掛在 033 的衍生統計元件內）；趨勢圖沿用專案既有的手刻 SVG 寫法，不引入圖表套件。

## Technical Context

**Language/Version**：延續既有（後端 Python 3.12+，FastAPI + SQLAlchemy 2.0 async；前端 Angular 20 + TypeScript strict mode）。

**Primary Dependencies**：沿用既有堆疊，**不新增任何第三方套件**（前後端皆然）。

**Storage**：PostgreSQL，**不需要任何 Alembic migration**。唯讀存取 `matches`（含賽制快照）、`score_events`、`score_serve_records`、`shot_placement_records`、`match_participants`／`roster_entries`。儀表板新增 3 個以 `match_id IN (...)` 為條件的批次查詢，三張表的 `match_id` 皆已有索引。

**Testing**：
- 後端：pytest。
  - `tests/unit/domains/group/test_match_stats.py`（擴充，無資料庫）——`_wins` 與 `schedule.service.match_wins` 的網格一致性；`clutch_stats`：局末門檻與 `target < 11` 不適用、未進延長、延長多次往返、賽末點多次未兌現後兌現、敗方曾握賽末點、封頂前雙方賽末點、`cap == target`、比分狀態三組不變式、含撤銷／亂序撤銷的序列；`player_landings` 抽出後 `landing_distribution` 行為不變。
  - `tests/unit/domains/member/test_player_dashboard.py`（新，無資料庫）——`normalize_landing`（A 不動、B 旋轉、界外值、同一物理落點兩種身分得到同座標）；`build_sample`（我方／本人挑選、單打無 `own_*`、各區塊缺資料）；`aggregate`（總和相除≠百分比平均、各指標納入條件、`matches_used`、分母為 0、≤10 場無對比、`insufficient`、`unchanged` 門檻、越低越好的判定、`better_when = null`、趨勢點數＝n−4 與 60 點上限、<6 場無趨勢、落點前綴長度）。
  - `tests/unit/domains/member/test_member_match_dashboard.py`（新，經資料庫）——批次載入與轉接、篩選連動、028 綁定的比賽、逐分不完整的比賽仍計入最終比分類；**單一比賽的儀表板 vs. 該場詳情回應**的一致性（FR-003）；查詢次數不隨場數成長。
  - `tests/unit/domains/member/test_member_match_records.py`（既有，不改斷言）——作為 `_filtered_member_matches()` 重構的安全網。
  - `tests/unit/domains/group/test_match_record_detail.py`（擴充）——`clutch_stats` 的組裝、`comeback` 與 `max_leads` 一致、不完整紀錄 → `null`。
  - `tests/contract/`：`test_group_match_record_detail.py`／`test_member_match_record_detail.py`（擴充回應形狀）；`test_member_match_dashboard_endpoint.py`（新）——兩端點的回應形狀、篩選參數驗證、未驗證信箱的會員 403 `EMAIL_NOT_VERIFIED`、好友端點四種拒絕情境的狀態碼與錯誤代碼、`me` 路由不被 `{member_id}` 攔截。
- 前端：Vitest。`match-clutch-stats.component.spec.ts`（新）——五個項目的有值／不適用／未進延長／未曾握有賽末點／未曾落後／整塊無資料。`player-dashboard.component.spec.ts`＋`dashboard-metric-card`／`dashboard-trend-chart` 的 spec（新）——空狀態、指標無資料提示、「0／0 —」、依據場數、對比欄位的顯示與隱藏、verdict 以圖示＋文字呈現、趨勢不足提示、落點範圍切換取前綴、`dense` 門檻、我方標示。`court-diagram.component.spec.ts`（擴充）——`dense` 輸入、預設行為不變。`match-history.component.spec.ts`（擴充）——篩選觸發儀表板請求、翻頁不觸發。`friend-match-records.component.spec.ts`（擴充）——掛載、拒絕時不出現第二則錯誤。`match-derived-stats.component.spec.ts`（擴充）——子元件有被掛上。

**Target Platform**：延續既有（Docker on AWS ECS；行動裝置優先的瀏覽器支援範圍）。

**Project Type**：Web application（monorepo，同時涉及 `apps/api` 與 `apps/web`；範圍侷限於「查看比賽詳情」與「查看個人／好友對戰紀錄」兩條唯讀路徑）。

**Performance Goals**：300 場比賽的會員，`match-dashboard` 回應 < 3 秒；既有 `match-records` 的回應時間不受影響（兩者為獨立請求、平行載入）；比賽詳情仍在 2 秒內可讀（SC-007）。儀表板查詢次數為常數（既有 summaries 查詢＋3 次批次查詢），其後為記憶體內線性走訪（約 1.3 萬筆事件）。

**Constraints**：唯讀，MUST NOT 改動計分寫入路徑或任何已儲存資料（FR-001）；無資料時回傳 `null`／空陣列由前端顯示提示，MUST NOT 回傳全零結構（FR-004）；既有回應欄位、既有函式對外簽章、既有端點的授權判斷完全不變（FR-005）；同一場比賽的數字在單場與儀表板之間 MUST 來自同一段程式（FR-003）；新增文字全數進語系檔（FR-006）；所有統計規則（含進步判定）只存在於後端。

**Scale/Scope**：後端 1 個新純函式模組＋1 個既有純函式模組擴充＋2 個 service 擴充（含 1 次保持行為不變的重構）＋2 個新端點＋schemas；前端 2 組新元件（共 4 個元件）＋1 個共用元件小擴充＋2 個頁面掛載＋service 方法＋兩份語系檔。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | 新增的 Pydantic schema、純函式 dataclass、`MemberMatchFilters` 皆為明確型別，`mypy --strict` 通過；前端 `DashboardMetricKey` 為字串聯集，使語系 key 對照表與群組表在 strict mode 下受檢，無 `any`。`ruff`／`mypy`／`tsc --noEmit`／`ng lint` 沿用既有 blocking check。 | PASS |
| II. 測試優先 | 關鍵分是「比分計算」核心邏輯的讀取延伸（重述了獲勝條件），彙總規則細緻（總和相除、視角旋轉、進步方向）。兩個純函式模組 MUST 有完整單元測試並**先於實作撰寫**；`_wins` MUST 以網格測試鎖定與寫入路徑的 `match_wins()` 一致；新端點 MUST 有契約測試；`_filtered_member_matches()` 的重構以既有測試不改斷言通過為準。 | PASS（列入 tasks.md 強制項） |
| III. 即時性與資料一致性 | 不新增寫入路徑。只讀 `completed` 比賽（`_completed_matches_query()`），abandoned 不混入。賽制一律讀 `Match` 上的**快照**而非團的現行設定——正是本原則「設定變更的時間一致性」要求的讀法。本原則同時是 Decision 3 的依據（completed 必然自然達標）。儀表板非即時畫面，不訂閱事件；重新進入頁面即重新請求。 | PASS |
| IV. 權限與安全 | 兩個新端點皆使用 `require_verified_member`——本原則明定對戰紀錄在信箱驗證前 MUST 鎖定。**刻意不比照**既有 `GET /members/me/match-records` 的 `require_member`：那是 005 留下、與本原則不符的既有偏離，本功能不延續它，也不在此修正它（應另案處理）。好友端點經同一個 `_resolve_viewable_member()`，每次請求重新檢查、不快取資格，錯誤代碼不變。回應只含數值與座標——**不含任何暱稱或他人識別資訊**，揭露範圍小於既有 `match-records`。不新增隱私設定（依 023 既定的「明細與彙總同一開關」）。PR 描述 MUST 說明此授權邊界。 | PASS |
| V. 破壞性操作二次確認 | 純呈現，無破壞性操作。 | 不適用 |
| VI. 可維護性 | 規則（`match_stats`）、視角與彙總（`player_dashboard`）、查詢與轉接（service）三者分離；兩個純模組皆不 import ORM。`member` → `group` 的 import 方向為既有，未新增反向依賴；`group` 只多公開一個批次載入函式作為介面。前端儀表板為單一共用元件，兩頁掛載；球場繪製仍只有 `CourtDiagramComponent` 一份。 | PASS |
| VII. 無障礙與行動裝置優先 | 進步／退步以**圖示＋文字**表達、得分／失分落點以**形狀**＋圖例區分（FR-008）；百分比同時附分子／分母文字；區塊收合用原生 `<details>`；趨勢圖提供文字替代（`aria-label` 摘要起訖值）；指標選擇與範圍切換為原生按鈕並帶 `aria-pressed`；「我方」以文字標示。手機上比賽詳情的新區塊預設收合、儀表板僅第一群組展開（FR-007）。 | PASS |
| VIII. i18n 與時區 | 新增文字全數放入 `zh-TW.json`／`en.json`；後端只回傳指標 `key`／`verdict` 等語意代碼，不回傳顯示用句子；錯誤沿用既有 error code。趨勢點的時間為 `ended_at`（系統自動記錄的絕對時間戳，`TIMESTAMPTZ`）→ ISO 8601 UTC 回傳；既有 `date_from`／`date_to` 篩選的日期比較邏輯原封不動沿用，本功能不引入新的時區處理。 | PASS |
| IX. 可攜性與可部署性 | 無 migration、無新套件、無新環境變數。 | PASS |
| X. 伺服器為可信來源 | 不涉及寫入或廣播。所有統計規則與進步判定只存在於後端；前端只做呈現與陣列前綴切片。 | PASS |
| XI. 防濫用 | 不新增「建立新資源」端點；兩個新端點皆需登入。 | 不適用 |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

**Post-design re-check（Phase 1 完成後）**：data-model.md 與 contracts/ 確認——無新資料表／欄位／索引；新端點 2 個、皆唯讀、授權完全重用既有路徑；比賽詳情回應只新增一個具預設值的欄位；既有函式對外簽章不變；回應不含他人識別資訊。Phase 1 設計期間另查證出「影響的詳情端點是 3 個而非 4 個」（四個 UI 入口共用三個端點），已反映於 contract。Gate 結果維持 PASS。

**`/speckit-analyze` 後修正**：初版本列原則 IV 誤把「比照既有 `match-records` 的 `require_member`」當成 PASS，未對照憲章條文——已改為 `require_verified_member`（analyze C1）。同次一併修正：`match_points_saved` 改為每場平均使其可比較、可畫趨勢（I1）；FR-004／FR-015 的「0／0」措辭互斥（I2）；SC-007 後半缺驗證任務（G1）；純單打篩選時球場圖改畫單打場地（U1）。

## Project Structure

### Documentation (this feature)

```text
specs/034-clutch-points-player-dashboard/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── match-record-detail-api.md      # Phase 1 output：既有回應新增 clutch_stats
│   └── member-match-dashboard-api.md   # Phase 1 output：兩個新端點
├── checklists/
│   └── requirements.md  # /speckit-specify output
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
apps/api/
├── app/domains/group/
│   ├── match_stats.py          # 擴充：clutch_stats()、_wins()、ClutchResult 等 dataclass；
│   │                           #       抽出 player_landings()（landing_distribution() 對外行為不變）
│   ├── schemas.py              # 擴充：ClutchStats 及子型別；MatchRecordDetailResponse.clutch_stats
│   └── service.py              # 擴充：load_match_stat_inputs()（批次）＋模組層級轉接函式；
│                               #       _build_derived_stats() 改用同一組轉接函式並組出 clutch_stats
├── app/domains/member/
│   ├── player_dashboard.py     # 新增：純函式 normalize_landing() / build_sample() / aggregate()
│   ├── schemas.py              # 擴充：MemberMatchDashboardResponse 及子型別
│   ├── service.py              # 擴充：MemberMatchFilters、_filtered_member_matches()（自既有函式抽出）、
│   │                           #       build_member_match_dashboard()、view_member_match_dashboard()
│   └── router.py               # 擴充：GET /members/me/match-dashboard、
│                               #       GET /members/{member_id}/match-dashboard（me 在前）＋篩選參數 dependency
└── tests/
    ├── unit/domains/group/
    │   ├── test_match_stats.py              # 擴充
    │   └── test_match_record_detail.py      # 擴充
    ├── unit/domains/member/
    │   ├── test_player_dashboard.py         # 新增：純函式（無資料庫）
    │   ├── test_member_match_dashboard.py   # 新增：經資料庫
    │   └── test_member_match_records.py     # 既有：重構安全網，不改斷言
    └── contract/
        ├── test_group_match_record_detail.py        # 擴充
        ├── test_member_match_record_detail.py       # 擴充
        └── test_member_match_dashboard_endpoint.py  # 新增

apps/web/src/
├── app/core/
│   ├── api/
│   │   ├── group-member-view.models.ts       # 擴充：ClutchStats…
│   │   └── player-dashboard.models.ts        # 新增
│   ├── court-diagram/                        # 擴充：選用的 dense 輸入（＋spec）
│   ├── match-record-detail/
│   │   ├── match-clutch-stats/               # 新增：關鍵分區塊（ts/html/scss/spec）
│   │   └── match-derived-stats/              # 擴充：於「比分走勢摘要」後掛上關鍵分區塊（＋spec）
│   └── player-dashboard/                     # 新增
│       ├── player-dashboard.component.{ts,html,scss,spec.ts}
│       ├── dashboard-metric-card/            # 數值、分子／分母、依據場數、對比與 verdict
│       └── dashboard-trend-chart/            # 手刻 SVG 折線
├── app/features/
│   ├── auth/auth.service.ts                  # 擴充：getMatchDashboard()、getFriendMatchDashboard()
│   ├── member/match-history/                 # 擴充：掛載儀表板；只在篩選變更時請求（＋spec）
│   └── friends/friend-match-records/         # 擴充：掛載儀表板（＋spec）
└── assets/i18n/{zh-TW,en}.json               # 擴充：matchRecordDetail.clutch.*、playerDashboard.*
```

**Structure Decision**：沿用既有 monorepo 的 `apps/api`（domain 分層）與 `apps/web`（`core/` 共用元件、`features/` 頁面）配置。單場規則留在擁有 `build_match_record_detail()` 的 `group` domain；「我的視角」與跨場彙總屬會員視圖，放 `member` domain 的新純模組。儀表板元件放 `core/` 而非任一 feature 之下，因為它同時被 `member` 與 `friends` 兩個 feature 使用（與 `match-record-detail` 放在 `core/` 的理由相同）。

**建議實作順序**（供 `/speckit-tasks` 參考）：US1（`clutch_stats` → 詳情回應 → 前端區塊）→ 基礎重構（`_filtered_member_matches()`、`load_match_stat_inputs()`）→ US2（`build_sample`／`aggregate` 的 `all` 值 → 端點 → 元件與本人頁掛載）→ US3（`recent`／`verdict`／`trends` → 卡片對比與趨勢圖）→ US4（落點正規化 → 球場圖）→ US5（好友端點與掛載）。

## Complexity Tracking

無違反項目，本節不適用。
