# Research: 會員首頁重新寄送驗證信

5 decisions。不新增資料表、不需要新 migration（冷卻狀態完全由既有
`EmailVerificationToken.created_at` 與總筆數即時計算而得）。

## 1. 冷卻門檻：直接調整既有常數 `_RESEND_VERIFICATION_COOLDOWN`

**Decision**：`apps/api/app/domains/member/service.py:54` 既有的
`_RESEND_VERIFICATION_COOLDOWN = timedelta(seconds=60)` 直接改為
`timedelta(minutes=5)`。既有 `resend_verification()` 內比對冷卻的邏輯
完全不需要更動（`datetime.now(UTC) - last_created_at < _RESEND_VERIFICATION_COOLDOWN`
這段比較式本身與門檻長度無關）——唯一需要調整的是常數本身，以及既有
`test_resend_verification_rate_limit.py` 內硬編碼 `timedelta(seconds=61)`
的測試斷言，需同步改為「超過 5 分鐘」的等效值。

**Rationale**：spec.md FR-004 明確要求「MUST 全面改為 5 分鐘」，取代
006-member-friends FR-011 既有的 1 分鐘門檻——這是使用者本次明確提出的
產品決策調整，既有的比對邏輯設計（以資料庫時間戳比對，而非
slowapi/記憶體計數器）本來就與門檻長度無關，不需要重新設計機制本身，
只改參數值即可。

**Alternatives considered**：無——這是 spec.md 已定案的範圍決策，不是
技術選型問題。

## 2. 共用查詢邏輯：抽出 `_verification_token_count_and_last_created_at()`

**Decision**：把既有 `resend_verification()` 內查詢「該會員最近一次
驗證信 Token 的建立時間」的查詢（`service.py:141-147`）抽成一個獨立的
模組層級私有函式 `_verification_token_count_and_last_created_at(session,
member_id) -> tuple[int, datetime | None]`——單次查詢同時回傳該會員
Token 總筆數與最近一筆的 `created_at`（decision #5 說明為何需要「總
筆數」）。既有 `resend_verification()`（寫入路徑：檢查冷卻、超過門檻
才核發新 Token）與新增的 `get_resend_verification_available_at()`
（唯讀路徑：純粹回答「現在是否還在冷卻中、要等到何時」，供
`GET /members/me`／`POST /auth/login` 這類讀取端點呈現狀態用）皆呼叫
這個共用函式。

**Rationale**：這兩個路徑問的是同一個問題的兩種問法（「可以寄嗎」vs.
「還要等多久」），資料來源完全相同；如果各自寫一份查詢，日後查詢條件
（例如未來若改成排除已失效的 Token）很容易只改到一處、造成兩個路徑
判斷依據不一致（憲章原則 VI），這正是 018/019 兩個 feature 已經在
`group/service.py` 的排名演算法上遇過、也已解決過的同一類風險。

**Alternatives considered**：
- 讓 `get_resend_verification_available_at()` 自己重新寫一份幾乎一樣的
  查詢——被拒絕，理由同上，屬於可預期會漂移不一致的重複邏輯。

## 3. 冷卻狀態的呈現依據：伺服器回傳明確時間戳，前端只排程一次到期事件

**Decision**：`GET /members/me`／`POST /auth/login`（透過
`MemberPublicResponse.resend_verification_available_at`）與
`POST /auth/resend-verification` 本身（透過
`ResendVerificationResponse.available_at`，成功時恆有值）皆由後端算好
「現在是否仍在冷卻中、若是則到何時結束」的明確時間戳（`None` 代表現在
就可以寄，或該帳號已驗證，兩者前端本來就已用 `verification_status`
另外區分，不會混淆）。前端拿到這個時間戳後，只需要排程「一次性」的
`setTimeout`，在到期的那個時刻把按鈕狀態從「冷卻中」翻回「可用」——
MUST NOT 自行用「現在時間 + 5 分鐘」推算冷卻結束時間，也 MUST NOT 用
每秒輪詢的方式反覆檢查。

**Rationale**：spec.md FR-009 明確要求「重新整理頁面後仍必須正確反映
冷卻狀態」——如果只靠前端記憶體（例如成功當下才記錄「現在+5分鐘」），
重新整理就會遺失這個狀態；而如果靠 `localStorage` 之類的裝置本地儲存
自行推算，則會跟 US2 驗收情境 2（「防範機機制以帳號為準，不分分頁/
裝置」）的既定行為產生不一致風險——同一帳號換一台裝置登入，
`localStorage` 是空的，前端就會誤判成「現在可以寄」，讓使用者以為能寄
卻被後端 429 擋下，體驗矛盾。改成後端在既有本來就會回傳會員資料的端點
（`GET /members/me`／登入）上順帶算出這個時間戳，前端不需要额外呼叫、
也不需要自行猜測，完全符合憲章原則 X「伺服器為唯一可信來源」。

**Alternatives considered**：
- 前端用 `localStorage` 記錄「上次成功寄出的時間」自行推算冷卻——被
  拒絕，理由同上，換裝置/清除瀏覽器資料會失準，且與 FR-004 的邊界情境
  （多分頁/裝置皆以帳號為準）矛盾。
- 前端每秒輪詢一個新的「查詢冷卻狀態」端點——被拒絕，`GET /members/me`
  本身在頁面載入時就會呼叫，不需要為了這一個欄位另外新增端點或輪詢，
  一次性 `setTimeout` 已經足夠讓按鈕在正確時刻自動恢復（spec.md FR-008
  只要求「不需要使用者重新整理頁面即可恢復」，並未要求即時 mm:ss 倒數
  數字，見 decision #4）。

## 4. 不做即時倒數數字（mm:ss），只做「冷卻中／可用」二元狀態

**Decision**：按鈕在冷卻中只呈現靜態的「冷卻中」文字＋圖示狀態
（例如「⏳ 請稍後再試」），不逐秒更新剩餘秒數的倒數數字；冷卻結束時
透過 decision #3 的一次性 `setTimeout` 自動翻回可用狀態。

**Rationale**：spec.md US3／FR-008 的驗收情境只要求「呈現明確的冷卻中
狀態」與「滿 5 分鐘後自動恢復，不需重新整理」，並未要求精確到秒的
即時倒數顯示；一次性 `setTimeout` 已經能滿足兩項驗收情境，且比「每秒
觸發一次變更偵測、格式化 mm:ss 字串」的做法單純得多，減少不必要的
實作與測試複雜度（避免為規格沒有要求的精緻度增加維護成本）。

**Alternatives considered**：
- 每秒更新的即時倒數（mm:ss）——被拒絕，spec.md 並未要求這個精緻度，
  屬於範圍外的加分項；若使用者日後明確要求，可在既有「一次性到期
  時間戳」的資料基礎上另行疊加，不需要重新設計資料流。

## 5. 「第一次手動重新寄送」不受冷卻限制：以 Token 總筆數判斷，不新增欄位

**Decision**（`/speckit-analyze` 發現的 I1 修復，Clarifications
2026-09-10）：原始設計（decision #1/#2）單純以「該會員最近一筆
`EmailVerificationToken.created_at`」作為冷卻基準——但註冊當下
`register()` 必定會核發一筆 Token，導致會員剛註冊完、在 5 分鐘內第一次
手動點擊「重新寄送」時，會被誤判為「距離上一次寄出信不滿 5 分鐘」而
遭拒絕，直接牴觸 spec.md Edge Cases 第一項的承諾（「第一次點擊 MUST
直接成功」），也與 SC-003 原文互相矛盾（見 `/speckit-analyze` 報告
finding I1）。修復方式：`_verification_token_count_and_last_created_at()`
額外回傳該會員 Token 的**總筆數**；`resend_verification()` 與
`get_resend_verification_available_at()` 皆改為「筆數 ≤ 1 時 MUST NOT
套用冷卻限制」——因為系統中新增 Token 只有「註冊」與「手動重新寄送」
兩種途徑，筆數 ≤ 1 即代表「這位會員從未手動觸發過重新寄送」，不需要
新增任何欄位或 migration 即可準確判斷（沿用 decision #1 前言「不新增
資料表」的既定範圍）。

**Rationale**：`COUNT()` 與 `MAX()` 可以在同一次查詢內一起取得
（`SELECT COUNT(id), MAX(created_at) ... WHERE member_id = :id`），不需要
額外一次查詢，效能成本與原設計相同；比起新增一個「來源」欄位（例如
`source: Literal["register","resend"]`）來區分 Token 種類，筆數判斷法
不需要修改既有資料表 schema、不需要新的 migration，且邏輯上等價——
「這是不是第一筆」與「這筆是不是註冊核發的」在這個系統裡是同一件事
（因為每個會員恰好只會有一筆「註冊」來源的 Token，且必定是最早的
一筆）。

**Alternatives considered**：
- 修改 spec.md，拿掉「第一次點擊必定成功」的保證，改為明確說明「剛
  註冊完 5 分鐘內點擊可能會看到冷卻提示，此為預期行為」——被拒絕
  （使用者於 `/speckit-analyze` remediation 時明確選擇讓保證成真，而非
  放寬保證）。
- 新增 `EmailVerificationToken.source` 欄位區分「註冊」與「重新寄送」
  ——被拒絕，需要新的 migration，且與 decision #1 前言「不新增資料表」
  的既定範圍矛盾；筆數判斷法已能達到相同效果，不需要額外的資料欄位。
