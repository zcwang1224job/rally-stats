# Quickstart: 多活動支援與比賽類型外掛基礎（043）

**Plan**: [plan.md](./plan.md) | **Contracts**: [contracts/](./contracts/)

本文件是驗證指南：每一節對應規格的一個使用者故事或成功指標，列出前置條件、指令與預期結果。實作細節在 tasks.md。

## 0. 前置條件

- 本地 Postgres（`infra/docker-compose.yml` 的 `infra-db-1`），測試 DB `rally_stats_test`。
- 後端：`cd apps/api && uv sync`（含新 dev 依賴 `import-linter`）。
- 前端：`cd apps/web && npm ci`。
- 若在 `.claude/worktrees/` 下驗證：後端把主 checkout 的 `.venv/bin` 放到 PATH，前端把 `node_modules` 以 symlink 接上（見專案既有做法）。

## 1. 零變更回歸（US1、SC-001、SC-002）

```bash
cd apps/api
alembic upgrade head && alembic downgrade -1 && alembic upgrade head     # migration 與 downgrade 可用
ruff check app tests && mypy app && lint-imports                          # 含新邊界契約
python -m pytest -q -rf 2>&1 | tee /tmp/043-backend.txt                   # 約 20 分鐘；全部通過
git diff origin/ut -- tests/ | grep -E '^\+.*expect|^\+.*assert' | wc -l  # 預期 0：既有測試檔沒有新增／修改的斷言（新測試檔除外，另以路徑過濾）
cd ../web
npm run lint && npx ng test --watch=false 2>&1 | tee /tmp/043-web.txt      # 全部通過
```

預期：既有 278 個後端測試檔與 97 個前端 spec 全數通過；`git diff --stat origin/ut -- apps/api/tests apps/web/src/app/**/*.spec.ts` 只出現匯入路徑、TestBed providers／mock 補方法與 `test-setup.ts` 的變更。

**手動比對**：以升級前的種子資料（`apps/api/scripts/seed_dashboard_demo.py`）分別在升級前後啟動，登入 `demo@example.com`，比對「我的團 → 週三羽球團 → 戰績／對戰紀錄詳細頁／分享圖卡」與「對戰紀錄 → 統計」頁籤的每個數值。

## 2. 開團選活動並計分（US2、SC-003）

1. `/groups/new`：第一個區塊為活動目錄，預設羽球；選「撞球」→ 每隊人數只剩 1、計分區塊變成「先贏幾局＝5」與「記局內比分」開關；團名佔位文字變「…的撞球團」。
2. 送出後管理頁：場地預設名「球桌一」；`GET /groups/{id}`（管理）回應含 `sport.sport_key="billiards"`、`team_size=1`、`end_mode="target"`、`target_score=5`、`win_by=1`、`cap_score=null`。
3. 嘗試在管理頁改活動：UI 無此欄位；`PATCH /groups/{id}` 帶不同 `sport` → `409 SPORT_IMMUTABLE`。
4. 選「桌球」開團：控制板只有 +1／−1，無發球站位、無落點；比分 10:10 後打到 15:13 自動結束（`cap_score=null`）。

契約測試：`tests/contract/test_sports_catalog.py`、`test_create_group_sport.py`；整合：`tests/integration/test_table_tennis_flow.py`。

## 3. 局數制（US3、SC-004）

```bash
cd apps/api && python -m pytest -q tests/unit/sports/test_frames_plugin.py tests/contract/test_match_events_endpoint.py tests/integration/test_frames_flow.py
```

手動：撞球團開啟局內比分（`frame_target=11`）→ 控制板：本局 +1／−1、「標記本局勝方」、「復原」；計分板顯示「局數 2:1、第 4 局、本局 7:5」；本局 11:9 自動結束該局；標記分低者為勝方出現二次確認；復原一次退一分，再復原到上一局結束處會取消該局結束；贏到第 5 局自動結束比賽並出現在排行榜。詳細頁顯示逐局清單與局數走勢，沒有發球／落點／deuce 區塊；儀表板「撞球」頁籤顯示場勝率、局勝率、先贏第一局後勝率、平均局數。

## 4. 通用類型與平手（US5）

手動：用「其他」開團（每隊 2 人、加分級距 1 與 2、手動結束、允許平手）→ 控制板顯示 +1／+2 各隊與復原、「結束並記錄結果」與「放棄比賽」兩個按鈕（名稱、確認文案不同）→ 7:7 按「結束並記錄結果」→ 排行榜顯示 1 平；再開一團不允許平手 → 同分結束被拒（`409 DRAW_NOT_ALLOWED` → 前端提示需先分出勝負）；任一團按「放棄比賽」→ 不計成績。

測試：`tests/unit/sports/test_generic_plugin.py`、`tests/unit/domains/group/test_standings_draws.py`、`tests/contract/test_finish_endpoint.py`、`tests/integration/test_generic_flow.py`。

## 5. 自訂活動（US4）

會員登入 → `/groups/new` 目錄「我的自訂」→「新增自訂活動」：名稱、類型、參數 → 出現在目錄並可開團；第 21 個 → `409 CUSTOM_SPORT_LIMIT`；同名 → `409 CUSTOM_SPORT_NAME_TAKEN`；刪除後既有團仍顯示原名稱（`sport_name` 快照）；訪客只看到內建與「其他」，無保存選項。

測試：`tests/contract/test_member_sports_endpoint.py`。

## 6. 篩選、頁籤、分享（US6）

- `/groups?sport=billiards`、`/groups?sport=custom_or_other`；`/members/me/groups?sport=custom:<id>`。
- 對戰紀錄「統計」頁籤：有羽球與撞球紀錄時顯示活動頁籤；只有一種時無頁籤列；羽球頁與升級前相同；撞球頁走 `GET /members/me/dashboard-sections?sport=billiards`。
- 分享圖卡：撞球單場卡顯示活動名、局數、勝方、成員，無亮點區塊、無走勢圖；羽球卡除活動名外與升級前一致（`share-card-renderer.spec.ts` 的既有 `texts()` 斷言不變）。

## 7. 可擴充性（US7、SC-005、SC-006、SC-008）

```bash
# 邊界：故意在核心加一行匯入外掛，關卡必須失敗
cd apps/api && echo "from app.sports.types.frames.plugin import FramesPlugin" >> app/domains/group/service.py && lint-imports; git checkout app/domains/group/service.py
cd ../web && echo "import '../../sports/types/frames/frames.module';" >> src/app/core/nickname/nickname.component.ts && npm run lint; git checkout src/app/core/nickname/nickname.component.ts

# SC-005：局數制與通用外掛的改動範圍
git log --format=%H --grep='frames' -- . | head -1 | xargs -I{} git show --name-only --format= {} | grep -vE '^(apps/api/app/sports/types/frames/|apps/web/src/app/sports/types/frames/|apps/api/alembic/versions/.*frames|apps/web/src/assets/i18n/|apps/api/app/sports/catalog.py|apps/api/app/sports/types/__init__.py|apps/web/src/app/sports/registry.ts|apps/api/tests/|apps/web/src/app/sports/types/frames/.*spec)' 
# 預期輸出為空（tasks.md 會把 frames／generic 各自的實作收斂成可獨立檢視的提交）

# SC-006：獨立 chunk
npx ng build --configuration production && ls dist/web/browser | grep -E 'frames|generic' && ! grep -l 'frames.frame_list' dist/web/browser/main-*.js

# SC-008：未知區塊退路
npx ng test --watch=false --include='src/app/sports/section-outlet/*.spec.ts'
```

## 8. 憲章與文件

- `.specify/memory/constitution.md` 版本 1.1.0：定位、原則 III 完賽定義、原則 XII 外掛邊界（`/speckit-constitution` 產出）。
- `docs/features.md`（功能總覽加「活動與比賽類型」）、`docs/tools.md`（`system_config` 新 key）、`docs/cicd-pipeline.md`（關卡指令加入 `lint-imports`）。
