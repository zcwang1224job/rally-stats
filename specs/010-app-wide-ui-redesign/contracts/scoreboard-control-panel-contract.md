# UI Contract: Scoreboard & Control Panel Redesign (US1, US2)

**Feature**: [../spec.md](../spec.md)

## Scoreboard (US1)

| # | Given | Then |
|---|-------|------|
| 1 | A match is in progress | Background is dark (`--scoreboard-bg`); left panel (team A, `--scoreboard-team-a-bg`) and right panel (team B, `--scoreboard-team-b-bg`) each show that team's current score in a very large font size. |
| 2 | Doubles match | Each panel additionally shows that team's two participant nicknames (stacked), in the panel's accent color. |
| 3 | Singles match | Each panel shows one nickname. |
| 4 | `state.next_up` is present | A "即將登場" badge with the next match's participant nicknames renders in a corner of the screen (reuses the existing `next-up status-badge` element already produced by current markup — this contract changes its position/styling only, not its data source). |
| 5 | `state.next_up` is absent | No such badge renders. |
| 6 | `connectionState() !== 'connected'` | The existing offline banner (`common.offlineBanner`, `status-badge--danger`) still renders — unaffected by the dark theme (must remain legible against the dark background; non-color-only status indicator rule, Constitution VII, still applies). |
| 7 | No match has ever been scheduled to this court yet | Panels show a `0`/`0` default and a waiting message; no nickname rows render (edge case, spec.md). |

## Control Panel — single and all-courts (US2)

| # | Given | Then |
|---|-------|------|
| 1 | A court has a match in progress | That court's block centers the score, with team A's `+1`/`-1` to its left and team B's `+1`/`-1` to its right; "提前結束" renders below the score. |
| 2 | All-courts control panel, 2+ courts active | Each court's block (as row 1 above) stacks vertically on one page; no pagination or tab-switching between courts. |
| 3 | A court's match ends (score reaches target) | That court's block updates to its waiting/next-up state, matching current behavior — unaffected by this layout change. |
| 4 | — | **No "下一場" (next-match) button is added to the control panel** — see research.md Decision 3. This is a deliberate exclusion, not a gap: the mockup's per-court "下一場" button would expose a Constitution-IV-restricted admin-only capability (Next Round) on an unauthenticated screen. |

## Non-goals

- No change to the underlying live-state polling/Ably subscription
  mechanism for either screen — this is a pure template/CSS redesign of
  already-working real-time components.
- No new backend fields — `next_up`, `score_a`/`score_b`, participant
  nicknames are all already returned by the existing court-state endpoints.
