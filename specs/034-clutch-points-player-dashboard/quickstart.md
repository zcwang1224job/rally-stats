# Quickstart: 關鍵分表現與跨場個人技術儀表板

本功能是純讀取擴充。以下情境使用既有的計分／落點端點準備資料，再驗證 [contracts/match-record-detail-api.md](./contracts/match-record-detail-api.md)、[contracts/member-match-dashboard-api.md](./contracts/member-match-dashboard-api.md) 與畫面。計算規則見 [research.md](./research.md)，欄位與指標目錄見 [data-model.md](./data-model.md)。

## 前置準備

沿用既有本地開發環境（`apps/api/README.md`、`docs/local-development.md`）。需要：

- 一個**會員帳號 M**（已驗證信箱）與一個**好友帳號 F**（與 M 互為好友）。
- 一個 21 分制、開啟 `detailed_scoring_enabled` 的雙打團；M 以會員身分加入。另備一個**目標分 7 分**的自訂賽制團（情境 3）。
- 所有比賽需**自然達標結束**才會出現在對戰紀錄（提前結束一律為 abandoned）。

自動化測試：

```bash
# 後端（於 apps/api，先 source .venv/bin/activate；需本機 Postgres 與 rally_stats_test 資料庫）
python -m pytest tests/unit/domains/group/test_match_stats.py            # 純函式：clutch_stats、_wins 網格
python -m pytest tests/unit/domains/member/test_player_dashboard.py      # 純函式：build_sample、aggregate
python -m pytest tests/unit/domains/group/test_match_record_detail.py \
                 tests/unit/domains/member/test_member_match_records.py \
                 tests/unit/domains/member/test_member_match_dashboard.py
python -m pytest tests/contract -k "match_record_detail or match_dashboard or match_records"
ruff check app/ tests/ && mypy app/

# 前端（於 apps/web）
npm test -- --watch=false
npm run lint && npx tsc --noEmit -p tsconfig.app.json
```

> 從 `.claude/worktrees/` 下的 checkout 執行時，worktree 沒有自己的 venv／`node_modules`：後端把主 checkout 的 `apps/api/.venv/bin` 放到 `PATH`（`conftest.py` 會呼叫 `alembic`），前端把主 checkout 的 `apps/web/node_modules` symlink 進來。

## 情境 1：平分延長與賽末點（US1 情境 2、4、5）

1. 打一場雙打，由 A 先得分、雙方交替得分到 20:20（此時 A 已在 20:19 握有過一次賽末點——要打到 20:20，前一分必為 20:19 或 19:20，領先方必然握有過賽末點），之後依序：A、B、A、B、B、B 得分（終場 22:24，B 勝）。查詢 `GET /groups/{group_id}/match-records/{match_id}`。

**預期**：`clutch_stats.deuce` 兩隊 `total == 6`，A `won == 2`、B `won == 4`。賽末點：A 在 20:19、21:20、22:21 各握有一次 → `held == 3`、`converted_on == null`、`saved == 0`；B 在 22:23 握有一次並兌現 → `held == 1`、`converted_on == 1`、`saved == 3`。畫面顯示「A 隊握有賽末點 3 次、未兌現」「B 隊化解對手賽末點 3 次」。

## 情境 2：封頂前的雙方賽末點（US1 情境 6）

1. 打到 29:29（cap 30），由 A 得分結束。

**預期**：最後一分同時計入雙方 `held`；A `converted_on == A.held`；`A.saved + B.saved + 1 == A.held + B.held`。

## 情境 3：目標分過低＝局末階段不適用（FR-010）

1. 在 7 分制的團完成一場比賽並查詢。

**預期**：`endgame_from == null`、`endgame == null`，畫面該項顯示「此賽制不適用」；`deuce`／`match_points`／`by_state` 照常有值。

## 情境 4：比分狀態分組與逆轉摘要（US1 情境 7、8；SC-002）

1. 打一場 A 隊一度 8:13 落後、最後逆轉獲勝的比賽。

**預期**：每隊 `by_state` 三組 `total` 相加 ＝ 終場兩隊比分和；A 的 `leading.total` ＝ B 的 `trailing.total`。`comeback == { winner: "A", max_deficit: 5, score_a: 8, score_b: 13 }`，且等於同一回應 `momentum_stats.max_leads` 中 B 那一筆。另打一場 A 從頭領先到尾的比賽 → `comeback == null`，畫面顯示「勝方全場未曾落後」，MUST NOT 出現「落後 0 分」。

## 情境 5：修正（-1）與不完整紀錄（Edge Cases）

1. 在 19:19 時 A +1、A −1、B +1，之後打完。
2. 另找一場 `record_completeness` 為 `partial` 的比賽。

**預期**：(1) 被撤銷的那一分不計入任何階段；局末階段以**重新累計**的比分判定；不變式仍成立。(2) `clutch_stats == null`，畫面整塊顯示無資料提示、不出現任何數字。

## 情境 6：儀表板指標與「依據 N 場／共 M 場」（US2）

讓 M 累積：3 場詳細計分雙打、2 場簡易計分雙打、1 場單打、（若環境有）030 之前的舊比賽。查詢 `GET /members/me/match-dashboard` 並開啟「對戰紀錄」頁。

**預期**：

- `metrics` 恆為 18 項、順序固定；`total_matches` ＝ 同條件 `GET /members/me/match-records` 的 `total_matches`。
- `avg_points_for` 等最終比分類指標 `matches_used == total_matches`；`points_scored` 只計詳細計分的 3 場；`own_serve` 不計單打。
- 任選 `team_serve`：把納入的每一場單場詳情中「我方」的 `serve_points_won`／`serve_points_total` 人工加總，MUST 等於該指標的 `numerator`／`denominator`（FR-003、SC-003）——**不是**各場百分比的平均。
- 每張指標卡顯示「依據 N 場／共 M 場」；沒有任何資料的指標顯示專屬提示，畫面上不出現 `0%`。
- 發球類指標旁有一行「每場第一分不列入」的說明。
- 以**尚未完成信箱驗證**的會員查詢 `GET /members/me/match-dashboard` → 403 `EMAIL_NOT_VERIFIED`（Constitution IV）。

## 情境 7：篩選連動、翻頁不重抓（FR-019）

1. 在對戰紀錄頁套用「雙打」篩選 → 觀察網路請求。
2. 翻到第 2 頁 → 觀察網路請求。

**預期**：(1) `match-records` 與 `match-dashboard` 各發一次，帶相同篩選參數，儀表板數字隨之改變。(2) 只發 `match-records?page=2`，**不**重新請求 `match-dashboard`。篩選到 0 場 → 儀表板顯示單一空狀態。

## 情境 8：最近 10 場對比與進步判定（US3）

讓 M 的比賽數 > 10，且最近幾場輸球的分差明顯比早期小。

**預期**：`has_comparison == true`；`avg_loss_margin` 的 `recent.value < all.value` 且 `verdict == "improved"`（越低越好）；卡片以**圖示＋文字**標示進步，非僅顏色。某指標在最近 10 場中具備資料者 < 3 場 → `verdict == "insufficient"`，畫面顯示「樣本不足」。`match_points_saved` 顯示每場平均（附總次數）與差異，但不標進步／退步。比賽數 ≤ 10 的帳號 → 所有 `recent == null`，畫面不出現對比欄。

## 情境 9：趨勢（US3 情境 6、7）

**預期**：具備資料 ≥ 6 場的指標出現在 `trends`，點數 ＝ 場數 − 4（上限 60）、由舊到新；選定指標後畫面顯示折線，資料點可看出涵蓋的日期區間。< 6 場的指標選定後顯示「比賽場數不足以呈現趨勢」，不出現單點或空白圖。

## 情境 10：落點視角正規化（US4；SC-006）

1. M 在比賽甲屬 **A 隊**，記錄一筆 M 的得分落點於「對手場地的右後角」。
2. M 在比賽乙屬 **B 隊**，同樣在「對手場地的右後角」（從 M 的視角）記錄一筆得分落點。

**預期**：`landing.scored` 中這兩筆座標相同（容許四捨五入誤差），且 `x > 0.5`（我方恆在左）。畫面球場圖下方有「← 我方｜對手 →」文字。點數 ＝ 各場單場分布圖中 M 的落點數加總；界外點畫在線外；切換「最近 10 場／全部」時圖上點數分別為 `recent_*_count` 與陣列全長；標記超過 150 個時改為較小、半透明的密集樣式，圓／菱形區分與圖例不變。套用「單打」篩選後，球場圖改以單打場地呈現（邊線外的走道顯示為界外）；清除篩選後回到雙打場地。

## 情境 11：好友檢視與隱私（US5；SC-010）

1. M 開啟「允許好友查看我的戰績」，以 F 登入開啟 M 的好友戰績頁。
2. M 關閉該設定，F 重新整理。

**預期**：(1) F 看到的儀表板數值 ＝ M 本人未篩選時所見；M 沒有收到任何通知。(2) `GET /members/{M}/match-dashboard` 回傳 `MATCH_RECORDS_PRIVATE`，頁面只出現既有的一則「已設為不公開」提示（儀表板不另外顯示第二則錯誤），且無殘留數字。以 F 查詢自己的 id → `SELF_VIEW_NOT_SUPPORTED`。

## 情境 12：效能、雙語、手機（SC-007～SC-009）

**預期**：以種子資料灌入 300 場比賽的帳號，`match-dashboard` 回應 < 3 秒，且 `match-records` 的回應時間與本功能上線前相當（增幅 < 10%；兩者平行載入）；一場 40 分以上比賽的詳情回應 < 2 秒。切換語言後關鍵分區塊與儀表板無殘留未翻譯字串。手機寬度下：比賽詳情的關鍵分區塊預設收合、位於「比分走勢摘要」之後；對戰紀錄頁的儀表板只有第一個群組預設展開，既有對戰清單在 3 次捲動／點擊內可達。

### 情境 12 量測結果（2026-09-17，T041／T042）

環境：本機、worktree 後端對 `rally_stats_test`；資料由 `python -m scripts.seed_dashboard_demo rally_stats_test` 灌入（`heavy@example.com`：300 場、每場完整逐分＋發球紀錄；`demo@example.com`：16 場、含落點）。各端點取 5 次（對照組 15 次、交錯量測）的中位數。

| 項目 | 結果 | 門檻 |
|---|---|---|
| `GET /members/me/match-dashboard`（300 場） | **241 ms**，108.6 KB（18 項指標、15 條趨勢 × 60 點、無落點） | < 3 秒 ✅ |
| `GET /members/me/match-records`（300 場）上線前 → 上線後 | 16.4 ms → **16.9 ms（+2.9%）**，回應內容逐位元組相同 | 增幅 < 10% ✅ |
| 46 分比賽（22:24）的詳情 | **7 ms**，6.9 KB | < 2 秒 ✅ |
| `demo` 的儀表板（16 場、166 個落點） | 28.7 KB | — |

「上線前」以主 checkout（034 之前的程式）對同一個資料庫另起一個後端取得；回應完全相同，同時佐證 `_filtered_member_matches()` 的抽出沒有改變行為。

版面（無頭 Chrome，1100×900 與 390×844，實際登入操作）：兩種寬度皆無水平溢出、無頁面錯誤。依實際畫面修正三處——趨勢圖加上寬度上限（原本在桌機上過高）、指標卡在手機上排兩欄（18 張單欄太長）、關鍵分表格的欄位標題不斷行。比賽詳情的關鍵分區塊預設收合、位於走勢摘要之後；儀表板僅第一群組預設展開。

