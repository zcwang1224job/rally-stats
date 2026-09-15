# Quickstart: 加分時記錄發球者與站位資訊

本功能沒有任何前端畫面（FR-005），驗證方式是後端整合測試 + 直接查詢
資料庫。以下步驟示範如何手動驗證，對應 tasks.md 將展開的自動化測試
（`tests/integration/test_score_serve_record_flow.py`）走的是同一條
路徑。

## 前置準備

沿用既有後端本地開發環境（見 `apps/api/README.md`）：

```bash
cd apps/api
source .venv/bin/activate
export $(grep -v '^#' .env | xargs)
```

需要一場**雙打**比賽（4 位參賽者）來驗證站位公式的完整情境（單打只用
到 2 個站位欄位，是雙打的子集）。

## 驗證情境 1：開賽即初始化發球狀態

1. 透過既有流程建立一個團、一個雙打模式球場、產生一場比賽並讓它進入
   `in_progress`（例如既有 `pull_queued_match_for_court()` 或直接以
   `status="in_progress"` 建立）。
2. 查詢該比賽的 `matches` 資料列。

**預期結果**：`serving_team` 為 `'A'` 或 `'B'` 其中之一（非 `NULL`），
`team_a_reference_server_id`／`team_b_reference_server_id` 皆已填入
（分別是 A、B 隊某一位參賽者的 `roster_entry_id`）。多次重複這個步驟
（建立多場比賽），確認結果不是每次都固定同一隊/同一人（隨機性，029
FR-001/FR-002）。

## 驗證情境 2：加分建立對應的發球紀錄

1. 對情境 1 的比賽呼叫既有加分端點（`side` 選擇目前 `serving_team`，
   `delta=1`）。
2. 查詢 `score_serve_records`，篩選 `match_id` = 該比賽。

**預期結果**：新增一筆資料列，`server_team` 等於呼叫前的
`serving_team`，`server_roster_entry_id` 等於呼叫前該隊的
`reference_server`；四個站位欄位皆非 `NULL`（雙打），且
`server_roster_entry_id` 等於其中一個站位欄位的值（依當下比分奇偶，
見 data-model.md 站位公式）。再次查詢 `matches`，確認
`serving_team`／兩個 `reference_server` 欄位維持不變（同隊繼續發球，
不是 side-out）。

## 驗證情境 3：對方得分（side-out）換邊發球

1. 對同一場比賽，改用**另一隊**（非目前 `serving_team`）呼叫加分端點
   （`delta=1`）。
2. 查詢 `matches`。

**預期結果**：`serving_team` 已切換為剛剛得分的那一隊；該隊（雙打）
的 `reference_server` 已換成該隊「另一位」球員（跟情境 1 初始化的值
不同）；另一隊的 `reference_server` 維持不變。查詢
`score_serve_records`，確認新增了一筆對應這次加分的紀錄，`server_team`
與新的 `serving_team` 一致。

## 驗證情境 4：`-1` 不建立紀錄、不改動發球狀態

1. 對同一場比賽呼叫既有的 `delta=-1` 修正端點。
2. 分別查詢 `matches` 與 `score_serve_records`（篩選該比賽）。

**預期結果**：`score_serve_records` 的筆數與這次呼叫前完全相同（沒有
新增任何一筆）；`matches` 的 `serving_team`／兩個 `reference_server`
欄位維持修正前的值，未被這次 `-1` 改動。

## 驗證情境 5：單打比賽的站位欄位

1. 重複情境 1–3，改用單打模式的比賽。

**預期結果**：每筆 `score_serve_records` 的
`team_a_left_roster_entry_id`／`team_a_right_roster_entry_id` 恰有一個
非 `NULL`（另一個是 `NULL`）；B 隊比照（呼應 029 FR-006「單打時另外
兩個角落保持空白」）。

## 驗證情境 6：連結重新產生不影響既有紀錄

1. 對情境 2–3 已經累積若干筆 `score_serve_records` 的比賽，呼叫既有的
   「重新產生計分板連結」或「重新產生控制板連結」端點。
2. 重新查詢該比賽的 `score_serve_records`。

**預期結果**：筆數與呼叫前完全相同，每一筆內容（發球者、站位、
`created_at`）皆未被改動——連結重新產生只影響 `courts` 表的 token
欄位，不觸碰 `score_serve_records`（spec.md Edge Cases 第 4 點）。
