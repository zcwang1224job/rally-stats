# API Contract Addendum: 賽程相關回應的新增欄位

延伸 `specs/003-schedule-rotation/contracts/schedule-api.md`、
`specs/005-member-view/contracts/member-view-api.md` 與
`specs/011-round-robin-scheduling` 的本輪賽程清單。**不新增端點**；
所有新欄位皆有預設值，舊版前端忽略它們即可，新版前端遇到舊版後端
（欄位缺省）時視為「沒有人休息」。

推導規則見 [data-model.md](../data-model.md)。

## `ScheduleResponse`

出現在 `GET /groups/{id}/schedule`（管理員）與
`GET /groups/{id}/member-schedule`（成員）——同一個建構函式
`build_schedule_snapshot()`，兩邊同時生效。

### `roster[]`（`RosterScheduleStatus`）新增

| 欄位 | 型別 | 說明 |
|---|---|---|
| `resting` | `bool` | 是否休息中。 |
| `resting_since` | `datetime \| null` | 開始休息的時間（UTC ISO 8601）；準備中為 `null`。 |
| `partner_roster_entry_id` | `string \| null` | 只在固定搭檔循環賽、且他在當前這一輪有場次時有值：這一輪與他同隊的人。 |

名單**仍包含**休息中的球員（他們還在團裡）；`wait_count` 照常回傳，
休息期間數值不變。

### `courts[].waiting_reason` 新增兩個值

| 值 | 說明 | 畫面文字（語系檔） |
|---|---|---|
| `held_for_rest` | 還有排隊中的場次，但全部在等休息中的球員。 | 「等待休息中的球員」 |
| `not_enough_ready` | 連續輪轉下，準備中的閒置球員不足以排出一場，且有人在休息。 | 「準備中的球員不足」 |

前端遇到不認得的值 MUST 退回既有的 `no_queued_match` 文字（舊版前端
搭新版後端時不會顯示空白）。

### `courts[].next_up`（`NextUpPreview`）新增

```json
{
  "match_id": "uuid",
  "participants": [ /* 替補之後的陣容 */ ],
  "substitutions": [
    {
      "resting":    { "roster_entry_id": "uuid", "nickname": "小明" },
      "substitute": { "roster_entry_id": "uuid", "nickname": "阿華" }
    }
  ]
}
```

- `participants` 是**實際會上場**的四個人；`substitutions` 說明其中誰是
  代替誰。沒有替補時為空陣列。
- 預告與實際叫場使用同一個判斷（FR-015）：同一份狀態下，預告的場次與
  陣容 MUST 與隨後真正被叫上場的相同。
- 預告是唯讀的——在真正叫場之前，資料庫裡該場次的參賽者仍是原本的
  四個人；休息者在那之前按「準備好了」，預告就變回原陣容。

## `RoundMatchesResponse`

出現在管理員與成員的本輪賽程清單端點（同一個建構函式
`build_round_matches_list()`）。

### `matches[]`（`RoundMatchSummary`）新增

| 欄位 | 型別 | 說明 |
|---|---|---|
| `rest_effect` | `"held" \| "substitute" \| null` | 只對 `queued` 且含休息中球員的場次有值。`held`＝保留等他回來；`substitute`＝輪到時由替補上場。 |

### 回應層級新增

```json
"waiting_on_rest": {
  "match_count": 2,
  "players": [ { "roster_entry_id": "uuid", "nickname": "小明" } ],
  "stalled": true
}
```

- `match_count`：`rest_effect` 不為 `null` 的場次數；為 0 時整個欄位為
  `null`。
- `players`：這些場次裡休息中的球員（不重複，依加入順序）。
- `stalled`：這一輪是否已被休息卡住（沒有比賽在打、剩下的場次全部
  無法上場）。管理頁據此決定提示的醒目程度，並在未開啟「自動進入
  下一輪」時提示管理員可以幫他按「準備好了」或進入下一輪（FR-021）。

### `sitting_out[]`

既有欄位（這一輪沒有任何場次的在團成員）——**不含**休息中的球員。
他們沒有場次是因為自己選擇休息，已由名單上的標示表達；放進這個清單
會被誤讀成「輪空」。

## 不變的部分

- 排行榜、對戰紀錄、個人統計、最終排名的所有回應**零變動**（FR-028）。
- `ParticipantSummary` 不加休息欄位——它被比分、紀錄、即時事件大量
  共用；需要知道某位參賽者是否休息的畫面，以 `roster_entry_id` 對照
  `roster[]` 即可。
