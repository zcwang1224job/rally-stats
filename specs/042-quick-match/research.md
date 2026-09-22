# Phase 0 Research: 快速開始比賽（不開團）

Technical Context 沒有 NEEDS CLARIFICATION——技術堆疊完全沿用既有，不新增套件。以下每一項決策都先查證過既有程式（`apps/api/app/domains/{group,schedule,group_invite,notification,court,member}/service.py`、`apps/api/app/scheduler/auto_disband.py`、`apps/web/src/app/features/{control-panel,home,group-admin/create-group,group-invites,notifications}`）。

## Decision 1：快速比賽在資料層就是一個 `kind = 'quick'` 的團

- **查證**：`matches.group_id`、`courts.group_id`、`roster_entries.group_id`、`score_events.group_id`、`score_serve_records.group_id`、`shot_placement_records.group_id`、`pair_history.group_id` 全部是 NOT NULL 外鍵；計分（`apply_score_delta()` 要 `Court` 與 `Group` 列更新 `last_activity_at`）、即時頻道命名（`court:{group_id}:{court_id}`）、逐點紀錄、發球／落點、會員對戰紀錄、好友對戰紀錄、分享卡、訪客綁定戰績（`resolve_guest_binding_target()` 刻意不看團狀態）全部依附在「團內比賽」上。
- **Decision**：`groups` 新增 `kind VARCHAR(16) NOT NULL DEFAULT 'normal'`（值域 `normal | quick`）。快速比賽＝一個 `kind='quick'` 的團，固定 `scheduling_mechanism='manual'`、`max_members` 為 2 或 4、`name` 存語系無關的後備值 `"快速比賽"`、不設通關密碼、`admin_pin_hash` 照樣產生但**永不回傳**。其餘欄位（計分制、詳細計分開關、`created_by_member_id`、`last_activity_at`、`status`）沿用原意。
- **Rationale**：零改動即可讓 US2 的「一模一樣」成立；所有「快速比賽要不一樣」的地方都收斂成「看 `kind`」：開團列表與「我的團」預設排除、by-token 回應多回一個 `group_kind` 讓前端換標籤與隱藏輪次、閒置收尾用不同期限。
- **Alternatives considered**：(a) 七張表的 `group_id` 改 nullable——每條寫入與統計路徑都要加分支，即時頻道無法命名；(b) 獨立 `quick_matches` 表——等於重做計分與統計，戰績無法合併（spec Assumptions 已排除）。

## Decision 2：新增 `quick_match` domain 當協調層，不改寫 `create_group()`

- **查證**：`group.service.create_group()`（`service.py:177`）一次做完：`_raise_if_active_elsewhere()`、人數上限、暱稱、預設團名、計分制 preset、密碼加密、PIN 產生、`Group` + 建立者 `RosterEntry` + 預設場地（inline，非 `create_court`）、commit、發布 `court.added`。它的請求形狀（`CreateGroupRequest`）與回應（含 `admin_pin`）都不適合快速比賽。
- **Decision**：新 domain `apps/api/app/domains/quick_match/`（`models.py`、`schemas.py`、`service.py`、`router.py`），`start_quick_session()` 自己組 `Group(kind='quick', …)`、場地、名單；PIN 與 token 的產生沿用 `group/security.py` 的 `generate_admin_pin()`／`hash_admin_pin()` 與模型欄位預設值（`join_link_token`、`all_courts_control_panel_token`、`group_number` 序列都是欄位預設，不需處理）。`create_group()` 一行不改。
- **與既有 domain 的依賴方向**：`quick_match` → `group`（`_raise_if_active_elsewhere()`、`join_group()`、`disband_group()`）、`schedule`（`manual_assign()`、`abandon_group_matches()`）、`group_invite`（`send_invite()`）、`court`（`get_court_by_token()`）、`notification`。既有 domain 只在兩個點回呼 `quick_match`，都用**注入的 hook**（比照 `disband_group(abandon_unfinished_matches=…)` 的既有模式），不 import：
  - `group_invite.service.accept_invite()` / `decline_invite()` 新增 `on_resolved: InviteResolvedHook | None` 參數，由 `group_invite/router.py` 注入 `quick_match.service.on_invite_resolved`。
  - `group.service._raise_if_active_elsewhere()` 新增 `close_idle_quick_session: CloseQuickSessionHook | None`（Decision 6）。
- **Rationale**：Constitution VI（模組化）；`create_group()` 是 Turnstile、開團預設值、通關密碼等多個規格的交會點，改它的風險遠大於多一個 100 行的組裝函式。
- **Alternatives considered**：把 `create_group()` 拆成 `_insert_group_row()` 給兩邊共用——`create_group()` 的六個 spec 的契約測試都要重跑驗證，且拆出來的函式參數會多到不可讀。

## Decision 3：每一場都走 `manual_assign()`；輪次固定為 1

- **查證**：`schedule.service.manual_assign(session, group, court, *, team_a, team_b)`（`service.py:2344`）已驗證：手動排程、無重複、場地空著、球員為本團 active 名單、沒人正在打；然後 `create_match_with_participants(status="in_progress", round_number=group.current_round_number)`（快照計分制與詳細計分）、`apply_wait_count_updates()`、commit、發布 `rotation.updated`。比賽結束後 `_advance_after_terminal()` 對手動排程沒有排隊場次可拉，場地變閒置、`waiting_reason = "manual_assignment"`，`_advance_other_idle_courts()` 對手動排程直接 return、`auto_next_round` 為 false 不換輪。
- **Decision**：開始、再打一場、換人再打三條路徑都呼叫 `manual_assign()`；建立快速比賽時把 `current_round_number` 設為 1 並寫一列 `round_history`，之後不再換輪。控制板與計分板在 `group_kind == 'quick'` 時隱藏輪次列。
- **Rationale**：不新增任何建立比賽的程式碼路徑（Constitution II：計分／排點的核心邏輯不多一份）；FR-011 的快照由 `create_match_with_participants()` 保證。
- **再打一場的換邊**：把上一場 `match_participants` 的 A／B 對調後傳入；規則在 `quick_match.service` 內，一個純函式 `swapped_lineup()` 可無資料庫測試。

## Decision 4：好友接受沿用 `group_invites` + 通知，名單狀態放在新表 `quick_match_slots`

- **查證**：`group_invite.service.send_invite()` 已驗證好友關係（`get_friendship_status() == "friends"`）、不在名單、無 pending 邀請；通知列與邀請列同一交易，commit 後 `publish_notification_created()`；`accept_invite()` 把整個加入委派給 `group.service.join_group(skip_password=True)`（人數上限、已解散、一人一團、暱稱全在那裡）。**`GroupInvite` 沒有到期時間**，只有被解散／配對失效時的 invalidation hook。
- **Decision**：
  - 邀請列與通知**沿用** `group_invites`（`inviter_member_id` = 建立者）與 `notifications`；通知 `type` 新增 `quick_match_invite`，讓前端走不同文字與路由（Decision 7）。`send_invite()` 的 `GROUP_NOT_MEMBER_CREATED` 檢查對快速比賽自然成立（只有登入會員才能挑好友）。
  - 新表 `quick_match_slots`（見 data-model.md）記錄**每一個位置**：隊伍、順位、來源（`self | friend | guest`）、暱稱、`member_id`、`invite_id`、`roster_entry_id`、狀態（`pending | ready`）、`expires_at`。訪客位置在建立時就 `join_group(member=None, nickname=…)` 拿到名單列（含 `guest_session_token`，028 的綁定入口）而直接 `ready`；好友位置 `pending`，接受後由 hook 填入 `roster_entry_id` 變 `ready`；拒絕／逾時／「不等了」則把該位置**轉成訪客**（同樣走 `join_group(member=None, nickname=好友暱稱)`），邀請列狀態設 `invalidated`。全部 `ready` 的那一刻呼叫 `manual_assign()`。
  - **逾時採惰性判定**：所有讀寫快速比賽狀態的入口（`GET …/by-token`、accept／decline hook、convert、rematch、lineup）先呼叫 `resolve_expired_slots()`；`scheduler/auto_disband.py` 的每分鐘 sweep 也順帶對 `kind='quick'` 且有 pending 位置的團呼叫一次，保證沒人看畫面時也會在期限後一分鐘內轉為訪客並開賽（SC-006 的精神）。期限 `quick_match_invite_timeout_seconds` 放 `system_config`（預設 120）。
  - 好友接受時 `join_group()` 拋 `ALREADY_ACTIVE_IN_ANOTHER_GROUP`（FR-029）→ hook 把該位置轉成訪客後**再把錯誤丟回給好友端**；建立者端由 `quickMatch.lineupChanged` 事件得知。
- **Rationale**：邀請、通知、好友關係、一人一團、人數上限、暱稱規則全部沿用同一條寫入路徑（`join_group()`），只新增「哪個位置等誰」這一層資訊。位置表也是「換人再打」的名單來源，與 `round_history` 一樣是內部表、不對外呈現。
- **Alternatives considered**：(a) `RosterEntry.status` 加 `invited`——`status == "active"` 在排程、名單、人數上限、授權、戰績的數十處查詢，037 已論證過不能擴充；(b) 位置資訊放 `group_invites` 上加欄位——訪客位置沒有邀請列，仍需另一處記錄，不如統一在一張表；(c) 獨立的 `quick_match_invites` 表與通知型別——重做好友驗證、通知建立、接受／拒絕端點，違反 Decision 2 的方向。

## Decision 5：控制板連結是快速比賽的唯一使用者憑證（Q1）

- **查證**：Constitution IV 規定無需驗證即可開啟的畫面 MUST NOT 提供管理員專屬操作（Next Round、踢人、解散、編輯排程）。`get_court_by_token()` 回傳 `link_type`（`scoreboard | control_panel`）；`_can_score_by_token()` 只讓 `control_panel` 寫入（計分板要開 `scoreboard_scoring_enabled`）。
- **Decision**：快速比賽的所有動作端點（再打一場、換人再打、不等了、取消、結束）都以 `control_panel` token 授權（`link_type != "control_panel"` → `LINK_NOT_FOUND`），不發任何管理 token 給前端。這是對 Constitution IV 的**有界例外**，記於 plan.md Complexity Tracking：(1) 快速比賽沒有管理頁，控制板就是它唯一的操作介面；(2) 這些動作的破壞力不高於控制板既有的「提前結束」（把進行中的比賽變成已捨棄）；(3) 例外以 `group.kind == 'quick'` 為守門條件——同一組端點對一般團一律 `QUICK_SESSION_ONLY`（404 語意），一般團的管理員邊界一行不變。挑好友（換人再打）另外要求呼叫者是登入的建立者本人（`optional_member` 且 `member.id == group.created_by_member_id`），否則只能填暱稱——因為邀請列的 `inviter_member_id` 與好友關係都是建立者的。
- **Alternatives considered**：把建立時的 admin token 存在瀏覽器 sessionStorage——訪客關掉分頁後整場卡住，且 Q1 已由使用者決定不區分建立者。

## Decision 6：閒置收尾沿用每分鐘的 `sweep_idle_groups()`，快速比賽用自己的期限

- **查證**：`scheduler/auto_disband.py` 用 APScheduler 每分鐘跑 `sweep_idle_groups()`：`status='active' AND last_activity_at < now - auto_disband_idle_minutes`（設定檔預設 **60 分鐘**）→ `disband_group()`（進行中比賽全部 abandoned、pending 邀請 invalidated、發布 `group.disbanded` 到每個場地頻道）。`apply_score_delta()` 每次計分都更新 `last_activity_at`。by-token 回應在解散後回 `group_disbanded: true`（不是 `LINK_NOT_FOUND`），控制板與計分板已有對應畫面。
- **Decision**：
  - 「結束」與等待中的「取消」＝`disband_group()`；已收尾的連結顯示既有的 `group_disbanded` 畫面，文字依 `group_kind` 換成「這場快速比賽已結束」（FR-023、US5 情境 4）。
  - sweep 的條件拆成兩段：`kind='normal'` 維持 60 分鐘；`kind='quick'` 用 `system_config.quick_session_idle_minutes`，預設 **60**（使用者於 2026-09-22 決定與一般團相同；規格 FR-022 已同步）。仍獨立成一個 `system_config` 鍵而不直接共用設定檔的 `auto_disband_idle_minutes`，是因為 FR-022 要求它可在系統共用設定中調整、且日後可與一般團分開調。
  - 快速比賽的每個動作端點都 `_touch_activity()`。
- **Rationale**：不新增排程工作、不新增狀態欄位——「已收尾」就是 `status='disbanded'`。
- **FR-020 的自動收尾**：`_raise_if_active_elsewhere()` 找到的 active 團若 `kind='quick'` 且沒有 `in_progress` 的比賽 → 透過注入的 hook 呼叫 `quick_match.service.close_quick_session()`（內部即 `disband_group()`）後放行；有比賽進行中 → 照舊拋 `ALREADY_ACTIVE_IN_ANOTHER_GROUP`，`detail` 加 `group_kind` 讓前端換提示文字。

## Decision 7：前端以 `group_kind` 換標籤，不改任何既有回應的欄位語意

- **查證**：`CourtByTokenResponse`／`CourtStateResponse` 今天不回團名也不回 kind；對戰紀錄與分享卡的活動名稱來自 `MemberMatchRecordSummary.group_name`（`member/service.py:1261` 從 `groups.name` 填）；分享卡在 `share-card-renderer.ts:101` 畫 `model.groupName`。通知型別→路由的唯一對應點是 `notification-list.component.ts:43` 的 `open()`。
- **Decision**：
  - by-token 兩個回應、`MemberMatchRecordSummary`／`Detail`、好友對戰紀錄、團戰績（`MemberGroupHistoryResponse`）、`MyGroupSummary`、`GroupInviteDetail` 各**新增** `group_kind: 'normal' | 'quick'`（具預設值、舊欄位不動）。`group_name` 對快速比賽仍回存的後備值，但前端一律以 `kind` 判斷顯示 `quickMatch.label`（zh-TW「快速比賽」／en「Quick match」），分享卡的 `groupName` 也在 model 轉換時換成該語系標籤（FR-017）。
  - 對戰紀錄與統計分析的篩選新增 `group_kind` 查詢參數（沿用 `match_mode` 篩選 join `Group` 的寫法）。
  - `GET /groups`（`list_groups()` 的基礎條件）與 `get_my_groups()` 預設排除 `quick`；後者加 `include_quick` 參數供 FR-019 的篩選。
  - 通知 `quick_match_invite` 在 `open()` 導到既有的 `group-invites/:inviteId` 頁；該頁依 `group_kind` 換文字（「XX 邀請你打一場快速比賽（單打）」）、接受後導到回應裡的計分板連結而非成員視圖。
- **Rationale**：i18n（Constitution VIII）——標籤在語系檔，不從後端字串推斷；既有回應只加欄位、零破壞。

## Decision 8：前端結構——一個新 feature、三個既有畫面的小分支

- **Decision**：
  - 新 `features/quick-match/`：`quick-start/`（表單＋等待畫面同一元件，以狀態切換；路由 `quick-match/new`）、`quick-match.service.ts`（API）、`quick-match.models.ts`、`quick-actions/`（控制板內嵌的「再打一場／換人再打／結束」與等待中名單的子元件）。
  - 控制板（`control-panel.component`）：`group_kind === 'quick'` 時隱藏輪次列與 `next_up`、`current_match` 為空的等待訊息位置改渲染 `<app-quick-actions>`，並多訂閱 `quickMatch.lineupChanged`。
  - 計分板：隱藏輪次、標題顯示 `quickMatch.label`。
  - 首頁：`home__actions` 新增「快速開始比賽」CTA（登入與否皆顯示）；登入會員另呼叫 `GET /members/me/quick-session` 顯示「你有一場進行中的快速比賽」橫幅（FR-021）。
  - 表單重用 `create-group` 的 `customScoringValidator` 與 `TurnstileWidgetComponent`、`GroupJoinService.getActiveGuestGroupId()` 的訪客「已在別團」前置檢查；好友挑選重用 `GET /friends` 的清單（不重用管理頁的邀請分頁，那是 admin token 授權）。
- **Rationale**：路由無守衛、元件內自行判斷登入狀態（既有慣例）；控制板已有 `frozenState` 機制，插入子元件不影響落點挑選視窗。

## Decision 9：測試策略

- 純函式（無資料庫）：`swapped_lineup()`、位置狀態機（全部 ready 才開賽、逾時轉訪客、轉換後不可再接受）、sweep 的期限選擇。
- 經資料庫的單元／契約測試：建立（會員／訪客、單打／雙打、含好友／不含好友、Turnstile 失敗、已在別團、驗證錯誤不留資料）、接受／拒絕／逾時／不等了、好友在別團視同拒絕、再打一場換邊與連結不變、換人再打（含本人不可移除、新好友再接受）、結束與取消、by-token 授權（計分板 token 一律 `LINK_NOT_FOUND`、一般團一律 `QUICK_SESSION_ONLY`）、列表與我的團的排除、對戰紀錄的 `group_kind` 欄位與篩選、sweep 兩種期限。
- 整合測試：「快速開始 → 計分到 21 → 再打一場 → 換人再打（挑好友→接受）→ 結束 → 對戰紀錄雙方可見、分享卡標籤、已收尾連結顯示」一條完整流程（Constitution II）。
- 前端：`ng test` 涵蓋表單驗證（人數依模式、同名、好友重複）、等待畫面狀態切換、控制板 quick 分支、通知路由、標籤替換；`ng lint`、`ng build`（與 `origin/ut` 的警告數相同）。
