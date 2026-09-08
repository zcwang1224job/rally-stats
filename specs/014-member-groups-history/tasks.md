# Tasks: 我的團完整參與紀錄與戰績（All My Groups — Participation History & Stats）

**Input**: Design documents from `/specs/014-member-groups-history/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md（皆已存在）

**Tests**: 依 `plan.md` Constitution Check（原則 II）之要求，`verify_ever_group_member()` 的曾經/從未參與邊界、`get_my_groups()` 的聯集去重與最新狀態判斷、`build_member_match_records(group_id=)` 新參數對既有呼叫端零行為影響的回歸測試、`get_member_group_history()` 的完整組裝與空清單情境，皆 MUST 有單元測試；至少一條整合測試涵蓋「加入 → 打比賽 → 退出 → 仍可查看歷史」全流程——本檔案的測試任務為強制項，非選用。

**Organization**：依 spec.md 之 3 個 User Story（US1–US3，優先序 P1/P2/P3）分階段組織。US1 與 US2 在後端層面彼此獨立（US2 的授權判斷式/端點不依賴 US1 的清單擴充即可獨立測試）；US3 依賴 US1 交付的 `is_creator` 欄位（用於前端判斷是否顯示「忘記管理PIN碼」按鈕），且 US2 交付的新路由是 US1「點擊列表項目」導向的目的地——三者程式碼上有先後累加關係，但各自新增的行為皆可獨立驗證。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行執行（不同檔案、無相依關係）
- **[Story]**: 對應 spec.md 的 US1–US3
- 每項任務皆附精確檔案路徑

## Path Conventions

沿用 `plan.md` Project Structure：`apps/api/`（FastAPI 後端）、`apps/web/`（Angular 20 前端）。monorepo 骨架已由 001 建立，本 feature 無新增 Setup 任務。

---

## Phase 1: Setup

*本 feature 無新增 Setup 任務——monorepo、CI、linting/型別檢查工具鏈已由 001 完整建立並沿用。*

---

## Phase 2: Foundational（Blocking Prerequisites）

*本 feature 無 Foundational 階段任務——不新增資料表、不新增 domain 模組，US1/US2 各自新增的 schema 欄位與函式彼此獨立，沒有任何跨故事共用且會阻塞的先決條件（research.md #6）。*

---

## Phase 3: User Story 1 - 查看自己參加過的所有團 (Priority: P1) 🎯 MVP

**Goal**：「我的團」清單擴充為顯示會員自己建立過 ∪ 曾經加入過（不限現役／已離開／已被踢除）的所有團之聯集，每筆清楚標示身份與目前狀態。

**Independent Test**：會員以會員身份建立一個團、並以會員身份加入另一位團長開的團，開啟「我的團」時，兩個團都必須出現在清單中，各自標示正確的身份與狀態。

### Tests for User Story 1

- [X] T001 [P] [US1] Unit test：`get_my_groups()` 回傳「自建」∪「曾經加入」的聯集，同一團不重複列出，`is_creator`/`member_status` 正確 in `apps/api/tests/unit/domains/member/test_get_my_groups.py`
- [X] T002 [P] [US1] Unit test：`get_my_groups()` 對同一團有多筆歷史 `RosterEntry`（加入→離開→重新加入）時，`member_status` 取最新一筆（`joined_at` DESC）；訪客加入（`member_id IS NULL`）的團不會出現 in `apps/api/tests/unit/domains/member/test_get_my_groups.py`
- [X] T003 [P] [US1] Contract test for `GET /members/me/groups` 擴充後的回應形狀（`is_creator`/`member_status` 欄位、既有 `MEMBER_TOKEN_INVALID`/`EMAIL_NOT_VERIFIED` 錯誤代碼不變）per `contracts/member-groups-history-api.md` in `apps/api/tests/contract/test_member_groups_history_endpoints.py`

### Implementation for User Story 1

- [X] T004 [US1] 擴充 `MyGroupSummary` schema 新增 `is_creator: bool`/`member_status: Literal["active","left","kicked"]` in `apps/api/app/domains/member/schemas.py`
- [X] T005 [US1] 重寫 `get_my_groups()`——(a) 既有「自建」查詢不變、(b) 新增「曾經是 `RosterEntry.member_id`」查詢（不限狀態），以 `group_id` 去重合併，計算 `is_creator`/`member_status`（research.md #4）in `apps/api/app/domains/member/service.py` (depends on T004)
- [X] T006 [US1] 更新 `GET /members/me/groups` router 端點的 docstring 反映擴充後的涵蓋範圍（簽章/回應 model 不變）in `apps/api/app/domains/member/router.py` (depends on T005)
- [X] T007 [P] [US1] 擴充 `MyGroupSummary` TypeScript 介面新增 `is_creator`/`member_status` in `apps/web/src/app/core/api/friend.models.ts`
- [X] T008 [US1] 更新 `my-groups.component.html`/`.ts`——每筆項目新增身份（團長/團員）與狀態（現役/已離開/已被踢除/已解散）徽章，圖示＋文字並用（憲章原則 VII）in `apps/web/src/app/features/member/my-groups/my-groups.component.ts` + `.html` (depends on T007)
- [X] T009 [P] [US1] 新增身份/狀態徽章的 zh-TW i18n 字串 in `apps/web/src/assets/i18n/zh-TW.json`

**Checkpoint**：US1 完整可運作——「我的團」正確顯示自建與加入過的所有團，含已離開/被踢除/已解散的團。

---

## Phase 4: User Story 2 - 點進特定團查看比賽資訊與個人戰績 (Priority: P2)

**Goal**：點擊「我的團」清單中任一團，可看到該團所有已完成比賽的清單，以及自己在該團的個人統計（總場次/勝/敗/勝率）；存取權限僅要求「曾經是此團正式成員」，不要求現役。

**Independent Test**：會員點擊清單中一個已有比賽紀錄的團，驗證可看到該團所有已完成比賽的清單與自己的勝敗統計；改用從未加入過此團的另一位會員呼叫同一端點，驗證被拒絕。

### Tests for User Story 2

- [X] T010 [P] [US2] Unit test：`verify_ever_group_member()` 對曾經有任一狀態 `RosterEntry` 的會員通過，對從未加入過的會員拒絕（`GROUP_MEMBERSHIP_NEVER_HELD`）in `apps/api/tests/unit/domains/group/test_verify_ever_group_member.py`
- [X] T011 [P] [US2] Unit test：`build_member_match_records()` 新增的 `group_id` 篩選參數正確縮小結果範圍；未傳入時（既有呼叫端）行為與擴充前完全一致（回歸測試）in `apps/api/tests/unit/domains/member/test_member_match_records_group_filter.py`
- [X] T012 [P] [US2] Unit test：`get_member_group_history()` 組裝「該團所有已完成比賽」+「自己在該團的統計」正確；尚無比賽紀錄時回傳空清單與 0 統計而非錯誤（FR-008）in `apps/api/tests/unit/domains/member/test_member_group_history.py`
- [X] T013 [P] [US2] Contract test for `GET /members/me/groups/{group_id}/history`（成功、空清單、`GROUP_MEMBERSHIP_NEVER_HELD`、`GROUP_NOT_FOUND`、未登入）per `contracts/member-groups-history-api.md` in `apps/api/tests/contract/test_member_groups_history_endpoints.py`
- [X] T014 [US2] Integration test：會員加入團 → 打完比賽 → 退出 → 仍可成功查看該團歷史比賽與統計；從未加入過的會員查看同一團被拒絕 in `apps/api/tests/integration/test_member_groups_history_flow.py`

### Implementation for User Story 2

- [X] T015 [US2] 新增 `verify_ever_group_member(session, group_id, member_id)`——只要曾經存在任一狀態的 `RosterEntry` 即通過，否則丟出 `GROUP_MEMBERSHIP_NEVER_HELD`（403），刻意獨立於既有 `resolve_active_roster_membership()`（research.md #3）in `apps/api/app/domains/group/service.py`
- [X] T016 [P] [US2] 擴充 `build_member_match_records()` 新增 keyword-only 參數 `group_id: uuid.UUID | None = None`，給定時在 `base_query` 加上 `Match.group_id == group_id` 篩選（research.md #2）in `apps/api/app/domains/member/service.py`
- [X] T017 [P] [US2] 新增 `MemberGroupStatsResponse`（`total_matches`/`total_wins`/`total_losses`/`win_rate`）與 `MemberGroupHistoryResponse`（`group_id`/`group_name`/`stats`/`matches`/`page`/`total_pages`，`matches` 重用既有 `MatchRecordSummary`）schemas in `apps/api/app/domains/member/schemas.py`
- [X] T018 [US2] 實作 `get_member_group_history(session, member_id, group_id, page)`——呼叫 `verify_ever_group_member()` 授權、重用既有 `build_group_match_records()` 取得該團所有比賽清單、重用擴充後的 `build_member_match_records(group_id=...)` 取得個人統計，組裝成 `MemberGroupHistoryResponse` in `apps/api/app/domains/member/service.py` (depends on T015, T016, T017)
- [X] T019 [US2] 實作 `GET /members/me/groups/{group_id}/history` router 端點（`require_member`，比照既有 `/members/me/match-records` 之既有寬鬆基準，research.md #5）in `apps/api/app/domains/member/router.py` (depends on T018)
- [X] T020 [P] [US2] 新增 `MemberGroupStatsResponse`/`MemberGroupHistoryResponse` TypeScript 介面，`matches` 重用既有 `MatchRecordSummary` in `apps/web/src/app/core/api/friend.models.ts`
- [X] T021 [P] [US2] 於 `friends.service.ts` 新增 `getMemberGroupHistory(groupId, page)` API 呼叫 in `apps/web/src/app/features/friends/friends.service.ts` (depends on T020)
- [X] T022 [US2] 建立 `group-history.component.ts`/`.html`/`.scss`——比照既有 `group-member-view/match-records` 分頁之呈現邏輯（`winnerNames()` 等），新增個人統計卡片區塊 in `apps/web/src/app/features/member/my-groups/group-history/` (depends on T021)
- [X] T023 [US2] 新增路由 `member/my-groups/:groupId` → `group-history.component.ts` in `apps/web/src/app/app.routes.ts` (depends on T022)
- [X] T024 [US2] `my-groups.component.html` 每列新增點擊導向 `member/my-groups/:groupId` 的互動 in `apps/web/src/app/features/member/my-groups/my-groups.component.ts` + `.html` (depends on T023, T008)
- [X] T025 [P] [US2] 新增 `GROUP_MEMBERSHIP_NEVER_HELD` 錯誤代碼、統計欄位標籤、「尚無比賽紀錄」提示的 zh-TW i18n 字串 in `apps/web/src/assets/i18n/zh-TW.json`

**Checkpoint**：US1–US2 皆可獨立運作——會員可從「我的團」點進任一團（含已離開/被踢除的團）查看完整比賽清單與個人戰績，未曾參與過的團正確被拒絕存取。

---

## Phase 5: User Story 3 - 團長沿用既有忘記管理PIN碼復原功能 (Priority: P3)

**Goal**：擴充後的「我的團」清單中，團長對自己建立的團仍可一鍵重設管理PIN碼並直接前往管理頁；此操作不得出現在非建立者的團上。

**Independent Test**：團長在擴充後的「我的團」清單中，對自己建立的團點擊「忘記管理PIN碼」，驗證仍可取得新PIN並直接前往管理頁；同一清單中「別人開的團」不得出現這個按鈕。

### Tests for User Story 3

- [X] T026 [US3] Integration test：既有 `POST /groups/{group_id}/forgot-admin-pin` 流程在「我的團」清單擴充後行為完全不變（成功取得新 admin_pin/admin_token）——回歸測試，確認本 feature 未觸及該端點本身的邏輯 in `apps/api/tests/integration/test_member_groups_history_flow.py`

### Implementation for User Story 3

- [X] T027 [US3] `my-groups.component.html` 的「忘記管理PIN碼」按鈕僅在該筆項目 `is_creator === true` 時顯示 in `apps/web/src/app/features/member/my-groups/my-groups.component.html` (depends on T008)

**Checkpoint**：US1–US3 全部皆可獨立運作——完整參與紀錄清單、點進去看比賽與戰績、既有PIN復原流程三者皆到位且互不干擾。

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**：跨 User Story 的收尾與驗證。

- [X] T028 [P] 依 `quickstart.md` 全部 3 個情境人工驗證實際運作
- [X] T029 [P] Security review：確認 `verify_ever_group_member()` 未被誤用於任何現役限定的即時操作端點（`resolve_active_roster_membership()` 保持獨立不變）；確認 `GROUP_MEMBERSHIP_NEVER_HELD` vs `GROUP_NOT_FOUND` 的區分不構成資訊洩漏（團是否存在本來就可透過既有公開的 `GET /groups` 瀏覽列表得知，非新增的洩漏面）
- [X] T030 [P] Accessibility review：身份（團長/團員）與狀態（現役/已離開/已被踢除/已解散）徽章 MUST NOT 僅靠顏色區分（憲章原則 VII）
- [X] T031 補齊 `GET /members/me/groups/{group_id}/history` 之 `response_model`/docstring 完整性（憲章原則 II 之強制項）

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**／**Foundational (Phase 2)**：皆無任務，略過。
- **User Stories (Phase 3–5)**：US1、US2 後端層面彼此獨立，可平行開發；US3 依賴 US1 交付的 `is_creator` 欄位（T004/T005/T008），且 US2 交付的新路由（T023）是 US1 清單項目點擊後的導向目的地（T024 因此同時依賴 US1 與 US2）。
- **Polish (Phase 6)**：依賴所有欲交付的 User Story 完成。

### User Story Dependencies

- **US1（P1，MVP）**：無其他 Story 相依；擴充 `get_my_groups()`（T005）與 `MyGroupSummary`（T004），交付 `is_creator`/`member_status` 兩個新欄位，供 US3 直接使用。
- **US2（P2）**：後端（`verify_ever_group_member()`、`get_member_group_history()`）不依賴 US1 即可獨立測試（可直接以任意已知 `group_id` 呼叫新端點驗證）；前端的「點擊列表項目導向新頁面」（T024）才需要等 US1 的清單畫面（T008）與 US2 自己的新路由（T023）都就緒。
- **US3（P3）**：直接依賴 US1 的 `is_creator` 欄位（T008 已渲染的清單基礎上，T027 只是新增一個條件式按鈕）。

### Within Each User Story

- Tests MUST 先寫且先失敗，再進行 Implementation。
- Service（含跨模組讀取、既有函式擴充）→ Router endpoints → 前端整合。
- Story 完成（含 Checkpoint 驗證）才進入下一優先序 Story。

### Parallel Opportunities

- 同一 User Story 內標記 `[P]` 的 Tests 可平行執行（例如 T001–T003、T010–T013）。
- US1 與 US2 的後端部分（T004–T006 vs T015–T019）可由不同開發者平行進行，因為兩者分別擴充 `get_my_groups()`／新增 `get_member_group_history()`，除了都落在 `member/service.py`/`member/schemas.py` 之外沒有邏輯相依——若同一人單獨開發則依序進行即可，多人協作時建議先各自完成同一檔案內不同函式的變更再合併。
- T016（`build_member_match_records()` 擴充）與 T017（新 schemas）之間、T020（TS 介面）之間互不相依，皆可平行。

---

## Parallel Example: User Story 2

```bash
# 平行執行 US2 的所有測試任務：
Task: "Unit test：verify_ever_group_member() 曾經/從未參與邊界 in apps/api/tests/unit/domains/group/test_verify_ever_group_member.py"
Task: "Unit test：build_member_match_records() group_id 篩選與既有呼叫端回歸 in apps/api/tests/unit/domains/member/test_member_match_records_group_filter.py"
Task: "Unit test：get_member_group_history() 組裝與空清單情境 in apps/api/tests/unit/domains/member/test_member_group_history.py"
Task: "Contract test for GET /members/me/groups/{group_id}/history in apps/api/tests/contract/test_member_groups_history_endpoints.py"
```

---

## Implementation Strategy

### MVP First（僅 User Story 1）

1. 完成 Phase 3：User Story 1
2. **停下並驗證**：獨立測試 US1（`quickstart.md` 情境 1）
3. 若已可展示，即可部署/demo（「我的團」清單完整涵蓋自建與加入過的團，此 MVP 本身已對使用者有實質價值，即使還不能點進去看細節）

### Incremental Delivery

1. 加入 US1 → 獨立測試 → Demo（完整參與紀錄清單）
2. 加入 US2 → 獨立測試 → Demo（點進去看比賽與個人戰績，核心使用者價值閉環到位）
3. 加入 US3 → 獨立測試 → Demo（既有PIN復原流程確認不受影響）
4. 每個 Story 皆為既有功能疊加價值，不破壞先前 Story

### Parallel Team Strategy

多位開發者情境：

1. 開發者 A：US1（清單擴充）
2. 開發者 B：US2 後端（`verify_ever_group_member()`／`get_member_group_history()`）——可與 A 平行開始，兩者除了共用 `member/service.py`/`member/schemas.py` 之外無邏輯相依
3. US2 前端（T022–T024）與 US3（T027）建議在 US1 的清單畫面（T008）就緒後再認領，因為兩者都需要在同一份「我的團」清單畫面上新增互動

## Notes

- `[P]` 任務 = 不同檔案、無相依關係。
- `[Story]` 標籤將任務對應回 spec.md 的特定 User Story，供追溯。
- 對既有 `build_member_match_records()` 的擴充是新增「預設關閉」的參數，既有 `/members/me/match-records` 呼叫端的既有測試 MUST 持續通過（回歸測試見 T011）。
- 實作前先確認測試會失敗（TDD，呼應 constitution 原則 II）。
- 建議每完成一項任務或一組邏輯相關任務即 commit 一次。
- 可在任一 Checkpoint 停下獨立驗證該 Story，不需等待後續 Story 完成。
- 避免：模糊任務描述、多任務同時修改同一檔案造成衝突、破壞既有呼叫端行為的非預設參數變更、放寬 `resolve_active_roster_membership()` 本身的既有門檻。
