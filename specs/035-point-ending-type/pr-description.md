## 035 — 得分方式紀錄（主動得分 vs. 對手失誤）

Spec / plan / tasks: `specs/035-point-ending-type/`

### What it adds

**1. 計分時記下這一分怎麼結束的**（US1）— a fourth optional detail on the existing shot-placement picker: one row of five chips under the court (主動得分／對手出界／對手掛網／發球失誤／其他失誤). Where the landing leaves no doubt it is pre-selected — out of bounds → 對手出界, a serve-fault landing → 發球失誤 — so those points cost **zero** extra taps; an in-bounds landing on the loser's half is deliberately *not* read as a winner (it looks the same as a net shot dropping on the hitter's own side), so that one stays a single tap. A hand-pick survives re-tapping the landing unless the new landing contradicts it. Skipping is always allowed; `-1` withdraws it with the rest of the row; simple-scoring matches are untouched.

**2. 單場詳情**（US2）— a sixth derived block 「得分方式」 after 關鍵分表現: coverage (已記錄 N／共 M 分), each team's winners and errors committed (with the errors' make-up), and a per-player table splitting points scored into 主動得分／對手失誤／未記錄 and points lost into 被主動得分／自己失誤／未記錄 — each triple adds up to 032's existing 得分／造成失分 totals. The event list labels every recorded point with an icon + text (★ winner / ✕ error), never by colour alone.

**3. 儀表板**（US3）— a fourth metric group 「主動得分與失誤」 with five metrics (主動得分比例、每場主動得分、每場失誤、失誤佔失分比例、主動得分／失誤比; the two error ones are "lower is better"), plus my own errors by kind. 034's landing-only 「全部／最近 10 場」 buttons become **one** dashboard-level switch that drives both the landing map and the error breakdown. Ratio denominators only ever hold points whose ending was recorded — unrecorded points are never counted as either kind. Old matches are never back-filled: winners cannot be inferred, and filling in only the errors would skew every ratio.

### How it is put together

- **One nullable column** `shot_placement_records.ending_type` (migration `e7a41c9b3d52`). No new table, index, endpoint or permission.
- `attach_shot_placement()` stores exactly what arrives — the auto-fill lives in the picker — and refuses only the two self-contradicting combinations (a winner out of bounds, an out shot in bounds → `ENDING_TYPE_CONTRADICTS_LANDING`). The picker's own in/out judgement and the server's are pinned together by **the same boundary-vector table copied verbatim into both test suites** (a point they disagreed on would let the picker auto-fill a value the server then refuses, and the callers drop a failed request silently).
- `match_stats.ending_stats()` (pure) attributes a winner to the scorer and an error to the loser; where that player was not recorded the point still counts for its team. `player_dashboard.build_sample()` reads the member's own row of it — only when at least one of *their* points carries an ending — and the five metrics are five more `_MetricSpec` entries; `aggregate()`'s loop is unchanged.
- The dashboard reads the placements it already loads for the landings, so the query count is the same as 034 (asserted).
- `ENDING_TYPES` on the frontend and `EndingType` on the backend are held together by a contract test that sends every value in order; the pure module's copy of the Literal is pinned to the write-side one by a unit test.

### Migration and deployment order — please read

**Run `alembic upgrade head` before deploying the backend.** The container does not run migrations, and every read of `ShotPlacementRecord` now selects the new column. If the order is reversed, the failures are broad, not local: **every match detail dialog, the whole dashboard, and `-1` on any detailed-scoring match** all 500 until the column exists (`column shot_placement_records.ending_type does not exist`).

Rollback: the reverse order — **revert the backend first, then `alembic downgrade -1`**. Downgrading while the new backend is still running reproduces the same outage. The old backend ignores the column, so it can stay in place until the downgrade.

Local docker: `docker compose -f infra/docker-compose.yml exec backend alembic upgrade head` after switching the main checkout to this branch.

### Authorization boundary (constitution IV)

- **No new endpoint.** The ending type rides the three existing shot-placement endpoints (court token, admin, all-courts token) as one more optional field of the same request, guarded exactly as the landing and the players already are — it is not an admin-only action; the scorer holding the court link records it.
- The match detail and the dashboard responses gain fields only; their visibility, the friend checks and `require_verified_member` are untouched, and the new fields carry nothing but counts and nicknames already present elsewhere in the same response.

### Verification

- Backend: `ruff check app/ tests/` and `mypy app/` clean; full `pytest` — **1339 passed, 0 failed (16 min)**. One integration test (`test_court_creation_flow`, untouched by this branch) hit a transient `KeyError: 'admin_token'` on group creation and passed on re-run; the same flake struck an untouched contract test once earlier in the session.
- Frontend: `ng lint`, `tsc --noEmit` (app + spec) and a production build clean; full `ng test` — **50 files / 560 tests pass**. The bundle-budget warnings predate this branch.
- i18n: `zh-TW.json` and `en.json` have identical key sets (821 keys); every key the touched templates use resolves; no hardcoded copy.
- Headless Chrome (1100×900 and 390×844): a real scoring flow on the control panel at 390 px — 10 points, singles: **30 taps before / +6 with the ending**, exactly the six in-bounds points I chose to label; the three out-of-bounds points auto-filled 對手出界 for 0 taps and the skipped point stayed unrecorded; the confirm button stayed in view before and after every pick; no horizontal overflow, no page errors. Match detail block and dashboard checked at both widths (23 cards, one range switch, breakdown 39 → 26 net errors on switching to 最近 10 場). Three layout fixes came out of looking at it (hovered selected chip, table containment on phones, totals line wrapping).
- Performance (SC-010): 300-match dashboard **262 ms median** (target < 3 s); query count unchanged from 034 (asserted).
- Scoring pace (SC-002) needs a human with a stopwatch — quickstart scenario 10 is left for manual acceptance.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
