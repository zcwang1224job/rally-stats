# Research: 訪客即時戰況頁面建立帳號並綁定戰績

## #1: 訪客連結的「綁定資格查詢」不能沿用既有 `resolve_guest_session()`

**Decision**: 新增一個獨立的、寬鬆的查詢函式/端點（暫名
`resolve_guest_binding_target()` / `GET /groups/guest-token/{token}/binding-status`），
只要求 `guest_session_token` 存在即可查到對應的 `RosterEntry`，**不**檢查
該筆 `RosterEntry.status`（active/left/kicked 皆可）也**不**檢查所屬
`Group.status`（active/disbanded 皆可），只有 token 本身查無資料（含被
管理員重新產生後失效的舊 token）時才回傳 `LINK_NOT_FOUND`。既有
`resolve_guest_session()`（`app/domains/group/service.py:837-854`，
`GET /by-guest-token/{token}`）維持完全不變。

**Rationale**：既有 `resolve_guest_session()` 是「把訪客導向目前仍在
進行的即時賽況頁」這個用途設計的，因此刻意要求 active RosterEntry +
active Group——對「訪客已被踢出/已離場/團已解散後仍要能綁定歷史戰績」
這個新用途（spec FR-004、Acceptance Scenario 4/5）而言，這個限制反而是
需要繞過的門檻，而不是可以重用的既有邏輯。兩個查詢的「查無資料」語意
完全不同：前者「查無資料」代表「你現在不能進來看直播」，後者「查無
資料」代表「這個連結從未存在或已被作廢」，混用同一個函式會讓其中一種
用途被迫遷就另一種的語意。

**Alternatives considered**：直接放寬 `resolve_guest_session()` 本身的
篩選條件——拒絕，因為這會同時放寬「訪客導向即時賽況頁」這個既有、與本
feature 無關的既有行為的存取邊界（例如讓已被踢出的訪客又能重新導向進入
即時賽況頁面，這不是本 feature 的範圍，也可能與踢人功能的既有預期行為
衝突）。

## #2: 綁定端點的四種路徑統一為單一端點，用既有 `optional_member` 分流

**Decision**：新增 `POST /groups/guest-token/{token}/bind`，以
`Depends(security.optional_member)` 取得 `current_member: Member | None`：

- `current_member` 不為 `None`（Clarifications 2026-09-15 已登入路徑，
  FR-012）：忽略 request body 的帳號建立/登入欄位，直接以
  `current_member.id` 執行綁定。
- `current_member` 為 `None` 且 body 帶 `mode: "register"`（US1）：呼叫
  既有 `verify_turnstile_token()`（XI，比照既有註冊端點）→ 既有
  `register()` 建立會員（`verification_status` 維持既有的
  `unverified` 預設值，不因此入口特殊放寬）→ 直接以新會員的
  `id`/`token_version` 呼叫既有 `issue_access_token()`/
  `issue_refresh_token()`（不重新呼叫 `login()` 再驗證一次密碼，避免
  多餘的一次資料庫往返與密碼再驗證）→ 執行綁定 → 回傳新 token 對。
- `current_member` 為 `None` 且 body 帶 `mode: "login"`（US2）：呼叫既有
  `login()`（回傳 `(member, access_token, refresh_token)`）→ 執行綁定
  → 回傳既有 token 對。

**Rationale**：`optional_member`（`security.py:202-217`）本來就是為
「登入是加分而非必要」的端點設計（既有 group 瀏覽/加入端點已用同一個
dependency），語意上與 Clarifications 2026-09-15 的決策（已登入時一鍵
用目前 session、未登入時才需要帳號建立/登入）完全吻合，不需要新增
分流用的 dependency。綁定端點本身刻意使用 `require_member`
等級（透過新建立/新登入取得的 token 一定滿足）而非
`require_verified_member`——帳號建立/登入這一刻本來就可能仍是
`unverified`（沿用既有「帳號建立後可先登入、僅看到驗證提示，其餘功能
才鎖定」的既有原則），此端點只是「把一筆訪客名冊身份指向這個帳號」，
屬於帳號建立/登入動作本身的直接延伸，比照 Guest 使用不受驗證鎖定影響的
既有精神，不應該因為新帳號尚未完成 Email 驗證而擋下綁定這個動作本身。

**Alternatives considered**：拆成四個獨立端點——拒絕，四條路徑除了
「怎麼取得 `member_id`」不同之外，「用這個 `member_id` 執行綁定」的
核心邏輯完全一樣，拆開只會讓併發防護（#3）與交易邊界要在四個地方各自
正確實作一次，增加出錯面。

## #3: OAuth 綁定路徑——延伸既有 `state` JWT，不新增第二套交握

**Decision**：`OAuthState`（`security.py:118-129`）、`issue_oauth_state()`、
`OAuthCallbackResult`（`service.py:154-167`）三處新增一個可選欄位
`bind_guest_token: str | None = None`。`GET /auth/oauth/{provider}/start`
在 `intent=login` 時新增一個可選 query 參數 `bind_guest_token`，原樣寫入
`state`。`complete_oauth_callback()` 在既有登入/建帳號成功的分支之後，
若 `oauth_state.bind_guest_token` 有值，額外執行與 #2 相同的綁定步驟
（同一筆資料庫交易內完成，`OAuthCallbackResult` 新增
`bound_group_id: str | None` 欄位回傳綁定結果所屬的 `group_id`）。router
層 `_oauth_callback_redirect_url()` 的 `status=success` 分支，於
`bound_group_id` 有值時在 URL fragment 多帶一個
`bound_group_id=<id>` 參數；既有前端 `/auth/oauth-callback` 落地頁
（`oauth-callback.component.ts`）讀到這個參數時導向
`/groups/<id>/member-view`（或依 #4 決定的實際落地路由），否則維持
現有預設導向行為完全不變。

**Rationale**：`state` 本來就是為了「讓交握前後兩端不需要伺服器端存放
狀態、又能安全帶一些交握前就決定好的意圖參數回來」設計的簽章 JWT
（027 research.md #2），新增一個欄位是這個既有機制設計上就預期會發生的
擴充方式，而不是引入新概念；比照 `member_id`（`intent=link` 用）已經是
「交握前決定、交握後才用得到」的同類欄位。若改成另開一條與 Email/密碼
路徑完全獨立的 OAuth 綁定專用流程，會違背 027 established 的「OAuth 的
最終行為與既有 Email／密碼流程殊途同歸、不引入第二套並存機制」的既有
決策精神。

**Alternatives considered**：綁定完成後導回一個通用的「請重新整理原本
分頁」提示頁，而不精準導回原本的即時戰況頁面——拒絕，會直接違反 spec
FR-007「不中斷、不需重新導覽」的明確要求。

## #4: 並發安全（FR-006）——單一條件式 UPDATE，不用悲觀鎖

**Decision**：綁定的資料庫寫入用
`UPDATE roster_entries SET member_id = :member_id WHERE id = :roster_entry_id AND member_id IS NULL`
這種條件式 UPDATE，檢查受影響 row 數：等於 1 視為綁定成功；等於 0
代表「已經被別的請求先綁定過」，回傳 `ROSTER_ENTRY_ALREADY_BOUND`
錯誤（若是同一個帳號重複點擊造成的 0 rows，前端依既有 idempotent
重試慣例處理，不視為錯誤畫面）。

**Rationale**：這個條件式 UPDATE 本身就是原子操作，不需要額外的
`SELECT ... FOR UPDATE` 悲觀鎖或應用層鎖，寫法與 027 research.md 對
`member_oauth_identities` 兩條 UNIQUE 約束「資料庫唯一索引本身是最終
防線」的既有精神一致——用資料庫的原子性保證正確性，而不是在應用層
用時間窗更短但仍有競態可能的「先查後寫」兩步驟。

## #5: 前端渲染位置——依訪客連結目前是否仍「現役」分兩種畫面

**Decision**：
- `GuestAccessComponent`（`guest-access.component.ts`）的初始化邏輯，
  改為優先呼叫新的 `binding-status` 查詢（#1）而非直接呼叫既有
  `resolveGuestSession()`。
  - 若回應顯示「已綁定」→ 導向既有登入頁（並帶上一個提示：這個連結已
    綁定過帳號，請登入查看）。
  - 若回應顯示「尚未綁定，且目前仍是現役（roster active 且 group
    active）」→ 沿用既有行為：呼叫既有 `resolveGuestSession()` 導向
    `GroupMemberViewComponent`；該元件新增一個小型、獨立的
    `GuestBindingCta` 子元件，讀取本機保存的
    `guest_session_token`（既有機制已在 `GuestAccessComponent` 完成
    「seed 本機狀態」這一步）與「尚未綁定」旗標，在畫面頂端顯示 FR-001
    的入口，成功後不離開這個畫面（FR-007）。
  - 若回應顯示「尚未綁定，且已非現役（roster left/kicked 或 group
    disbanded）」→ 不導向 `GroupMemberViewComponent`（該元件是為現役
    即時檢視設計，讀取的既有 `getGroupPublic()` 對已解散團的行為未經
    本次調查確認，不假設它能正確呈現非現役情境），改由
    `GuestAccessComponent` 自己渲染一個輕量的「個人戰績摘要」畫面
    （團名、暱稱、FR-001 的入口），同樣使用同一個
    `GuestBindingCta` 子元件。

  **命名澄清**（/speckit-analyze 2026-09-15 remediation，finding
  C1）：「現役／非現役」這個分流軸線判斷的是**這筆訪客名冊身份**當下是
  否仍是該團輪替名單的一員（`RosterEntry.status == active` 且所屬
  `Group.status == active`），**不是**「這個團的活動整體是否已經結束」
  ——一個仍在進行中、對其他團員而言活動正熱烈進行的團，這位訪客仍可能
  因為已離場或被踢出而落在「非現役」這一格。因此這個畫面刻意命名為
  「個人戰績摘要」而非「已結束摘要」，文案與實作 MUST NOT 假設或顯示
  「本團已結束」這類語意，避免在團仍活躍時對這位訪客顯示錯誤的訊息。

**Rationale**：`GuestBindingCta` 抽成一個獨立、不含頁面骨架的小元件，
讓「現役即時檢視」與「個人戰績摘要」兩種外殼可以各自重用同一份綁定 UI/
邏輯（呼叫 #2 端點、依 `optional_member` 對應的登入狀態切換文案，即
Clarifications 2026-09-15 的入口文字規則），符合原則 VI（模組化、避免
重複實作同一段商業邏輯）。刻意不去改動或假設 `GroupMemberViewComponent`
對非現役情境的既有行為，是為了不在沒有調查清楚既有行為的前提下，冒然
擴大既有元件的職責範圍。

**Alternatives considered**：所有情境一律導向 `GroupMemberViewComponent`
——拒絕，因為已解散/已離場情境下該元件目前的既有行為未經確認，貿然假設
它「應該也能動」有引入既有功能迴歸的風險；比起確認清楚，不如新增一個
職責單純的輕量摘要畫面。

## #6: 即時性（原則 III/X）——不新增 Ably 即時事件

**Decision**：綁定完成後 MUST NOT 額外新增一個 Ably 事件廣播「這筆
名冊身份已綁定」。CTA 是否顯示，只在每次載入/重新載入該畫面時透過 #1
的查詢即時反映當下狀態（spec Acceptance Scenario 3 的「之後再次開啟」
本來就是描述「重新開啟」而非「另一個分頁即時同步」）。

**Rationale**：spec 沒有任何一條 acceptance scenario 要求「同一筆名冊
身份被綁定後，另一個當下開著同一個連結的分頁要即時反映」，強行加一個
新的即時事件類型是超出 spec 範圍的過度設計；且這個 CTA 本來就只對
「持有這個連結的那個人」有意義，多分頁同時開啟本身已經是邊緣情境
（Edge Cases 已涵蓋「同一人開兩個分頁」，用 #4 的並發防護即可正確處理，
不需要即時通知）。

## #7: 防機器人（原則 XI）——僅 `mode: "register"` 路徑要求 Turnstile

**Decision**：綁定端點只有 `mode: "register"`（建立新帳號）這條路徑
呼叫既有 `verify_turnstile_token()`；`mode: "login"`、已登入一鍵綁定、
OAuth 三條路徑皆不要求 Turnstile token。

**Rationale**：直接沿用既有原則 XI 與 027 已確立的既有慣例——Turnstile
只掛在「建立新資源」（此處是「建立新會員帳號」）這個動作上，登入本身
從未要求過 Turnstile；OAuth 授權流程本身已被 027 認定「已具備等同
Turnstile 的防自動化機器人保護」，此 feature 沿用同一個既有結論，不
重複要求。
