# Research: 從對戰紀錄／即時戰況頁面加好友

> **實作後調整（2026-09-14）**：#1 決策原本讓 `build_schedule_snapshot()`
> 在「目前進行中比賽」（`MatchSummary.participants`）填入 `member_id`，供
> 賽程頁/管理頁場地控制區塊的即時比分顯示旁加好友。使用者事後要求將
> 「加好友」入口改放到輪替名單（涵蓋所有現役團員，不限於正在比賽中），
> 管理頁並改為圖示樣式。因此 #1 的落點改為 `build_schedule_snapshot()`
> 尾端組出 `roster_statuses`（`RosterScheduleStatus`）那段迴圈，
> `MatchSummary.participants`／`NextUpPreview.participants` 的
> `ParticipantSummary.member_id` 則完全不再填入（改回恆為 `None`，等同
> `court_live_state()`/`_match_participants_payload()` 的既有行為）。
> 「公開路徑/Ably payload 絕不外洩」這條核心邊界不變，只是「安全落點」從
> `ParticipantSummary`（比賽參與者）換成 `RosterScheduleStatus`（輪替名單
> 項目）——兩者本來就是 `build_schedule_snapshot()` 回傳的 `ScheduleResponse`
> 之下兩個獨立欄位，`roster` 從未被任何公開端點消費。下方 #1 原文保留
> 供歷史對照，實際程式碼請見
> `apps/api/app/domains/schedule/service.py`/`schemas.py` 現況。

## #1（原始決策，部分已由上方調整取代）`member_id` 只在三個既授權路徑填入，公開路徑與 Ably payload 完全不變

**Decision**：`ParticipantSummary`（`app/domains/schedule/schemas.py`）新增
`member_id: str | None = None`（安全預設 `None`）。只在下列三個「本來就
需要登入/管理員驗證」的既有查詢路徑填入真實值：

1. `schedule/service.py` 的 `build_schedule_snapshot()`——「目前進行中比賽」
   那段查詢（目前只 `select(Match, MatchParticipant, RosterEntry.nickname)`，
   改為一併 `select(..., RosterEntry.member_id)`）。此函式同時餵給
   `GET /{group_id}/member-schedule`（FR-001c，一般成員賽程頁）與
   `GET /groups/{group_id}/schedule`（FR-001d，管理頁——已確認管理頁前端
   `CourtControlComponent` 是透過 `ScheduleService.getSchedule()` 呼叫此
   端點，不是走 007 的公開 token 端點），一次改動同時滿足兩個 FR。
2. `group/service.py` 的 `_build_match_record_summaries()`（FR-001b，團內
   對戰紀錄）。
3. `member/service.py` 的 `_build_member_match_record_summaries()`
   （FR-001a，跨團對戰紀錄）——`build_member_match_records()` 內部呼叫的
   私有摘要建構函式，實際組出每筆 `ParticipantSummary` 的地方；與
   `group/service.py` 的 `_build_match_record_summaries()`/
   `build_group_match_records()` 屬同一種「公開端點函式 + 私有摘要建構
   函式」拆分模式，此處填入 `member_id` 的目標是後者（私有函式），不是
   `build_member_match_records()` 本身。

**明確不變動**（回歸測試需覆蓋）：

- `schedule/service.py` 的 `_match_participants_payload()`——這是
  `court_live_state()`（docstring 明載「供公開 `GET .../state` 端點與…
  共用」）與 `_publish_rotation_updated()`（Ably `rotation.updated` 事件
  payload，任何訂閱該公開頻道的匿名計分板/控制板前端都能收到）兩者共用
  的唯一資料來源。若在此填入 `member_id`，會直接繞過 FR-013 的邊界——即使
  前端刻意不渲染按鈕，`member_id` 本身已經外洩到一個完全匿名、可能被
  分享出去的 URL／WebSocket payload 上，這正是 US3（新增獨立隱私開關）想
  保護的那件事被開一個後門。
- `schedule/service.py` 的 `build_round_matches_list()`（管理頁「本輪賽程
  清單」，`RoundMatchSummary`）——spec FR-001(d) 明確限定「場地控制區塊」
  （`CourtControlComponent`／`current_match`），不是這個顯示全輪次（含
  排隊中/已捨棄）比賽的獨立清單元件；不擴大 spec 未點名的範圍。
- `NextUpPreview` 的任何建構點——FR-011 已明訂排隊中的預告名單一律不顯示
  入口，不需要 `member_id`。

**Rationale**：`ParticipantSummary` 是一個被 8+ 處呼叫點共用的型別，若不
先釐清「誰的資料流最終流向匿名可存取的 URL」，直接加欄位有很高機率無聲地
繞過 FR-013——這正是憲章原則 IV「無需驗證即可開啟的畫面 MUST NOT 提供
管理員專屬操作」精神的延伸（本 feature 進一步收斂為「連 member_id 本身
都不該出現」，因為那正是新隱私開關要保護的資訊）。加一個預設 `None` 的
可選欄位、只在三個明確、已通過身分驗證的建構點填值，是風險最小、改動面
最小的做法。

**Alternatives considered**：

- 為賽程頁/管理頁另外設計一套獨立型別（不共用 `ParticipantSummary`）——
  拒絕：會讓 `ScheduleResponse`/`CourtScheduleStatus`/`MatchSummary` 整條
  既有型別鏈全部要分叉一份，改動面遠大於「加一個預設 None 的欄位」，且
  未來任何人維護時仍要記得兩套型別要同步欄位，維護成本更高。
- 直接在 `_match_participants_payload()` 也加 `member_id`，靠前端「不渲染
  按鈕」把關——拒絕：後端資料一旦序列化到公開回應/公開 Ably 頻道就已經
  外洩，前端渲染與否只是畫面呈現層級的把關，無法補救資料層級的洩漏，
  違反「後端為唯一可信邊界」的最小權限原則。

## #2 批次好友關係狀態＋邀請資格查詢，避免逐列 N+1

**Decision**：新增 `POST /friends/invite-candidates`，request body
`{"member_ids": ["<uuid>", ...]}`（去重後的清單，通常一頁列表可見人數，見
Scale/Scope），回應對每個 id 回傳
`{member_id, friendship_status, invite_eligible}`——`friendship_status`
直接重用既有 `get_friendship_status()`（四態：`none`/`friends`/
`pending_outgoing`/`pending_incoming`）；`invite_eligible` 為
`friendship_status == "none"` 且目標
`allow_friend_invite_from_match_pages == true` 且目標為現役已驗證會員時
才是 `true`（Guest/非會員不會出現在請求清單中——前端一開始就只對有
`member_id` 的參與者發起查詢）。前端新元件 `AddFriendButtonComponent`
所在的四個整合點頁面，各自在載入資料後收集畫面上出現的（去重、排除自己）
`member_id` 清單，呼叫這一支端點一次，而不是每個按鈕各自呼叫一次。

**Rationale**：對戰紀錄/賽程頁一次可能同時顯示數十位不同參與者的名字，若
每個「加好友」按鈕各自呼叫一次既有 `GET /members/search` 之類的端點來判斷
目前關係狀態，會造成明顯的 N+1 請求量；且既有 `GET /members/search` 是
「以 user_number 搜尋」語意，不適合被重新解讀為「以 member_id 查狀態」。
獨立一支批次端點，語意清楚、效能可控，且不需要更動任何既有搜尋端點的
行為。

**Alternatives considered**：

- 直接把 `friendship_status`/`invite_eligible` 塞進三個既有 match-records
  /schedule 回應本身（例如 `ParticipantSummary` 再加兩個欄位）——拒絕：
  這些既有 builder 函式（`build_group_match_records`/
  `build_member_match_records`/`build_schedule_snapshot`）目前皆與「呼叫者
  是誰」弱耦合或無耦合（管理頁的 `ScheduleResponse` 甚至不特別區分是哪個
  admin 在看），硬塞入一個「相對於當前登入者」的欄位，會讓這些已經頗複雜、
  已有完整測試覆蓋的既有函式多一個新的耦合維度，改動風險與測試回歸範圍
  遠大於新增一支獨立、單純的查詢端點。
- 每個按鈕元件各自呼叫（不批次）——拒絕：N+1，且 SC-001「3 次點擊內送出
  邀請」的體感速度會被大量並發請求拖慢。

## #3 以 member_id 直接送出邀請——重構既有 `create_friend_request()` 抽出共用核心

**Decision**：新增 `POST /friends/requests/by-member`，body
`{"addressee_member_id": "<uuid>"}`。後端將 `friend/service.py` 現有的
`create_friend_request()` 拆成：

- 一個共用的核心函式（例如 `_create_friend_request_for_addressee(session,
  requester_id, addressee: Member)`），涵蓋「檢查目標存在且已驗證且未刪除、
  不可邀請自己、查詢現有關係狀態、建立 `FriendRequest`、建立通知、處理
  `IntegrityError`」等既有邏輯——完全不變動任何既有行為。
- 既有 `create_friend_request()`（by `user_number`）改為「先用
  `user_number` 查出 `Member`，再呼叫共用核心」。
- 新增 `create_friend_request_by_member_id()`（by `member_id`）：「先用
  `member_id` 查出 `Member`，多一道 FR-006~010 要求的新檢查——目標的
  `allow_friend_invite_from_match_pages` 若為 `false` 且雙方目前無好友
  關係/待處理邀請，拋出新錯誤碼 `INVITE_VIA_MATCH_PAGES_NOT_ALLOWED`（409）
  ——再呼叫同一個共用核心」。

**Rationale**：FR-005 明訂「MUST 使用與既有搜尋加好友功能完全相同的邀請
建立、重複發送防呆、拒絕後可重新發送等規則，不建立獨立的另一套邀請
機制」——抽出共用核心、只在「怎麼找到 `Member`」與「多一道新隱私開關檢查」
兩點分岔，是滿足這條約束最直接的做法，同時完全重用既有錯誤碼
（`MEMBER_NOT_FOUND`/`CANNOT_FRIEND_SELF`/`FRIEND_REQUEST_ALREADY_PENDING`/
`ALREADY_FRIENDS`）與其既有 i18n 翻譯（`zh-TW.json`/`en.json` 的 `errors`
物件已存在，不需新增，見 plan.md Constitution Check 原則 VIII）。

**Alternatives considered**：

- 讓前端自己「先查 user_number 再呼叫既有端點」——拒絕：對戰紀錄/賽程頁的
  回應目前只帶 `nickname`（顯示用，可能重複/非唯一），不會也不該帶
  `user_number`（那是帳號識別碼，屬於個人設定頁刻意才顯示的資訊，見
  006 spec）；用 `member_id`（本來就已經是這些回應內部的資料庫外鍵）直接
  定位，才是正確、最小曝露的作法。
- 完全獨立一套邏輯（不重構既有函式，直接複製貼上再改）——拒絕：違反
  FR-005「不建立獨立的另一套邀請機制」的精神，且日後兩套邏輯容易走鐘
  （例如其中一套忘記同步套用新的防呆規則）。

## #4 新隱私欄位命名與遷移——直接沿用 022 既有兩欄位的慣例

**Decision**：`members` 表新增 `allow_friend_invite_from_match_pages
BOOLEAN NOT NULL DEFAULT true`，型別、預設值、Alembic migration 檔案命名
風格（`<rev>_<snake_case 描述>.py`）完全比照 `allow_search`/
`share_match_records_with_friends` 兩個既有欄位（同樣由 022 引入）。

**Rationale**：FR-007「此新設定 MUST 預設為開啟」與 022 既有兩項隱私設定
「預設開啟，不因新功能上線被動改變既有會員曝光狀態」的一貫原則完全一致，
沒有理由用不同的技術實作方式；沿用既有慣例也讓 `PrivacySettingsRequest`/
`PrivacySettingsResponse` 的擴充是機械性的「照抄現有兩欄位的寫法加第三
欄位」，改動風險最低。

**Alternatives considered**：獨立一張「隱私設定」表——拒絕：spec Key
Entities 明確定位這是既有「隱私設定」實體新增的一個欄位，且 022 當初已經
決定直接掛在 `members` 表上（而非獨立表），三個欄位性質完全相同，沒有
理由這次改變資料模型形狀。

## #5 前端：新增一個共用元件，四個整合點重用

**Decision**：新增 `apps/web/src/app/shared/add-friend-button/
add-friend-button.component.ts`，接受 `memberId: string` 與（可選）
已知的 `friendshipStatus`/`inviteEligible`（讓呼叫端可以先用批次查詢結果
餵入，元件本身不強制自己發請求，允許父層批次查詢後逐一傳入，避免元件
自己各自呼叫造成 N+1，呼應 research.md #2）。元件本身只負責三態渲染
（可點擊的「加好友」按鈕／既有關係狀態標籤，重用既有 `friends.
pendingOutgoing`/`pendingIncoming`/`alreadyFriends` i18n key／送出中狀態）
與送出後的樂觀狀態更新（比照既有 `friend-add.component.ts` 送出成功後
`result.set({ ...target, friendship_status: 'pending_outgoing' })` 的既有
模式）。四個整合點（`match-history`/`group-member-view/match-records`/
`member-schedule`/`group-admin` 的 `court-control`）的模板各自負責：（a）
從各自既有的 `ParticipantSummary`/`MatchRecordSummary` 資料中收集
`member_id` 清單、呼叫批次查詢端點，（b）用 `@if (participant.member_id
&& participant.member_id !== currentMemberId())` 條件式決定是否渲染這個
共用元件（FR-002/FR-003 的 Guest/自己一律不顯示，在呼叫端而非元件內部
把關，元件本身可以假設「有拿到 memberId 就代表值得顯示」）。

**Rationale**：呼應 Constitution VI（可維護性/模組化）——四個整合點的
「按鈕/標籤三態渲染＋送出＋樂觀更新」邏輯完全相同，唯一差異只是「這個
member_id 從哪個既有回應欄位讀出來」，集中成一個共用元件可避免四份幾乎
相同的程式碼各自維護、各自可能出現不一致的行為（例如其中一處忘記套用
FR-012 的換場後更新規則）。

**Alternatives considered**：四個整合點各自實作——拒絕，見上。
