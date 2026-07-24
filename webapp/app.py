# -*- coding: utf-8 -*-
"""
Streamlit web interface for Taidy.

Run with: streamlit run webapp/app.py (from the project root), behind a
reverse proxy that terminates HTTPS.

This file only builds forms, renders results, and enforces role checks
immediately before each action; the actual work happens in subprocesses
launched by webapp/tasks.py, which itself only invokes the existing,
unmodified CLI entry points in src/** (`python -m src.main ...`, etc.).

To add a new UI action: add an argv-builder to adapter.py (if needed), wire
it into tasks.MODULE_FOR_ACTION / tasks.launch(), and add a form/page below
gated with auth.check_role(...)/check_any_role(...) — nothing else changes.

Each page is a standalone zero-argument function, registered with
st.navigation() near the bottom of this file. To add a new page: write a
`def page_x(): ...` function next to the others and add an `st.Page(...)`
entry to the relevant section below.
"""

from __future__ import annotations

import sys
import uuid
from datetime import date, datetime
from pathlib import Path

import streamlit as st

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from webapp import (  # noqa: E402
    adapter,
    auth,
    history,
    scheduler as sched_module,
    tasks,
    users_db,
    workflow_engine,
    workflows,
)

st.set_page_config(page_title="Taidy — Panel de datos", page_icon="🗂️", layout="wide")

# Hard gate: must be first. Blocks anonymous access and enforces a pending
# forced password change. Nothing below this line renders otherwise.
auth.require_authenticated_user()


@st.cache_resource
def _get_scheduler():
    return sched_module.build_scheduler()


scheduler = _get_scheduler()

ACTION_LABELS = tasks.ACTION_LABELS
# "run_workflow" isn't a tasks.py subprocess action (it orchestrates several of
# them via workflow_engine.py), so it's added only to the display-label map,
# used for the schedule picker and history/schedule list rendering.
SCHEDULABLE_LABELS = {**ACTION_LABELS, "run_workflow": "Flujo (varios bloques)"}

_TABLE_STATUS_LABELS = {
    "ok": ("✅", "OK"),
    "skipped": ("⏭️", "Omitida"),
    "dry_run": ("🧪", "Simulada"),
    "error": ("❌", "Error"),
    "unknown": ("❓", "Desconocido"),
    "in_progress": ("⏳", "En curso"),
}

# (badge color, icon, text) — st.badge is native to Streamlit, no custom CSS needed.
_TASK_STATUS_BADGE = {
    "running": ("blue", "🔵", "En curso"),
    "stopping": ("orange", "🟠", "Deteniendo…"),
    "ok": ("green", "✅", "Completada"),
    "error": ("red", "❌", "Error"),
    "stopped": ("gray", "⏹️", "Detenida"),
}


def _status_badge(status: str) -> None:
    color, icon, text = _TASK_STATUS_BADGE.get(status, ("gray", "❓", status))
    st.badge(text, icon=icon, color=color)


# --------------------------------------------------------------------------------------
# Shared render helpers
# --------------------------------------------------------------------------------------


def _render_table_statuses(statuses) -> None:
    if not statuses:
        return
    has_phase = any(s.phase for s in statuses)
    rows = []
    for s in statuses:
        icon, label = _TABLE_STATUS_LABELS.get(s.status, ("❓", s.status))
        row = {}
        if has_phase:
            row["Fase"] = s.phase or "-"
        row["Tabla / fichero"] = s.name
        row["Estado"] = f"{icon} {label}"
        row["Detalle"] = s.detail
        rows.append(row)
    st.dataframe(rows, width="stretch", hide_index=True)


def _launch_and_report(action: str, params: dict) -> None:
    if not auth.check_any_role(auth.ROLES_OPERATE):
        st.error("No tienes permiso para ejecutar esta acción (requiere rol App.Operator o App.Admin).")
        return
    try:
        task = tasks.launch(action, params, auth.get_current_user())
    except (RuntimeError, ValueError) as exc:
        st.error(str(exc))
        return
    st.success(f"Tarea iniciada (`{task.id[:8]}`). Sigue el progreso en **Tareas en curso**.")


def _parse_employee_ids(raw: str) -> tuple[list[int] | None, str | None]:
    raw = raw.strip()
    if not raw:
        return None, None
    try:
        return [int(x.strip()) for x in raw.split(",") if x.strip()], None
    except ValueError:
        return None, "Los IDs de empleados deben ser números separados por comas (ej. 123, 456)."


# --------------------------------------------------------------------------------------
# Confirmation dialogs — every irreversible or high-impact action goes through one of
# these instead of acting on a single click. Each dialog re-checks the role right
# before acting, same as everywhere else — the confirmation step is about intent,
# not a substitute for the authorization check.
# --------------------------------------------------------------------------------------


@st.dialog("Borrar usuario")
def _confirm_delete_user(username: str) -> None:
    st.warning(
        f"Vas a borrar definitivamente al usuario **{username}**. "
        "No podrá volver a iniciar sesión y esta acción no se puede deshacer."
    )
    c1, c2 = st.columns(2)
    if c1.button("Cancelar", key=f"cancel_deluser_{username}", width="stretch"):
        st.rerun()
    if c2.button("Borrar definitivamente", key=f"confirm_deluser_{username}", type="primary", width="stretch"):
        if not auth.check_role(auth.ROLE_ADMIN):
            st.error("Requiere el rol App.Admin.")
        else:
            try:
                users_db.delete_user(username)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.rerun()


@st.dialog("Cambiar rol")
def _confirm_change_role(username: str, old_role: str, new_role: str) -> None:
    st.warning(
        f"Vas a cambiar el rol de **{username}** de `{old_role}` a `{new_role}`. "
        "Esto cambia inmediatamente lo que esa persona puede hacer en la aplicación."
    )
    c1, c2 = st.columns(2)
    if c1.button("Cancelar", key=f"cancel_role_{username}", width="stretch"):
        st.rerun()
    if c2.button("Confirmar cambio", key=f"confirm_role_{username}", type="primary", width="stretch"):
        if not auth.check_role(auth.ROLE_ADMIN):
            st.error("Requiere el rol App.Admin.")
        else:
            try:
                users_db.set_role(username, new_role)
            except ValueError as exc:
                st.error(str(exc))
            else:
                st.rerun()


@st.dialog("Borrar flujo")
def _confirm_delete_workflow(workflow_id: str, name: str) -> None:
    st.warning(
        f"Vas a borrar el flujo **{name}** y su definición completa. "
        "Las tareas programadas que lo usen dejarán de funcionar. Esta acción no se puede deshacer."
    )
    c1, c2 = st.columns(2)
    if c1.button("Cancelar", key=f"cancel_wfdel_{workflow_id}", width="stretch"):
        st.rerun()
    if c2.button("Borrar definitivamente", key=f"confirm_wfdel_{workflow_id}", type="primary", width="stretch"):
        if not auth.check_role(auth.ROLE_ADMIN):
            st.error("Requiere el rol App.Admin.")
        else:
            workflows.delete_workflow(workflow_id)
            st.rerun()


@st.dialog("Borrar tarea programada")
def _confirm_delete_schedule(schedule_id: str, name: str) -> None:
    st.warning(f"Vas a borrar la tarea programada **{name}**. Dejará de ejecutarse y no se puede deshacer.")
    c1, c2 = st.columns(2)
    if c1.button("Cancelar", key=f"cancel_scheddel_{schedule_id}", width="stretch"):
        st.rerun()
    if c2.button("Borrar definitivamente", key=f"confirm_scheddel_{schedule_id}", type="primary", width="stretch"):
        if not auth.check_role(auth.ROLE_ADMIN):
            st.error("Requiere el rol App.Admin.")
        else:
            sched_module.remove_schedule(scheduler, schedule_id)
            st.rerun()


@st.dialog("Detener tarea")
def _confirm_stop_task(task_id: str, label: str) -> None:
    st.warning(
        f"Vas a detener la tarea **{label}** en curso. "
        "Si estaba escribiendo datos, se interrumpirá en el punto en el que esté."
    )
    c1, c2 = st.columns(2)
    if c1.button("Cancelar", key=f"cancel_stop_{task_id}", width="stretch"):
        st.rerun()
    if c2.button("Detener definitivamente", key=f"confirm_stop_{task_id}", type="primary", width="stretch"):
        current = auth.get_current_user()
        t = tasks.get_task(task_id)
        owns = t is not None and (auth.has_role(auth.ROLE_ADMIN) or t.triggered_by == current)
        if not owns:
            st.error("Solo puedes detener tus propias tareas (o tener el rol Admin).")
        elif not auth.check_any_role(auth.ROLES_OPERATE):
            st.error("Detener una tarea requiere rol App.Operator o App.Admin.")
        else:
            tasks.stop_task(task_id)
            st.rerun()


@st.dialog("Detener flujo")
def _confirm_stop_workflow(run_id: str, workflow_name: str) -> None:
    st.warning(
        f"Vas a detener el flujo **{workflow_name}** en curso. "
        "El bloque que esté ejecutándose se interrumpe y los bloques pendientes no se lanzarán."
    )
    c1, c2 = st.columns(2)
    if c1.button("Cancelar", key=f"cancel_wfstop_{run_id}", width="stretch"):
        st.rerun()
    if c2.button("Detener definitivamente", key=f"confirm_wfstop_{run_id}", type="primary", width="stretch"):
        current = auth.get_current_user()
        run = workflow_engine.get_run(run_id)
        owns = run is not None and (auth.has_role(auth.ROLE_ADMIN) or run.triggered_by == current)
        if not owns:
            st.error("Solo puedes detener tus propios flujos (o tener el rol Admin).")
        elif not auth.check_any_role(auth.ROLES_OPERATE):
            st.error("Detener un flujo requiere rol App.Operator o App.Admin.")
        else:
            workflow_engine.stop_workflow(run_id)
            st.rerun()


defaults = adapter.config_defaults()
bc_default_output = defaults.get("business_central", {}).get("output_dir", "./exports")
factorial_default_output = defaults.get("factorial", {}).get("output_dir", "./exports_factorial")

bc_tables = adapter.list_bc_tables()
factorial_tables = adapter.list_factorial_tables()


# --------------------------------------------------------------------------------------
# Inicio — resumen de estado + accesos directos a las páginas más usadas.
# --------------------------------------------------------------------------------------
def page_home() -> None:
    st.title("Taidy — Panel de datos")
    st.caption("Extracción y carga al datalake de Business Central y Factorial HR, sin depender de la terminal.")

    running_tasks = [t for t in tasks.list_tasks() if t.status == "running"]
    running_workflows = [r for r in workflow_engine.list_runs() if r.status == "running"]
    active_schedules = [s for s in sched_module.list_schedules() if s.get("enabled", True)]
    recent_history = history.get_history(limit=5)

    m1, m2, m3 = st.columns(3)
    m1.metric("Tareas en curso", len(running_tasks) + len(running_workflows))
    m2.metric("Tareas programadas activas", len(active_schedules))
    failed_recent = sum(1 for e in recent_history if not e["ok"] and e.get("status") != "stopped")
    m3.metric("Errores en las últimas 5 ejecuciones", failed_recent)

    st.divider()
    st.markdown("#### Accesos directos")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.page_link(PAGE_BC_SYNC, label="Business Central · Sync", icon="🔁")
        st.page_link(PAGE_BC_EXTRACT, label="Business Central · Extraer", icon="⬇️")
        st.page_link(PAGE_BC_UPLOAD, label="Business Central · Subir", icon="⬆️")
    with c2:
        st.page_link(PAGE_FAC_SYNC, label="Factorial · Sync", icon="🔁")
        st.page_link(PAGE_FAC_EXTRACT, label="Factorial · Extraer", icon="⬇️")
        st.page_link(PAGE_FAC_UPLOAD, label="Factorial · Subir", icon="⬆️")
    with c3:
        st.page_link(PAGE_PIPELINES, label="Fabric · Pipelines", icon="🧵")
        st.page_link(PAGE_WORKFLOWS, label="Flujos", icon="🧩")
        st.page_link(PAGE_SCHEDULES, label="Tareas programadas", icon="📅")

    st.divider()
    st.markdown("#### Actividad reciente")
    st.page_link(PAGE_RUNNING, label="Ver tareas en curso", icon="🔵")
    st.page_link(PAGE_HISTORY, label="Ver historial completo", icon="📈")
    if not recent_history:
        st.info("Todavía no se ha ejecutado ninguna tarea.")
    for entry in recent_history:
        icon = "✅" if entry["ok"] else ("⏹️" if entry.get("status") == "stopped" else "❌")
        st.markdown(
            f"{icon} **{SCHEDULABLE_LABELS.get(entry['action'], entry['action'])}** — "
            f"{entry['source']} — {entry['finished_at']}"
        )


# --------------------------------------------------------------------------------------
# Tareas en curso — Reader+ can view; stop is Operator+ AND (own task OR Admin)
#
# The task list lives in its own st.fragment so the periodic refresh (ND-06) reruns
# only this portion of the page, never the whole app — no more blocking time.sleep().
# Interacting with a widget inside the fragment (e.g. the "Ver" toggle) also now only
# reruns the fragment, not the entire page.
# --------------------------------------------------------------------------------------
def _render_running_tasks() -> None:
    current_user = auth.get_current_user()
    is_admin = auth.has_role(auth.ROLE_ADMIN)

    all_tasks = tasks.list_tasks()
    if not all_tasks:
        st.info("No hay tareas registradas en esta sesión del servidor.")
        return

    actions_present = sorted({t.action for t in all_tasks})
    users_present = sorted({t.triggered_by for t in all_tasks})
    statuses_present = sorted({t.status for t in all_tasks})

    f1, f2, f3 = st.columns([2, 2, 2])
    f_actions = f1.multiselect(
        "Acción", actions_present, format_func=lambda a: ACTION_LABELS.get(a, a), key="running_f_action"
    )
    f_users = f2.multiselect("Usuario", users_present, key="running_f_user")
    f_statuses = f3.multiselect(
        "Estado",
        statuses_present,
        format_func=lambda s: _TASK_STATUS_BADGE.get(s, (None, None, s))[2],
        key="running_f_status",
    )
    f4, f5 = st.columns(2)
    date_from = f4.date_input("Desde", value=None, key="running_f_from")
    date_to = f5.date_input("Hasta", value=None, key="running_f_to")

    def _matches(t) -> bool:
        if f_actions and t.action not in f_actions:
            return False
        if f_users and t.triggered_by not in f_users:
            return False
        if f_statuses and t.status not in f_statuses:
            return False
        if date_from or date_to:
            started_date = datetime.fromisoformat(t.started_at).date()
            if date_from and started_date < date_from:
                return False
            if date_to and started_date > date_to:
                return False
        return True

    filtered_tasks = [t for t in all_tasks if _matches(t)]
    st.caption(f"Mostrando {len(filtered_tasks)} de {len(all_tasks)} tareas.")
    if not filtered_tasks:
        st.info("Ninguna tarea coincide con los filtros actuales.")
    for t in filtered_tasks:
        cols = st.columns([3, 2, 2, 1, 1])
        cols[0].markdown(f"**{ACTION_LABELS.get(t.action, t.action)}**  \n👤 {t.triggered_by}")
        with cols[1]:
            _status_badge(t.status)
        step_info = ""
        if len(t.step_labels) > 1:
            step_info = f"  \npaso {min(t.current_step + 1, len(t.step_labels))}/{len(t.step_labels)}: {t.step_labels[t.current_step]}"
        cols[2].markdown(f"⏱️ {t.duration_seconds():.0f}s{step_info}")

        can_stop = t.status == "running" and (is_admin or t.triggered_by == current_user)
        if cols[3].button("Detener", key=f"stop_{t.id}", disabled=not can_stop, width="stretch"):
            _confirm_stop_task(t.id, ACTION_LABELS.get(t.action, t.action))

        with cols[4]:
            expand = st.toggle("Ver", key=f"toggle_{t.id}", width="stretch")
        if expand:
            _render_table_statuses(t.table_statuses())
            full_log = t.log()
            lines = full_log.splitlines()
            if not lines:
                st.code("(sin salida todavía)", language="log")
            else:
                st.caption(f"Últimas {min(10, len(lines))} líneas de {len(lines)}")
                st.code("\n".join(lines[-10:]), language="log")
                if len(lines) > 10:
                    with st.expander("Ver log completo"):
                        st.code(full_log, language="log")
        st.divider()


def page_running() -> None:
    st.subheader("Tareas en curso")
    top_cols = st.columns([1, 1, 3])
    refresh_clicked = top_cols[0].button("Actualizar ahora", key="running_refresh", width="stretch")
    auto_refresh = top_cols[1].checkbox("Auto (cada 5 s)", key="running_autorefresh")

    if refresh_clicked:
        st.rerun()

    # run_every must be chosen before wrapping: passing None disables the timed
    # rerun, so unchecking "Auto" stops the ticking without a blocking sleep either way.
    st.fragment(run_every=5 if auto_refresh else None)(_render_running_tasks)()


# --------------------------------------------------------------------------------------
# BC · Extraer
# --------------------------------------------------------------------------------------
def page_bc_extract() -> None:
    st.subheader("Extraer tablas de Business Central")
    is_admin = auth.check_role(auth.ROLE_ADMIN)
    with st.form("form_bc_extract"):
        col1, col2 = st.columns(2)
        with col1:
            f_tables = st.multiselect("Tablas (vacío = todas)", bc_tables, key="bc_ex_tables")
            mode = st.selectbox("Modo", ["incremental", "full"], key="bc_ex_mode")
            parallel = st.number_input("Hilos en paralelo", min_value=1, value=1, step=1, key="bc_ex_parallel")
        with col2:
            output_dir = st.text_input("Directorio de salida", value=bc_default_output, key="bc_ex_outdir")
            page_size = st.number_input(
                "Tamaño de página (0 = usar el de config.json)", min_value=0, value=0, step=100, key="bc_ex_pagesize"
            )
            checkpoint_path = st.text_input(
                "Ruta de checkpoints en OneLake (vacío = por defecto)", key="bc_ex_ckpt"
            )
        dry_run = st.checkbox("Modo simulación (no llama a la API, no descarga nada)", key="bc_ex_dry")
        reset_watermarks = st.checkbox(
            "Resetear checkpoints antes de extraer",
            key="bc_ex_reset",
            disabled=not is_admin,
            help="Requiere el rol App.Admin." if not is_admin else "Borra el checkpoint de incrementalidad antes de extraer.",
        )
        verbose = st.checkbox("Log detallado (verbose)", key="bc_ex_verbose")
        submitted = st.form_submit_button("Ejecutar extracción BC")

    if submitted:
        if reset_watermarks and not auth.check_role(auth.ROLE_ADMIN):
            st.error("Resetear checkpoints es una operación crítica: requiere el rol App.Admin.")
        else:
            params = dict(
                tables=f_tables or None,
                output_dir=output_dir.strip(),
                page_size=page_size or None,
                mode=mode,
                parallel=int(parallel),
                dry_run=dry_run,
                reset_watermarks=reset_watermarks,
                checkpoint_path=checkpoint_path.strip(),
                verbose=verbose,
            )
            _launch_and_report("extract_bc", params)


# --------------------------------------------------------------------------------------
# BC · Subir
# --------------------------------------------------------------------------------------
def page_bc_upload() -> None:
    st.subheader("Subir CSVs de Business Central a Fabric OneLake")
    with st.form("form_bc_upload"):
        output_dir = st.text_input("Directorio con los CSV", value=bc_default_output, key="bc_up_outdir")
        dry_run = st.checkbox("Modo simulación (solo lista los ficheros, no sube nada)", key="bc_up_dry")
        skip_existing = st.checkbox("Omitir ficheros ya subidos", key="bc_up_skip")
        verbose = st.checkbox("Log detallado", key="bc_up_verbose")
        submitted = st.form_submit_button("Ejecutar subida BC")

    if submitted:
        if not output_dir.strip():
            st.error("Indica un directorio de salida.")
        else:
            params = dict(
                output_dir=output_dir.strip(), dry_run=dry_run, skip_existing=skip_existing, verbose=verbose
            )
            _launch_and_report("upload_bc", params)


# --------------------------------------------------------------------------------------
# BC · Sync
# --------------------------------------------------------------------------------------
def page_bc_sync() -> None:
    st.subheader("Extraer + subir Business Central en un paso")
    with st.form("form_bc_sync"):
        f_tables = st.multiselect("Tablas (vacío = todas)", bc_tables, key="bc_sy_tables")
        mode = st.selectbox("Modo", ["incremental", "full"], key="bc_sy_mode")
        parallel = st.number_input("Hilos en paralelo", min_value=1, value=1, step=1, key="bc_sy_parallel")
        output_dir = st.text_input("Directorio de salida", value=bc_default_output, key="bc_sy_outdir")
        dry_run = st.checkbox("Modo simulación (no hace cambios reales)", key="bc_sy_dry")
        skip_existing = st.checkbox("Omitir ficheros ya subidos al subir", key="bc_sy_skip")
        verbose = st.checkbox("Log detallado", key="bc_sy_verbose")
        submitted = st.form_submit_button("Ejecutar sync BC")

    if submitted:
        params = dict(
            tables=f_tables or None,
            output_dir=output_dir.strip(),
            mode=mode,
            parallel=int(parallel),
            dry_run=dry_run,
            skip_existing=skip_existing,
            verbose=verbose,
        )
        _launch_and_report("sync_bc", params)


# --------------------------------------------------------------------------------------
# Factorial · Extraer
# --------------------------------------------------------------------------------------
def page_fac_extract() -> None:
    st.subheader("Extraer tablas de Factorial HR")
    is_admin = auth.check_role(auth.ROLE_ADMIN)
    with st.form("form_fac_extract"):
        col1, col2 = st.columns(2)
        with col1:
            start_on = st.date_input("Desde", value=date(2025, 1, 1), key="fac_ex_start")
            end_on = st.date_input("Hasta", value=date.today(), key="fac_ex_end")
            employee_status = st.selectbox("Empleados", ["active", "inactive", "all"], key="fac_ex_empstatus")
            employees_raw = st.text_input(
                "IDs de empleados concretos (coma-separados, vacío = auto-descubrir)", key="fac_ex_emp"
            )
        with col2:
            f_tables = st.multiselect("Tablas (vacío = todas)", factorial_tables, key="fac_ex_tables")
            mode = st.selectbox("Modo", ["full", "incremental"], key="fac_ex_mode")
            parallel = st.number_input("Hilos en paralelo", min_value=1, value=5, step=1, key="fac_ex_parallel")
            output_dir = st.text_input("Directorio de salida", value=factorial_default_output, key="fac_ex_outdir")
        reset_all = st.checkbox(
            "Resetear TODOS los checkpoints antes de extraer",
            key="fac_ex_resetall",
            disabled=not is_admin,
            help="Requiere el rol App.Admin." if not is_admin else "Borra todos los checkpoints antes de extraer.",
        )
        dry_run = st.checkbox("Modo simulación (no llama a la API, no descarga nada)", key="fac_ex_dry")
        verbose = st.checkbox("Log detallado", key="fac_ex_verbose")
        submitted = st.form_submit_button("Ejecutar extracción Factorial")

    if submitted:
        employees, emp_error = _parse_employee_ids(employees_raw)
        if start_on > end_on:
            st.error("'Desde' no puede ser posterior a 'Hasta'.")
        elif emp_error:
            st.error(emp_error)
        elif reset_all and not auth.check_role(auth.ROLE_ADMIN):
            st.error("Resetear checkpoints es una operación crítica: requiere el rol App.Admin.")
        else:
            params = dict(
                start_on=start_on.isoformat(),
                end_on=end_on.isoformat(),
                employees=employees,
                employee_status=employee_status,
                tables=f_tables or None,
                output_dir=output_dir.strip(),
                mode=mode,
                parallel=int(parallel),
                reset_all_checkpoints=reset_all,
                dry_run=dry_run,
                verbose=verbose,
            )
            _launch_and_report("extract_factorial", params)


# --------------------------------------------------------------------------------------
# Factorial · Subir
# --------------------------------------------------------------------------------------
def page_fac_upload() -> None:
    st.subheader("Subir CSVs de Factorial a Fabric OneLake")
    with st.form("form_fac_upload"):
        output_dir = st.text_input("Directorio con los CSV", value=factorial_default_output, key="fac_up_outdir")
        f_tables = st.multiselect("Tablas (vacío = todas)", factorial_tables, key="fac_up_tables")
        dry_run = st.checkbox("Modo simulación (solo lista los ficheros, no sube nada)", key="fac_up_dry")
        skip_existing = st.checkbox("Omitir ficheros ya subidos", key="fac_up_skip")
        verbose = st.checkbox("Log detallado", key="fac_up_verbose")
        submitted = st.form_submit_button("Ejecutar subida Factorial")

    if submitted:
        if not output_dir.strip():
            st.error("Indica un directorio de salida.")
        else:
            params = dict(
                output_dir=output_dir.strip(),
                tables=f_tables or None,
                dry_run=dry_run,
                skip_existing=skip_existing,
                verbose=verbose,
            )
            _launch_and_report("upload_factorial", params)


# --------------------------------------------------------------------------------------
# Factorial · Sync
# --------------------------------------------------------------------------------------
def page_fac_sync() -> None:
    st.subheader("Extraer + subir Factorial en un paso")
    with st.form("form_fac_sync"):
        col1, col2 = st.columns(2)
        with col1:
            start_on = st.date_input("Desde", value=date(2025, 1, 1), key="fac_sy_start")
            end_on = st.date_input("Hasta", value=date.today(), key="fac_sy_end")
            employee_status = st.selectbox("Empleados", ["active", "inactive", "all"], key="fac_sy_empstatus")
        with col2:
            f_tables = st.multiselect("Tablas (vacío = todas)", factorial_tables, key="fac_sy_tables")
            mode = st.selectbox("Modo", ["incremental", "full"], key="fac_sy_mode")
            parallel = st.number_input("Hilos en paralelo", min_value=1, value=5, step=1, key="fac_sy_parallel")
        output_dir = st.text_input("Directorio de salida", value=factorial_default_output, key="fac_sy_outdir")
        dry_run = st.checkbox("Modo simulación (no hace cambios reales)", key="fac_sy_dry")
        skip_existing = st.checkbox("Omitir ficheros ya subidos al subir", key="fac_sy_skip")
        verbose = st.checkbox("Log detallado", key="fac_sy_verbose")
        submitted = st.form_submit_button("Ejecutar sync Factorial")

    if submitted:
        if start_on > end_on:
            st.error("'Desde' no puede ser posterior a 'Hasta'.")
        else:
            params = dict(
                start_on=start_on.isoformat(),
                end_on=end_on.isoformat(),
                employee_status=employee_status,
                tables=f_tables or None,
                output_dir=output_dir.strip(),
                mode=mode,
                parallel=int(parallel),
                dry_run=dry_run,
                skip_existing=skip_existing,
                verbose=verbose,
            )
            _launch_and_report("sync_factorial", params)


# --------------------------------------------------------------------------------------
# Fabric · Pipelines — lanza y sigue en vivo un pipeline de Fabric Data Factory
# --------------------------------------------------------------------------------------
def page_pipelines() -> None:
    st.subheader("Ejecutar un pipeline de Fabric Data Factory")
    fabric_pipelines = adapter.list_fabric_pipelines()
    if not fabric_pipelines:
        st.info(
            "No hay pipelines configurados todavía. Añade entradas en la sección "
            "`fabric_pipelines.pipelines` de `config.json` (nombre + item_id de Fabric)."
        )
    else:
        with st.form("form_run_pipeline"):
            pipeline_name = st.selectbox("Pipeline", fabric_pipelines, key="pipe_name")
            wait = st.checkbox(
                "Esperar y seguir el estado en vivo (recomendado)", value=True, key="pipe_wait"
            )
            poll_seconds = st.number_input(
                "Cada cuántos segundos consultar el estado", min_value=5, value=15, step=5, key="pipe_poll"
            )
            verbose = st.checkbox("Log detallado", key="pipe_verbose")
            submitted = st.form_submit_button("Lanzar pipeline")

        if submitted:
            params = dict(
                pipeline=pipeline_name,
                wait=wait,
                poll_seconds=int(poll_seconds),
                verbose=verbose,
            )
            _launch_and_report("run_pipeline", params)
        st.caption(
            "Detener el seguimiento aquí NO cancela el pipeline en Fabric — solo deja de consultarlo. "
            "Para cancelarlo de verdad, hazlo desde el propio portal de Fabric."
        )


# --------------------------------------------------------------------------------------
# Flujos — DAG de bloques (secuencial + paralelo). Diseñar/borrar: Admin.
# Lanzar/detener: Operator+Admin (solo tareas propias, salvo Admin). Consultar: todos.
# --------------------------------------------------------------------------------------
def page_workflows() -> None:
    st.subheader("Flujos")
    st.caption(
        "Compón un flujo añadiendo bloques uno a uno. Un bloque sin 'depende de' se lanza en paralelo "
        "con los demás bloques sin dependencias; uno con dependencias espera a que TODAS terminen "
        "antes de decidir si se lanza (según lo que elijas para él)."
    )

    is_workflow_admin = auth.check_role(auth.ROLE_ADMIN)
    fabric_pipelines_wf = adapter.list_fabric_pipelines()

    if not is_workflow_admin:
        st.info("Diseñar o borrar flujos requiere el rol App.Admin. Puedes consultarlos y lanzarlos abajo.")
    else:
        st.markdown("#### Diseñar un flujo nuevo")
        if "wf_draft_steps" not in st.session_state:
            st.session_state["wf_draft_steps"] = []
        draft_steps = st.session_state["wf_draft_steps"]

        wf_action = st.selectbox(
            "Acción del nuevo bloque",
            list(ACTION_LABELS.keys()),
            format_func=lambda k: ACTION_LABELS[k],
            key="wf_new_action",
        )
        existing_labels = [s["label"] for s in draft_steps]

        with st.form("form_wf_add_step"):
            step_label = st.text_input("Etiqueta del bloque", value=ACTION_LABELS[wf_action], key="wf_step_label")
            step_params: dict = {}

            with st.expander("Parámetros de la acción", expanded=True):
                if wf_action in ("extract_bc", "sync_bc"):
                    step_params["tables"] = (
                        st.multiselect("Tablas (vacío = todas)", bc_tables, key="wf_bc_tables") or None
                    )
                    step_params["mode"] = st.selectbox("Modo", ["incremental", "full"], key="wf_bc_mode")
                    step_params["parallel"] = int(
                        st.number_input("Hilos", min_value=1, value=1, key="wf_bc_parallel")
                    )
                    if wf_action == "sync_bc":
                        step_params["output_dir"] = bc_default_output
                        step_params["skip_existing"] = st.checkbox("Omitir ya subidos", key="wf_bc_skip")

                if wf_action == "upload_bc":
                    step_params["output_dir"] = st.text_input(
                        "Directorio con los CSV", value=bc_default_output, key="wf_bc_up_dir"
                    )
                    step_params["skip_existing"] = st.checkbox("Omitir ya subidos", key="wf_bc_up_skip")

                if wf_action in ("extract_factorial", "sync_factorial"):
                    step_params["start_on"] = st.date_input(
                        "Desde", value=date(2025, 1, 1), key="wf_fac_start"
                    ).isoformat()
                    step_params["end_on"] = st.date_input("Hasta", value=date.today(), key="wf_fac_end").isoformat()
                    step_params["tables"] = (
                        st.multiselect("Tablas (vacío = todas)", factorial_tables, key="wf_fac_tables") or None
                    )
                    step_params["mode"] = st.selectbox("Modo", ["full", "incremental"], key="wf_fac_mode")
                    step_params["parallel"] = int(
                        st.number_input("Hilos", min_value=1, value=5, key="wf_fac_parallel")
                    )
                    if wf_action == "sync_factorial":
                        step_params["output_dir"] = factorial_default_output
                        step_params["skip_existing"] = st.checkbox("Omitir ya subidos", key="wf_fac_skip")

                if wf_action == "upload_factorial":
                    step_params["output_dir"] = st.text_input(
                        "Directorio con los CSV", value=factorial_default_output, key="wf_fac_up_dir"
                    )
                    step_params["tables"] = (
                        st.multiselect("Tablas (vacío = todas)", factorial_tables, key="wf_fac_up_tables") or None
                    )
                    step_params["skip_existing"] = st.checkbox("Omitir ya subidos", key="wf_fac_up_skip")

                if wf_action == "run_pipeline":
                    if fabric_pipelines_wf:
                        step_params["pipeline"] = st.selectbox("Pipeline", fabric_pipelines_wf, key="wf_pipe_name")
                    else:
                        st.warning("No hay pipelines configurados en `config.json` todavía.")
                    step_params["wait"] = True
                    step_params["poll_seconds"] = int(
                        st.number_input(
                            "Cada cuántos segundos consultar el estado", min_value=5, value=15, key="wf_pipe_poll"
                        )
                    )

            with st.expander("Dependencias y orden de ejecución"):
                st.caption("Déjalo vacío para que el bloque se lance en paralelo desde el principio del flujo.")
                depends_on_labels = st.multiselect("Depende de", existing_labels, key="wf_step_deps")
                trigger_rule = workflows.TRIGGER_ALL_SUCCESS
                if depends_on_labels:
                    trigger_rule = st.selectbox(
                        "¿Cuándo lanzar este bloque?",
                        list(workflows.TRIGGER_LABELS.keys()),
                        format_func=lambda k: workflows.TRIGGER_LABELS[k],
                        key="wf_step_trigger",
                    )

            add_submitted = st.form_submit_button("Añadir bloque al flujo")

        if add_submitted:
            label = step_label.strip()
            label_to_id = {s["label"]: s["id"] for s in draft_steps}
            if not label:
                st.error("Ponle una etiqueta al bloque.")
            elif label in existing_labels:
                st.error(f"Ya hay un bloque con la etiqueta '{label}' en este borrador.")
            elif wf_action == "run_pipeline" and not step_params.get("pipeline"):
                st.error("No hay pipelines configurados; no se puede añadir este bloque.")
            else:
                draft_steps.append(
                    {
                        "id": f"step_{uuid.uuid4().hex[:8]}",
                        "label": label,
                        "action": wf_action,
                        "params": step_params,
                        "depends_on": [label_to_id[lbl] for lbl in depends_on_labels],
                        "trigger_rule": trigger_rule,
                    }
                )
                st.rerun()

        if draft_steps:
            st.markdown("**Bloques del borrador actual:**")
            for i, s in enumerate(draft_steps):
                deps_labels = [d["label"] for d in draft_steps if d["id"] in s["depends_on"]]
                cols = st.columns([4, 1])
                cols[0].write(
                    f"**{s['label']}** ({ACTION_LABELS.get(s['action'], s['action'])})"
                    + (f" — depende de: {', '.join(deps_labels)}" if deps_labels else " — sin dependencias")
                )
                if cols[1].button("Quitar", key=f"wf_remove_{s['id']}", width="stretch"):
                    draft_steps.pop(i)
                    st.rerun()

            st.graphviz_chart(workflows.to_dot(draft_steps), width="stretch")

            with st.form("form_wf_save"):
                wf_name = st.text_input("Nombre del flujo", key="wf_save_name")
                save_submitted = st.form_submit_button("Guardar flujo")
            if save_submitted:
                try:
                    workflows.create_workflow(wf_name, draft_steps)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.success(f"Flujo '{wf_name}' guardado.")
                    st.session_state["wf_draft_steps"] = []
                    st.rerun()

            if st.button("Descartar borrador", key="wf_discard"):
                st.session_state["wf_draft_steps"] = []
                st.rerun()

    st.markdown("#### Flujos guardados")
    saved_workflows = workflows.list_workflows()
    if not saved_workflows:
        st.info("Todavía no hay flujos guardados.")
    for wf in saved_workflows:
        with st.expander(f"{wf['name']} ({len(wf['steps'])} bloque(s))"):
            st.graphviz_chart(workflows.to_dot(wf["steps"]), width="stretch")
            wf_cols = st.columns([1, 1])
            if wf_cols[0].button("Lanzar flujo", key=f"wf_launch_{wf['id']}", width="stretch"):
                if not auth.check_any_role(auth.ROLES_OPERATE):
                    st.error("Lanzar un flujo requiere rol App.Operator o App.Admin.")
                else:
                    try:
                        wf_run = workflow_engine.start_workflow(wf["id"], auth.get_current_user())
                    except (RuntimeError, ValueError) as exc:
                        st.error(str(exc))
                    else:
                        st.success(f"Flujo lanzado (`{wf_run.id[:8]}`). Míralo abajo en 'Flujos en curso'.")
            if is_workflow_admin and wf_cols[1].button(
                "Borrar flujo", key=f"wf_delete_{wf['id']}", width="stretch"
            ):
                _confirm_delete_workflow(wf["id"], wf["name"])

    st.markdown("#### Flujos en curso / recientes")
    wf_runs = workflow_engine.list_runs()
    if not wf_runs:
        st.info("No hay ejecuciones de flujos en esta sesión del servidor.")
    for run in wf_runs:
        wf_run_cols = st.columns([3, 1])
        wf_run_cols[0].markdown(
            f"**{run.workflow_name}**  \n👤 {run.triggered_by} — ⏱️ {run.duration_seconds():.0f}s"
        )
        with wf_run_cols[1]:
            _status_badge(run.status)
        can_stop_wf = run.status == "running" and (
            auth.has_role(auth.ROLE_ADMIN) or run.triggered_by == auth.get_current_user()
        )
        if run.status == "running":
            if st.button("Detener flujo", key=f"wf_stop_{run.id}", disabled=not can_stop_wf):
                _confirm_stop_workflow(run.id, run.workflow_name)
        steps_for_diagram = [
            {
                "id": s.id,
                "label": s.label,
                "action": s.action,
                "depends_on": s.depends_on,
                "trigger_rule": s.trigger_rule,
            }
            for s in run.steps.values()
        ]
        st.graphviz_chart(
            workflows.to_dot(steps_for_diagram, step_status=run.step_status_map()), width="stretch"
        )
        st.divider()


# --------------------------------------------------------------------------------------
# Tareas programadas — visible a todos; crear/pausar/borrar solo Admin
# --------------------------------------------------------------------------------------
def page_schedules() -> None:
    st.subheader("Tareas programadas")
    st.caption(
        "Se ejecutan en segundo plano mientras este proceso de Streamlit siga vivo. "
        "En el despliegue en Linux, arráncalo bajo un supervisor de procesos (systemd, Docker con "
        "restart policy, etc.) para que no dependa de dejar una terminal abierta."
    )

    is_schedule_admin = auth.check_role(auth.ROLE_ADMIN)
    schedulable_labels = SCHEDULABLE_LABELS

    if not is_schedule_admin:
        st.info("Crear, pausar o borrar tareas programadas requiere el rol App.Admin. Puedes consultarlas abajo.")
    else:
        st.markdown("#### Nueva tarea")
        action_key = st.selectbox(
            "Acción a programar",
            list(schedulable_labels.keys()),
            format_func=lambda k: schedulable_labels[k],
            key="sched_new_action",
        )

        with st.form("form_new_schedule"):
            name = st.text_input("Nombre de la tarea", value=schedulable_labels[action_key], key="sched_new_name")
            schedule_params: dict = {}

            if action_key == "run_workflow":
                available_workflows = workflows.list_workflows()
                if available_workflows:
                    wf_choice = st.selectbox(
                        "Flujo",
                        available_workflows,
                        format_func=lambda w: w["name"],
                        key="sched_workflow_choice",
                    )
                    schedule_params["workflow_id"] = wf_choice["id"]
                else:
                    st.warning("Todavía no hay flujos guardados en 'Flujos'.")

            if action_key in ("extract_bc", "sync_bc"):
                schedule_params["mode"] = st.selectbox("Modo", ["incremental", "full"], key="sched_bc_mode")
                schedule_params["parallel"] = int(
                    st.number_input("Hilos", min_value=1, value=1, key="sched_bc_parallel")
                )

            if action_key in ("extract_factorial", "sync_factorial"):
                schedule_params["start_on"] = st.date_input(
                    "Fecha de inicio (solo se usa si aún no hay checkpoint)",
                    value=date(2025, 1, 1),
                    key="sched_fac_start",
                ).isoformat()
                schedule_params["employee_status"] = st.selectbox(
                    "Empleados", ["active", "inactive", "all"], key="sched_fac_empstatus"
                )
                schedule_params["mode"] = st.selectbox("Modo", ["incremental", "full"], key="sched_fac_mode")
                schedule_params["parallel"] = int(
                    st.number_input("Hilos", min_value=1, value=5, key="sched_fac_parallel")
                )
                st.caption("'Hasta' se calcula automáticamente como la fecha de hoy en cada ejecución.")

            if action_key in ("upload_bc", "upload_factorial", "sync_factorial", "sync_bc"):
                schedule_params["skip_existing"] = st.checkbox("Omitir ficheros ya subidos", key="sched_skip")

            if action_key == "run_pipeline":
                fabric_pipelines_sched = adapter.list_fabric_pipelines()
                if fabric_pipelines_sched:
                    schedule_params["pipeline"] = st.selectbox(
                        "Pipeline", fabric_pipelines_sched, key="sched_pipeline_name"
                    )
                    schedule_params["wait"] = True
                    schedule_params["poll_seconds"] = int(
                        st.number_input(
                            "Cada cuántos segundos consultar el estado",
                            min_value=5,
                            value=15,
                            step=5,
                            key="sched_pipeline_poll",
                        )
                    )
                else:
                    st.warning("No hay pipelines configurados en `config.json` todavía.")

            st.markdown("**Frecuencia**")
            trigger_kind = st.radio("Tipo", ["Intervalo", "Cron"], key="sched_trigger_kind", horizontal=True)
            hours = minutes = 0
            cron_expr = ""
            if trigger_kind == "Intervalo":
                hours = st.number_input("Cada cuántas horas", min_value=0, value=24, key="sched_hours")
                minutes = st.number_input("Y cuántos minutos", min_value=0, value=0, key="sched_minutes")
            else:
                cron_expr = st.text_input(
                    "Expresión cron (minuto hora día mes día-semana)",
                    value="0 6 * * *",
                    key="sched_cron",
                    help="Ejemplo: '0 6 * * *' = todos los días a las 06:00",
                )

            submitted = st.form_submit_button("Crear tarea programada")

        if submitted:
            if not auth.check_role(auth.ROLE_ADMIN):
                st.error("Requiere el rol App.Admin.")
            elif not name.strip():
                st.error("Indica un nombre para la tarea.")
            elif trigger_kind == "Intervalo" and hours <= 0 and minutes <= 0:
                st.error("El intervalo debe ser mayor que 0.")
            else:
                if trigger_kind == "Intervalo":
                    trigger, trigger_args = "interval", {"hours": int(hours), "minutes": int(minutes)}
                else:
                    trigger, trigger_args = "cron", {"expr": cron_expr.strip()}
                try:
                    sched_module.add_schedule(
                        scheduler,
                        name=name.strip(),
                        action=action_key,
                        params=schedule_params,
                        trigger=trigger,
                        trigger_args=trigger_args,
                    )
                except Exception as exc:
                    st.error(f"No se pudo crear la tarea: {exc}")
                else:
                    st.success(f"Tarea '{name}' creada.")
                    st.rerun()

    st.markdown("#### Tareas existentes")
    schedules = sched_module.list_schedules()
    if not schedules:
        st.info("No hay tareas programadas todavía.")
    for s in schedules:
        cols = st.columns([3, 2, 3, 1, 1])
        cols[0].write(f"**{s['name']}**  \n{schedulable_labels.get(s['action'], s['action'])}")
        with cols[1]:
            if s.get("enabled", True):
                st.badge("Activa", icon="🟢", color="green")
            else:
                st.badge("Pausada", icon="⏸️", color="gray")
        if s["trigger"] == "cron":
            freq = s["trigger_args"].get("expr", "")
        else:
            ta = s["trigger_args"]
            freq = f"cada {ta.get('hours', 0)}h {ta.get('minutes', 0)}min"
        cols[2].write(freq)
        if is_schedule_admin:
            if cols[3].button(
                "Pausar" if s.get("enabled", True) else "Reanudar", key=f"toggle_{s['id']}", width="stretch"
            ):
                if not auth.check_role(auth.ROLE_ADMIN):
                    st.error("Requiere el rol App.Admin.")
                else:
                    sched_module.set_schedule_enabled(scheduler, s["id"], not s.get("enabled", True))
                    st.rerun()
            if cols[4].button("Borrar", key=f"del_{s['id']}", width="stretch"):
                _confirm_delete_schedule(s["id"], s["name"])


# --------------------------------------------------------------------------------------
# Historial — visible a todos los roles autenticados
# --------------------------------------------------------------------------------------
def page_history() -> None:
    st.subheader("Historial de ejecuciones")
    if st.button("Actualizar", key="history_refresh"):
        st.rerun()
    run_history = history.get_history(limit=200)
    if not run_history:
        st.info("Todavía no se ha ejecutado ninguna tarea.")
        return

    actions_present = sorted({e["action"] for e in run_history})
    sources_present = sorted({e["source"] for e in run_history})

    f1, f2, f3 = st.columns([2, 2, 2])
    f_actions = f1.multiselect(
        "Acción", actions_present, format_func=lambda a: SCHEDULABLE_LABELS.get(a, a), key="hist_f_action"
    )
    f_sources = f2.multiselect("Usuario / origen", sources_present, key="hist_f_source")
    f_result = f3.selectbox("Resultado", ["Todos", "Correcto", "Error", "Detenida"], key="hist_f_result")
    f4, f5 = st.columns(2)
    date_from = f4.date_input("Desde", value=None, key="hist_f_from")
    date_to = f5.date_input("Hasta", value=None, key="hist_f_to")

    def _matches(e: dict) -> bool:
        if f_actions and e["action"] not in f_actions:
            return False
        if f_sources and e["source"] not in f_sources:
            return False
        if f_result == "Correcto" and not e["ok"]:
            return False
        if f_result == "Error" and (e["ok"] or e.get("status") == "stopped"):
            return False
        if f_result == "Detenida" and e.get("status") != "stopped":
            return False
        if date_from or date_to:
            entry_date = datetime.fromisoformat(e["finished_at"]).date()
            if date_from and entry_date < date_from:
                return False
            if date_to and entry_date > date_to:
                return False
        return True

    filtered = [e for e in run_history if _matches(e)]
    if not filtered:
        st.caption(f"Mostrando 0 de {len(run_history)} ejecuciones.")
        st.info("Ningún resultado con los filtros actuales.")
        return

    page_size = 20
    total_pages = max(1, (len(filtered) + page_size - 1) // page_size)
    cap, cpage = st.columns([3, 1])
    cap.caption(f"Mostrando {len(filtered)} de {len(run_history)} ejecuciones.")
    page_num = cpage.number_input(
        "Página", min_value=1, max_value=total_pages, value=1, step=1, key="hist_page"
    )
    page_num = min(page_num, total_pages)
    start = (page_num - 1) * page_size
    if total_pages > 1:
        st.caption(f"Página {page_num} de {total_pages}")

    for entry in filtered[start : start + page_size]:
        icon = "✅" if entry["ok"] else ("⏹️" if entry.get("status") == "stopped" else "❌")
        duration = f" · {entry['duration_seconds']}s" if entry.get("duration_seconds") is not None else ""
        st.markdown(
            f"{icon} **{SCHEDULABLE_LABELS.get(entry['action'], entry['action'])}** — "
            f"{entry['source']} — {entry['finished_at']}{duration}"
        )
        st.caption(entry["message"])
        if entry.get("log"):
            with st.expander("Ver log"):
                st.code(entry["log"], language="log")
        st.divider()


# --------------------------------------------------------------------------------------
# Auditoría — solo Admin
# --------------------------------------------------------------------------------------
def page_audit() -> None:
    st.subheader("Auditoría de seguridad")
    if not auth.check_role(auth.ROLE_ADMIN):
        st.error("Esta sección requiere el rol App.Admin.")
    else:
        st.caption("Eventos de login, cierre de sesión y accesos denegados. Nunca contiene tokens ni secretos.")
        entries = auth.get_audit_log(200)
        if not entries:
            st.info("Sin eventos registrados todavía.")
        else:
            events_present = sorted({e.get("event", "") for e in entries})
            users_present = sorted({e.get("user", "") for e in entries})
            outcomes_present = sorted({e.get("outcome", "") for e in entries})

            f1, f2, f3 = st.columns([2, 2, 2])
            f_events = f1.multiselect("Evento", events_present, key="audit_f_event")
            f_users = f2.multiselect("Usuario", users_present, key="audit_f_user")
            f_outcomes = f3.multiselect("Resultado", outcomes_present, key="audit_f_outcome")
            f4, f5 = st.columns(2)
            date_from = f4.date_input("Desde", value=None, key="audit_f_from")
            date_to = f5.date_input("Hasta", value=None, key="audit_f_to")

            def _matches(e: dict) -> bool:
                if f_events and e.get("event", "") not in f_events:
                    return False
                if f_users and e.get("user", "") not in f_users:
                    return False
                if f_outcomes and e.get("outcome", "") not in f_outcomes:
                    return False
                if date_from or date_to:
                    ts = e.get("ts", "")
                    if not ts:
                        return False
                    entry_date = datetime.fromisoformat(ts).date()
                    if date_from and entry_date < date_from:
                        return False
                    if date_to and entry_date > date_to:
                        return False
                return True

            filtered = [e for e in entries if _matches(e)]
            st.caption(f"Mostrando {len(filtered)} de {len(entries)} eventos.")
            rows = [
                {
                    "Fecha": e.get("ts", ""),
                    "Evento": e.get("event", ""),
                    "Resultado": e.get("outcome", ""),
                    "Usuario": e.get("user", ""),
                    "Detalle": e.get("detail", ""),
                }
                for e in filtered
            ]
            st.dataframe(rows, width="stretch", hide_index=True)


# --------------------------------------------------------------------------------------
# Usuarios — solo Admin: alta, cambio de rol, reset de contraseña, borrado
# --------------------------------------------------------------------------------------
def page_users() -> None:
    st.subheader("Usuarios")
    if not auth.check_role(auth.ROLE_ADMIN):
        st.error("Esta sección requiere el rol App.Admin.")
    else:
        st.markdown("#### Crear usuario")
        with st.form("form_new_user"):
            new_username = st.text_input("Usuario", key="user_new_username")
            new_password = st.text_input(
                "Contraseña temporal (mín. 8 caracteres)", type="password", key="user_new_password"
            )
            new_role = st.selectbox(
                "Rol", [auth.ROLE_READER, auth.ROLE_OPERATOR, auth.ROLE_ADMIN], key="user_new_role"
            )
            submitted = st.form_submit_button("Crear usuario")
        if submitted:
            if not auth.check_role(auth.ROLE_ADMIN):
                st.error("Requiere el rol App.Admin.")
            else:
                try:
                    users_db.create_user(new_username, new_password, new_role)
                except ValueError as exc:
                    st.error(str(exc))
                else:
                    st.success(
                        f"Usuario '{new_username.strip()}' creado. Deberá cambiar la contraseña en su primer login."
                    )
                    st.rerun()

        st.markdown("#### Usuarios existentes")
        current_user = auth.get_current_user()
        for u in users_db.list_users():
            cols = st.columns([2, 2, 1, 2, 1, 1])
            cols[0].write(f"**{u['username']}**" + ("  \n👤 tú" if u["username"] == current_user else ""))
            role_options = [auth.ROLE_READER, auth.ROLE_OPERATOR, auth.ROLE_ADMIN]
            new_role_value = cols[1].selectbox(
                # Visually collapsed (the row already gives visual context), but the
                # label still names the user so a screen reader announces "Rol de
                # <usuario>", not just "Rol" (audit finding A-04).
                f"Rol de {u['username']}",
                role_options,
                index=role_options.index(u["role"]) if u["role"] in role_options else 0,
                key=f"role_{u['username']}",
                label_visibility="collapsed",
            )
            # Changing the selectbox no longer applies the role by itself (H-04) —
            # it only reveals a "Guardar rol" button, and that opens a confirmation
            # dialog before anything is actually saved.
            if new_role_value != u["role"]:
                if cols[2].button("Guardar rol", key=f"saverole_{u['username']}", width="stretch"):
                    _confirm_change_role(u["username"], u["role"], new_role_value)

            status_bits = []
            if u["must_change_password"]:
                status_bits.append("⏳ pendiente cambio de contraseña")
            if u["locked_until"]:
                status_bits.append("🔒 bloqueado temporalmente")
            cols[3].write(" · ".join(status_bits) or "✅ activo")

            if cols[4].button("Resetear contraseña", key=f"reset_{u['username']}", width="stretch"):
                if not auth.check_role(auth.ROLE_ADMIN):
                    st.error("Requiere el rol App.Admin.")
                else:
                    users_db.force_password_reset(u["username"])
                    st.info(f"'{u['username']}' deberá establecer una contraseña nueva en su próximo login.")

            if u["username"] != current_user:
                if cols[5].button("Borrar", key=f"deluser_{u['username']}", width="stretch"):
                    _confirm_delete_user(u["username"])
            st.divider()


# --------------------------------------------------------------------------------------
# Mi cuenta — cualquier usuario autenticado puede cambiar su propia contraseña
# --------------------------------------------------------------------------------------
def page_account() -> None:
    st.subheader("Mi cuenta")
    st.caption(f"Sesión iniciada como **{auth.get_current_user()}** — rol: {', '.join(auth.get_current_roles())}")
    st.markdown("#### Cambiar mi contraseña")
    auth.render_change_password_form(force=False)


# --------------------------------------------------------------------------------------
# Navegación — menú lateral agrupado por sección (st.navigation / st.Page). Cada página
# de arriba es una función sin argumentos; el rol Admin solo ve la sección extra
# "Administración".
# --------------------------------------------------------------------------------------
PAGE_HOME = st.Page(page_home, title="Inicio", icon="🏠", default=True)
PAGE_BC_EXTRACT = st.Page(page_bc_extract, title="BC · Extraer", icon="⬇️")
PAGE_BC_UPLOAD = st.Page(page_bc_upload, title="BC · Subir", icon="⬆️")
PAGE_BC_SYNC = st.Page(page_bc_sync, title="BC · Sync", icon="🔁")
PAGE_FAC_EXTRACT = st.Page(page_fac_extract, title="Factorial · Extraer", icon="⬇️")
PAGE_FAC_UPLOAD = st.Page(page_fac_upload, title="Factorial · Subir", icon="⬆️")
PAGE_FAC_SYNC = st.Page(page_fac_sync, title="Factorial · Sync", icon="🔁")
PAGE_PIPELINES = st.Page(page_pipelines, title="Fabric · Pipelines", icon="🧵")
PAGE_WORKFLOWS = st.Page(page_workflows, title="Flujos", icon="🧩")
PAGE_SCHEDULES = st.Page(page_schedules, title="Tareas programadas", icon="📅")
PAGE_RUNNING = st.Page(page_running, title="Tareas en curso", icon="🔵")
PAGE_HISTORY = st.Page(page_history, title="Historial", icon="📈")
PAGE_USERS = st.Page(page_users, title="Usuarios", icon="🛡️")
PAGE_AUDIT = st.Page(page_audit, title="Auditoría", icon="🗒️")
PAGE_ACCOUNT = st.Page(page_account, title="Mi cuenta", icon="👤")

with st.sidebar:
    st.markdown("## 🗂️ Taidy")
    st.caption("Panel de datos")

_pages = {
    "Inicio": [PAGE_HOME],
    "Ejecutar": [
        PAGE_BC_EXTRACT,
        PAGE_BC_UPLOAD,
        PAGE_BC_SYNC,
        PAGE_FAC_EXTRACT,
        PAGE_FAC_UPLOAD,
        PAGE_FAC_SYNC,
        PAGE_PIPELINES,
    ],
    "Flujos": [PAGE_WORKFLOWS],
    "Programación": [PAGE_SCHEDULES],
    "Actividad": [PAGE_RUNNING, PAGE_HISTORY],
}
if auth.has_role(auth.ROLE_ADMIN):
    _pages["Administración"] = [PAGE_USERS, PAGE_AUDIT]
_pages["Cuenta"] = [PAGE_ACCOUNT]

nav = st.navigation(_pages)

with st.sidebar:
    st.divider()
    st.markdown(f"**{auth.get_current_user()}**")
    roles = auth.get_current_roles()
    st.caption(", ".join(roles) if roles else "(ninguno)")
    st.button("Cerrar sesión", on_click=auth.do_logout, width="stretch")

nav.run()
