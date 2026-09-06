# Quickstart: 全站導覽規劃（行動裝置優先）

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

Validates this feature end-to-end once implemented. Assumes the local dev
stack is already running — see `docs/local-development.md` if not
(`docker compose up -d --build` from `infra/`, or the manual venv/Postgres
path documented there).

## Prerequisites

- Frontend running at `http://localhost:4200` (`npm start` in `apps/web`,
  or via the Docker frontend service).
- At least one registered, email-verified member account (any account
  created via `/auth/register` + the verification-link flow works).
- Browser DevTools responsive-mode, or a real phone/tablet, to check both
  breakpoints (< 768px and >= 768px).

## Scenario 1 — Guest navigation shell (US1, US2)

1. Open `http://localhost:4200/` in a mobile-width viewport (< 768px).
2. Confirm the nav shell shows a compact bar with a toggle; tap it.
3. Confirm the expanded panel shows: 首頁, 揪團列表, 登入, 註冊 — and
   nothing member-only (no暱稱, no 登出).
4. Confirm the home page body itself shows four entry points: 瀏覽揪團列表,
   建立揪團場次, 登入, 註冊.
5. Widen the viewport to >= 768px. Confirm the shell now shows the same
   links inline, with no toggle control.

## Scenario 2 — Member login/logout via the shell (US1)

1. From the guest home page, log in with a verified test account.
2. Confirm you land somewhere sensible (existing login redirect behavior is
   unchanged by this feature) and the nav shell now shows: 首頁, 揪團列表,
   your nickname or a 會員專區 entry, 設定, 對戰紀錄, 登出 — and no
   login/register links.
3. Revisit the home page (`/`). Confirm its guest-only CTA (login/register)
   is replaced by a single 前往會員專區 entry (US2 scenario 2).
4. Click 登出 from the shell. Confirm you land on the home or login page,
   and the shell immediately reflects the guest state again (no full page
   reload should be necessary, but a reload is acceptable if the
   implementation chose to navigate that way — the shell state itself must
   already be correct before or immediately after).
5. Count your taps from step 2 to step 4's logout click: must be <= 2 taps
   from any member-area page (SC-002).

## Scenario 3 — Member-area cross-navigation (US3)

1. Logged in, navigate to `/member/match-history`.
2. Using the nav shell (not the browser back button), switch directly to
   `/member/settings`. Confirm no detour through `/member` was required.
3. From `/member/settings`, log out directly (US3 scenario 2) — confirm
   this behaves identically to Scenario 2 step 4.

## Scenario 4 — Admin page return path (US4)

1. Create a group (or reuse one) and open its admin page
   (`/groups/:groupId/admin`) via its 組團編號 + 管理 PIN 碼.
2. Confirm the admin page shows a plain "返回首頁" link — and confirm the
   full nav shell (login/logout, etc.) is **not** present on this page
   (research.md Decision 6).
3. Click 返回首頁; confirm you land on `/`.
4. Re-open the same group's admin page again via its group number + PIN.
   Confirm the PIN is still required — the earlier "return to home" click
   must not have invalidated or bypassed it (spec.md Edge Cases, last
   bullet).

## Scenario 5 — Excluded pages stay chrome-free (edge cases, FR-009/FR-010)

1. Open a group's member-view page (`/groups/:groupId/member-view`) as a
   member or guest participant. Confirm only the existing 008-era bottom
   nav (賽程/戰績/對戰紀錄/退出組團) is present — no second, global nav
   shell appears above or below it.
2. Open a scoreboard link (`/scoreboard/:courtToken`) and a control-panel
   link (`/control/:courtToken`). Confirm neither shows any nav shell —
   the visible scoring/control area occupies the same space as before this
   feature (SC-004).

## Automated checks

```bash
cd apps/web
npm test               # Vitest — run nav-shell.component.spec.ts, home.component.spec.ts,
                        # admin-page.component.spec.ts, app.spec.ts alongside the rest of the suite
npm run lint
npx tsc --noEmit
```

No backend changes in this feature, so no API/pytest run is required.
