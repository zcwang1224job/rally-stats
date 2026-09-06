# Tasks: 循環賽賽程排程（Round-Robin Scheduling）

**Input**: Design documents from `/specs/011-round-robin-scheduling/`

**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md（皆已存在）

**Tests**: 依 `plan.md` Constitution Check（原則 II），核心領域邏輯（循環法生成正確性、多波次貪婪迴圈之覆蓋率與停止條件、場地跳過忙碌參與者的領取邏輯、`partner_source` 切換資料保留）MUST 有單元測試，且 MUST 有至少一條整合測試涵蓋完整流程——本檔案的測試任務為強制項，非選用。

**Organization**：依 spec.md 之 4 個 User Story（US1、US4 為 P1；US2、US3 為 P2）分階段組織。US1、US4 合為 MVP（單打全員循環賽 + Next Round 正確清空重排即可獨立展示核心價值）；US2、US3 為後續優先項目。

## Format: `[ID] [P?] [Story] Description`

- **[P]**：可平行執行（不同檔案、無相依關係）
- **[Story]**：對應 spec.md 的 US1–US4
- 每項任務皆附精確檔案路徑

## Path Conventions

沿用 `plan.md` Project Structure：`apps/api/`（FastAPI 後端）、`apps/web/`（Angular 20 前端）。monorepo 骨架已由 001 建立並沿用。

---

## Phase 1: Setup

*本 feature 無新增 Setup 任務——monorepo、CI、linting/型別檢查工具鏈已完整建立並沿用。*

---

## Phase 2: Foundational（Blocking Prerequisites）

**Purpose**：US1～US4 皆依賴的資料庫欄位、通用排點演算法函式、以及場地領取比賽時的防重複上場檢查。

**⚠️ CRITICAL**：此階段完成前不可開始任何 User Story 任務。

- [X] T001 Create Alembic migration adding `groups.partner_source`（`VARCHAR NOT NULL DEFAULT 'manual'`）per `data-model.md` in `apps/api/alembic/versions/`
- [X] T002 [P] Add `partner_source` column to `Group` SQLAlchemy model in `apps/api/app/domains/group/models.py`
- [X] T003 [P] Implement `round_robin_pairs(units: Sequence[T]) -> list[list[tuple[T, T]]]`（循環法，回傳依「批次」分組、批次內互不衝突的兩兩組合序列，count 為奇數時內部處理輪空並排除）in `apps/api/app/domains/schedule/algorithms.py` per research.md #1
- [X] T004 [P] Unit test：`round_robin_pairs()` 涵蓋偶數/奇數輸入、總組合數等於 C(n,2)、每組合恰出現一次、批次內無重複元素 in `apps/api/tests/unit/domains/schedule/test_round_robin_pairs.py`
- [X] T005 Modify `pull_queued_match_for_court()` in `apps/api/app/domains/schedule/service.py`：新增條件跳過任一參與者目前在同團其他場地「進行中」比賽的候選場次，依原建立順序找出第一筆通過條件者，找不到則維持回傳 `None`（research.md #4）
- [X] T006 [P] Unit test：`pull_queued_match_for_court()` 在有多筆排隊中比賽時，正確跳過參與者正忙碌的場次、領取下一筆可行場次；全部候選皆忙碌時回傳 `None` in `apps/api/tests/unit/domains/schedule/test_pull_queued_match_conflict.py`
- [X] T006a（實作中新增，未在原規劃列出）Modify `_advance_after_terminal()` to also re-check every OTHER idle court in the group (not just the one whose match just ended) via new `_advance_other_idle_courts()` — a full round-robin can leave a court idle only because its candidates were busy elsewhere, a block that lifts the instant any match ends anywhere in the group, not just on that specific court in `apps/api/app/domains/schedule/service.py`
- [X] T006b（實作中新增）Unit test：ending a match unblocks a different, previously-idle court (not just the ending court itself) in `apps/api/tests/unit/domains/schedule/test_advance_other_idle_courts.py`

**Checkpoint**：Foundation ready — User Story 任務可以開始。

---

## Phase 3: User Story 1 - 單打：全員循環賽賽程 (Priority: P1) 🎯 MVP

**Goal**：公平輪替排程機制、單打比賽模式下，一個 Round 一次產生「在場輪替名單每兩人恰對戰一次」的完整賽程，供場地依序消耗。

**Independent Test**：在僅使用公平輪替＋單打模式的團上，觸發 Round 產生，驗證賽程表場次數為 C(n,2)、涵蓋所有兩兩組合、場地依序消耗且不會讓同一人分身上場，直到賽程表全部消耗完畢才視為 Round 完成。

### Tests for User Story 1

- [X] T007 [P] [US1] Unit test：`_generate_fair_rotation_matches()` 單打分支呼叫 `round_robin_pairs()` 產生恰好 C(n,2) 場、涵蓋所有兩兩組合、皆為 `queued` 狀態 in `apps/api/tests/unit/domains/schedule/test_round_robin_singles.py`
- [X] T008 [P] [US1] Integration test：5 人單打、1 場地——產生 Round 後資料庫可查得 10 筆 `queued` 比賽；依序結束比賽直到全部消耗完畢，`round_is_complete()` 才回傳真（quickstart 情境 1）in `apps/api/tests/integration/test_round_robin_singles_flow.py`

### Implementation for User Story 1

- [X] T009 [US1] 修改 `_generate_fair_rotation_matches()` in `apps/api/app/domains/schedule/service.py`：`match_mode == "singles"` 分支改為對「當時所有在場輪替名單成員」呼叫 `round_robin_pairs()` 產生完整賽程，不再呼叫 `_get_active_roster_for_selection`/`stage1_select_players`/`apply_wait_count_updates`；`match_mode == "doubles"`（雙打）分支維持既有「依場地數量填滿」邏輯完全不變（depends on T003, T009 前置 T003）
- [X] T010 [US1] 執行既有雙打 fair_rotation 相關測試（`test_next_round_fair_rotation.py`、`test_fair_rotation_flow.py`、`test_schedule_lifecycle.py`）確認 T009 未變更雙打行為，全數維持通過 in `apps/api/tests/`（regression check，無需修改檔案內容，僅驗證）
- [X] T011 [US1] 更新既有測試對「單打 fair_rotation 產生比賽數＝場地數」的過期假設：`apps/api/tests/integration/test_round_number_consistency.py`、`apps/api/tests/integration/test_scoring_lifecycle.py`、`apps/api/tests/integration/test_scoring_flow.py`（皆為 8 人 2 場地單打情境，原斷言「每輪固定 2 場」需改為驗證「賽程表共 C(8,2)=28 場、場地依序消耗」）(depends on T009)
- [X] T012 [P] [US1] 前端：`wait_count` 徽章顯示邏輯加上 `scheduling_mechanism === 'manual'` 條件（演算法模式下不再顯示凍結不變的數字，research.md #5）in `apps/web/src/app/features/group-admin/admin-page/admin-page.component.html`

**Checkpoint**：US1 完整可運作——可獨立展示「單打全員循環賽產生 → 場地依序消耗 → Round 完成判定」。

---

## Phase 4: User Story 4 - Next Round：清空剩餘賽程並重新排整輪 (Priority: P1)

**Goal**：管理員在任何時候按下 Next Round，系統把當下賽程表所有排隊中／進行中比賽捨棄，並依當時排程機制重新產生下一輪的完整循環賽賽程。

**Independent Test**：在任一排程機制的團上，於賽程表尚有未消耗場次時按下 Next Round，驗證剩餘比賽全部被捨棄、新一輪完整賽程被重新產生。

### Tests for User Story 4

- [X] T013 [P] [US4] Integration test：單打 5 人團，賽程表 10 場僅完成 3 場時按下 Next Round——驗證剩餘 7 場全部轉為 `abandoned`、新 `round_number` 下重新產生 10 場新賽程（quickstart 情境 7）in `apps/api/tests/integration/test_round_robin_next_round_reset.py`

### Implementation for User Story 4

- [X] T014 [US4] 確認 `generate_next_round()` 既有的悲觀鎖／`abandon_group_matches()` 呼叫順序（research.md #7、#8）在新演算法下不需修改；若 T013 測試發現任何邊界情況（例如捨棄時機與新賽程生成的交易邊界）不正確，於 `apps/api/app/domains/schedule/service.py` 修正 (depends on T009；若 US2/US3 已完成則一併涵蓋固定搭檔／個人混搭情境，否則本階段僅驗證單打路徑)

**Checkpoint**：US1 + US4 構成可交付的 MVP——單打模式下的完整循環賽生成與強制重排皆正確運作。

---

## Phase 5: User Story 2 - 固定搭檔循環賽：完整循環賽＋搭檔來源可選 (Priority: P2)

**Goal**：固定搭檔循環賽（人數需偶數）一個 Round 產生「每隊對戰其他每隊恰一次」的完整賽程；搭檔來源可在「手動搭檔設定」與「自動配對」間切換，切換不遺失任一方資料。

**Independent Test**：分別測試手動與自動兩種搭檔來源下的 Round 產生結果，驗證奇數人數防呆、隊伍循環賽場次數與涵蓋率、自動配對的重複率降低、切換來源不遺失資料。

### Tests for User Story 2

- [X] T015 [P] [US2] Unit test：固定搭檔隊伍循環賽——m 支隊伍呼叫 `round_robin_pairs()` 產生恰好 C(m,2) 場隊伍對戰、零重複 in `apps/api/tests/unit/domains/schedule/test_round_robin_fixed_partner.py`
- [X] T016 [P] [US2] Unit test：固定搭檔循環賽在場人數為奇數時，`generate_next_round()` 拋出 `FIXED_PARTNER_REQUIRES_EVEN_HEADCOUNT`，不產生賽程、`current_round_number` 不變（實際併入 `test_round_robin_fixed_partner.py`，未另建檔案）in `apps/api/tests/unit/domains/schedule/test_round_robin_fixed_partner.py`
- [X] T017 [P] [US2] Unit test：`partner_source = 'auto'` 時的隊伍組成依 `PairHistory` 配對次數最少原則計算（重用 `stage2_pair_players`），且與既有 `auto_pair_on_enter_fixed_partner()` 為不同函式、不寫入 `partnerships` 表 in `apps/api/tests/unit/domains/schedule/test_auto_partner_source.py`
- [X] T018 [P] [US2] Unit test：`partner_source` 在 `'manual'`/`'auto'` 間切換時，`partnerships` 表資料列完全不受影響（新增、修改、刪除筆數皆為零）in `apps/api/tests/unit/domains/group/test_partner_source_toggle.py`
- [X] T019 [P] [US2] Contract test：`PATCH /groups/{group_id}` 接受 `partner_source` 欄位並回傳於 `AdminGroupResponse`；`POST /groups/{group_id}/next-round` 於奇數人數時回傳 400 `FIXED_PARTNER_REQUIRES_EVEN_HEADCOUNT` in `apps/api/tests/contract/test_partner_source.py`
- [X] T020 [US2] Integration test：8 人雙打固定搭檔團——手動搭檔設定產生 6 場隊伍循環賽 → 切換為自動配對再次產生 Round → 切回手動、原搭檔資料原樣恢復（quickstart 情境 2～4）in `apps/api/tests/integration/test_fixed_partner_round_robin_flow.py`

### Implementation for User Story 2

- [X] T021 [US2] `EditGroupRequest`/`AdminGroupResponse` schema 新增 `partner_source` 欄位（選填）in `apps/api/app/domains/group/schemas.py`
- [X] T022 [US2] `edit_group()` 新增 `partner_source` 讀寫邏輯：僅在 `scheduling_mechanism == 'fixed_partner'` 時生效，非該機制時忽略此欄位、不視為錯誤 in `apps/api/app/domains/group/service.py`(depends on T002, T021)
- [X] T023 [US2] 實作 `compute_auto_partner_teams_for_round(session, group_id) -> list[tuple[uuid.UUID, uuid.UUID]]`（依 `PairHistory` 配對次數最少原則、重用 `stage2_pair_players`，命名刻意與既有 `auto_pair_on_enter_fixed_partner()` 區隔，見 research.md #6 命名澄清）in `apps/api/app/domains/schedule/service.py`
- [X] T024 [US2] 修改 `_generate_fixed_partner_matches()` in `apps/api/app/domains/schedule/service.py`：新增偶數人數驗證（不足則拋出 `FIXED_PARTNER_REQUIRES_EVEN_HEADCOUNT`）；依 `group.partner_source` 決定隊伍來源（`'manual'` 讀 `Partnership` 表、`'auto'` 呼叫 T023）；隊伍決定後呼叫 `round_robin_pairs()` 產生完整隊伍對戰賽程，不再呼叫 `team_stage1_select`/`apply_wait_count_updates`(depends on T003, T023)
- [X] T025 [US2] 新增 `FIXED_PARTNER_REQUIRES_EVEN_HEADCOUNT` 錯誤代碼至既有錯誤代碼定義，`generate_next_round()`/router 層正確回傳 400 in `apps/api/app/domains/schedule/service.py`、`apps/api/app/domains/schedule/router.py`(depends on T024)
- [X] T026 [P] [US2] 前端：`partnership-settings.component.ts` 新增「手動／自動配對」搭檔來源切換 UI，呼叫既有 `PATCH /groups/{group_id}` 帶上 `partner_source` in `apps/web/src/app/features/group-admin/schedule-management/partnership-settings.component.ts`
- [X] T027 [P] [US2] 前端：`group-admin.service.ts` 編輯團設定的呼叫passthrough `partner_source` 欄位 in `apps/web/src/app/features/group-admin/group-admin.service.ts`

**Checkpoint**：US1、US4、US2 皆可獨立運作。

---

## Phase 6: User Story 3 - 個人混搭循環賽：全員搭檔一輪 (Priority: P2)

**Goal**：個人混搭循環賽一個 Round 排出「每個人都跟其他每個人搭檔過一次」（在組合數學限制內盡量完整覆蓋）的賽程。

**Independent Test**：觸發 Round 產生，驗證賽程涵蓋所有人兩兩搭檔組合（可行範圍內）、隊伍對戰組合依既有配對次數規則決定、多波次迴圈能在有限步驟內正確停止。

### Tests for User Story 3

- [X] T028 [P] [US3] Unit test：多波次貪婪迴圈對 8 人（可完美覆蓋之人數）產生的賽程涵蓋全部 C(8,2)=28 組搭檔恰一次 in `apps/api/tests/unit/domains/schedule/test_round_robin_individual_mixed.py`
- [X] T029 [P] [US3] Unit test：對無法完美覆蓋的人數輸入，某一波無新搭檔組合時迴圈正確停止且不寫入該波（不進入無限迴圈），涵蓋率為「已產生波次中的最大可行覆蓋」in `apps/api/tests/unit/domains/schedule/test_round_robin_individual_mixed.py`
- [X] T030 [US3] Integration test：8 人雙打個人混搭團、2 場地——產生 Round 後查詢 `match_participants` 同隊組合，驗證涵蓋 28 組搭檔（quickstart 情境 5）in `apps/api/tests/integration/test_individual_mixed_round_robin_flow.py`

### Implementation for User Story 3

- [X] T031 [US3] 實作 `generate_individual_mixed_round_robin_matches(session, group, courts, round_number)`：以 in-memory `set[tuple[uuid.UUID, uuid.UUID]]` 追蹤本次生成已形成之隊友組合（research.md #3），迴圈呼叫既有 `stage2_pair_players`/`team_matchup_stage2`/`create_match_with_participants` 逐波產生比賽，直到涵蓋全部組合或某一波無新組合則停止 in `apps/api/app/domains/schedule/service.py`(depends on 既有 `stage2_pair_players`/`team_matchup_stage2`)
- [X] T032 [US3] 修改 `generate_next_round()` 的 `individual_mixed` dispatch 分支，改呼叫 T031 之新函式，取代現行「沿用 fair_rotation 雙打單波次 pipeline」的既有呼叫 in `apps/api/app/domains/schedule/service.py`(depends on T031)
- [X] T033 [US3] 更新既有 `apps/api/tests/unit/domains/schedule/test_individual_mixed.py`（原為驗證「dispatch 沿用 fair_rotation pipeline、單波次產生」的既有測試，現行為已由 T031/T032 取代，需改寫為驗證新的多波次 dispatch 正確被呼叫）(depends on T031, T032)

**Checkpoint**：US1～US4 全部可獨立運作。

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**：既有文件/測試的過時假設盤點修正、整體迴歸驗證。

- [X] T034 [P] 更新 `specs/003-schedule-rotation/spec.md`、`research.md` 中「單打 fair_rotation 之 N＝場地數×每場所需人數」「Round 產生後比賽數必然≤場地數」相關敘述，加註說明現僅適用於雙打 fair_rotation，單打/固定搭檔/個人混搭改依 `specs/011-round-robin-scheduling/spec.md`（`data-model.md`/`quickstart.md`/`contracts/schedule-api.md` 三份檢查後未含此類敘述，無需修改）
- [X] T035 執行完整後端測試套件（`pytest -q`），修正 T011/T033 未預期涵蓋、因本 feature 而失真的既有測試斷言（`test_scoring_lifecycle.py`、`test_scoring_flow.py`）；最終乾淨執行 502 項測試全數通過（期間曾見 `test_score_concurrency.py` 偶發失敗一次，已確認在未修改的 main 上同樣會失敗、且與本 feature 無關，屬既有 timing flake，非本次改動引入）
- [X] T036 執行 `ruff check app tests` 與 `mypy app`，修正本 feature 新增程式碼的 lint／型別問題（皆為 0 錯誤）
- [X] T037 [P] 依 `quickstart.md` 情境 1 手動驗證：啟動本機 uvicorn（沿用既有 `db` 容器與 `rally_stats` 開發資料庫）、以真實 HTTP 呼叫建立單打 5 人團＋1 場地並觸發 next-round，經 psql 確認產生恰好 10 筆（C(5,2)）比賽、場地立即領到 1 場 `in_progress`；提前結束該場後，經真實 API 呼叫確認場地立即領到下一場排隊中比賽（驗證 `_advance_other_idle_courts` 在真實伺服器行為下正確運作），驗證完畢後已清除測試資料
- [X] T038 [P] 前端執行既有測試套件（`ng test`）與 lint（`ng lint`），確認 T012/T026/T027 未造成既有元件測試迴歸（70/70 測試通過，lint 0 錯誤）

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：無任務。
- **Foundational (Phase 2)**：無外部相依，但**阻擋**所有 User Story——T003（`round_robin_pairs`）為 US1、US2 共用；T005（跳過忙碌參與者）為 US1～US4 消耗階段共用。
- **User Stories (Phase 3～6)**：皆須等 Phase 2 完成。US1（Phase 3）與 US4（Phase 4）建議優先完成以交付 MVP；US2（Phase 5）、US3（Phase 6）可在 US1 完成後以任一順序進行，彼此無相依。
- **Polish (Phase 7)**：建議等 US1～US4 皆完成後執行，但 T034（既有文件更新）可與任一階段平行進行。

### User Story Dependencies

- **US1（P1）**：Foundational 完成後即可開始，無其他 Story 相依。
- **US4（P1）**：Foundational 完成後即可開始；T014 的驗證範圍會隨 US2/US3 是否已完成而擴大，但 US1 完成後即可獨立驗證單打路徑的 Next Round 行為。
- **US2（P2）**：Foundational 完成後即可開始，不依賴 US1/US4；與 US1 共用 T003（`round_robin_pairs`），但實作（T021～T027）與 US1 的實作（T009～T012）完全是不同檔案/函式，可平行進行。
- **US3（P2）**：Foundational 完成後即可開始，不依賴 US1/US2/US4。

### Parallel Opportunities

- Foundational 階段的 T002、T003（+T004）、T006 可平行進行（T005 需等 T006 之前的理解但可與 T002/T003 平行寫）。
- Foundational 完成後，US1、US2、US3 三條實作線可由不同人平行推進。
- 每個 Story 內標記 [P] 的測試任務（不同檔案）可平行撰寫。

---

## Parallel Example: Foundational Phase

```bash
Task: "Add partner_source column to Group model in apps/api/app/domains/group/models.py"
Task: "Implement round_robin_pairs() in apps/api/app/domains/schedule/algorithms.py"
Task: "Unit test round_robin_pairs() in apps/api/tests/unit/domains/schedule/test_round_robin_pairs.py"
```

## Parallel Example: User Story 2

```bash
Task: "Unit test fixed-partner team round-robin in apps/api/tests/unit/domains/schedule/test_round_robin_fixed_partner.py"
Task: "Unit test even-headcount guard in apps/api/tests/unit/domains/schedule/test_fixed_partner_even_headcount.py"
Task: "Unit test auto partner source computation in apps/api/tests/unit/domains/schedule/test_auto_partner_source.py"
Task: "Unit test partner_source toggle data retention in apps/api/tests/unit/domains/group/test_partner_source_toggle.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 + User Story 4)

1. 完成 Phase 2：Foundational（阻擋一切）
2. 完成 Phase 3：US1（單打全員循環賽）
3. 完成 Phase 4：US4（Next Round 清空重排，驗證涵蓋單打路徑）
4. **STOP and VALIDATE**：獨立驗證單打模式下「產生完整循環賽 → 依序消耗 → Next Round 重排」全流程符合 quickstart 情境 1、6、7
5. 視情況部署/展示

### Incremental Delivery

1. Foundational 完成 → 地基就緒
2. 加入 US1 → 獨立驗證 → 部署/展示（單打循環賽可用）
3. 加入 US4 → 獨立驗證 → 部署/展示（MVP：單打完整循環賽 + Next Round 正確重排）
4. 加入 US2 → 獨立驗證 → 部署/展示（固定搭檔循環賽 + 搭檔來源切換可用）
5. 加入 US3 → 獨立驗證 → 部署/展示（個人混搭循環賽可用，四種排程機制全數完成新行為）
6. 執行 Phase 7 Polish，確保既有文件與測試套件皆與新行為一致

### Parallel Team Strategy

1. 團隊共同完成 Foundational
2. Foundational 完成後：
   - 開發者 A：US1 → US4（同一組演算法脈絡，適合同一人接續）
   - 開發者 B：US2（固定搭檔 + 搭檔來源切換）
   - 開發者 C：US3（個人混搭多波次迴圈）
3. 各 Story 獨立完成與驗證後，於 Phase 7 一併執行整體迴歸測試

---

## Notes

- [P] 任務＝不同檔案、無相依關係。
- [Story] 標籤對應 spec.md 的 US1～US4，供追溯用途。
- 每個 User Story 完成後皆應可獨立測試與展示。
- 依 constitution 原則 II，實作前先寫測試並確認會失敗，再進行實作。
- 建議每完成一項任務或一組邏輯相關任務後即進行 commit。
- 避免：模糊任務描述、同一檔案的平行任務衝突、破壞 Story 獨立性的跨 Story 相依。
