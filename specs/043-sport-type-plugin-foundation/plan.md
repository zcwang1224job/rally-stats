# Implementation Plan: 多活動支援與比賽類型外掛基礎（Sport Type Plugin Foundation）

**Branch**: `feature/sport-type-plugin-foundation` | **Date**: 2026-09-24 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/043-sport-type-plugin-foundation/spec.md`，交叉比對以下檔案（僅閱讀）：`apps/api/app/domains/schedule/{models,service,schemas,router}.py`（脊椎表、`apply_score_delta`、發球與落點、即時狀態）、`apps/api/app/domains/group/{schemas,service,match_stats}.py`（開團、排行榜、詳細頁、純統計）、`apps/api/app/domains/member/{router,service,player_dashboard,insights,group_benchmark,matchups}.py`（儀表板管線與篩選）、`apps/api/app/system_config/service.py`、`apps/api/alembic/{env.py,versions/}`、`apps/api/tests/conftest.py` 與 `tests/unit/domains/_match_history.py`、`apps/web/src/app/{app.routes.ts,app.config.ts}`、`features/{scoreboard,control-panel,group-admin,shot-placement,member,group-join}/**`、`core/{match-record-detail,player-dashboard,court-diagram,match-share-card,group-share-card,api}/**`、`apps/web/{angular.json,eslint.config.js}`。

## Summary

把 Rally Stats 從「羽球專用」改成「任何回合制活動皆可用」，同時建立**比賽類型外掛架構**：核心只保留一條很薄的比賽事件脊椎（既有 `score_events` 加 `kind`）、通用參數（每隊人數、達標／手動結束、領先分、可空上限、平手、加分級距）與活動目錄；每種比賽類型是一個後端 package 加一個前端模組，各自擁有規則、事件種類、型別化資料表、統計、頁面區塊與控制板／計分板呈現。本期實作三種類型：**隔網回合制**（承接羽球全部功能，行為與測試零變更）、**局數制**（先贏 N 局、可選局內逐分）、**通用**（+N、手動結束、可平手）。

技術路線（研究 Decision 1–21 的濃縮）：

1. **零變更優先**：不改表名、不改 ORM 類別名（`ScoreEvent` 等留在原模組）、`match_mode` 保留為相容別名、既有 `/score`／`/end` 端點與 Ably 訊息鍵名不變、儀表板回應形狀不變（新內容走新端點）。羽球邏輯**整個搬**進 `app/sports/types/net_rally/` 與 `src/app/sports/types/net-rally/`，測試只改匯入路徑。
2. **薄脊椎、厚外掛表**：`score_events` 加 `kind`／`side` 可空；場級比分永遠是 `point` 事件；外掛表以 `score_event_id` 外鍵 cascade。局數制的「局」就是脊椎 `point`（`win_by=1`），局內逐分是外掛事件。
3. **核心交易骨架＋外掛掛鉤**：`apply_score_delta` 固定為「原子更新 → 脊椎事件 → 外掛掛鉤 → commit → 達標 → 終局 → publish」；外掛回傳 payload、永不 publish。
4. **參數化勝負**：`match_wins(target, win_by, cap)` 一份，兩處呼叫。平手 `winner_team='D'`。
5. **內建目錄在程式、自訂活動在 `member_sports`**；團與比賽快照 `sport_key`／`type_key`／名稱／通用參數／`type_params`。
6. **前端絞殺者模式**：宿主元件依 `type_key` 解析類型模組並渲染整面元件；詳細頁與儀表板由伺服器回傳區塊清單、`SectionOutlet` 解析、未知區塊通用退路；類型模組獨立 chunk；vitest setup 同步預載 `net-rally` 讓既有 spec 保持同步。
7. **邊界自動化**：後端 `import-linter` 三條契約、前端 eslint `no-restricted-imports`、兩個契約測試，納入品質關卡指令；憲章修訂為 1.1.0（原則 III 完賽定義、新增原則 XII）。

## Technical Context

**Language/Version**: Python 3.12（後端）、TypeScript 5.x／Angular 20（前端）

**Primary Dependencies**: FastAPI、SQLAlchemy 2 async、Alembic、pydantic 2、Ably；Angular 20 standalone＋signals、`@ngx-translate`、vitest。**新增 dev 依賴**：`import-linter`（後端）。前端不新增套件。

**Storage**: PostgreSQL（既有）。一支 Alembic migration（含 downgrade）：`groups`／`matches` 通用參數欄位與回填、`score_events.kind`／`side` 可空、`cap_score` 可空、新表 `member_sports`、`frames_frame_results`、`frames_frame_points`、`system_config` 新 key。

**Testing**: pytest（278 檔、約 1,623 個測試，全數須通過且斷言不改）、vitest（97 spec、約 1,116 個 `it`，同上）；新增：外掛單元測試、契約測試（後端 kind 清單／前端 outlet）、邊界 lint、局數制與通用類型的契約與整合測試、`match_wins` 參數化等價測試。

**Target Platform**: Web（既有 Docker 映像流程不變；無新環境變數）

**Project Type**: Web application（`apps/api` + `apps/web`）

**Performance Goals**: 詳細頁與儀表板的請求次數與延遲不劣於升級前（羽球儀表板仍為一次 `match-dashboard` 呼叫；詳細頁一次呼叫拿到 `sections`）；局數制 `live_state()` 推導每次 ≤ 2 個查詢。

**Constraints**: 研究 F1–F10（測試釘點、TRUNCATE、`server_default`、同步 spec、無 CI）；每隊人數本期 1–2；每場 2 隊；不改 `score_events` 表名。

**Scale/Scope**: 後端新增 1 個 package（`app/sports`，3 個外掛）、約 8 個新端點、1 支 migration；前端新增 `src/app/sports/`（registry、outlet、7 個宿主、3 個類型模組），搬移約 12 個既有元件／模組；i18n 新增約 120 個 key × 2 語言。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | 後端外掛介面以 `Protocol`＋pydantic model 定義（`type_params`、事件 payload、`Section`）；`type_params` JSONB 在邊界即驗證成 typed model，核心不以 `dict` 亂傳。前端 `SportTypeModule`、`Section`、`SectionComponent` 明確型別；`sectionKinds` 為 `Record<string, Type<SectionComponent>>`。`mypy --strict`、`tsc`、`ng lint` 沿用 blocking；新增 `lint-imports` 與 eslint 邊界規則同列關卡。 | PASS |
| II. 測試優先 | 核心規則：`scoring.match_wins` 參數化（先以既有 `test_match_wins.py` 表格證明等價，再加 `win_by=1`／`cap=None` 案例）、脊椎 `kind` 過濾、平手彙總、`/finish`／`/undo`／`/events` 的狀態機、局數制事件→狀態、`SectionOutlet` 退路——**spec 先於實作**。羽球：既有 278＋97 個測試作為回歸底線，斷言零修改（允許：匯入路徑、TestBed providers／mock 補方法、vitest setup 檔）。端到端：撞球搶五「開團→排點→計分→結束→排行榜→詳細頁→儀表板」整合測試；通用類型平手流程；桌球無發球模組流程。 | PASS（tasks.md 強制先寫測試） |
| III. 即時性與資料一致性 | 所有比分／事件變更仍「先寫 DB 再 publish」，publish 只從 `schedule.service.publish` 發出（外掛回傳 payload）。設定快照：`matches` 快照全部通用參數與 `type_params`。**完賽定義**：達標模式維持「達標自然結束」；手動結束模式新增「計分員宣告結束並記錄結果」也產生 MatchResult——**與現行原則 III 文字衝突**，以憲章修訂處理（見 Complexity Tracking）；放棄比賽（原提前結束）與所有中止情境一律 `abandoned`、不計成績，原則不變。 | PASS（附憲章修訂） |
| IV. 權限與安全 | 新端點 `/events`、`/finish`、`/undo` 與 `/score` 同級（計分員操作），在三個授權面沿用既有依賴；不新增任何管理員專屬操作到免驗證畫面。自訂活動只限 `require_verified_member`、只讀寫本人資料；`sport_key='custom'` 開團須為本人（`403`）。活動名稱為自由文字，前端沿用既有逸出（`app-nickname` 同級處理）。`sport`／`custom_sport_id` 開團後不可改。 | PASS |
| V. 破壞性操作二次確認 | 「放棄比賽」沿用既有確認對話；「結束並記錄結果」新增確認（含平手提示）；局數制「分低者被標勝」二次確認；刪除自訂活動確認。兩個結束動作以不同名稱與文案區分（FR-017a）。 | PASS |
| VI. 可維護性 | 依賴方向單向：外掛 → 核心（models／plugin／presentation／scoring），核心 → registry 介面，組裝根（`main.py`、`alembic/env.py`、`registry.ts`、`test-setup.ts`）是唯一例外並以行內註記標示。核心不得查詢外掛表、不得依活動分支；外掛之間互不匯入。以 `import-linter`、eslint、契約測試機械強制。既有的 `core → features` 反向匯入（研究 F8 列出）不在本期修正範圍，但搬移羽球元件時不得新增此類反向匯入。 | PASS |
| VII. 無障礙與行動裝置優先 | 局數制與通用的控制板按鈕沿用既有 44px 觸控目標與鍵盤可操作；計分板局數與本局比分沿用大字體樣式；活動圖示一律配文字標籤；平手以「平」文字呈現不只靠顏色；活動卡片以 `<button aria-pressed>`。 | PASS |
| VIII. i18n 與時區 | 內建活動名稱、名詞、區塊標題、指標名稱、新錯誤碼全部為 i18n key（zh-TW／en 同步，沿用 key-parity spec 模式）；自訂活動名稱為使用者輸入不翻譯；後端只回 error code 與 `*_key`。無新時間欄位；事件時間沿用 `created_at`（UTC）。 | PASS |
| IX. 可攜性與可部署性 | 一支 migration，Docker 流程不變，無新環境變數；`import-linter` 只是 dev 依賴。既有測試 session 的 `downgrade base` 要求 migration downgrade 可用。 | PASS |
| X. 伺服器為可信來源 | 區塊清單、勝負、平手、局數狀態、活動目錄全由伺服器決定；前端只渲染。外掛即時狀態隨 Ably 訊息由伺服器推送；前端不自行推導局數。 | PASS |
| XI. 防濫用 | 開團仍走 Turnstile；`POST /members/me/sports` 是新的「建立資源」端點但只限已驗證會員且每人上限 20（`409 CUSTOM_SPORT_LIMIT`），不另加 CAPTCHA（與註冊／開團的公開端點性質不同，記錄於此供 review）。 | PASS |
| XII. 比賽類型外掛邊界（憲章 1.1.0 新增） | 本功能即此原則的落地：核心不依活動分支（研究 Decision 3、8、11）、不匯入外掛（組裝根例外並以行內註記標示）、不查詢外掛表（grep 契約測試）、外掛互不匯入且不 publish、新增類型只加不改（contracts/plugin-boundary.md §5）、每型附測試；`import-linter`＋eslint＋區塊契約測試列入品質關卡（研究 Decision 15）。 | PASS |

**Gate 結果**：原則 III 的完賽定義需修訂憲章（已於本 plan 完成後以 `/speckit-constitution` 修訂為 1.1.0，同時新增原則 XII）；原則 VI 的「核心匯入外掛 registry」為介面依賴（非實作依賴）且限組裝根，記錄於 Complexity Tracking。其餘無違反。

**Post-design re-check（Phase 1 完成後）**：data-model.md 確認所有新 NOT NULL 欄位皆有 `server_default`、外掛表皆 cascade 到脊椎、`completed ⇒ winner_team ∈ {A,B,D}` 不變量成立；contracts/ 確認既有端點只做新增欄位或放寬型別（`delta: int`、`cap_score: int | null`、`winner_team` 加 `D`）、三個釘死形狀的端點零變更、新動作只在既有三個授權面；plugin-boundary.md 確認 import-linter／eslint 規則可在不新增前端套件下落地。Gate 結果維持 PASS（附憲章修訂）。妥協：`EndingType`／`RecordShotPlacementRequest` 仍留在核心 `schedule/schemas.py`（既有請求形狀釘點與 `net_rally.stats.EndingType is schedule.schemas.EndingType` 同一性），由隔網回合制外掛引用，見 research.md Decision 10。

## Project Structure

### Documentation (this feature)

```text
specs/043-sport-type-plugin-foundation/
├── plan.md                      # 本文件
├── research.md                  # Phase 0：21 條決策
├── data-model.md                # Phase 1：資料表、擁有權、快照、狀態機、外掛介面
├── quickstart.md                # Phase 1：驗證流程
├── contracts/
│   ├── sports-api.md            # 活動目錄、自訂活動、開團／編輯、列表篩選、活動清單
│   ├── match-events-api.md      # /score 放寬、/events、/finish、/undo、即時狀態、Ably
│   ├── sections-manifest.md     # Section 形狀、各類型區塊、詳細頁與儀表板端點、契約測試
│   └── plugin-boundary.md       # 前後端目錄邊界、import-linter／eslint 規則、外掛介面、新增類型清單
├── checklists/requirements.md
└── tasks.md                     # Phase 2（/speckit-tasks，本命令不產生）
```

### Source Code (repository root)

```text
apps/api/
├── app/
│   ├── main.py                              # 呼叫 app.sports.types.register_all()
│   ├── sports/                              # 新：核心外掛基礎
│   │   ├── registry.py  plugin.py  presentation.py  scoring.py  catalog.py  section-kinds.json
│   │   └── types/
│   │       ├── __init__.py                  # register_all()
│   │       ├── net_rally/   plugin.py params.py serve.py placement.py stats.py dashboard.py schemas.py
│   │       ├── frames/      plugin.py params.py models.py events.py stats.py presentation.py
│   │       └── generic/     plugin.py params.py presentation.py
│   ├── domains/
│   │   ├── group/{models,schemas,service,router}.py        # sport 欄位、通用參數、平手彙總、sections、篩選
│   │   ├── group/match_stats.py                            # 只留核心純函式
│   │   ├── schedule/{models,schemas,service,router}.py     # 脊椎 kind、交易骨架、/events /finish /undo、live_state
│   │   ├── member/{router,service,schemas}.py              # sport 篩選、activities、dashboard-sections、member_sports
│   │   ├── member/player_dashboard.py                      # metric_specs 參數化
│   │   ├── member/insights.py                              # 目錄注入
│   │   └── member/sports_models.py                         # MemberSport ORM（或置於 app/sports/models.py，屬核心）
│   └── system_config/service.py                            # 依 sport_key 查表
├── alembic/env.py                                          # 匯入外掛 models
├── alembic/versions/<rev>_sport_type_plugin_foundation.py  # 單一 migration
├── pyproject.toml                                          # [tool.importlinter]
├── requirements-dev.txt                                    # import-linter
└── tests/
    ├── unit/sports/                                        # 新：registry、scoring、catalog、契約、frames、generic
    ├── unit/domains/**（既有，僅匯入路徑調整）
    ├── contract/test_sports_*.py  test_match_events_*.py  test_dashboard_sections_*.py
    └── integration/test_frames_flow.py  test_generic_flow.py  test_table_tennis_flow.py

apps/web/src/app/
├── app.routes.ts                     # 計分板／控制板／全部場地路由改掛宿主
├── sports/                           # 新（見 contracts/plugin-boundary.md §3）
│   ├── registry.ts  sport-type-module.ts  section-outlet/  generic-sections/  hosts/
│   └── types/{net-rally,frames,generic}/
├── core/api/*.models.ts              # SportSummary、Section、cap_score 可空、delta: number、draws
├── core/api/sports.service.ts        # GET /sports、自訂活動、activities、dashboard-sections
├── features/group-admin/create-group/  admin-page/  shared/group-form-validators.ts   # 活動區塊、team_size、通用參數
├── features/group-join/group-list/   features/member/my-groups/   features/member/match-history/   # sport 篩選、活動標籤、活動頁籤
├── core/match-share-card/  core/group-share-card/           # 活動名稱、亮點改由類型模組提供
├── assets/i18n/{zh-TW,en}.json       # sports.*、frames.*、genericSport.*、errors.*
├── test-setup.ts                     # 預載 net-rally
├── angular.json                      # test.options.setupFiles
└── eslint.config.js                  # no-restricted-imports 覆寫
```

**Structure Decision**：維持既有的 `apps/api`＋`apps/web` 雙專案；在兩邊各加一個 `sports/` 頂層目錄承載「外掛基礎（核心）」與「類型外掛」，以目錄邊界（而非新 package／新 app）落實可擴充性，讓 import-linter 與 eslint 能以路徑規則強制。

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| 原則 III「只有達標自然結束才產生 MatchResult」與 `end_mode='manual'` 的「結束並記錄結果」衝突 | 籃球、足球、桌遊等活動沒有「達標」概念，必須由計分員宣告結束才能有勝負與排行榜（規格 FR-017、clarify Q2） | 「手動模式的比賽一律 abandoned」等於這些活動沒有戰績，違反本功能目的；以憲章 MINOR 修訂把「完賽」定義為「依該團活動的結束規則完賽」，放棄比賽仍 abandoned，原則精神不變 |
| 原則 VI：核心 `registry.py` 在型別上認識「外掛介面」，`main.py`／`alembic/env.py`／`registry.ts`／`test-setup.ts` 實際匯入外掛 | 外掛必須在某處註冊；組裝根是唯一合理位置 | 以 entry points／自動掃描套件實作「零匯入註冊」——多一層魔法、mypy 無法檢查、與現有單體結構不符；改以 import-linter 明列組裝根為例外，邊界仍可機械驗證 |
| `match_mode` 與 `team_size` 並存（兩個欄位表達同一件事） | 研究 F4：210 個測試檔依賴 `match_mode`，刪除會違反「斷言零修改」 | 只在 API 層做別名——ORM kwarg 仍壞；第二期做 `team_size ≥ 3` 時一次移除 |
| `ScoreServeRecord`／`ShotPlacementRecord` 的 ORM 類別留在核心模組但由外掛擁有 | 研究 F1：10 個測試檔從 `app.domains.schedule.models` 匯入並建構 | 搬到外掛並留 alias＝核心匯入外掛；改以 grep 契約測試守「核心不得 select 這兩個類別」 |

## Implementation Strategy（供 /speckit-tasks 分解）

依規格使用者故事的優先序，並讓每一階段結束時測試全綠：

1. **基礎與零變更（US1）**：migration；`Group`／`Match` 新欄位與 validator；`scoring.match_wins`；脊椎 `kind`；`app/sports` 介面與 registry；`net_rally` 外掛承接（搬移發球／落點／統計／指標目錄，測試改路徑）；`apply_score_delta` 骨架化；核心讀者過濾 `point`；`system_config` 查表；前端 `sports/` 基礎（registry、outlet、hosts、test-setup）＋搬移羽球元件；`import-linter`／eslint 規則；契約測試。**驗收：既有全部測試通過、`lint-imports` 與 `ng lint` 通過。**
2. **活動目錄與開團（US2）**：`catalog.py`、`GET /sports`、`CreateGroupRequest` 新欄位與驗證、回應 `sport`／`team_size`、`create-group` 活動區塊與類型 `createFormFields`、管理頁參數編輯與 `SPORT_IMMUTABLE`、名詞化文案、預設團名／場地名。
3. **局數制（US3）**：`frames` 外掛（params、models、events、live_state、stats、sections）、`/events`／`/undo`、前端 `frames` 模組（計分板、控制板、區塊）、Ably `match.eventApplied`。
4. **通用類型與平手（US5）**：`generic` 外掛、`/score` 放寬、`/finish`、`winner_team='D'` 與 `draws` 彙總、前端 `generic` 模組、結束動作文案。
5. **自訂活動（US4）**：`member_sports`、`POST/DELETE /members/me/sports`、目錄「我的自訂」區、訪客「其他」。
6. **篩選、頁籤、分享（US6）**：`sport` 篩選（groups、my-groups、四路由）、`activities` 端點、`dashboard-sections`、match-history 活動頁籤、分享圖卡活動名與類型亮點。
7. **可擴充性驗收（US7）**：section-kinds.json 契約、SC-005 的 diff 驗證腳本（quickstart）、chunk 驗證、憲章修訂（`/speckit-constitution` 1.1.0）與 docs 更新（features.md、tools.md、cicd-pipeline.md 關卡指令）。

## Risks & Mitigations

| 風險 | 緩解 |
|---|---|
| `apply_score_delta` 骨架化改變羽球 `match.scoreUpdated` payload 或 commit 順序 | 先寫「payload 位元相同」的整合測試（沿用 `test_scoring_flow.py` 的 monkeypatch 模式）再重構；`serve` 鍵名保留 |
| 脊椎 `kind` 過濾遺漏，非 `point` 事件混入比分走勢／完整度判定 | 核心讀者統一走 `point_events(match_id)` 查詢函式；契約測試以含 `frame_point` 的資料驗證羽球讀者不受影響 |
| 前端 spec 因宿主非同步載入而失敗 | `test-setup.ts` 同步預載；宿主在 `peek()` 命中時同步渲染；先跑全部 spec 再動任何模板 |
| `match_mode`／`team_size` 不同步 | 模型層單一推導函式＋單元測試矩陣；API 兩者皆給時強制一致 |
| 測試 DB `downgrade base` 因新 migration 的 downgrade 失敗 | migration 先寫 downgrade 並在 quickstart 列入 `alembic downgrade -1 && upgrade head` 檢查 |
| 邊界規則落地後才發現既有 `core → features` 反向匯入導致 eslint 覆寫誤報 | 規則只針對 `sports/types/**` 模式，不觸及既有反向匯入；既有問題另案 |
