# Quickstart: 休息／準備切換

驗證 [contracts/rest-state-api.md](./contracts/rest-state-api.md)、[contracts/schedule-api-additions.md](./contracts/schedule-api-additions.md)、[contracts/ably-events-additions.md](./contracts/ably-events-additions.md) 與畫面。決策見 [research.md](./research.md)，欄位與推導規則見 [data-model.md](./data-model.md)。

## 前置準備

沿用既有本地開發環境。**這次有一支 migration**（兩個新欄位、一張新表，皆為純新增）：

```bash
# 於 apps/api
alembic upgrade head
```

部署順序：**先 migration、再後端、前端先後皆可**。新欄位皆有預設值，舊版前端搭新版後端不會壞（看不到休息按鈕而已）；新版前端搭舊版後端時，切換按鈕會得到 404——因此前端不要早於後端上線。回滾：`alembic downgrade -1` 會丟掉休息狀態與區間，不影響任何比賽紀錄。

自動化測試：

```bash
# 後端（於 apps/api）
python -m pytest tests/unit/domains/schedule/test_rest_histories.py        # 純函式：休息區間不計入 rest、played_credit 的下中位數
python -m pytest tests/unit/domains/schedule/test_rest_state.py            # 切換、冪等、區間寫入、credit 調整、收斂流程
python -m pytest tests/unit/domains/schedule/test_rest_round_generation.py # 各排程方式產生新一輪時排除休息者；正式搭檔關係不受影響
python -m pytest tests/unit/domains/schedule/test_rest_fairness.py         # wait_count 凍結、rest 扣除休息期間、played_credit
python -m pytest tests/unit/domains/schedule/test_rest_call_up.py          # 叫場優先序、替補、保留、預告與實際一致、同時空場不重複替補
python -m pytest tests/unit/domains/schedule/test_rest_return.py           # 回來後走中途加入者流程、立即叫場
python -m pytest tests/unit/domains/schedule/test_rest_round_stall.py      # 被休息卡住的判斷、自動換輪、兩個守門條件、REST_ENDS_ROUND 的提醒
python -m pytest tests/integration/test_schedule_fairness_simulation.py    # SC-004：隨機休息／回來的模擬
python -m pytest tests/contract -k "rest_state or schedule or round_matches"
python -m pytest tests/integration/test_rest_toggle_flow.py
ruff check app/ tests/ && mypy app/

# 前端（於 apps/web）
npm test -- --watch=false
npm run lint && npx tsc --noEmit -p tsconfig.app.json
```

> 從 `.claude/worktrees/` 執行：後端把主 checkout 的 `apps/api/.venv/bin` 放到 `PATH`，前端 symlink 主 checkout 的 `node_modules`。**背景測試跑完之前不要結束回合**——worktree 會被清掉。

手動情境需要同時開三個視窗：管理頁、球員 A 的成員頁（會員）、球員 B 的成員頁（訪客連結）。

## 情境 1：自己切換，所有人即時看到（US1，SC-001、SC-007）

公平輪替雙打、8 人、1 面場地，輪次進行中。A 不在場上，按「我要休息」。

**預期**：一次點按、無確認框；2 秒內三個視窗的名單都在 A 旁邊顯示「休息中」（圖示＋文字，不只顏色）；A 的按鈕變成「準備好了」。重新整理 A 的頁面，仍是休息中。

## 情境 2：在場上時按休息（FR-014）

A 正在場上。按「我要休息」。

**預期**：比賽照常進行與計分；A 的畫面顯示「打完這一場後開始休息」。該場結束後，下一場的四個人裡沒有 A。

## 情境 3：休息者不進新的一輪、換輪不解除（FR-009、FR-006）

A 休息中。管理員結束這一輪、規劃下一輪。

**預期**：規劃出的場次沒有 A；本輪賽程清單的「輪空」不列 A；A 仍是休息中。各排程方式各做一次——固定搭檔循環賽（手動搭檔）時，A 的搭檔也沒有場次，且沒有被臨時配給別人。

**搭檔關係不受影響（FR-034）**：A 休息中時，把團從公平輪替切到固定搭檔循環賽（自動建立正式搭檔）→ 搭檔設定頁裡 A **有**被配到搭檔；A 休息中時一位新成員加入 → 若 A 是唯一落單的人，新成員與 A 配成正式搭檔。

## 情境 4：短暫休息，場次原封不動（US2 情境 1–3，SC-003）

個人全混搭循環賽、6 人、1 面場地，剛規劃並開始一輪。A 還有好幾場排隊中。A 按休息。

**預期**：本輪賽程清單裡 A 的場次一場都沒變，只是標示「輪到時由替補上場」；場地的「下一場預告」跳過含 A 的場次。A 在任何一場被處理之前按「準備好了」→ 標示消失，之後這些場次以原本的搭檔與對手被叫上場。

## 情境 5：輪到了、人還在休息——替補（FR-016、FR-017、FR-023）

承情境 4，A 持續休息，直到可叫的只剩含 A 的場次。

**預期**：
- 場地空出前，「下一場預告」顯示替補後的陣容，並註明「○○ 代替 A（休息中）」。
- 場地空出後，上場的正是預告的四個人；替補者當下不在別的場地、不是休息中。
- 其餘含 A 的排隊場次仍維持原樣（逐場、輪到才處理）。
- A 之後按「準備好了」：那一場不會補給他，他的等待場數也沒有因此變大。
- 把其他人也切成休息直到沒有人可替補 → 該場留在排隊中、場地顯示「等待休息中的球員」；任一人回來後立即叫場。

## 情境 6：單打循環／固定搭檔——保留，回來立刻叫場（FR-018、FR-019、FR-022）

單打循環、4 人、2 面場地。A 休息；打到只剩含 A 的場次，其中一面場地閒置。

**預期**：含 A 的場次標示「保留，等他回來」，不換人；閒置的場地顯示「等待休息中的球員」。A 按「準備好了」→ **不必等別場打完**，閒置的場地立刻叫他的場次。
固定搭檔循環賽重做一次：A 的搭檔的畫面顯示「搭檔休息中，你們的場次暫緩」。

## 情境 7：這一輪被休息卡住（FR-020、FR-021）

承情境 6，A 不回來，其他比賽全部打完。

- **未開啟自動進入下一輪**：管理頁顯示「剩下 N 場在等休息中的球員：A」，樣式醒目；管理員可以幫 A 按「準備好了」、或結束這一輪。
- **開啟自動進入下一輪**：最後一場別人的比賽一結束就自動換輪，A 的場次被取消，新的一輪沒有 A。
- **守門條件**：只有 A、B 兩人的單打團，A 休息 → **不**換輪（換了也排不出比賽），A 的場次留著；輪次編號不變。反覆切換 A 的狀態，輪次編號 MUST NOT 每次加一。

## 情境 7b：按下去就會結束這一輪——先提醒（FR-031～FR-033，SC-009）

單打循環、4 人、2 面場地、**開啟自動進入下一輪**。打到所有場地都閒置、只剩 2 場含 A 的排隊場次（其餘三人準備中，下一輪排得出來）。A 按「我要休息」。

**預期**：
- 跳出提醒：「本輪還沒打的 2 場比賽會被取消，並直接進入下一輪」，有「取消」與「確認休息」。此時其他視窗的名單上 A **仍是準備中**，本輪賽程清單沒有任何變化。
- 按「取消」→ 什麼都沒變；A 的按鈕仍是「我要休息」。
- 再按一次並「確認休息」→ A 變成休息中、這一輪結束、自動進入下一輪，新的一輪沒有 A。
- **不該跳的情況**：同樣的團，但還有一場別人的比賽在打時 A 按休息 → 不跳提醒、一鍵生效；A 的畫面出現說明文字「你還有 2 場保留中，這一輪結束前沒回來會被取消」。關閉自動進入下一輪後重做 → 不跳提醒。
- **確認不是強制**：提醒跳出後先不按；用管理頁為這一輪手動加一場不含 A 的比賽（或讓一位新成員加入，產生新場次），再回到 A 的視窗按「確認休息」→ A 變成休息中，但這一輪**沒有**結束。
- 管理員在管理頁替 A 按休息 → 同樣的提醒，文字指明是 A。

## 情境 8：休息不是插隊的捷徑（US3，SC-004）

公平輪替雙打、9 人、1 面場地、開啟「場地一空就排下一場」。記下 A 的等待場數（名單上有顯示）。A 休息，其餘 8 人連打 6 場，A 回來。

**預期**：
- 休息期間名單上 A 的等待場數不變；回來時仍是原值，不是「從未上場」。
- 回來後第一次挑人，等待場數比 A 高的人排在 A 前面。
- 之後連打 10 場，A 的上場次數與其他人相當——**不會**因為總場數少而每一次平手都勝出（research Decision 4）。
- 閒置且準備中的人只有 3 個、場地空著時，A 按「準備好了」→ 立即排出一場。

## 情境 9：管理員代為切換（US4）

管理頁名單上，對一位訪客球員按「休息」。

**預期**：該訪客自己的頁面即時變成休息中；再按一次恢復。建立者自己的那一列也可以切換。手動安排、替換球員的選單裡，休息中的人有標示但仍可選；選了之後他的狀態不變。

## 情境 10：權限（FR-004）

```bash
# 以 B 的訪客 token 去切換 A 的列 → 404 ROSTER_ENTRY_NOT_FOUND（與不存在的 id 回應完全相同）
# 不帶任何身分 → 404 ROSTER_ENTRY_NOT_FOUND
# 對已離開的列 → 404 ROSTER_ENTRY_NOT_FOUND
# 連送兩次 {"resting": true} → 第二次 200、changed: false、沒有 roster.restChanged
```

## 情境 11：紀錄完全不受影響（FR-028、SC-008）

上述情境做完後，比對排行榜、對戰紀錄、個人統計：與「同一批比賽、沒有人用過休息功能」的結果逐項相同。被替補的那一場記在替補者名下，A 沒有那一場的紀錄。

## 情境 12：手機與無障礙

375px 寬：名單上的休息標示與切換按鈕不造成水平溢出；按鈕是原生 `<button>`、可用鍵盤操作、`aria-pressed` 反映狀態；螢幕報讀讀得到「休息中」。
