# Phase 0 Research: 會員個人設定（四大分區）

## #1 好友檢視他人戰績：新端點 vs. 重用既有 service 函式

**Decision**：新增兩支路由 `GET /members/{member_id}/match-records`、
`GET /members/{member_id}/match-records/{match_id}`，router 層先做
「好友關係＋隱私設定」授權檢查，通過後直接呼叫既有
`build_member_match_records(session, member_id, ...)`／
`get_member_match_record_detail(session, member_id, match_id)`——這兩個
service 函式（`apps/api/app/domains/member/service.py:340,600`）本來就已
是泛用 `member_id` 參數簽章，並非寫死「呼叫者自己」；既有的
`/members/me/match-records*` 端點只是單純把 `member.id`（來自
`require_member`）傳進去。因此「查看別人的戰績」在 service 層不需要任何
新邏輯，只需要在 router 層新增一條路徑，傳入路徑參數 `member_id` 而非
`member.id`，並在呼叫前插入授權檢查。

**Rationale**：符合憲章原則 VI（可維護性）——不建立一套平行的「檢視他人
戰績」邏輯；也符合原則 X——授權判斷（好友關係、隱私設定）由後端在請求當下
查詢最新狀態決定，不快取判斷結果。

**Alternatives considered**：
- 在既有 `/members/me/match-records` 加一個 `?view_as=<member_id>` 之類
  的參數——拒絕：混淆「我自己的資料」與「他人資料」兩種語意於同一端點，
  且既有端點用 `require_member`（不要求驗證信箱），而查看他人資料應比照
  `search_member()` 要求 `require_verified_member`，混在一起會讓既有端點
  的驗證等級被迫提高，影響既有行為。
- 複製一份新的 `service.py` 函式（例如 `build_friend_match_records()`）
  ——拒絕：與既有函式邏輯 100%相同，純粹是不必要的重複。

## #2 登入紀錄的保留策略

**Decision**：每位會員保留最近 **50 筆**主動登入紀錄；每次新增一筆時，於
同一交易內執行「刪除該會員超出最近 50 筆範圍的舊紀錄」（`DELETE ...
WHERE member_id = :id AND id NOT IN (SELECT id FROM member_login_records
WHERE member_id = :id ORDER BY created_at DESC LIMIT 50)`），不需要額外的
背景排程/定期清理任務。

**Rationale**：50 筆遠超過「察覺近期異常登入」實際需要查看的範圍（一般
使用者近期登入頻率遠低於此數字），同時足以讓 FR-009 的分頁需求（搭配
`default_page_size`=20，見 `system_config.service.get_default_page_size()`）
有真實的多頁情境可測試；裁切在寫入當下同步完成，避免引入新的排程基礎
設施（符合憲章「未來規劃事項」對維運複雜度的謹慎態度，也符合原則 IX
不新增基礎設施）。

**Alternatives considered**：
- 依時間保留（例如「最近 90 天」）——拒絕：多一個時間相關的裁切維度，
  複雜度高於單純的「筆數上限」，且對這個功能的核心價值（近期異常登入）
  沒有額外幫助。
- 交由背景排程定期清理——拒絕：需要新的排程基礎設施，且與本 feature
  「不新增基礎設施」的範圍不符；同步裁切已足夠簡單可靠。

## #3 裝置類別判斷方式

**Decision**：後端從 `Request` 的 `User-Agent` header 以簡單正則判斷
`"mobile"` 或 `"desktop"`（找不到 header 或無法判斷時存
`"unknown"`）——與既有 `member/schemas.py` 已有的「輕量正則」風格
（`_PASSWORD_HAS_LETTER`/`_PASSWORD_HAS_DIGIT`）一致，實作為 member
domain 內的一個小型純函式 `classify_device(user_agent: str | None) ->
str`。

**Rationale**：符合原則 IX（不新增第三方套件）；「桌面/行動裝置」這種
粗粒度分類不需要完整的 UA 解析套件（例如 `user-agents`），簡單關鍵字比對
（`Mobile`/`Android`/`iPhone`/`iPad` → mobile，其餘 → desktop）已足以達成
FR-007 的驗收標準（讓使用者判斷「這是不是我常用的裝置類型」）。

**Alternatives considered**：
- 引入 `user-agents` 等第三方套件做完整 UA 解析（含瀏覽器名稱、版本、
  作業系統）——拒絕：超出 spec 實際要求的粒度（FR-007 只要求「裝置類別」
  這種粗粒度資訊），且違反原則 IX 不新增非必要依賴的精神。
- 前端偵測裝置類型後隨登入請求一併送出——拒絕：違反原則 X（伺服器為唯一
  可信來源）——裝置分類這種安全提示用途的資訊不應信任前端自報，容易被
  竄改，後端從 `User-Agent` header 自行判斷更可靠。

## #4 語言偏好欄位的可擴充設計

**Decision**：`members.language_preference` 為 `VARCHAR(8) NOT NULL
DEFAULT 'zh-TW'`（純字串欄位，**不加 DB 層級 CHECK 約束**列舉合法值）；
合法值清單改放在後端程式碼中的一個小型常數（例如
`SUPPORTED_LANGUAGES = ("zh-TW",)`），由 Pydantic schema 的 validator
在請求時檢查是否屬於這份清單。

**Rationale**：FR-004 明確要求「此清單結構 MUST 支援未來新增語言選項而
不需重新設計此分區的呈現方式」——若合法值寫死在 DB CHECK 約束，未來新增
語言需要一次新的 migration 才能通過寫入驗證；改用程式碼常數清單，未來
新增語言只需修改這個常數（不需要 migration），同時前端下拉選單也改為
讀取後端提供的「目前支援的語言清單」而非寫死選項本身（見
`contracts/member-settings-api.md` 的 `GET /members/me` 回應新增
`supported_languages` 欄位）。

**Alternatives considered**：
- DB CHECK 約束枚舉合法值——拒絕：如上，違反 FR-004 的可擴充性要求。
- 前端寫死語言選單選項（不從後端取得）——拒絕：未來新增語言時前後端
  兩邊都要改，且若兩邊清單不同步會出現「選單顯示了後端尚不支援的語言」
  的不一致狀態。

## #5 隱私設定的 API 形狀：合併端點 vs. 各自獨立端點

**Decision**：單一端點 `PATCH /members/me/privacy`，body 為兩個皆可選的
布林欄位（`allow_search?`、`share_match_records_with_friends?`）。**前端
互動模式（2026-09-13 實作階段調整）**：兩個 checkbox 僅為本地草稿狀態，
切換本身 MUST NOT 觸發任何 API 呼叫；分區底部提供一個「送出」按鈕，MUST
點擊後才一次送出兩個欄位目前的草稿值——與「基本設定」暱稱/語言偏好、
「安全性」密碼分區的既有「填寫後按按鈕送出」互動模式一致，而非最初
`research.md` 草案設想的、比照 `scoreboard_scoring_enabled` 的「切換即
送出」即時儲存模式（使用者於實作階段明確要求改為此版本）。回應一律回傳
兩個欄位的目前完整狀態。

**Rationale**：兩個隱私設定雖然是獨立的可切換狀態，但同屬「隱私設定」
一個分區、共用同一組驗證信箱前提與同一種「立即生效」語意（FR-020——
此處「立即生效」指的是儲存成功後對後續請求的效果沒有快取延遲，非指
UI 互動本身不需要送出動作）；合併一個端點可讓前端用同一支 API 一次送出
兩個 checkbox 的草稿值，不需要為了兩個布林值各自維護一支端點。

**Alternatives considered**：
- 兩個完全獨立的端點（`PATCH /members/me/privacy/searchable`、
  `PATCH /members/me/privacy/match-visibility`）——拒絕：徒增端點數量，
  兩者本來就沒有各自獨立演進的跡象（都是「隱私設定」分區底下的簡單布林
  開關），合併端點更精簡且無明顯壞處。

## #6 好友查看戰績被拒絕時的錯誤語意

**Decision**：新增兩個語意化錯誤碼：
- `FRIENDSHIP_REQUIRED`（403）——呼叫者與目標會員尚未成立好友關係時。
- `MATCH_RECORDS_PRIVATE`（403）——已是好友，但目標會員已關閉
  `share_match_records_with_friends` 時。

兩者皆與「允許被搜尋」關閉時刻意回應「查無此人」（`MEMBER_NOT_FOUND`，
FR-017）不同——因為呼叫者本來就已經知道目標會員存在（雙方是好友關係，
彼此在好友列表中互相可見），沒有「隱藏帳號是否存在」的需求，明確告知
「已設為不公開」對使用者體驗更友善（也符合 spec 驗收情境 3 的明確措辭
「並提示此會員已將戰績設為不公開」）。

**Rationale**：`MEMBER_NOT_FOUND` 的「查無此人」語意是為了防止陌生人
透過搜尋探知帳號是否存在（FR-017 的核心目的）；但好友關係場景下這個
「隱藏存在與否」的威脅模型不成立（雙方互為好友，存在與否早已互相可見），
用不同錯誤碼可以給出更明確、更有幫助的錯誤訊息，兩者語意不衝突。

**Alternatives considered**：
- 統一都回 `MEMBER_NOT_FOUND`——拒絕：對已經是好友的使用者而言，隱藏
  「其實是被設為不公開」這個事實沒有安全效益，反而讓使用者誤以為系統
  故障或對方帳號消失。
