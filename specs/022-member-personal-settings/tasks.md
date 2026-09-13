# Tasks: 會員個人設定（四大分區）

**Input**: Design documents from `/specs/022-member-personal-settings/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md（皆已存在）

**Tests**: 依 `plan.md` Constitution Check（原則 II）之要求，隱私設定授權矩陣（自己/好友開/好友關/非好友/未登入）、搜尋隱私、登入紀錄寫入與裁切、裝置類別判斷、語言偏好讀寫皆屬使用者可觀察的核心行為，MUST 有單元/契約/前端測試覆蓋；本檔案的測試任務為強制項，非選用。

**Organization**：依 spec.md 之 4 個 User Story（US1 P1／US2 P2／US3 P3／US4 P4）分階段組織。三項全新後端能力（語言偏好、登入紀錄、隱私設定）各自的資料欄位與端點彼此獨立，可分別歸入各自的 User Story 階段；但三者共用同一支 `MemberPublicResponse`（`GET /members/me`）與同一個前端 `settings.component`（四分區容器），這兩處無法乾淨拆成互不相干的變更，因此歸類為 Foundational（比照 021 的既有慣例）。US3（安全性／密碼變更）後端邏輯零變更，僅需在 Foundational 已重組好的分區容器內補上區塊標題，範圍最小。

## Format: `[ID] [P?] [Story] Description`

- **[P]**：可平行執行（不同檔案、無相依關係）
- **[Story]**：對應 spec.md 的 US1–US4
- 每項任務皆附精確檔案路徑

## Path Conventions

沿用 `plan.md` Project Structure：`apps/api/`（FastAPI 後端，domain-driven）、`apps/web/`（Angular 20 前端，feature-based）。monorepo 骨架已由 001 建立，本 feature 無新增 Setup 任務。

---

## Phase 1: Setup

*本 feature 無新增 Setup 任務——monorepo、CI、linting/型別檢查工具鏈已由 001 完整建立並沿用。*

---

## Phase 2: Foundational（Blocking Prerequisites）

**Purpose**：三個新後端屬性（語言偏好、隱私設定兩個布林、登入紀錄）共用的 schema 擴充（`MemberPublicResponse`）與前端四分區容器重組——任一 User Story 皆無法在此階段完成前獨立驗證。

### Tests for Foundational（先寫、先失敗）

- [X] T001 [P] Contract test：`GET /members/me` 回應 MUST 包含 `language_preference`（新註冊會員預設 `"zh-TW"`）、`allow_search`（預設 `true`）、`share_match_records_with_friends`（預設 `true`）三個新欄位 per contracts/member-settings-api.md in `apps/api/tests/contract/test_member_personal_settings.py`（新增）

### Implementation for Foundational

- [X] T002 [P] Migration：`members` 表新增 `language_preference VARCHAR(8) NOT NULL DEFAULT 'zh-TW'`、`allow_search BOOLEAN NOT NULL DEFAULT true`、`share_match_records_with_friends BOOLEAN NOT NULL DEFAULT true`；新建 `member_login_records` 表（`id` UUID PK、`member_id` UUID FK ON DELETE CASCADE + 索引、`device_category VARCHAR(16) NOT NULL`、`created_at TIMESTAMPTZ NOT NULL DEFAULT now()`）data-model.md §1/§2 in `apps/api/alembic/versions/<new>_member_personal_settings.py`（新增）
- [X] T003 [P] `Member` model 新增三個對應欄位；新增 `MemberLoginRecord` model（`__tablename__ = "member_login_records"`）data-model.md §1/§2 in `apps/api/app/domains/member/models.py` (depends on T002)
- [X] T004 `MemberPublicResponse` 新增 `language_preference: str`、`allow_search: bool`、`share_match_records_with_friends: bool` 三個欄位 data-model.md §3 in `apps/api/app/domains/member/schemas.py` (depends on T003)
- [X] T005 既有 `_to_public()` helper 補上三個新欄位的組裝 in `apps/api/app/domains/member/router.py` (depends on T004, T001)
- [X] T006 [P] `MemberPublic` TS interface 新增對應三個欄位（mirrors schemas.py）in `apps/web/src/app/core/api/member-auth.models.ts`
- [X] T007 `settings.component.ts`：狀態改為四個分區（`basic`/`accountDetails`/`security`/`privacy`），既有暱稱表單、密碼表單邏輯原封不動搬入對應分區的 signal/表單群組，不新增任何行為 in `apps/web/src/app/features/member/settings/settings.component.ts` (depends on T006)
- [X] T008 `settings.component.html`：改為四個 `<section>`（基本設定／帳號詳細資訊／安全性／隱私設定），既有暱稱表單搬入「基本設定」、既有密碼表單搬入「安全性」，畫面行為與既有完全一致 in `apps/web/src/app/features/member/settings/settings.component.html` (depends on T007)
- [X] T009 `settings.component.spec.ts`：既有暱稱/密碼測試的 DOM 選擇器更新以符合新的分區結構，確認既有測試全數維持綠燈 in `apps/web/src/app/features/member/settings/settings.component.spec.ts` (depends on T008)

**Checkpoint**：Foundational 完成——`MemberPublicResponse` 已含三個新欄位、前端四分區容器已就緒（既有暱稱/密碼行為零回歸），各 User Story 可以開始獨立疊加新能力。

---

## Phase 3: User Story 1 - 基本設定：暱稱與語言偏好 (Priority: P1) 🎯 MVP

**Goal**：會員在「基本設定」分區查看/修改暱稱（既有行為，已由 Foundational 搬入）；新增語言偏好下拉選單，目前僅「繁體中文」一個選項，選單結構支援未來擴充。

**Independent Test**：依 `quickstart.md` 情境 1 步驟 1–2（暱稱）與情境 2（語言偏好）——開啟語言偏好選單確認唯一選項並選取送出，確認成功徽章與後端持久化。

### Tests for User Story 1

- [X] T010 [P] [US1] Unit test：`set_language_preference()`——合法語言（`"zh-TW"`）成功更新並回傳最新 `Member`；不在 `SUPPORTED_LANGUAGES` 常數清單中的值 MUST 拋出 `LANGUAGE_NOT_SUPPORTED` in `apps/api/tests/unit/domains/member/test_personal_settings.py`（新增）
- [X] T011 [P] [US1] Contract test：`GET /members/me/supported-languages` 回傳 `{"languages": ["zh-TW"]}`；`PATCH /members/me/language` 合法值 `200` 且回應更新後的 `MemberPublicResponse`、不合法值 `400`/`LANGUAGE_NOT_SUPPORTED`、未驗證信箱會員 `403`/`EMAIL_NOT_VERIFIED`、未登入 `401` per contracts/member-settings-api.md in `apps/api/tests/contract/test_member_personal_settings.py`

### Implementation for User Story 1

- [X] T012 [US1] 新增模組常數 `SUPPORTED_LANGUAGES = ("zh-TW",)`；新增 `SetLanguagePreferenceRequest`（`language: str`，validator 檢查屬於常數清單）、`SupportedLanguagesResponse` schemas research.md #4 in `apps/api/app/domains/member/schemas.py` (depends on T010, T011)
- [X] T013 [US1] `set_language_preference(session, member, language)` service 函式 in `apps/api/app/domains/member/service.py` (depends on T012)
- [X] T014 [US1] `GET /members/me/supported-languages`（`require_member`）、`PATCH /members/me/language`（`require_verified_member`）路由 in `apps/api/app/domains/member/router.py` (depends on T013)
- [X] T015 [P] [US1] i18n 字串：`member.basicSection.languageLabel`、`member.basicSection.languageSaved`、`member.basicSection.zhTW`、`LANGUAGE_NOT_SUPPORTED` 錯誤字串 in `apps/web/src/assets/i18n/zh-TW.json`
- [X] T016 [US1] 「基本設定」分區新增語言偏好下拉選單（載入 `GET /members/me/supported-languages`、送出 `PATCH /members/me/language`）＋成功徽章（比照既有 `nicknameSaved` pattern）in `apps/web/src/app/features/member/settings/settings.component.ts`、`settings.component.html` (depends on T014, T015, T009)
- [X] T017 [US1] Vitest：語言偏好選單僅顯示「繁體中文」且預設選取、送出成功顯示徽章、錯誤時顯示對應錯誤訊息 in `apps/web/src/app/features/member/settings/settings.component.spec.ts` (depends on T016)

**Checkpoint**：US1 完整可運作——基本設定分區（暱稱＋語言偏好）獨立可用，MVP。

---

## Phase 4: User Story 2 - 帳號詳細資訊：登入紀錄 (Priority: P2)

**Goal**：會員在「帳號詳細資訊」分區查看近期登入紀錄（時間＋裝置類別，不含 IP/地理位置）；僅主動登入計入，token refresh 不計入；保留最近 50 筆。

**Independent Test**：依 `quickstart.md` 情境 3——重新登入兩次後查看登入紀錄列表；觸發一次 token refresh 後確認筆數不變。

### Tests for User Story 2

- [X] T018 [P] [US2] Unit test：`classify_device(user_agent)`——含 `Mobile`/`Android`/`iPhone`/`iPad` 關鍵字回傳 `"mobile"`；一般桌面瀏覽器 UA 回傳 `"desktop"`；`None`/無法辨識回傳 `"unknown"` research.md #3 in `apps/api/tests/unit/domains/member/test_personal_settings.py`
- [X] T019 [P] [US2] Unit test：`record_login()`——每次呼叫新增一筆 `MemberLoginRecord`（含裝置類別、時間）；同一會員紀錄超過 50 筆時，同一交易內裁切為最新 50 筆 research.md #2；既有 `refresh()` 函式流程 MUST NOT 呼叫 `record_login()`／MUST NOT 新增紀錄；`list_login_records()` 依 `created_at` 新到舊排序並正確分頁 in `apps/api/tests/unit/domains/member/test_personal_settings.py`
- [X] T020 [P] [US2] Contract test：`GET /members/me/login-records` 回應筆數/排序正確、每筆僅含 `created_at`/`device_category`（**MUST NOT** 含 IP/地理位置欄位）、支援 `page` 分頁；未驗證信箱會員 `403`/`EMAIL_NOT_VERIFIED`；登入後立即查詢 MUST 已包含這次登入 per contracts/member-settings-api.md in `apps/api/tests/contract/test_member_personal_settings.py`

### Implementation for User Story 2

- [X] T021 [US2] `classify_device(user_agent: str | None) -> str` 純函式；`LoginRecordSummary`、`LoginRecordsResponse` schemas in `apps/api/app/domains/member/service.py`、`apps/api/app/domains/member/schemas.py` (depends on T018)
- [X] T022 [US2] `record_login(session, member_id, device_category)`（含裁切邏輯）；於既有 `login()` 函式簽發 token 成功後呼叫（`refresh()` 函式不呼叫）；`list_login_records(session, member_id, page)` in `apps/api/app/domains/member/service.py` (depends on T021, T019)
- [X] T023 [US2] `GET /members/me/login-records`（`require_verified_member`，解析 `Request.headers["user-agent"]`）路由；`login()` 呼叫端傳入 `Request` 以取得登入當下的 User-Agent in `apps/api/app/domains/member/router.py` (depends on T022, T020)
- [X] T024 [P] [US2] i18n 字串：`member.accountDetailsSection.title`、`loginRecordsEmpty`、`deviceDesktop`、`deviceMobile`、`deviceUnknown`、分頁按鈕文字 in `apps/web/src/assets/i18n/zh-TW.json`
- [X] T025 [US2] 「帳號詳細資訊」分區顯示登入紀錄列表（時間＋裝置類別圖示/文字）＋分頁控制 in `apps/web/src/app/features/member/settings/settings.component.ts`、`settings.component.html` (depends on T023, T024, T009)
- [X] T026 [US2] Vitest：登入紀錄列表渲染排序正確、分頁切換、空狀態（僅一筆時不顯示空白/困惑畫面）in `apps/web/src/app/features/member/settings/settings.component.spec.ts` (depends on T025)

**Checkpoint**：US1+US2 皆可獨立運作。

---

## Phase 5: User Story 3 - 安全性：變更密碼 (Priority: P3)

**Goal**：既有密碼變更表單（含目前密碼驗證、新密碼確認、其他裝置登出）已由 Foundational 搬入「安全性」分區，行為零變更；本階段僅補上分區級標題與回歸驗證。

**Independent Test**：依 `quickstart.md` 情境 1 步驟 3——在「安全性」分區完成一次密碼變更，確認其他裝置登出、本裝置維持登入。

### Implementation for User Story 3

- [X] T027 [P] [US3] i18n 字串：`member.securitySection.title`（「安全性」，作為既有 `passwordSectionTitle` 表單外層的分區標題）in `apps/web/src/assets/i18n/zh-TW.json`
- [X] T028 [US3] 「安全性」分區外層補上 T027 的分區標題（既有密碼表單本身不變）in `apps/web/src/app/features/member/settings/settings.component.html` (depends on T009, T027)
- [X] T029 [US3] Vitest：確認既有密碼變更成功/目前密碼錯誤/新密碼不一致三個既有情境，在新的「安全性」分區結構下依然全數通過（回歸驗證，非新增行為）in `apps/web/src/app/features/member/settings/settings.component.spec.ts` (depends on T028)

**Checkpoint**：US1+US2+US3 皆可獨立運作。

---

## Phase 6: User Story 4 - 隱私設定：可搜尋性與好友戰績可視性 (Priority: P4)

**Goal**：會員在「隱私設定」分區控制「允許被搜尋」與「好友可查看我的戰績」兩個布林開關；前者接入既有 `search_member()`；後者是全新能力——新增好友檢視戰績的兩支端點，重用既有 `build_member_match_records()`/`get_member_match_record_detail()`，只新增授權檢查層。

**Independent Test**：依 `quickstart.md` 情境 4（允許被搜尋）、情境 5（好友可查看戰績）、情境 6（非好友一律拒絕）。

### Tests for User Story 4

- [X] T030 [P] [US4] Unit test：`search_member()`——目標 `allow_search=false` 且非呼叫者本人時 MUST 拋出 `MEMBER_NOT_FOUND`（與帳號不存在時相同錯誤碼）；呼叫者搜尋自己時，不論自己的 `allow_search` 值為何，既有 `CANNOT_SEARCH_SELF` 行為 MUST 不受影響 spec.md FR-017 in `apps/api/tests/unit/domains/member/test_personal_settings.py`
- [X] T031 [P] [US4] Unit test：`update_privacy_settings()`——只送出一個欄位時只更新該欄位、另一欄位維持原值；兩欄位皆為 `None`/未提供時 MUST 拋出驗證錯誤 in `apps/api/tests/unit/domains/member/test_personal_settings.py`
- [X] T032 [P] [US4] Unit test：`view_member_match_records()`／`view_member_match_record_detail()` 授權矩陣——(a) `member_id` 為呼叫者自己 → `SELF_VIEW_NOT_SUPPORTED`，MUST 在好友關係檢查**之前**判斷、MUST NOT 誤判為 `FRIENDSHIP_REQUIRED`（contracts/member-settings-api.md 授權檢查順序第 1 步）；(b) 目標不存在/未驗證 → `MEMBER_NOT_FOUND`；(c) 非好友 → `FRIENDSHIP_REQUIRED`（不論目標隱私設定為何，spec.md FR-019）；(d) 好友但 `share_match_records_with_friends=false` → `MATCH_RECORDS_PRIVATE`；(e) 好友且設定開啟 → 直接委派既有 `build_member_match_records()`/`get_member_match_record_detail()`，回應形狀與既有 `/members/me/match-records*` 完全相同（含逐場明細與彙總統計兩者，spec.md FR-018）in `apps/api/tests/unit/domains/member/test_personal_settings.py`
- [X] T033 [P] [US4] Contract test：`PATCH /members/me/privacy`（單欄位更新、回應完整目前狀態、未驗證信箱 `403`、兩欄位皆未提供 `400`/`VALIDATION_ERROR`）；`GET /members/search` 隱私關閉後回應與不存在時相同（`404`/`MEMBER_NOT_FOUND`）；`GET /members/{member_id}/match-records`＋`/{match_id}` 完整授權矩陣（`member_id`=自己 → `400`/`SELF_VIEW_NOT_SUPPORTED`／非好友/好友+關/好友+開/未登入）per contracts/member-settings-api.md、quickstart.md 情境 4–6 in `apps/api/tests/contract/test_member_personal_settings.py`

### Implementation for User Story 4

- [X] T034 [US4] `PrivacySettingsRequest`（兩個可選布林欄位，至少一個非 `None`）、`PrivacySettingsResponse` schemas in `apps/api/app/domains/member/schemas.py` (depends on T031)
- [X] T035 [US4] `update_privacy_settings(session, member, allow_search, share_match_records_with_friends)` service 函式 in `apps/api/app/domains/member/service.py` (depends on T034)
- [X] T036 [US4] `search_member()` 補上 `allow_search` 檢查（非本人且已關閉 → `MEMBER_NOT_FOUND`）research.md #6 in `apps/api/app/domains/member/service.py` (depends on T035, T030)
- [X] T037 [US4] `view_member_match_records(session, viewer_id, member_id, ...)`／`view_member_match_record_detail(session, viewer_id, member_id, match_id)`——依序檢查 `viewer_id == member_id`（否則 `SELF_VIEW_NOT_SUPPORTED`，MUST 在好友關係檢查之前執行）、目標存在/已驗證、`get_friendship_status()=="friends"`（否則 `FRIENDSHIP_REQUIRED`）、`share_match_records_with_friends`（否則 `MATCH_RECORDS_PRIVATE`），通過後委派既有 `build_member_match_records()`/`get_member_match_record_detail()` research.md #1/#6，contracts/member-settings-api.md 授權檢查順序 in `apps/api/app/domains/member/service.py` (depends on T036, T032)
- [X] T038 [US4] 路由：`PATCH /members/me/privacy`（`require_verified_member`）、`GET /members/{member_id}/match-records`、`GET /members/{member_id}/match-records/{match_id}`（皆 `require_verified_member`，透傳既有 query 參數）in `apps/api/app/domains/member/router.py` (depends on T037, T033)
- [X] T039 [P] [US4] i18n 字串：`member.privacySection.*`（標題、兩個開關標籤、成功徽章、`FRIENDSHIP_REQUIRED`/`MATCH_RECORDS_PRIVATE` 錯誤字串）in `apps/web/src/assets/i18n/zh-TW.json`
- [X] T040 [US4]（2026-09-13 依使用者要求調整為表單＋按鈕，非切換即存，見 research.md #5）「隱私設定」分區新增 `privacyForm`（兩個 checkbox 為本地草稿，切換本身不呼叫 API）＋「送出」按鈕，點擊後一次送出兩個欄位目前值至 `PATCH /members/me/privacy`＋成功徽章 in `apps/web/src/app/features/member/settings/settings.component.ts`、`settings.component.html` (depends on T038, T039, T009)
- [X] T041 [US4] Vitest：切換 checkbox 本身不呼叫 API／不顯示徽章；點擊「送出」後才呼叫 `PATCH /members/me/privacy` 並顯示成功徽章；開/關狀態文字標籤（非僅顏色區分，憲章原則 VII）in `apps/web/src/app/features/member/settings/settings.component.spec.ts` (depends on T040)

**Checkpoint**：US1–US4 全數獨立可運作，四大分區功能完整。

---

## Phase 7: Polish & Cross-Cutting Concerns

- [X] T042 [P] Vitest：於「基本設定」分區輸入未儲存的暱稱草稿（不送出），切換至「安全性」分區並成功變更密碼，切回「基本設定」確認暱稱欄位仍是先前的未儲存草稿（未被其他分區的儲存動作覆蓋或清空）spec.md FR-026 in `apps/web/src/app/features/member/settings/settings.component.spec.ts` (depends on T009, T028)
- [X] T043 [P] Contract test：`quickstart.md` 情境 7——未驗證信箱會員呼叫本 feature 新增的每一支端點（`PATCH /members/me/language`、`PATCH /members/me/privacy`、`GET /members/me/login-records`、`GET /members/{member_id}/match-records*`）皆 MUST `403`/`EMAIL_NOT_VERIFIED` in `apps/api/tests/contract/test_member_personal_settings.py`
- [X] T044 [P] 後端 `ruff check` + `mypy --strict` 全量通過
- [X] T045 [P] 前端 `tsc --noEmit` + lint 全量通過
- [X] T046 後端 `pytest`、前端 `vitest` 全量迴歸測試皆綠燈（既有 811+ 後端／221+ 前端測試 + 本 feature 新增測試）
- [ ] T047 依 `quickstart.md` 全部 7 個情境手動走一遍驗收（Docker 本地環境，`docker-compose up --build` 後套用新 migration）

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**：無任務，可視為已完成。
- **Foundational (Phase 2)**：Blocks 所有 User Story——`MemberPublicResponse` 擴充與前端四分區容器必須先就緒。
- **User Stories (Phase 3–6)**：皆依賴 Foundational 完成後才能開始；US1–US4 彼此之間 MUST NOT 互相依賴（各自新增獨立的欄位/端點/UI 區塊），可依優先序 P1→P2→P3→P4 循序交付，亦可平行分工。
- **Polish (Phase 7)**：依賴所有欲交付的 User Story 完成。

### User Story Dependencies

- **US1（P1）**：可於 Foundational 完成後立即開始，不依賴其他 User Story。
- **US2（P2）**：可於 Foundational 完成後立即開始，不依賴 US1；`record_login()` 掛在既有 `login()` 函式上，與 US1/US3/US4 互不干擾。
- **US3（P3）**：可於 Foundational 完成後立即開始；後端零變更，僅前端補標題，範圍最小。
- **US4（P4）**：可於 Foundational 完成後立即開始，不依賴 US1–US3；唯一依賴既有（非本 feature 新增）的 `friend` domain（`get_friendship_status()`）。

### Within Each User Story

- 測試先寫、先失敗，再實作（Tests → Models/Schemas → Service → Router → 前端 → 前端測試）。
- 同一檔案內的任務依序執行（不可標記 `[P]`）；不同檔案且無相依關係的任務可平行。

### Parallel Opportunities

- Foundational 的 T002（migration）、T003（models）、T006（前端 TS interface）三者可平行進行（不同檔案）。
- 一旦 Foundational 完成，US1/US2/US3/US4 四個 User Story 的**後端**任務可由不同開發者完全平行進行（各自獨立的 service 函式與路由）；**前端**的 `settings.component.ts`/`.html`/`.spec.ts` 因四個 User Story 共用同一組檔案，實務上仍需依序合併（每個 Story 的前端任務彼此有檔案層級的合併順序，但邏輯上互不依賴，衝突僅是文字合併層級）。
- 每個 User Story 內標記 `[P]` 的測試任務可彼此平行撰寫。

---

## Parallel Example: User Story 1

```bash
# 平行撰寫 US1 的測試：
Task: "Unit test set_language_preference() in apps/api/tests/unit/domains/member/test_personal_settings.py"
Task: "Contract test supported-languages + PATCH language in apps/api/tests/contract/test_member_personal_settings.py"
```

## Parallel Example: Foundational

```bash
# 平行進行 Foundational 的三個獨立檔案任務：
Task: "Migration in apps/api/alembic/versions/<new>_member_personal_settings.py"
Task: "Member + MemberLoginRecord models in apps/api/app/domains/member/models.py"
Task: "MemberPublic TS interface in apps/web/src/app/core/api/member-auth.models.ts"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. 完成 Phase 2：Foundational（schema 擴充＋四分區容器）。
2. 完成 Phase 3：User Story 1（基本設定：暱稱＋語言偏好）。
3. **STOP and VALIDATE**：依 `quickstart.md` 情境 1–2 獨立驗證。
4. 視需要部署/展示。

### Incremental Delivery

1. Foundational 就緒 → 四分區容器可見（暱稱/密碼行為零回歸）。
2. + US1（語言偏好）→ 獨立驗證 → 部署（MVP）。
3. + US2（登入紀錄）→ 獨立驗證 → 部署。
4. + US3（安全性分區標題）→ 獨立驗證 → 部署。
5. + US4（隱私設定＋好友戰績檢視）→ 獨立驗證 → 部署。
6. 每個 Story 疊加價值，不破壞先前已交付的 Story。

### Parallel Team Strategy

多人協作時：

1. 團隊共同完成 Foundational。
2. Foundational 完成後：
   - 開發者 A：US1（語言偏好，後端+前端）
   - 開發者 B：US2（登入紀錄，後端+前端）
   - 開發者 C：US4（隱私設定＋好友戰績檢視，後端+前端，範圍最大）
   - US3（安全性標題）範圍極小，可由任一人順手完成
3. 前端 `settings.component.*` 三個檔案因多人同時編輯，建議約定分區順序（基本設定/帳號詳細資訊/安全性/隱私設定，由上至下）以降低合併衝突。

---

## Notes

- `[P]` 任務 = 不同檔案、無相依關係。
- `[Story]` 標籤將任務對應回 spec.md 的 US1–US4，便於追蹤。
- 每個 User Story 完成後皆應可獨立驗證（依 `quickstart.md` 對應情境）。
- 實作前先確認測試會失敗。
- 每完成一項任務或一組邏輯相關任務後建議 commit。
- 可在任一 Checkpoint 停下獨立驗證該 Story。
- 避免：模糊的任務描述、同檔案衝突、破壞 Story 獨立性的跨 Story 依賴。
