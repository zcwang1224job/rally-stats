# Phase 1 Data Model: 新增英文語系

No new database tables, columns, or migrations. This feature is additive at
the code-constant level only.

## Existing entities touched (no shape change)

### `Member.language_preference` (from 022-member-personal-settings)

- Column: `VARCHAR(8) NOT NULL DEFAULT 'zh-TW'`, unchanged.
- Previously effectively single-valued (`SUPPORTED_LANGUAGES = ("zh-TW",)`
  meant only `'zh-TW'` could ever be validly written). This feature extends
  the *code-level* allow-list to `SUPPORTED_LANGUAGES = ("zh-TW", "en")` —
  no column width/type/default change needed (`"en"` fits in `VARCHAR(8)`).
- New write path: `register()` may now set this at creation time from the
  registering browser's current language (FR-009), instead of always
  relying on the column default. Still validated against
  `SUPPORTED_LANGUAGES`; an invalid/missing value falls back to the column
  default exactly as before.

### `RegisterRequest` (backend `schemas.py` / frontend `member-auth.models.ts`)

- New field: `language: str | None = None` (backend, optional, defaults to
  `None`) / `language?: string` (frontend, optional).
- Validation: if provided, MUST be one of `SUPPORTED_LANGUAGES`; invalid
  values are silently ignored (fall back to the existing default), not
  rejected — a bad/unexpected language value must never block registration.

## New client-only state (no backend persistence)

### Anonymous "guest" display-language choice

- Storage: browser `localStorage`, single key
  (`rally-stats.language`), value one of `SUPPORTED_LANGUAGES`.
- Lifecycle: written whenever an anonymous visitor uses the global switcher
  or a standalone court/scoreboard-page switcher (FR-003b). Read once at
  app init when no logged-in member session exists. Overridden (not
  merged) by the member's `language_preference` the moment a login
  succeeds (FR-003b/US2#3) — the localStorage value itself is left as-is
  (not cleared) so it's available again after logout (US2#4: logging out
  keeps showing the language that was active, whether that came from the
  account or from the pre-login guest choice).

### In-memory current-language signal (`LanguageService`)

- A single reactive signal, the resolved "what `ngx-translate` is currently
  set to" value, exposed read-only to consumers (the switcher component(s),
  and anything needing to display the current choice). Not itself persisted
  — it's a derived/cache view over (member session | localStorage |
  default), recomputed per research.md item #2's precedence rule.

## Cosmetic-only, non-authoritative data

### Language display-name map (FR-008)

- A small frontend map, e.g. `{ 'zh-TW': <i18n key>, 'en': <i18n key> }`,
  used purely to render each option's own label. Lives alongside
  `LanguageSwitcherComponent`/the settings dropdown. Explicitly NOT a
  second source of truth for which languages are selectable — that remains
  `SUPPORTED_LANGUAGES` (backend) as fetched via `GET /members/me/
  supported-languages`. Adding a third language in the future means adding
  one entry here and one entry to the backend tuple; this feature doesn't
  need to design for that beyond keeping the map keyed by the same codes.
