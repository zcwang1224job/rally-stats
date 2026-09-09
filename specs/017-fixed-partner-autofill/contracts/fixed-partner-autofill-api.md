# API Contract: 固定搭檔循環賽——手動配對後，剩餘未配對者自動隨機配對

延伸既有 `specs/011-round-robin-scheduling` 之搭檔相關端點；新增 1 個
端點，擴充 1 個既有端點的請求 body（不改變既有回應形狀）。錯誤代碼皆為
語意化字串（憲章原則 VIII），由前端依語系檔轉換顯示。皆為管理員限定
（`require_admin`），沿用既有 `GET`/`PATCH /groups/{group_id}/partnerships`
的授權模式。

## `POST /groups/{group_id}/partnerships/random-preview`（新增）

**用途**：搭檔設定畫面上「剩下的人隨機配對」操作——針對目前所有沒有
正式搭檔的現役成員，計算一組隨機配對供管理員預覽/調整（FR-001，US2）。
**純運算、不寫入任何資料**——每次呼叫都是全新計算，不會影響既有正式
搭檔資料，也不會留下任何伺服器端狀態。

**權限**：`require_admin`（沿用既有搭檔相關端點的既有授權模式）。

**回應** `200`：`TemporaryPairingsResponse`（見 data-model.md）：

```json
{
  "pairings": [
    {
      "player_a": { "roster_entry_id": "uuid", "nickname": "小明" },
      "player_b": { "roster_entry_id": "uuid", "nickname": "小華" }
    }
  ]
}
```

`pairings` 涵蓋呼叫當下所有未配對現役成員；若當下沒有任何未配對成員，
回傳 `{ "pairings": [] }`（`200`，非錯誤）。

**錯誤**：
- `ADMIN_TOKEN_INVALID`（401）：既有語意。
- `SCHEDULING_MECHANISM_MISMATCH`（409）：團的比賽模式不是「固定搭檔」
  （既有錯誤碼，沿用既有語意）。
- `PARTNER_SOURCE_MISMATCH`（409，新增）：團目前的配對來源不是「手動
  配對」（research.md #4——刻意與 `SCHEDULING_MECHANISM_MISMATCH` 分開，
  代表不同原因）。

---

## `POST /groups/{group_id}/next-round`（既有端點，請求 body 新增可選欄位）

**用途不變**：強制結束目前輪次、產生下一輪（既有 FR-031）。

**變更**：既有請求完全無 body；新增可選的 `NextRoundRequest` body（見
data-model.md）：

```json
{
  "temporary_pairings": [
    { "player_a_id": "uuid", "player_b_id": "uuid" }
  ]
}
```

`temporary_pairings` 省略、為 `null`、或空陣列，行為與擴充前完全一致
（既有呼叫端、既有排點機制皆零行為變動——US3）。

**新增行為**（僅 `scheduling_mechanism == "fixed_partner"` 且
`partner_source == "manual"` 時生效，見 data-model.md 之三段聯集邏輯）：

- 若管理員先呼叫過 `random-preview` 並在前端調整過結果，把最終結果放進
  `temporary_pairings` 一併送出：系統 MUST 驗證每一組是否仍然只涉及
  「目前確實未配對」的現役成員，驗證通過的組合 MUST 直接採用、MUST NOT
  重新隨機配對（FR-007）；驗證未通過的組合 MUST 被捨棄——包含同一位成員
  在提交的 `temporary_pairings` 中出現超過一次的情形：所有包含該重複
  成員的組合 MUST 一律視為無效（FR-003）。
- 不論 `temporary_pairings` 是否有帶、或帶了之後是否仍有未涵蓋到的
  未配對現役成員：系統 MUST 在產生賽程的當下，把這些人自動隨機配對
  補齊，確保賽程涵蓋所有現役成員（FR-002）。
- 上述過程中產生的暫時配對，MUST NOT 被寫入 `partnerships` 資料表
  （FR-004）。

**回應/錯誤**：既有形狀（`ScheduleResponse`）與既有錯誤碼
（`ADMIN_TOKEN_INVALID`、`NO_COURTS_AVAILABLE`、
`ROUND_GENERATION_IN_PROGRESS`、`FIXED_PARTNER_REQUIRES_EVEN_HEADCOUNT`）
完全不變，不新增任何錯誤碼——`temporary_pairings` 內容有問題時是「靜默
捨棄無效組合＋自動補齊」，MUST NOT 讓整個「產生下一輪賽程」請求失敗
（該端點既有的「不可恢復地強制結束目前輪次」語意不應該因為一份暫時
配對草稿過期而被打斷）。

---

## 兩個端點的共通行為

- 皆不觸發任何即時廣播（Ably）——`random-preview` 純運算無副作用；
  `next-round` 沿用既有的賽程產生廣播行為，不新增額外事件。
- `temporary_pairings`／`random-preview` 回應中的配對組合，每次都是
  「當下」重新計算的結果，不保證與前一次呼叫的結果相同（Edge Cases
  「多次觸發」）。
