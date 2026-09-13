# Implementation Plan: 會員個人設定（四大分區）

**Branch**: `main`（本專案未使用 per-feature git branch，延續既有慣例）| **Date**: 2026-09-13 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/022-member-personal-settings/spec.md`，
交叉比對 `/specs/006-member-friends`（既有 `members` 表、`set_nickname()`、
`change_password()`、`search_member()`、`friend_requests`/`get_friendship_status()`）、
`/specs/005-member-view` 與其 `016-match-score-timeline` 後續擴充（既有
`build_member_match_records()`、`get_member_match_record_detail()`——皆已是
`member_id` 泛用簽章，非寫死「我自己」）、`/specs/014-member-groups-history`
（既有 `/member/settings` 頁面、`SettingsComponent` 既有的暱稱＋密碼兩個表單）。
本 feature 是在既有能力上：重組既有畫面為四分區、新增語言偏好與隱私設定
兩個全新的會員屬性、新增登入紀錄這個全新實體、新增一組「好友檢視他人戰績」
的新端點（重用既有 service 函式，只是換一個 `member_id` 呼叫）。

## Summary

「個人設定」頁面目前只有暱稱、密碼兩個各自獨立的表單，散落無分區結構。
本 feature 重新組織為「基本設定／帳號詳細資訊／安全性／隱私設定」四個分區：

1. **基本設定**：既有暱稱表單原封不動搬入；新增「語言偏好」下拉選單（僅
   `zh-TW` 一個選項，但存為可擴充的字串欄位+程式碼常數清單，而非資料庫
   ENUM/CHECK 約束，避免未來新增語言需要 migration）。
2. **帳號詳細資訊**：全新「登入紀錄」——每次 Email＋密碼主動登入時寫入一筆
   （時間＋裝置類別，不含 IP/地理位置），token refresh 不計入；保留最近
   50 筆，超過時同一交易內裁切舊資料，不需背景排程。
3. **安全性**：既有密碼表單原封不動搬入，行為不變（含既有的
   `token_version` 其他裝置登出機制）。
4. **隱私設定**：兩個全新布林欄位（`allow_search`、
   `share_match_records_with_friends`，皆預設 `true`）：前者接入既有
   `search_member()`，關閉時回應與「查無此人」一致；後者是全新能力——新增
   `GET /members/{member_id}/match-records`、
   `GET /members/{member_id}/match-records/{match_id}` 兩支端點，直接重用
   既有 `build_member_match_records()`/`get_member_match_record_detail()`
   （這兩個 service 函式本來就已經是泛用 `member_id` 簽章，只是既有端點
   一律寫死呼叫者自己），新增的僅是「呼叫者與目標必須是好友（重用既有
   `get_friendship_status()`）＋目標必須開啟此設定」這一層授權檢查。

全程新增 3 個資料表欄位於既有 `members` 表 + 1 張全新表
（`member_login_records`），新增 1 個小型純函式（User-Agent → 裝置類別
啟發式判斷，不引入新套件），不影響既有的團隊/賽程/計分板領域。

## Technical Context

**Language/Version**：延續既有（後端 Python 3.12+；前端 TypeScript /
Angular 20+）。

**Primary Dependencies**：沿用既有 FastAPI/SQLAlchemy 堆疊與 Angular，
**不新增套件**——裝置類別判斷用簡單 User-Agent 字串比對（正則），不引入
`user-agents`/`ua-parser` 等第三方套件（research.md #3）。

**Storage**：PostgreSQL，新增 1 個 migration：`members` 表新增
`language_preference VARCHAR(8) NOT NULL DEFAULT 'zh-TW'`、
`allow_search BOOLEAN NOT NULL DEFAULT true`、
`share_match_records_with_friends BOOLEAN NOT NULL DEFAULT true`；新建
`member_login_records` 表（`id`、`member_id` FK、`device_category`、
`created_at TIMESTAMPTZ`）。

**Testing**：pytest + pytest-asyncio（後端：語言偏好讀寫、`allow_search`
關閉後 `search_member()` 回應 `MEMBER_NOT_FOUND`、
`share_match_records_with_friends` 關閉後好友查看被拒＋提示、非好友一律
被拒、登入紀錄寫入/裁切/排序、裝置類別判斷單元測試；契約測試涵蓋
`GET/PATCH /members/me/*` 新端點與 `GET /members/{member_id}/match-records*`
的授權矩陣：自己／好友（設定開／關）／非好友／未登入）。Vitest（前端：
`settings.component` 改為四個 `<section>`/tab 分區、語言偏好選單、隱私
設定 checkbox 立即儲存＋成功徽章——比照既有 `scoreboardScoringSaved`
的既有 pattern）。

**Target Platform**：延續既有（Docker on AWS ECS，本地 `docker-compose`）。

**Project Type**：Web application（monorepo，延續既有 `apps/api` +
`apps/web` 結構）。

**Performance Goals**：SC-001/SC-002——比照既有系列 feature 對「使用者
體感時間」成功標準的處理慣例，人工抽測，非嚴格自動化效能測試。

**Constraints**：FR-007——登入紀錄 MUST NOT 含 IP/地理位置，MUST NOT 將
token refresh 計入。FR-017——搜尋隱私關閉時的回應 MUST 與「查無此人」
不可區分（不得洩露帳號存在但已隱藏）。FR-019——好友戰績可視性設定
MUST NOT 放寬至非好友範圍。FR-020——隱私設定變更 MUST 立即生效（無快取
延遲）。

**Scale/Scope**：新增資料量與既有 `members` 表同數量級（每會員固定 3 個
新欄位）；`member_login_records` 每會員上限 50 筆（裁切機制，見
research.md #2），不會無界成長。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | 新增欄位皆有明確型別（`str`/`bool`/`datetime`）；新 Pydantic schema 與 TS interface 一一對應；`ruff`/`mypy --strict`/前端 strict mode 皆為 blocking check。 | PASS |
| II. 測試優先 | 隱私設定授權矩陣（自己/好友開/好友關/非好友/未登入）、搜尋隱私、登入紀錄寫入與裁切、裝置類別判斷皆屬核心可觀察行為，MUST 有單元/契約測試覆蓋（列入 tasks.md 強制項）。 | PASS |
| III. 即時性與資料一致性 | 本 feature 不涉及計分板/賽程即時狀態，不觸及 Ably 廣播；隱私/語言設定變更僅影響「未來的讀取請求」（FR-020 立即生效於查詢時，非快取值），無需快照既有進行中活動。 | PASS |
| IV. 權限與安全 | 新端點 `GET /members/{member_id}/match-records*` MUST 使用 `require_verified_member`（比照既有 `search_member`）＋好友關係與隱私設定雙重檢查，不建立新的一套平行授權機制；密碼變更沿用既有 `change_password()`（`token_version` 機制不變）；不新增任何無需驗證即可開啟的畫面。 | PASS |
| V. UX 一致性（破壞性操作二次確認） | 四分區內所有操作皆為可逆的個人設定變更（暱稱/語言/密碼/隱私開關），無破壞性操作，不適用本原則。 | 不適用 |
| VI. 可維護性 | 好友檢視戰績直接重用既有 `build_member_match_records()`/`get_member_match_record_detail()`（僅新增授權檢查層），不複製一套平行邏輯（research.md #1）；沿用既有 `get_friendship_status()`，不在本 feature 重新實作好友判斷。 | PASS |
| VII. 無障礙與行動裝置優先 | 四分區採用既有 `admin-page`/`settings.component` 既有的表單/按鈕/徽章樣式慣例，隱私開關的開/關狀態 MUST NOT 僅靠顏色區分（搭配文字標籤「已開啟」/「已關閉」）。 | PASS |
| VIII. i18n 與時區 | 新增顯示文字（分區標題、語言偏好選單、隱私設定文案、登入紀錄欄位）集中於 `zh-TW.json`；新錯誤碼（`MEMBER_NOT_FOUND`沿用既有、`FRIENDSHIP_REQUIRED`、`MATCH_RECORDS_PRIVATE`）皆為語意化 code，由前端對應 i18n key。登入時間戳記沿用既有 `TIMESTAMPTZ`+UTC+ISO8601 慣例（原則 VIII 絕對時間戳規則），非場地時間，不適用場地時區特例。 | PASS |
| IX. 可攜性與可部署性 | 不新增第三方套件、不新增外部服務依賴（裝置類別為本地字串判斷，非 GeoIP 等外部 API）。 | PASS |
| X. 即時同步的可信來源 | 隱私/語言設定的生效判斷（FR-020）全部由後端在每次請求當下查詢 `members` 表最新值決定，前端 MUST NOT 快取「是否可搜尋/可查看戰績」的判斷結果並自行決定要不要送出請求——一律送出、由後端當下判斷並回應。 | PASS |
| XI. 防機器人/防濫用 | 本 feature 不新增「建立新資源」類型的公開端點（`GET /members/{member_id}/match-records*` 需登入且僅開放已登入的好友使用，非公開匿名端點），不在原則 XI 範疇內。 | PASS（不適用） |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/022-member-personal-settings/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md         # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/
│   └── member-settings-api.md
└── tasks.md             # Phase 2 output (/speckit-tasks command — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
apps/api/
├── app/domains/member/
│   ├── models.py         # Member: + language_preference, allow_search,
│   │                      # share_match_records_with_friends；新增
│   │                      # MemberLoginRecord model
│   ├── schemas.py         # + SetLanguagePreferenceRequest, PrivacySettingsRequest/
│   │                      # Response, LoginRecordSummary/Response；
│   │                      # MemberPublicResponse + 3 個新欄位
│   ├── service.py         # + set_language_preference(), update_privacy_settings(),
│   │                      # record_login()（login() 內呼叫）,
│   │                      # list_login_records(), classify_device()；
│   │                      # search_member() 補上 allow_search 檢查；
│   │                      # + view_member_match_records()/
│   │                      # view_member_match_record_detail()（好友授權層，
│   │                      # 內部委派既有 build_member_match_records()/
│   │                      # get_member_match_record_detail()）
│   ├── router.py          # + PATCH /members/me/language,
│   │                      # PATCH /members/me/privacy,
│   │                      # GET /members/me/login-records,
│   │                      # GET /members/{member_id}/match-records,
│   │                      # GET /members/{member_id}/match-records/{match_id}
│   └── security.py        # （不變，沿用 require_member/require_verified_member）
├── alembic/versions/
│   └── <new>_member_personal_settings.py  # ALTER members + CREATE member_login_records
└── tests/
    ├── unit/domains/member/
    │   └── test_personal_settings.py      # 語言偏好、隱私設定、登入紀錄、裝置判斷
    └── contract/
        └── test_member_personal_settings.py

apps/web/
└── src/app/features/member/settings/
    ├── settings.component.ts    # 拆為四個分區的狀態/表單；沿用既有
    │                              # passwordStrengthValidator 等既有 validator
    ├── settings.component.html  # 四個 <section>（或 tab）：基本設定/
    │                              # 帳號詳細資訊/安全性/隱私設定
    └── settings.component.spec.ts
```

**Structure Decision**：延續既有 monorepo 結構（`apps/api` domain-driven +
`apps/web` feature-based）。全部改動集中於既有 `member` domain（後端）與
既有 `features/member/settings`（前端），不新增新 domain/feature 目錄；
新端點 `GET /members/{member_id}/match-records*` 雖然跨到「檢視他人資料」
語意，但因為只是既有 `build_member_match_records()` 加一層授權，且回傳的
仍是 member domain 既有的 `MemberMatchRecordsResponse`/
`MatchRecordDetailResponse` 型別，故放在 `member/router.py`，不建立新
domain。

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

無違反項目，本表格從缺。
