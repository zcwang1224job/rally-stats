# Quickstart: 全站介面重新設計

**Feature**: [spec.md](./spec.md) | **Plan**: [plan.md](./plan.md)

Assumes the local dev stack is running (`docker compose up -d --build` from
`infra/`, per `docs/local-development.md`) and the DB migrations are at
head (`docker exec infra-backend-1 alembic upgrade head`).

## Scenario 1 — Scoreboard (US1)

1. Create a group, start a doubles match on one court.
2. Open that court's scoreboard link. Confirm: dark background, two large
   colored score panels, each showing that team's two participant
   nicknames.
3. From the control panel, score a point. Confirm the scoreboard updates
   within ~1s (existing real-time behavior, unaffected by the redesign).
4. Confirm a scheduled next match shows a "即將登場" badge with the correct
   names; confirm it disappears once that match starts.

## Scenario 2 — Control Panel (US2)

1. With 2+ courts active, open the all-courts control panel link. Confirm
   every active court's block is visible on one page, no tab-switching
   needed.
2. On any court block, confirm score is centered with `+1`/`-1` for the
   left team to its left and the right team's to its right, and "提前結束"
   below.
3. Confirm there is **no** "下一場" button anywhere on this screen
   (research.md Decision 3 — deliberately excluded).

## Scenario 3 — Admin Page Tab Shell (US3)

1. Open a group's admin page. Confirm a left nav with 6 items (場地/賽程/
   輪替名單/團名/管理權限資訊/管理員設定), defaulting to 場地.
2. Click each item; confirm the right content switches without a full page
   reload, and every existing action (新增場地, Next Round, 重新產生 PIN
   碼, 解散, etc.) still works exactly as before from its new location.
3. Disband the group, reload the admin page. Confirm the tab shell still
   renders, now showing each section's existing read-only content.
4. At a mobile viewport width, confirm the left nav collapses per FR-008
   and every remaining interactive element still meets the 44×44px touch
   target minimum.

## Scenario 4 — Home Page Icon Nav (US4)

1. Open `/` as a guest. Confirm the top nav is icon-based (嘎團/開團/登入),
   not the plain text links from before this feature.
2. Log in; reload `/`. Confirm the icon nav's login slot switches to the
   member entry, consistent with 009's existing login-state behavior.

## Scenario 5 — Join Flow (US5)

1. Open `/groups`. Confirm cards show 團名/創建者/人數/比賽模式/場地/活動
   時間, and that pagination controls appear when there's more than one
   page of results.
2. Click "加入" on a password-protected group. Confirm a centered modal
   (not a full page) asks for the password; enter it wrong once, confirm
   the error shows inside the modal without closing it.
3. As a guest, continue past the password. Confirm a centered nickname
   modal appears next. As a logged-in member, confirm this step is skipped
   entirely and a confirm-only modal appears instead.

## Scenario 6 — Member Pages (US6)

1. Open `/auth/register`, `/auth/login`, `/auth/forgot-password`. Confirm
   each renders as a centered card, not an edge-to-edge plain form.
2. Log in as a member with no nickname set yet. Confirm the first-login
   nickname prompt is also a centered card.
3. Open the member home page. Confirm it lists 對戰紀錄/好友/我的團/個人設定
   as menu rows, plus a 登出 action.

## Scenario 7 — Friends & My Groups (US7)

1. With two verified member accounts (A, B): log in as A, go to
   `/friends/add`, search B's `user_number`. Confirm the four-state button/
   label logic (per `contracts/friends-frontend-contract.md` row 1-3).
2. Send the request as A. Log in as B, open `/friends/requests`. Confirm
   A's request appears; click 接受.
3. Confirm both A's and B's `/friends` list now show each other, with
   working nickname/user-number filtering.
4. As A, open `/friends`, click 解除好友 on B, confirm the two-step dialog,
   confirm. Confirm B's list no longer shows A (reload B's `/friends` to
   check) and B received no notification of any kind.
5. As a member who created a group earlier, open `/member/my-groups`.
   Confirm it lists that group (even if since disbanded). Click 忘記管理
   PIN 碼, confirm the two-step dialog, confirm. Confirm you land directly
   on that group's admin page with no further PIN entry, and that the old
   PIN/token no longer works if you had it saved elsewhere.

## Automated checks

```bash
cd apps/api && source .venv/bin/activate && ruff check . && mypy . && pytest
cd apps/web && npm test && npm run lint && npx tsc --noEmit
```
