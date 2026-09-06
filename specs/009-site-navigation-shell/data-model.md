# Phase 1 Data Model: 全站導覽規劃（行動裝置優先）

**Feature**: [spec.md](./spec.md) | **Research**: [research.md](./research.md)

This feature introduces no database entities, migrations, or API request/
response shapes (see research.md Decision summary — pure front-end scope).
The only new "data" is client-side view state. Documented here for
traceability since the template calls for a data-model artifact whenever a
feature has structured data, even purely client-side state.

## `AuthService.loggedIn` (new reactive field)

| Field | Type | Description |
|-------|------|--------------|
| `loggedIn` | `Signal<boolean>` | `true` when a member access token is present. Read-only to consumers; flipped internally by `setTokens()` → `true` and the new `logout()` → `false`. |

No validation rules — it mirrors `getAccessToken() !== null` at all times by
construction (set at the same call sites that already mutate the token).

## `NavItem` (view-model, not persisted)

Internal shape used by `NavShellComponent` to render its link list. Not
exported outside the component; not an API contract.

| Field | Type | Description |
|-------|------|--------------|
| `labelKey` | `string` | i18n key resolved via `translate` pipe (Constitution VIII — no hardcoded text). |
| `routerLink` | `string` | Angular route path. |
| `visibility` | `'always' \| 'guest-only' \| 'member-only'` | Gates whether the item renders given `AuthService.loggedIn()`. |

Example set (illustrative — final copy/keys decided during implementation):

| labelKey | routerLink | visibility |
|---|---|---|
| `nav.home` | `/` | always |
| `nav.groups` | `/groups` | always |
| `nav.login` | `/auth/login` | guest-only |
| `nav.register` | `/auth/register` | guest-only |
| `nav.memberHome` | `/member` | member-only |
| `nav.settings` | `/member/settings` | member-only |
| `nav.matchHistory` | `/member/match-history` | member-only |
| `nav.logout` (action, not a route) | — | member-only |

## State transitions

```
Guest (loggedIn=false)
  --[login() succeeds]--> Member (loggedIn=true)

Member (loggedIn=true)
  --[logout() invoked from shell]--> Guest (loggedIn=false)
```

No other states exist; there is no "partially authenticated" nav state —
an unverified-email member is still `loggedIn=true` for navigation purposes
(the existing email-verification gate, per Constitution IV, blocks the
*pages themselves*, not the nav shell's own rendering).
