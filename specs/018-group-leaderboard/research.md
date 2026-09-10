# Research: 團內即時排行榜（強化既有戰績頁）

6 decisions。不新增資料表、不需要新 migration（戰績頁排名刻意設計為完全
由既有比賽資料即時計算而得，見 spec.md Assumptions）。

## 1. 即時廣播：在既有的「比賽完成」發布點上，多發一則群組廣播事件

**Decision**：整個後端只有一處會把 `Match.status` 設為 `"completed"`——
`apply_score_delta()` 內、緊接著呼叫既有 `_publish_match_ended()` 之前
（`schedule/service.py:1583`）。在 `_publish_match_ended()` 內新增一則對
`group_notifications_channel(group_id)` 的 `publish(..., "standings.updated",
{"group_id": group_id})`，與既有對 `court_channel` 發布的 `"match.ended"`
事件並存、互不影響——`court_channel` 服務的是該場地的計分板/控制板，
`group_notifications_channel` 服務的是任何目前開著戰績頁的團內成員（不限
特定場地）。前端收到這則事件後，比照既有 `notification.service.ts` 的
既定模式，直接整包重新呼叫 `GET /groups/{group_id}/standings`（不在前端
用事件 payload 做任何增量計算），維持「伺服器為唯一可信來源」（憲章
原則 X）。

**Rationale**：`_publish_match_ended()` 是全系統唯一、保證涵蓋所有「比賽
變成已完成」情境的發布點（不論是一般得分致勝，未來若新增其他致勝路徑
也會經過這裡）——不需要在多個呼叫端各自記得要發布戰績頁更新事件。
`group_notifications_channel` 本來就是「全團廣播、不分場地」用途的既有
頻道（`member.left`、`link.regenerated` 皆用這個頻道），戰績頁更新沿用
同一頻道，前端只需要訂閱一次即可涵蓋全團所有場地的比賽結果，不需要
先查詢場地清單、也不需要管理多個訂閱的生命週期。

**Alternatives considered**：
- 讓戰績頁前端直接訂閱該團所有場地各自的 `court_channel`——被拒絕，
  需要先知道場地清單、且訂閱數會隨場地數量變動，複雜度不成比例；
  `group_notifications_channel` 本來就是為了這種「跟特定場地無關的
  全團事件」而存在。
- 讓事件 payload 帶完整的新排名結果，前端直接套用不用重新呼叫 API——
  被拒絕，違反憲章原則 X：排名計算（尤其並列名次的次要排序邏輯）
  MUST 只在伺服器端算一次，所有客戶端看到的結果 MUST 一致；讓前端各自
  根據 payload 片段推算排名，等於把排序邏輯複製一份到前端，兩處實作
  之後很容易產生不一致。

## 2. 排序與名次計算：擴充既有 `build_group_standings()`，在既有回應中新增 `rank`／`total_wins`／`total_losses` 欄位

**Decision**：`build_group_standings()`（`group/service.py:858`）在既有
「依 `RosterEntry.joined_at` 查詢現役成員、逐輪累計勝敗」的邏輯之後，
新增一段後處理：加總每位成員的 `total_wins`／`total_losses`，依「勝場數
（`total_wins`）由高到低」排序，並依 spec.md FR-006／US3 之規則算出
`rank`（並列時同一數字，緊接其後的名次依人數跳號——即 standard
competition ranking／「1224」排名法，而非 dense ranking／「1223」；並列時
的次要排序依據固定是 `joined_at`，早加入者排前面）。這三個新欄位
（`rank`、`total_wins`、`total_losses`）加進既有 `MemberStandingRow`，
既有的 `rounds`（逐輪明細）、`current_round_number` 欄位完全不變（spec.md
Assumptions：逐輪細目予以保留）。

**Rationale**：現有前端 `totalRecord()` 是純前端加總、且完全沒有排序——
如果排序/名次規則（尤其並列時的次要依據）留給前端各自實作，會重複
違反憲章原則 X 的「單一計算來源」；而且前端目前收到的 `MemberStandingRow`
根本沒有 `joined_at` 欄位，要在前端做次要排序還得額外多傳一個欄位，
不如直接在後端把排序做完、把結果（`rank`）直接算好給前端渲染最單純。

**Alternatives considered**：
- 前端沿用既有 `totalRecord()` 自己加總，再額外傳一個 `joined_at` 欄位
  讓前端自己排序、自己算並列跳號——被拒絕，理由同上，且並列跳號演算法
  （standard competition ranking）如果各自實作，前後端或未來新增的呼叫端
  容易寫出不一致的版本。

## 3. 離團成員排除：查詢條件從「全部曾經加入過的人」改為「目前現役」

**Decision**：`build_group_standings()` 既有的 `roster_result` 查詢
（`select(RosterEntry).where(RosterEntry.group_id == group.id)`，目前
沒有依 `status` 過濾）改為額外加上 `RosterEntry.status == "active"`——
只有現役成員才會出現在回傳的 `members` 清單裡。這個過濾只影響「誰會被
列一列在清單上」，不影響 `participation` 的計算來源（`MatchParticipant`/
`Match` 資料表本身不因對手離團而改變），所以離團者過去比賽貢獻給現役
對手的勝負，依然正確累計在對手身上（spec.md FR-008／SC-005）。

**Rationale**：這是既有函式裡唯一需要改動查詢條件的地方；其餘「勝負怎麼
算」的邏輯完全不需要更動，因為勝負本來就是從 `MatchParticipant`／`Match`
關聯查出來的，不是從「對手現在還在不在團」反推。

**Alternatives considered**：
- 保留查詢全部曾加入過的人，改成在回應組裝完後於記憶體中過濾掉非現役
  者——被拒絕，這個過濾條件直接下在既有的 SQL `WHERE` 子句最簡單，也
  避免多查出、多組裝了一批之後又要丟棄的資料。

## 4. 「重新連線時強制刷新」：直接重用既有 `ReconnectRefetchService`

**Decision**：`standings.component.ts` 直接注入既有的
`ReconnectRefetchService`（`core/realtime/reconnect-refetch.service.ts`，
已被 `notification.service.ts` 使用的同一支服務），訂閱其
`onReconnect()`，收到事件時呼叫既有 `getStandings()` 重新拉取——不新增
任何斷線提示 UI 元件（spec.md FR-012／Clarifications Q4：本畫面純唯讀，
比照 012-realtime-notifications 而非 007-live-scoreboard 的既定作法）。

**Rationale**：`ReconnectRefetchService.onReconnect()` 本來就是為了
「這個畫面的資料在斷線期間可能過期，重新連上時強制重新拉取」這個確切
情境而存在的共用元件，`notification.service.ts` 已經用同一支服務實作
一模一樣的模式（斷線重連 → 呼叫 `refetchUnreadCount()`）——戰績頁直接
比照辦理即可，不需要新的抽象。

**Alternatives considered**：無——這是既有共用元件的直接重用，沒有需要
評估的替代方案。

## 5. 前端訂閱：重用既有 `RealtimeService.subscribe()`，訂閱 `group_notifications_channel` 的新事件

**Decision**：`standings.component.ts` 注入既有 `RealtimeService`，呼叫
`subscribe(groupNotificationsChannel(groupId), 'standings.updated')`（前端
需新增一個小工具函式或直接組字串，比照 `notification.service.ts` 組
`member:${memberId}:notifications` 頻道名稱的既有寫法），訂閱到事件後呼叫
`getStandings()` 重新拉取。元件銷毀時取消訂閱（沿用 `RealtimeService.
subscribe()` 既有的 teardown 行為，回傳的 `Observable` unsubscribe 時
自動呼叫 `channel.unsubscribe()`）。

**Rationale**：`RealtimeService.subscribe()` 已經是全站唯一、標準化的
Ably 訂閱介面（供計分板、通知功能共用），戰績頁沒有理由另外接一套訂閱
邏輯。

**Alternatives considered**：無——同決策 4，這是既有共用元件的直接重用。

## 6. 並列名次演算法之精確定義

**Decision**：採用 standard competition ranking（俗稱「1224」排名法）：
若 N 位成員的 `total_wins` 嚴格大於某位成員，則該成員的 `rank` =
N + 1（不論這 N 位成員之間彼此是否也有並列）。例如 4 人戰績為
[5 勝, 3 勝, 3 勝, 1 勝]，名次為 [1, 2, 2, 4]——並列第 2 名的兩人之後，
下一位直接是第 4 名，不是第 3 名。

**Rationale**：spec.md US3 驗收情境 1 已經明確舉例「兩人並列第 2 名，
下一位是第 4 名」，這就是 standard competition ranking 的定義（相對於
dense ranking 「1223」——下一位會是第 3 名）；本決策只是把規格裡已經
用範例定案的演算法，用精確公式記錄下來，供實作與測試對照，不是一個
待決策的開放問題。

**Alternatives considered**：dense ranking（1223）——與 spec.md 驗收情境
的具體範例矛盾，予以排除。
