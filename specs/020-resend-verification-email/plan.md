# Implementation Plan: 會員首頁重新寄送驗證信

**Branch**: `main`（本專案未使用 per-feature git branch，延續既有慣例）| **Date**: 2026-09-10 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/020-resend-verification-email/spec.md`，
交叉比對 `/specs/006-member-friends`（既有 `POST /auth/resend-verification`、
`resend_verification()`、`_RESEND_VERIFICATION_COOLDOWN`、
`contracts/auth-api.md`——本 feature 沿用並調整其冷卻時間門檻，並補上
006 從未實作的前端觸發入口）。

## Summary

會員登入後看到的會員首頁（`/member`）目前只顯示「請驗證你的信箱」文字，
沒有任何操作可以重新取得驗證信——後端其實已經有完整的
`POST /auth/resend-verification` 機制（006-member-friends FR-011：登入後
才可觸發、同帳號 60 秒內限一次），只是畫面上從未接上觸發入口。本 feature
（1）在會員首頁新增「重新寄送驗證信」按鈕與對應的成功/失敗提示，
（2）把既有冷卻時間門檻由 60 秒改為使用者明確要求的 5 分鐘，
（3）讓 `GET /members/me`／`POST /auth/login`／resend 本身的回應都附帶
「目前是否仍在冷卻中、要等到什麼時候」的伺服器算好的時間戳，讓按鈕在
成功寄出後自動停用、滿 5 分鐘後自動恢復可用，且重新整理頁面後狀態依然
正確（不需要前端自行用「現在時間 + 5 分鐘」用猜的），
（4）修復 `/speckit-analyze` 發現的 I1：冷卻基準改為「上一次**手動**
觸發重新寄送的時間」，不把註冊當下系統自動寄出的第一封信算進去，確保
會員剛註冊完就點擊重新寄送時 MUST 直接成功（research.md #5）。全程不
新增資料表、不新增獨立畫面/路由、不新增第三方套件、不新增 Turnstile
驗證。

## Technical Context

**Language/Version**：延續既有（後端 Python 3.12+；前端 TypeScript /
Angular 20+）。

**Primary Dependencies**：沿用既有 FastAPI/SQLAlchemy 堆疊與 Angular，
**不新增套件**。

**Storage**：PostgreSQL，**不新增資料表、不需要新 migration**——冷卻狀態
沿用既有 `EmailVerificationToken.created_at` 欄位與總筆數即時計算而得，
不需要新增欄位（research.md #5）。

**Testing**：pytest + pytest-asyncio（後端：擴充既有
`test_resend_verification_rate_limit.py`——既有「剛註冊就呼叫必被拒絕」
的舊斷言改為「剛註冊（僅 1 筆 Token）時第一次手動重新寄送 MUST 直接
成功，第二次才受 5 分鐘門檻限制」（research.md #5，修復
`/speckit-analyze` I1）；新增 `get_resend_verification_available_at()` 的
單元測試——已驗證會員恆傳 `None`、僅有 1 筆 Token（含尚無任何紀錄）時
恆傳 `None`、2 筆以上時依最近一筆判斷冷卻中／已過；擴充既有
`test_verify_email.py` 契約測試涵蓋 `GET /members/me`／`POST /auth/login`／
`POST /auth/resend-verification` 新增欄位的型別與情境）。Vitest（前端：
`member.component` 新增的按鈕顯示條件、成功/錯誤訊息呈現、冷卻中停用
狀態、冷卻結束後自動恢復可用）。

**Target Platform**：延續既有（Docker on AWS ECS，本地 `docker-compose`）。

**Project Type**：Web application（monorepo，延續既有 `apps/api` +
`apps/web` 結構）。

**Performance Goals**：SC-001——尚未驗證信箱的會員從登入到看到重新寄送
成功提示，10 秒內完成，人工抽測，非嚴格自動化效能測試（比照既有
018/019 對這類「使用者體感時間」成功標準的處理慣例）。

**Constraints**：FR-004——冷卻門檻 MUST 為 5 分鐘，取代既有 006 的 60 秒
設定，MUST NOT 保留舊的 60 秒門檻。FR-007——MUST 沿用既有登入閘門
（`require_member`），MUST NOT 額外疊加 IP 或裝置層級的限制。FR-009——
重新整理頁面後 MUST 仍正確反映冷卻狀態，MUST NOT 僅靠前端記憶體/
`localStorage` 猜測冷卻結束時間。

**Scale/Scope**：本功能只影響單一會員自己的重新寄送操作與其自身的
冷卻狀態查詢，無額外規模考量。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | 新增 `resend_verification_available_at: datetime \| None`（`MemberPublicResponse`）與 `available_at: datetime`（`ResendVerificationResponse`），前端對應 TypeScript 型別（`string \| null`／`string`）同步更新；`ruff`/`mypy --strict`/前端 strict mode 皆為 blocking check。 | PASS |
| II. 測試優先 | 冷卻門檻變更（60 秒→5 分鐘）、「第一次手動重新寄送不受冷卻限制」的修復（research.md #5）、新增的冷卻狀態查詢函式、前端按鈕的顯示/停用/成功/錯誤呈現，皆屬使用者可觀察的核心行為，MUST 有單元/契約/整合/前端測試覆蓋（列入 tasks.md 強制項，並更新既有 `test_resend_verification_rate_limit.py` 內因門檻變更、以及 `/speckit-analyze` I1 修復而過期的斷言）。 | PASS |
| III. 即時性與資料一致性 | 不涉及即時廣播，純粹是一般 REST 請求/回應；不適用。 | 不適用 |
| IV. 權限與安全 | 沿用既有 `require_member` 登入閘門（FR-007），未新增或放寬任何權限語意；冷卻機制沿用既有以帳號、非以分頁/裝置為準的既定設計（research.md）。 | PASS |
| V. UX 一致性（破壞性操作二次確認） | 「重新寄送驗證信」屬於可重複、無資料遺失風險的操作（比照既有「忘記密碼」不需二次確認的既定慣例），不適用本原則。 | 不適用 |
| VI. 可維護性 | 抽出共用函式 `_verification_token_count_and_last_created_at()`，供既有 `resend_verification()`（寫入路徑的冷卻檢查）與新增 `get_resend_verification_available_at()`（唯讀路徑的冷卻查詢）共用同一份查詢與同一套「筆數 ≤ 1 即無冷卻限制」規則，不重複實作（research.md #2/#5）。 | PASS |
| VII. 無障礙與行動裝置優先 | 按鈕的「冷卻中」狀態 MUST 同時使用文字/圖示與視覺樣式標示，MUST NOT 僅依賴顏色（spec.md FR-008），比照既有 `status-badge` 圖示＋文字並用慣例。 | PASS |
| VIII. i18n 與時區 | 新增文字（按鈕標籤、冷卻中提示、成功訊息）集中於語系檔；`ALREADY_VERIFIED`／`RESEND_RATE_LIMITED` 既有錯誤碼 i18n 字串直接重用，不重複定義。冷卻時間戳為系統自動記錄的絕對時間，MUST 使用 `TIMESTAMPTZ`／UTC 運算（沿用既有 `EmailVerificationToken.created_at` 既定作法）。 | PASS |
| IX. 可攜性與可部署性 | 不新增任何基礎設施、不新增 migration、不新增前後端第三方套件。 | PASS |
| X. 即時同步的可信來源 | 冷卻是否結束、還要等到何時，全部由後端 `get_resend_verification_available_at()` 算好並回傳明確時間戳；前端只根據這個時間戳排程一個到期時刻，MUST NOT 自行用「現在時間 + 5 分鐘」推算冷卻結束時間（research.md #3，spec.md FR-009）。 | PASS |
| XI. 防機器人/防濫用 | 沿用既有 `require_member` 保護，此端點本身不建立任何新資源，不在原則 XI 之 Turnstile 強制範圍內；不新增 IP 層級限制（spec.md Assumptions，與 006 對「登入閘門已足夠、風險特性不同於免登入端點」之既有判斷一致）。 | PASS（明確排除項，非違反） |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/020-resend-verification-email/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/
│   └── auth-api.md
└── tasks.md             # Phase 2 output (/speckit-tasks command — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
apps/api/
├── app/domains/member/
│   ├── schemas.py       # MemberPublicResponse + resend_verification_available_at；
│   │                     # ResendVerificationResponse + available_at
│   ├── service.py       # _RESEND_VERIFICATION_COOLDOWN 60s→5min；抽出
│   │                     # _verification_token_count_and_last_created_at()
│   │                     # （含「筆數 ≤ 1 即無冷卻限制」規則，research.md #5）；
│   │                     # 新增 get_resend_verification_available_at()
│   └── router.py        # _to_public() 改為 async（需要 session）；
│                         # GET /members/me、POST /auth/login、
│                         # PATCH /members/me/nickname、
│                         # POST /auth/resend-verification 皆更新呼叫方式
└── tests/
    ├── unit/domains/member/
    │   ├── test_resend_verification_rate_limit.py   # 擴充（60s→5min 斷言更新，
    │   │                                             # 含 research.md #5 修復後的斷言）
    │   └── test_resend_verification_available_at.py # 新增
    ├── contract/test_verify_email.py                 # 擴充
    └── integration/test_resend_verification_flow.py  # 新增

apps/web/
├── src/app/core/api/member-auth.models.ts   # MemberPublic +
│                                              # resend_verification_available_at；
│                                              # ResendVerificationResponse + available_at
├── src/app/features/auth/auth.service.ts     # 型別隨 member-auth.models.ts 更新（無新方法）
├── src/app/features/member/
│   ├── member.component.ts                   # + 重新寄送狀態機（idle/sending/sent/error）、
│   │                                          # 冷卻中停用/自動恢復排程
│   ├── member.component.html                 # + 按鈕、成功/錯誤提示、冷卻中狀態
│   ├── member.component.scss                 # + 對應樣式
│   └── member.component.spec.ts              # 擴充
└── src/assets/i18n/zh-TW.json                 # + 按鈕/冷卻中/成功訊息文案
```

**Structure Decision**：延續既有 monorepo 結構（`apps/api` + `apps/web`）。
後端邏輯全部落在既有 `member` domain（既有 006 的 auth 端點同層）；前端
邏輯全部落在既有 `member/member.component`——不新增 domain、不新增
Angular feature 模組、不新增路由（spec.md Assumptions）。

## Complexity Tracking

*Gate 無違反項目，本節無需填寫。*
