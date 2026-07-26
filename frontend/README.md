# Taidy — Frontend (React + TypeScript + Vite)

React UI talking to the FastAPI backend in `../api/`, which itself reuses
the auth/workflows/scheduler business logic in `../webapp/`. See
`../ARCHITECTURE.md` for design decisions.

## Prerequisites

- Node.js 20+ and npm
- The backend running first (see `../api/README` section of the root
  `README.md`, or just: `uvicorn api.main:app --reload --host 127.0.0.1 --port 8000`
  from the project root, with the Python virtualenv active)

## Setup

```bash
npm install
cp .env.example .env.local   # defaults already point at http://127.0.0.1:8000
```

## Development

```bash
npm run dev
```

Opens on `http://127.0.0.1:5173` (bound explicitly to `127.0.0.1`, not
`localhost` — the session cookie is host-only and `SameSite=Lax`; mixing
`localhost`/`127.0.0.1` between the frontend and API silently drops it, see
`../ARCHITECTURE.md`).

## Testing

```bash
npm run test        # Vitest + Testing Library (component tests)
npm run test:e2e    # Playwright (requires both the API and this dev server
                     #   already running against ISOLATED state -- never
                     #   point an E2E run at the real webapp/users.db;
                     #   see the isolation pattern in api/tests/conftest.py
                     #   and mirror it with your own throwaway launcher)
```

## Production build

```bash
npm run build      # tsc -b (strict) && vite build -> dist/
npm run preview    # serve the built dist/ locally to sanity-check it
```

## Project layout

```
src/
  api/          typed fetch client + one module per backend domain
  auth/         session context, route guards (mirrors webapp/auth.py's gate)
  components/   shared UI: NavShell, StatusBadge, ConfirmDialog, Form styles
  hooks/        usePolling (periodic refresh for in-flight tasks/runs)
  pages/        one file per route, grouped to match the nav sections
  styles/       design tokens (WCAG-AA verified)
  test/         Vitest setup (includes a jsdom <dialog> polyfill)
e2e/            Playwright specs
```
