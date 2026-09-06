# Phase 0 Research: 加入團（嘎團）

## 1. 決議：本 feature 擴充既有 `group` 模組，不新建 `roster` 服務模組

**Decision**：`app/domains/roster/` 目前僅有 `models.py`（`RosterEntry`，001 建立）；本 feature 不新建 `app/domains/roster/service.py`/`router.py`，而是將加入流程（列表查詢、密碼驗證、加入送出）的 REST 端點與 service 邏輯放在既有 `app/domains/group/` 模組（`service.py`/`router.py` 新增函式），直接 `import` 並寫入 `RosterEntry`。加入成功後，呼叫 003 已提供的 `handle_member_joined(session, group, new_member)` hook（研究其邊界見 003 plan.md Assumptions），不重新實作賽程收斂邏輯。

**Rationale**：加入流程的核心資料實體（`Group.current_member_count`、`join_link_token`、密碼欄位）皆屬 `group` 模組既有欄位，`RosterEntry` 本身雖是獨立表但尚未有專屬「擁有」模組（003 讀寫其排點語意欄位、001 建立其基礎欄位，皆未建立 CRUD service）；比照 003 research.md #2 的既有先例（新 feature 可擴充既有模組而非強行拆出單一實體對應單一模組），加入流程的業務邏輯（密碼/人數檢查）與 `Group` 欄位高度耦合，放在 `group` 模組內最符合單一職責，且能直接重用 `group/security.py` 之 `decrypt_group_password`。

## 2. 決議：`GET /groups`（開團列表）與 `GET /join/{join_link_token}` 皆支援「可選會員身份」

**Decision**：兩個端點皆新增一個 FastAPI dependency `optional_member`（`Authorization` header 存在則解碼驗證，不存在則回傳 `None`，格式錯誤或已失效則同樣回傳 `None`——與 `require_member` 不同，這裡登入狀態是「加值」而非「必要條件」，不應讓過期 token 導致整個請求失敗）：
- `GET /groups`：已登入時每筆列表項目額外標註 `joined_by_me: bool`（該會員在該團是否有 active 狀態的 `RosterEntry`）。
- `GET /join/{join_link_token}`：已登入且該會員在解析出的團已有 active 狀態的 `RosterEntry` 時，回應額外包含 `already_joined: true` 與其 `roster_entry_id`，前端據此略過密碼/暱稱頁直接導向現有狀態（FR-020a）。

**Rationale**：FR-006、FR-020a 皆要求「已登入會員」分支邏輯，但這兩個端點本身是公開端點（無需登入即可瀏覽/預覽），比照 `require_member` 的「缺 token 即 401」語意在此不適用；獨立設計 `optional_member` dependency 避免誤用既有的強制驗證版本。

## 3. 決議：`POST /groups/{group_id}/verify-password` 為獨立、無次數限制的輕量端點；`POST /groups/{group_id}/join` 送出當下重新驗證密碼

**Decision**：`architecture.md` 已將 `verify-password` 端點列在 `group`（001）章節下，本 feature 據此於 `group/router.py` 新增此端點：純粹解密比對 `group.password_ciphertext`，回傳 `{correct: bool}`，MUST NOT 有錯誤次數限制（FR-016）。真正送出的 `POST /groups/{group_id}/join` 請求 body 亦包含明文密碼欄位（若該團有密碼），並在同一次請求內重新比對——不依賴前一次 `verify-password` 呼叫的結果作為信任依據。密碼正確性檢查與 FR-013 之人數上限「前置檢查 vs 最終保證」為同一種兩層式設計精神的延伸：`verify-password` 是 UX 用的即時回饋（無限次重試），`join` 送出當下的重新驗證才是唯一事實依據。

**Rationale**：HTTP 為無狀態協定，若僅信任「先前呼叫過 verify-password」，兩次請求之間沒有任何綁定機制（無 session、無簽章 token）可證明使用者真的通過了驗證，等同於讓密碼保護形同虛設；在 `join` 當下重新驗證一次，成本極低（同一組 AES-GCM 解密與字串比對），且不需引入任何額外的短效期中介 token 或 session 機制。

## 4. 決議：Guest Session Token 為隨機不透明字串，透過 `GET /groups/by-guest-token/{token}` 解析（比照既有 `by-token` 慣例）

**Decision**：`roster_entries.guest_session_token`（001 已建立此欄位）之值採 `secrets.token_urlsafe(32)` 產生，寫入時機為 Guest 完成加入的同一筆交易；解析端點沿用 002 已建立的 `GET /courts/by-token/{token}`、`GET /groups/by-all-courts-token/{token}` 之路徑命名慣例，新增 `GET /groups/by-guest-token/{token}`，回傳該筆 `RosterEntry` 的基本狀態（`roster_entry_id`、`nickname`、所屬 `group_id`）供前端確認還原；若該團已解散、或該筆 `RosterEntry` 狀態已非 `active`（已退出/被踢除），一律回傳 `404 LINK_NOT_FOUND`（不區分兩種失效原因給前端，避免洩漏內部狀態細節，且兩者前端行為相同——導向全新加入流程）。

**Rationale**：`architecture.md` 之 `roster_entries` 表註解已明文「Guest Session Token 內嵌於 roster_entries 表...改以 roster_entries.guest_session_token（nullable、唯一）欄位承載」，本決議僅補完其解析端點與產生方式；`secrets.token_urlsafe` 為 Python 標準庫之密碼學安全隨機字串產生器，不需要簽章或可驗證結構（不像 JWT 需要驗證篡改），因為此 Token 的角色僅是「不可猜測的查找鍵」，比對邏輯全部落在後端資料庫查詢，不需自我描述的 payload。

## 5. 決議：人數上限的原子性保證採單一條件式 `UPDATE ... WHERE` 語句（非悲觀鎖）

**Decision**：`POST /groups/{group_id}/join` 真正寫入 `RosterEntry` 前，先執行 `UPDATE groups SET current_member_count = current_member_count + 1 WHERE id = :group_id AND current_member_count < max_members`，並檢查 `rowcount`；若為 0（更新影響 0 筆），視為已滿，MUST 拋出 `GROUP_FULL`（FR-013 明文指定此 SQL 語句作為唯一事實依據）。此 UPDATE 與後續 `RosterEntry` 的 `INSERT` 屬同一筆資料庫交易，UPDATE 失敗（rowcount=0）時整筆交易 MUST 回滾、不寫入任何 `RosterEntry` 列。

**Rationale**：PostgreSQL 單一 `UPDATE ... WHERE` 語句本身即為原子操作（row-level lock 由資料庫引擎自動於該筆 UPDATE 執行期間持有，不需應用層額外呼叫 `SELECT ... FOR UPDATE`），兩個近乎同時的請求對同一團的 `current_member_count` 執行此 UPDATE 時，PostgreSQL MVCC 機制保證僅有一個請求能在名額耗盡前成功遞增，另一個會因 WHERE 條件此時已不成立而影響 0 筆——這正是 SC-002「100% 只有一位成功加入」的資料庫層級保證來源；此模式比 003 之 Next Round 悲觀鎖（`SELECT ... FOR UPDATE NOWAIT`）更輕量，因為此處的寫入範圍僅單一整數欄位遞增+單筆新記錄插入，不像 Next Round 需要鎖住整個操作區間內的複雜多表寫入。

## 6. 決議：`current_member_count` 遞減（退出/踢除釋放名額）延用既有的直接寫入，不受本 feature 影響

**Decision**：003（`kick_member`/`handle_member_left`）與未來 005（成員主動退出）皆需在成員狀態轉為 `left`/`kicked` 時遞減 `current_member_count`；本 feature 確認此遞減邏輯已存在於（或應存在於）003/005 各自的職責範圍內，`join`（遞增）與「退出/踢除」（遞減）為對稱的兩個操作但分屬不同 feature 擁有，本 feature 僅新增遞增側，不重新設計或搬動遞減側的既有/既定邏輯。

**Rationale**：避免本次規劃誤將整個 `current_member_count` 生命週期攬入 004 範圍——FR-012 明確指出「退出/被踢除立即釋放名額」是既有規則的延伸應用，非本 feature 新增行為；此決議記錄純粹是釐清邊界，供 `/speckit-tasks` 判斷本 feature 的 Foundational/US3 任務範圍時，不誤將 003 的 `kick_member` 重新拉入本 feature 的任務清單。

## 7. 決議：開團列表的「場地名稱」欄位為該團所有未刪除場地名稱的陣列；搜尋比對任一場地符合即算命中

**Decision**：`Group` 本身無場地名稱欄位（場地屬 002 之 `Court` 表，一團可有多個場地）；`GET /groups` 回應之每筆列表項目新增 `court_names: list[str]`（該團所有 `deleted_at IS NULL` 之 `Court.name`，依 `created_at` 排序）；FR-003 之「依場地名稱搜尋」比對邏輯為：該團底下任一場地的名稱包含（ILIKE 子字串）搜尋字串即視為符合；「依場地 ID 搜尋」為精確比對任一場地的 `id`。

**Rationale**：spec.md Assumptions 明確將「場地名稱/ID 比對邏輯細節」留待 `/speckit-plan` 決定；一團可有多場地是 002 已定案的既有模型，開團列表既然要呈現「場地名稱」欄位，比較合理的呈現方式是列出全部場地（而非任選其一），搜尋邏輯採「任一命中即算命中」與此呈現方式一致，避免「顯示全部但搜尋只認第一個」的不一致體驗。

## 8. 決議：分頁採 `page`（1-based）+ 固定 `page_size=20`

**Decision**：`GET /groups?page=1`，每頁固定 20 筆（不開放使用者調整），回應包含 `page`、`total_pages`、`groups`。

**Rationale**：spec.md Assumptions 明確留待 plan 決定「每頁筆數等技術細節」；20 筆為與好友列表分頁（006 已採用）一致的合理預設值，維持全站分頁筆數風格統一。

## 9. 決議：`POST /groups/{group_id}/join` 之會員/Guest 分流與 FR-020a 短路邏輯

**Decision**：`join` 端點同時接受「有 `Authorization` Bearer（已登入會員）」與「無此 header（Guest）」兩種呼叫方式（同一端點，非兩個端點）：
- 已登入會員：body 不需 `nickname`（若提供也忽略，MUST NOT 用於覆蓋會員暱稱），直接用 `member.nickname` 寫入 `RosterEntry.nickname`；若該會員 `nickname IS NULL`（尚未完成首次暱稱設定，見 006 FR-012），本端點 MUST 拒絕並回傳 `NICKNAME_REQUIRED_FOR_MEMBER`，由前端導向 006 已建立的「首次登入設定暱稱」頁面，完成後才重新呼叫本端點（FR-019）。
- Guest：body MUST 提供 `nickname`（1–20 字，去除頭尾空白後不可為空）。
- 兩種情境送出前，服務層 MUST 先查詢該會員（若已登入）在此團是否已有 `status='active'` 之 `RosterEntry`；若有，直接回傳該筆既有記錄（`created_new: false`），MUST NOT 重新執行密碼驗證或人數上限檢查（FR-020a）。Guest 無此短路邏輯（Guest 沒有可比對的既有身份，每次皆視為新加入請求，直到 FR-023 之 Guest Session Token 還原機制介入——後者透過 `GET /groups/by-guest-token/{token}` 另外處理，不經過 `join` 端點本身）。

**Rationale**：單一端點比雙端點（`/join` 與 `/join-as-guest`）更貼近 spec 描述的「同一組加入流程，僅暱稱處理分流」精神（FR-010「後續流程...完全一致」）；FR-020a 之短路檢查放在 service 層最前面（先查詢既有記錄，早於密碼/人數檢查）確保「不重新執行」的要求確實落實，而非事後才發現重複但仍執行了不必要的驗證。
