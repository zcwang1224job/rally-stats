# Tasks: 好友戰績檢視入口

**Input**: Design documents from `/specs/023-view-friend-match-records/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md（皆已存在）

**Tests**: 依 `plan.md` Constitution Check（原則 II）之要求，好友列表新增的連結、好友戰績列表/分頁/彙總統計、三種拒絕情境（`FRIENDSHIP_REQUIRED`/`MATCH_RECORDS_PRIVATE`/`MEMBER_NOT_FOUND`）與空狀態呈現、單場比賽詳情皆屬使用者可觀察的核心行為，MUST 有 Vitest 測試覆蓋；本檔案的測試任務為強制項，非選用。**後端不新增任何測試**——022 既有測試已完整覆蓋這兩支端點的授權矩陣，本 feature 純粹消費既有端點，不重複驗證已測試正確的後端行為。

**Organization**：依 spec.md 之 2 個 User Story（US1 P1／US2 P2）分階段組織。本 feature 完全不觸及後端（`apps/api` 零變動），故無 Foundational 階段——沒有任何跨 Story 共用、會阻擋 Story 獨立驗證的後端/schema 前置工作（比照 021 在無共用阻擋工作時省略 Foundational 階段的既有慣例）。US2（單場比賽詳情）在檔案上依附於 US1 建立的同一個元件（新增方法與樣板區塊），但邏輯上是疊加、不影響 US1 已完成的能力，符合「Story 完成後不破壞前一個 Story」的原則。

## Format: `[ID] [P?] [Story] Description`

- **[P]**：可平行執行（不同檔案、無相依關係）
- **[Story]**：對應 spec.md 的 US1–US2
- 每項任務皆附精確檔案路徑

## Path Conventions

沿用 `plan.md` Project Structure：僅涉及 `apps/web/`（Angular 20 前端，feature-based）。`apps/api` 本 feature 零變動。

---

## Phase 1: Setup

*本 feature 無新增 Setup 任務——monorepo、CI、linting/型別檢查工具鏈已由 001 完整建立並沿用。*

---

## Phase 2: Foundational

*本 feature 無 Foundational 任務——後端（022）已完整建立所需的端點與授權邏輯，零變動；前端沒有任何跨 US1/US2 共用、會阻擋任一 Story 獨立驗證的前置工作（research.md 前言）。*

---

## Phase 3: User Story 1 - 從好友列表檢視好友戰績 (Priority: P1) 🎯 MVP

**Goal**：好友列表每一列新增「檢視戰績」連結；點擊後導向新頁面，顯示該好友的對戰紀錄列表（新到舊、分頁）與彙總統計（總場次/勝/敗/勝率）；好友已關閉分享、已非好友關係、目標不存在、或尚無對戰紀錄時，皆有明確且彼此可區分的畫面呈現。

**Independent Test**：依 `quickstart.md` 情境 1、2、3、5、6、8——點擊「檢視戰績」看到列表與統計；好友關閉分享後看到明確不公開提示；好友解除好友關係後原本開著的頁面換頁會立即失效；好友無對戰紀錄時看到空狀態（非錯誤畫面）；直接以網址存取套用相同授權檢查；行動裝置瀏覽時入口與頁面皆可正常操作（SC-004）。

### Tests for User Story 1

- [X] T001 [P] [US1] Vitest：`friend-list.component` 每一列好友新增「檢視戰績」連結——`routerLink` 指向 `/friends/{member_id}/match-records`，`nickname` 有值時帶入 query 參數，`nickname` 為 `null` 時 MUST NOT 帶入該 query 參數（research.md #2）in `apps/web/src/app/features/friends/friend-list/friend-list.component.spec.ts`
- [X] T002 [P] [US1] Vitest：新元件 `friend-match-records.component`——初始載入呼叫 `AuthService.getFriendMatchRecords(memberId, 1)`，成功時依新到舊顯示對戰紀錄列表與彙總統計（總場次/勝場/敗場/勝率）；點擊分頁按鈕以對應的 `page` 值重新呼叫 in `apps/web/src/app/features/friends/friend-match-records/friend-match-records.component.spec.ts`（新增）
- [X] T003 [P] [US1] Vitest：同元件——`MEMBER_NOT_FOUND`/`FRIENDSHIP_REQUIRED`/`MATCH_RECORDS_PRIVATE` 三種錯誤碼分別顯示對應既有 i18n key 文字；`total_matches === 0` 時顯示「尚無對戰紀錄」空狀態，且此空狀態的呈現方式 MUST 與上述三種錯誤狀態明確可區分（不得共用同一個模糊訊息）；重新整理/換頁 MUST 重新呼叫端點，不沿用前一次的授權判斷結果（FR-008）in `apps/web/src/app/features/friends/friend-match-records/friend-match-records.component.spec.ts`

### Implementation for User Story 1

- [X] T004 [US1] `AuthService` 新增 `getFriendMatchRecords(memberId: string, page = 1): Observable<MemberMatchRecordsResponse>`，呼叫既有 `GET /members/{memberId}/match-records`（比照既有 `getMatchRecords()` 寫法，不透傳進階篩選參數，research.md #3）in `apps/web/src/app/features/auth/auth.service.ts` (depends on T002, T003)
- [X] T005 [P] [US1] i18n 字串：`friends.viewMatchRecords`（連結文字/aria-label）、`friendMatchRecords.title`（帶暱稱）、`friendMatchRecords.titleGeneric`（無暱稱後備）、`friendMatchRecords.empty`（尚無對戰紀錄空狀態）in `apps/web/src/assets/i18n/zh-TW.json`
- [X] T006 [US1] 新增 `friend-match-records.component.ts`：讀取路由 `memberId` 與 query `nickname`，呼叫 `getFriendMatchRecords()`，管理 `page`/`totalPages`/`errorKey`/`records` 等 signal，三種錯誤碼與空狀態的判斷邏輯（沿用既有 `match-history.component.ts` 的 signal/computed 寫法，但**不含**篩選表單、`round_win_rates`/`opponent_records` 相關的 computed，research.md #1）in `apps/web/src/app/features/friends/friend-match-records/friend-match-records.component.ts`（新增）(depends on T004, T005)
- [X] T007 [US1] 新增 `friend-match-records.component.html`：標題（`nickname` 有值用 `friendMatchRecords.title`，否則用 `titleGeneric`）、彙總統計卡片（總場次/勝/敗/勝率，沿用既有 `member.matchHistory.stats.*`/`resultWinBadge`/`resultLossBadge` 既有 i18n key）、對戰紀錄列表、分頁控制、三種錯誤訊息、空狀態 in `apps/web/src/app/features/friends/friend-match-records/friend-match-records.component.html`（新增）(depends on T006)
- [X] T008 [P] [US1] 新增 `friend-match-records.component.scss`：沿用既有 `match-history.component.scss`/`friend-list.component.scss` 的卡片/清單/分頁樣式慣例 in `apps/web/src/app/features/friends/friend-match-records/friend-match-records.component.scss`（新增）(depends on T006)
- [X] T009 [US1] `app.routes.ts` 新增 `'friends/:memberId/match-records'` lazy route，指向 `FriendMatchRecordsComponent` in `apps/web/src/app/app.routes.ts` (depends on T006)
- [X] T010 [US1] `friend-list.component.html` 每一列好友新增「檢視戰績」連結（`routerLink` + `queryParams`，`nickname` 為 `null` 時不帶該參數）in `apps/web/src/app/features/friends/friend-list/friend-list.component.html` (depends on T005, T009, T001)

**Checkpoint**：US1 完整可運作——好友列表可導向好友戰績頁面，正常顯示與三種拒絕情境、空狀態皆已涵蓋，MVP。

---

## Phase 4: User Story 2 - 查看單場比賽詳情 (Priority: P2)

**Goal**：在好友的戰績列表中點擊任一場對戰紀錄，開啟既有的比賽詳情 dialog，顯示雙方隊伍成員、比分、比賽時間。

**Independent Test**：依 `quickstart.md` 情境 4——點擊戰績列表中任一筆，驗證開啟既有 `MatchRecordDetailDialogComponent` 並正確顯示比賽詳情。

### Tests for User Story 2

- [X] T011 [P] [US2] Vitest：點擊戰績列表中一筆對戰紀錄，呼叫 `AuthService.getFriendMatchRecordDetail(memberId, matchId)`，成功後以 `detail`/`loading`/`loadError` 三個 input 餵給既有 `MatchRecordDetailDialogComponent` 並開啟（比照 `match-history.component.ts` 既有 `openDetail()` 寫法與其既有測試涵蓋方式）in `apps/web/src/app/features/friends/friend-match-records/friend-match-records.component.spec.ts` (depends on T003)

### Implementation for User Story 2

- [X] T012 [US2] `AuthService` 新增 `getFriendMatchRecordDetail(memberId: string, matchId: string): Observable<MatchRecordDetailResponse>`，呼叫既有 `GET /members/{memberId}/match-records/{matchId}` in `apps/web/src/app/features/auth/auth.service.ts` (depends on T011)
- [X] T013 [US2] `friend-match-records.component.ts` 新增 `openDetail(matchId: string)` 方法與既有 `MatchRecordDetailDialogComponent` 的 `viewChild`/`detail`/`detailLoading`/`detailLoadError` signal（完全比照 `match-history.component.ts` 既有寫法，research.md #4）in `apps/web/src/app/features/friends/friend-match-records/friend-match-records.component.ts` (depends on T012)
- [X] T014 [US2] `friend-match-records.component.html` 新增列表項目點擊事件（呼叫 `openDetail()`）與 `<app-match-record-detail-dialog>` 樣板 in `apps/web/src/app/features/friends/friend-match-records/friend-match-records.component.html` (depends on T013)

**Checkpoint**：US1+US2 皆可獨立運作，功能完整。

---

## Phase 5: Polish & Cross-Cutting Concerns

- [X] T015 [P] Vitest：`quickstart.md` 情境 7——確認檢視好友戰績（含開啟單場詳情）的流程中，元件 MUST NOT 呼叫任何通知相關的 API/service 方法（FR-011）in `apps/web/src/app/features/friends/friend-match-records/friend-match-records.component.spec.ts`
- [X] T016 [P] 前端 `tsc --noEmit` + `ng lint` 全量通過
- [X] T017 前端 `vitest` 全量迴歸測試皆綠燈（既有 239+ 測試 + 本 feature 新增測試）
- [ ] T018 依 `quickstart.md` 全部 8 個情境手動走一遍驗收（Docker 本地環境，僅需重建/重啟 `frontend` 容器，`backend`/資料庫皆不受影響）——情境 8（行動裝置瀏覽，SC-004）MUST 實際以行動裝置尺寸驗證，非僅桌面瀏覽器縮放視窗

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：無任務，可視為已完成。
- **Foundational (Phase 2)**：無任務——本 feature 沒有需要先完成的共用/後端前置工作。
- **User Stories (Phase 3–4)**：皆可於本檔案建立後立即開始；US2 在檔案上依附 US1 建立的元件（同一支 `.ts`/`.html`），故實務上 MUST 待 US1 的 T006（元件骨架）完成後才能開始 US2 的實作任務，但 US2 的完成與否不影響 US1 已交付的能力（純疊加）。
- **Polish (Phase 5)**：依賴 US1（必要）與 US2（若欲一併驗收情境 7 的「開啟單場詳情」部分）完成。

### User Story Dependencies

- **US1（P1）**：無其他 Story 依賴，可獨立完成並交付（MVP）。
- **US2（P2）**：依附 US1 建立的 `friend-match-records.component.ts`/`.html`（同一組檔案的疊加修改），MUST 待 US1 的元件骨架（T006）存在後才能開始，但不修改 US1 已完成的任何既有邏輯，僅新增。

### Within Each User Story

- 測試先寫、先失敗，再實作（Tests → Service 方法 → 元件邏輯 → 樣板 → 路由/入口）。
- 同一檔案內的任務依序執行（不可標記 `[P]`）；不同檔案且無相依關係的任務可平行。

### Parallel Opportunities

- US1 的 T001（`friend-list` 測試）、T002、T003（新元件測試）三者可平行撰寫（不同檔案）。
- US1 的 T005（i18n）與 T008（scss）可與同 Story 內其他任務平行進行（各自獨立檔案，皆已標記 `[P]`）。
- Polish 的 T015/T016 可平行進行。

---

## Parallel Example: User Story 1

```bash
# 平行撰寫 US1 的測試：
Task: "friend-list 檢視戰績連結 in apps/web/src/app/features/friends/friend-list/friend-list.component.spec.ts"
Task: "新元件列表/統計/分頁 in apps/web/src/app/features/friends/friend-match-records/friend-match-records.component.spec.ts"
Task: "新元件三種錯誤碼＋空狀態 in apps/web/src/app/features/friends/friend-match-records/friend-match-records.component.spec.ts"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. 完成 Phase 3：User Story 1。
2. **STOP and VALIDATE**：依 `quickstart.md` 情境 1、2、3、5、6、8 獨立驗證。
3. 視需要部署/展示（僅需重建 `frontend` 容器）。

### Incremental Delivery

1. + US1（好友列表入口＋戰績列表/統計/拒絕情境/空狀態）→ 獨立驗證 → 部署（MVP）。
2. + US2（單場比賽詳情）→ 獨立驗證 → 部署。
3. US2 純粹疊加價值，不破壞 US1 已交付的能力。

### Parallel Team Strategy

本 feature 範圍小（僅前端、無 Foundational 階段），單人即可依序完成；若多人協作，US1 的測試撰寫（T001/T002/T003）可由不同人平行進行，US2 需等待 US1 的元件骨架（T006）完成後才能開始。

---

## Notes

- `[P]` 任務 = 不同檔案、無相依關係。
- `[Story]` 標籤將任務對應回 spec.md 的 US1–US2，便於追蹤。
- 每個 User Story 完成後皆應可獨立驗證（依 `quickstart.md` 對應情境）。
- 實作前先確認測試會失敗。
- 每完成一項任務或一組邏輯相關任務後建議 commit。
- 可在任一 Checkpoint 停下獨立驗證該 Story。
- 避免：模糊的任務描述、同檔案衝突、破壞 Story 獨立性的跨 Story 依賴。
