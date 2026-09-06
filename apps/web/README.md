# Rally Stats Web

Angular 20 (standalone components, Signals) frontend for Rally Stats. See
`specs/architecture.md` (repo root) for the full route map and design, and
`specs/001-create-manage-group/` for the feature currently implemented
(`features/group-admin/`).

## Prerequisites

- Node.js (matching `@angular/cli` 20.x's supported range)
- The API backend running locally (see `apps/api/README.md`) — the dev
  proxy target is `http://localhost:8000` (`src/environments/environment.ts`)

## Local setup

```bash
cd apps/web
npm install
```

## Running

```bash
npm start   # ng serve, http://localhost:4200
```

`environment.ts` (used by the `development` build config) points at
`http://localhost:8000` for the API and uses Cloudflare's Turnstile test
site key, which always passes. Update `environment.prod.ts` /
`fileReplacements` in `angular.json` for production values.

## Tests

Vitest, via Angular's experimental `@angular/build:unit-test` builder:

```bash
npm test
```

## Linting

```bash
npm run lint
```

## Project layout

```
src/app/
├── app.routes.ts             # 6 lazy-loaded feature route groups
├── core/
│   ├── api/                   # ApiClient base + error-code → i18n interceptor
│   └── realtime/               # RealtimeService (Ably JS SDK wrapper)
└── features/
    ├── group-admin/            # 001: create-group, admin-page, reauth
    ├── home/ group-join/ member/ scoreboard/ control-panel/   # placeholders
                                  #   until their specs (002/004/006/007) ship
src/assets/i18n/zh-TW.json     # i18n strings (ngx-translate)
```
