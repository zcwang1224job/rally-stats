# Implementation Plan: 加入團（嘎團）（Join Group）

**Branch**: `N/A (no git repository initialized)` | **Date**: 2026-09-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/004-join-group/spec.md`，交叉比對 `/specs/architecture.md`（`GET /groups`、`GET /join/{join_link_token}`、`POST /groups/{group_id}/join` 之路徑草案已定案）、`/specs/001-create-manage-group/`（`Group` 之密碼/人數/加入連結欄位、`RosterEntry` 之 `member_id`/`guest_session_token` 皆已建立）、`/specs/002-court-management/`（`Court.name`，供列表場地名稱顯示）、`/specs/003-schedule-rotation/`（`handle_member_joined` hook）、`/specs/006-member-friends/`（本次規劃前置完成之會員帳號核心——JWT 認證、`members.nickname` 首次設定狀態，解除本 feature 對已登入會員分支的阻塞依賴）。

## Summary

使用者可從開團列表瀏覽/搜尋/篩選公開場次，或透過管理員分享的加入連結/QR Code 直接進入加入流程；若團設密碼則先驗證（不限次數重試），完成後依登入狀態分流——Guest 輸入暱稱、已登入會員直接使用會員暱稱（尚未設定過暱稱者先導向 006 已建立的設定流程）。真正建立加入記錄時，以單一條件式 `UPDATE ... WHERE current_member_count < max_members` 作為人數上限的唯一原子性事實依據，確保近乎同時的加入請求不會超賣。Guest 加入後核發不透明的 Guest Session Token，供重新整理/斷線重連後辨識同一人並還原狀態；已登入會員若在此團已有 active 記錄，透過相同精神短路，不重新建立記錄或重新驗證。本 feature 擴充既有 `group` 模組（不新建 `roster` 服務模組），新增 6 個公開端點，並延續呼叫 003 之 `handle_member_joined` hook。

## Technical Context

**Language/Version**：延續 001-003、006（後端 Python 3.12+；前端 TypeScript / Angular 20+）。

**Primary Dependencies**：沿用既有 FastAPI/SQLAlchemy/Alembic 堆疊，不新增套件；密碼比對重用 001 之 `decrypt_group_password`；Guest Session Token 產生使用標準庫 `secrets.token_urlsafe`。

**Storage**：PostgreSQL，不新增資料表/欄位——全部欄位已由 001/002 建立（見 data-model.md）。

**Testing**：pytest + pytest-asyncio。核心領域邏輯（人數上限原子性保證之併發測試、密碼驗證無鎖定機制、Guest Session Token 生命週期、FR-020a 短路邏輯、場地名稱/時間區間篩選查詢）MUST 有單元測試；至少一條整合測試涵蓋「瀏覽列表→驗證密碼→輸入暱稱→加入成功→取得 Guest Session Token→還原狀態」全流程。人數上限併發測試 MUST 使用真實資料庫兩條並行連線驗證（比照 003 之 `test_next_round_locking.py` 模式），不可僅用 mock 驗證 SQL 語句本身。

**Target Platform**：延續 001-003、006。

**Project Type**：Web application（monorepo，延續既有結構）。

**Performance Goals**：無密碼情境下，從列表點擊加入到看到輪替名單狀態 30 秒內完成（SC-001，UX 層級，含使用者輸入時間）。

**Constraints**：人數上限之原子性保證 MUST 使用單一條件式 `UPDATE ... WHERE`（research.md #5），MUST NOT 採悲觀鎖（與 003 之 Next Round 場景性質不同，見該決議理由）；忘記密碼驗證 MUST NOT 有錯誤次數限制（FR-016，與會員登入/管理 PIN 碼之防暴力破解機制刻意不同）；加入流程 MUST NOT 整合 Turnstile（FR-001）。

**Scale/Scope**：開團列表規模與好友列表相近（中小型社群規模），分頁機制足以應付；人數上限併發場景之測試規模為 2 條並行請求（真實情境下的最大競爭程度已由 FR-013 之單一 SQL 語句保證，不需模擬更高併發量）。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | Pydantic v2 schema 對應所有請求/回應；`ruff`/`mypy --strict` blocking check。 | PASS |
| II. 測試優先 | 人數上限原子性（真實併發測試）、密碼驗證無鎖定、Guest Token 生命週期、FR-020a 短路邏輯皆屬核心領域邏輯，MUST 有單元測試；至少一條整合測試涵蓋完整加入流程。 | PASS（列入 tasks.md 強制項） |
| III. 即時性與一致性 | 開團列表為瀏覽性查詢畫面，非即時同步需求（spec Edge Cases 已明確排除 Ably 訂閱必要性）；加入成功後的賽程收斂已由 003 之 hook 負責，本 feature 僅呼叫、不重新實作。 | PASS（不適用之處已說明） |
| IV. 權限與安全 | 通關密碼驗證 MUST NOT 設錯誤次數限制（FR-016，與管理 PIN 碼之防暴力破解為刻意不同的兩套規則）；Guest Session Token MUST NOT 具備會員權限、MUST NOT 跨團使用（FR-022）；本 feature 無公開表單提交端點整合 Turnstile 之必要（FR-001 明確排除，防濫用暫依賴既有人數上限/密碼/自動解散機制）。 | PASS |
| V. UX 一致性 | 加入本身無破壞性操作，不適用二次確認要求。 | PASS（不適用） |
| VI. 可維護性 | 擴充既有 `group` 模組（research.md #1）而非強行新建 `roster` 服務模組，理由已記錄；對 003 的唯一觸碰為呼叫既有 `handle_member_joined` hook（不修改其簽章）。 | PASS |
| VII. 無障礙 | 「是否需要密碼」狀態顯示 MUST 同時滿足圖示形狀與文字標籤兩種區分方式，不可僅靠顏色（FR-005，前端落實，於 tasks.md 展開）。 | PASS |
| VIII. i18n 與時區 | 錯誤回應一律語意化代碼（`GROUP_FULL`、`GROUP_PASSWORD_INCORRECT` 等，`architecture.md` 已預先命名）；活動時間區間篩選比對邏輯延續 001 已定案之系統預設時區規則，不使用瀏覽器時區偵測。 | PASS |
| IX. 可攜性 | 沿用既有 Docker/AWS 設計，不需額外基礎設施。 | PASS |
| X. 伺服器為單一事實來源 | 人數上限之原子性保證完全在資料庫層完成（單一 SQL 語句），前端僅接收最終結果；本 feature 無 Ably 事件發布需求。 | PASS |
| XI. 防機器人 | 加入團端點本次 MUST NOT 整合 Turnstile（FR-001，已定案），暫依賴既有人數上限/密碼/自動解散機制自然限縮濫用範圍；日後如需追加另行 `/specify`。 | PASS（明確排除項，非違反） |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/004-join-group/
├── plan.md                    # 本檔案
├── research.md                # Phase 0 產出
├── data-model.md              # Phase 1 產出
├── quickstart.md              # Phase 1 產出
├── contracts/                 # Phase 1 產出
│   ├── group-list-api.md
│   └── join-api.md
└── tasks.md                   # /speckit-tasks 產出（本指令不建立）
```

### Source Code (repository root)

```text
apps/api/
├── app/
│   └── domains/
│       └── group/
│           ├── schemas.py     # 擴充：GroupListItem/GroupListResponse/VerifyPasswordRequest/
│           │                    #   JoinLinkPreviewResponse/JoinGroupRequest/JoinGroupResponse/
│           │                    #   GuestSessionResponse
│           ├── service.py     # 擴充：list_groups()、verify_password()、resolve_join_link()、
│           │                    #   join_group()（FR-020a 短路+原子性人數保證+密碼驗證）、
│           │                    #   resolve_guest_session()
│           └── router.py      # 擴充：GET /groups、GET /join/{token}、
│                                #   POST /{group_id}/verify-password、POST /{group_id}/join、
│                                #   GET /groups/by-guest-token/{token}；optional_member dependency
└── tests/
    ├── unit/domains/group/    # 擴充：本 feature 之新測試檔案
    ├── contract/
    └── integration/

apps/web/
└── src/app/features/
    └── group-join/
        ├── group-list/            # 開團列表（搜尋/篩選/分頁）
        ├── join-flow/             # 密碼驗證 → 暱稱輸入 → 加入完成，單一多步驟元件
        └── group-join.service.ts  # 擴充：list/verifyPassword/resolveJoinLink/join/resolveGuestSession
```

**Structure Decision**：擴充既有 `app/domains/group` 模組（research.md #1）；前端沿用既有 `features/group-join` 目錄（001 已建立骨架，見其 placeholder component），本 feature 補上實際實作，新增 `group-list`/`join-flow` 子目錄。

## Complexity Tracking

*本 feature 無 Constitution Check 違反項目，此表格從略。*

## Post-Design Constitution Check

*Re-evaluated after Phase 1（`data-model.md`、`contracts/`、`quickstart.md`）產出。*

設計階段的關鍵決策——(1) 人數上限採單一條件式 `UPDATE ... WHERE` 而非悲觀鎖（research.md #5，與 003 之場景性質差異已記錄）、(2) 密碼驗證於 `join` 送出當下重新驗證、不信任前一次 `verify-password` 呼叫結果（research.md #3）、(3) Guest Session Token 為不透明隨機字串而非 JWT（research.md #4，因其角色僅為查找鍵而非自我描述憑證）——皆為在不違反任何 FR 的前提下確保正確性與效能的實作細節，未引入新的 Constitution 違反項目。對既有模組的唯一擴充（`group` 模組新增函式、呼叫 003 既有 hook）維持「新增，不變更既有行為」原則，符合原則 VI 之模組邊界要求。**Gate 結果維持 PASS，無需新增 Complexity Tracking 項目。**

## Assumptions

- 「已加入的團」個人化列表（FR-006）與「忘記管理 PIN 碼」列表（006 之 `GET /members/me/groups`）為兩個獨立概念（前者是「我作為一般成員加入過的團」，後者是「我作為管理員建立過的團」），本 feature 僅實作前者，透過 `GET /groups` 的 `joined_by_me` 欄位呈現，不與 006 已完成的端點合併或重用。
- Guest/會員完成加入後之「還原現有狀態」畫面（賽程/戰績等詳細檢視）屬 005 spec（團內成員視圖）範圍；本 feature 僅提供 `GET /groups/by-guest-token/{token}` 與 `already_joined`/`roster_entry_id` 欄位供前端識別「應導向現有狀態」，不實作該狀態畫面本身的詳細內容（暫以最小化的加入成功確認畫面呈現，待 005 完工後前端可接上其唯讀賽程頁）。
- 前端 `features/group-join/` 目錄下既有的 placeholder 元件（001 建立）將於本 feature 實作階段整個取代為真實功能，非另建新目錄。
