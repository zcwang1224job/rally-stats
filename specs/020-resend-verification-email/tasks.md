# Tasks: 會員首頁重新寄送驗證信

**Input**: Design documents from `/specs/020-resend-verification-email/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md（皆已存在）

**Tests**: 依 `plan.md` Constitution Check（原則 II）之要求，冷卻門檻變更、新增的冷卻狀態查詢函式、前端按鈕的顯示/停用/成功/錯誤呈現，皆屬使用者可觀察的核心行為，MUST 有單元/契約/整合/前端測試覆蓋；本檔案的測試任務為強制項，非選用。

**Organization**：依 spec.md 之 3 個 User Story（US1/US2 皆為 P1，US3 為 P3）分階段組織。三者共用**同一組**後端變更（冷卻門檻、共用查詢函式、回應欄位擴充）——US1（按鈕與成功提示）需要既有端點可用，US2（5 分鐘防範機制）需要新門檻值，US3（按鈕主動反映冷卻狀態）需要新增的時間戳欄位——因此後端與前端型別擴充歸類為 Foundational；US1、US2 依 spec.md 之說明「並列最高優先度，缺一不可」，皆為 MVP 範圍；US3 為體驗加分項，可獨立於 US1/US2 之後再疊加。

## Format: `[ID] [P?] [Story] Description`

- **[P]**: 可平行執行（不同檔案、無相依關係）
- **[Story]**: 對應 spec.md 的 US1–US3
- 每項任務皆附精確檔案路徑

## Path Conventions

沿用 `plan.md` Project Structure：`apps/api/`（FastAPI 後端）、`apps/web/`（Angular 20 前端）。monorepo 骨架已由 001 建立，本 feature 無新增 Setup 任務。

---

## Phase 1: Setup

*本 feature 無新增 Setup 任務——monorepo、CI、linting/型別檢查工具鏈已由 001 完整建立並沿用；不新增資料表，不需要新的 migration（research.md 前言）。*

---

## Phase 2: Foundational（Blocking Prerequisites）

**Purpose**：US1（按鈕與成功提示）、US2（5 分鐘防範機制）、US3（主動反映冷卻狀態）共用的冷卻門檻調整、共用查詢函式、回應欄位擴充與前端型別同步——任一 User Story 皆無法在此階段完成前開始獨立驗證。

### Tests for Foundational（先寫、先失敗）

- [X] T001 [P] Unit test：新函式 `get_resend_verification_available_at()`——(a) 已驗證會員恆回傳 `None`（不觸發查詢）；(b) 該會員完全查無任何驗證信 Token 紀錄時回傳 `None`（防禦性情境）；(c) 該會員名下**恰好只有 1 筆**Token（即註冊當下核發的那一筆，尚未手動觸發過重新寄送）時，無論該筆 `created_at` 距今多近，MUST 回傳 `None`（不受冷卻限制，research.md #5，修復 `/speckit-analyze` I1）；(d) 該會員名下有 **2 筆以上** Token 時，以最近一筆的 `created_at` 為準——距今未滿 5 分鐘回傳「該時間 + 5 分鐘」的未來時間戳，已滿 5 分鐘回傳 `None` in `apps/api/tests/unit/domains/member/test_resend_verification_available_at.py`
- [X] T002 [P] Unit test：更新既有 `test_resend_within_cooldown_is_rejected`／`test_resend_after_cooldown_succeeds`（006-member-friends）——(a) 會員剛註冊（名下只有 1 筆 Token）時，緊接著呼叫 `resend_verification()` MUST 直接成功（取代既有「剛註冊就呼叫必被拒絕」的舊斷言，該舊斷言即 `/speckit-analyze` I1 所指出的錯誤行為）；(b) 承 (a)，成功後該會員名下已有 2 筆 Token，緊接著再次呼叫 MUST 被拒絕（`RESEND_RATE_LIMITED`）；(c) 距上一次成功寄出已滿 5 分鐘（例如 `timedelta(minutes=5, seconds=1)`）後呼叫 MUST 成功；未滿 5 分鐘（例如 `timedelta(seconds=61)`）MUST 仍被拒絕 in `apps/api/tests/unit/domains/member/test_resend_verification_rate_limit.py`
- [X] T003 [P] Contract test：`GET /members/me`／`POST /auth/login`／`POST /auth/resend-verification` 三個既有端點回應新增的欄位——`resend_verification_available_at`（前兩者）與 `available_at`（後者）皆存在且型別正確（ISO 8601 時間戳字串）；未驗證會員剛註冊、剛登入、尚未手動觸發過重新寄送時，`GET /members/me` 之 `resend_verification_available_at` MUST 為 `null`（可立即觸發，即使距離註冊當下系統自動寄出的第一封信不滿 5 分鐘）；額外明確斷言 `POST /auth/resend-verification` 未帶 `Authorization` header 時 MUST 回傳 `401`／`MEMBER_TOKEN_INVALID`（FR-007，既有 `require_member` 行為的回歸驗證，`/speckit-analyze` L1）per `contracts/auth-api.md` in `apps/api/tests/contract/test_verify_email.py`

### Implementation for Foundational

- [X] T004 [P] 調整 `_RESEND_VERIFICATION_COOLDOWN` 由 `timedelta(seconds=60)` 改為 `timedelta(minutes=5)`；抽出共用純函式 `_verification_token_count_and_last_created_at(session, member_id) -> tuple[int, datetime | None]`（單次查詢同時取得該會員 Token 總筆數與最近一筆 `created_at`），並將既有 `resend_verification()` 內查詢最近一筆 Token 建立時間的邏輯改為呼叫此函式；`resend_verification()` 的冷卻判斷改為「筆數 ≤ 1 時 MUST NOT 套用冷卻限制（尚未手動觸發過重新寄送），筆數 ≥ 2 時才以最近一筆 `created_at` 比對 5 分鐘門檻」（data-model.md，research.md #5，修復 `/speckit-analyze` I1）；`_issue_verification_token_and_email()` 改為回傳新建立的 `EmailVerificationToken` in `apps/api/app/domains/member/service.py`
- [X] T005 新增 `get_resend_verification_available_at(session, member) -> datetime | None`（呼叫 T004 的共用函式，套用同一套「筆數 ≤ 1 即無冷卻限制」規則，data-model.md）；`resend_verification()` 改為回傳 `datetime`（本次核發的新 Token 對應的冷卻結束時間，`= 新 Token.created_at + _RESEND_VERIFICATION_COOLDOWN`，即使這是第一次手動觸發也一樣要回傳「下一次」的最早可行時間），供 router 層組進 `ResendVerificationResponse.available_at` in `apps/api/app/domains/member/service.py` (depends on T001, T002, T003, T004)
- [X] T006 [P] `MemberPublicResponse` 新增 `resend_verification_available_at: datetime | None` 欄位；`ResendVerificationResponse` 新增 `available_at: datetime` 欄位（data-model.md）in `apps/api/app/domains/member/schemas.py`
- [X] T007 `_to_public()` 改為 `async def _to_public(session, member)`，內部呼叫 `get_resend_verification_available_at()` 組進 `resend_verification_available_at`；同步更新三個既有呼叫端（`GET /members/me`、`POST /auth/login`、`PATCH /members/me/nickname`）皆改為 `await _to_public(session, member)`；`POST /auth/resend-verification` 改為接住 `service.resend_verification()` 的回傳值組進 `ResendVerificationResponse(sent=True, available_at=...)` in `apps/api/app/domains/member/router.py` (depends on T005, T006)
- [X] T008 [P] 前端型別同步：`MemberPublic` 新增 `resend_verification_available_at: string | null`；`ResendVerificationResponse` 新增 `available_at: string` in `apps/web/src/app/core/api/member-auth.models.ts`

**Checkpoint**：Foundational 完成——冷卻門檻、共用查詢函式、回應欄位擴充皆已在後端就緒，前端型別同步完成，User Story 的獨立驗證與前端渲染工作可以開始。

---

## Phase 3: User Story 1 - 在會員首頁重新寄送驗證信 (Priority: P1) 🎯 MVP（與 US2 並列）

**Goal**：尚未驗證信箱的會員在登入後的會員首頁看到「重新寄送驗證信」按鈕，點擊後成功寄出新的驗證信並看到明確的成功提示；已驗證的會員不會看到這個按鈕；帳號已驗證時嘗試觸發會看到明確的「已完成驗證」提示。

**Independent Test**：依 `quickstart.md` 情境 1——以未驗證帳號登入，確認按鈕存在、點擊後成功且畫面顯示成功提示、實際收到新驗證信；已驗證帳號登入確認按鈕不存在。

### Implementation for User Story 1

- [X] T009 [P] [US1] 新增 i18n 字串：「重新寄送驗證信」按鈕標籤、成功提示訊息（例如 `member.resendVerification.button`／`member.resendVerification.success`）——既有 `errors.ALREADY_VERIFIED`／`errors.RESEND_RATE_LIMITED` 錯誤碼字串直接沿用，不重複定義 in `apps/web/src/assets/i18n/zh-TW.json`
- [X] T010 [US1] `member.component.ts`：新增重新寄送狀態（`resendSubmitting`／`resendSent`／`resendErrorKey`／`resendAvailableAt` signals），新增 `resendVerification()` 方法呼叫 `AuthService.resendVerification()`——成功時更新 `resendSent`／`resendAvailableAt`（採用回應的 `available_at`），失敗時依既有 `ApiError.i18nKey` 慣例設定 `resendErrorKey`（`ALREADY_VERIFIED`／`RESEND_RATE_LIMITED`／其他錯誤皆走同一條路徑，比照既有 `errorKey` 呈現慣例）；`getMe()` 成功時同步以回應的 `resend_verification_available_at` 初始化 `resendAvailableAt` in `apps/web/src/app/features/member/member.component.ts` (depends on T008)
- [X] T011 [US1] `member.component.html`：在既有「請驗證你的信箱」提示旁新增「重新寄送驗證信」按鈕——MUST 只在 `verification_status === 'unverified'` 時顯示（FR-002）；點擊呼叫 `resendVerification()`；成功時顯示成功提示，失敗時顯示 `resendErrorKey` 對應訊息 in `apps/web/src/app/features/member/member.component.html` (depends on T010, T009)
- [X] T012 [P] [US1] `member.component.scss`：新增按鈕與成功/錯誤提示之樣式 in `apps/web/src/app/features/member/member.component.scss`
- [X] T013 [US1] Vitest：未驗證會員的首頁顯示按鈕、已驗證會員不顯示；點擊成功後顯示成功提示；`ALREADY_VERIFIED` 錯誤時顯示明確的「已完成驗證」訊息而非寄出多餘的信或顯示不明確錯誤 in `apps/web/src/app/features/member/member.component.spec.ts` (depends on T011, T012)

**Checkpoint**：US1 完整可運作——會員能在首頁重新寄送驗證信並看到成功提示。

---

## Phase 4: User Story 2 - 短時間內重複要求會被防範機制擋下 (Priority: P1) 🎯 MVP（與 US1 並列）

**Goal**：同一帳號在 5 分鐘內第二次觸發重新寄送 MUST 被拒絕，MUST NOT 寄出第二封信，且畫面 MUST 顯示明確的「請稍後再試」提示；此防範機制以帳號為準，不分分頁/裝置。

**Independent Test**：依 `quickstart.md` 情境 2——同一帳號 5 分鐘內連續觸發兩次，驗證第二次被拒絕、只收到一封信；滿 5 分鐘後第三次成功。

### Implementation for User Story 2

- [X] T014 [US2] Integration test：未驗證會員**剛註冊完**（名下僅有註冊時核發的 1 筆 Token）登入後，透過真實 HTTP 立即呼叫 `POST /auth/resend-verification`——MUST 直接 `200` 成功，MUST NOT 被誤判為冷卻中（quickstart.md 情境 5，修復 `/speckit-analyze` I1）；緊接著（間隔在 5 分鐘內）再次呼叫——MUST `429`／`RESEND_RATE_LIMITED`，且實際只核發了那一筆「第一次手動重新寄送」的新 Token（連同註冊時的那筆共 2 筆，不寄出第三封信）；將最近一筆 Token 的 `created_at` 調整為 5 分鐘前後，驗證滿 5 分鐘後再次呼叫成功（quickstart.md 情境 2）in `apps/api/tests/integration/test_resend_verification_flow.py`（新增）
- [X] T015 [US2] `member.component.ts`：`resendVerification()` 對 `RESEND_RATE_LIMITED` 錯誤的處理——MUST 顯示既有 `errors.RESEND_RATE_LIMITED` 訊息，MUST NOT 誤顯示為成功（`resendSent` MUST NOT 被設為 `true`）in `apps/web/src/app/features/member/member.component.ts` (depends on T010)
- [X] T016 [US2] Vitest：點擊按鈕收到 `429`／`RESEND_RATE_LIMITED` 時，畫面顯示「請稍後再試」訊息，MUST NOT 顯示成功提示 in `apps/web/src/app/features/member/member.component.spec.ts` (depends on T015)

**Checkpoint**：US1+US2 皆可獨立運作——「按鈕看得到、按得動」與「防範機制確實擋下濫用」兩層價值疊加，構成安全可上線的 MVP。

---

## Phase 5: User Story 3 - 按鈕主動反映冷卻中狀態 (Priority: P3)

**Goal**：成功觸發重新寄送後，按鈕 MUST 主動呈現「冷卻中」狀態（圖示＋文字，非純顏色）；滿 5 分鐘後 MUST 自動恢復為可用，不需要使用者重新整理頁面；重新整理頁面後冷卻狀態 MUST 仍正確反映（FR-009）。

**Independent Test**：依 `quickstart.md` 情境 3——成功觸發後立即查看按鈕為冷卻中狀態；重新整理頁面後狀態仍正確；等到冷卻結束後按鈕自動恢復可用。

### Implementation for User Story 3

- [X] T017 [P] [US3] 新增 i18n 字串：「冷卻中」按鈕狀態文字（例如 `member.resendVerification.cooldown`，圖示＋文字，例如「⏳ 請稍後再試」）in `apps/web/src/assets/i18n/zh-TW.json`
- [X] T018 [US3] `member.component.ts`：新增 computed `resendCoolingDown`（依 `resendAvailableAt` 與目前時間比較）；成功寄出或 `getMe()` 回傳非 `null` 的 `resend_verification_available_at`／`available_at` 時，排程一次性 `setTimeout`（到期時刻精確等於該時間戳），到期時將冷卻狀態翻回可用；元件銷毀時 MUST 清除該 timeout（research.md #3/#4，MUST NOT 用「現在時間 + 5 分鐘」自行推算，也 MUST NOT 使用每秒輪詢）in `apps/web/src/app/features/member/member.component.ts` (depends on T010)
- [X] T019 [US3] `member.component.html`：按鈕在 `resendCoolingDown()` 為 `true` 時 MUST 停用，並顯示「冷卻中」文字/圖示狀態（非純顏色，FR-008，憲章原則 VII）in `apps/web/src/app/features/member/member.component.html` (depends on T018, T017)
- [X] T020 [US3] Vitest：成功寄出後按鈕立即呈現冷卻中且停用；模擬時間前進到 `available_at` 之後，驗證按鈕自動恢復可用（不需重新整理，使用假計時器）；元件初始化時若 `getMe()` 回傳的 `resend_verification_available_at` 已在未來，按鈕一開始就呈現冷卻中（涵蓋「重新整理頁面後仍正確」情境，FR-009）in `apps/web/src/app/features/member/member.component.spec.ts` (depends on T019)

**Checkpoint**：US1–US3 全部皆可獨立運作——按鈕可用、防範機制確實擋下、冷卻狀態主動呈現且跨重新整理保持正確。

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**：跨 User Story 的收尾與驗證。

- [ ] T021 [P] 依 `quickstart.md` 全部 5 個情境人工驗證實際運作（含情境 5：剛註冊完 5 分鐘內第一次手動重新寄送 MUST 直接成功）
- [X] T022 [P] Security review：確認 `POST /auth/resend-verification`／`GET /members/me`／`POST /auth/login`／`PATCH /members/me/nickname` 四個端點皆沿用既有 `require_member`／`require_verified_member` 授權，未新增或放寬任何權限語意（FR-007）；確認新增的 `resend_verification_available_at`／`available_at` 欄位僅回傳呼叫者自己帳號的時間戳，不洩漏任何其他會員的資訊
- [X] T023 [P] Accessibility review：確認 T019 的「冷卻中」狀態符合憲章原則 VII（非純顏色，圖示/文字並用，FR-008）
- [X] T024 補齊 `GET /members/me`／`POST /auth/login`／`POST /auth/resend-verification`／`PATCH /members/me/nickname` 之 docstring 完整性——既有 docstring 只引用 006-member-friends 的 FR，補上對 020 新增/調整 FR（FR-004、FR-009）的引用（憲章原則 II 之強制項）in `apps/api/app/domains/member/router.py`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：無任務，略過。
- **Foundational (Phase 2)**：無其他依賴，但 BLOCKS 所有 User Story——US1 的按鈕依賴擴充後的回應形狀（`available_at`）與前端型別；US2 的防範機制依賴新的 5 分鐘門檻；US3 的冷卻狀態呈現依賴新增的時間戳欄位。
- **User Stories (Phase 3–5)**：皆依賴 Foundational 完成；US1、US2 依 spec.md 定案為並列 P1，共同構成可安全上線的 MVP，MUST 一起交付；US3 可在 US1 完成後獨立疊加（T018 依賴 T010 已存在的元件狀態基礎）。
- **Polish (Phase 6)**：依賴所有欲交付的 User Story 完成。

### User Story Dependencies

- **US1（P1，MVP 之一）**：依賴 Foundational（T001–T008）。
- **US2（P1，MVP 之一）**：依賴 Foundational 提供的 5 分鐘門檻；前端錯誤處理（T015）依賴 US1 的 T010（重新寄送方法本身已存在）。
- **US3（P3）**：依賴 Foundational 提供的時間戳欄位，以及 US1 的 T010（元件狀態基礎）；不依賴 US2 的任何實作。

### Within Each Phase

- Tests（Foundational 的 T001–T003；US2 的 T014；US1/US2/US3 的 Vitest T013/T016/T020）MUST 先寫且先失敗，再進行對應 Implementation。
- 常數/共用函式 → service 函式 → schema → router → 前端型別 → 前端元件邏輯 → 前端樣板 → 前端測試。
- 每個 Checkpoint 皆可停下獨立驗證，不需等待後續 Story 完成。

### Parallel Opportunities

- Foundational 的三個測試任務（T001–T003）可平行執行；T004（常數+共用函式）完成後 T005 才能開始；T006（schema）可與 T004/T005 平行進行；T008（前端型別）可與後端任務平行進行。
- US1 的 T009（i18n）、T012（樣式）可與 T010/T011（元件邏輯/樣板）平行進行。
- US3 的 T017（i18n）可與 T018（元件邏輯）平行進行。

---

## Parallel Example: Foundational

```bash
# 平行執行 Foundational 的測試任務：
Task: "Unit test：get_resend_verification_available_at() in apps/api/tests/unit/domains/member/test_resend_verification_available_at.py"
Task: "Unit test：更新既有 5 分鐘冷卻斷言 in apps/api/tests/unit/domains/member/test_resend_verification_rate_limit.py"
Task: "Contract test：三個既有端點新增欄位 in apps/api/tests/contract/test_verify_email.py"
```

## Parallel Example: User Story 1

```bash
# US1 的 i18n 與樣式任務可平行執行：
Task: "新增重新寄送驗證信相關 zh-TW i18n 字串 in apps/web/src/assets/i18n/zh-TW.json"
Task: "member.component.scss：按鈕與提示樣式 in apps/web/src/app/features/member/member.component.scss"
```

---

## Implementation Strategy

### MVP First（User Story 1 + User Story 2，兩者並列缺一不可）

1. 完成 Phase 2：Foundational（冷卻門檻、共用查詢函式、回應欄位擴充就緒）
2. 完成 Phase 3：User Story 1（按鈕與成功提示）
3. 完成 Phase 4：User Story 2（5 分鐘防範機制的前端呈現與端到端驗證）
4. **停下並驗證**：依 `quickstart.md` 情境 1、2 獨立測試 US1+US2
5. 若已可展示，即可部署/demo（會員能重新寄送驗證信，且防範機制確實擋下濫用）

### Incremental Delivery

1. 完成 Foundational → 後端與前端型別就緒
2. 加入 US1 → 獨立測試 → （尚不足以單獨上線，因缺少防範機制的前端呈現）
3. 加入 US2 → 獨立測試 → Demo（MVP：按鈕可用且防範機制確實生效）
4. 加入 US3 → 獨立測試 → Demo（冷卻狀態主動呈現，體驗加分）
5. 每個 Story 皆為既有功能疊加價值，不破壞先前 Story

### Parallel Team Strategy

多位開發者情境：

1. 開發者 A：Foundational 後端部分（T001–T007）
2. 開發者 B：待 T008 完成後接手前端（US1 的 T009–T013、US2 的 T015–T016、US3 的 T017–T020，皆共用同一個元件，建議同一人接續完成以避免同檔案衝突）
3. 開發者 C：待 Foundational 完成後接手 US2 的後端整合測試（T014），與開發者 B 的前端工作平行進行

## Notes

- `[P]` 任務 = 不同檔案、無相依關係。
- `[Story]` 標籤將任務對應回 spec.md 的特定 User Story，供追溯；Foundational 任務無 Story 標籤，因 US1–US3 共用同一組後端變更。
- 冷卻狀態計算 MUST 只在後端 `get_resend_verification_available_at()`／`resend_verification()` 完成一次，前端 MUST NOT 自行用「現在時間 + 5 分鐘」推算，也 MUST NOT 用 `localStorage` 等裝置本地儲存記錄冷卻狀態（憲章原則 X，research.md #3）——實作與 code review 時請特別留意。
- 實作前先確認測試會失敗（TDD，呼應憲章原則 II）。
- 建議每完成一項任務或一組邏輯相關任務即 commit 一次。
- 可在任一 Checkpoint 停下獨立驗證該 Story，不需等待後續 Story 完成；但 US1 單獨上線（沒有 US2）不符合 spec.md 對「兩者並列缺一不可」的定案，正式上線建議至少完成 US1+US2。
- 避免：模糊任務描述、多任務同時修改同一檔案造成衝突、在前端重新計算冷卻結束時間（那會產生與後端不一致的風險，違反 research.md #3 的決策）、在回應或畫面上暴露非呼叫者自己帳號的冷卻資訊。
