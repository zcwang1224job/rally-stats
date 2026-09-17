# Specification Quality Checklist: 得分方式紀錄（主動得分 vs. 對手失誤）

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-18
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

- Validation iteration 1 (2026-09-18): all items pass.
- 「No implementation details」：spec 以功能編號（016/023/024/031～034）指稱既有資料、畫面與規則，未提及資料表、欄位、框架或端點。
- 寫 spec 前對既有程式的查證結果（供 `/speckit-plan` 直接沿用，不必重查）：
  - 詳細計分的操作是「按 + 立即加分 → 開啟共用的落點／球員選擇畫面補記細節 → 確認」，加分本身從不等待這個畫面；落點、得分球員、失分球員三者皆選填，唯一會擋住確認的是「落點與已判給的得分方矛盾」。→ 得分方式同樣選填（FR-005）、可單獨記錄（FR-010）。
  - 同一個選擇畫面由計分板、單一場地控制板、全部場地控制板三處共用（`/speckit-plan` 查證後更正：管理頁的場地控制並未掛載它；後端另有一支 admin 版端點共用同一個 request，會一併得到新欄位）。→ FR-013。
  - 選擇畫面**已經**依官方規則判定落點：界內／界外（單打用較窄的邊線）、落在哪一方半場、以及「落在得分方自己半場的發球失誤區、且得分方當時是接發球方」＝發球失誤。→ 界外與發球失誤可自動帶入（FR-006），這是「最多多點一下」（FR-008、SC-001）做得到的原因。
  - 既有判定的語意是「界內落在哪一方半場，就是那一方沒接到」——它分不出「被打死」與「自己掛網、球掉在自己這側」。→ 這一種落點不自動帶入（FR-007、SC-006），也是舊比賽不能回填的原因（FR-025）。
  - `-1` 修正會收回該隊最近一筆附帶紀錄；附帶紀錄除此之外不可變。→ FR-012。
  - 034 的儀表板以「每場 (分子, 分母) 貢獻」統一計算所有指標，新增指標不需要新的彙總規則。→ FR-019。
  - 個人得分／失分已分別歸屬得分球員與失分球員（032）。→ FR-003 的歸屬方式直接沿用，且能把既有的「失分」拆成「被打死」與「自己失誤」——這是目前畫面上完全看不到的區別。
- 無 [NEEDS CLARIFICATION]：以下皆採合理預設並記錄於 Assumptions——不要求計分員判斷受迫／非受迫（畫面用語為「失誤」）、得分方式固定五種、「主動得分」採寬鬆定義、只在無歧義時自動帶入、舊比賽不回填、確認後不可編輯。若對這些預設有異議，可用 `/speckit-clarify` 調整。
- **最值得你確認的一項預設**：你的原始描述用的是「非受迫性失誤」，規格改為只記錄客觀可見的「失誤」（出界／掛網／發球失誤／其他），不要求計分員判斷是否受迫。理由見 Assumptions 第一條。
- Validation iteration 2 (2026-09-18，`/speckit-plan` 之後)：all items still pass。設計期間對規格的兩處修正——FR-013 的入口由四個更正為三個；FR-009 明訂「新落點使親手選擇自相矛盾時清除」的例外，並新增 FR-009a（選項隨落點收斂）。
- 建議實作順序：US1 → US2 → US3（US2、US3 的所有數字都來自 US1；US3 的單場貢獻值來自 US2）。
