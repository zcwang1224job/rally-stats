# Research: 即時通知功能

## #1 Ably 頻道：新增 `member:{member_id}:notifications`，沿用既有 wildcard subscribe-only token

**Decision**：新增一個會員層級頻道 `member:{member_id}:notifications`（helper
`member_notifications_channel(member_id)`，比照既有 `court_channel()`/
`group_notifications_channel()` 命名慣例，置於 `app/core/realtime.py`）。
前端沿用完全相同、未經任何修改的 `/realtime/ably-token` 端點——該端點目前
簽發的 token capability 是 `{"*": ["subscribe"]}`（全頻道萬用字元、無需
登入即可取得），存取邊界完全依賴「頻道名稱本身不可猜測」而非 token
capability 限制（`group_id`/`court_id` 皆為 UUID）。`member_id` 同樣是
UUID，套用完全相同的安全模型——不需要為此新增任何 token 能力限制或修改
`create_subscribe_token_request()`。

**Rationale**：這是目前架構（`specs/architecture.md` §3.2）已確立的既有
慣例，不是本 feature 需要重新設計的項目；沿用可避免引入「部分頻道有
capability 限制、部分沒有」的不一致設計。真正的存取控制（誰能讀到通知
內容）發生在 REST API 層（`GET /notifications` 等端點皆需
`require_verified_member` 並僅回傳該會員自己的資料，見 #4）——Ably 頻道
本身只負責「有新事件時提醒前端重新拉取」，不透過 Ably payload 傳遞任何
敏感內容（見 #6）。

**Alternatives considered**：發 token 時依登入會員身份限制 capability
只能訂閱自己的 `member:{member_id}:notifications`——被否決，這會讓通知
功能的 token 簽發邏輯與其他所有既有功能的簽發邏輯（皆為未登入可用的
萬用字元 token）產生分歧，且既有安全模型（頻道名稱不可猜測）已足夠，
沒有實際需求需要這一層額外限制。

## #2 前端如何得知自己的 `member_id`：擴充 `AuthService`，於登入時快取

**Decision**：`AuthService`（`apps/web/src/app/features/auth/auth.service.ts`）
新增第三個 localStorage key（比照既有 `ACCESS_TOKEN_KEY`/
`REFRESH_TOKEN_KEY` 慣例）快取 `member_id`：登入成功（`login()`）與
`getMe()` 呼叫成功時寫入；`logout()`/`clearTokens()` 時一併清除。新增
`getCachedMemberId(): string | null` 讀取方法。`NotificationService`（新
增，見 #3）初始化時優先讀取快取值；若為 `null`（例如舊 session 在此
feature 上線前就已登入、從未快取過），退回呼叫一次既有 `getMe()` 補齊，
拿到後立即快取，之後不再重複呼叫。

**Rationale**：`GET /members/me` 回應（`MemberPublic`）本來就含
`member_id` 欄位，登入回應（`LoginResponse.member`）也是同一形狀——現有
資料本來就有這個值，只是目前沒有任何地方快取它。比起在每個頁面載入時
都呼叫一次 `getMe()` 才能訂閱通知頻道，快取一次、之後直接讀取更省一次
不必要的網路往返，且不需要新增 `jwt-decode` 這類額外套件去解析 access
token payload（本專案目前沒有任何 JWT 前端解碼的既有慣例，不宜為此
單一需求首次引入）。

**Alternatives considered**：前端解碼 access token 的 JWT payload 取出
`member_id`（token 簽發時本來就帶這個欄位）——被否決，需要新增套件或
手刻 base64 解碼邏輯，複雜度與新增一個 localStorage 快取欄位相比不成
比例，且本專案目前無此慣例。

## #3 前端通知狀態集中於新的 `NotificationService`，未讀角標放在 `nav-shell`

**Decision**：新增 `apps/web/src/app/features/notifications/notification.service.ts`
（root-provided），職責：
- `unreadCount = signal<number>(0)`，供角標與列表頁共用。
- `init()`：解析 `member_id`（#2）→ 呼叫 `GET /notifications/unread-count`
  取得初始值 → 訂閱 Ably `member:{member_id}:notifications` 頻道的
  `notification.created` 事件 → 訂閱既有 `ReconnectRefetchService
  .onReconnect()`（007 research.md #8 已建立，直接重用，不重新實作斷線
  判斷邏輯）——兩者收到訊號時都呼叫同一個私有 `refetchUnreadCount()`，
  以伺服器回應**覆蓋**本地值（不做本地樂觀遞增），呼應 constitution
  III「重新連線後 MUST 以伺服器回傳的最新狀態強制覆蓋畫面」的既有原則
  ——即時事件到達時的行為比照辦理，避免本地計數因事件遺失/重複而
  漂移。
- `list(page)`/`markRead(id)`/`markAllRead()`：呼叫對應 REST 端點
  （contracts/notification-api.md），成功後以回應內容更新
  `unreadCount`。

`init()` 由 `NavShellComponent`（`apps/web/src/app/core/nav-shell/`，
唯一保證登入後每個主要頁面都會渲染的全域元件，見其既有 docstring）在
建構子中、`loggedIn()` 為真時呼叫一次；`nav-shell` 內新增一個
`notification-bell`子元件顯示 `unreadCount()`（FR-006），點擊導向新增的
`/notifications` 路由（通知列表頁，US2/US3）。

**Rationale**：FR-006 要求「系統各主要頁面皆可見」——`nav-shell` 是唯一
符合此條件的既有全域元件（比照其自身 docstring「rendered from the app
root on every route that doesn't opt out」）；比分板/控制板/計分板等
`navShell: false` 的公開頁面本來就不是會員通知的適用情境（未登入）。將
即時訂閱與狀態集中在單一 service，而非讓 `nav-shell` 與未來的
`notification-list` 頁面各自訂閱一次 Ably 頻道，避免重複訂閱與狀態
不同步。

**Alternatives considered**：`nav-shell` 直接內嵌 Ably 訂閱邏輯，不拆
service——被否決，通知列表頁（`/notifications`）之後也需要即時更新
（US2 隱含情境：已開著列表時收到新通知），若邏輯寫在 `nav-shell` 裡，
列表頁無法重用，會被迫重複訂閱同一頻道兩次。

## #4 後端新增獨立 `notification` domain 模組，不塞進 `friend` 模組

**Decision**：新增 `apps/api/app/domains/notification/`
（`models.py`/`schemas.py`/`service.py`/`router.py`），比照 `friend`
模組的既有規模。`friend/service.py` 的 `create_friend_request()` 於
**同一個資料庫交易**內（`session.add(friend_request)` 之後、
`await session.commit()` 之前）呼叫新增的
`notification.service.create_friend_request_notification(session,
friend_request)`（僅 `session.add()`，不自行 commit），確保好友申請與
其對應通知一起原子建立，不會出現其中一筆存在、另一筆遺漏的中間狀態
（呼應 spec Assumptions「一則好友申請只會產生一則對應通知」）。commit
成功後，`create_friend_request()` 才呼叫
`notification.service.publish_notification_created(notification)`
（內部呼叫既有 `app.core.realtime.publish()`，見 #6）。

**Rationale**：通知本質上是「跨多種來源事件的獨立概念」（FR-011 之可
擴充性——未來邀請入團通知的來源事件是另一個尚不存在的模組，不會是
`friend` 模組），若直接塞進 `friend` 模組，未來新增其他通知類型時勢必
要把通知邏輯搬出來重構，不符合原則 VI 的模組邊界精神。`friend` 模組對
`notification` 模組僅有「建立好友申請後呼叫一個函式」這一個單向依賴，
`notification` 模組不反向依賴 `friend` 模組的內部實作（僅在
`schemas.py` 匯入其公開的 `FriendSummary` schema 做回應組裝，比照
`member/service.py` 既有匯入 `group/schemas.py`、`group/service.py`
之 `_completed_matches_query()` 的既有跨模組重用慣例）。

**Alternatives considered**：通知邏輯直接寫在 `friend/service.py` 內部
（例如 `FriendRequest` 模型自己多一個 `notified_at` 欄位）——被否決，
無法滿足 FR-011「未來新增其他類型不需重新設計」的要求，且會讓
`friend` 模組承擔本不屬於它的職責（通知列表、未讀計數、已讀狀態管理
與好友系統本身無關）。

## #5 `notifications` 表結構：`type` + `source_id`，不做 FK、不做 payload 快照

**Decision**：
- `type`（`String(32)`，本次僅有 `"friend_request"` 一種合法值）與
  `source_id`（`UUID`，依 `type` 決定指向哪張表；本次恆指向
  `friend_requests.id`）為通知的核心識別欄位，**不**對 `source_id` 建立
  資料庫層級 FK 約束（多型參照，不同 `type` 指向不同表，單一 FK 無法
  同時滿足）。
- **不**新增 `payload`/快照欄位儲存申請人暱稱等展示用資訊——`GET
  /notifications` 一律即時查詢 `FriendRequest` + `Member`（申請人）組裝
  回應，比照 `friend/service.py` 既有的 `list_incoming_requests()`
  （已是「即時查 `Member.nickname`，非快照」的既定慣例，見其實作）。
- `read_at`（`TIMESTAMPTZ`，nullable）以單一欄位同時承載「已讀/未讀」
  布林語意與「何時已讀」時間戳，`NULL` = 未讀。

**Rationale**：專案內唯一與「暱稱是否快照」相關的既有慣例是
`RosterEntry.nickname`（`test_nickname_snapshot_isolation.py`）——但那
是特定於「加入某團當下的暱稱」這個完全不同的領域概念（呼應該團賽程/
戰績歷史的當下真實），不是「好友系統展示會員身份」的通用規則；好友
系統本身（`FriendSummary`/`list_incoming_requests`）從未快照過
`Member.nickname`，通知功能沿用好友系統自己的既有慣例，而非誤用另一個
不相關功能的快照慣例。即時查詢也自然滿足 spec Assumptions「若通知關聯
的好友申請已在其他管道被處理，點擊通知仍呈現最新狀態」——不需要額外的
「過期快照偵測」邏輯，即時查詢本身就是最新狀態。

**Alternatives considered**：`source_id` 改用多欄位（`friend_request_id
UUID NULL`、未來 `group_invite_id UUID NULL`……）取代單一 `type` +
`source_id`——被否決，每新增一種通知類型就要新增一個 nullable 外鍵
欄位並跑一次 migration，違反 FR-011「不需要重新設計既有機制」的精神；
目前的 `type` + `source_id` 設計新增類型時只需要在 `service.py`/
`schemas.py` 增加對應的查詢與回應分支，資料表結構完全不變。

## #6 `notification.created` 事件 payload 僅含最小識別資訊，不含展示內容

**Decision**：Ably payload 僅為
`{"notification_id": "uuid", "type": "friend_request"}`。前端收到後
一律呼叫 `GET /notifications/unread-count`（並在通知列表頁開著時額外
重新拉取列表）取得最新狀態，不從 payload 直接组裝畫面內容。

**Rationale**：比照 007 research.md #9「回應/事件皆附最新狀態供前端
直接校正畫面」的精神，但反過來取捨——通知內容需要即時查詢
`FriendRequest`/`Member`（#5 已決定不快照），若要讓 Ably payload 自帶
完整展示內容，等於要在發布事件前多做一次與 `GET /notifications` 完全
重複的組裝邏輯，且 Ably payload 一旦發出無法「即時反映最新狀態」
（例如發布後好友申請立刻被撤回，payload 內容就過期了）；讓前端收到
事件後永遠回頭問伺服器一次，同時滿足「內容永遠最新」與「不重複實作
組裝邏輯」兩個目標。

**Alternatives considered**：payload 內嵌完整的申請人暱稱等展示欄位，
前端直接渲染不必再打一次 API——被否決，見上，且通知數量/頻率極低
（好友申請本來就是低頻事件），多一次輕量的 `GET
/notifications/unread-count` 呼叫沒有效能疑慮。

## #7 已讀狀態轉換與「全部標示已讀」：獨立端點，非批次覆蓋整張表

**Decision**：
- `POST /notifications/{notification_id}/read`——`UPDATE notifications
  SET read_at = now() WHERE id = :id AND member_id = :member_id AND
  read_at IS NULL`（`read_at IS NULL` 條件讓重複點擊天然成為 no-op，
  不需要额外檢查目前是否已讀才決定要不要寫入）。
- `POST /notifications/read-all`——`UPDATE notifications SET read_at =
  now() WHERE member_id = :member_id AND read_at IS NULL`，回傳
  `marked_count`（`rowcount`）。

兩者皆以 `member_id = :member_id` 限定範圍（來自
`require_verified_member` 解析出的登入身份，非請求參數），確保會員
MUST NOT 能標記別人的通知已讀。

**Rationale**：FR-013 明確定案「開啟列表不會自動已讀，僅點擊/開啟該則
才已讀」——不需要「列表載入時批次標記可見項目已讀」這種邏輯，兩個
端點各自對應 FR-007/FR-008 的獨立操作即可，且皆可用單一原子 `UPDATE
... WHERE` 達成，不需要「先查詢再判斷」的應用層邏輯（比照 007
research.md #5 之原子 SQL 風格慣例）。

**Alternatives considered**：`GET /notifications` 回應時「順便」把
回應內含的通知都標記已讀——被否決，直接牴觸 FR-013 之明確定案。

## #8 索引設計：依查詢型態各建一個

**Decision**：
- `ix_notifications_member_created`（`member_id`, `created_at DESC`）
  ——供 `GET /notifications` 分頁列表查詢。
- `ix_notifications_member_unread`（`member_id`）`WHERE read_at IS
  NULL`（partial index）——供 `GET /notifications/unread-count`（FR-006
  角標，會在每個主要頁面載入時被呼叫，是本 feature 最高頻的查詢）與
  `POST /notifications/read-all` 使用。
- `uq_notifications_type_source_member`（`type`, `source_id`,
  `member_id`）UNIQUE——資料庫層級保證同一筆來源事件不會對同一會員
  重複建立通知（比照 `friend_requests` 既有的 partial unique index
  慣例，DB 層而非僅應用層保證此不變量）。

**Rationale**：未讀角標查詢頻率遠高於列表查詢（每個主要頁面載入都會
觸發，見 #3），值得一個專用 partial index；一般好友申請場景下同一位
會員的通知總量與其好友申請總量同一數量級（本來就很小，比照 005
`match-history` 之 Scale/Scope 假設），index 主要是為了查詢型態正確
而非因為資料量大。

**Alternatives considered**：僅建立單一 `(member_id)` 索引，不分列表/
未讀兩種——被否決，未讀計數查詢若掃過所有已讀通知（隨時間增長）效率
會逐漸變差，partial index 讓這個高頻查詢的成本恆定為「未讀筆數」而非
「總筆數」。
