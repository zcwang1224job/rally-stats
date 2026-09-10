# Research: 開團流程優化——合理預設值與自動預設場地

5 decisions。不新增資料表、不需要新 migration。

## 1. 團名預設值：後端於 `create_group()` 內計算，前端只送「留空」

**Decision**：`CreateGroupRequest.name` 型別由 `str` 改為 `str | None =
None`，其 `field_validator` 改為：`None` 或去除頭尾空白後為空字串時，
一律正規化為 `None`（視同「未提供」）；非空時維持既有 1–30 字長度檢查。
`create_group()`（`group/service.py:133`）內，把既有第 190 行「計算
建立者暱稱」（`nickname = member.nickname if member else
stripped_creator_nickname`）的時機提前到既有的暱稱驗證檢查之後
（第 149–153 行之後）、組出 `Group(...)` 之前；若 `payload.name` 為
`None`，MUST 用這個已提前算出的暱稱組出預設團名
`f"{nickname}的羽球團"` 作為 `Group.name`。

**Rationale**：spec.md FR-001 的預設團名規則依賴「建立者暱稱」——這個值
本來就要在既有的會員/訪客暱稱驗證通過後才能確定，`create_group()`
內本來就會算出這個值（只是原本用在稍後建立 `RosterEntry`時），提前
計算並重複使用同一個變數，不需要另外設計一套判斷邏輯。放在後端計算
（而非前端組字串後送出）符合憲章原則 X——避免前後端各自組出不同的
預設團名字串（例如未來暱稱正規化規則變動時，只需要改後端一處）。

**Alternatives considered**：
- 前端在使用者送出前，若團名欄位為空就自行組出「{暱稱}的羽球團」再
  送給後端——被拒絕，違反憲章原則 X（伺服器為唯一可信來源）；且訪客
  身份時，暱稱本身也是同一個表單的另一個欄位，前端組字串的時機容易
  與最終送出的暱稦不同步（例如使用者送出前一刻才改了暱稱欄位）。

## 2. 自動建立「球場一」：在既有 `create_group()` 交易內直接 `session.add()`，不呼叫既有 `create_court()`

**Decision**：`create_group()`（`group/service.py`）在既有
`session.add(roster_entry)`（第 203 行）之後、既有的單一 `await
session.commit()`（第 205 行）之前，新增
`session.add(Court(group_id=group.id, name="球場一"))`；commit 後比照
既有 `group`/`roster_entry` 一併 `await session.refresh()`，並沿用既有
`create_court()`（`court/service.py:27`）已定義的 `court.added` 即時
事件 payload 形狀（`{"court_id": ..., "name": ...}`），對
`group_notifications_channel(group_id)` 發布同一種事件，讓假設性的
「剛好在這個瞬間已經打開全部場地控制板」情境也能收到通知（雖然實務上
建團當下不太可能已有人在看）。**不**直接呼叫既有的
`create_court()` 服務函式本身——該函式內建自己的
`await session.commit()` 與 `IntegrityError` 例外處理，若在
`create_group()` 尚未完成建立團本身之前就先呼叫它，會提前把整個
session（含尚未組裝完整的 Group/RosterEntry）一併 commit，破壞
FR-007「球場建立與團建立為同一個原子性單位」的要求。

**Rationale**：這個新球場的名稱是系統內部常數（不是使用者輸入），
不可能與「這個全新團」內任何既有球場撞名（此時這個團根本還沒有任何
其他球場），因此不需要 `create_court()` 內那段處理使用者輸入撞名的
`IntegrityError` 例外處理；直接在既有交易內 `session.add()`，讓它與
`Group`/`RosterEntry` 共用同一次 `commit()`，是滿足 FR-007（失敗時
不留孤兒球場）最直接的做法——失敗自然導致整個 session 不 commit，
不需要額外的補償/回滾邏輯。

**Alternatives considered**：
- 呼叫既有 `create_court()`——被拒絕，理由如上，會破壞交易原子性。
- 團建立成功、回應給前端之後，另外再發一個 API 請求建立球場——被
  拒絕，多一次網路往返、且無法滿足 FR-007「同一交易」的要求（團建立
  成功但球場建立失敗的中間態會被使用者看到）。

## 3. 球場更名前端：既有服務方法直接可用，新增畫面入口與遺失的測試覆蓋

**Decision**：`CourtManagementService.renameCourt(groupId, courtId,
name)`（`court-management.service.ts:36`）與後端
`PATCH /courts/{court_id}`（`court/router.py:87`，`rename_court()`，
`court/service.py:68`）皆已存在且邏輯完整（含既有
`COURT_NAME_ALREADY_EXISTS`／`COURT_DELETED` 錯誤處理），只是從未被
任何畫面呼叫、也從未被任何既有測試覆蓋過（單元或契約測試皆無）。
本 feature 在既有 `court-list.component`（`court-list.component.ts`）
新增「重新命名」狀態與操作——比照既有「新增球場」表單
（`Validators.required`／`Validators.maxLength(20)`）的既有驗證規則，
點擊「重新命名」時該筆球場列切換為可編輯的文字輸入，確認送出後呼叫
既有 `renameCourt()`，成功後 `load()` 重新整理列表；錯誤時沿用既有
`errorKey` 呈現慣例（`COURT_NAME_ALREADY_EXISTS`／`COURT_DELETED` 的
既有 i18n 字串直接重用）。同時新增單元測試（`rename_court()`）與契約
測試（`PATCH /courts/{court_id}`），補齊這條既有路徑原本完全空白的
測試覆蓋（憲章原則 II）。

**Rationale**：既然更名的後端能力與前端 API 呼叫方法都已經正確存在，
重新設計一套機制只會違反憲章原則 VI（可維護性/不重複實作）；真正
缺少的是「使用者從畫面上能不能觸發它」與「這條路徑有沒有測試保護」
兩件事，這正是本 feature 該補的範圍。

**Alternatives considered**：
- 用彈出視窗（modal）取代列內編輯——被拒絕，既有刪除確認已經用了
  `ConfirmDialogComponent`（是/否二元操作），更名需要文字輸入，
  硬套同一個元件會需要修改其既有介面；列內編輯沿用既有「新增球場」
  表單同一套輸入/驗證慣例，實作與既有畫面風格更一致，也不需要新增
  共用元件。

## 4. 比賽模式/人數上限/排程機制：純前端表單初始值調整，後端不變

**Decision**：`create-group.component.ts` 既有表單初始值
（`match_mode: ['doubles' as MatchMode, ...]`）改為
`'singles' as MatchMode`；`max_members`（既有 `4`）與
`scheduling_mechanism`（既有 `'fair_rotation'`）**維持不動**——這兩項
本來就已經符合 spec.md FR-003/FR-004 的要求，不需要任何修改。後端
`CreateGroupRequest` 的 `match_mode`／`max_members`／
`scheduling_mechanism` 三個欄位維持既有的必填語意不變（spec.md
Assumptions：預設值只決定表單「尚未被使用者更動」時的初始畫面狀態，
不改變欄位本身是否必填）。

**Rationale**：spec.md 對這三項的描述是「開團表單的...初始值」，而非
「留空時系統代填」——這三個欄位在既有實作中本來就是有固定初始值的
下拉選單/數字輸入（不存在「使用者看到的是空的」這種狀態），與「團名」
欄位（既有文字輸入框、原本允許看起來空白）性質不同，不需要也不應該
比照團名引入後端「留空生預設值」的邏輯，維持現狀最簡單、風險最低。

**Alternatives considered**：
- 讓後端也把這三個欄位改成可選、留空時代入預設值——被拒絕，這三個
  欄位在前端本來就恆有值（沒有「留空」這個狀態需要處理），後端跟著
  改動只會憑空增加程式碼與測試負擔，卻沒有對應的使用情境。

## 5. 團名欄位不再必填後的既有前端驗證訊息清理

**Decision**：`create-group.component.ts` 的 `name` 表單控制項移除
`Validators.required`（保留 `Validators.maxLength(30)`）；
`create-group.component.html` 內既有「團名必填」的錯誤訊息區塊
（`form.controls.name.errors?.['required']`）一併移除；既有
`createGroup.nameRequired` 語系字串因此不再被任何程式碼引用，一併從
`zh-TW.json` 移除（而非保留成用不到的孤兒字串，憲章原則 VIII）。
`namePlaceholder` 的既有文案（「例如：週三夜羽球團」）調整為同時提示
「留空將自動帶入預設團名」的行為。

**Rationale**：`Validators.required` 若保留，使用者在前端就完全無法
把團名留空送出，直接與 FR-001「MUST 允許留空直接送出」矛盾——這是
本次調整的必要項，而非可選的清理工作；孤兒語系字串則是連帶的既有
清理，避免留下死碼。

**Alternatives considered**：無——`Validators.required` 與 FR-001 直接
衝突，沒有保留的空間。
