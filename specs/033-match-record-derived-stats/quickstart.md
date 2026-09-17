# Quickstart: 對戰紀錄衍生統計

本功能是純讀取擴充。以下情境使用既有的計分／落點端點準備資料，再驗證擴充後的比賽詳情回應（[contracts/match-record-detail-api.md](./contracts/match-record-detail-api.md)）與畫面。計算規則見 [research.md](./research.md)，欄位定義見 [data-model.md](./data-model.md)。

## 前置準備

沿用既有本地開發環境（`apps/api/README.md`、`docs/local-development.md`）。準備一個已開啟 `detailed_scoring_enabled` 的團、一個場地、一場**雙打**比賽（4 位參賽者）；另備一場**單打**比賽供情境 3 使用。比賽需自然結束（達目標分數）才查得到詳情。

自動化測試：

```bash
# 後端（於 apps/api，先 source .venv/bin/activate；需本機 Postgres 與 rally_stats_test 資料庫）
python -m pytest tests/unit/domains/group/test_match_stats.py          # 純函式，無需資料庫
python -m pytest tests/unit/domains/group/test_match_record_detail.py tests/contract -k match_record_detail
ruff check app/ tests/ && mypy app/

# 前端（於 apps/web）
npm test -- --watch=false
npm run lint && npx tsc --noEmit -p tsconfig.app.json
```

## 情境 1：發球統計的分母與排除說明（US1）

1. 打完一場雙打，過程中不做任何修正。查詢 `GET /groups/{group_id}/match-records/{match_id}`。

**預期**：`serve_stats.excluded_points == 1`；兩隊 `serve_points_total` 相加 ＝ 總比分 − 1；`teams[A].serve_points_total == teams[B].receive_points_total`；`players` 為 4 筆。任選幾分對照逐點清單人工核對：某一分的發球方＝**上一分**的得分方。

## 情境 2：發球得分率不是恆為 100%（回歸防護）

**預期**：情境 1 的回應中，至少一隊的 `serve_points_won < serve_points_total`（只要比賽中出現過 side-out 就必然成立）。若兩隊都是 `won == total`，代表誤用了「得分後」的快照（research.md Decision 3）。

## 情境 3：單打不重複顯示球員層級（US1 情境 3）

**預期**：單打比賽的 `serve_stats.players == []`，`teams` 仍為 2 筆且接發球數字正確；畫面只出現隊伍層級表格。

## 情境 4：修正（-1）不污染統計（FR-002）

1. 比賽中 A 隊 +1 後立刻 A 隊 -1，再由 B 隊 +1；完賽後查詢。

**預期**：被撤銷的那一分不出現在任何統計中；`momentum_stats` 的比分序列沒有那一分造成的假領先／假連續得分；夾著修正的那個區間不計入 `tempo_stats`（`counted_points` 比有效得分總數少）；不變量 1 依然成立。

## 情境 5：走勢摘要（US2）

**預期**：`longest_runs`、`max_leads` 與趨勢圖人工核對一致；「A 領先 → 平手 → A 再領先」不出現在 `lead_changes`；一路領先到底的比賽 `lead_changes == []`，畫面不顯示空白清單。

## 情境 6：無資料提示各自獨立（FR-003／FR-004）

| 比賽 | 預期 |
|---|---|
| 簡易計分模式、030 之後 | 發球／走勢／耗時有值；`landing_distribution == []`，畫面顯示「此比賽沒有落點紀錄」 |
| 030 之前完成的舊比賽 | `serve_stats == null`，畫面顯示「此比賽沒有發球紀錄」；走勢／耗時照常 |
| `record_completeness` 為 `partial`／`none` | 四者皆無資料，四個區塊各自顯示提示，不出現任何數字 |

畫面上 MUST NOT 出現全零表格、空白球場、或 `0%`／`100%` 之類由空資料算出的數字。

## 情境 7：落點分布圖（US4）

1. 在詳細計分比賽中，為同一位球員記錄數筆得分落點（含一筆界外）、數筆失分落點，另記一筆只選球員不標落點。完賽後開啟比賽詳情，展開「落點分布」，選擇該球員。

**預期**：得分以圓形、失分以菱形標示，並有文字圖例；界外那一點畫在球場線外、未被裁切；圖旁顯示「已標落點／總數」且分母含未標落點的那一分；切換顯示開關可分別隱藏兩類；選擇沒有落點的球員時顯示該球員專屬提示。同一個落點在此圖與逐點清單展開圖中位置一致（FR-028）。

## 情境 8：四個入口一致、雙語、手機版面（FR-005／FR-007／FR-009）

分別從「某團對戰紀錄」「個人對戰歷史」「我的團→歷史戰績」「好友的對戰紀錄」開啟同一場比賽。

**預期**：四處內容完全一致。切換語言後四個新區塊無殘留未翻譯字串。手機寬度下新區塊預設僅第一個展開，既有的趨勢圖與逐點清單仍在原位、容易找到。
