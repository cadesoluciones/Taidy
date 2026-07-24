# Migration Plan — Taidy Streamlit → React/FastAPI

Branch: `migration/streamlit-to-react` (created off `feature/factorial-main`
at commit `efeb617`, which is a clean, fully-committed baseline of the
Streamlit app after its own modernization pass — nothing pending, nothing
mixed in with migration work).

Read `FUNCTIONAL_EQUIVALENCE.md` first (what exists, what must not regress)
and `ARCHITECTURE.md` second (the target shape). This document is the
execution order and what "done" means at each step.

## Ground rules carried through every phase

- `src/` business logic is called, never duplicated, never rewritten to make
  the migration easier.
- `webapp/` (Streamlit) stays fully functional and untouched-in-behavior
  until React reaches parity for the feature being replaced — it is the
  rollback path, not dead code to delete early.
- Every mutating operation is re-authorized server-side; the frontend hiding
  a button is never the only protection (this is already how the Streamlit
  app works — the bar does not lower).
- No real secrets touched, no destructive operations against `users.db`,
  `run_history.json`, `schedules.json`, `workflows.json`, or `audit.log` —
  all new backend tests use the same isolated-tmp-path pattern already
  established in `webapp/tests/conftest.py`.
- Small, phase-scoped commits on `migration/streamlit-to-react` — each phase
  below ends with one or a few commits, not one giant commit at the end.

## Phase 0 — Housekeeping (done)

- Committed all pending Streamlit-side work as a clean baseline
  (`efeb617`).
- Created `migration/streamlit-to-react` off that commit.

## Phase 1 — Full audit (done, this commit)

- Deliverable: `FUNCTIONAL_EQUIVALENCE.md` (27 functional rows + 2 known bugs
  + 1 new-feature row, all traced to file:line-level source), plus the
  architecture map inside it.
- Method: read every file under `webapp/` in full (already done across this
  project's history) + a fresh dynamic grep sweep for `st.*` calls,
  `session_state` keys, and config/env access across the **whole** repo, not
  just `app.py` — commands logged at the bottom of that document for
  reproducibility.

## Phase 2 — Verifiable baseline (this commit)

- Confirmed the current app starts cleanly (`streamlit run webapp/app.py`,
  repeated boot checks throughout this project's history, most recently
  right before this migration began).
- `webapp/tests/` (9 tests, added this session) already covers the three
  audit-identified user journeys (BC sync launch + permission check, user
  creation + role-change-confirmation flow, history filtering) plus a
  regression test for the per-table status bug (BUG-01). This *is* Fase 2's
  requested characterization-test baseline — not something to redo from
  scratch. Ran and confirmed green immediately before starting Phase 3.
- **Not captured, and explicitly flagged rather than glossed over**: byte-
  for-byte output recordings from real Business Central / Factorial HR /
  Fabric runs. This environment has no real credentials for those systems —
  every test (Streamlit-side and the new API-side ones) exercises the
  orchestration layer with the real subprocess boundary swapped for a
  harmless stand-in (`webapp/tests/conftest.py:fake_subprocess`). This is a
  pre-existing limitation of the test environment, not something the
  migration introduces or can fix.

## Phase 3 — Backend API (in progress)

Order (each a separately testable, committable slice):

1. `api/main.py` skeleton: FastAPI app, CORS restricted to the Vite dev
   origin, global exception handler (no stack traces to the client),
   lifespan hook starting the same `BackgroundScheduler` `webapp/scheduler.py`
   already uses.
2. `api/routers/auth.py` + `api/dependencies.py`: login, logout,
   change-password, `get_current_user()` — a thin wrapper around
   `webapp/auth.py`/`webapp/users_db.py`, not a reimplementation. **First
   vertical slice** (see Phase 4) pairs this with the React login page so
   there is a real, running, click-testable path before the remaining 26
   features are ported.
3. `api/routers/tasks.py`: the six task-launching endpoints (F-06..F-11) +
   list/stop (F-13), wrapping `webapp/tasks.py`/`webapp/adapter.py` verbatim,
   including the just-fixed `finished` flag for per-table status (BUG-01).
4. `api/routers/workflows.py`, `schedules.py`, `history.py`, `audit.py`,
   `users.py`, `dashboard.py`: remaining routers, in that order (workflows
   before schedules because schedules can target a workflow).
5. `api/tests/`: one pytest file per router, same isolation fixtures as
   `webapp/tests/conftest.py`.

## Phase 4 — Frontend (starts once Phase 3's auth slice is live)

1. Vite + React + TS scaffold, typed API client, auth context, login page,
   route guard. **Paired with Phase 3 step 2 as the first end-to-end vertical
   slice** — proves the whole chain (browser → Vite → fetch → FastAPI →
   `users_db` → SQLite) before investing in the other 13 pages.
2. Remaining pages, grouped by the same 6 nav sections the Streamlit sidebar
   already uses (Inicio; Ejecutar ×7; Flujos; Programación; Actividad ×2;
   Administración ×2, Admin-only; Cuenta) — same information architecture,
   not reinvented.
3. Flujos gets the interactive-diagram upgrade (see `ARCHITECTURE.md`) once
   its baseline create/list/launch/delete parity is in place — upgrade,
   not a prerequisite for parity.

## Phase 5 — Security pass

Checklist lives in `ARCHITECTURE.md`; executed once the full surface exists,
not per-endpoint ad hoc, so it can be verified exhaustively in one pass.

## Phase 6 — Equivalence testing

- Backend: pytest per router (written alongside each router in Phase 3, not
  deferred).
- Frontend: Vitest + Testing Library per page/component.
- E2E: Playwright covering the journeys in `FUNCTIONAL_EQUIVALENCE.md`
  (login, full nav sweep, filter+paginate history, launch a task, edit a
  workflow, upload/download if applicable, permission checks, logout).
- Explicit Streamlit-vs-React comparison: for each launched task/workflow,
  compare the resulting `run_history.json` entry (action, status, message)
  produced by each UI for the same inputs — both call the identical
  `tasks.launch()`, so this is really a comparison that the API layer didn't
  introduce a discrepancy, not that the two UIs "coincidentally look similar."

## Phase 7 — Controlled cleanup

Only after Phase 6 is green: enumerate now-obsolete files, grep the whole
repo for references, remove only what's proven unreferenced, re-run every
test suite, confirm `git status` shows only migration-related changes. Until
then `webapp/` stays exactly as it is — this phase is not started.

## Phase 8 — Local execution docs

Folded into the final `README.md` update once Phase 4 produces a real
`frontend/` to document (a "how to run it" section written before the thing
it describes exists would just be speculative).

## Status reporting format (used at the end of every phase from here on)

- Changes made
- Files affected
- Tests run and result
- Risks or differences found
- Next phase
