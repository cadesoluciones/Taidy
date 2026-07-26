# Architecture — Taidy React/FastAPI

Companion to `FUNCTIONAL_EQUIVALENCE.md` (what was migrated from the retired
Streamlit UI). This document describes the shipped architecture.

## Stack decision

The prescribed default stack was checked against the repo and adopted as-is —
nothing here justified a deviation:

| Layer | Choice | Why not something else |
|---|---|---|
| Frontend | React + TypeScript (strict) | prescribed default; no existing frontend framework to conflict with |
| Build tool | Vite | prescribed default; no existing bundler in the repo |
| Backend | Python, FastAPI | prescribed default; **zero** existing API code found (`grep -rl "fastapi\|flask"` → no hits outside `.venv`) — greenfield, no framework to duplicate |
| Validation | Pydantic v2 (FastAPI's own dependency) | matches FastAPI idioms exactly |
| Backend tests | pytest | already the project's test framework — `webapp/tests/` (added this session) already exercises the business-logic modules this API will wrap |
| Frontend tests | Vitest + Testing Library | prescribed default |
| E2E tests | Playwright | prescribed default |
| Local execution | `uvicorn` (backend) + Vite dev server (frontend), both bound to `127.0.0.1` by default | matches the existing Streamlit deployment's own loopback-only posture (`.streamlit/config.toml`) |

## Directory layout (proposed)

```
Taidy/
  src/                     # UNCHANGED — existing business logic (bc_client,
                            #   factorial_client, fabric_upload, fabric_pipelines,
                            #   ingest). The API imports from here; nothing here
                            #   is duplicated in Python or reimplemented in TS.
  webapp/                   # UNCHANGED during migration — kept as the rollback
                            #   path until React reaches parity (per constraint #4).
  api/                       # NEW — FastAPI backend
    main.py                  #   app factory, CORS, startup/shutdown (scheduler)
    dependencies.py          #   get_current_user() — the ONE place that reads
                              #     the session and enforces roles, mirroring
                              #     auth.require_role()/check_role()
    routers/
      auth.py                #   /auth/login, /auth/logout, /auth/change-password
      tasks.py                #   /tasks/* (extract/upload/sync/run-pipeline, list, stop)
      workflows.py             #   /workflows/*, /workflow-runs/*
      schedules.py              #   /schedules/*
      history.py                 #   /history
      audit.py                    #   /audit
      users.py                     #   /users/*
      dashboard.py                  #   /dashboard/summary (Inicio)
    schemas/                 #   Pydantic request/response models, 1:1 with
                              #     the routers above
    services/                 #   THIN wrappers around webapp/*.py functions --
                              #     no business logic lives here, just
                              #     translating a Pydantic model <-> the
                              #     existing function signatures (tasks.launch,
                              #     workflows.create_workflow, users_db.*, etc.)
    tests/                      #   pytest, one file per router, isolated state
                              #     (same tmp_path pattern as webapp/tests/)
  frontend/                  # NEW — React + TypeScript + Vite
    src/
      api/                     #   typed fetch client, one function per endpoint
      auth/                     #   auth context, route guard, login page
      pages/                     #   Home, BcExtract, BcUpload, BcSync,
                              #     FactorialExtract/Upload/Sync, Pipelines,
                              #     Workflows, Schedules, Running, History,
                              #     Audit, Users, Account
      components/                 #   shared: ConfirmDialog, StatusBadge,
                              #     DataTable (filter+paginate), NavShell
      hooks/                       #   usePolling (Tareas en curso / workflow
                              #     runs), useAuth
      test/                         #   Vitest + Testing Library
    e2e/                        #   Playwright specs
    .env.example                 #   VITE_API_BASE_URL=http://127.0.0.1:8000
  .env.example                 # backend equivalent (session secret, CORS origins,
                              #   DB paths) -- no real secrets, matches the
                              #   existing project's .env.example convention
```

## Backend design

### Auth

Local username/password (bcrypt + SQLite in `webapp/users_db.py`) — Entra ID
was built and then explicitly removed earlier in this project's history after
real production incidents with a persistent-cookie library, and is not being
resurrected.

Session model: FastAPI issues an HttpOnly, `SameSite=Lax`, `Secure`-when-
possible session cookie (not a bare JWT in `localStorage`, to avoid XSS token
theft — Streamlit's own session already had no client-readable token, so this
preserves the same threat model rather than weakening it). `get_current_user()`
is a FastAPI dependency injected into **every** protected route — the same
"never trust a hidden button, re-check the role server-side" invariant the
Streamlit app documents explicitly in `auth.py` carries over unchanged.

### Long-running tasks — no indefinitely-blocked requests

`webapp/tasks.py`'s subprocess model (spawn `python -m src.X`, pump stdout in
a background thread, expose `stop()` via `proc.terminate()`) is reused
**as-is** — the API layer does not reimplement it. `POST /tasks/extract-bc`
etc. return `202 Accepted` with a task ID immediately; the frontend then
either:

- polls `GET /tasks/{id}` (simplest, matches the existing `st.fragment`
  polling model 1:1), or
- subscribes to `GET /tasks/{id}/stream` (Server-Sent Events) for live log
  lines, which is a strict improvement over Streamlit's "expand to see last
  10 lines" pattern.

Recommendation: **start with polling** (lower risk, matches existing
behavior exactly, easier to test) and treat SSE as a fast-follow enhancement
— not required for functional parity.

### Scheduler

`webapp/scheduler.py`'s `BackgroundScheduler` (APScheduler) is framework-
agnostic — it is instantiated once in FastAPI's `lifespan` startup hook
instead of behind `st.cache_resource`, and ticks call the exact same
`tasks.launch()` / `workflow_engine.start_workflow()` functions.

### Session cookie — a local-dev gotcha found and fixed

The session cookie is `HttpOnly`, `SameSite=Lax`, host-only (no explicit
`Domain`). Found via a real, failing E2E test (not by inspection): serving
the frontend on `localhost:5173` while the API ran on `127.0.0.1:8000`
silently dropped the cookie on every request after login, because
`localhost` and `127.0.0.1` are different *sites* for `SameSite` purposes
even though both are loopback — login "worked" (its response body is used
directly, no cookie round-trip needed to render the result), but logout
called an endpoint that depends on the cookie and got a silent 401, which
an unawaited exception then swallowed client-side. **Both the API and the
Vite dev server must be addressed as `127.0.0.1`, never a mix with
`localhost`**, for the session to work at all locally. Documented here so
the next person (or session) doesn't lose an hour to the same symptom.

## Frontend design

### Visual design language (approved by the project owner)

The owner shared reference screenshots of a *different* CADE product
("ANEMIOT" device-provisioning console) and asked for that visual language,
not its functionality, applied here: a white/light UI with a top header bar
(logo + product name + live-status dot + user identity + a bordered
danger-toned logout button), colored-left-border accent cards for
hero/status emphasis, metric tile rows, a two-column list/detail layout, a
modal-based management pattern (list on the left, detail form on the
right), timeline lists with dot markers, and a split-screen login page
(dark photographic/brand panel left, form panel right). Adopted structurally;
colors use Taidy's own already-WCAG-AA-verified palette from
`.streamlit/config.toml` (see `frontend/src/styles/tokens.css`) rather than
literally copying the other product's blue/orange branding — Taidy isn't
ANEMIOT and reusing already-vetted, accessible tokens is strictly better
than introducing an unverified new palette.

A second, more detailed round of ANEMIOT screenshots (directory/detail user
management modal, a checklist-style step grid, connected-line timelines, a
dark hero + metric tiles + accent card + system-status bar, and an explicit
"read-only" indicator for a restricted role) drove a follow-up pass that
actually built those specific patterns, each mapped onto real Taidy data —
never a fabricated field or a control that doesn't call anything real (see
each component's own doc comment for the specific tradeoff):

- **State/data fetching**: a small typed API client (`fetch` wrapper) plus
  a `usePolling` hook for live-updating pages — avoids hand-rolled
  `useEffect` polling loops sprinkled across pages.
- **Confirmation dialogs**: one `<ConfirmDialog>` component reused for all
  destructive actions (delete user, delete workflow, delete schedule, stop
  task, stop workflow, change role) — mirrors `webapp/app.py`'s own "one
  pattern, six call sites" design.
- **Status badges**: one `<StatusBadge status="running|ok|error|...">`
  component, driven by the same status vocabulary the backend already emits
  (`running, stopping, ok, error, stopped, pending, cancelled, in_progress`)
  — never inventing new client-side states.
- **Icons**: `lucide-react` app-wide (nav, badges, buttons) — replaced every
  emoji/unicode icon that predated the migration.
- **`<UserDirectory>`**: the directory/detail user-management pattern —
  used both as `/administracion/usuarios`'s page content and inside a
  `<Modal>` opened from a header icon (lazily mounted only while the modal
  is actually open, so the two entry points never double-fetch). ANEMIOT's
  mockup has fields Taidy has no backend for (an admin-typed new password, an
  "active/inactive" toggle) — rather than fake them, the "Seguridad" section
  only exposes what `webapp/users_db.py` actually supports: forcing a
  password change on next login, not setting one directly.
- **`<Timeline>`**: a generic dot-and-connecting-line list (icon, tone,
  title, description, timestamp) — used by Historial and the dashboard's
  recent-activity feed.
- **`<StepStatusGrid>`**: a checklist-card grid (icon + name + phase +
  detail) replacing the plain table Tareas en curso used for a task's
  per-table/file status.
- **`<ReadOnlyNotice>`**: a small "Modo consulta" banner shown on the 7
  Ejecutar forms when the current user's role is Reader, with the submit
  button disabled to match — previously Reader could click submit and only
  find out via a 403 after the fact.
- **HomePage hero**: a dark panel with an abstract, inline-SVG data/network
  motif (`<DataNetworkArt>`) rather than a stock photo — nothing here claims
  to depict real Taidy infrastructure. The accent card and status bar below
  it are both driven by the same `/dashboard/summary` fields already in use
  (active schedule count; a derived tone from recent-error/running counts),
  not decorative placeholders.

## Flujos (workflow designer) — the one deliberately-new piece of UX

The owner asked for two upgrades beyond parity while this migration happens:
editing an already-saved workflow (today: create/delete only), and a more
visual, interactive diagram. Two options were presented and the owner chose
the interactive one:

- **Rejected**: a fully custom drag-and-drop canvas (hand-rolled SVG/canvas +
  pointer-event handling) — highest control, highest ongoing maintenance risk.
- **Chosen**: a proper graph-visualization React library (e.g. **React Flow**
  or **Cytoscape.js** — final pick during Fase 4 implementation) rendering
  each workflow as an interactive node graph: click a node to open its edit
  panel (reusing the same per-action form fields as the "add block" form),
  drag to reposition (cosmetic only — `depends_on` is still edited via an
  explicit control, not by drawing arrows, to avoid accidental DAG changes),
  and an explicit "Guardar cambios" step before persisting — same
  intent-before-mutation discipline as the rest of the app.

This does **not** block Streamlit-parity work; it is additive scope on the
React side once F-14/F-15/F-16 reach baseline parity.

## Email notifications — new feature, backend-only secrets

Per the owner's decision: notifications go to a **fixed admin distribution
list**, not per-user addresses (no new field on the user model). SMTP
settings live in `config.json`/`.env` (same place BC/Factorial/Fabric
credentials already live) — **never** sent to or stored in the frontend.
`POST /tasks/{id}` and workflow-run completion hooks call a
`services/notifications.py` module; a per-task/schedule/workflow boolean
("avisar por email") is the only piece of this that reaches the UI.

## Security checklist

- [x] Secrets only via `.env`/`config.json` (existing pattern), never in
      frontend bundle or committed to git.
- [x] `.env.example` for both `api/` and `frontend/`, no real values.
- [x] CORS restricted to an explicit origin allowlist — never `*`.
- [x] Every mutating endpoint re-validates role server-side (never "the
      button was hidden so it must be fine").
- [x] Path/traversal checks on any file-serving endpoint — reuse the
      existing `_MAX_LOG_CHARS`-capped, path-free log storage model rather
      than serving raw file paths.
- [x] No stack traces returned to the client on unhandled exceptions — a
      global exception handler returns a generic 500 body, full trace only
      in server logs.
