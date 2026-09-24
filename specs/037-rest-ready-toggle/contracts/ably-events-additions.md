# Ably Event Contract Addendum: 休息／準備切換

延伸 `specs/003-schedule-rotation/contracts/ably-events.md` 與
`specs/005-member-view/contracts/member-view-api.md` 的即時同步段落。
新增一個事件；不新增頻道。

## `roster.restChanged`（新）

**觸發時機**：任一支休息狀態端點（見
[rest-state-api.md](./rest-state-api.md)）成功且狀態**確實改變**
（`changed: true`）之後。no-op 的請求 MUST NOT 發布。

**發布頻道**：`group:{group_id}:notifications`——與 `member.joined`／
`member.left` 同一個頻道，因為它同樣是「名單上某一列變了」。

**發布者**：只有後端（Constitution X）。前端切換成功後 MUST NOT 自行
發布，也 MUST NOT 樂觀更新其他人的畫面。

**Payload**（刻意精簡，比照 `member.left`）：

```json
{ "roster_entry_id": "uuid", "nickname": "小明", "resting": true }
```

**訂閱端預期行為**：當作**重抓的觸發**——收到後重新讀取賽程
（`ScheduleResponse`）與本輪賽程清單，MUST NOT 依 payload 自行修改
本地狀態（與專案內所有既有事件的處理方式一致）。

| 訂閱者 | 檔案 | 行為 |
|---|---|---|
| 成員頁賽程 | `features/group-member-view/member-schedule` | 重抓；自己的切換按鈕以重抓結果為準。 |
| 管理頁 | `features/group-admin/admin-page` | 重抓名單、賽程與本輪賽程清單。 |

斷線重連後的補抓沿用既有的 `reconnect-refetch.service.ts`，不需要
為這個事件另外處理。

## 沿用既有事件的情境

切換之後的收斂流程可能讓場地狀態改變，這些變化以既有事件通知，
不新增事件：

| 情境 | 事件 | 頻道 |
|---|---|---|
| 有場次因此被叫上場（含替補後上場、連續輪轉排出新場次） | `rotation.updated` | 該場地 |
| 任何切換（場地的「下一場預告」與等待原因可能改變） | `match.nextRound` | 每一面場地 |
| 因此觸發自動進入下一輪 | `match.nextRound`（新的 `round_number`）、`rotation.updated` | 同既有換輪流程 |

計分板、控制面板、全場地面板只訂閱場地頻道，靠上表的既有事件即可
保持同步，**不需要**訂閱 `roster.restChanged`。

## 不新增事件的情境（明確排除）

- 休息中的球員離開或被踢——只發既有的 `member.left`，MUST NOT 另發
  `roster.restChanged`。
- 替補在叫場當下發生——替補後的陣容已包含在 `rotation.updated` 的
  `participants` 裡，MUST NOT 另發「被替補」事件；被替補的球員從重抓
  的結果得知自己不在該場。
- 不對個別會員的通知頻道（`member:{id}:notifications`）發任何東西——
  休息狀態不是需要留存的通知。
