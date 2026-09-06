# Phase 0 Research: 場地管理（Court Management）

## 1. 決議：join-link / all-courts-link 重新產生操作歸屬哪個程式模組

**Decision**：`POST /groups/{group_id}/regenerate-join-link` 與 `POST /groups/{group_id}/regenerate-all-courts-link`（含對應的心跳端點）之程式碼實作於 `app/domains/group/`（擴充 001 既有的 `service.py`/`router.py`），採用與既有 `regenerate_admin_pin()` 完全相同的「樂觀鎖版本比對 + `link.regenerated` 事件廣播」模式。

**Rationale**：`join_link_token`/`join_link_version`/`all_courts_control_panel_token`/`all_courts_link_version` 四個欄位在 `groups` 資料表上，由 001 spec 的 `data-model.md` §1 明確標註「本 feature 定義欄位存在，實際重新產生操作由 002 spec 實作」——即 001 已預留欄位並將「操作」的實作責任明確移交給本 feature。依 constitution 原則 VI（模組化：以實體所屬領域劃分模組，而非以 spec 編號劃分），變更 `groups` 資料列的程式碼應留在擁有該資料表的 `group` 領域模組內，避免 `court` 模組跨界直接寫入 `groups` 資料列。本 feature（002）僅負責這兩個端點所對應的**使用者故事與驗收標準**，實作檔案位置延續既有領域邊界。

**Alternatives considered**：於 `app/domains/court/` 內另建對 `groups` 表的寫入邏輯——否決，會造成兩個領域模組同時直接寫入同一張表，違反原則 VI。

## 2. 決議：場地刪除時的比賽捨棄邏輯（US2, FR-010）

**Decision**：比照 001 `disband_group()` 已建立的 `AbandonMatchesHook` 模式，新增一個場地層級版本 `AbandonCourtMatchesHook = Callable[[AsyncSession, uuid.UUID], Awaitable[None]]`（傳入 `court_id`），`delete_court()` 接受此 hook 作為可選參數，預設值為 no-op；待 003 spec 實作 Match 領域模組後再傳入真正的邏輯（於 003 的 plan 中完成串接，非本 feature 範圍）。

**Rationale**：`matches` 資料表與其狀態機屬於 003 spec 擁有範圍（見 `specs/architecture.md` §7.1 相依關係圖：003 依賴 001+002，002 不應反向依賴尚未存在的 003 領域模組）。此模式已於 001 驗證可行（`disband_group()` 目前仍以 no-op hook 運作，待 003 完工後串接），本 feature 延續相同做法保持一致性。

**Alternatives considered**：延後整個 US2 直到 003 完工——否決，場地的軟刪除生命週期本身（`deleted_at` 寫入、連結立即失效、場地計數更新）與「是否已有 Match 領域模組可呼叫」無關，可獨立完成並正確運作；僅「捨棄該場地未收尾比賽」這一個子步驟需要 hook 延後串接。

## 3. 決議：US3（全部場地控制板）與 US4（管理頁內建場地控制區塊）之範圍邊界

**Decision**：本 feature 完整實作這兩個畫面**進入這兩個畫面所需的連結/Token/身分解析/場地清單基礎設施**（US3 的 FR-013~017、US4 的 FR-018~019、FR-024），但兩者畫面上實際的 +1/-1、提前結束、手動安排選人等**操作本身**依賴尚未存在的 Match/RosterEntry 領域邏輯（003、007 spec 擁有），故本 feature 於這兩處以明確的空狀態呈現（例如「尚無進行中比賽」），操作按鈕先行建立畫面骨架與正確的即時訂閱/心跳基礎設施，實際評分/安排邏輯留待 007、003 spec 完工後串接。

**Rationale**：與 001 對 002/003/007 的範圍界定方式一致（001 `plan.md`：「本功能不涵蓋場地、賽程、計分…僅定義與這些周邊功能的資料/事件邊界」）；`specs/architecture.md` §7.2 亦明確將「即時計分板與控制板」列為第 6 步、晚於本 feature（第 4 步）。提前把「全部場地控制板」「管理頁場地控制區塊」這兩個進入點與其連結管理、即時同步基礎設施做好，可讓 007 完工時只需插入評分邏輯而不需重新設計這兩個畫面的框架。

**Alternatives considered**：完整實作假的 Match 讀寫邏輯以「模擬」US3/US4 的完整驗收情境——否決，會產生日後需整批捨棄重寫的技術債，且違反「不做超出當前範圍的事」的專案慣例。

## 4. 決議：場地連結初始化與心跳查詢合併為單一 by-token 端點

**Decision**：場地層級的計分板/控制板連結，其「畫面初始化資料」與「心跳檢查（5 分鐘週期）」使用同一支端點 `GET /courts/by-token/{token}`——依傳入的 token 判斷是命中 `scoreboard_token` 還是 `control_panel_token`，回傳對應的 `link_type`、目前版本號、`deleted`/`group_disbanded` 狀態；初次載入與定期心跳皆呼叫同一支端點，不另建 `/link-status` 端點。全部場地控制板比照設計 `GET /groups/by-all-courts-token/{token}`。

**Rationale**：FR-034 僅要求「場地層級連結與團層級連結（全部場地控制板）之心跳檢查 MUST 使用彼此獨立的檢查端點」——即場地層級與團層級兩者之間要獨立，並未要求「初始化」與「心跳」是兩支不同端點；兩者回傳內容本質相同（目前連結是否仍有效、版本號、所屬團/場地是否已被刪除或解散），合併可減少端點數量與前端程式碼重複。以 token（而非內部 UUID `court_id`/`group_id`）作為查詢鍵，是因為這兩個端點刻意設計為「無需登入」（見 spec 原始描述「不需要登入」），呼叫方在拿到連結的當下只知道 token，不應要求其額外持有內部 ID。

**Alternatives considered**：延續 `specs/architecture.md` §3 草稿中以 `{court_id}` 為路徑參數的寫法——否決，該草稿本身標註「依 token 解析」卻誤用 `{court_id}` 作路徑參數命名，屬於架構文件早期粗略草案的筆誤，本 plan 予以修正並以本文件記錄理由。

## 5. 決議：場地重新命名不設獨立樂觀鎖版本欄位

**Decision**：`PATCH /courts/{court_id}`（重新命名）不比照 Group 的 `base_settings_version` 模式新增專屬版本欄位，改以「最後寫入為準」+ 資料庫唯一索引（`ux_courts_group_name_active`）作為並發防呆——若兩位管理員幾乎同時將不同場地改成同一個名稱，其中一方的請求會被唯一索引擋下並回傳 `COURT_NAME_ALREADY_EXISTS`，不會造成資料損毀，僅可能造成使用者需重新整理後再次嘗試。

**Rationale**：spec 之 Key Entities 段落明確列出 Court 僅有「計分板連結版本」「控制板連結版本」兩個各自獨立的版本欄位（呼應 FR-036），並未定義任何用於一般欄位編輯（重新命名）的版本欄位；且 spec 全文的驗收情境（US1、Edge Cases）僅涉及唯一性檢查，未提及重新命名的併發衝突情境或 409 回應。因此本 feature 不引入 spec 未定義的欄位，維持最小驗證範圍。

**Alternatives considered**：新增泛用 `version` 欄位供未來所有欄位編輯共用——否決，spec 未要求，且與既有 Group 之「互不相關面向各自獨立版本」原則（FR-028/FR-036）矛盾——重新命名若真的需要版本化，應是獨立於連結版本之外的第三個欄位，屬於超出目前規格範圍的臆測性設計。

## 6. 決議：QR Code 產生方式沿用既定前端套件

**Decision**：沿用 `specs/architecture.md` 已選定的 `angularx-qrcode`（`apps/web` 已安裝，版本鎖定 20.0.0）產生計分板/控制板/全部場地控制板連結的 QR Code，QR 內容為完整可直接開啟的網址（`{origin}/scoreboard/{token}`、`{origin}/control/{token}`、`{origin}/control/all/{token}`），非僅 token 本身。

**Rationale**：001 已安裝此套件但尚未有機會實際使用（001 沒有任何連結/QR 需求）；002 是本專案第一個真正渲染 QR Code 的 feature，沿用既定選型，不重新評估。

**Alternatives considered**：無——已於專案 `architecture.md` 定案，本 feature 僅為首次消費此套件的模組。
