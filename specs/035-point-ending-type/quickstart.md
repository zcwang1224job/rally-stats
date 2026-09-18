# Quickstart: 得分方式紀錄

驗證 [contracts/shot-placement-api.md](./contracts/shot-placement-api.md)、[contracts/match-record-detail-api.md](./contracts/match-record-detail-api.md)、[contracts/member-match-dashboard-api.md](./contracts/member-match-dashboard-api.md) 與畫面。決策見 [research.md](./research.md)，欄位與指標見 [data-model.md](./data-model.md)。

## 前置準備

沿用既有本地開發環境。這次**有 migration**：

```bash
# 於 apps/api（先 source .venv/bin/activate）
alembic upgrade head        # 新增 shot_placement_records.ending_type
alembic downgrade -1 && alembic upgrade head   # 確認可逆
```

> **本機 docker 環境也要手動執行**：`infra` 的後端容器不會自動跑 migration（而且它直接掛載主 checkout 的 `apps/api`，在主 checkout 切到這個分支就等於換了它跑的程式）。切分支、重啟容器之後，若比賽詳情或儀表板出現 500（`column shot_placement_records.ending_type does not exist`），就是少了這一步：
>
> `docker compose -f infra/docker-compose.yml exec backend alembic upgrade head`
>
> 正式環境同理：**先跑 migration，再部署後端**。順序反了，壞掉的是所有比賽詳情、整個儀表板與詳細計分的 `-1`。

需要：一個開啟 `detailed_scoring_enabled` 的雙打團與一個單打團、一個場地、一位已驗證信箱的會員 M（在團內有 roster entry）。比賽需自然達標結束才會出現在對戰紀錄。

自動化測試：

```bash
# 後端
python -m pytest tests/unit/domains/schedule/test_shot_placement.py      # 寫入與驗證
python -m pytest tests/unit/domains/group/test_match_stats.py            # 純函式 ending_stats
python -m pytest tests/unit/domains/member/test_player_dashboard.py      # 5 項新指標、失誤組成
python -m pytest tests/unit/domains/group/test_match_record_detail.py \
                 tests/unit/domains/member/test_member_match_dashboard.py
python -m pytest tests/contract -k "shot_placement or match_record_detail or match_dashboard"
ruff check app/ tests/ && mypy app/

# 前端
npm test -- --watch=false
npm run lint && npx tsc --noEmit -p tsconfig.app.json
```

> 從 `.claude/worktrees/` 執行：後端把主 checkout 的 `apps/api/.venv/bin` 放到 `PATH`，前端 symlink 主 checkout 的 `node_modules`。**背景測試跑完之前不要結束回合**——worktree 會被清掉。

## 情境 1：界外 → 自動帶入「對手出界」，零額外點擊（US1-1；SC-001）

1. 詳細計分的比賽中按 A 隊 +，在球場圖**線外**點一下，不碰得分方式，直接確認。

**預期**：得分方式那一排已選中「對手出界」；確認後該分的 `ending_type == "out"`。「主動得分」選項為停用狀態。

## 情境 2：發球失誤區 → 自動帶入「發球失誤」（US1-2）

1. 輪到 B 隊發球時按 A 隊 +，把落點點在 **A 隊自己半場的短發球線之前**（既有畫面此時會出現發球失誤的標示）。

**預期**：自動選中「發球失誤」；確認後 `ending_type == "serve_fault"`。

## 情境 3：界內落在失分方半場 → 不自動帶入，一次點擊（US1-3；SC-006）

1. 按 A 隊 +，把落點點在 **B 隊半場界內**。

**預期**：得分方式**沒有**任何選項被選中；「對手出界」停用。點一下「主動得分」後確認 → `ending_type == "winner"`。重複一次改點「對手掛網」→ `"net"`。不點直接確認 → `ending_type == null`，且確認不被阻擋。

## 情境 4：親手選過就不被落點覆蓋（US1-4、US1-7；FR-009）

1. 先點界外落點（自動帶入「對手出界」），再親手改選「其他失誤」，然後把落點改點到另一個界外位置。
2. 另一分：親手選「主動得分」，再把落點改點到界外。

**預期**：(1) 仍是「其他失誤」。(2)「主動得分」與界外矛盾——選取被清除並回到自動帶入的「對手出界」，不會存下矛盾的組合。再點一次已選中的選項 → 取消選取（未記錄）。

## 情境 5：只記得分方式、不記其他（US1-6；FR-010）

1. 按 + 後不點落點、不選球員，只點「對手掛網」並確認。

**預期**：成功。比賽詳情的逐點清單中，這一分顯示「對手掛網」，沒有球員與落點。

## 情境 6：簡易模式不變、`-1` 一併收回、後端擋矛盾（US1-8、US1-9）

**預期**：簡易計分的比賽按 + 不出現任何新選項（SC-003／SC-008）。記錄一分含得分方式後對該隊按 −1 → 比賽詳情不再有那一分的任何明細。直接呼叫 API 送 `ending_type: "winner"` 配界外落點 → 422 `ENDING_TYPE_CONTRADICTS_LANDING`；送值域外的字串 → 422。

## 情境 7：單場詳情的拆分對得上（US2；SC-004）

打完一場：其中數分記錄得分方式（含至少一分「有得分方式、沒有球員」）、數分略過、中途做一次 `-1`。查詢比賽詳情。

**預期**：

- 逐點清單有得分方式的分數顯示標籤，主動得分與失誤以**圖示＋文字**區分；略過的分數外觀與上線前相同。
- `ending_stats.recorded_points` ＝ 逐點清單中有標籤的有效得分數；`total_points` ＝ 兩隊比分和。
- 每位球員 `winners + opponent_errors + scored_unrecorded` ＝ 既有球員得失分統計的得分數；失分端同理。
- 「有得分方式、沒有球員」的那一分出現在隊伍摘要、不出現在任何球員列。
- 被 `-1` 撤銷的那一分不在任何數字中。
- 找一場上線前的舊比賽 → `ending_stats == null`，新區塊顯示單一無資料提示，其餘畫面與上線前一致。

## 情境 8：儀表板新指標（US3；SC-005）

讓 M 累積：3 場有得分方式紀錄的比賽、2 場詳細計分但全部略過、1 場簡易計分。

**預期**：

- `metrics` 為 23 項，前 18 項與上線前相同；新群組「主動得分與失誤」出現 5 張卡片，皆標示「依據 3 場／共 6 場」。
- 任選 `winner_share`：把 3 場單場詳情中 M 的 `winners` 與 `winners + opponent_errors` 人工加總，等於該指標的分子／分母。
- `error_breakdown.all` 四項相加 ＝ 3 場 `own_errors` 的總和；畫面以四列「次數＋佔比」呈現。
- 超過 10 場後：`errors_per_match` 下降 → 「▲ 進步」（越低越好）；可查看趨勢。
- 沒有任何得分方式紀錄的會員：5 張新卡片各自顯示專屬提示，`error_breakdown == null`，既有 18 項不受影響。

## 情境 9：好友檢視、雙語、手機、效能

**預期**：好友在 M 開啟分享時看得到新群組，關閉後整個儀表板被拒絕（沿用 034）。切換語言後選擇畫面的五個選項、詳情的新區塊、儀表板的新群組皆無殘留未翻譯字串。390px 寬的手機上，選擇畫面的確認按鈕在選定得分方式前後都不需捲動即可看見（SC-011）。`python -m scripts.seed_dashboard_demo rally_stats_test`（已含得分方式）的 300 場會員，儀表板仍 < 3 秒（SC-010）。

**結果（2026-09-18，worktree 後端 :8001 + `ng serve` :4300 + 無頭 Chrome；腳本 `shoot035.js`）**：

- 手機 390×844 的計分流程（單打、連記 10 分，每分點落點＋確認；單打的兩位球員為預選）：上線前 30 次點擊，得分方式額外 **6** 次——正是 6 個界內落點各點一下；3 個界外落點自動帶入「對手出界」（`winner` 停用）**0 次**；1 個界內落點刻意略過 0 次。資料庫中 10 列的 `ending_type` 與畫面所選一致，略過者為 NULL。
- 確認按鈕在選定得分方式前後 10 次皆在可視範圍內；`scrollWidth − clientWidth` 為 0（SC-011）。
- 1100×900 與 390×844：儀表板 23 張卡片、恰一組範圍切換鈕；切到「最近 10 場」後失誤組成由 出界 6／掛網 39 變為 6／26；詳情逐點清單 22 個得分方式標籤；兩種寬度皆無水平溢出、無 `pageerror`。
- 看圖修了三處：選定的 chip 被全域 `.btn--secondary:hover` 蓋成灰底白字（提高選擇器優先度）；詳情的球員表把區塊撐超出手機寬度（host `min-width: 0`）；「得 11／失 0」逐字換行（`nowrap`）。
- 效能（SC-010）：300 場會員的儀表板 5 次 240–270 ms，中位數 **262 ms**；查詢次數與 034 相同（單元測試斷言）。
- 語系：`zh-TW.json` 與 `en.json` 鍵集合相同（821 鍵）；本功能觸及的模板所用 key 全部存在、無寫死文字。

## 情境 10：計分節奏（SC-002）

以碼表連續記 10 分（每分都點落點＋兩位球員），分別在上線前後的版本各做一次。

**預期**：總時間增加不超過 10%。界外與發球失誤的分數不需要任何額外點擊。

**結果**：需人工以碼表量測——待使用者執行後填入。無頭瀏覽器只能數點擊次數（見情境 9：界外 0 次、界內最多 1 次），量不到人的操作時間。
