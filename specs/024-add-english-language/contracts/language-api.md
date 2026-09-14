# Contract: Language-related API surface

## `GET /members/me/supported-languages` (relaxed — auth removed)

**Change**: Remove the `Depends(security.require_member)` dependency. The
route path, method, and response shape are unchanged.

- **Auth**: None (was: `require_member`, a Bearer access token).
- **Request**: no body, no query params.
- **Response 200** — `SupportedLanguagesResponse`:
  ```json
  { "languages": ["zh-TW", "en"] }
  ```
- **Errors**: none (previously could 401 with `MEMBER_TOKEN_INVALID`; that
  is no longer possible since auth is no longer required).
- **Callers**: `settings.component.ts` (existing, 個人設定 dropdown — no
  request-side change needed, it simply now succeeds without a token too),
  new `LanguageService` (fetched once at app init regardless of login
  state), new standalone switchers on `scoreboard`/`control-panel`/
  `all-courts-control-panel`.

## `PATCH /members/me/language` (unchanged)

No contract change. Still `require_verified_member`-gated, still
`{ language: str }` → `MemberPublicResponse`, still raises
`LANGUAGE_NOT_SUPPORTED` for a value outside `SUPPORTED_LANGUAGES`. Now also
invoked by the new `LanguageService.setLanguage()` (in addition to the
existing 個人設定 dropdown) whenever a logged-in member uses the new global
switcher (FR-003c).

## `POST /members/register` (extended)

**Change**: `RegisterRequest` gains one new optional field.

- **Request body** — `RegisterRequest`:
  ```json
  {
    "email": "user@example.com",
    "password": "...",
    "confirm_password": "...",
    "turnstile_token": "...",
    "language": "en"
  }
  ```
  `language` is optional; when omitted, behavior is byte-for-byte identical
  to today (column default `'zh-TW'` applies).
- **Response**: unchanged (`RegisterResponse`).
- **Validation**: an unsupported/malformed `language` value is ignored
  (falls back to the default), never causes a 4xx — registration must not
  fail because of this cosmetic field.

## Transactional emails (no HTTP contract — internal behavior change)

Not an API contract in the request/response sense, but a documented
behavior change to `_issue_verification_token_and_email()` and
`forgot_password()` (both in `apps/api/app/domains/member/service.py`):
subject/body are now selected by `member.language_preference` (`zh-TW` →
existing Chinese text, unchanged; `en` → new English text), instead of
always being the hardcoded Chinese strings. No change to `send_email()`'s
own signature (`to`, `subject`, `body`).
