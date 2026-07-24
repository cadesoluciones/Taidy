# Target Architecture — Taidy React/FastAPI migration

Companion to `FUNCTIONAL_EQUIVALENCE.md` (what's being migrated) and
`MIGRATION_PLAN.md` (phased execution order). This document is the "how."

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

### Auth — preserving the existing mechanism exactly

Per constraint #4 (never invent auth if it doesn't exist) and the explicit
"conservar Entra ID si existe" clause: **Entra ID does not exist in this
project.** It was built and then explicitly removed earlier in this project's
history, replaced by local username/password (bcrypt + SQLite in
`webapp/users_db.py`) after real production incidents with a persistent-
cookie library. The only correct reading of constraint #4 here is: *preserve
the local auth mechanism that actually exists* — not resurrect Entra ID. This
is flagged again in Open Questions for explicit confirmation before Fase 3
auth work is finalized.

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

## Frontend design

- **State/data fetching**: a small typed API client (`fetch` wrapper) plus
  React Query (or SWR) for polling/caching — avoids hand-rolled `useEffect`
  polling loops sprinkled across pages.
- **Confirmation dialogs**: one `<ConfirmDialog>` component reused for all 6
  destructive actions (delete user, delete workflow, delete schedule, stop
  task, stop workflow, change role) — mirrors `webapp/app.py`'s own "one
  pattern, six call sites" design.
- **Status badges**: one `<StatusBadge status="running|ok|error|...">`
  component, driven by the same status vocabulary the backend already emits
  (`running, stopping, ok, error, stopped, pending, cancelled, in_progress`)
  — never inventing new client-side states.
- **Icons**: the Streamlit side just adopted Material Symbols
  (`:material/icon_name:`) for a modern look; the React side uses
  `@mui/icons-material` or plain SVGs from the same Material Symbols set, so
  the two UIs read as the same product during the parallel-run period.

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

## Security checklist (Fase 5, tracked here so it isn't lost)

- [ ] Secrets only via `.env`/`config.json` (existing pattern), never in
      frontend bundle or committed to git.
- [ ] `.env.example` for both `api/` and `frontend/`, no real values.
- [ ] CORS restricted to `http://127.0.0.1:5173` (Vite dev) and the eventual
      production origin — never `*`.
- [ ] Every mutating endpoint re-validates role server-side (never "the
      button was hidden so it must be fine" — this is already the Streamlit
      app's own documented invariant, carried forward unchanged).
- [ ] Path/traversal checks on any file-serving endpoint (log downloads, if
      added) — reuse the existing `_MAX_LOG_CHARS`-capped, path-free log
      storage model rather than serving raw file paths.
- [ ] No stack traces returned to the client on unhandled exceptions
      (`.streamlit/config.toml`'s `showErrorDetails = "none"` has a direct
      FastAPI equivalent: a global exception handler returning a generic
      500 body, full trace only in server logs).

## Open questions (blocking, need an explicit answer before Fase 3 is "final")

1. **Entra ID vs. local auth** — confirming the reading above (preserve local
   bcrypt+SQLite auth; Entra ID is not being resurrected) before building
   `api/routers/auth.py`.
2. **Session mechanism** — HttpOnly cookie (recommended, matches the current
   threat model) vs. bearer JWT in a frontend store. Cookie is the default
   unless told otherwise.
3. **Polling vs. SSE** for task/workflow-run live status — polling proposed
   as the Fase-3 baseline; SSE as later enhancement.
4. **React Flow vs. Cytoscape.js** for the interactive diagram — a reversible
   technical choice, will be decided during Fase 4 implementation using best
   judgment (both satisfy the "no custom JS component, use a maintained
   library" constraint the owner set) unless there's a preference now.
