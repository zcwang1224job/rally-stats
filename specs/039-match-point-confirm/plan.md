# Implementation Plan: 決勝分二次確認

**Branch**: `feature/match-point-confirm` | **Date**: 2026-09-20 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/039-match-point-confirm/spec.md`

## Summary

簡易模式（未啟用比賽詳細設定）的決勝分是整個計分流程中唯一「一按定生死、且完全沒有提示」的操作——比賽一結束，連「-1」都會靜默失效，而那一分寫下的是計入戰績的永久紀錄。本功能替它補上二次確認，四個計分畫面一致。

技術上分三塊。**後端**把每場比賽的 `target_score` 與 `cap_score` 送進兩個 live state schema（各一個建構點，共兩行），前端才有辦法判斷「下一分會不會贏」。**判定邏輯**抽成 `core/match-point.ts` 一支純函式，對應後端的 `match_wins()`；最大的陷阱是 `deuce_threshold` **不參與**判定，20:20 加一分只到 21:20 不算贏、不該跳確認。**四個元件**各自把「+」的兩路分支改成三路，並掛上一個確認框。

需要留意的是兩個都會造成「靜默卡死」的坑，都在 research.md 有完整記錄：`ConfirmDialogComponent` 目前**沒有任何取消或關閉的 output**，而 `<dialog>` 的 Esc 關閉根本不經過元件的 `cancel()`；以及 `ScoreTapGuard` 一旦在開啟確認框前取得就沒有解鎖時機。前者靠新增一個綁在原生 `close` 事件的 `closed` output 解決，後者靠「確認流程完全不碰 guard」解決。

## Technical Context

**Language/Version**: TypeScript 5.9（前端）、Python 3.12（後端）

**Primary Dependencies**: Angular 20.3（standalone components + signals）、`@ngx-translate/core` 18、Ably 2.28、RxJS 7.8；FastAPI + Pydantic v2 + SQLAlchemy（async）

**Storage**: PostgreSQL。**本功能無資料庫變更、無 Alembic migration。**

**Testing**: 前端 Vitest（`ng test`）；後端 pytest（contract / integration / unit）

**Target Platform**: 響應式網頁，主要使用情境是球場邊的手機瀏覽器

**Project Type**: Web application（`apps/web` Angular SPA + `apps/api` FastAPI）

**Performance Goals**: 確認框必須在同一次按壓內出現；非決勝分的計分路徑完全不受影響（SC-002）

**Constraints**:
- 判定 MUST 與後端 `match_wins()` 一致，且 MUST NOT 使用 `deuce_threshold`
- 取消（含 Esc）後 MUST 能立即繼續計分——不得殘留狀態或鎖
- 四個畫面的判定條件、文案與行為 MUST 一致
- 0 個新端點、0 個新錯誤碼、0 個 migration；**新增 4 個語系 key**

**Scale/Scope**: 後端 2 個 schema 各 +2 欄位、2 個建構點各 +2 行；前端 1 支新純函式、1 個共用元件加 1 個 output、4 個計分元件各加一段三路分支與一個確認框。無 NEEDS CLARIFICATION。

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

逐條對照憲章 v1.0.0 核心原則 I–XI：

| 原則 | 是否觸及 | 如何符合 |
|---|---|---|
| **I. 程式碼品質與型別安全** | ✅ 觸及 | 新欄位前後端型別同步宣告；判定函式簽章明確、無 `any`。合併前跑 `npm run lint`、`tsc --noEmit`、`ruff`、`mypy`。 |
| **II. 測試優先** | ✅ 觸及（比分計算相關） | `core/match-point.spec.ts` 以 data-model.md 的邊界對照表逐列驗證（含 deuce 與 cap）；四個元件各驗三路分支；後端補契約測試。 |
| **III. 即時性與資料一致性** | ✅ **重點觸及** | (a) **快照**：判定讀 `matches.target_score` / `cap_score`，不讀團當下設定；契約測試鎖住「中途改團設定不影響進行中比賽」。(b) **不送會過期的衍生值**：刻意不送伺服器算好的布林值，因為 038 的凍結與各畫面的就地 patch 會讓它失準（research.md Decision 5）。(c) 確認框不快取任何比分，純粹讀當下顯示狀態。 |
| **IV. 權限與安全** | ➖ 幾乎不觸及 | 不新增端點、不改權限模型。本功能只是在既有計分權限之上多一道確認，四個畫面各自沿用原本的驗證路徑（token 或管理員 PIN session）。 |
| **V. UX 二次確認** | ✅ **本功能即是此原則的落實** | 憲章明定「所有具破壞性或不可逆影響的互動元件 MUST 提供明確的二次確認流程」。決勝分會產生計入戰績的永久紀錄且無法從 UI 復原，正是此原則的適用對象——本功能補上的就是這個長期缺口。沿用既有 `ConfirmDialogComponent`，`variant` 取 `primary`（紅色保留給破壞性操作，與「提前結束」一致）。 |
| **VI. 可維護性** | ✅ 觸及 | 判定邏輯集中在一支純函式，四個元件共用，不各寫一份；三路分支移進 TypeScript，模板反而比現在更乾淨（research.md Decision 6）。對共用 `ConfirmDialogComponent` 的擴充是純新增，不改既有行為。 |
| **VII. 無障礙與行動優先** | ✅ 觸及 | 沿用既有確認框的樣式與無障礙處理（原生 `<dialog>` + `showModal()`，焦點管理與 Esc 由瀏覽器負責）。**Esc 關閉必須正常運作**是本功能明列的驗收項（quickstart 情境 7）。 |
| **VIII. i18n** | ✅ 觸及 | **新增 4 個 key**（`matchPointConfirmTitle` / `matchPointConfirmBody`，zh-TW + en）。刻意與既有 `endMatchConfirmBody` 同句型、相反結論，讓兩種「結束比賽」的差別一眼可辨。無硬寫文字，後端不新增錯誤碼。 |
| **IX. 可攜性與可部署性** | ➖ 不觸及 | 無新環境變數、無新密鑰、無 migration。 |
| **X. 伺服器為唯一可信來源** | ✅ 觸及 | 前端的決勝分判定**只決定要不要先問一句**，不參與任何實際判定；比賽是否結束、是否產生比賽結果，一律由伺服器收到該分後決定（FR-013）。前端判斷錯誤最多是多問或少問一次，不會造成狀態不一致。 |
| **XI. 防機器人/防濫用** | ➖ 不觸及 | 不涉及公開的建立資源端點。 |

**Gate 結果**：全數通過，無偏離。Complexity Tracking 表為空。

**Post-Design re-check（Phase 1 後）**：data-model.md 與 contracts/ 完成後重新對照——設計確認為「零資料庫變更、零新端點、兩個 schema 各加兩個靜態整數欄位、一支純函式、一個共用元件的純新增 output」。唯一新增的複雜度是四個元件各有一段相似的繫結，已在 research.md 風險註 4 說明為何本次不做共用抽象。上表結論不變，仍無需 Complexity Tracking 條目。

## Project Structure

### Documentation (this feature)

```text
specs/039-match-point-confirm/
├── plan.md              # This file (/speckit-plan output)
├── spec.md              # /speckit-specify output
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/
│   └── live-state-additions.md   # Phase 1 output
├── checklists/
│   └── requirements.md  # /speckit-specify output
└── tasks.md             # Phase 2 output (/speckit-tasks — NOT created here)
```

### Source Code (repository root)

```text
apps/api/
├── app/domains/schedule/
│   ├── schemas.py        # MatchSummary += target_score, cap_score
│   │                     # MatchLiveDetail += target_score, cap_score
│   └── service.py        # build_schedule_snapshot() ~L2064  → 填值
│                         # MatchLiveDetail 建構點  ~L3907    → 填值
└── tests/contract/       # 兩個 schema 的新欄位 + 快照不回溯

apps/web/src/app/
├── core/
│   ├── match-point.ts            # 新增：isMatchPoint() 純函式
│   └── match-point.spec.ts       # 新增：邊界（deuce / cap / 雙方同時）
├── features/group-admin/shared/
│   └── confirm-dialog.component.ts   # += closed output（綁原生 close 事件）
├── features/control-panel/
│   ├── control-panel.component.{ts,html,spec.ts}
│   └── all-courts/all-courts-court-block.component.{ts,html,spec.ts}
├── features/scoreboard/
│   └── scoreboard.component.{ts,html,spec.ts}
├── features/group-admin/schedule-management/
│   ├── court-control.component.{ts,html,spec.ts}
│   └── schedule.models.ts        # MatchSummary += target_score?, cap_score?
├── core/api/
│   └── court-live-state.models.ts # MatchLiveDetail += target_score?, cap_score?
└── assets/i18n/
    ├── zh-TW.json                # += matchPointConfirmTitle / Body
    └── en.json                   # 同上
```

**Structure Decision**：沿用既有 `apps/api` + `apps/web` 雙專案結構，不新增目錄或模組。判定邏輯放在 `apps/web/src/app/core/`，與 `waiting-reason-label.ts`、`benchmark-group-preference.ts` 等既有純函式同址、同樣配一支 `.spec.ts`。共用的 `ConfirmDialogComponent` 雖然位於 `features/group-admin/shared/`，但全專案 14 處都在用它（包含三個非管理頁畫面），本功能沿用現況不搬家——搬移它會牽動 14 個 import，與本功能無關。

## 實作順序建議（供 `/speckit-tasks` 參照）

1. **後端欄位**：兩個 schema + 兩個建構點 + 契約測試。可獨立合併，對現行前端零影響。
2. **共用基礎**：`core/match-point.ts` 與其單元測試；`ConfirmDialogComponent` 的 `closed` output。兩者都是純新增，不改任何既有行為。
3. **前端型別**：兩個 models 檔各加兩個可選欄位。
4. **US1（P1）**：先在**一個**畫面（建議管理頁場地控制，因為 038 剛做過、最熟）完成三路分支 + 確認框 + 測試，把流程走通。
5. **US3（P3）**：把同一套複製到其餘三個畫面。
6. **US2（P2）**：其實由步驟 2 的純函式測試涵蓋大半；此階段補各畫面「不該跳的時候不跳」的元件測試。

> 註：US2（只在該出現時出現）與 US1 在實作上是同一段分支的一體兩面，無法真正分開實作；上面的順序反映的是**驗證**重心的推進，不是三次獨立開發。

## Complexity Tracking

> 無憲章偏離，本表為空。
