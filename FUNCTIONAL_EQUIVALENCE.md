# Functional Equivalence Matrix — Taidy (Streamlit → React/FastAPI)

Fase 1 deliverable. Produced by reading every file under `webapp/` in full and
grepping the entire repository for Streamlit usage (not just `app.py`) — see
the verification commands at the bottom of this document.

Legend for **Migration status**: `pending` (not started) · `in progress` ·
`done` (implemented + tested in React/FastAPI) · `n/a` (Streamlit-only concern
that has no React equivalent, e.g. `st.session_state`).

## Scope confirmed by dynamic grep

- Streamlit API surface actually used (28 distinct calls, `webapp/*.py`):
  `st.Page, st.badge, st.button, st.cache_data, st.cache_resource, st.caption,
  st.checkbox, st.code, st.columns, st.dataframe, st.date_input, st.dialog,
  st.divider, st.error, st.expander, st.form, st.form_submit_button,
  st.fragment, st.graphviz_chart, st.info, st.markdown, st.multiselect,
  st.navigation, st.number_input, st.page_link, st.radio, st.rerun,
  st.selectbox, st.session_state, st.set_page_config, st.sidebar, st.stop,
  st.subheader, st.success, st.text_input, st.title, st.toggle, st.warning,
  st.write`.
- `st.session_state` keys: `auth_user` (current session identity/role),
  `_auth_login_audited` (internal, suppresses duplicate audit-log lines),
  `wf_draft_steps` (in-progress workflow designer draft) — plus one
  `st.session_state`-backed key per widget (`key=` on every form field).
- No existing API layer found anywhere in the repo (`fastapi`/`flask` grep:
  zero hits outside `.venv`). This is a from-scratch backend.
- No Microsoft Entra ID present. It was built in an earlier phase of this
  project and explicitly removed at the owner's request, replaced with local
  username/password (bcrypt + SQLite) after two real production incidents
  with a persistent-cookie library. **The migration must preserve this local
  auth mechanism, not reintroduce Entra ID or invent a new scheme.**

## Architecture map (`webapp/*.py` → responsibility)

| Module | Responsibility | Side effects |
|---|---|---|
| `app.py` (1320 lines) | All 14 pages + sidebar + 6 confirmation dialogs; pure presentation, delegates everything else | none directly — calls into the modules below |
| `adapter.py` (360) | Builds CLI argv from form params; parses subprocess log text into per-table/file status | reads `tables.yaml`/`factorial_tables.yaml`/`config.json` (cached on mtime) |
| `tasks.py` (467) | Launches `python -m src.X ...` as real subprocesses; live log capture; stop; in-memory registry | spawns OS processes, writes `run_history.json` via `history.py` |
| `workflow_engine.py` (226) | Polling DAG coordinator: runs several `tasks.py` launches in parallel/sequence per `depends_on`/`trigger_rule` | in-memory registry of `WorkflowRun` |
| `workflows.py` (151) | CRUD + validation (cycle detection) for saved workflow *definitions*; Graphviz DOT generator | reads/writes `workflows.json` |
| `scheduler.py` (241) | APScheduler `BackgroundScheduler` CRUD; dispatches ticks into `tasks.launch()`/`workflow_engine.start_workflow()` | reads/writes `schedules.json`; runs in the same process as the web server |
| `history.py` (69) | Append-only run history (last 200 entries, log capped at 20k chars) | reads/writes `run_history.json` |
| `auth.py` (256) | Session gate, role checks, login/logout/forced-password forms, audit log | reads/writes `audit.log`; reads `st.session_state` |
| `users_db.py` (231) | SQLite user store: bcrypt hashing, lockout after 5 failed attempts, role CRUD (protects last admin) | reads/writes `users.db` |

## Equivalence matrix

| ID | Current feature | Streamlit file(s) | Backend called | State used | Side effects | React/API implementation | Test needed | Status |
|---|---|---|---|---|---|---|---|---|
| F-01 | Login (username/password) | `auth.py:_render_login_form`, `app.py` gate | `users_db.verify_login` | `session_state.auth_user` | reads `users.db`; writes `audit.log`; 5-attempt lockout (5 min) | `POST /auth/login` → HttpOnly session cookie or JWT; React login form + auth context | unit (lockout, bad creds), API, E2E login | done |
| F-02 | Forced password change (first login / admin reset) | `auth.py:render_change_password_form` | `users_db.change_password` | `session_state.auth_user.must_change_password` | writes `users.db` | `POST /auth/change-password`; React blocks all routes until satisfied, mirroring the hard gate | unit, API, E2E | done |
| F-03 | Logout | `auth.py:do_logout`, sidebar button | — | clears `session_state.auth_user` | writes `audit.log` | `POST /auth/logout`; clear cookie/token client-side | API, E2E | done |
| F-04 | Session/role gate on every page | `auth.py:require_authenticated_user/require_role/check_role` | — | `session_state.auth_user.role` | — | FastAPI dependency (`Depends(current_user)`) re-checked on **every** endpoint, never trusted from the client; React route guards mirror it for UX only | unit, API (403 cases) | done |
| F-05 | Inicio (home): status summary + quick links | `app.py:page_home` | `tasks.list_tasks`, `workflow_engine.list_runs`, `scheduler.list_schedules`, `history.get_history` | — | none (read-only) | `GET /dashboard/summary`; React dashboard cards + links | component, API | done |
| F-06 | BC · Extraer (form + launch) | `app.py:page_bc_extract` | `adapter.build_extract_bc_argv`, `tasks.launch` | role check (Admin for reset-checkpoints) | spawns subprocess | `POST /tasks/extract-bc` (Pydantic model); React form | unit (argv building), API, E2E launch | done |
| F-07 | BC · Subir | `app.py:page_bc_upload` | `adapter.build_upload_bc_argv`, `tasks.launch` | — | spawns subprocess | `POST /tasks/upload-bc` | unit, API | done |
| F-08 | BC · Sync (extract+upload chained) | `app.py:page_bc_sync` | `tasks.launch("sync_bc")` → `start_sync_task` | — | 2 sequential subprocesses | `POST /tasks/sync-bc` | unit, API, E2E | done |
| F-09 | Factorial · Extraer (date range, employee filter/IDs) | `app.py:page_fac_extract` | `adapter.build_extract_factorial_argv`, `tasks.launch` | role check (Admin for reset-all) | spawns subprocess | `POST /tasks/extract-factorial` | unit (date validation, employee-id parsing), API | done |
| F-10 | Factorial · Subir | `app.py:page_fac_upload` | `adapter.build_upload_factorial_argv`, `tasks.launch` | — | spawns subprocess | `POST /tasks/upload-factorial` | unit, API | done |
| F-11 | Factorial · Sync | `app.py:page_fac_sync` | `tasks.launch("sync_factorial")` | — | 2 sequential subprocesses | `POST /tasks/sync-factorial` | unit, API, E2E | done |
| F-12 | Fabric · Pipelines (list + trigger + live poll) | `app.py:page_pipelines` | `adapter.list_fabric_pipelines`, `tasks.launch("run_pipeline")` → `src/fabric_pipelines` | — | calls Fabric REST API | `GET /pipelines`, `POST /tasks/run-pipeline` | unit, API (mocked Fabric client) | done |
| F-13 | Tareas en curso: live list, per-table status, stop (confirm) | `app.py:_render_running_tasks/page_running`, dialog `_confirm_stop_task` | `tasks.list_tasks/stop_task/get_task`, `adapter.parse_*` | filters (`running_f_*`, session-backed) | terminates subprocess | `GET /tasks` (poll or SSE), `POST /tasks/{id}/stop`; React polls or subscribes | unit (parser fix regression, see BUG-01), API, E2E stop flow | done |
| F-14 | Flujos: design a new workflow (blocks, dependencies, trigger rule) | `app.py:page_workflows` (design section) | `workflows.create_workflow` (validates cycles) | `session_state.wf_draft_steps` | writes `workflows.json` | `POST /workflows` with a step-graph body; React designer (see ARCHITECTURE.md for the Plotly-interactive plan) | unit (cycle detection), API, E2E | done |
| F-15 | Flujos: list saved, launch, delete (confirm) | `app.py:page_workflows` (saved section), dialog `_confirm_delete_workflow` | `workflows.list_workflows/delete_workflow`, `workflow_engine.start_workflow` | — | writes `workflows.json`; spawns subprocesses | `GET /workflows`, `DELETE /workflows/{id}`, `POST /workflows/{id}/run` | unit, API, E2E | done |
| F-16 | Flujos: live run list, per-step diagram, stop (confirm) | `app.py:page_workflows` (running section), dialog `_confirm_stop_workflow` | `workflow_engine.list_runs/stop_workflow` | — | terminates subprocess(es) | `GET /workflow-runs`, `POST /workflow-runs/{id}/stop` | unit, API, E2E | done |
| F-17 | Tareas programadas: create (interval/cron), any action incl. workflows | `app.py:page_schedules` (new section) | `scheduler.add_schedule` | role check (Admin) | writes `schedules.json`; registers APScheduler job | `POST /schedules`; React form now collects the same action-specific params `page_schedules` did (`start_on`/`employee_status` for Factorial, `mode`/`parallel`, `skip_existing`, `pipeline`/`poll_seconds`, saved-workflow picker) — previously it only ever sent `{notify}`, so every scheduled Factorial or pipeline run, and `run_workflow` (missing as an option entirely), failed at execution time; also verified `scheduler._run_scheduled` recomputes `end_on` to today for recurring Factorial schedules rather than reusing the stale date saved at creation | unit (`webapp/tests/test_scheduler.py`, `_run_scheduled` end_on recompute), API (cron/interval validation), E2E (`schedules.spec.ts`) | done |
| F-18 | Tareas programadas: list, pause/resume, delete (confirm) | `app.py:page_schedules` (existing section), dialog `_confirm_delete_schedule` | `scheduler.list_schedules/set_schedule_enabled/remove_schedule` | — | writes `schedules.json` | `GET /schedules`, `PATCH /schedules/{id}`, `DELETE /schedules/{id}` | unit, API | done |
| F-19 | Historial: list, filter (acción/usuario/resultado/fecha), paginate, view log | `app.py:page_history` | `history.get_history` | filters (`hist_f_*`) | — | `GET /history?action=&source=&result=&from=&to=&page=` | unit (filter logic), API | done |
| F-20 | Auditoría: list, filter, view (Admin only) | `app.py:page_audit` | `auth.get_audit_log` | filters (`audit_f_*`) | — | `GET /audit?...` (403 for non-Admin) | unit, API (authz) | done |
| F-21 | Usuarios: create | `app.py:page_users` (create section) | `users_db.create_user` | — | writes `users.db` | `POST /users` (Admin only) | unit (validation), API | done |
| F-22 | Usuarios: list, change role (2-step: select then "Guardar rol" then confirm dialog) | `app.py:page_users` (list section), dialog `_confirm_change_role` | `users_db.set_role` (protects last admin) | — | writes `users.db` | `PATCH /users/{username}/role`; React: same 2-step + confirm-modal pattern (H-04/ND-05 fix must not regress) | unit (last-admin protection), API, E2E | done |
| F-23 | Usuarios: force password reset | `app.py:page_users` | `users_db.force_password_reset` | — | writes `users.db` | `POST /users/{username}/reset-password` | unit, API | done |
| F-24 | Usuarios: delete (confirm, protects last admin) | `app.py:page_users`, dialog `_confirm_delete_user` | `users_db.delete_user` | — | writes `users.db` | `DELETE /users/{username}` | unit, API, E2E | done |
| F-25 | Mi cuenta: voluntary password change | `app.py:page_account` | `auth.render_change_password_form(force=False)` | — | writes `users.db` | `POST /auth/change-password` (same endpoint as F-02, `force=false`) | unit, API | done |
| F-26 | Sidebar identity + logout, grouped nav (6 sections, Admin-only "Administración") | `app.py` bottom (Page objects + `st.navigation`) | `auth.has_role` | — | — | React Router + role-gated nav config; role-conditional section rendering | component, E2E (Reader doesn't see Admin nav) | done |
| F-27 | Theming (light/dark, WCAG AA verified in Fase 7) | `.streamlit/config.toml` | — | — | — | CSS custom properties / design tokens carried over 1:1 (documented palette + contrast ratios in this repo's history) | visual regression (manual) | done |
| BUG-01 | **Known bug, just fixed on the Streamlit side**: per-table status showed "error" for a table that was simply still exporting | `adapter.py:parse_bc_extract_tables/parse_factorial_extract_tables` | — | — | — | Port the fixed logic (`finished` flag) verbatim; regression test already exists (`webapp/tests/test_table_status_while_running.py`) — must have a FastAPI-side equivalent | unit (already written for Streamlit; needs a Python-side port, not a rewrite) | done |
| BUG-02 | **Known bug, not yet fixed**: one exhausted-retries file aborts the whole upload batch, reporting a total failure even when most files succeeded | `src/fabric_upload/uploader.py:upload_files/_upload_with_retry` | — | — | — | Fix in `src/` (business logic, shared by both UIs) before or during migration — flagged separately, see Open Questions | unit | done |
| NEW-01 | Requested but not yet built on the Streamlit side either: modern icon set, editable saved workflows, interactive click-to-edit diagram, email notifications | — (feature request, not existing functionality) | `webapp/notifications.py`, `webapp/workflows.py:update_workflow`, `webapp/tasks.py`/`webapp/workflow_engine.py` `notify` flag | admin-only workflow design/edit | writes `workflows.json`; sends email via `smtplib` (best-effort, never raises) | `PATCH /workflows/{id}`; `notify` field on all task/workflow-run launch endpoints; React: `lucide-react` icons app-wide, `@xyflow/react` interactive diagram (click-to-select, drag-to-connect, edge-click to disconnect) for designing, editing, and viewing saved/running workflows | unit (`webapp/tests/test_notifications.py`), API (notify-flag plumbing, PATCH endpoint), component (Vitest), E2E (`workflow-diagram.spec.ts`, `workflows-and-notify.spec.ts`) | done |
| NEW-02 | Requested but not present on the Streamlit side either: register, edit, or remove a Business Central or Factorial table from the web UI instead of hand-editing `tables.yaml`/`factorial_tables.yaml` on the server; sidebar "Ejecutar" split into distinct Business Central / Factorial / Fabric sections; table pickers on the Extract/Sync/Upload forms replaced with a tag-based multiselect (the native `<select multiple>` gave no visible way to deselect once something was picked) | — (feature request, not existing functionality) | `webapp/table_configs.py` (add/update/delete/list, shared path constants with `adapter.list_bc_tables/list_factorial_tables`) | admin-only add/update/delete | writes `tables.yaml` / `factorial_tables.yaml` (the exact files `src/bc_client/config.py` / `src/factorial_client/config.py` already read for real runs) | `GET/POST/PATCH/DELETE /meta/{bc,factorial}-tables[/{name}]`; React: dedicated `/administracion/conexiones-api` page ("Conexiones API"), two-column layout (fixed add/edit form on the left, live list on the right) with `<BcTableManager>`/`<FactorialTableManager>`, both admin-gated — kept out of the Extract pages themselves per feedback, which now just link to it ("Gestionar tablas"); `<TagMultiSelect>` replaces the native multiselect on all 5 table-picker forms; `NavShell` sidebar regrouped (Inicio → Actividad → Programación → Flujos → Business Central → Factorial → Fabric → Administración → Cuenta), admin nav item renamed "Conexiones API" | unit (`webapp/tests/test_table_configs.py`), API (`api/tests/test_meta.py`), E2E (`table-management.spec.ts`) | done |

## Difficult-to-migrate functionality (flag now, per Fase 1 instructions)

1. **`st.dialog` confirmation modals** (6 of them) — trivial in React (any modal
   library or a hand-rolled one), but the *2-step role-change pattern*
   (selector change → reveals "Guardar rol" button → opens modal → confirms)
   must be preserved exactly; it exists specifically to fix a real accidental-
   permission-change incident (finding H-04).
2. **`st.fragment(run_every=...)` non-blocking auto-refresh** for "Tareas en
   curso" — the React equivalent is a polling `useQuery`/`setInterval` or SSE;
   must not blockingly `sleep()` like the pre-Fase-9 Streamlit code did.
3. **Subprocess lifecycle** (`tasks.py`) — a background thread pumps
   `subprocess.Popen` stdout live and exposes stop-via-`terminate()`. In
   FastAPI this needs an explicit progress/status mechanism (the Fase 3
   instructions explicitly forbid indefinitely-blocked HTTP requests) —
   proposed: `GET /tasks` polling, or Server-Sent Events streaming the log.
4. **APScheduler running in-process** — FastAPI can host the same
   `BackgroundScheduler` (it's just a Python object, framework-agnostic), but
   its lifecycle must be tied to the FastAPI app's startup/shutdown events
   instead of `st.cache_resource`.
5. **Per-table/per-file status reconstructed from raw log text** (`adapter.py`)
   — inherently fragile (it greps the subprocess's log output because
   `src/` has no structured progress API); must be ported byte-for-byte, not
   redesigned, to avoid silently changing behavior.
6. **Local auth is bcrypt+SQLite, not Entra ID** — contradicts this
   migration's own default assumption ("conservar Entra ID si existe"); it
   does not exist here. Flagged in Open Questions.

## Verification commands used to build this document

```
git log --oneline -5
grep -rohE "st\.[a-zA-Z_]+" webapp/*.py | python -c "..." # dedup/sort
grep -rohE "session_state\[[\"'][a-zA-Z_0-9]+[\"']\]" webapp/*.py
grep -rn "os.environ|load_dotenv|config.json|\.env" webapp/*.py src/config_loader.py
grep -rln "fastapi|flask" --include="*.py" .   # zero hits outside .venv
```
