# Quickstart: 驗證快速開始比賽（042-quick-match）

**Plan**: [plan.md](./plan.md) | 契約：[contracts/](./contracts/) | 模型：[data-model.md](./data-model.md)

## 前置條件

- 本機 docker 的 Postgres（`infra-db-1`），測試庫 `rally_stats_test`。
- 在 worktree 中執行：後端把主 checkout 的 `apps/api/.venv/bin` 放到 PATH（conftest 會呼叫 `alembic`）；前端 `ln -s` 主 checkout 的 `apps/web/node_modules`。
- 本功能有 **一支 migration**（`groups.kind`、`quick_match_slots`、兩列 `system_config`）。pytest 會自動 downgrade/upgrade；跑 docker 堆疊時要手動 `alembic upgrade head`。

## 1. 自動化測試

```bash
cd apps/api
python -m pytest tests/unit/domains/quick_match tests/contract/test_quick_match_*.py tests/integration/test_quick_match_flow.py -q
# 全套（四段各在 10 分鐘內）：
python -m pytest tests/contract -q
python -m pytest tests/integration -q
python -m pytest tests/unit/domains/schedule -q
python -m pytest tests/unit --ignore=tests/unit/domains/schedule -q

cd ../web
npx ng test --watch=false --include='**/*.spec.ts'
npx ng lint
npx ng build      # 警告數與 origin/ut 相同（8 個既有警告）
```

**預期**：全部通過，並特別確認：

- migration 往返：`alembic downgrade -1 && alembic upgrade head` 不報錯；既有 `groups` 列的 `kind` 全為 `normal`。
- 純函式測試（不碰資料庫）涵蓋：換邊、位置狀態機（全部 ready 才開賽、逾時轉訪客、轉換後接受被拒）、sweep 期限選擇。
- 契約測試涵蓋 contracts/quick-match-api.md 的每一個錯誤碼至少一次，以及「計分板 token 打任何 quick 端點 → `LINK_NOT_FOUND`」「一般團的控制板 token → `QUICK_SESSION_ONLY`」。
- 既有的 `test_create_group.py`、`test_group_list*.py`、`test_manual_assign.py`、`test_group_invite_endpoints.py`、`test_member_match_records_endpoint.py` **零 diff** 且全綠（一般團行為不變）。
- 整合測試 `test_quick_match_flow.py` 走完：建立（含一位好友）→ 好友接受 → 開賽 → 計到 21 → 再打一場（換邊、連結相同）→ 換人再打（換掉一位訪客）→ 結束 → 雙方對戰紀錄各 2 場、`group_kind == 'quick'` → 舊連結回 `group_disbanded: true`。

## 2. 實際畫面驗收

以 worktree 的前後端（:8001／:4300）開啟，`playwright-core` 驅動，做法見專案的 worktree 測試慣例；後端啟動要帶主 checkout `.env` 的 `ABLY_API_KEY`（需要真的即時事件）。先用 `seed_dashboard_demo` 建 `demo@example.com` 與 `friend@example.com`（互為好友），並確認兩人都不在任何 active 團中（示範團需先解散或讓兩人 `left`）。

| # | 步驟 | 預期結果（對應需求） |
|---|---|---|
| 1 | 訪客開首頁 → 「快速開始比賽」 | 一頁表單，只有比賽模式／球員／計分制／詳細設定四組欄位，無團名、PIN、排程機制（FR-002、SC-002） |
| 2 | 單打、填「小明」「小美」、送出 | 60 秒內落在 `/control/<token>`；畫面有計分板連結與 QR；有「請保留連結」提示；無輪次列（US1、FR-009、FR-024、SC-001） |
| 3 | 另開分頁開計分板連結；控制板按 +1 到 21:19 | 計分板即時更新；到 21 自動結束、判 A 勝；控制板出現「再打一場／換人再打／結束」（US2、FR-010、FR-013） |
| 4 | 按「再打一場」 | 新的一場立刻開始，兩方互換；控制板與計分板 URL 不變；計分板分頁自動切到新的一場（FR-014、SC-005） |
| 5 | 按「提前結束」→ 「結束」→ 確認 | 兩個連結都顯示「這場快速比賽已結束」；不是錯誤畫面（FR-023、US5 情境 4） |
| 6 | 以 demo 登入 → 首頁「快速開始比賽」→ 雙打；A1 為本人（有「本人」標籤，不可改）、A2 填暱稱、B1 從好友挑 friend、B2 填暱稱 → 送出 | 進入等待畫面：friend 為「等待中」＋倒數；其餘三位「已就位」（US4 情境 2） |
| 7 | 另一瀏覽器以 friend 登入 | 通知鈴 +1；通知列點開 → 邀請頁標題為快速比賽、顯示 demo 暱稱與「雙打」；按「接受」 | 
| 8 | 回到 demo 的分頁 | 1 秒內自動進入控制板；friend 的分頁導向計分板（US4 情境 3、SC-008） |
| 9 | 計到 21 → 「換人再打」→ 把 A2 換成新暱稱、B1 保留 friend → 送出 | 不再向 friend 發邀請、立即開賽（FR-030） |
| 10 | 再開一場快速比賽挑 friend，這次 friend 不回應，等 `quick_match_invite_timeout_seconds`（測試時把 `system_config` 改成 10 秒） | 倒數歸零後 friend 位置變成「小友（訪客）」、比賽自動開始；friend 之後點通知顯示「這場已經開始」（FR-028、邊界情境） |
| 11 | 「結束」後：demo 開「對戰紀錄」；friend 開「對戰紀錄」與「好友對戰紀錄」 | demo 看到本次全部場次、活動名稱為「快速比賽」標籤；friend 只看到他接受後打的那些場；篩選「快速比賽」只剩這些（FR-016、FR-017、SC-003） |
| 12 | 任一場點「分享」 | 分享卡標題為「快速比賽」（FR-017） |
| 13 | 「我的團」 | 預設看不到快速比賽；勾「包含快速比賽」才出現；開團列表 `/groups` 永遠看不到（FR-019、SC-004） |
| 14 | demo 有一次 idle 的快速比賽未結束時去 `/groups/new` 開團 | 開團成功、快速比賽自動收尾；改成有比賽進行中時再試 → 被拒且提示先結束（FR-020） |
| 15 | 把 `quick_session_idle_minutes` 設為 1，放著一場 idle 的快速比賽 2 分鐘 | sweep 自動收尾；連結顯示已結束；已完成的紀錄仍在（FR-022、SC-006） |
| 16 | 360px 寬手機視窗重跑 1、2、6 | 無水平捲動、按鈕可點（Constitution VII） |

驗收完把 `system_config` 的兩個 key 改回預設（`DELETE` 該列即回到程式內建預設），並 TRUNCATE 測試庫（與 conftest 相同語句）。腳本與截圖存到主 checkout 的 `docs/042-quick-match-check/`（docs/ 為本機資料夾，不進 git）。
