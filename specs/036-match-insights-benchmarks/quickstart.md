# Quickstart: 對戰紀錄洞察

驗證 [contracts/member-match-records-api.md](./contracts/member-match-records-api.md)、[contracts/member-match-dashboard-api.md](./contracts/member-match-dashboard-api.md)、[contracts/group-benchmark-api.md](./contracts/group-benchmark-api.md)、[contracts/match-comparison-api.md](./contracts/match-comparison-api.md) 與畫面。決策見 [research.md](./research.md)，規則表與欄位見 [data-model.md](./data-model.md)。

## 前置準備

沿用既有本地開發環境。**這次沒有 migration**，部署順序沒有限制；舊版前端搭新版後端、新版前端搭舊版後端（新欄位缺省）皆不會壞。

示範資料（只能對白名單內的拋棄式資料庫執行）：

```bash
# 於 apps/api
python -m scripts.seed_dashboard_demo rally_stats_test
```

本功能會擴充這支腳本，除了既有的 `demo@example.com`（16 場）與 `heavy@example.com`（300 場）之外，另外建立：

- `demo` 的比賽分布在**兩個團**，其中一位固定球友在兩個團使用**不同暱稱**（驗證身分合併）；另有兩位不同球員**同暱稱**。
- `demo` 有一位勝率明顯偏高的搭檔（≥ 5 場）、一位勝率明顯偏低的對手（≥ 5 場）、一位只打過 2 場的搭檔。
- `demo` 在其中一個團**離開後重新加入**（兩列名單，驗證 research Decision 7）。
- 一位互為好友、開啟分享、與 `demo` 既當過對手也當過搭檔的會員 `friend@example.com`。
- 一個效能用的團：40 位球員、1,000 場逐分紀錄完整的已完成比賽，`heavy` 是其中一員。

自動化測試：

```bash
# 後端（於 apps/api）
python -m pytest tests/unit/domains/member/test_matchups.py           # 身分合併、分差、重點摘要、head_to_head
python -m pytest tests/unit/domains/member/test_insights.py           # 每條規則、門檻邊界、成對去重、排序、status
python -m pytest tests/unit/domains/member/test_group_benchmark.py    # 門檻、平均、名次方向、並列、四種 status
python -m pytest tests/unit/domains/member/test_player_dashboard.py   # overall_values；aggregate 既有測試零變動
python -m pytest tests/unit/domains/member/test_member_match_records.py \
                 tests/unit/domains/member/test_member_match_dashboard.py \
                 tests/unit/domains/member/test_member_group_benchmark.py \
                 tests/unit/domains/member/test_member_match_comparison.py
python -m pytest tests/contract -k "match_records or match_dashboard or group_benchmark or match_comparison or groups_history"
ruff check app/ tests/ && mypy app/

# 前端（於 apps/web）
npm test -- --watch=false
npm run lint && npx tsc --noEmit -p tsconfig.app.json
```

> 從 `.claude/worktrees/` 執行：後端把主 checkout 的 `apps/api/.venv/bin` 放到 `PATH`，前端 symlink 主 checkout 的 `node_modules`。**背景測試跑完之前不要結束回合**——worktree 會被清掉。

## 情境 0：前置缺陷——重新加入過的會員能開啟團歷史（research Decision 7）

以 `demo` 登入，開啟他離開後重新加入的那個團的「歷史戰績」。

**預期**：修正前 500（迴歸測試先紅）；修正後正常顯示。從未加入的團仍為 403。

## 情境 1：摘要與儀表板數字一致、可重現（US1；SC-001、SC-002）

以 `demo` 登入，開啟個人對戰紀錄頁。

**預期**：頁面前段出現「優缺點摘要」，不需任何點擊即可讀到至少一句強項與一句待加強。每一句附的分子／分母、百分比、依據場數，與下方儀表板同一張指標卡**逐位相等**。重新整理 20 次、切換中英文，挑出的項目與順序不變。點擊任一句 → 所屬群組展開、捲動到該指標卡、焦點落在卡片上。

## 情境 2：不該出現的敘述（US1-2、US1-3；SC-003）

**預期**：發球／接發球只出現一句；不會同時說「發球局是強項」又說「接發球局待加強」。`demo` 的落後時得分率低於全場得分率，但摘要中**沒有**任何僅因此產生的敘述（`when_trailing` 只可能出現在「最近變化」，或團內比較來源）。

## 情境 3：樣本不足與表現均衡（US1-8、US1-9）

以一位只有 2 場比賽的會員登入 → 摘要顯示「資料還不夠」的說明，不是空白。以一位各指標都貼近基準的會員登入 → 顯示「各項表現均衡」。兩者的 `insights.status` 分別為 `insufficient_data`、`balanced`。

## 情境 4：搭檔／對手戰績對得上（US2；SC-004）

**預期**：出現「搭檔戰績」與擴充後的「對手戰績」，各列含場數、勝敗、勝率、平均分差。任選 5 位搭檔與 5 位對手，以對戰清單人工逐場核對一致。在兩個團用不同暱稱的那位球友是**一列**；同暱稱的兩位球員是**兩列**。只打過 2 場的搭檔有列出、標示「場數少」、沒有被選進重點摘要。依勝率、平均分差排序可用。

## 情境 5：點某個人 → 整頁縮小（US2-8；SC-005）

點擊勝率偏高的那位搭檔。

**預期**：最多 2 次點擊即看到「只和他同隊」的清單；勝敗統計、儀表板、摘要、對手戰績同步改變；畫面上方顯示目前套用的對象與「清除」。再疊加「只看贏的」→ 兩個條件同時生效；清除其一不影響另一個。暱稱相近的其他球員**不會**被一起帶進來。

## 情境 6：只打單打的會員（US2-10）

**預期**：搭檔戰績顯示「單打比賽沒有搭檔」，不是空表格。

## 情境 7：團內比較對得上（US3；SC-006）

`demo` 展開「團內比較」。

**預期**：首次使用預設為他場數最多的團；重新整理後記得上次的選擇。任選 3 項指標，以該團對戰紀錄人工計算每位達門檻（≥ 5 場）球員的數值 → 平均、比較人數、名次一致。越低越好的指標（每場失誤數）最低者第 1 名；數值相同者並列。無好壞方向的指標只有平均。區塊內有一行「固定以此團的全部比賽計算」。

## 情境 8：團內比較的匿名與存取（SC-007；Clarifications 2026-09-18）

在瀏覽器開發者工具檢視 `group-benchmark` 的回應全文。

**預期**：不含任何其他球員的暱稱、`member_id`、`roster_entry_id` 或個別數值。以一位從未加入該團的會員直接帶 `group_id` 請求 → 403。已離開該團、或該團已解散的會員 → 200。達門檻者不足 3 人的指標顯示「團內樣本不足」；`demo` 自己未達門檻的指標顯示平均但不排名。

## 情境 9：團內來源併入摘要，且遇到篩選就退場（US3-11；FR-033、FR-034）

**預期**：團內比較載入期間，摘要下方有一行「正在加入團內比較…」；完成後，`demo` 名列前四分之一的指標以「高於團內平均…，在『團名』排第 r／n」出現，並取代同一指標原本的自我對比敘述。套用任何篩選（含情境 5 的點擊）→ 團內來源的敘述消失，出現一行說明；清除篩選 → 回來。

## 情境 10：好友頁（US4；SC-007）

以 `friend` 的好友身分開啟 `demo` 的戰績頁。

**預期**：看得到 `demo` 的完整摘要（含待加強）與搭檔／對手戰績，列不可點擊；**看不到**團內比較，摘要中沒有任何團內來源的敘述。開啟「與我比較」→ 每項指標並排兩個數字，各附依據場數；雙方皆 ≥ 3 場者以**文字或圖示**（非僅顏色）標示較佳的一方，其餘不標示。「我們的交手紀錄」與自己對戰清單中和對方有關的比賽核對一致；從未同隊的那一組顯示明確文字。`demo` 關閉分享後重新請求 → 三支好友端點與比較端點全部 403，畫面不殘留先前內容。全程 `demo` 沒有收到任何通知。

## 情境 11：雙語、手機、效能（SC-008～SC-010）

**預期**：切換語言後，每一種摘要句型、搭檔／對手欄位、團內比較的四種狀態、比較頁皆無殘留未翻譯字串；`zh-TW.json` 與 `en.json` 鍵集合相同。390px 寬的手機上無水平溢出；3 次以內的捲動或點擊可到達既有對戰清單、任一指標卡、本功能任一區塊。

效能（以 seed 的資料實測，各取 5 次中位數，結果回填於此）：

| 項目 | 目標 |
|---|---|
| `heavy`（300 場）的對戰紀錄＋儀表板（含摘要） | 與上線前相比無明顯變慢；摘要與搭檔／對手戰績 < 3 秒 |
| 40 位球員、1,000 場的團的 `group-benchmark` | < 5 秒 |
| `group-benchmark` 執行期間，另一個請求（例如 `/members/me`）的回應時間 | 不被卡住（純運算在執行緒中） |
