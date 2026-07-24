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

## Phase 4 — Frontend (started; step 1 done)

1. **Done.** Vite + React + TS (strict) scaffold in `frontend/`, design
   tokens reusing Taidy's WCAG-AA-verified palette, typed API client
   (`src/api/client.ts`), auth context + route guards (`src/auth/`), login
   page + forced-change-password page + a minimal authenticated shell
   (`src/components/AppShell.tsx`) matching the owner-approved visual
   language (see `ARCHITECTURE.md`). This is the first end-to-end vertical
   slice — proved the whole chain (browser → Vite → fetch → FastAPI →
   `users_db` → SQLite) with a real Playwright run against live servers, not
   just unit tests. Found and fixed a real bug in the process: the session
   cookie silently failed to round-trip when the frontend was served on
   `localhost` while the API ran on `127.0.0.1` (see `ARCHITECTURE.md`,
   "Session cookie — a local-dev gotcha").
2. Remaining pages, grouped by the same 6 nav sections the Streamlit sidebar
   already uses (Inicio; Ejecutar ×7; Flujos; Programación; Actividad ×2;
   Administración ×2, Admin-only; Cuenta) — same information architecture,
   not reinvented. Each pairs with its FastAPI router from Phase 3.
3. **Not done** — Flujos gets the interactive-diagram upgrade (see
   `ARCHITECTURE.md`) as a deliberate follow-up once its baseline
   create/list/launch/delete parity is in place. Baseline parity (step 2)
   is done and tested; the interactive diagram itself, the "edit an
   existing saved workflow" capability (ND-11), and email notifications
   (the owner's other new-feature ask) are **not started**. Tracked as
   `NEW-01` in `FUNCTIONAL_EQUIVALENCE.md`.

## Phase 5 — Security pass (done)

Checklist verified against actual source (not just asserted) in
`ARCHITECTURE.md`'s "Security checklist" section: no hardcoded secrets, every
mutating endpoint's `dependencies=` audited directly against each router's
source, parameterized SQL confirmed pre-existing, CORS locked to one origin,
no stack traces to the client, cookie flags confirmed, `api/.env.example`
added (was missing).

## Phase 6 — Equivalence testing (done for everything built so far)

- Backend: pytest per router, written alongside each router in Phase 3 —
  41 tests (webapp/tests + api/tests) + 2 more from the Fase-8-adjacent bug
  fix below = 43, all passing.
- Frontend: Vitest + Testing Library — 12 tests (StatusBadge, ConfirmDialog,
  LoginPage).
- E2E: Playwright — 10 tests covering a full 15-route nav sweep (Admin sees
  all pages, non-Admin is redirected out of Administración and doesn't see
  it in the sidebar), a real task launch settling in Tareas en curso, and
  admin user-management through the 2-step role-change confirm dialog. Run
  against BOTH live servers with isolated state, never the real
  `webapp/users.db`.
- **Not done**: the explicit Streamlit-vs-React output comparison this phase
  originally called for (same inputs, same `run_history.json` entry from
  both UIs) — both UIs call the identical `tasks.launch()`, so this is a
  low-risk gap, but it is a real, deliberate gap, not silently skipped.
- **Not done**: accessibility/responsive verification of the new React
  pages (the Streamlit side went through a dedicated WCAG AA pass; React
  reused the same verified color tokens but hasn't had its own contrast/
  keyboard-nav/responsive-breakpoint check).

## Phase 7 — Controlled cleanup (explicitly NOT started)

Blocked on the two Phase 6 gaps above by the migration's own rule: "no
elimines Streamlit hasta que React haya alcanzado equivalencia funcional Y
todas las verificaciones hayan terminado correctamente." `webapp/` has not
been touched-in-behavior and stays the rollback path. This phase requires
explicit sign-off before it starts — removing Streamlit is exactly the kind
of hard-to-reverse, broad-scope action this project treats as a stop-and-ask
point, not a default continuation.

## Phase 8 — Local execution docs (done)

`README.md` gained a `webapp/` section (previously undocumented despite
existing) and a migration section with run instructions for both `api/` and
`frontend/`. `frontend/README.md` replaced the generic Vite scaffold
template with real project docs, `.env.example` added for both `api/` and
`frontend/`.

## Status reporting format (used at the end of every phase from here on)

- Changes made
- Files affected
- Tests run and result
- Risks or differences found
- Next phase
