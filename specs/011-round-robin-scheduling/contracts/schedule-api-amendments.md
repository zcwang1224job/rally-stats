# API Contract Amendments: 循環賽賽程排程

本文件僅記錄相對於 `specs/003-schedule-rotation/contracts/schedule-api.md` 的**變更**與**新增**部分；未提及的端點與欄位維持該份既有合約不變。

## 既有端點：行為變更（形狀不變）

### GET /groups/{group_id}/schedule

**Response 形狀完全不變**（見 003 契約）。行為變更：

- `courts[].current_match`／`waiting_reason` 的計算邏輯不變，但底層「該場地下一場可領取的排隊中比賽」查詢新增「跳過所有參與者正在其他場地進行中」的條件（research.md #4）——對呼叫端（前端）完全透明，回應形狀與既有欄位語意不變。
- `roster[].wait_count`：當 `scheduling_mechanism` 為三種演算法機制之一時，此值為切換到該機制當下的最後數值（凍結，不再變動）；當為 `manual` 時行為完全不變（research.md #5）。前端徽章顯示邏輯需一併調整（見 plan.md 前端任務），本契約不因此改變欄位本身的型別或存在與否。

### POST /groups/{group_id}/next-round

**Response 形狀完全不變**。行為變更：內部生成邏輯依 `scheduling_mechanism` 改採循環法（單打／固定搭檔，research.md #1）或多波次貪婪迴圈（個人混搭，research.md #2），賽程表場次數大幅增加，但本端點本身回傳的仍是「重新產生後的最新狀態」（同 `GET .../schedule`），呼叫端無需感知內部場次數量的變化。

**新增錯誤代碼**：

- `FIXED_PARTNER_REQUIRES_EVEN_HEADCOUNT`（400）：`scheduling_mechanism = fixed_partner` 且觸發 Round 生成當下，在場人數為奇數時回傳；不產生賽程表、`current_round_number` 不變（比照既有 `NO_COURTS_AVAILABLE` 之防呆風格）。

## 既有端點：Request 欄位新增

### PATCH /groups/{group_id}（既有的團設定編輯端點，見 001 契約）

**Request 新增欄位**（皆為選填，比照既有 `scheduling_mechanism` 等欄位的 partial-update 風格）：

```json
{
  "partner_source": "manual"
}
```

- `partner_source`：`"manual"` | `"auto"`。僅在當下（或本次一併送出的）`scheduling_mechanism` 為 `fixed_partner` 時允許設定為非預設值；若團當下的 `scheduling_mechanism` 不是 `fixed_partner` 且送出此欄位，系統 MUST 忽略此欄位並回傳成功（比照其餘機制專屬設定於非對應機制下的既有寬容處理慣例），不視為驗證錯誤。
- 切換此欄位本身 MUST NOT 觸發 `partnerships` 表的任何寫入（research.md #6）；若同一次請求「同時」將 `scheduling_mechanism` 從其他機制切換為 `fixed_partner`，既有的 `auto_pair_on_enter_fixed_partner()`（依加入順序自動配對、寫入 `partnerships`）仍會照既有行為執行一次，作為 `partner_source = 'manual'` 情境下的初始值——這與新的 `partner_source = 'auto'` 是兩件不衝突的事（見 research.md #6 命名澄清）。

**Response 新增欄位**：`AdminGroupResponse` 新增 `partner_source` 欄位，回傳團目前生效的值。

**錯誤代碼**：沿用既有 `ADMIN_TOKEN_INVALID`、`VERSION_CONFLICT`，不新增。

## 契約層級的既有假設變更說明

003 契約文件中「Response 200：同 GET .../schedule 之結構」等描述皆維持成立，本次變更完全發生在「該結構底下實際會有多少筆比賽資料」與「新增一個團設定欄位」，未變更任何既有端點的路徑、方法或既有欄位的型別。
