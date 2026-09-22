# Implementation Plan: 快速開始比賽（不開團）

**Branch**: `feature/quick-match` | **Date**: 2026-09-22 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/042-quick-match/spec.md`，交叉比對 `/apps/api/app/domains/group/service.py`（`create_group()`、`_raise_if_active_elsewhere()`、`join_group()`、`disband_group()`、`list_groups()`）、`/apps/api/app/domains/schedule/service.py`（`manual_assign()`、`create_match_with_participants()`、`apply_score_delta()`、`_advance_after_terminal()`、`court_live_state()`、`abandon_group_matches()`）、`/apps/api/app/domains/group_invite/service.py`（`send_invite()`、`accept_invite()`、`decline_invite()`、`invalidate_pending_invites_for_group()`）、`/apps/api/app/domains/notification/service.py`、`/apps/api/app/domains/court/service.py`（`get_court_by_token()`）、`/apps/api/app/domains/member/service.py`（`get_my_groups()`、`_build_member_match_record_summaries()`、`_filtered_member_matches()`）、`/apps/api/app/scheduler/auto_disband.py`、`/apps/api/app/system_config/service.py`、`/apps/web/src/app/features/{home,control-panel,scoreboard,group-admin/create-group,group-invites,notifications,member/match-history}`、`/apps/web/src/app/core/match-share-card/`

## Summary

讓使用者在首頁按一顆「快速開始比賽」，填單頁表單就直接進到控制板計分；打完可再打一場或換人再打；戰績、逐點紀錄、分享卡、對戰紀錄與團內比賽完全相同。

1. **資料層（research Decision 1）**：快速比賽就是一個 `groups.kind = 'quick'` 的團——固定手動排程、一個場地、2 或 4 人、不回傳 PIN。七張表的 NOT NULL `group_id` 外鍵、計分、即時頻道、統計、綁定戰績全部零改動。
2. **協調層（Decision 2、3）**：新 domain `quick_match` 自己組團／場地／名單，每一場都走既有的 `manual_assign()`，輪次固定 1。`create_group()` 一行不改。
3. **好友接受（Decision 4）**：邀請列與通知沿用 `group_invites` + `notifications`（新型別 `quick_match_invite`），接受仍由 `join_group()` 單一路徑寫入；新表 `quick_match_slots` 記錄「哪個位置等誰」，全部 ready 才開賽；拒絕／逾時／「不等了」把位置轉為訪客。逾時惰性判定＋每分鐘 sweep 兜底。
4. **憑證（Decision 5，Q1）**：所有快速比賽動作以控制板 token 授權、守門條件 `kind == 'quick'`；對 Constitution IV 的有界例外，見 Complexity Tracking。
5. **收尾（Decision 6）**：結束／取消／閒置＝既有 `disband_group()`；sweep 對 `quick` 用 `system_config.quick_session_idle_minutes`（依 spec 預設 1440，**建議使用者考慮改 60 與一般團一致**）。FR-020 的自動收尾掛在 `_raise_if_active_elsewhere()` 的 hook。
6. **呈現（Decision 7、8）**：既有回應只新增 `group_kind`，前端依它換語系標籤、隱藏輪次、排除列表；新 feature `quick-match`（表單＋等待畫面）、控制板內嵌 `quick-actions`、首頁 CTA 與橫幅、通知路由一條。

## Technical Context

**Language/Version**：延續既有（後端 Python 3.12+，FastAPI + SQLAlchemy 2.0 async + APScheduler；前端 Angular 20 + TypeScript strict mode）。

**Primary Dependencies**：沿用既有堆疊，**不新增任何第三方套件**。即時同步 Ably（`core/realtime.py::publish()`）、Turnstile（`core/turnstile.py::verify_turnstile_token()`）、速率限制 slowapi（`core/rate_limit.py`）。

**Storage**：PostgreSQL。**一支 migration**（接在 `b7e2d4a9c130` 之後）：`groups.kind VARCHAR(16) NOT NULL DEFAULT 'normal'` + 索引、新表 `quick_match_slots`、`system_config` 兩列（`quick_match_invite_timeout_seconds='120'`、`quick_session_idle_minutes='1440'`）。純新增、可 downgrade。詳見 [data-model.md](./data-model.md)。

**Testing**：
- 後端 pytest：
  - `tests/unit/domains/quick_match/test_lineup_rules.py`（新，無資料庫）——`swapped_lineup()`；名單驗證（人數依模式、`self` 位置、重複暱稱／好友、訪客不可挑好友）；位置狀態機（全部 ready 才開賽、pending 逾時、轉換後不可接受）；sweep 期限選擇（normal 60 分／quick 用設定）。
  - `tests/unit/domains/quick_match/test_quick_session.py`（新，經資料庫）——`start_quick_session()` 建立的團／場地／名單／round_history 欄位值；會員與訪客建立者；含好友時為 waiting 且不建比賽；失敗 rollback 不留任何列；`resolve_expired_slots()`；`on_invite_resolved()` 的接受／拒絕／在別團三種結果；換人再打的名單差異（保留 ready 好友、移除者 left、新好友 pending）；`close_quick_session()`。
  - `tests/contract/test_quick_match_create.py`、`test_quick_match_by_token.py`、`test_quick_match_lineup.py`（新）——contracts/quick-match-api.md 的每個端點與錯誤碼；計分板 token → `LINK_NOT_FOUND`；一般團 → `QUICK_SESSION_ONLY`；Turnstile 失敗；速率限制；`GET /members/me/quick-session` 的 creator／participant 差異。
  - `tests/contract/test_group_invite_endpoints.py`（擴充）——快速比賽邀請的 detail 新欄位、accept 回 `scoreboard_token`、已開賽後 accept → `GROUP_INVITE_NOT_PENDING`。
  - `tests/contract/test_group_list_filters.py`、`test_member_groups_history_endpoints.py`、`test_member_match_records_endpoint.py`、`test_court_by_token.py`、`test_court_state.py`（擴充）——排除／`include_quick`／`group_kind` 欄位與篩選。
  - `tests/unit/scheduler/test_auto_disband_quick.py`（新）——兩種期限；有 pending 位置的 quick 團被 sweep 觸發逾時轉換並開賽。
  - `tests/integration/test_quick_match_flow.py`（新）——quickstart §1 的完整流程。
- 前端 `ng test`：`quick-start.component.spec.ts`（表單規則、模式切換、等待畫面狀態、事件導向）、`quick-actions.component.spec.ts`、`control-panel.component.spec.ts`（quick 分支）、`notification-list.component.spec.ts`（新型別路由）、`share-card-model.spec.ts`（標籤替換）、`match-history.component.spec.ts`（標籤與篩選）。`ng lint`、`ng build`。

**Target Platform**：Linux 容器（Docker）；瀏覽器以手機優先。

**Project Type**：web application（`apps/api` + `apps/web`）。

**Performance Goals**：建立端點一次交易（≤ 1 個 Turnstile 外部呼叫 + 數次 INSERT）；好友接受到建立者畫面切換 ≤ 1 秒（SC-008，靠 Ably 事件）；sweep 每分鐘一次、以索引掃描。

**Constraints**：不改 `create_group()`、`manual_assign()`、`apply_score_delta()` 的任何行為；一般團的所有既有回應只增欄位；Constitution IV 例外以 `kind == 'quick'` 守門。

**Scale/Scope**：後端 1 新 domain（4 檔）、1 migration、6 個既有 domain 各數十行；前端 1 新 feature（4–5 檔）、6 個既有畫面小分支、2 個語系檔。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本功能如何符合 | 結果 |
|---|---|---|
| I. 型別安全 | 後端新增 Pydantic schema 與型別化 ORM；前端 strict mode、新 models 檔；`ng lint`／`tsc` 為關卡。 | PASS |
| II. 測試優先 | 開賽、換邊、位置狀態機為純函式可獨測；建立→接受→計分→再打→結束有整合測試；既有 `manual_assign`、`create_group`、邀請的契約測試零 diff 證明不變。 | PASS |
| III. 即時性與一致性 | 每場由 `create_match_with_participants()` 快照計分制（FR-011）；提前結束、結束、取消、閒置收尾一律 `abandoned` 不計入（FR-012、FR-023）；所有畫面在事件後重新載入伺服器狀態。 | PASS |
| IV. 權限與安全 | PIN 雜湊、不回傳；無需驗證的控制板**新增**「再打一場／換人再打／結束／取消／不等了」——這是管理性質的操作，為對本原則的有界例外，理由與守門條件見 Complexity Tracking。暱稱等自由文字前端一律 escape（既有）。連結 token 沿用既有可重新產生的機制（快速比賽不提供重產入口，但機制不變）。 | **例外（已記錄）** |
| V. UX 一致性 | 「結束」「取消」走 `app-confirm-dialog`；playing 時「結束」說明比賽會被捨棄；「再打一場」「換人再打」不具破壞性、不加確認。 | PASS |
| VI. 可維護性 | 新 domain `quick_match` 只透過既有 service 函式與注入 hook 與其他 domain 互動；`create_group()`、`manual_assign()` 不改。 | PASS |
| VII. 無障礙與行動裝置 | 「快速比賽」標籤為文字非顏色；表單與等待畫面以 360px 為基準；quickstart 有手機驗收步驟。 | PASS |
| VIII. i18n 與時區 | 所有新文字在 `quickMatch.*`／`errors.*` 語系 key；後端只回錯誤碼與 `group_kind`，團名後備值不被前端顯示；`expires_at` 等時間皆 `TIMESTAMPTZ` UTC、ISO 8601 回傳。 | PASS |
| IX. 可攜性 | 無新環境變數；兩個期限放 `system_config`。 | PASS |
| X. 伺服器為可信來源 | `quickMatch.lineupChanged`、`rotation.updated` 只由後端 commit 後發布；前端收到只重新載入；開賽判定在後端交易內（`FOR UPDATE`）。 | PASS |
| XI. 防濫用 | `POST /quick-matches` 是「建立新資源」端點：Turnstile fail-closed + `20/minute` 速率限制（比 `POST /groups` 多了速率限制，為本功能新增）。其餘動作端點以控制板 token 為憑證、不建立新團。 | PASS |

**Gate 結果**：一項有界例外（IV），已於 Complexity Tracking 記錄並需使用者確認；其餘 PASS。

**Post-design re-check（Phase 1 完成後）**：data-model.md 與 contracts/ 確認——儲存變更為一欄、一表、兩列設定，皆純新增；既有端點只增欄位與查詢參數，一般團回應零變動；控制板的 quick 端點全部以 `kind == 'quick'` 守門，一般團打到任何一支都是 404 語意。設計期間三處回頭對照規格：(1) 規格 Key Entities 沒有「位置」這個實體——`quick_match_slots` 是 FR-027／FR-030 的內部依據（哪個位置等誰、換人時誰保留），不對外呈現，與 037 的 `roster_rest_periods` 同性質；(2) 規格 FR-022 的閒置期限預設一天——查證後發現一般團既有的自動解散是 60 分鐘，設計保留規格值但把建議寫進 research Decision 6 與本文 Summary，由使用者決定；(3) 規格 FR-020 只講「會員」——訪客建立者沒有跨團身分，沿用既有「訪客不受一人一團限制、前端以本機紀錄擋」的作法（`getActiveGuestGroupId()`），不需修改規格。Gate 結果維持不變。

## Project Structure

### Documentation (this feature)

```text
specs/042-quick-match/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   ├── quick-match-api.md         # 新 router /quick-matches、既有端點的擴充
│   ├── ably-events-additions.md   # 新事件 quickMatch.lineupChanged、沿用事件對照
│   └── frontend-surfaces.md       # 新路由、表單、控制板／計分板／通知／紀錄的分支
├── checklists/
│   └── requirements.md  # /speckit-specify output
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
apps/api/
├── alembic/versions/<new>_quick_match.py     # 新增：down_revision = b7e2d4a9c130
├── app/main.py                               # 修改：include quick_match router
├── app/domains/quick_match/                  # 新增 domain
│   ├── models.py        # QuickMatchSlot
│   ├── schemas.py       # QuickMatchCreateRequest、LineupSlotInput、QuickSessionState、SlotView、
│   │                    # MemberQuickSessionResponse
│   ├── service.py       # start_quick_session()、get_session_state()、rematch()、replace_lineup()、
│   │                    # convert_slot_to_guest()、cancel_session()、close_quick_session()、
│   │                    # resolve_expired_slots()、on_invite_resolved()（hook）、
│   │                    # close_idle_quick_session()（hook，FR-020）、純函式 swapped_lineup()、
│   │                    # validate_lineup()、pick_idle_cutoff()
│   └── router.py        # POST /quick-matches；GET/POST /quick-matches/by-token/{token}[/rematch|
│                        # /lineup|/slots/{id}/convert|/cancel|/close]；GET /members/me/quick-session
├── app/domains/group/
│   ├── models.py        # 擴充：Group.kind
│   ├── schemas.py       # 擴充：GroupListItem 不變；MyGroupSummary.group_kind（在 member）
│   ├── service.py       # 修改：list_groups() 基礎條件 kind='normal'；
│   │                    #       _raise_if_active_elsewhere(close_idle_quick_session=…) hook、
│   │                    #       detail.group_kind
│   └── router.py        # 修改：注入 hook；GET /groups 不變
├── app/domains/group_invite/
│   ├── schemas.py       # 擴充：GroupInviteDetail.group_kind / match_mode / inviter_nickname；
│   │                    #       AcceptResponse.scoreboard_token
│   ├── service.py       # 修改：accept_invite() / decline_invite() 的 on_resolved hook；
│   │                    #       send_invite() 依 group.kind 建 quick_match_invite 通知
│   └── router.py        # 修改：注入 quick_match.service.on_invite_resolved
├── app/domains/notification/
│   ├── schemas.py       # 擴充：NotificationType 加 quick_match_invite、detail 物件
│   └── service.py       # 擴充：create_quick_match_invite_notification()、summaries 的 batch 查詢
├── app/domains/court/
│   ├── schemas.py       # 擴充：CourtByTokenResponse.group_kind
│   └── router.py        # 修改：填 group_kind
├── app/domains/schedule/
│   ├── schemas.py       # 擴充：CourtStateResponse.group_kind
│   └── router.py        # 修改：_court_state_response() 填 group_kind
├── app/domains/member/
│   ├── schemas.py       # 擴充：MemberMatchRecordSummary/Detail、MemberGroupHistoryResponse、
│   │                    #       MyGroupSummary 的 group_kind
│   ├── service.py       # 修改：get_my_groups(include_quick)、_filtered_member_matches(group_kind)、
│   │                    #       summaries 填 group_kind；好友對戰紀錄同
│   └── router.py        # 修改：新查詢參數
├── app/scheduler/auto_disband.py             # 修改：兩種期限；quick 團先 resolve_expired_slots()
├── app/system_config/service.py              # 擴充：get_quick_match_invite_timeout_seconds()、
│                                             #       get_quick_session_idle_minutes()
└── tests/                                    # 見 Technical Context

apps/web/src/
├── app/app.routes.ts                                   # 新增：quick-match/new
├── app/features/quick-match/                           # 新增 feature
│   ├── quick-match.models.ts
│   ├── quick-match.service.ts                          # /quick-matches API、/members/me/quick-session
│   ├── quick-start/quick-start.component.{ts,html,scss,spec.ts}   # 表單＋等待畫面
│   ├── lineup-editor/lineup-editor.component.{ts,html,scss}       # 名單編輯（表單與換人再打共用）
│   └── quick-actions/quick-actions.component.{ts,html,scss,spec.ts} # 控制板內嵌
├── app/features/home/home.component.{ts,html}          # 擴充：CTA、橫幅
├── app/features/control-panel/control-panel.component.* # 擴充：quick 分支、訂閱 lineupChanged
├── app/features/scoreboard/*                           # 擴充：標籤、隱藏輪次、closed 文字
├── app/features/notifications/notification-list/*      # 擴充：型別→路由、文字
├── app/features/group-invites/group-invite-detail/*    # 擴充：quick 文字、接受後導向計分板
├── app/features/member/match-history/*、my-groups/*、friends/*/match-records/* # 擴充：標籤、篩選
├── app/core/api/court-control.service.ts、notification.models.ts、*.models.ts   # 擴充：group_kind
├── app/core/match-share-card/share-card-model.ts       # 擴充：quick 標籤
└── assets/i18n/zh-TW.json、en.json                     # 擴充：quickMatch.*、errors.*
```

**Structure Decision**：維持既有的「後端依 domain、前端依 feature」結構；快速比賽作為新 domain／新 feature 加入，其他模組只做欄位與分支的小擴充。

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Constitution IV：無需驗證的控制板提供「再打一場／換人再打／結束／取消／不等了」——這些是建立比賽、改名單、解散的管理性質操作 | 快速比賽刻意沒有管理頁與 PIN（spec 背景、FR-002）；使用者於 2026-09-22 決定（Q1）控制板連結是唯一憑證、不區分建立者。這些動作的破壞力不超過控制板既有的「提前結束」；守門條件 `group.kind == 'quick'` 讓一般團的邊界一行不變（一般團打到這些端點一律 `QUICK_SESSION_ONLY`）。 | (a) 把建立時的管理 token 存在瀏覽器——訪客關掉分頁後整場卡住，且違反 Q1 的決定；(b) 快速比賽也給一個管理頁——把本功能要消除的「團」概念又帶回來。**需專案負責人確認**後才進入 `/speckit-tasks`（Constitution Governance）。 |
