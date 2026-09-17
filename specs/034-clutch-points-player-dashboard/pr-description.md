## 034 — 關鍵分表現與跨場個人技術儀表板

Spec / plan / tasks: `specs/034-clutch-points-player-dashboard/`

### What it adds

**1. 單場「關鍵分表現」**（US1）— a fifth derived block in the match detail dialog, right after 比分走勢摘要: endgame (from target − 3), deuce, match points held / converted / saved, win rate when leading / tied / trailing, and the comeback line. Applies to every existing entry point of the dialog.

**2. 跨場「個人技術儀表板」**（US2–US5）— on 會員對戰紀錄 and on a friend's records page:
- 18 metrics, each labelled 「依據 N 場／共 M 場」, following the page's filters;
- past 10 matches: 最近 10 場 vs. 全部, with a verdict decided on the backend so that "lower is better" metrics (e.g. 輸球時平均分差) read as progress when they shrink;
- a five-match moving-window trend per metric;
- a cross-match landing distribution, turned so the member's own side is always on the left.

No new table, column, index, migration, dependency, permission or write path. Everything is derived at view time.

### How it is put together

- `group/match_stats.py` gains `clutch_stats()`; `_wins()` restates the write path's win rule and a grid test pins it to `schedule.service.match_wins()`.
- `member/player_dashboard.py` (new, pure): `build_sample()` turns one match into the owner's point of view, `aggregate()` sums numerator/denominator pairs — a rate is always Σwon ÷ Σplayed, never a mean of percentages.
- The match detail and the dashboard go through **the same converters and the same pure functions**, so a match contributes exactly what its own dialog shows (tested: single-match dashboard vs. that match's detail response).
- `_filtered_member_matches()` is extracted from `build_member_match_records()` (signature and response unchanged; its existing tests pass with no assertion edited), so the list and the dashboard are computed over the same matches.
- Point logs load in three `IN` queries regardless of match count (asserted in tests).

### Authorization boundary (constitution IV — please check this part)

- **Both new endpoints use `require_verified_member`.** The constitution says match records MUST stay locked until the e-mail is verified. This is *deliberately stricter* than the existing `GET /members/me/match-records`, which uses `require_member` — a pre-existing deviation that this PR neither copies nor fixes (it deserves its own change).
- `GET /members/{member_id}/match-dashboard` goes through the **same** `_resolve_viewable_member()` as the friend's match records: same check order (`SELF_VIEW_NOT_SUPPORTED` → `MEMBER_NOT_FOUND` → `FRIENDSHIP_REQUIRED` → `MATCH_RECORDS_PRIVATE`), re-checked on every request, never cached, and the viewed member is not notified. Contract tests assert the four rejections match the match-records endpoint code for code, and that turning sharing off takes effect on the next request.
- The dashboard response carries numbers and coordinates only — **no nickname or any other member's identifier** — so it discloses less than the record list it sits next to. No new privacy setting: 023 already settled that the record list and aggregate stats share one switch.
- No write path, no realtime publish; the server stays the single source of truth (constitution X) — including for "is this progress", which the frontend never decides.

### Found along the way

- **Spec correction:** a `completed` match can only end on a converted match point — anything cut short becomes `abandoned` (constitution III) — so the "completed but no match point" state in the first draft of the spec does not exist.
- **Doc correction while writing tests:** nobody reaches 20:20 without one side having held a match point at 20:19, so quickstart scenario 1 expects 3 held / 3 saved, not 2.
- `/speckit-analyze` caught that the plan had marked constitution IV as PASS while copying the looser dependency; fixed before implementation (see plan.md).

### Verification

- Backend: `ruff` and `mypy` clean; full `pytest` — **1264 passed, 0 failed** (25 min).
- Frontend: `ng lint` and `tsc --noEmit` clean; full `ng test` — **49 files / 517 tests pass**. The one "unhandled error" (`NG04002 … 'groups/reauth'` from `admin-page.component.spec.ts`) predates this branch.
- Performance (SC-007), 300 matches with full point logs: dashboard **241 ms** (target < 3 s); `match-records` 16.4 ms before → 16.9 ms after (**+2.9%**, and a byte-identical response); a 46-point match detail **7 ms** (target < 2 s). Details under quickstart.md scenario 12.
- Driven end to end in headless Chrome at 1100×900 and 390×844 (login → match history → trend → match detail): no page errors, no horizontal overflow. Three layout fixes came out of looking at it (trend width cap, two card columns on phones, no-wrap table headers).
- `apps/api/scripts/seed_dashboard_demo.py` reproduces the demo/perf data; it refuses any database other than `rally_stats_test`.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
