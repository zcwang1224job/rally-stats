# Implementation Plan: 訪客即時戰況頁面建立帳號並綁定戰績

**Branch**: `main`（本專案未使用 per-feature git branch，延續既有慣例）| **Date**: 2026-09-15 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/028-guest-stats-binding/spec.md`，
交叉比對 `/specs/015-manual-add-guest`（既有 `RosterEntry`/
`guest_session_token`/個人查看連結機制）、`/specs/026-match-record-friend-invite`
（既有輪替名單/即時戰況畫面對 Guest 的呈現方式）、
`/specs/027-google-line-oauth-login`（既有 `register()`/`login()`/
OAuth `state` JWT 交握/`optional_member`/`require_verified_member`
既有認證核心，本 feature 直接擴充其 `state` 機制而非另立一套）。

## Summary

訪客透過自己的個人查看連結（`guest_session_token`）瀏覽即時戰況（進行中）
或賽後摘要（已完結，含已解散）時，可就地建立帳號、登入既有帳號、或（若
瀏覽器已是登入狀態）一鍵把這筆訪客名冊身份（`RosterEntry`）綁定到一個
會員帳號——綁定後，`RosterEntry.member_id` 從 `NULL` 轉為該會員的
`id`，既有透過 `roster_entry_id` 關聯的所有比賽紀錄（`MatchParticipant`）
自動歸戶，不需要另外搬移或複製任何既有紀錄列（data-model.md）。

核心技術挑戰有兩個：

1. **既有 `resolve_guest_session()`（015）刻意只服務「現役訪客導向即時
   賽況頁」這個用途，要求 RosterEntry 與 Group 皆為 active**——本
   feature 因 FR-004（進行中/已完結兩種狀態皆須支援）與 Edge Cases（
   left/kicked/disbanded 皆須可綁定）的本質，MUST 新增一個獨立、寬鬆的
   「綁定資格查詢」，不與既有導向邏輯混用（research.md #1）。
2. **四種綁定路徑（新帳號、既有登入、已登入一鍵綁定、OAuth）的授權/
   資料寫入邏輯 MUST 收斂成同一段程式碼，只有『怎麼取得 member_id』
   不同**——沿用既有 `optional_member` dependency 分流前三種路徑
   （research.md #2），OAuth 路徑則延伸既有 `state` JWT（027 既有
   `provider`/`intent`/`code_verifier`/`nonce`/`member_id` 之外新增
   `bind_guest_token`），讓綁定完成後精準導回原本瀏覽的即時戰況/摘要
   畫面，而不是登入後的預設頁面（research.md #3，FR-007「不中斷、不需
   重新導覽」）。

其餘技術決策（見 research.md）：綁定的並發安全用單一條件式 UPDATE
（`WHERE member_id IS NULL`）作為最終防線，不用悲觀鎖（research.md #4）；
前端依訪客連結目前是否仍「現役」分兩種外殼呈現，但共用同一顆
`GuestBindingCta` 元件（research.md #5）；不新增 Ably 即時事件，CTA 的
顯示/隱藏只在每次載入時查詢當下狀態（research.md #6）；防機器人 Turnstile
只掛在「建立新帳號」這條路徑，沿用既有 XI 原則與 027 的既有結論
（research.md #7）。

## Technical Context

**Language/Version**：延續既有（後端 Python 3.12 + FastAPI；前端
TypeScript / Angular 20+）。

**Primary Dependencies**：沿用既有堆疊（SQLAlchemy 2.x async ORM、
Pydantic v2；前端 RxJS、ngx-translate）。**不新增任何依賴**——本 feature
純粹是既有 `group`/`member` domain 既有函式（`register()`/`login()`/
`issue_access_token()`/`issue_refresh_token()`/`start_oauth_flow()`/
`complete_oauth_callback()`/`verify_turnstile_token()`）的組合與擴充。

**Storage**：PostgreSQL（既有）。**不新增 migration**——`RosterEntry.
member_id` 欄位已存在（015 既有），本 feature 只新增這個既有欄位
「NULL → 某會員 id」的狀態轉換規則（data-model.md），非 schema 變更。

**Testing**：pytest（後端）：`binding-status` 查詢在 active/left/kicked
× active/disbanded 各組合下的正確回應（含既有 `resolve_guest_session()`
完全不受影響的回歸測試）；`bind` 端點四條路徑（`register`/`login`/
已登入一鍵綁定/OAuth）各自成功分支、`ROSTER_ENTRY_ALREADY_BOUND` 併發
衝突（條件式 UPDATE 的 0-row 分支）、`mode: "register"` 的 Turnstile
失敗與 Email 撞號分支、OAuth 路徑 `bind_guest_token` 存在/不存在兩種
`state` 下 `complete_oauth_callback()` 的行為，以及「綁定失敗但 OAuth
登入本身仍成功」這個關鍵分支（contracts/guest-binding-api.md 明確要求）。
Vitest（前端）：`GuestAccessComponent` 依 `binding-status` 回應三分流
（已綁定/現役未綁定/非現役未綁定）導向不同畫面的邏輯、新
`GuestBindingCta` 共用元件在「未登入」與「FR-012 已登入」兩種狀態下的
文案與行為差異、`oauth-callback.component.ts` 新增的 `bound_group_id`
導向分支（含該參數不存在時維持既有預設行為的回歸測試）。

**Target Platform**：延續既有（Docker on AWS ECS，本地
`docker-compose`）；**不新增環境變數**，沿用既有 `Settings`/OAuth/
Turnstile 設定。

**Project Type**：Web application（monorepo）；本 feature 同時觸及
`apps/api` 與 `apps/web`。

**Performance Goals**：SC-001（訪客從點擊入口到完成綁定、看到戰績歸戶，
2 分鐘內且不離開原畫面）——`binding-status` 查詢與 `bind` 寫入皆為單次
資料庫往返等級的操作，與既有 `login()`/`register()` 同數量級，不需額外
效能設計。

**Constraints**：FR-006（並發安全）——`bind` 的資料庫寫入 MUST 使用
`UPDATE roster_entries SET member_id = :member_id WHERE id = :id AND
member_id IS NULL` 這種條件式寫入並檢查受影響 row 數（research.md #4），
MUST NOT 依賴「先查後寫」兩步驟。OAuth 路徑的綁定失敗 MUST NOT 導致整個
OAuth 登入流程回傳失敗（帳號建立/登入本身仍算成功，contracts/
guest-binding-api.md）。

**Scale/Scope**：與既有訪客連結/註冊/登入同等規模（單次請求，無批次
語意），沿用既有 `20/minute` 速率限制，不需要額外的分頁或速率限制設計。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | 新增的 Pydantic schema（`BindingStatusResponse`、`BindRequest` 三種互斥形狀之一的 discriminated union、`BindResponse`）與對應 TS 介面皆完整定型；`OAuthState`/`OAuthCallbackResult` 新增欄位（`bind_guest_token`/`bound_group_id`）延續既有 `@dataclass(frozen=True)` 型別化寫法，不使用 `dict[str, Any]`；mypy --strict／`tsc --strict`／ESLint 皆為既有 blocking check，不新增例外。 | PASS |
| II. 測試優先 | 綁定動作直接影響戰績歸戶正確性與帳號身份，雖非原則 II 字面列出的「開團/加入/輪替/比分」，但比照同等嚴謹度要求測試覆蓋：四條綁定路徑、並發衝突（FR-006）、disbanded/kicked/left 各種既有狀態組合、OAuth 綁定失敗但登入仍成功的分支，皆 MUST 有對應單元/整合測試（見 tasks.md）。 | PASS |
| III. 即時性與資料一致性 | 本 feature 不觸及比分/賽程即時同步，不適用；research.md #6 已明確記錄「不新增 Ably 即時事件」的理由（CTA 顯示與否只在每次載入時查詢當下狀態，spec 無任何一條 acceptance scenario 要求跨分頁即時同步）。 | 不適用 |
| IV. 權限與安全 | `binding-status`/`bind` 兩端點皆公開，授權依據是持有正確的 `guest_session_token`（與既有訪客連結信任模型一致，spec Assumptions 已明確記錄，不新增額外身份驗證）。**對「會員帳號 MUST 完成 Email 驗證後才能使用任何功能」一條的解釋延伸**（與 027 對同一條的既有延伸並列）：`bind` 端點刻意使用 `optional_member`／`require_member` 等級而非 `require_verified_member`——綁定動作是帳號建立/登入這個動作本身的直接延伸（把剛建立/剛登入的這個帳號指向這筆訪客名冊身份），功能範圍僅止於此，新帳號稍後嘗試使用其他一般會員功能（好友、開團、對戰紀錄頁面本身等）時仍會被既有 `require_verified_member` 正常擋下並要求完成 Email 驗證，本 feature 完全不修改該既有 gate 的判斷邏輯，只是不讓「尚未驗證」這件事擋下「把訪客時期的戰績接到這個帳號」這個更早、更基礎的一次性動作。**對連結類 Token 重新產生原則**：`binding-status`/`bind` 沿用既有唯一的 `guest_session_token` 欄位，不新增平行 token 機制；管理員既有的「重新產生訪客連結」操作，天然使舊 token 對本 feature 的兩個新端點也一併失效（`LINK_NOT_FOUND`），不需要額外實作。 | PASS（延伸解釋，已明確記錄） |
| V. UX 一致性（破壞性操作二次確認） | 綁定關係一旦建立即不可逆（data-model.md §1），但本質是「建立對應關係」而非原則 V 列舉的刪除/解散/踢除類破壞性操作，且使用者本來就是主動點擊入口才會觸發（非容易誤觸的常駐控制項），不強制要求二次確認對話框；實作 SHOULD 在按鈕旁的說明文字清楚表明「綁定後無法變更」，屬於一般 UX 文案品質，不列為本原則的強制關卡。 | PASS（非本原則定義範疇，備註文案建議） |
| VI. 可維護性 | 新端點掛在既有 `group` domain（`app/domains/group/router.py`/`service.py`/`schemas.py`），沿用既有訪客連結相關邏輯所在位置，不新增 `roster` domain；「執行綁定」這段核心邏輯抽成一個共用內部函式，供 `POST /groups/guest-token/{token}/bind` 與 `complete_oauth_callback()` 共用，不重複實作同一段商業邏輯（research.md #2/#3）；前端新增一個獨立、不含頁面骨架的 `GuestBindingCta` 元件，供「現役即時檢視」與「個人戰績摘要」兩種外殼重用（research.md #5）。 | PASS |
| VII. 無障礙與行動裝置優先 | 綁定入口沿用既有 `.btn` 版面慣例，文字標籤（「建立帳號並綁定戰績」／「將本場戰績綁定到我的帳號」）搭配既有帳號建立/登入表單元件，不僅靠圖示或顏色區分狀態。 | PASS |
| VIII. i18n 與時區 | 新增顯示文字（兩種狀態的入口文案、`mode: "register"`/`"login"` 表單文案、「個人戰績摘要」畫面文案）集中於 `zh-TW.json`/`en.json`；新增錯誤碼 `ROSTER_ENTRY_ALREADY_BOUND` 比照既有慣例加入 `errors` 物件；`LINK_NOT_FOUND`/`EMAIL_ALREADY_REGISTERED`/`INVALID_CREDENTIALS`/`CAPTCHA_INVALID` 皆為既有錯誤碼直接沿用，不新增重複語意的碼。本 feature 不涉及任何新的時間欄位。 | PASS |
| IX. 可攜性與可部署性 | 不新增依賴、不新增環境變數、不新增 migration，Docker 建置流程不需改動。 | PASS |
| X. 即時同步的可信來源 | 本 feature 不觸及比分/賽程狀態，不適用；但精神上延伸適用——綁定的唯一寫入路徑是後端條件式 UPDATE（research.md #4），前端僅接收 `bind` 端點的回應決定要不要更新本機登入狀態，不參與任何需要信任判斷的步驟。 | 不適用（精神延伸已落實） |
| XI. 防機器人/防濫用 | 只有 `mode: "register"`（建立新帳號）這條路徑呼叫既有 `verify_turnstile_token()`，其餘三條路徑（登入/已登入一鍵綁定/OAuth）不要求，沿用既有原則與 027 已確立的既有結論（research.md #7）；兩個新端點皆沿用既有 `20/minute` 速率限制。 | PASS |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking（原則 IV/V 的
延伸解釋已在上表明確記錄理由，非未說明的偏離）。

## Project Structure

### Documentation (this feature)

```text
specs/028-guest-stats-binding/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/
│   └── guest-binding-api.md
└── tasks.md             # Phase 2 output (/speckit-tasks command — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
apps/api/
├── app/domains/group/
│   ├── schemas.py        # + BindingStatusResponse、
│   │                         #   + BindRequest（register/login/已登入
│   │                         #   三種形狀的 discriminated union）、
│   │                         #   + BindResponse
│   ├── service.py         # + resolve_guest_binding_target()
│   │                         #   （research.md #1，寬鬆查詢，不影響既有
│   │                         #   resolve_guest_session()）、
│   │                         #   + bind_roster_entry_to_member()
│   │                         #   （research.md #2/#4，條件式 UPDATE 共用
│   │                         #   核心邏輯，供 router 與 member/service.py
│   │                         #   共用）
│   └── router.py          # + GET /groups/guest-token/{token}/binding-status
│                         #   + POST /groups/guest-token/{token}/bind
├── app/domains/member/
│   ├── security.py        # OAuthState/issue_oauth_state() 新增
│   │                         #   bind_guest_token: str | None 欄位
│   │                         #   （research.md #3）
│   ├── service.py         # OAuthCallbackResult 新增
│   │                         #   bound_group_id: str | None 欄位；
│   │                         #   complete_oauth_callback() 於既有成功
│   │                         #   分支後呼叫
│   │                         #   group.service.bind_roster_entry_to_member()
│   └── router.py          # start_oauth 新增可選 query 參數
│                         #   bind_guest_token（僅 intent=login 允許）；
│                         #   _oauth_callback_redirect_url() 新增
│                         #   bound_group_id fragment 參數
                            # （ROSTER_ENTRY_ALREADY_BOUND 於 raise
                            #   ApiError(...) 處直接帶入字串即可——
                            #   app/core/errors.py 的 ApiError 是自由格式
                            #   例外，無中央錯誤碼登記檔需要修改）

apps/web/src/app/
├── features/group-join/guest-access/
│   ├── guest-access.component.ts/html
│   │                         # 初始化改為優先呼叫新
│   │                         #   getGuestBindingStatus()，依回應三分流
│   │                         #   （已綁定/現役未綁定/非現役未綁定）
│   │                         #   導向不同畫面（research.md #5）
│   └── guest-access.component.spec.ts
├── features/group-join/guest-binding-cta/    # 新增：共用綁定入口元件
│   ├── guest-binding-cta.component.ts/html/scss
│   │                         # 依 AuthService.loggedIn 顯示 FR-001 的
│   │                         #   兩種入口文案；封裝三種 mode 的表單/
│   │                         #   OAuth 導向（呼叫既有 continueWithOAuth
│   │                         #   模式，帶上 bindGuestToken 參數）
│   └── guest-binding-cta.component.spec.ts
├── features/group-member-view/group-member-view.component.html
│                         # + 嵌入 <app-guest-binding-cta> （現役情境）
├── features/auth/oauth-callback/oauth-callback.component.ts
│                         # + 讀取 bound_group_id fragment 參數，導向
│                         #   /groups/<id>/member-view，否則維持既有預設
│                         #   行為
└── core/api/
    ├── group-guest.models.ts   # 新增：BindingStatusResponse/
    │                             #   BindRequest/BindResponse 對應介面
    └── group-guest.service.ts  # 新增：getGuestBindingStatus()/
                                #   bindGuestSession() 呼叫新端點
```

**Structure Decision**：後端變更集中於既有 `group` domain（新增查詢/
綁定兩個函式與兩個端點，沿用既有訪客連結邏輯所在位置）與既有 `member`
domain 的 OAuth 既有函式擴充，不新增 domain；前端新增一個獨立的
`guest-binding-cta` 共用元件與其對應的 API service/models，既有
`guest-access.component`/`group-member-view.component`/
`oauth-callback.component` 僅做局部擴充，不新增新的 feature 目錄。

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

無違反項目，本表格從缺。
