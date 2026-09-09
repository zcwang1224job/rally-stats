# Implementation Plan: 比賽加減分紀錄與趨勢圖（Match Score Timeline & Trend Chart）

**Branch**: `main`（本專案未使用 per-feature git branch，延續既有慣例）| **Date**: 2026-09-09 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/016-match-score-timeline/spec.md`，交叉比對 `/specs/005-member-view/`（`_completed_matches_query()`、`resolve_active_roster_membership()`）、`/specs/007-live-scoreboard/`（`score_events` 的寫入路徑 `apply_score_delta()`，本 feature 的唯一資料來源，未修改）、`/specs/014-member-groups-history/`（`verify_ever_group_member()`）。

## Summary

現有「對戰紀錄」三個入口（團內對戰紀錄分頁、會員跨團對戰紀錄、我的團
歷史）皆只顯示最終比分。本 feature 新增兩個唯讀端點——
`GET /groups/{group_id}/match-records/{match_id}`（重用既有
`resolve_active_roster_membership()`）與 `GET
/members/me/match-records/{match_id}`（重用既有
`verify_ever_group_member()`）——回傳同一份 `MatchRecordDetailResponse`：
既有的比賽基本資訊，加上依「開賽後經過秒數」排序的完整加減分紀錄
（`score_events`，007-live-scoreboard 已寫入、未曾有讀取端點）與一個
「完整／部分／無」三態標記（純粹從紀錄本身的第一筆資料推導，見
research.md #3）。前端新增一個共用彈出視窗元件，供三個既有清單點擊
使用，以既有的手刻 inline SVG 慣例畫出雙方比分趨勢圖，兩條曲線以線條
樣式＋文字圖例雙重區分（不僅靠顏色，FR-008）。全程不新增資料表、不新增
第三方套件。

## Technical Context

**Language/Version**：延續既有（後端 Python 3.12+；前端 TypeScript /
Angular 20+）。

**Primary Dependencies**：沿用既有 FastAPI/SQLAlchemy 堆疊與 Angular，
**不新增套件**——趨勢圖沿用既有 hand-rolled inline SVG + computed signal
慣例（`group-history.component.ts`／`match-history.component.ts` 既有
模式，research.md #5），`apps/web/package.json` 目前無任何圖表套件依賴。

**Storage**：PostgreSQL，**不新增資料表、不需要新 migration**——
`score_events` 表已於上一階段（本次對話稍早）建立並由
`apply_score_delta()` 寫入（`apps/api/alembic/versions/
f3a1c9d4e7b2_score_events_table.py`），本 feature 純粹是新增唯讀查詢
端點。

**Testing**：pytest + pytest-asyncio（後端：`get_completed_match_or_404`/
`build_match_record_detail` 的完整／部分／無三態判斷邊界、`elapsed_
seconds` 換算正確性、兩個新端點各自的授權邊界（現役 vs 曾經）皆 MUST
有單元/契約測試；至少一條整合測試涵蓋「打完一場比賽→查看詳情→看到
完整紀錄」全流程）。Vitest（前端：彈出視窗元件依 `record_completeness`
呈現三種畫面、趨勢圖 computed signal 的資料點正確性、雙曲線非純色彩
區分之渲染屬性存在性檢查）。

**Target Platform**：延續既有（Docker on AWS ECS，本地 `docker-compose`）。

**Project Type**：Web application（monorepo，延續既有 `apps/api` +
`apps/web` 結構）。

**Performance Goals**：SC-001——一次點擊、SHOULD 3 秒內看到詳情畫面
（比照既有 014 基準，人工抽測，非 blocking gate）。

**Constraints**：FR-005——兩個新端點 MUST 分別重用既有
`resolve_active_roster_membership()`／`verify_ever_group_member()`，
MUST NOT 新增或放寬任何授權語意。FR-006/006a——三態判斷 MUST 有明確、
可測試的邊界定義（research.md #3）。FR-008——趨勢圖雙曲線 MUST NOT
僅以顏色區分。

**Scale/Scope**：單場比賽的加減分紀錄筆數，理論上限由 `cap_score`
（既有欄位，一般 ≤ 30）與偶發的操作修正（扣分後重加）決定，數量級遠低於
既有清單分頁機制服務的資料量，本 feature 之 `events` 陣列不分頁
（FR：edge case「拉鋸很久」——MUST 完整回傳，不截斷）。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | 新增 Pydantic schema（`ScoreEventSummary`、`MatchRecordDetailResponse(MatchRecordSummary)`）涵蓋所有回應欄位；`ruff`/`mypy --strict` blocking check；前端 TypeScript strict mode，新彈出視窗元件與 API service 的型別直接對應後端 schema。 | PASS |
| II. 測試優先 | 本功能非原則 II 明列的核心領域清單，但比照既有 014 慣例，MUST 有單元測試覆蓋三態判斷（none/partial/complete）邊界與 `elapsed_seconds` 換算、兩個新端點的授權邊界契約測試；至少一條整合測試涵蓋「比賽自然結束→查看詳情」全流程。 | PASS（列入 tasks.md 強制項） |
| III. 即時性與資料一致性 | 本功能全程唯讀，不新增任何寫入路徑；沿用既有 `_completed_matches_query()` 之 `status == "completed"` 過濾，維持既有「只有自然結束的比賽才計入對戰紀錄」保證，未新增例外。 | PASS |
| IV. 權限與安全 | 兩個新端點分別重用既有 `resolve_active_roster_membership()`／`verify_ever_group_member()`，零修改、零放寬（research.md #1）——不同信任層級的授權路徑維持獨立。 | PASS |
| V. UX 一致性（破壞性操作二次確認） | 本功能全程唯讀查詢，無任何寫入或破壞性操作。 | 不適用 |
| VI. 可維護性 | 重用既有 `_completed_matches_query()`、`_build_match_record_summaries()`、兩支既有授權判斷式——不重新發明「什麼算已完成比賽」或「誰能看」的第三套邏輯。 | PASS |
| VII. 無障礙與行動裝置優先 | FR-008：趨勢圖 A/B 兩條曲線 MUST 搭配線條樣式＋文字圖例，不僅靠顏色，比照既有 `status-badge` 圖示＋文字並用慣例。 | PASS（前端落實於 tasks.md 展開） |
| VIII. i18n 與時區 | 新端點不新增任何錯誤代碼（沿用既有 `MEMBERSHIP_REQUIRED`/`MATCH_NOT_FOUND`/`MEMBER_TOKEN_INVALID`/`GROUP_MEMBERSHIP_NEVER_HELD`）；`elapsed_seconds` 為與時區無關的純數字秒數，前端「開賽後 X 分 Y 秒」文字集中於語系檔；`started_at`/`ended_at` 沿用既有 TIMESTAMPTZ/ISO8601 UTC 慣例。 | PASS |
| IX. 可攜性與可部署性 | 不新增任何基礎設施、不新增 migration、不新增前後端第三方套件。 | PASS |
| X. 即時同步的可信來源 | 本功能純讀取既有由伺服器寫入的 `score_events`，不涉及 Ably 或任何即時廣播，不新增寫入路徑。 | 不適用 |
| XI. 防機器人/防濫用 | 兩個新端點皆為既有授權保護下的唯讀查詢，不建立任何新資源，不在原則 XI 之 Turnstile 強制範圍內。 | PASS（明確排除項，非違反） |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/016-match-score-timeline/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/
│   └── match-record-detail-api.md
└── tasks.md             # Phase 2 output (/speckit-tasks command — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
apps/api/
├── app/domains/group/
│   ├── schemas.py       # + ScoreEventSummary, MatchRecordDetailResponse(MatchRecordSummary)
│   ├── service.py       # + get_completed_match_or_404(), build_match_record_detail()
│   └── router.py        # + GET /groups/{group_id}/match-records/{match_id}
├── app/domains/member/
│   ├── service.py       # + get_member_match_record_detail() (calls group.service's
│   │                     #   get_completed_match_or_404 / verify_ever_group_member /
│   │                     #   build_match_record_detail — same layering as get_member_group_history())
│   └── router.py        # + GET /members/me/match-records/{match_id}
└── tests/
    ├── unit/domains/group/test_match_record_detail.py       # 三態判斷、elapsed_seconds
    ├── contract/test_group_match_record_detail.py           # 群組範圍端點授權/形狀
    ├── contract/test_member_match_record_detail.py          # 會員範圍端點授權/形狀
    └── integration/test_match_score_timeline_flow.py        # 打完比賽→查看詳情、none/partial

apps/web/
└── src/app/
    ├── core/
    │   ├── api/group-member-view.models.ts             # + ScoreEventSummary, MatchRecordDetailResponse
    │   └── match-record-detail/                          # 新增：純呈現彈出視窗元件（比照既有 core/nav-shell、
    │       ├── match-record-detail-dialog.component.ts   #   core/breadcrumb 之慣例，放在 core/ 而非新開 shared/
    │       └── match-record-detail-dialog.component.html #   目錄）——不注入任何 service，只吃 @Input()
    ├── features/group-member-view/
    │   ├── group-member-view.service.ts                  # + getMatchRecordDetail(groupId, matchId)
    │   └── match-records/                                # 既有：新增點擊呼叫上面那支方法、餵給彈出視窗
    ├── features/auth/
    │   └── auth.service.ts                               # + getMatchRecordDetail(matchId)（跨團/我的團歷史共用）
    ├── features/member/match-history/                    # 既有：新增點擊呼叫 AuthService.getMatchRecordDetail
    └── features/member/my-groups/group-history/          # 既有：新增點擊呼叫同一支 AuthService 方法
```

（`/speckit-implement` 階段修訂：原規劃的 `core/api/match-record-detail.service.ts`
單一共用 service 已放棄，改為在既有 `GroupMemberViewService`/`AuthService`
上各自新增方法——理由與 research.md #4 的修訂說明相同：消除「呼叫端需要
傳對 `groupId` 參數」這個 I1 bug 的根源。）

**Structure Decision**：延續既有 monorepo 結構（`apps/api` + `apps/web`）。
後端新邏輯放在 `group` domain（與既有 `match-records` 端點同層，重用其
既有 helper），`member` domain 只新增一支端點呼叫 `group` domain 既有
函式（跨 domain 唯讀重用，比照既有 `member/service.py` 已在用
`group/service.py` 之 `_completed_matches_query()` 的既有先例）。前端
新增一個共用元件而非三份重複實作，供三個既有清單各自呼叫（research.md
#4）。

## Complexity Tracking

*Gate 無違反項目，本節無需填寫。*
