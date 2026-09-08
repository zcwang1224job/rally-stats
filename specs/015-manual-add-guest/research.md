# Research: 團長手動新增訪客入團

沒有 spec 留下的 `[NEEDS CLARIFICATION]` 標記——`/speckit-clarify` 已確認
無需強制澄清。以下是規劃階段確認的技術決策，皆基於對現有程式碼的實際
檢查（非假設）。

## #1：新增訪客的核心邏輯，直接重用 `join_group()`

**Decision**：新端點的 handler 直接呼叫既有
`group.service.join_group(session, group, member=None, password=None,
nickname=nickname, skip_password=True)`，不新寫任何平行的「建立訪客
RosterEntry」邏輯。

**Rationale**：檢視 `apps/api/app/domains/group/service.py:642-747` 的
`join_group()` 實作後確認，它已經是「訪客建立」的唯一寫入路徑，內含：
已解散團擋下（`GROUP_DISBANDED`）、人數上限的 atomic conditional update
（`UPDATE ... WHERE current_member_count < max_members`，避免併發搶名額，
直接滿足 spec FR-010）、暱稱驗證（1–20 字，`NICKNAME_REQUIRED_FOR_GUEST`）、
`RosterEntry(member_id=None, status="active", wait_count=None,
guest_session_token=secrets.token_urlsafe(32))` 建立、排點掛勾
（`handle_member_joined`）、即時通知廣播（`publish(..., "member.joined",
...)`）。且它已經有 `skip_password: bool = False` 這個 keyword-only 參數
——這是 013-group-invite-friends 為「邀請連結免密碼」新增的既有安全擴充
（見該函式 docstring：「an invite is itself the creator's per-friend
authorization，the invitee never needs to know or enter the group's
password」）。管理員手動新增的語意與此完全一致：「管理員的授權」本身就
足以取代「知道密碼」，不需要另外驗證密碼或新增第三種授權邏輯。

**Alternatives considered**：
- 另寫一個 `admin_add_guest()` service 函式，內部重複人數上限/暱稱驗證
  邏輯——違反憲章原則 VI（可維護性/模組化：MUST NOT 依賴跨模組的內部
  實作細節或重複邏輯），且會產生兩套「訪客建立」邏輯未來容易失步的風險
  （例如日後暱稱驗證規則改變，只改到一處）。已否決。
- 讓 `join_group()` 內部依「呼叫者是否為 admin」分支——不必要，現有
  `skip_password` 參數已足以表達本功能所需的行為差異，不需要新增分支
  條件。

## #2：新端點的授權模式，比照 `kick_member` 的 `require_admin` + 交叉比對

**Decision**：新端點 `POST /groups/{group_id}/members` 使用
`Depends(require_admin)` 取得 `Group` ORM 物件，並比照
`apps/api/app/domains/schedule/router.py:162-180`（`kick_member`）的既有
模式，明確檢查 `if group.id != group_id: raise ApiError("ADMIN_TOKEN_INVALID",
status_code=401)`——不信任路徑參數本身，一律以 token 解出的 `group` 為準。

**Rationale**：`require_admin`（`apps/api/app/domains/group/security.py:79-97`）
注入的是已解碼驗證過的 `Group` 物件，而不只是一個 ID；`kick_member` 已經
證明這是本專案既有的「路徑參數 vs token 內容」交叉比對慣例，沿用它可以
避免在新端點重新設計一套授權檢查方式，符合憲章原則 IV「不同安全等級
不得混用同一套機制」的反面陳述——同一安全等級（管理員動作）則應該用
同一套機制，不要各自發明。

**Alternatives considered**：改用 member-based 驗證（會員登入）——否決，
因為本系統的團管理動作（開團、踢人、改設定）一律走 `admin_token`，與
「這個團是誰建立的」（member-created 或 guest-created）無關；本功能沒有
理由打破這個既有邊界。

## #3：US2 的個人查看連結，前端零新增後端查詢、重用既有 `resolveGuestSession()`

**Decision**：後端新端點的回應直接沿用既有 `JoinGroupResponse`
（已包含 `guest_session_token`），不需要額外欄位或新端點。前端新增一個
路由 `guest-access/:token`（`GuestAccessComponent`），行為：讀取路徑參數
`token` → 呼叫既有 `GroupJoinService.resolveGuestSession(token)`（打既有
`GET /groups/by-guest-token/{token}`）解出 `group_id` → 呼叫既有
`setGuestSessionToken(group_id, token)` 寫入 localStorage → 導向既有
`/groups/:groupId/member-view`。

**Rationale**：檢視 `apps/web/src/app/features/group-join/group-join.service.ts:83-85`
確認 `resolveGuestSession()` 與其背後的 `GET /groups/by-guest-token/{token}`
端點（`apps/api/app/domains/group/router.py:454-465`）**已經存在**——
目前只被 `group-member-view.service.ts`（同瀏覽器復原 session）與
`join-flow.component.ts`（重新載入頁面時驗證已存的 token 是否還有效）
呼叫，用途是「同一台裝置、同一個瀏覽器的 session 復原」。本功能是它
第一次被用於「跨裝置分享」情境——語意完全相容（都是「用一個
`guest_session_token` 換回這個訪客在哪個團、叫什麼暱稱」），不需要修改
這個既有端點的行為，只需要在前端新增一個「進入點元件」把它接到一個可
公開分享的 URL 上。這與既有 `join/:token`（`GroupJoinComponent`，
`apps/web/src/app/features/group-join/group-join.component.ts`）走
「解析 token → 導向下一步」的元件結構完全一致，是同一種設計模式的第二個
應用，不需要發明新模式。

**Alternatives considered**：
- 讓後端在新增訪客時額外組好完整分享 URL 回傳——否決，`window.location.origin`
  屬於前端執行環境資訊，後端組 URL 會讓 API 回應綁死一個特定的前端網域，
  且既有 `court-link-card.component.ts`／`admin-page.component.ts` 的
  join-link QR 皆已是「前端組 URL、後端只給 token」的既有慣例
  （`${origin}/join/${token}`、`${origin}/scoreboard/${token}`），沿用一致
  即可。
- 新增一個專門的「訪客存取連結」後端端點——否決，`by-guest-token` 端點
  已經做了完全一樣的事（token → 該訪客的 `group_id`/`nickname`），沒有
  理由重複實作。

## #4：QR code／複製連結 UI，重用既有 `QRCodeComponent` + `copyTextToClipboard` 模式

**Decision**：管理頁新增訪客成功後顯示的分享區塊，直接重用
`court-link-card.component.ts` 與 `admin-page.component.ts` 既有 join-link
區塊已經在用的 `angularx-qrcode` 的 `QRCodeComponent` 與
`copyTextToClipboard` 工具函式，URL 格式沿用既有慣例（origin + path
segment token，例如 `${origin}/guest-access/${guest_session_token}`）。

**Rationale**：這是既有元件與既有 URL 設計慣例的直接重用，不需要引入
新套件、不需要設計新的 URL scheme。

## #5：錯誤碼全部重用既有代碼，不新增

**Decision**：新端點的所有錯誤情境（額滿、已解散、暱稱不合法、
`group_id` 與 token 不符）皆直接重用既有 `ApiError` 代碼：
`GROUP_FULL`（409，來自 `join_group()` 內部的 atomic update 失敗分支）、
`GROUP_DISBANDED`（409，`join_group()` 內部既有檢查）、
`NICKNAME_REQUIRED_FOR_GUEST`（400，`join_group()` 內部既有檢查）、
`ADMIN_TOKEN_INVALID`（401，比照 `kick_member` 的路徑/token 交叉比對）。
不新增任何錯誤碼。

**Rationale**：`ApiError` 是全域統一的 `error_code` + `status_code` 機制
（`apps/api/app/core/errors.py:10-51`），前端一律透過 `error.i18nKey`
（`errors.<error_code>`）查語系檔顯示訊息（憲章原則 VIII）。已確認
`apps/web/src/assets/i18n/zh-TW.json` 中 `errors.NICKNAME_REQUIRED_FOR_GUEST`
（line 436）、`errors.ADMIN_TOKEN_INVALID`（442）、`errors.GROUP_DISBANDED`
（445）、`errors.GROUP_FULL`（465）皆已存在，本功能 100% 重用
`join_group()` 的既有邏輯分支即可原樣沿用，不需要新增任何語系檔項目。
