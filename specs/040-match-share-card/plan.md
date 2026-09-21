# Implementation Plan: 單場比賽分享圖卡（Match Share Card）

**Branch**: `feature/match-share-card` | **Date**: 2026-09-21 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/040-match-share-card/spec.md`，交叉比對以下檔案：`/apps/api/app/domains/group/service.py`（`build_match_record_detail()`，三個比賽詳情端點唯一的共用組裝入口）、`/apps/api/app/domains/schedule/models.py`（`Match.target_score` 分制快照）、`/apps/web/src/app/core/match-record-detail/`（四個入口共用的比賽詳情 dialog）、四個呼叫端（`features/member/match-history`、`features/friends/friend-match-records`、`features/group-member-view/match-records`、`features/member/my-groups/group-history`）、`/apps/web/src/app/core/line-share.ts` 與 `/apps/web/src/app/core/clipboard.ts`（既有分享／複製工具）。

## Summary

在比賽詳情 dialog 加上「分享圖卡」按鈕。按下後開啟預覽，在瀏覽器以 **Canvas 2D** 產生一張 1080×1350 的 PNG，可以下載、以系統分享選單分享圖片檔（Web Share Level 2），或複製到剪貼簿。**不新增第三方套件、不新增端點、不動資料表。**

後端唯一的變動：`MatchRecordDetailResponse` 新增唯讀欄位 `target_score`（取自 `Match.target_score` 快照），供亮點門檻依分制換算（clarify Q3／FR-012a）。因為三個詳情端點都經過 `build_match_record_detail()`，只要改這一處就會全部帶上。

前端分三層，讓規格中所有「對不對」的判斷都落在可窮舉測試的純函式上（research Decision 2）：

1. `buildShareCardModel()`：詳情資料加上呼叫端提供的 `ShareCardContext`（團名與視角），轉換成圖卡模型，負責視角、隊伍排序、勝負徽章、時長、降級與走勢點。
2. `pickHighlights()`：依 FR-012 的七個候選、分制換算門檻與固定優先順序，挑出最多 3 個亮點。
3. `renderShareCard()`：薄繪製層，負責文字量測、截斷、排版與繪圖。

走勢點的計算從詳情 dialog 抽成共用純函式（Decision 4），以保證圖卡和詳情趨勢圖的形狀一致。視角與團名由四個呼叫端透過新的 `shareContext` 輸入傳給 dialog（Decision 5），沿用 016「dialog 純呈現、呼叫端餵資料」的設計。

## Technical Context

**Language/Version**：沿用既有技術，後端 Python 3.12+（FastAPI + SQLAlchemy 2.0 async + Pydantic v2），前端 Angular 20 + TypeScript strict mode。

**Primary Dependencies**：沿用既有技術堆疊，**不新增任何第三方套件**。前端使用瀏覽器原生的 Canvas 2D、`HTMLCanvasElement.toBlob`、Web Share API Level 2（`navigator.canShare`／`share({ files })`）、Async Clipboard API（`ClipboardItem`）、`document.fonts.ready`，另外使用既有的 `@ngx-translate/core` 與 Angular `formatDate`。

**Storage**：PostgreSQL，**不需要任何 Alembic migration**。只多讀取 `matches.target_score`，這是 `build_match_record_detail()` 手上那筆 `Match` 已經載入的欄位，**不增加任何查詢**。

**Testing**：
- 後端（pytest）：
  - 擴充 `tests/contract/test_group_match_record_detail.py`、`tests/contract/test_member_match_record_detail.py`：回應包含 `target_score`，值等於比賽的快照；另有一例是比賽建立後才修改團設定，回應仍為原本的快照值。
  - 擴充 `tests/unit/domains/member/test_personal_settings.py`：好友詳情端點同樣帶有 `target_score`。
- 前端（Vitest，`@angular/build:unit-test`）：
  - `share-card-highlights.spec.ts`（新增）：七個候選各自的門檻邊界（剛好達標／差 1），11／15／21 分制的換算，`max(3, …)` 下限，優先順序與只取 3 個，我方落敗時略過 #1／#3／#7，簡易模式略過 #5，涵蓋率 79% 或 80%，不完整紀錄回傳 `[]`，確定性。
  - `share-card-model.spec.ts`（新增）：中立視角勝方在前、我方視角我方在前，排序後比分與暱稱的對應正確（FR-019），徽章文字的 key，時長與平均每分耗時的有無，partial／none 的降級，檔名，alt 文字。
  - `score-trend.spec.ts`（新增）：抽出的走勢點計算。詳情 dialog 既有 spec 維持全綠，作為重構行為不變的保證。
  - `share-card-renderer.spec.ts`（新增）：以 `RecordingContext` 驗證該畫的文字都有畫、被省略的元素沒畫、20 字雙打暱稱經過截斷且不超過邊界、兩種色盤。
  - `share-card-dialog.component.spec.ts`（新增）：以替身 `ShareCardActions` 驗證三顆按鈕依能力顯示或隱藏、`AbortError` 不顯示錯誤、其他錯誤顯示提示、切換配色會重新產生圖片、關閉時 revoke object URL、兩份語系檔的 key 一致。
  - 擴充 `match-record-detail-dialog.component.spec.ts`：`shareContext` 為 null 時不顯示按鈕；載入中或錯誤時不可點。
  - 擴充四個呼叫端的 spec：傳入正確的 `shareContext`（其中 match-history 的 `myTeam` 從 `won`＋`winner_team` 推導）。

**Target Platform**：沿用既有部署方式（Docker on AWS ECS）。圖卡功能以行動裝置瀏覽器為主要使用情境：iOS Safari 15+、Android Chrome 可用系統分享；桌機 Chrome、Edge、Safari 提供下載與複製圖片。

**Project Type**：Web application（monorepo，改動 `apps/api` 一處 schema 加組裝，其餘都在 `apps/web`）。

**Performance Goals**：從按下「分享圖卡」到預覽出現，在一般手機上不超過 2 秒（SC-001）。單張 1080×1350 的 Canvas 繪製加上 PNG 編碼，通常只要數十到數百毫秒；走勢點最多約 60 個，繪製量可以忽略。

**Constraints**：輸出固定為 1080×1350（FR-004）；圖卡上不得有 QR 碼或連結（FR-006）；分享按鈕必須在使用者手勢內同步發起，因此 Blob 要預先產生（Decision 9）；複製圖片需要 secure context，在 http 的 LAN 測試環境下會隱藏（Decision 9）；新增文字全部進語系檔（FR-027）；授權邊界不變（FR-026）。

**Scale/Scope**：後端改動 1 個 schema 欄位加 1 行組裝，擴充 3 個測試檔。前端新增 1 個 `core/match-share-card/` 模組（model、highlights、palette、renderer、actions service、preview dialog 元件），抽出 1 個共用純函式，擴充詳情 dialog 與 4 個呼叫端，以及 2 份語系檔。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | 新增的 `target_score: int` 為明確型別的 Pydantic 欄位。前端的 `ShareCardContext`、`ShareCardModel`、`Highlight` 以可辨識聯集（discriminated union）定義，沒有 `any`。Canvas context 的替身以介面子集定義，不使用型別斷言。`ruff`、`mypy`、`tsc --noEmit`、`ng lint` 沿用既有的 blocking check。 | PASS |
| II. 測試優先 | 亮點規則與視角與排序是本功能的核心規則，純函式 spec **先於實作撰寫**，並窮舉 research Decision 7 表格中的每一個門檻邊界。回應新欄位要有契約測試。 | PASS（列為 tasks.md 強制項） |
| III. 即時性與資料一致性 | 沒有寫入路徑。門檻使用 `Match.target_score` 快照，而非團目前的設定，符合「設定變更不回溯」的要求（FR-012a）。只處理 completed 比賽，abandoned 比賽依既有查詢本就排除。 | PASS |
| IV. 權限與安全 | 不新增端點，三個既有詳情端點的授權判斷完全不變（FR-026）。新欄位 `target_score` 是非敏感的比賽設定。暱稱以 Canvas `fillText` 繪製（純文字，不經 HTML 解析，沒有 XSS 面）；預覽的 alt 文字經 Angular 屬性繫結，自動逸出。圖卡在使用者裝置上產生，系統不保存也不上傳。 | PASS |
| V. 破壞性操作二次確認 | 沒有破壞性操作。 | 不適用 |
| VI. 可維護性 | 圖卡自成 `core/match-share-card/` 模組，只依賴 `MatchRecordDetailResponse` 型別與抽出的 `score-trend.ts`。詳情 dialog 只多一個輸入與一顆按鈕。規則（model、highlights）、繪製（renderer）、平台能力（actions）三者分離。 | PASS |
| VII. 無障礙與行動裝置優先 | 勝負以文字徽章加字重呈現，不只靠顏色（FR-029）。色盤的文字與背景對比度 ≥ 4.5:1。預覽 `<img>` 附有 alt 文字（FR-028）。按鈕為原生 `<button>`，配色切換使用 `aria-pressed`。預覽 dialog 為原生 `<dialog>`，內建焦點管理。 | PASS |
| VIII. i18n 與時區 | 新增文字全部放進 `matchShareCard.*` 命名空間，同時提供 `zh-TW`／`en`，canvas 文字經 `TranslateService.instant()` 取得。日期依 `started_at`（系統記錄的絕對時間戳，不是場地時段）以裝置時區格式化，與既有 `match-card` 一致；時長由 UTC 時間相減得出（Decision 8）。後端沒有新增任何顯示文字。 | PASS |
| IX. 可攜性與可部署性 | 沒有 migration、新套件、新環境變數或新字型檔。 | PASS |
| X. 伺服器為可信來源 | 不涉及寫入或廣播。圖卡上的統計數字全部直接讀取後端算好的欄位（FR-010）；前端只做「挑選與措辭」，不重新推導統計。 | PASS |
| XI. 防濫用 | 沒有新增「建立新資源」的端點。 | 不適用 |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

**Post-design re-check（Phase 1 完成後）**：data-model.md 與 contracts/ 確認後端只多一個非敏感、有既有快照來源的回應欄位，沒有新資料表、新端點或新授權分支；前端新模組沒有反向依賴任何呼叫端。Gate 結果維持 PASS。

## Project Structure

### Documentation (this feature)

```text
specs/040-match-share-card/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── match-record-detail-api.md     # Phase 1：回應新增 target_score
│   └── share-card-module.md           # Phase 1：前端模組的公開介面與 dialog 輸入
├── checklists/
│   └── requirements.md  # /speckit-specify output
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
apps/api/
├── app/domains/group/
│   ├── schemas.py              # 擴充：MatchRecordDetailResponse.target_score: int
│   └── service.py              # 擴充：build_match_record_detail() 填入 match.target_score
└── tests/
    ├── contract/
    │   ├── test_group_match_record_detail.py    # 擴充
    │   └── test_member_match_record_detail.py   # 擴充
    └── unit/domains/member/
        └── test_personal_settings.py            # 擴充：好友詳情端點

apps/web/src/
├── app/core/
│   ├── api/group-member-view.models.ts          # 擴充：MatchRecordDetailResponse.target_score
│   ├── match-record-detail/
│   │   ├── score-trend.ts                       # 新增：從 dialog 抽出的走勢點純函式
│   │   ├── score-trend.spec.ts                  # 新增
│   │   ├── match-record-detail-dialog.component.{ts,html}   # 擴充：shareContext 輸入、分享按鈕、改用 score-trend
│   │   └── match-record-detail-dialog.component.spec.ts     # 擴充
│   └── match-share-card/                        # 新增模組
│       ├── share-card.models.ts                 # ShareCardContext / ShareCardModel / Highlight 型別
│       ├── share-card-model.ts (+ .spec.ts)     # buildShareCardModel()
│       ├── share-card-highlights.ts (+ .spec.ts)# pickHighlights()
│       ├── share-card-palette.ts                # 亮色／暗色色盤
│       ├── share-card-renderer.ts (+ .spec.ts)  # renderShareCard()＋文字截斷
│       ├── share-card-actions.service.ts        # 產生 Blob、分享、複製、下載（可替換）
│       └── share-card-dialog/                   # 預覽 dialog 元件
│           ├── share-card-dialog.component.{ts,html,scss}
│           └── share-card-dialog.component.spec.ts
├── app/features/
│   ├── member/match-history/match-history.component.{ts,html}                  # 擴充：mine 視角 context
│   ├── friends/friend-match-records/friend-match-records.component.{ts,html}   # 擴充：neutral context
│   ├── group-member-view/group-member-view.component.html                     # 擴充：傳 groupName
│   ├── group-member-view/match-records/match-records.component.{ts,html}       # 擴充：groupName 輸入、neutral context
│   └── member/my-groups/group-history/group-history.component.{ts,html}        # 擴充：neutral context
│   （以上各自的 .spec.ts 同步擴充）
└── assets/i18n/{zh-TW,en}.json                  # 擴充：matchShareCard.*
```

**Structure Decision**：沿用既有 monorepo 配置。圖卡放在 `apps/web/src/app/core/`，與 `match-record-detail/`、`court-diagram/` 等跨頁共用元件並列，因為它會從四個 feature 頁面經由共用的詳情 dialog 被使用。後端改動留在擁有 `build_match_record_detail()` 的 `group` domain 內，只讀取該函式手上的 `Match` 物件，不構成新的跨 domain 依賴（Constitution VI）。

## Complexity Tracking

無違反項目，本節不適用。
