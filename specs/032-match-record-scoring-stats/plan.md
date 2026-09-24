# Implementation Plan: 對戰紀錄逐點得失分球員與落點資訊、球員得失分統計

**Branch**: `032-match-record-scoring-stats` | **Date**: 2026-09-16 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/032-match-record-scoring-stats/spec.md`，交叉比對 `/apps/api/app/domains/group/service.py`（`build_match_record_detail()`——016-match-score-timeline 既有的比賽詳情組裝函式，四個既有端點的唯一共用入口）、`/apps/api/app/domains/schedule/models.py`（`ShotPlacementRecord`——031/032 已寫入、但從未被任何「查看」畫面讀取過的落點資料表）、`/apps/web/src/app/core/match-record-detail/match-record-detail-dialog.component.{ts,html}`（016 既有的三處對戰紀錄清單共用比賽詳情彈窗）、`/apps/web/src/app/features/shot-placement/shot-placement-picker.component.{html,scss}`（031 既有的互動式球場示意圖，本功能唯讀重用其視覺呈現）。

## Summary

擴充既有「比賽詳情」回應（`MatchRecordDetailResponse`），讓已開啟詳細計分模式的比賽，其逐點加減分紀錄（`ScoreEventSummary`）附帶當時記錄的得分/失分球員暱稱與落點座標（來自既有 `ShotPlacementRecord`，本功能是第一個讀取它的畫面），並新增一份以整場比賽為範圍、即時計算的「球員得失分統計」（`player_stats`）。這是純粹的**唯讀擴充**——不新增資料表、不新增欄位、不新增任何寫入路徑，只在既有的 `build_match_record_detail()` 這一個函式內多做兩件事：(1) 一次查詢把該場比賽所有 `ShotPlacementRecord` 依 `score_event_id` 建索引，逐一附掛到對應的 `ScoreEventSummary`；(2) 對這些記錄依 `roster_entry_id`/`losing_roster_entry_id` 分別加總，產出每位參賽球員的得分/造成失分次數。由於四個既有端點（團對戰紀錄、會員個人跨團對戰紀錄、會員歷史戰績、查看好友對戰紀錄）全部共用同一個 `build_match_record_detail()`，此擴充自動套用到全部四處，不需要新增任何端點。前端則擴充既有的單一共用彈窗元件 `MatchRecordDetailDialogComponent`：逐點清單每一列視情況顯示球員暱稱徽章，點擊已有記錄的列原地展開球場示意圖（Clarifications 2026-09-16 決議），並新增一個球員得失分統計區塊；球場示意圖唯讀重用既有 `shot-placement-picker` 元件已經畫好的 `.court`/`.landing-marker`/`.out-of-play-band` 純視覺區塊，抽出成一個新的共用唯讀元件，避免重複實作球場繪製邏輯。

## Technical Context

**Language/Version**：延續既有（後端 Python 3.12+，FastAPI + SQLAlchemy 2.0 async；前端 Angular 20 + TypeScript strict mode）。

**Primary Dependencies**：沿用既有 FastAPI/SQLAlchemy（後端）與既有 Angular standalone components/signals（前端）堆疊，**不新增任何第三方套件**。球場示意圖唯讀呈現重用既有 031 詳細計分畫面已建立的純 CSS 繪製技巧（`shot-placement-picker.component.scss` 的 `.court`），抽出成一個新的共用元件，供互動版（計分當下）與唯讀版（本功能）共同使用。

**Storage**：PostgreSQL，**不需要任何 Alembic migration**——本功能純讀取既有的 `shot_placement_records`（031/032 已建）、`score_events`（007 已建）、`match_participants`/`roster_entries`（既有）等資料表，不新增欄位、不新增資料表。

**Testing**：
- 後端：pytest（單元測試擴充 `build_match_record_detail()`——附掛落點紀錄到對應事件、只計入已記錄欄位的球員統計加總、完全沒有落點紀錄時 `player_stats` 回傳空陣列、扣分事件〔delta=-1〕永遠沒有 `detail`、一場比賽同時存在「開啟前無落點資料」與「開啟後有落點資料」事件並存的情況；契約測試擴充既有 `MatchRecordDetailResponse` 回應形狀斷言，涵蓋四個既有端點中至少各一個）。
- 前端：Vitest（`MatchRecordDetailDialogComponent` 擴充測試——球員徽章顯示條件、點擊展開/收合/切換行為（同時間至多一筆展開）、新的球員得失分統計區塊含「全數掛零」與「完全無資料時顯示提示」兩種狀態；新抽出的共用唯讀球場示意圖元件的獨立單元測試）。

**Target Platform**：延續既有（Docker on AWS ECS；瀏覽器：與既有對戰紀錄頁面相同的行動裝置優先支援範圍）。

**Project Type**：Web application（monorepo，本功能同時涉及 `apps/api` 與 `apps/web`，但範圍侷限在既有「查看比賽詳情」這一條路徑上，不涉及計分寫入路徑）。

**Performance Goals**：比賽詳情頁面既有的載入時間不應因本功能明顯劣化——新增的落點紀錄查詢以 `match_id` 為條件（既有索引），單場比賽筆數上限等同該場比賽的加分事件數（≤ `cap_score`，數量級小，一般 ≤ 30 筆），可與既有的 `score_events` 查詢在同一次請求內以一次額外查詢完成，不需要分頁或額外快取層。

**Constraints**：本功能是**唯讀**擴充，不得新增或修改任何計分當下（詳細計分模式挑選畫面）的寫入邏輯或資料格式（spec Assumptions）；落點/球員資訊只在「當時確實記錄了對應欄位」時才顯示，不得推論或補齊未記錄的欄位（FR-001/FR-002/FR-007）；同一時間至多一筆加分紀錄處於展開狀態（Clarifications 2026-09-16，FR-004a）；本功能新增的顯示對象與可見範圍 MUST 與各既有端點原本的授權規則完全一致（FR-011）——不得因為新增欄位而意外放寬或限縮任何一個既有端點的授權判斷。

**Scale/Scope**：後端變更集中在 1 個既有函式（`build_match_record_detail()`）+ 其所在的 schemas；前端變更集中在 1 個既有共用彈窗元件 + 新增 1 個共用唯讀球場示意圖元件（從既有互動元件抽出）。範圍明顯小於 031（031 是新增一整套計分互動 + 新資料表 + 新端點），因為本功能不寫入、不新增端點，純粹讀取並呈現既有已經存在的資料。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| 原則 | 本 feature 的因應方式 | 結果 |
|---|---|---|
| I. 型別安全 | 新增的 Pydantic schema（`ShotPlacementSummary`、`PlayerScoringStat`）與 `ScoreEventSummary.detail`/`MatchRecordDetailResponse.player_stats` 皆為明確型別；前端對應的新 TypeScript interface 全程 strict mode。`ruff`/`mypy`/`tsc --noEmit`/`ng lint` 沿用既有 CI blocking check。 | PASS |
| II. 測試優先 | 本功能是既有「比分計算」核心邏輯（`build_match_record_detail()`）的直接讀取延伸，MUST 有單元測試涵蓋落點附掛、球員統計加總、扣分事件無 detail、完全無資料時的空陣列行為；MUST 有契約測試涵蓋擴充後的回應形狀。 | PASS（列入 tasks.md 強制項） |
| III. 即時性與資料一致性 | 本功能不新增任何寫入路徑，不影響既有比分/賽程狀態的一致性保證；讀取的落點紀錄本身已受 031/032 既有交易邊界保護（與觸發它的 `ScoreEvent` 同一交易寫入，或透過既有的 -1 收回機制刪除），本功能只是把既有已一致的資料呈現出來。 | PASS |
| IV. 權限與安全 | 不新增任何端點，四個既有端點（`GET /groups/{group_id}/match-records/{match_id}`、`GET /members/me/match-records/{match_id}`、`GET /members/{member_id}/match-records/{match_id}`、好友檢視變體）的既有授權判斷式完全不變，只是回應內容多了欄位；新增的球員暱稱資訊全部來自該回應原本就會回傳的 `team_a`/`team_b` 名單，未擴大任何資訊揭露範圍。 | PASS |
| V. UX 一致性（破壞性操作二次確認） | 本功能純呈現、無任何破壞性或不可逆操作，不適用。 | 不適用 |
| VI. 可維護性 | 後端：擴充既有 `build_match_record_detail()` 單一函式，不建立平行的第二套組裝邏輯，四個端點自動受惠。前端：把球場示意圖的純視覺繪製（`.court`/`.landing-marker`/`.out-of-play-band`）從既有互動元件（`shot-placement-picker`）抽出成一個新的共用唯讀元件，供互動版與本功能唯讀版共同使用，避免兩份重複的球場繪製 CSS/HTML（呼應 research.md Decision 5）。 | PASS |
| VII. 無障礙與行動裝置優先 | 球員暱稱徽章與得失分統計以文字呈現，不僅依賴顏色；落點標記沿用既有 `shot-placement-picker` 已符合本原則的視覺設計（邊框而非純色塊區分）。展開/收合互動 MUST 提供可辨識的觸控目標與 `aria` 屬性（沿用既有 `matchRecordDetail` 對話框的既有無障礙慣例）。 | PASS |
| VIII. i18n 與時區 | 新增顯示文字（球員徽章標籤、「未記錄落點」提示、球員得失分統計標題與欄位、「此比賽沒有球員得失分紀錄」提示）MUST 全數放入既有語系檔（`zh-TW.json`/`en.json`），不寫死文字；本功能不新增任何時間欄位，不涉及原則 VIII 的時區規則。 | PASS |
| IX. 可攜性與可部署性 | 不新增 migration、不新增第三方套件、不新增基礎設施，沿用既有部署流程。 | PASS |
| X. 即時同步的可信來源 | 本功能完全不涉及比分/賽程狀態的寫入或即時廣播，純粹是既有「查看已完成比賽」端點的回應擴充；所有顯示資料均由後端組裝回傳，前端不做任何跨欄位推論（例如不因為只有 landing 就自行猜測球員）。 | PASS |
| XI. 防機器人/防濫用 | 不新增任何「建立新資源」類型的公開端點。 | 不適用 |

**Gate 結果**：無違反項目，不需填寫 Complexity Tracking。

## Project Structure

### Documentation (this feature)

```text
specs/032-match-record-scoring-stats/
├── plan.md              # This file (/speckit-plan command output)
├── research.md          # Phase 0 output (/speckit-plan command)
├── data-model.md        # Phase 1 output (/speckit-plan command)
├── quickstart.md        # Phase 1 output (/speckit-plan command)
├── contracts/
│   └── match-record-detail-api.md
└── tasks.md              # Phase 2 output (/speckit-tasks command — NOT created by /speckit-plan)
```

### Source Code (repository root)

```text
apps/api/
├── app/domains/group/
│   ├── schemas.py          # + ShotPlacementSummary
│   │                       # + PlayerScoringStat
│   │                       # + ScoreEventSummary.detail: ShotPlacementSummary | None
│   │                       # + MatchRecordDetailResponse.player_stats: list[PlayerScoringStat]
│   └── service.py          # build_match_record_detail()：新增
│                            #   一次查詢該場比賽所有 ShotPlacementRecord（含 JOIN
│                            #   roster_entries 取得暱稱），依 score_event_id 建索引
│                            #   附掛到對應 ScoreEventSummary；另外依
│                            #   roster_entry_id/losing_roster_entry_id 分別加總，
│                            #   組出 player_stats（參照既有 team_a/team_b 名單，
│                            #   完全無資料時回傳空陣列）
└── tests/
    ├── unit/domains/group/test_match_record_detail_shot_placement.py  # 新增：
    │                                                        #   落點附掛、球員統計
    │                                                        #   加總、扣分事件無
    │                                                        #   detail、無資料時
    │                                                        #   player_stats=[]
    └── contract/test_match_record_detail_endpoint.py         # 既有檔案（若無則新增）
                                                                #   擴充：回應形狀
                                                                #   含 detail/player_stats

apps/web/
└── src/app/
    ├── core/
    │   ├── court-diagram/                    # 新增：從 shot-placement-picker 抽出
    │   │   ├── court-diagram.component.ts     #   的共用唯讀球場示意圖元件（`.court`/
    │   │   ├── court-diagram.component.html   #   `.landing-marker`/`.out-of-play-band`
    │   │   ├── court-diagram.component.scss   #   純視覺渲染，無 pointer 事件）
    │   │   └── court-diagram.component.spec.ts
    │   └── match-record-detail/
    │       ├── match-record-detail-dialog.component.ts    # + 球員徽章顯示邏輯、
    │       │                                                #   展開/收合狀態
    │       │                                                #   （expandedEventIndex）、
    │       │                                                #   player_stats 呈現
    │       ├── match-record-detail-dialog.component.html   # + 逐點列的球員徽章、
    │       │                                                #   原地展開的球場示意圖區塊、
    │       │                                                #   球員得失分統計區塊
    │       └── match-record-detail-dialog.component.spec.ts
    ├── core/api/
    │   └── group-member-view.models.ts        # + ShotPlacementDetail interface
    │                                            # + PlayerScoringStat interface
    │                                            # + ScoreEventSummary.detail
    │                                            # + MatchRecordDetailResponse.player_stats
    └── features/shot-placement/
        ├── shot-placement-picker.component.ts   # 改用新的共用 <app-court-diagram>
        │                                          #   取代原本內嵌的 .court 區塊，
        │                                          #   .court-area 的 pointer 處理邏輯
        │                                          #   不變
        └── shot-placement-picker.component.html
```

**Structure Decision**：後端集中在既有 `apps/api/app/domains/group/` 一個模組（`build_match_record_detail()` 原本就住在這裡），不新增後端模組、不新增端點；前端擴充既有 `core/match-record-detail/` 共用彈窗元件，並新增 1 個共用唯讀元件（`core/court-diagram/`）供該彈窗與既有 `features/shot-placement/` 互動元件共同使用，避免球場繪製邏輯重複（呼應原則 VI）。

## Complexity Tracking

*本 feature 無 Constitution Check 違反項目，此表格從略。*

## Post-Design Constitution Check

*Re-evaluated after Phase 1（`data-model.md`、`contracts/`、`quickstart.md`）產出。*

設計階段的關鍵決策——(1) 落點/球員資訊以巢狀 `ScoreEventSummary.detail` 物件呈現，比照既有 `MatchLiveDetail.serve`（`ServeStationInfo | None`）的巢狀慣例而非把四個欄位攤平（research.md Decision 1），(2) 「有無可顯示的 detail」定義為至少一個欄位有記錄，而非「這筆 ScoreEvent 是否曾經呼叫過 `/shot-placement`」，正確涵蓋「按下確認但什麼都沒選」這個既有可能的邊界情況（research.md Decision 2），(3) 球員得失分統計以「兩個獨立欄位各自加總」而非「以每一筆記錄視為單一得失分配對」計算，正確反映一筆紀錄可能只設定其中一個欄位的既有資料模型（research.md Decision 3），(4) `player_stats` 用「空陣列」單一訊號同時代表「完全無資料」，非空時必定包含比賽全部參賽者（含 0 次的球員），不新增額外的 boolean 旗標（research.md Decision 4），(5) 前端抽出共用唯讀球場示意圖元件而非複製既有 CSS（research.md Decision 5），(6) 單打/雙打完全由既有的 `team_a`/`team_b` 人數推導，不新增 `match_mode` 欄位（research.md Decision 6）——皆為在既有函式/既有回應物件內完成的延伸，未新增任何端點、未新增任何資料表/欄位、未變更任何既有欄位的既有語意（`MatchRecordDetailResponse` 現有欄位全部維持原樣，只新增欄位）。對照 Technical Context/Constitution Check 兩節的判定，Phase 1 設計沒有引入任何新的違反項目。**Gate 結果維持 PASS，無需新增 Complexity Tracking 項目。**

## Assumptions

- 沿用 spec Assumptions 的既有決議：得失分統計為即時計算的衍生資料，不落地儲存；落點視覺重用既有球場示意圖呈現方式；點擊查看落點為既有比賽詳情對話框內的原地展開（Clarifications 2026-09-16），不另開新對話框、不跳轉頁面。
- `MatchRecordDetailResponse` 目前已經是四個既有端點（團對戰紀錄、會員個人跨團對戰紀錄、會員歷史戰績、好友檢視）唯一共用的回應形狀（`build_match_record_detail()`），本功能延續此既有慣例，新增欄位不需要對任何一個端點做特別處理或例外分支。
- 單打／雙打的判斷沿用既有 `shot-placement-picker.component.ts` 的 `isSinglesMatch()` 慣例（`team_a`/`team_b` 參賽人數合計 ≤ 2 視為單打），不新增 `match_mode` 欄位到回應中——`MatchRecordDetailResponse` 既有的 `team_a`/`team_b` 名單長度已足以推導。
- 球員得失分統計的「球員」範圍為該場比賽 `team_a`/`team_b` 名單中的實際參賽者（既有 `MatchParticipant`/`ParticipantSummary` 資料），不包含中途被替換下場、未實際出現在該場 `MatchParticipant` 名單中的球員。
- 抽出的共用唯讀球場示意圖元件（`core/court-diagram/`）與既有 `features/shot-placement/shot-placement-picker` 元件的關係為「後者的 `.court` 內容改用前者」，屬於既有元件的內部重構，不改變 `shot-placement-picker` 對外的 `input`/`output` 合約，不影響 031/032 既有計分互動流程與其既有測試涵蓋範圍以外的行為。
