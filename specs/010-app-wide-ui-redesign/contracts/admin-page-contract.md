# UI Contract: Admin Page Tab Shell (US3)

**Feature**: [../spec.md](../spec.md) | **Data model**: [../data-model.md](../data-model.md)

## Behavioral contract

| # | Given | Then |
|---|-------|------|
| 1 | Admin page loads | Left nav shows exactly 6 items: 場地, 賽程, 輪替名單, 團名, 管理權限資訊, 管理員設定. `AdminSection` defaults to `'courts'`. |
| 2 | User clicks a left-nav item | The right content area switches to that section's existing markup (moved as-is from today's single-scroll template); no HTTP request is made by the click itself — all section data is already loaded on initial page load, exactly as today. |
| 3 | `view.read_only` is `true` (group disbanded) | Left nav still renders all 6 items; each section's content renders in its existing read-only form (unchanged from today's `@if (!view.read_only)` gating, now scoped per-section instead of one page-wide flag). |
| 4 | Viewport width `< 768px` | Left nav collapses to a horizontally-scrollable tab strip or an expandable menu (per Constitution VII / 008 tokens — exact mechanism decided at implementation time, must meet the 44×44px touch target minimum either way). |
| 5 | Viewport width `>= 768px` | Left nav renders as a persistent vertical sidebar alongside the content area. |
| 6 | Any dialog-triggering action (解散, 重新產生 PIN 碼, 重新產生連結, 踢除成員, Next Round) is invoked from its new section | Behavior is byte-for-byte identical to today — same `<app-confirm-dialog>` instances, same service calls, same error handling. Only the container they render inside has moved. |

## Non-goals

- No new route per tab (research.md Decision 2) — `AdminSection` is a
  client-side signal, never reflected in the URL.
- No new admin capability is added or removed by this contract — it is a
  pure container refactor of `AdminPageComponent`'s existing template.
