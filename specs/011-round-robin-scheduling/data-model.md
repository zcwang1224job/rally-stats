# Data Model: 循環賽賽程排程

## 新增／修改欄位

### `groups.partner_source`（新欄位，research.md #6）

| 欄位 | 型別 | 說明 |
|---|---|---|
| `partner_source` | `VARCHAR` 列舉：`'manual'` \| `'auto'`，`NOT NULL DEFAULT 'manual'` | 僅在 `scheduling_mechanism = 'fixed_partner'` 時有意義；決定固定搭檔循環賽的隊伍組成來源。`'manual'` 讀取既有 `partnerships` 表；`'auto'` 於每次 Round 生成當下即時計算，不寫回 `partnerships` 表。切換此欄位本身 MUST NOT 新增、修改或刪除任何 `partnerships` 資料列（research.md #6）。 |

新增 Alembic migration：`ALTER TABLE groups ADD COLUMN partner_source VARCHAR NOT NULL DEFAULT 'manual'`，既有資料列一律回填為 `'manual'`（等同既有行為，向後相容——現行所有固定搭檔循環賽團隊都是手動搭檔設定）。

## 既有實體（本 feature 讀寫規則變更，schema 不變）

### `Match` / `MatchParticipant`（003 owns，schema 不變）

- 本 feature 大幅增加同一 `round_number` 底下的 `Match` 筆數（從「場地數量」變成「C(n,2)」或多波次貪婪迴圈的累積場次數），但欄位與既有約束（`status` 列舉、`round_number`、`court_id` nullable 等）完全不變。
- `create_match_with_participants()` 的呼叫方式不變（`status="queued"`、`court_id=None`），只是呼叫次數變多、由新的迴圈函式（循環法／多波次貪婪迴圈）驅動。

### `PairHistory`（003 owns，schema 不變，讀取語意增加一項限制）

- 寫入時機與計數語意完全沿用既有決議（同場比賽任兩人皆計一次，建立當下即累加，不因 `abandoned` 回滾）。
- 本 feature 新增一項讀取端認知：`PairHistory` 數值**不能**單獨用來判斷「兩人是否已當過隊友」（因為它不區分隊友與對手），個人混搭循環賽的「本輪搭檔覆蓋」判斷因此需要另一份執行期狀態（見下方「Round 生成執行期狀態」）而非直接查 `PairHistory`。

### `Partnership`（003 owns，schema 不變）

- `partner_source = 'manual'` 時的隊伍組成資料來源，讀寫方式完全不變（管理員於搭檔設定畫面手動調整）。
- `partner_source = 'auto'` 時，本 feature 產生的隊伍組成 MUST NOT 寫入此表——此表在 `'auto'` 模式下維持不動（可能是空的、也可能是先前 `'manual'` 模式遺留的既有資料，等待管理員切回 `'manual'` 時繼續使用）。

### `RosterEntry.wait_count`（001 owns，schema 不變，寫入/讀取語意窄化）

- 演算法排程機制（`fair_rotation`／`fixed_partner`／`individual_mixed`）的 Round 生成路徑 MUST NOT 再讀取或寫入此欄位（research.md #5）。
- `scheduling_mechanism = 'manual'` 時的既有讀寫行為（`manual_assign()`、`apply_wait_count_updates()`）完全不變。
- 欄位本身不刪除、不遷移；切換到演算法機制後其數值凍結在切換當下的最後值，不再變動，直到（若曾經）切回手動模式才會繼續更新。

## Round 生成執行期狀態（僅存在於單次函式呼叫的記憶體中，不落地為資料表）

### 「本次 Round 生成中已形成過的隊友組合」集合（research.md #3）

- 型別：`set[tuple[uuid.UUID, uuid.UUID]]`（每個 tuple 依 UUID 排序正規化，確保 `(a, b)` 與 `(b, a)`視為同一組合）。
- 生命週期：僅存在於個人混搭循環賽單次 `generate_next_round()` 呼叫的執行過程中；每完成一波（wave）即更新，函式回傳後即捨棄。
- 用途：判斷多波次貪婪迴圈的停止條件（是否已涵蓋全部 C(n,2) 組合、或連續兩波沒有新組合）。
- 明確排除持久化：函式執行完畢後，該輪「誰跟誰當過隊友」的完整資訊已完整反映在當輪所有 `Match`/`MatchParticipant` 資料列中，可隨時重建，不需要另外儲存。

## 驗證規則（新增／變更）

| 規則 | 涉及欄位 | 依據 |
|---|---|---|
| `partner_source` 僅接受 `'manual'`／`'auto'` 兩種值 | `groups.partner_source` | FR-008 |
| 固定搭檔循環賽（`scheduling_mechanism = 'fixed_partner'`）觸發 Round 生成時，在場人數 MUST 為偶數，否則拒絕並回傳語意化錯誤代碼 | `groups.scheduling_mechanism`、在場 `roster_entries` 計數 | FR-003（沿用既有「零場地防呆」之錯誤回應風格，新增對應錯誤代碼，詳見 contracts） |
| `partner_source` 切換操作本身 MUST NOT 觸發 `partnerships` 資料列的新增/刪除 | `groups.partner_source`、`partnerships` | FR-010（資料庫層級以「切換端點不觸碰 `partnerships` 表」的實作方式保證，非資料庫約束） |
