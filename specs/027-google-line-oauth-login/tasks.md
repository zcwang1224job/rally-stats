---
description: "Task list for 027-google-line-oauth-login"
---

# Tasks: 使用 Google／LINE 帳號註冊與登入

**Input**: Design documents from `/specs/027-google-line-oauth-login/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/oauth-login-api.md, contracts/account-recovery-api.md, quickstart.md

**Tests**: Included — this session's established convention (see specs/026) is tests alongside/before each implementation task, run to full-suite green before a task is considered done. Constitution II's Test-First mandate applies directly here: the OAuth callback's success/collision/cancel branches and the `member_oauth_identities` uniqueness constraints are exactly the kind of core-auth-logic/security-boundary code the principle targets.

**Organization**: Tasks are grouped by user story (US1/US2/US3, P1/P1/P2 per spec.md) in priority order. US1 (Google) builds the entire provider-agnostic OAuth machinery (it's generic by design, per plan.md's Constitution Check principle VI reasoning); US2 (LINE) reuses that machinery and adds only the LINE-specific config and no-email branch — same relationship as 026's US1→US2 dependency.

**Revision note** (/speckit-analyze 2026-09-14 remediation): this version renumbers every task from the pre-analyze draft to insert T015/T016/T017 (dedicated tests for FR-005 email-collision, FR-011 deleted-account rejection, and the FR-005/FR-006/FR-007 concurrent-duplicate race condition — findings E1/E2/E3) and to fold the C1 finding (FR-006's "second different account" case) into T032/T038's existing descriptions rather than adding a new task ID. No implementation has started, so renumbering carries no historical-record cost (unlike specs/026's post-implementation addendum approach).

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no unmet dependency)
- **[Story]**: US1, US2, or US3
- Paths are exact, relative to repo root

---

## Phase 1: Setup

**Purpose**: New dependency, new env vars, the one schema change everything else depends on.

- [X] T001 Add `authlib` to `apps/api/requirements.txt` dependencies (research.md #3; the actual dependency manifest — not pyproject.toml, corrected during implementation)
- [X] T002 [P] Add `google_oauth_client_id`/`google_oauth_client_secret`/`line_oauth_channel_id`/`line_oauth_channel_secret` settings to `apps/api/app/core/config.py` (`Settings`, plan.md Target Platform)
- [X] T003 Create an Alembic migration in `apps/api/alembic/versions/`: new `member_oauth_identities` table (data-model.md §2, with its two UNIQUE constraints), `members.email`/`members.password_hash` changed to `nullable=True`, `ux_members_email` recreated as a partial unique index `WHERE email IS NOT NULL` (data-model.md §1) (depends on T001)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Type/schema plumbing every story builds on. No behavior change yet.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T004 Add `MemberOAuthIdentity` ORM model to `apps/api/app/domains/member/models.py`; change `Member.email`/`Member.password_hash` to `Mapped[str | None]` (data-model.md §1/§2, depends on T003)
- [X] T005 [P] Create `apps/api/app/domains/member/oauth_providers.py`: `OAuthProviderConfig` dataclass (`authorize_url`/`token_url`/`jwks_url`/`client_id`/`client_secret`/`scopes`) + `GOOGLE`/`LINE` constants (research.md #3, depends on T002)
- [X] T006 [P] Add `issue_oauth_state()`/`decode_oauth_state()` to `apps/api/app/domains/member/security.py` — `typ: "oauth_state"`, reusing the existing `_issue_token()`/`_decode_token()` machinery (research.md #2)
- [X] T007 [P] Update `apps/api/app/domains/member/schemas.py`: `MemberPublicResponse.email` → `str | None`, add `linked_oauth_providers: list[Literal["google", "line"]]`; `ChangePasswordRequest.current_password`/`DeleteAccountRequest.current_password` → `str | None = None` (data-model.md §4, depends on T004)
- [X] T008 [P] Update `apps/web/src/app/core/api/member-auth.models.ts`: `email?: string | null`, add `linkedOauthProviders`, `currentPassword` becomes optional (data-model.md §4)

**Checkpoint**: Shapes exist; nothing yet reads or writes `member_oauth_identities` or the relaxed columns.

---

## Phase 3: User Story 1 - 使用 Google 帳號快速註冊/登入 (Priority: P1) 🎯 MVP

**Goal**: A first-time visitor clicks "使用 Google 繼續", authorizes with Google, and is immediately logged into a newly-created, already-verified account; a returning visitor is logged back into the same account. This phase builds the entire provider-agnostic OAuth handshake (start/callback/state/PKCE/id_token verification) — Google is simply the first provider exercised through it.

**Independent Test**: A visitor with no existing account clicks "使用 Google 繼續", completes Google's consent screen, and lands back in the app already logged in with a brand-new verified member account (no email-verification screen); clicking it again with the same Google account logs back into the same account rather than creating a second one; cancelling on Google's screen returns to the login page with nothing created.

### Tests for User Story 1

- [X] T009 [P] [US1] Unit tests for `member_oauth_identities`'s two UNIQUE constraints (FR-006/FR-007) in new file `apps/api/tests/unit/domains/member/test_member_oauth_identities.py`
- [X] T010 [P] [US1] Unit tests for `issue_oauth_state()`/`decode_oauth_state()` in new file `apps/api/tests/unit/domains/member/test_oauth_state.py`: round-trips `provider`/`intent`/`member_id`/`code_verifier`; rejects tampered signature, expired token, and a token with the wrong `typ`
- [X] T011 [P] [US1] Unit tests for `start_oauth_flow(provider="google", intent="login")` in new file `apps/api/tests/unit/domains/member/test_oauth_flow.py`: returned `authorize_url` contains `client_id`/`redirect_uri`/`scope`/`code_challenge`/`code_challenge_method=S256`/`state`; the `state` decodes back to the right `provider`/`intent`
- [X] T012 [P] [US1] Unit tests for `complete_oauth_callback()` intent=login/provider=google **new-member success path** (mocking the provider's token+JWKS HTTP calls via `authlib`'s test utilities or `httpx` mock transport): creates a `Member` with `verification_status="verified"`, `email` set from the id_token, no verification email sent (research.md #6); creates one `member_oauth_identities` row; returns a valid access/refresh token pair — extend `test_oauth_flow.py`
- [X] T013 [P] [US1] Unit tests for `complete_oauth_callback()` intent=login/provider=google **returning-member path** (FR-003): an existing `member_oauth_identities` row for this `(provider, sub)` logs into that member, no second `Member`/identity row created — extend `test_oauth_flow.py`
- [X] T014 [P] [US1] Unit tests for `complete_oauth_callback()` **cancel/deny path** (FR-010, `error=access_denied`) and **state-invalid path** (missing/tampered/expired `state`): no `Member`/identity row created either way — extend `test_oauth_flow.py`
- [X] T015 [P] [US1] Unit tests for `complete_oauth_callback()` intent=login **FR-005 email-collision path** (/speckit-analyze 2026-09-14 remediation, finding E1 — previously untested): the Google/LINE profile's email matches an existing member's email — (a) an existing Email／密碼 member, (b) an existing OAuth-only member with no password — both MUST return `OAUTH_EMAIL_ALREADY_REGISTERED`, create no new `Member`, create no new `member_oauth_identities` row, and issue no tokens; a LINE profile with no email at all MUST skip this check entirely (nothing to collide on, FR-004) — extend `test_oauth_flow.py`
- [X] T016 [P] [US1] Unit tests for `complete_oauth_callback()` intent=login **FR-011 deleted-account path** (/speckit-analyze 2026-09-14 remediation, finding E2 — previously untested): an existing `member_oauth_identities` row whose `Member.deleted_at IS NOT NULL` MUST return `ACCOUNT_DELETED` and issue no tokens, exactly like the existing Email/password `login()`'s deleted-account handling — extend `test_oauth_flow.py`
- [X] T017 [P] [US1] Unit test for `complete_oauth_callback()` **concurrent-duplicate race condition** (/speckit-analyze 2026-09-14 remediation, finding E3 — plan.md Constraints requires this, previously had no task at all): simulate two requests passing the FR-005 application-level collision check before either has committed (e.g. pre-insert a colliding row between the check and the write, or directly assert the service function catches an `IntegrityError` from the `member_oauth_identities` unique constraint) and confirm it's translated into the matching error code (`OAUTH_EMAIL_ALREADY_REGISTERED`/`OAUTH_IDENTITY_ALREADY_LINKED`/`OAUTH_PROVIDER_ALREADY_LINKED`) rather than propagating as an unhandled exception — new assertions in `test_oauth_flow.py`
- [X] T018 [P] [US1] Contract tests for `GET /auth/oauth/google/start` and `GET /auth/oauth/google/callback` in new file `apps/api/tests/contract/test_oauth_login.py`, covering **every** row of contracts/oauth-login-api.md's callback table for `intent=login` (success/cancelled/`OAUTH_STATE_INVALID`/`OAUTH_PROVIDER_ERROR`/`ACCOUNT_DELETED`/`OAUTH_EMAIL_ALREADY_REGISTERED`) — /speckit-analyze 2026-09-14 remediation, finding E1: the pre-analyze draft of this task named only 4 of the 6 `intent=login` branches, silently dropping `ACCOUNT_DELETED` and `OAUTH_EMAIL_ALREADY_REGISTERED`
- [X] T019 [P] [US1] Frontend tests: login page renders "使用 Google 繼續"/"使用 LINE 繼續" buttons; clicking one calls `GET /auth/oauth/{provider}/start` and sets `window.location.href` to the returned `authorize_url` — `apps/web/src/app/features/auth/login/login.component.spec.ts`
- [X] T020 [P] [US1] Frontend tests for the new `oauth-callback.component`: `status=success` calls `AuthService.setTokens()` and navigates to the existing post-login destination (`is_new_member=true` → existing nickname-setup flow, FR-012); `status=cancelled`/`status=error` navigates to the login page with the right i18n message; hash is cleared via `history.replaceState` after reading — new file `apps/web/src/app/features/auth/oauth-callback/oauth-callback.component.spec.ts`

### Implementation for User Story 1

- [X] T021 [US1] Implement `start_oauth_flow(session, provider, intent, member_id=None)` in `apps/api/app/domains/member/service.py`: generates PKCE verifier/challenge, builds `state` via T006, builds the provider's authorize URL from T005's config (depends on T011, T005, T006)
- [X] T022 [US1] Implement `complete_oauth_callback(session, provider, code, state, error)` in `apps/api/app/domains/member/service.py`: decodes/validates `state`; on `error` redirects per FR-010; exchanges `code` via `httpx` at the provider's token endpoint; verifies the returned `id_token` via `authlib` against the provider's JWKS (`iss`/`aud`/`exp`/`nonce`); looks up `member_oauth_identities` by `(provider, sub)`; intent=login branch: existing → check `Member.deleted_at` (FR-011, `ACCOUNT_DELETED` if set) else login and issue tokens; not found → FR-005 collision check against **any** existing member's email (data-model.md §1, skipped when the profile has no email) then create a new `Member`(`verification_status="verified"`) + identity row and issue tokens; the whole write path MUST catch `IntegrityError` from the two `member_oauth_identities` unique constraints and translate it into the matching error code rather than letting it propagate (E3, contracts/oauth-login-api.md「併發防護」) (depends on T012, T013, T014, T015, T016, T017, T005, T006, T004)
- [X] T023 [US1] Add `GET /auth/oauth/{provider}/start` and `GET /auth/oauth/{provider}/callback` to `apps/api/app/domains/member/router.py`, both rate-limited `20/minute`; `callback` returns a `RedirectResponse` per contracts/oauth-login-api.md's table (depends on T021, T022, T018)
- [X] T024 [P] [US1] Add "使用 Google 繼續"/"使用 LINE 繼續" buttons to `apps/web/src/app/features/auth/login/login.component.html`/`.ts`: call `GET /auth/oauth/{provider}/start?intent=login`, then `window.location.href = authorize_url` (depends on T019)
- [X] T025 [P] [US1] Create `oauth-callback.component` (`.ts`/`.html`/`.spec.ts`) in `apps/web/src/app/features/auth/oauth-callback/`, registered as a route in `apps/web/src/app/app.routes.ts` at path `auth/oauth-callback` (/speckit-analyze 2026-09-14 remediation, finding L1 — routes file was previously unnamed); reads `location.hash`, calls existing `AuthService.setTokens()`, navigates per contracts/oauth-login-api.md's frontend-behavior section (depends on T020)
- [X] T026 [P] [US1] Add i18n keys to `apps/web/src/assets/i18n/zh-TW.json` and `en.json`: `auth.continueWithGoogle`/`auth.continueWithLine`, and the callback page's status/error keys for every code the callback can return under `intent=login` — `status=cancelled`, `OAUTH_STATE_INVALID`, `OAUTH_PROVIDER_ERROR`, `ACCOUNT_DELETED`, `OAUTH_EMAIL_ALREADY_REGISTERED` (the last two named explicitly per finding E1 — easy to silently drop otherwise)

**Checkpoint**: User Story 1 is fully functional and independently testable — Google registration/login works end-to-end (quickstart.md scenario 1); the generic OAuth machinery (state, PKCE, callback branching, race-condition handling) now exists for US2 to reuse.

---

## Phase 4: User Story 2 - 使用 LINE 帳號快速註冊/登入 (Priority: P1)

**Goal**: The same one-click registration/login as US1, through LINE instead of Google, including the LINE-specific case where the user declines to share their email (FR-004).

**Independent Test**: A visitor with no existing account clicks "使用 LINE 繼續", completes LINE's consent screen (with or without granting email access), and lands back in the app already logged in with a new verified account; clicking it again with the same LINE account logs back into the same account.

### Tests for User Story 2

- [X] T027 [P] [US2] Unit test: `oauth_providers.LINE`'s config has the right `authorize_url`/`token_url`/`jwks_url`/scopes (including the LINE-specific `nonce` requirement noted in research.md #3) — extend `test_oauth_flow.py`
- [X] T028 [P] [US2] Unit tests for `complete_oauth_callback()` intent=login/provider=line: **with** an email in the id_token (same success shape as T012); **without** an email (FR-004) — creates a `Member` with `email=None`, `password_hash=None`, still `verification_status="verified"`, FR-005 collision check correctly skipped (T015 already covers the "skip when no email" assertion generically; this task confirms it specifically for LINE's real no-email response shape) — extend `test_oauth_flow.py`
- [X] T029 [P] [US2] Contract tests for `GET /auth/oauth/line/start` and `GET /auth/oauth/line/callback` in `test_oauth_login.py`, mirroring T018 for LINE plus the no-email success branch

### Implementation for User Story 2

- [X] T030 [US2] Verify/adjust the `LINE` entry in `oauth_providers.py` against T027's test (trivial if T005 already matches research.md #3; this task exists to make the LINE-specific config change explicit and reviewable) (depends on T027)
- [X] T031 [US2] In `complete_oauth_callback()`, confirm/adjust the branch that handles a `None` email from the provider profile — skip the FR-005 collision query entirely when email is absent (depends on T028, T022)

**Checkpoint**: User Stories 1 AND 2 both independently functional — quickstart.md scenarios 1–3 pass (Google, LINE-with-email, LINE-without-email).

---

## Phase 5: User Story 3 - 既有 Email／密碼會員為帳號額外綁定 Google／LINE 登入方式 (Priority: P2)

**Goal**: A logged-in Email/password member can bind a Google and/or LINE account to their existing account from Settings, then log in with either method afterward; FR-008's last-method guard and FR-013's account-recovery reminder/set-password/add-email paths are also delivered here.

**Independent Test**: A logged-in existing member selects "綁定 Google 帳號" in Settings, completes Google's consent screen, and Settings now shows "已綁定"; after logging out, clicking "使用 Google 繼續" with that same Google account logs back into the *original* existing account (same nickname/friends/match history), not a new one.

### Tests for User Story 3

- [X] T032 [P] [US3] Unit tests for `complete_oauth_callback()` intent=link in `test_oauth_flow.py`: success creates a new `member_oauth_identities` row bound to the caller's `member_id`; re-binding the same `(provider, sub)` to the same caller is idempotent (no error, no duplicate row); binding a `(provider, sub)` already bound to a **different** member is rejected (`OAUTH_IDENTITY_ALREADY_LINKED`, FR-007) without touching the existing binding; **the caller already has a *different* `(provider, sub)` bound for this same provider — rejected with `OAUTH_PROVIDER_ALREADY_LINKED`, existing binding untouched, no replacement** (/speckit-analyze 2026-09-14 remediation, finding C1 — spec.md FR-006 previously left this branch undefined)
- [X] T033 [P] [US3] Unit tests for `unlink_oauth_identity()` in new file `apps/api/tests/unit/domains/member/test_unlink_oauth_identity.py`: success removes the row; `OAUTH_IDENTITY_NOT_LINKED` when the provider isn't bound; `LAST_LOGIN_METHOD` (FR-008) when removing it would leave the member with no `password_hash` and no other binding — no row is deleted in that case
- [X] T034 [P] [US3] Unit tests: `change_password()` and `delete_account()` skip password verification when `member.password_hash is None` (research.md #7) — extend `apps/api/tests/unit/domains/member/test_personal_settings.py` and the existing 025-delete-account unit test file
- [X] T035 [P] [US3] Unit tests for `add_email()` (FR-013) in new file `apps/api/tests/unit/domains/member/test_add_email.py`: success writes `member.email` and sends a verification email via the existing `EmailVerificationToken` flow; `EMAIL_ALREADY_SET` when `member.email` is already non-null; `EMAIL_ALREADY_REGISTERED` when the target email collides with another existing member (case-insensitive, matching `register()`)
- [X] T036 [P] [US3] Contract tests in `apps/api/tests/contract/test_member_personal_settings.py`: `DELETE /members/me/oauth-identities/{provider}`, `POST /members/me/email`; `PATCH /members/me/password` and `DELETE /members/me` both accept an omitted `current_password` when the member has none, and still require/validate it when one exists; binding a second different account for an already-linked provider returns `OAUTH_PROVIDER_ALREADY_LINKED` (C1)
- [X] T037 [P] [US3] Frontend tests: Settings page renders `linked_oauth_providers` status, 綁定/解除綁定 controls, the FR-013 reminder block (only when `password_hash` and `email` are both absent), and the add-email form — `apps/web/src/app/features/member/settings/settings.component.spec.ts`

### Implementation for User Story 3

- [X] T038 [US3] Implement the `intent=link` branch of `complete_oauth_callback()` in `service.py`: success/idempotent-repeat/FR-007-reject, plus the FR-006/C1 check — query the caller's existing bindings for this `provider` **before** attempting the insert and reject with `OAUTH_PROVIDER_ALREADY_LINKED` if one already exists for a different `(provider, sub)`, MUST NOT delete-then-replace (depends on T032, T022)
- [X] T039 [US3] Implement `unlink_oauth_identity(session, member, provider)` in `service.py` + `DELETE /members/me/oauth-identities/{provider}` in `router.py` (depends on T033)
- [X] T040 [US3] Update `change_password()`/`delete_account()` in `service.py` for the password-optional branch (research.md #7); wire the already-relaxed `ChangePasswordRequest`/`DeleteAccountRequest` from T007 through their routers (depends on T034, T007)
- [X] T041 [US3] Implement `add_email(session, member, email)` in `service.py`, reusing `_issue_verification_token_and_email()` + `POST /members/me/email` in `router.py` (depends on T035)
- [X] T042 [US3] Update `_to_public()`/`GET /members/me` in `router.py` to populate `linked_oauth_providers` from `member_oauth_identities` (depends on T007)
- [X] T043 [P] [US3] Add 綁定/解除綁定 controls (calling `GET .../start?intent=link` and `DELETE .../oauth-identities/{provider}`), the FR-013 reminder block, and the add-email form to `apps/web/src/app/features/member/settings/settings.component.html`/`.ts` (depends on T037, T039, T041, T042)
- [X] T044 [P] [US3] Add remaining i18n keys (`settings.oauth.*`, `errors.OAUTH_IDENTITY_ALREADY_LINKED`/`OAUTH_PROVIDER_ALREADY_LINKED`/`OAUTH_IDENTITY_NOT_LINKED`/`LAST_LOGIN_METHOD`/`EMAIL_ALREADY_SET`) to `zh-TW.json`/`en.json` (`OAUTH_PROVIDER_ALREADY_LINKED` added per finding C1)

**Checkpoint**: All three stories independently functional; FR-001–FR-013 fully enforced end-to-end.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [ ] T045 [P] Run `specs/027-google-line-oauth-login/quickstart.md` end-to-end against the local Docker Compose stack (all 7 scenarios, using real or sandbox Google/LINE OAuth app credentials) — **partially verified, 2026-09-14**: the user registered a real Google OAuth client (redirect URI `http://localhost:4200/api/auth/oauth/google/callback`, `FRONTEND_BASE_URL` switched to `localhost` for local testing — a LAN IP redirect_uri is rejected by Google outside `https`) and completed **quickstart scenario 1 live** — clicked "使用 Google 繼續" as a first-time visitor, completed Google's real consent screen, and was logged into a brand-new account. Confirmed directly in the dev DB: `member_oauth_identities` has one row (`provider=google`, real `provider_user_id`/`email_at_link`), the linked `members` row has `verification_status=verified` and `password_hash IS NULL` (research.md #6/#4), and the first-login nickname-setup redirect (FR-012) was completed. Along the way, `oauth_client.py` gained structured error logging (`logger.error`/`logger.exception` on every `OAUTH_PROVIDER_ERROR` branch, including Google's raw error body) since the generic error code alone gave no way to diagnose a real failure from `docker logs`. That logging immediately paid off twice: (1) a transient container-clock-skew rejection ("issued in the future") — fixed by adding a 60s `leeway` to `claims.validate()`, since authlib defaults to zero tolerance and the OIDC spec itself recommends a small allowance; (2) a **real bug** — `_ALLOWED_ALGORITHMS` was hardcoded to `["RS256"]` (Google's scheme), but LINE Login signs its id_token with `HS256` (HMAC via the channel secret) by default, so every LINE login failed signature verification outright. Fixed by adding `_peek_alg()` (reads the JWT header's `alg`, unverified, purely to route) so `HS256` verifies against `config.client_secret` directly and `RS256`/`ES256` still verify via JWKS — no hardcoded per-provider assumption anymore. Neither bug had test coverage (the existing unit/contract tests monkeypatch `exchange_code_for_profile()` entirely, never exercising real JWT verification) — closed with a new file, `tests/unit/domains/member/test_oauth_client.py` (11 tests, real `authlib`-signed RS256/HS256 tokens against a monkeypatched `httpx.AsyncClient`, no live network): covers the RS256-via-JWKS and HS256-via-client-secret paths, the HS256 path asserting the JWKS endpoint is never even called, the clock-skew leeway boundary (accepted just inside it, rejected just outside), and the existing nonce/aud/iss/wrong-secret rejection paths. `ruff`/`pytest` clean; `mypy` untouched deliberately (this project's mypy gate is `app/` only, tests aren't type-checked here).

With that fixed, **quickstart scenario 2 (LINE) also ran live** — including the FR-004 "no email" branch specifically (this test LINE account had no email permission granted): `member_oauth_identities` got a `provider=line` row with `email_at_link` empty, the linked `members` row has `email` empty, `verification_status=verified`, `password_hash IS NULL`, and first-login nickname setup completed — exactly per design. Two distinct real Google accounts and one LINE account have now round-tripped through this flow. Scenarios 3–7 (returning-login across both providers, cancel, email-collision, account-recovery reminder UI, mobile layout) and any AWS/production redirect URI are still not run.
- [X] T046 Full regression pass: backend `ruff check` + `mypy --strict` + `pytest` (970 passed); frontend `ng lint` + `ng build --configuration development` + `ng test --watch=false` (325 passed)

**Notes on requirements with no dedicated task**: FR-009 (accounts created/linked via OAuth follow every existing member rule — nickname, friends, match records, privacy settings, account deletion) requires no new code of its own — it's the *absence* of a parallel account system, verified implicitly by every other task reusing the existing `Member` entity and its existing endpoints rather than introducing new ones.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies.
- **Foundational (Phase 2)**: Depends on Setup (T003) — BLOCKS all three user stories.
- **User Story 1 (Phase 3)**: Depends on Foundational completion. Builds the entire generic OAuth machinery (state/PKCE/callback branching/race-condition handling); no dependency on US2/US3.
- **User Story 2 (Phase 4)**: Depends on Foundational completion. Reuses `start_oauth_flow()`/`complete_oauth_callback()`/`oauth-callback.component` built in US1 (T021/T022/T025) — not independently buildable *before* US1, but independently *testable/deployable* once both exist, same relationship as 026's US1→US2.
- **User Story 3 (Phase 5)**: Depends on Foundational completion and on US1's `complete_oauth_callback()`/`start_oauth_flow()` (T021/T022) existing to extend with the `intent=link` branch. Independently testable once those exist.
- **Polish (Phase 6)**: Depends on all three user stories being complete.

### Parallel Opportunities

- Foundational: T005–T008 are all parallel (four different files) once T004 lands.
- US1: T009–T020 (all twelve test tasks) are parallel (different files/frameworks). T024/T025/T026 are parallel once T021–T023 exist.
- US2: T027–T029 are parallel. T030/T031 are small, sequential adjustments to files US1 already created.
- US3: T032–T037 are parallel. T043/T044 are parallel once T038–T042 exist.

---

## Parallel Example: User Story 1

```bash
# Tests, launched together:
Task: "member_oauth_identities UNIQUE constraints unit tests"
Task: "issue_oauth_state()/decode_oauth_state() unit tests"
Task: "start_oauth_flow() unit tests"
Task: "complete_oauth_callback() new-member success path unit tests"
Task: "complete_oauth_callback() returning-member path unit tests"
Task: "complete_oauth_callback() cancel/state-invalid path unit tests"
Task: "complete_oauth_callback() FR-005 email-collision unit tests"
Task: "complete_oauth_callback() FR-011 deleted-account unit tests"
Task: "complete_oauth_callback() concurrent-duplicate race-condition unit test"
Task: "GET /auth/oauth/google/start and /callback contract tests (full branch table)"
Task: "login.component Google/LINE button tests"
Task: "oauth-callback.component tests"

# Implementation, launched together once their tests exist:
Task: "login.component.html/.ts button wiring"
Task: "oauth-callback.component creation + route registration"
Task: "auth.* i18n keys"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1 (Setup) → Phase 2 (Foundational) → Phase 3 (US1).
2. **STOP and VALIDATE**: run quickstart.md scenario 1 — Google one-click registration and returning-login both work.
3. This alone delivers the feature's core stated value (one-click account creation via a mainstream provider, no verification-email wait) even before US2's LINE entry point or US3's account-linking exist.

### Incremental Delivery

1. Setup + Foundational → shapes ready, no behavior change.
2. Add US1 → validate independently → Google login/registration works end-to-end (MVP).
3. Add US2 → validate independently → LINE entry point added (with/without email), reusing US1's machinery.
4. Add US3 → validate independently → existing members can bind/unbind, FR-008/FR-013 account-recovery paths land.
5. Polish → full regression + quickstart replay (all 7 scenarios).

---

## Notes

- [P] tasks touch different files with no unmet dependency.
- Tests are written before their corresponding implementation task; each task is done only when its test(s) pass and the full suite (backend + frontend) stays green.
- research.md #1–#3 are the load-bearing design constraints across all three stories: the entire OAuth handshake (state/PKCE/id_token verification) is provider-agnostic and lives in `start_oauth_flow()`/`complete_oauth_callback()`/`oauth_providers.py` — US2 and US3 extend it, they don't duplicate it.
- research.md #4/#7 are the load-bearing constraints for US3 specifically: every existing call site that assumed `member.email`/`member.password_hash` is never `None` (`change_password()`, `delete_account()`, any mail-sending path) MUST get an explicit `None`-handling branch — T034/T040 exist specifically to prove that boundary holds for the two known call sites; a regression here would silently 500 for OAuth-only members using otherwise-ordinary account features.
- FR-005 (email collision, account-takeover prevention) and FR-011 (deleted-account rejection) are the two highest-severity branches in this feature — T015/T016/T017/T018 exist specifically because a pre-analyze pass over this task list had *implementation* coverage for them (folded into T022's description) but no *dedicated test* coverage at all (/speckit-analyze 2026-09-14 findings E1/E2/E3). Do not let a future edit collapse these back into "covered by T022's implementation" — they need their own green test runs.
- FR-006's "second different account for an already-linked provider" branch (C1) is intentionally tested as part of T032 (the same function under test) rather than as a separate task — it's one more assertion on `complete_oauth_callback()`'s `intent=link` branch, not a new code path.
- Avoid: adding a second, parallel "OAuth session" concept distinct from the existing `access_token`/`refresh_token` pair — every success path (new account, returning login, or link) MUST end at the same `issue_access_token()`/`issue_refresh_token()` used by the existing Email/password `login()`.
