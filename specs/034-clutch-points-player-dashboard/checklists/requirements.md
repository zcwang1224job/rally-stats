# Specification Quality Checklist: 關鍵分表現與跨場個人技術儀表板

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-17
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Notes

- Validation iteration 1 (2026-09-17): all items pass.
- 「No implementation details」：spec 以功能編號（014/016/023/024/028/030～033）指稱既有資料、畫面與權限規則，未提及資料表、欄位、框架或端點名稱。Key Entities 提到「座標以比賽中兩隊的固定方向記錄」屬於既有資料的**業務語意**（決定 FR-031 為何必須統一視角），不是實作方式，刻意保留。
- 寫 spec 前對既有程式的查證結果（供 `/speckit-plan` 直接沿用，不必重查）：
  - 每場比賽為單局制，建立當下快照目標分／平分門檻／封頂分（預設 21／20／30，團可自訂，目標分下限為 1）；勝負判定只用目標分與封頂分（達封頂，或達目標且領先 2 分），平分門檻不參與 → Assumptions「比賽為單局制」、FR-011/FR-012 的定義、Edge Case「目標分過低」與「不同賽制混合彙總」。
  - 落點座標以 A 隊底線＝0、B 隊底線＝1 的絕對方向儲存 → 同一位會員在 A 隊與 B 隊的場次方向相反，跨場疊圖前必須統一視角 → FR-031、SC-006。
  - 個人對戰紀錄頁既有的彙總（勝敗、勝率走勢、對手戰績）皆對「整個篩選結果」計算而非當頁，且只含以會員身分參與的比賽（訪客場次經 028 綁定後才歸屬）→ FR-018/FR-019、US2 情境 7。
  - 033 已有純函式的單場推導（有效得分重新累計、發球歸屬與排除規則、最大領先）→ FR-002/FR-003/FR-014/FR-023 要求沿用同一套規則，不得出現第二套算法。
  - 023 已定案戰績明細與彙總統計由同一項隱私設定共同控管、不可分開授權，且好友檢視不通知 → US5、FR-035/FR-036。
  - 比賽詳情為單一共用對話框（四個入口），目前已有七個預設收合的區塊 → FR-009、Edge Case「畫面長度」。
- 無 [NEEDS CLARIFICATION]：以下皆採合理預設並記錄於 Assumptions——局末階段取「目標分 − 3」且目標分低於 11 分不適用、「最近 N 場」固定 10 場（對比最低樣本 3 場、趨勢平滑區間 5 場）、關鍵分以隊伍為單位、儀表板首版不放進 014 的單一團歷史戰績頁、好友可見範圍沿用 023 不新增隱私開關。若對這些預設有異議，可用 `/speckit-clarify` 調整。
- 建議實作順序：US1 → US2 → US3 → US4 → US5（US2 的關鍵分指標依賴 US1 的定義；US3～US5 皆建立在 US2 之上）。
