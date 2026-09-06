# Implementation Plan: 團內成員視圖（Member View）

**Branch**: `N/A (no git repository initialized)` | **Date**: 2026-09-01 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/005-member-view/spec.md`，交叉比對 `/specs/architecture.md`（Match/MatchResult 合併決策）、`/specs/001-create-manage-group/`（`RosterEntry` 之 `status`/`joined_at`/`member_id` 欄位）、`/specs/003-schedule-rotation/`（`Match`/`MatchParticipant`、`handle_member_left`、`build_schedule_snapshot`、`generate_next_round`）、`/specs/004-join-group/`（`resolve_guest_session`、`active_roster_entry_for_member`、公開端點之 Guest/Member 雙軌身分驗證模式）、`/specs/006-member-friends/`（`require_member`）、`/specs/007-live-scoreboard/`（`match.scoreUpdated`/`match.ended`/`rotation.updated` 等既有 Ably 事件、比分/賽程即時同步基礎設施）。

## Summary

一般成員（非管理員）進入已加入的團時看到「賽程／戰績／退出組團／
對戰紀錄」四項唯讀+單一操作的導覽，與管理員視圖完全區隔。賽程頁直接
重用既有 `build_schedule_snapshot()` 與 007 已建立的 Ably 事件，僅
換一套不需管理 PIN 的身分驗證（Guest token 或 Member JWT + active
`RosterEntry`）。戰績頁的核心挑戰是「已離開」狀態判定需要「該輪開始
時間點」——這在目前系統完全不存在，故新增 `round_history` 表（由
003 既有的 `generate_next_round()` 順手寫入）與 `roster_entries
.left_at` 欄位，讓「勝／敗／未上場／已離開」四狀態可用一套純函式
公式即時推導、不需額外狀態機。對戰紀錄與會員跨團彙總共用同一份
「已完成比賽」查詢基礎，差異僅在篩選範圍。退出組團重用 003 既有的
`handle_member_left()`（與踢除同一函式，差在觸發者是本人還是管理員）。
Guest 紀錄不可回溯合併會員帳號的規則，經確認現有資料模型（`roster_
entries.member_id` 於建立當下即定案、無任何事後改寫路徑）已天然滿足，
不需新增防呆邏輯。

## Technical Context

**Language/Version**：延續 001-004、006、007（後端 Python 3.12+；
前端 TypeScript / Angular 20+）。

**Primary Dependencies**：沿用既有 FastAPI/SQLAlchemy/Alembic、Ably
JS SDK 堆疊，不新增套件。

**Storage**：PostgreSQL，新增 1 張表（`round_history`）+ 1 個既有表
新增欄位（`roster_entries.left_at`），MUST 有對應 Alembic migration
（本 feature 的唯一 schema 變更需求，見 research.md #1、#3）。

**Testing**：pytest + pytest-asyncio。核心領域邏輯（四狀態判定公式之
全部四種狀態與其各自成因、`round_history` 寫入時機、`left_at` 一旦
成立即不可逆之單向鎖定特性、身分驗證函式之 Guest/Member 雙軌與
disbanded 團仍可讀取、跨團查詢天然排除 Guest 紀錄）MUST 有單元測試；
至少一條整合測試涵蓋「多輪比賽（含候補/捨棄/中途退出/中途加入）→
戰績頁四狀態皆正確」全流程。

**Target Platform**：延續 001-004、006、007。

**Project Type**：Web application（monorepo，延續既有結構）。

**Performance Goals**：SC-002——賽程頁比分/賽程狀態變動後約 1 秒內
同步（沿用 007 既有 Ably 基礎設施，非本 feature 新增效能需求）；
戰績/對戰紀錄頁為讀取即時查詢，無 Ably 即時同步要求（quickstart.md
情境 2、3 為載入時查詢，spec Assumptions 未要求次秒級同步）。

**Constraints**：`round_history` 之寫入 MUST 與 `generate_next_round()`
既有的 `current_round_number` 遞增在同一交易內完成（research.md #1，
避免兩者不同步）；一般成員視圖之所有讀取端點 MUST NOT 以
`Group.status == 'active'` 作為存取條件（research.md #5，disbanded
團仍可唯讀查閱）；退出組團 MUST NOT 觸發 Round 重新排點（FR-014，
直接沿用 003 `handle_member_left` 既有保證，不需額外程式碼確保）。

**Scale/Scope**：戰績表格規模與「賽程與輪替名單」規格的輪替演算法
規模相近（單團中小型社群規模，逐輪逐人查詢，`round_history` 主鍵
查詢皆為 O(1) 命中）；會員跨團彙總之查詢規模為單一會員曾參與的團數
（預期為個位數至十位數量級），即時計算即可，不需快取層（research.md
#8）。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | Pydantic v2 schema 對應所有新回應（`GroupStandingsResponse`/`GroupMatchRecordsResponse`/`MemberMatchRecordsResponse` 等）；`ruff`/`mypy --strict` blocking check。 | PASS |
| II. 測試優先 | 四狀態判定公式（含全部成因）、`round_history` 寫入時機、`left_at` 不可逆特性、Guest/Member 雙軌身分驗證、跨團查詢天然排除 Guest 紀錄，皆屬核心領域邏輯，MUST 有單元測試；至少一條整合測試涵蓋完整戰績流程。 | PASS（列入 tasks.md 強制項） |
| III. 即時性與一致性 | 賽程頁直接重用 007 已建立的 Ably 事件與 1 秒同步保證（research.md #6），不重新實作；戰績/對戰紀錄為讀取即時查詢，spec 未要求 Ably 即時同步，PASS（不適用之處已說明）。 | PASS |
| IV. 權限與安全 | 一般成員視圖 MUST NOT 提供任何管理員專屬操作（FR-002，前端落實，後端端點本身即無法觸發任何寫入類管理操作）；讀取端點 MUST 驗證呼叫者持有有效加入憑證（research.md #5），MUST NOT 僅憑 `group_id` 即可存取，落實憲章「密碼保護的是查看/加入資格」之既有規則；退出組團之授權 MUST 驗證呼叫者就是 `roster_entry_id` 本人（不可代替他人退出）。 | PASS |
| V. UX 一致性 | 「退出組團」為有一定不可逆影響的操作（失去加入狀態、需重新走加入流程），MUST 提供二次確認彈窗（FR-013）。 | PASS（前端落實於 tasks.md 展開） |
| VI. 可維護性 | 新增獨立的 `member-view`/`standings` 服務邏輯（暫定置於 `group` 模組擴充，見 Project Structure），重用而非重新實作 003 之 `build_schedule_snapshot`/`handle_member_left`、004 之 `active_roster_entry_for_member`；對 003 的唯一擴充（`generate_next_round` 新增一次 INSERT、`handle_member_left` 新增一次欄位賦值）皆為新增，不變更既有行為。 | PASS |
| VII. 無障礙 | 戰績表格的「已離開」狀態 MUST 同時有文字標籤與非純色彩之視覺區分（例如圖示或底線），不可僅靠顏色區分四種狀態（憲章原則 VII 之既有通用規則，前端落實於 tasks.md 展開）。 | PASS |
| VIII. i18n 與時區 | 錯誤回應一律語意化代碼（`MEMBERSHIP_REQUIRED`、`ROSTER_ENTRY_NOT_FOUND`）；戰績狀態列舉（`won`/`lost`/`did_not_play`/`left`）為後端語意化字串，前端依語系檔轉換為「勝/敗/未上場/已離開」等顯示文字，不寫死中文於後端。 | PASS |
| IX. 可攜性 | 沿用既有 Docker/AWS 設計，僅需一支新 Alembic migration，不需額外基礎設施。 | PASS |
| X. 伺服器為單一事實來源 | 戰績/對戰紀錄之四狀態判定完全在後端查詢時即時推導，前端不做任何本地判定邏輯；本 feature 無新增 Ably 發布事件（重用既有）。 | PASS |
| XI. 防機器人 | 本 feature 之端點皆非「建立新資源」類型（讀取查詢、退出既有資源），不在原則 XI 之 Turnstile 強制範圍內。 | PASS（明確排除項，非違反） |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/005-member-view/
├── plan.md                    # 本檔案
├── research.md                # Phase 0 產出
├── data-model.md              # Phase 1 產出
├── quickstart.md              # Phase 1 產出
├── contracts/                 # Phase 1 產出
│   └── member-view-api.md
└── tasks.md                   # /speckit-tasks 產出（本指令不建立）
```

### Source Code (repository root)

```text
apps/api/
├── alembic/versions/          # 新增：round_history 表 + roster_entries.left_at 欄位
├── app/
│   └── domains/
│       ├── roster/
│       │   └── models.py      # 擴充：RosterEntry.left_at
│       ├── group/
│       │   ├── models.py      # 新增：RoundHistory model
│       │   ├── schemas.py     # 新增：GroupStandingsResponse/MemberStandingRow/
│       │   │                    #   RoundStatus/GroupMatchRecordsResponse/
│       │   │                    #   MatchRecordSummary/MemberMatchRecordsResponse/
│       │   │                    #   MemberMatchRecordSummary/LeaveGroupRequest/
│       │   │                    #   LeaveGroupResponse（含會員跨團版本，供 member
│       │   │                    #   模組匯入重用，見下方 member/ 說明）
│       │   ├── service.py     # 新增：resolve_active_roster_membership()、
│       │   │                    #   build_group_standings()、build_group_match_
│       │   │                    #   records()、_completed_matches_query()、
│       │   │                    #   leave_group()
│       │   └── router.py      # 新增：GET .../member-schedule、GET .../standings、
│       │                        #   GET .../match-records、POST .../roster/{id}/leave
│       ├── member/
│       │   ├── service.py     # 新增：build_member_match_records()（跨模組匯入
│       │   │                    #   重用 group.service._completed_matches_query()，
│       │   │                    #   research.md #8）
│       │   └── router.py      # 新增：GET /members/me/match-records（require_
│       │                        #   member，006 既有）
│       └── schedule/
│           └── service.py     # 擴充：generate_next_round() 寫入 round_history、
│                                #   handle_member_left() 寫入 left_at
└── tests/
    ├── unit/domains/group/    # 擴充：本 feature 之新測試檔案
    ├── unit/domains/member/   # 新增：build_member_match_records() 測試
    ├── contract/
    └── integration/

apps/web/
└── src/app/features/
    ├── group-member-view/     # 新增：一般成員導覽 + 賽程/戰績/對戰紀錄/退出組團
    │   ├── member-schedule/
    │   ├── standings/
    │   └── match-records/
    └── member/
        └── match-history/     # 新增：會員頁面跨團對戰紀錄（US5）
```

**Structure Decision**：擴充既有 `app/domains/group` 模組（US1–US4 之
所有新讀取/寫入邏輯皆以 `group_id` 為核心，且大量重用 004 已建立於此
模組的身分驗證輔助函式），不新建獨立模組；對 `schedule`/`roster`
模組僅做 research.md #1、#3 所述之最小新增，不修改既有行為。**例外**：
US5 之 `GET /members/me/match-records` 本質上是「會員」而非「群組」
範疇的端點（無 `group_id` 路徑參數，驗證方式為 006 既有
`require_member` 而非本 feature 之 `resolve_active_roster_membership()`），
故其 `service.py`/`router.py` 置於既有 `app/domains/member/` 模組而非
`group/`；其 `build_member_match_records()` 透過跨模組匯入重用
`group.service._completed_matches_query()`（research.md #8 明確設計為
共用查詢基礎，非重複實作）。前端新增 `features/group-member-view/`
（比照既有 `features/group-admin/` 之目錄慣例，管理頁 vs 成員頁分屬
平行目錄），`features/member/` 下新增 `match-history/` 子目錄呈現
跨團彙總（沿用 006 已建立的 `features/member/` 骨架）。

## Complexity Tracking

*本 feature 無 Constitution Check 違反項目，此表格從略。*

## Post-Design Constitution Check

*Re-evaluated after Phase 1（`data-model.md`、`contracts/`、
`quickstart.md`）產出。*

設計階段的關鍵決策——(1) 新增 `round_history` 表而非嘗試從既有欄位
推算 Round 開始時間（research.md #1，手動安排模式下確認別無選擇）、
(2) 「已發生 Round」範圍排除第 1 輪（research.md #2，避免恆為空的
雜訊欄位）、(3) 四狀態判定為純函式公式、不新增狀態機或額外寫入路徑
（research.md #4）、(4) 一般成員身分驗證獨立於 004 既有 `resolve_
guest_session()`、刻意不檢查 `Group.status`（research.md #5，落實
disbanded 團仍可讀取的 Edge Case 要求）——皆為在不違反任何 FR 與既有
Constitution 判定的前提下確保正確性的必要設計，未引入新的違反項目。
對既有模組（`schedule`、`roster`）的唯一觸碰皆為新增寫入（`round_
history` INSERT、`left_at` 賦值），不變更既有函式簽章或既有可觀察
行為，符合原則 VI。**Gate 結果維持 PASS，無需新增 Complexity
Tracking 項目。**

## Assumptions

- 戰績表格與對戰紀錄列表之呈現細節（Round 排序方向、分頁機制、
  「已離開」的圖示樣式）留待 tasks.md/實作階段依既有 UI 慣例決定，
  不影響本規格定義的可觀察行為（spec Assumptions 已明確授權）。
- 會員跨團對戰紀錄之彙總勝率計算僅計入 `completed` 比賽（spec
  Assumptions 已定案），`total_matches == 0` 時 `win_rate` 回傳 `0.0`
  （避免除以零，data-model.md 已明確）。
- 「退出組團」端點回傳 `201`（比照 004 `POST .../join` 之語意——
  「這次呼叫建立了一筆新的狀態轉換記錄」），而非 `200`；此為實作細節
  慣例選擇，不影響 FR 定義的可觀察行為。
