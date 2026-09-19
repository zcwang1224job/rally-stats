# Specification Quality Checklist: 休息／準備切換

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-19
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

- 第一輪檢查：SC-005 原寫「空等超過一次叫場的時間」無法客觀驗證，已改為「排隊中還有場次且有可用替補時，場地空出後 100% 能立即叫出下一場」。
- 「誰可以切換」「休息是否自動結束」「已排定場次的處理」「是否補償」四項已於 2026-09-19 由使用者確認，記錄於 spec 的 Clarifications。
- 有一項由規格撰寫時自行決定、尚待使用者過目：FR-020（自動進入下一輪遇到「只剩因休息而保留的場次」時，視為該輪結束）。理由與代價寫在 Assumptions；若使用者偏好「等他回來」，只需改 FR-020／US2 情境 9／SC-006。
- 規格提及的排程方式名稱（公平輪替、個人全混搭循環賽、固定搭檔循環賽、手動安排、「場地一空就排下一場」、自動進入下一輪）皆為畫面上既有的使用者用語，不屬於實作細節。
