# Tasks: 對戰紀錄衍生統計（發球得分率、比分走勢、每分耗時、落點分布）

**Input**: Design documents from `/specs/033-match-record-derived-stats/`

**Prerequisites**: plan.md、spec.md、research.md、data-model.md、contracts/、quickstart.md（皆已存在）

**Tests**：依 `plan.md` Constitution Check（原則 II），純函式模組 `match_stats.py` 的每一個函式 MUST 有單元測試，且測試任務 MUST **先於**對應的實作任務完成並確認為失敗（紅燈）；回應形狀 MUST 有契約測試。本檔案的測試任務為強制項，非選用。

**Organization**：依 spec.md 之 4 個 User Story（US1 P1、US2 P2、US3 P3、US4 P3）分階段。四者共用同一個前置——`effective_points()`（research.md Decision 2）、回應 schema、前端元件骨架——放在 Foundational；之後四個 Story 各自對應回應中的一個獨立欄位與前端的一個獨立 `<details>` 區塊，彼此無相依，可個別交付與驗證。

## Format: `[ID] [P?] [Story] Description`

- **[P]**：可平行執行（不同檔案、無相依關係）
- **[Story]**：對應 spec.md 的 US1–US4；Setup／Foundational／Polish 階段任務無此標籤
- 每項任務皆附精確檔案路徑

## Path Conventions

沿用 `plan.md` Project Structure：後端 `apps/api/`，前端 `apps/web/src/`。

---

## Phase 1: Setup

*本 feature 無 Setup 任務——不新增第三方依賴、不新增 migration（plan.md Technical Context）。*

---

## Phase 2: Foundational（Blocking Prerequisites）

**Purpose**：四個 Story 共用的「有效得分序列」、回應 schema、前端型別與元件骨架。

**⚠️ CRITICAL**：此階段完成前，不可開始任何 User Story 的工作。

- [X] T001 新增 `apps/api/app/domains/group/match_stats.py`：輸入／中間 dataclass（`RawEvent`、`ServeSnapshot`、`Placement`、`Participant`、`EffectivePoint`，皆 `frozen=True`，欄位依 data-model.md）與 `effective_points()` 的函式簽章（本體先 `raise NotImplementedError`）；模組 MUST NOT import 任何 ORM model 或 `AsyncSession`
- [X] T002 Unit test（先紅燈）：`effective_points()`——(a) 無修正時逐分重新累計比分；(b) `+1` 後同隊 `-1` 撤銷該分；(c) 連續兩次 `-1` 依序撤銷該隊最近兩分；(d) 亂序撤銷（A+1、B+1、A−1）後 B 那一分的重新累計比分為 0:1、`recorded_score` 仍為 1:1；(e) 有效得分數與 `final_score` 不符回傳 `None`；(f) `gap_is_clean`：全場第一筆事件為 `True`、前一筆為 `-1` 或為後來被撤銷的 `+1` 時為 `False` in `apps/api/tests/unit/domains/group/test_match_stats.py`（depends on T001）
- [X] T003 實作 `effective_points()`（逐隊堆疊撤銷＋第二趟重新累計與 `gap_is_clean` 判定，research.md Decision 2/5）於 `apps/api/app/domains/group/match_stats.py`，使 T002 全綠（depends on T002）
- [X] T004 [P] 新增回應 schema `ServeCounts`／`TeamServeStat`／`PlayerServeStat`／`ServeStats`／`ScoringRun`／`MaxLead`／`LeadChange`／`MomentumStats`／`LongestPoint`／`TempoStats`／`LandingPoint`／`PlayerLandingDistribution`，並於 `MatchRecordDetailResponse` 新增 `serve_stats`／`momentum_stats`／`tempo_stats`（預設 `None`）與 `landing_distribution`（預設 `[]`）於 `apps/api/app/domains/group/schemas.py`
- [X] T005 於 `build_match_record_detail()` 加入共用前置：`record_completeness == "complete"` 時把 `score_events` 轉成 `RawEvent`（`at_seconds` 用 `created_at - started_at` 的浮點秒）並呼叫 `effective_points()`；結果為 `None` 或紀錄不完整時四個新欄位維持預設值 in `apps/api/app/domains/group/service.py`（depends on T003, T004）
- [X] T006 [P] 新增前端 interface（與後端 JSON 一對一的 snake_case，見 data-model.md）並擴充 `MatchRecordDetailResponse` 於 `apps/web/src/app/core/api/group-member-view.models.ts`；同步補上既有測試 fixture 缺少的新欄位預設值於 `apps/web/src/app/core/match-record-detail/match-record-detail-dialog.component.spec.ts`
- [X] T007 新增 `MatchDerivedStatsComponent` 骨架（`detail` 為 required input；四個原生 `<details>` 區塊，第一個預設 `open`；每區塊先只放標題與無資料提示）於 `apps/web/src/app/core/match-record-detail/match-derived-stats/match-derived-stats.component.{ts,html,scss}`，並新增 `matchRecordDetail.derived.*` 的區塊標題與四則無資料提示於 `apps/web/src/assets/i18n/zh-TW.json` 與 `apps/web/src/assets/i18n/en.json`（depends on T006）
- [X] T008 於既有彈窗「球員得失分統計」區塊之後掛上 `<app-match-derived-stats>`（僅在 `record_completeness !== 'none'` 的既有分支內）於 `apps/web/src/app/core/match-record-detail/match-record-detail-dialog.component.{ts,html}`，並新增一則斷言子元件有被渲染的測試於 `match-record-detail-dialog.component.spec.ts`（depends on T007）

**Checkpoint**：後端回應已帶四個新欄位（皆為無資料預設值），前端四個區塊皆顯示無資料提示；既有測試全綠。

---

## Phase 3: User Story 1 - 發球／接發球得分率（Priority: P1）🎯 MVP

**Goal**：首度把 030 起就寫入、卻從未呈現的發球紀錄變成雙方與每位球員的發球／接發球得分率。

**Independent Test**：quickstart.md 情境 1／2／3——分母加總＋`excluded_points` 等於總比分、發球得分率不恆為 100%、單打不重複球員層級。

- [X] T009 [US1] Unit test（先紅燈）：`serve_stats()`——(a) 第一分恆被排除；(b) 第 *i* 分的發球方取自第 *i−1* 分的快照，side-out 與連續發球得分皆正確歸屬（斷言至少一隊 `won < total`，防止誤用得分後快照）；(c) 快照所屬事件的 `recorded_score` 與該分開打前比分不一致 → 排除並計入 `excluded_points`；(d) 前一分缺快照 → 排除；(e) 完全沒有快照、或全數被排除 → 回傳 `None`；(f) 雙打接發球者＝對方同名區球員；(g) 單打對方同名區為 `None` 時退回對方唯一參賽者，且 `players == []`；(h) 雙打 `players` 恆 4 筆、順序 `team_a`+`team_b`、含全 0 者；(i) 不變量 `sum(serve_points_total) + excluded_points == 總分` in `apps/api/tests/unit/domains/group/test_match_stats.py`
- [X] T010 [US1] 實作 `serve_stats()` 與其結果 dataclass（research.md Decision 3/4）於 `apps/api/app/domains/group/match_stats.py`，使 T009 全綠（depends on T009）
- [X] T011 [US1] 於 `build_match_record_detail()` 查詢 `ScoreServeRecord`（`WHERE match_id`）、轉成 `dict[event_id, ServeSnapshot]`、呼叫 `serve_stats()` 並組成 `ServeStats`（暱稱取自 `summary.team_a + team_b`）in `apps/api/app/domains/group/service.py`（depends on T010, T005）
- [X] T012 [US1] Unit test（經資料庫）：新增 fixture helper `_add_serve_record()`；驗證雙打比賽回傳正確的 `serve_stats`、沒有任何發球紀錄的比賽回傳 `None`、`record_completeness == "partial"` 的比賽四個新欄位皆為無資料 in `apps/api/tests/unit/domains/group/test_match_record_detail.py`（depends on T011）
- [X] T013 [P] [US1] 前端：發球統計區塊——隊伍層級表格（次數＋百分比，`total == 0` 顯示「0／0」與「—」）、雙打時的球員層級表格（`players.length > 0` 才顯示）、`excluded_points` 說明列、`serve_stats === null` 顯示無資料提示；對應文字加入兩份語系檔 in `apps/web/src/app/core/match-record-detail/match-derived-stats/match-derived-stats.component.{ts,html,scss}`、`apps/web/src/assets/i18n/{zh-TW,en}.json`
- [X] T014 [US1] 前端測試：上述四種狀態（有資料雙打、單打不顯示球員表、分母 0 顯示「—」、`null` 顯示提示）in `apps/web/src/app/core/match-record-detail/match-derived-stats/match-derived-stats.component.spec.ts`（depends on T013）

**Checkpoint**：US1 可獨立展示——這是 MVP。

---

## Phase 4: User Story 2 - 比分走勢摘要（Priority: P2）

**Goal**：每隊最長連續得分、最大領先、領先易手次數與各次比分。

**Independent Test**：quickstart.md 情境 5。

- [X] T015 [US2] Unit test（先紅燈）：`momentum_stats()`——(a) 最長連續得分含開始前／結束後比分；(b) 同長度取最早一段；(c) 整場 0 分的隊伍 `length == 0` 且比分為 `None`；(d) 最大領先回報**首次**達到該分差時的比分，從未領先 → `margin == 0`、比分 `None`；(e) 「A 領先→平手→A 再領先」不計易手；(f) 「A 領先→平手→B 領先」計一次且 `new_leader == "B"`；(g) 首次取得領先不算易手；(h) 一路領先 `lead_changes == []` in `apps/api/tests/unit/domains/group/test_match_stats.py`
- [X] T016 [US2] 實作 `momentum_stats()`（research.md Decision 6）於 `apps/api/app/domains/group/match_stats.py`，使 T015 全綠（depends on T015）
- [X] T017 [US2] 於 `build_match_record_detail()` 呼叫 `momentum_stats()` 並組成 `MomentumStats`；擴充經資料庫的單元測試一則（含一次 `-1` 修正的比賽，走勢不含被撤銷的那一分）in `apps/api/app/domains/group/service.py`、`apps/api/tests/unit/domains/group/test_match_record_detail.py`（depends on T016, T005）
- [X] T018 [P] [US2] 前端：走勢摘要區塊——兩隊最長連續得分（含比分區間）、最大領先、領先易手次數與清單（次數為 0 時不渲染清單）、`null` 顯示無資料提示；文字加入兩份語系檔 in `apps/web/src/app/core/match-record-detail/match-derived-stats/match-derived-stats.component.{ts,html,scss}`、`apps/web/src/assets/i18n/{zh-TW,en}.json`
- [X] T019 [US2] 前端測試：有資料、易手 0 次不渲染清單、`length`／`margin` 為 0 的呈現、`null` 顯示提示 in `apps/web/src/app/core/match-record-detail/match-derived-stats/match-derived-stats.component.spec.ts`（depends on T018）

---

## Phase 5: User Story 3 - 每分耗時（Priority: P3）

**Goal**：平均每分耗時與最長的一分，並明示為估計值。

**Independent Test**：quickstart.md 情境 4（耗時部分）。

- [X] T020 [US3] Unit test（先紅燈）：`tempo_stats()`——(a) 第一分自 0 秒（開賽）起算；(b) 其餘各分為與前一個有效得分的時間差；(c) `gap_is_clean == False` 的分數不計入平均、也不會被選為最長；(d) `average_seconds` 四捨五入至小數一位、`counted_points` 正確；(e) 最長的一分回報該分結束後的重新累計比分；(f) 沒有任何可計入的分 → `None` in `apps/api/tests/unit/domains/group/test_match_stats.py`
- [X] T021 [US3] 實作 `tempo_stats()`（research.md Decision 5）於 `apps/api/app/domains/group/match_stats.py`，使 T020 全綠（depends on T020）
- [X] T022 [US3] 於 `build_match_record_detail()` 呼叫 `tempo_stats()` 並組成 `TempoStats` in `apps/api/app/domains/group/service.py`（depends on T021, T005）
- [X] T023 [P] [US3] 前端：每分耗時區塊——平均值、最長的一分（秒數格式化為「X 分 Y 秒」，沿用既有 `elapsedParts` 的做法由模板組字）、固定顯示「估計值，包含回合之間的間隔」說明（FR-022）、`null` 顯示無資料提示；文字加入兩份語系檔；並補測試 in `apps/web/src/app/core/match-record-detail/match-derived-stats/match-derived-stats.component.{ts,html,spec.ts}`、`apps/web/src/assets/i18n/{zh-TW,en}.json`

---

## Phase 6: User Story 4 - 球員落點分布圖（Priority: P3）

**Goal**：選定球員後，一張球場圖同時呈現其全部得分落點與失分落點。

**Independent Test**：quickstart.md 情境 7。

- [X] T024 [US4] Unit test（先紅燈）：`landing_distribution()`——(a) 依 `scorer_id`／`loser_id` 分別歸入該球員的 `scored`／`lost`；(b) 有球員無座標的紀錄只計入 `*_total`、不產生點；(c) 界外座標原樣保留；(d) 所屬事件非有效得分的落點紀錄被忽略；(e) 全場沒有任何含座標的紀錄 → `[]`；(f) 非空時列出全部參賽者（含兩組皆空者），順序 `team_a`+`team_b` in `apps/api/tests/unit/domains/group/test_match_stats.py`
- [X] T025 [US4] 實作 `landing_distribution()`（research.md Decision 7）於 `apps/api/app/domains/group/match_stats.py`，使 T024 全綠（depends on T024）
- [X] T026 [US4] 於 `build_match_record_detail()` 重用 032 既有的 `placements` 查詢結果轉成 `Placement`、呼叫 `landing_distribution()` 並組成回應；擴充經資料庫的單元測試一則，斷言 `scored_total`／`lost_total` 與同一回應的 `player_stats[].scored_count`／`fault_count` 相等 in `apps/api/app/domains/group/service.py`、`apps/api/tests/unit/domains/group/test_match_record_detail.py`（depends on T025, T005）
- [X] T027 [P] [US4] 擴充 `CourtDiagramComponent`：新增選用輸入 `markers: CourtMarker[]`（預設 `[]`）；得分＝圓形、失分＝菱形（形狀區分，Constitution VII）；不裁切界外座標；既有 `landingX`／`landingY` 單點行為完全不變；補測試（多標記渲染、`kind` 對應的 class、既有單點測試仍通過）in `apps/web/src/app/core/court-diagram/court-diagram.component.{ts,html,scss,spec.ts}`
- [X] T028 [US4] 前端：落點分布區塊——球員選擇鈕（`aria-pressed`，預設第一位有落點的球員）、得分／失分兩個顯示切換、形狀＋文字圖例、「已標落點／總數」兩組比例（FR-026）、球員專屬無資料提示、整場 `[]` 時的無資料提示；文字加入兩份語系檔 in `apps/web/src/app/core/match-record-detail/match-derived-stats/match-derived-stats.component.{ts,html,scss}`、`apps/web/src/assets/i18n/{zh-TW,en}.json`（depends on T027）
- [X] T029 [US4] 前端測試：切換球員更新 `markers`、兩個顯示切換各自過濾、比例文字、球員專屬提示、整場無資料提示 in `apps/web/src/app/core/match-record-detail/match-derived-stats/match-derived-stats.component.spec.ts`（depends on T028）

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T030 [P] 契約測試：擴充既有兩個端點的回應形狀斷言，涵蓋 contracts/ 的不變量 1–4 與「既有欄位值不變」in `apps/api/tests/contract/test_group_match_record_detail.py`、`apps/api/tests/contract/test_member_match_record_detail.py`
- [X] T031 [P] 語系檔一致性：確認 `zh-TW.json` 與 `en.json` 的 `matchRecordDetail.derived.*` 鍵集合完全相同、模板中沒有寫死的中英文字串 in `apps/web/src/assets/i18n/`
- [X] T032 後端品質關卡：`ruff check app/ tests/`、`mypy app/`、`python -m pytest tests/` 全數通過 in `apps/api/`
- [X] T033 前端品質關卡：`npm run lint`、`npx tsc --noEmit -p tsconfig.app.json`、`npm test -- --watch=false` 全數通過 in `apps/web/`
- [X] T034 手機寬度版面檢查（FR-009）：新區塊預設僅第一個展開，既有趨勢圖／逐點清單位置不變；四個入口共用同一元件故只需驗證一處 in `apps/web/src/app/core/match-record-detail/`

---

## Dependencies & Execution Order

- **Foundational（T001–T008）** 阻擋全部 Story。其中 T004、T006 與 T001–T003 互不相依，可平行。
- **US1–US4 彼此獨立**：各自對應回應的一個欄位與前端的一個 `<details>` 區塊。後端任務都會改到 `match_stats.py`／`service.py`，前端任務都會改到同一個元件檔，因此同一人實作時依 P1→P2→P3 順序進行；多人時以 Story 為單位分工並留意合併衝突。
- 每個 Story 內：單元測試（紅）→ 純函式實作（綠）→ `service.py` 轉接 → 前端區塊 → 前端測試。前端區塊任務（標 [P]）只依賴 Foundational 的型別，可與同 Story 的後端任務平行。
- **Polish（T030–T034）** 於所有 Story 完成後進行。

## Parallel Example: User Story 1

```text
後端：T009 → T010 → T011 → T012
前端：T013 → T014            （與後端平行，T006 已提供型別）
```

## Implementation Strategy

1. **MVP**＝Foundational＋US1：首度呈現發球紀錄，且能暴露「得分後快照」語意是否處理正確（quickstart 情境 2）。
2. 之後依 US2 → US3 → US4 逐一疊加；每個 Story 完成即是一個可獨立驗證的增量，未完成的區塊維持 Foundational 的無資料提示，不影響已完成者。
