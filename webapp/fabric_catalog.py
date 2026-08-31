# -*- coding: utf-8 -*-
"""
A documentation/context layer over the workspace's own structure -- NOT
another way to run or manage anything already covered by src/fabric_pipelines
(that's orchestration; this is pure annotation).

Fabric/BC/HubSpot/Factorial are the source of truth for *structure* (which
notebooks/pipelines/tables exist): Fabric's discovered live via
FabricPipelineClient.list_items()/list_folders() (plus, per Lakehouse,
list_lakehouse_tables() for its own bronze./gold. tables -- those aren't
Fabric workspace items, so they don't show up in list_items()); BC/HubSpot/
Factorial come from the same static tables.yaml/hubspot_tables.yaml/
factorial_tables.yaml the extraction jobs already read. This module only
stores the human-curated layer on top: descriptions, governance roles, and
typed relationships between items, keyed by each item's stable id so a
rename upstream doesn't orphan the metadata.
"""

from __future__ import annotations

import base64
import json
import re
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from src.fabric_pipelines.semantic_model_tmdl import (
    append_missing_columns,
    build_new_model_parts,
    parse_table_columns,
    set_column_description,
)
from webapp import table_configs
from webapp.state_dir import state_path

_CATALOG_PATH = state_path("fabric_catalog.json", Path(__file__).resolve().parent)
_LOCK = threading.Lock()

RELATIONSHIP_TYPES = {"reads_from", "writes_to", "triggered_by", "generates", "updates"}
CRITICALITY_LEVELS = {"baja", "media", "alta"}
STATUS_VALUES = {"activo", "en_desuso", "deprecado"}

# The four governance roles (DAMA-style) an item's responsables are split
# across -- each is its own free-text name list rather than one generic
# "owners" bucket, so "who decides" (Owner) is never conflated with "who
# just consumes" (Consumer).
DATA_ROLE_FIELDS = ("data_owner", "data_steward", "data_custodian", "data_consumer")

# Matches the icon-key set the frontend's icon picker offers (lucide-react
# components looked up by this key) -- kept as a fixed, small vocabulary
# rather than a free string so a stored key can never point at nothing.
ICON_KEYS = {
    "database",
    "table",
    "file",
    "pipeline",
    "warehouse",
    "cloud",
    "external",
    "manual",
    "folder",
    "chart",
    "boxes",
    "git",
}

_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

# Custom items exist ONLY in this local store -- there's no live upstream
# record to fall back to, so (unlike a real item) their name/type live here
# too, and they're the one kind of entry this module actually lets you
# delete outright rather than just clear the metadata on.
CUSTOM_ID_PREFIX = "custom:"
CUSTOM_FOLDER_PATH = ["Personalizados"]

# BC/HubSpot items aren't discovered live (no per-request API call, unlike
# Fabric) -- they come from the same static tables.yaml/hubspot_tables.yaml
# already used for extraction, so their id is deterministic (prefix + the
# table's own stable `name`), not a random uuid like a custom item's.
BC_ID_PREFIX = "bc:"
HUBSPOT_ID_PREFIX = "hubspot:"
FACTORIAL_ID_PREFIX = "factorial:"
BC_FOLDER_PATH = ["Business Central"]
HUBSPOT_FOLDER_PATH = ["HubSpot"]
FACTORIAL_FOLDER_PATH = ["Factorial"]
FABRIC_FOLDER_LABEL = "Fabric"

# A Lakehouse's own tables (bronze.*, gold.*, ... -- discovered live via its
# SQL analytics endpoint, see FabricPipelineClient.list_lakehouse_tables)
# aren't Fabric workspace items themselves, so they need their own id
# scheme: deterministic like BC/HubSpot's (derived from the parent
# Lakehouse's id + the table's own schema-qualified name), not random like
# a custom item's.
LAKEHOUSE_TABLE_ID_PREFIX = "lakehouse-table:"

_EMPTY_ENTRY: dict = {
    "short_description": "",
    "long_description_markdown": "",
    "data_owner": [],
    "data_steward": [],
    "data_custodian": [],
    "data_consumer": [],
    "criticality": "",
    "status": "",
    "tags": [],
    "relationships": [],
    "reviewed_by": "",
    "reviewed_at": "",
    "is_custom": False,
    "name": "",
    "type": "",
    "color": "",
    "icon": "",
    # Positions are keyed by the OTHER item's id, as seen from THIS item's
    # own relationship canvas -- the same neighbor can sit at a different
    # spot in a different item's canvas, so positions are never shared.
    "canvas_positions": {},
    # Personal-bookmark-style flags -- global on the item (there's no
    # per-user store anywhere else in this module), not tied to who set them.
    "is_favorite": False,
    # Opt-in curation: with Fabric+BC+HubSpot merged, an untouched catalog
    # is 100+ items -- everything starts hidden until someone explicitly
    # un-hides the ones worth tracking day to day (via "mostrar ocultos" to
    # find and reveal them), rather than starting from a full, noisy list.
    "is_hidden": True,
    # The Fabric item id of this table's linked semantic model, if one was
    # created/linked through the app -- the source of truth for "does this
    # table have a semantic model", since there's no naming convention to
    # search Fabric by (see get_semantic_model_state() below). Only ever set
    # by set_semantic_model_link(), never by set_metadata()'s general edit form.
    "semantic_model_item_id": "",
}


def _read() -> Dict[str, dict]:
    if not _CATALOG_PATH.exists():
        return {}
    try:
        return json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _write(data: Dict[str, dict]) -> None:
    tmp = _CATALOG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(_CATALOG_PATH)


def get_metadata(item_id: str) -> dict:
    """Always returns a fully-shaped entry (every field present, even if
    empty) -- callers never need a None-check or a KeyError guard."""
    with _LOCK:
        entry = _read().get(item_id)
    return {**_EMPTY_ENTRY, **(entry or {})}


def list_metadata() -> Dict[str, dict]:
    with _LOCK:
        return _read()


def _clean_list(values: List[str]) -> List[str]:
    seen: List[str] = []
    for value in values:
        cleaned = value.strip()
        if cleaned and cleaned not in seen:
            seen.append(cleaned)
    return seen


def _validate_relationships(item_id: str, relationships: List[Dict[str, str]]) -> None:
    for rel in relationships:
        rel_type = rel.get("type")
        target = rel.get("target_item_id")
        if rel_type not in RELATIONSHIP_TYPES:
            raise ValueError(f"Tipo de relación desconocido: {rel_type!r}")
        if not target or not isinstance(target, str):
            raise ValueError("Cada relación necesita un 'target_item_id'.")
        if target == item_id:
            raise ValueError("Un elemento no puede relacionarse consigo mismo.")


def _validate_canvas_positions(positions: Dict[str, Dict[str, float]]) -> None:
    for pos in positions.values():
        if not isinstance(pos, dict) or "x" not in pos or "y" not in pos:
            raise ValueError("Cada posición necesita 'x' e 'y'.")
        if isinstance(pos["x"], bool) or isinstance(pos["y"], bool):
            raise ValueError("Las coordenadas deben ser numéricas.")
        if not isinstance(pos["x"], (int, float)) or not isinstance(pos["y"], (int, float)):
            raise ValueError("Las coordenadas deben ser numéricas.")


def set_metadata(
    item_id: str,
    *,
    short_description: str,
    long_description_markdown: str,
    data_owner: List[str],
    data_steward: List[str],
    data_custodian: List[str],
    data_consumer: List[str],
    criticality: str,
    status: str,
    tags: List[str],
    relationships: List[Dict[str, str]],
    reviewed_by: str,
    color: str = "",
    icon: str = "",
    canvas_positions: Optional[Dict[str, Dict[str, float]]] = None,
    is_favorite: Optional[bool] = None,
    is_hidden: Optional[bool] = None,
) -> dict:
    # None means "not provided" -- preserve whatever's already stored,
    # since these have their own lightweight save paths (set_canvas_positions,
    # set_favorite, set_hidden) and the general edit form never sends them.
    # Pass `{}`/explicit booleans to actually change them through this call.
    if canvas_positions is None or is_favorite is None or is_hidden is None:
        current = get_metadata(item_id)
        if canvas_positions is None:
            canvas_positions = current["canvas_positions"]
        if is_favorite is None:
            is_favorite = current["is_favorite"]
        if is_hidden is None:
            is_hidden = current["is_hidden"]

    _validate_relationships(item_id, relationships)
    _validate_canvas_positions(canvas_positions)

    if criticality and criticality not in CRITICALITY_LEVELS:
        raise ValueError(f"Criticidad desconocida: {criticality!r}")
    if status and status not in STATUS_VALUES:
        raise ValueError(f"Estado desconocido: {status!r}")
    if color and not _HEX_COLOR_RE.match(color):
        raise ValueError("El color debe ser un código hexadecimal, p. ej. #3b82f6.")
    if icon and icon not in ICON_KEYS:
        raise ValueError(f"Icono desconocido: {icon!r}")

    entry = {
        "short_description": short_description.strip(),
        "long_description_markdown": long_description_markdown,
        "data_owner": _clean_list(data_owner),
        "data_steward": _clean_list(data_steward),
        "data_custodian": _clean_list(data_custodian),
        "data_consumer": _clean_list(data_consumer),
        "criticality": criticality,
        "status": status,
        "tags": _clean_list(tags),
        "relationships": relationships,
        "reviewed_by": reviewed_by,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
        "color": color,
        "icon": icon,
        "canvas_positions": canvas_positions,
        "is_favorite": is_favorite,
        "is_hidden": is_hidden,
    }
    with _LOCK:
        data = _read()
        # A custom item's identity (name/type/is_custom) lives in this same
        # store with no live upstream record behind it -- set_metadata must
        # preserve those, not silently drop them.
        existing = data.get(item_id, {})
        if existing.get("is_custom"):
            entry = {**entry, "is_custom": True, "name": existing.get("name", ""), "type": existing.get("type", "")}
        data[item_id] = entry
        _write(data)
    return entry


def set_canvas_positions(item_id: str, positions: Dict[str, Dict[str, float]]) -> dict:
    """Dragging a block around isn't a governance edit -- keeps its own
    lightweight save path so arranging a canvas never touches (or
    conflicts with) an in-progress edit of the item's other fields."""
    _validate_canvas_positions(positions)
    with _LOCK:
        data = _read()
        entry = {**_EMPTY_ENTRY, **data.get(item_id, {})}
        entry["canvas_positions"] = positions
        data[item_id] = entry
        _write(data)
    return entry


def set_favorite(item_id: str, is_favorite: bool) -> dict:
    """Bookmarking isn't a governance review -- doesn't stamp reviewed_by/at,
    unlike set_metadata()."""
    with _LOCK:
        data = _read()
        entry = {**_EMPTY_ENTRY, **data.get(item_id, {})}
        entry["is_favorite"] = is_favorite
        data[item_id] = entry
        _write(data)
    return entry


def set_hidden(item_id: str, is_hidden: bool) -> dict:
    with _LOCK:
        data = _read()
        entry = {**_EMPTY_ENTRY, **data.get(item_id, {})}
        entry["is_hidden"] = is_hidden
        data[item_id] = entry
        _write(data)
    return entry


def set_semantic_model_link(item_id: str, semantic_model_item_id: str) -> dict:
    """Records which Fabric semantic model (by its own item id) this table
    is linked to, right after it's created via the app -- its own
    lightweight save path, same reasoning as set_favorite()/set_hidden():
    this is set programmatically by the create flow, never typed into the
    general edit form. Pass "" to unlink (e.g. if the model was deleted
    directly in Fabric and the app should offer "crear" again)."""
    with _LOCK:
        data = _read()
        entry = {**_EMPTY_ENTRY, **data.get(item_id, {})}
        entry["semantic_model_item_id"] = semantic_model_item_id
        data[item_id] = entry
        _write(data)
    return entry


def add_relationship(item_id: str, rel_type: str, target_item_id: str, *, reviewed_by: str) -> dict:
    """Appends a single relationship without touching any of the item's
    other fields -- used by the free-form relationship canvas, where a
    connection drawn between two arbitrary items must save onto whichever
    one owns it without clobbering that item's own in-progress draft of
    description/roles/etc that might be open elsewhere."""
    current = get_metadata(item_id)
    relationships = [*current["relationships"], {"type": rel_type, "target_item_id": target_item_id}]
    return _resave_with_relationships(current, item_id, relationships, reviewed_by)


def remove_relationship(item_id: str, rel_type: str, target_item_id: str, *, reviewed_by: str) -> dict:
    current = get_metadata(item_id)
    relationships = [
        r
        for r in current["relationships"]
        if not (r.get("type") == rel_type and r.get("target_item_id") == target_item_id)
    ]
    return _resave_with_relationships(current, item_id, relationships, reviewed_by)


def _resave_with_relationships(current: dict, item_id: str, relationships: List[Dict[str, str]], reviewed_by: str) -> dict:
    return set_metadata(
        item_id,
        short_description=current["short_description"],
        long_description_markdown=current["long_description_markdown"],
        data_owner=current["data_owner"],
        data_steward=current["data_steward"],
        data_custodian=current["data_custodian"],
        data_consumer=current["data_consumer"],
        criticality=current["criticality"],
        status=current["status"],
        tags=current["tags"],
        relationships=relationships,
        reviewed_by=reviewed_by,
        color=current["color"],
        icon=current["icon"],
        canvas_positions=current["canvas_positions"],
        is_favorite=current["is_favorite"],
        is_hidden=current["is_hidden"],
    )


def delete_metadata(item_id: str) -> None:
    """Not exposed via the API today (items are never deleted through this
    module, only through the upstream system itself) -- kept for
    symmetry/tests and in case an admin ever wants to explicitly clear stale
    metadata."""
    with _LOCK:
        data = _read()
        if item_id in data:
            del data[item_id]
            _write(data)


def create_custom_item(name: str, type_: str, *, created_by: str) -> dict:
    """A manually-declared catalog entry for something outside Fabric/BC/
    HubSpot (an external system, a manual process, ...) that still needs to
    show up in the lineage/relationship picture. Usable as a relationship
    source or target exactly like a real item -- set_metadata() never checks
    that a target_item_id actually exists."""
    name = name.strip()
    if not name:
        raise ValueError("El bloque personalizado necesita un nombre.")

    item_id = f"{CUSTOM_ID_PREFIX}{uuid.uuid4()}"
    entry = {
        **_EMPTY_ENTRY,
        "is_custom": True,
        "name": name,
        "type": type_.strip() or "Personalizado",
        "reviewed_by": created_by,
        "reviewed_at": datetime.now(timezone.utc).isoformat(),
    }
    with _LOCK:
        data = _read()
        data[item_id] = entry
        _write(data)
    return {"item_id": item_id, "folder_path": CUSTOM_FOLDER_PATH, **entry}


def delete_custom_item(item_id: str) -> None:
    with _LOCK:
        data = _read()
        entry = data.get(item_id)
        if entry is None or not entry.get("is_custom"):
            raise ValueError("Ese bloque personalizado no existe.")
        del data[item_id]
        _write(data)


def _folder_path(folder_id: Optional[str], folders_by_id: Dict[str, dict]) -> List[str]:
    path: List[str] = []
    seen = set()
    current_id = folder_id
    while current_id and current_id not in seen:
        seen.add(current_id)
        folder = folders_by_id.get(current_id)
        if folder is None:
            break
        path.append(folder.get("displayName", ""))
        current_id = folder.get("parentFolderId")
    path.reverse()
    return path


# Every field a catalog item exposes beyond item_id/name/type/folder_path,
# all sourced from the metadata store -- one shared list so items from
# different sources can never drift out of shape with each other (a field
# added to only one of the shaping loops below was a real bug caught by
# tests, twice).
_METADATA_FIELDS = (
    "short_description",
    "long_description_markdown",
    "data_owner",
    "data_steward",
    "data_custodian",
    "data_consumer",
    "criticality",
    "status",
    "tags",
    "relationships",
    "reviewed_by",
    "reviewed_at",
    "color",
    "icon",
    "canvas_positions",
    "is_favorite",
    "is_hidden",
    "semantic_model_item_id",
)


def _shape_item(item_id: str, name: str, type_: str, folder_path: List[str], meta: dict, is_custom: bool) -> dict:
    shaped = {"item_id": item_id, "name": name, "type": type_, "folder_path": folder_path, "is_custom": is_custom}
    for field in _METADATA_FIELDS:
        shaped[field] = meta[field]
    return shaped


def list_catalog_items(client: Any) -> List[dict]:
    """Merges six sources into one flat list, each item shaped identically:
    live Fabric items+folders (nested one level under "Fabric" so it reads
    as its own system alongside the others), each Lakehouse's own tables
    (nested one level further under the Lakehouse's own name, discovered
    live via its SQL analytics endpoint -- there's no Fabric workspace item
    per table), the static BC/HubSpot/Factorial table configs (flat, one
    level under "Business Central"/"HubSpot"/"Factorial"), and any custom
    items (under "Personalizados") -- all merged with locally-stored
    governance metadata. `client` is a FabricPipelineClient (passed in
    rather than constructed here so tests can inject a fake)."""
    fabric_items = client.list_items()
    folders = client.list_folders()
    folders_by_id = {f["id"]: f for f in folders}
    metadata = list_metadata()

    result: List[dict] = []
    for item in fabric_items:
        item_id = item.get("id", "")
        display_name = item.get("displayName", "")
        meta = {**_EMPTY_ENTRY, **metadata.get(item_id, {})}
        folder_path = [FABRIC_FOLDER_LABEL, *_folder_path(item.get("folderId"), folders_by_id)]
        result.append(_shape_item(item_id, display_name, item.get("type", ""), folder_path, meta, is_custom=False))

        if item.get("type") == "Lakehouse":
            for table in client.list_lakehouse_tables(item_id, display_name):
                table_name = f"{table['schema']}.{table['table']}"
                table_id = f"{LAKEHOUSE_TABLE_ID_PREFIX}{item_id}:{table_name}"
                table_meta = {**_EMPTY_ENTRY, **metadata.get(table_id, {})}
                result.append(
                    _shape_item(table_id, table_name, "Tabla", [*folder_path, display_name], table_meta, is_custom=False)
                )

    for table in table_configs.list_bc_tables_full():
        item_id = f"{BC_ID_PREFIX}{table.get('name', '')}"
        meta = {**_EMPTY_ENTRY, **metadata.get(item_id, {})}
        result.append(_shape_item(item_id, table.get("name", ""), "Tabla", BC_FOLDER_PATH, meta, is_custom=False))

    for table in table_configs.list_hubspot_tables_full():
        item_id = f"{HUBSPOT_ID_PREFIX}{table.get('name', '')}"
        meta = {**_EMPTY_ENTRY, **metadata.get(item_id, {})}
        result.append(_shape_item(item_id, table.get("name", ""), "Tabla", HUBSPOT_FOLDER_PATH, meta, is_custom=False))

    for table in table_configs.list_factorial_tables_full():
        item_id = f"{FACTORIAL_ID_PREFIX}{table.get('name', '')}"
        meta = {**_EMPTY_ENTRY, **metadata.get(item_id, {})}
        result.append(_shape_item(item_id, table.get("name", ""), "Tabla", FACTORIAL_FOLDER_PATH, meta, is_custom=False))

    for item_id, raw_meta in metadata.items():
        if not raw_meta.get("is_custom"):
            continue
        meta = {**_EMPTY_ENTRY, **raw_meta}
        result.append(_shape_item(item_id, meta["name"], meta["type"], CUSTOM_FOLDER_PATH, meta, is_custom=True))
    return result


def parse_lakehouse_table_id(item_id: str) -> Optional[Tuple[str, str, str]]:
    """Splits "lakehouse-table:{lakehouseId}:{schema}.{table}" back into
    (lakehouse_id, schema, table), or None if item_id isn't one of these
    (the only kind of catalog item a structure preview makes sense for --
    everything else is a REST-discovered Fabric item, a static BC/HubSpot/
    Factorial table, or a custom item, none of which are SQL-queryable)."""
    if not item_id.startswith(LAKEHOUSE_TABLE_ID_PREFIX):
        return None
    rest = item_id[len(LAKEHOUSE_TABLE_ID_PREFIX) :]
    lakehouse_id, _, table_name = rest.partition(":")
    schema, _, table = table_name.partition(".")
    if not lakehouse_id or not schema or not table:
        return None
    return lakehouse_id, schema, table


def preview_lakehouse_table(client: Any, item_id: str, *, limit: int = 10) -> Dict[str, Any]:
    """Runs a `SELECT TOP {limit} *` against the real table a
    "lakehouse-table:..." catalog item stands for -- just enough to see its
    actual columns and a few sample rows. `client` is a FabricPipelineClient
    (passed in rather than constructed here so tests can inject a fake, same
    as list_catalog_items())."""
    parsed = parse_lakehouse_table_id(item_id)
    if parsed is None:
        raise ValueError(f"'{item_id}' no es una tabla de Lakehouse previsualizable.")
    lakehouse_id, schema, table = parsed
    lakehouse_item = client.get_item(lakehouse_id)
    display_name = lakehouse_item.get("displayName", "")
    return client.preview_lakehouse_table(lakehouse_id, display_name, schema, table, limit=limit)


# --------------------------------------------------------------------------------------
# Semantic models -- one single-table DirectLake Fabric semantic model per
# Lakehouse table, created/edited from the app so an external MCP has a
# focused model per table to query. Column *structure* (name/type) is
# always auto-detected from the real table -- never typed by hand -- only
# descriptions are editable here. See src/fabric_pipelines/semantic_model_tmdl.py
# for how the TMDL itself is built/patched, and that module's tests for the
# live-validated create/update round trip this is built on.
# --------------------------------------------------------------------------------------


def _lakehouse_table_source_columns(client: Any, lakehouse_id: str, schema: str, table: str) -> List[Dict[str, str]]:
    lakehouse_item = client.get_item(lakehouse_id)
    display_name = lakehouse_item.get("displayName", "")
    return client.list_lakehouse_table_columns(lakehouse_id, display_name, schema, table)


def _table_tmdl_part(parts: List[Dict[str, Any]]) -> Dict[str, Any]:
    for part in parts:
        path = part.get("path", "")
        if path.startswith("definition/tables/") and path.endswith(".tmdl"):
            return part
    raise ValueError("El modelo semántico no tiene ninguna tabla en su definición -- no se puede editar desde aquí.")


def _empty_semantic_model_state(missing_columns: List[str]) -> Dict[str, Any]:
    return {"linked": False, "model_item_id": "", "model_name": "", "columns": [], "missing_columns": missing_columns}


def get_semantic_model_state(client: Any, item_id: str) -> Dict[str, Any]:
    """Live state of the table's linked semantic model (or the "not linked
    yet" state): its columns with their current descriptions, plus which
    real source-table columns aren't in the model yet (`missing_columns`,
    for the "sync columns" convenience). `client` is a FabricPipelineClient
    (passed in, same as preview_lakehouse_table()/list_catalog_items()).

    Confirmed live this can genuinely take 20-40s end to end: the source
    table's columns need their own SQL connection (get_item + a fresh
    pyodbc connection), and get_definition() on the model can itself be a
    polled Fabric long-running operation. Since those three round trips
    (source columns, get_item, get_definition) are all independent of each
    other, they're all fired in parallel threads (this module's established
    pattern for concurrent I/O, see src/hubspot_main.py/src/factorial_main.py)
    rather than back to back.

    get_item and get_definition are deliberately NOT treated the same way
    on failure. get_item failing (a 404-shaped error) is real evidence the
    model itself is gone -- e.g. deleted directly in Fabric -- so that
    self-heals by unlinking, offering "crear" again instead of failing
    forever on a dangling id. get_definition failing (confirmed live: it
    can time out on its own long-running-operation polling, unrelated to
    whether the model still exists) must NOT trigger that same unlink --
    doing so once genuinely discarded a live link (and its saved
    descriptions) here during testing, just because that one read was slow.
    A get_definition failure is surfaced as a normal error instead; the
    link stays intact and a retry can succeed once Fabric responds."""
    parsed = parse_lakehouse_table_id(item_id)
    if parsed is None:
        raise ValueError(f"'{item_id}' no es una tabla de Lakehouse -- no puede tener un modelo semántico.")
    lakehouse_id, schema, table = parsed
    model_item_id = get_metadata(item_id).get("semantic_model_item_id", "")

    if not model_item_id:
        source_columns = _lakehouse_table_source_columns(client, lakehouse_id, schema, table)
        return _empty_semantic_model_state([c["name"] for c in source_columns])

    from concurrent.futures import ThreadPoolExecutor

    from src.fabric_pipelines.api import FabricPipelineError  # local: keep this module decoupled on the hot path

    with ThreadPoolExecutor(max_workers=3) as pool:
        source_future = pool.submit(_lakehouse_table_source_columns, client, lakehouse_id, schema, table)
        item_future = pool.submit(client.get_item, model_item_id)
        defn_future = pool.submit(client.get_definition, model_item_id)

        source_columns = source_future.result()
        source_names = [c["name"] for c in source_columns]
        try:
            model_item = item_future.result()
        except FabricPipelineError:
            set_semantic_model_link(item_id, "")
            return _empty_semantic_model_state(source_names)
        defn = defn_future.result()

    table_part = _table_tmdl_part(defn.get("definition", {}).get("parts", []))
    table_tmdl = base64.b64decode(table_part["payload"]).decode("utf-8")
    model_columns = parse_table_columns(table_tmdl)

    model_names = {c["name"] for c in model_columns}
    source_name_set = set(source_names)
    for column in model_columns:
        column["in_source"] = column["name"] in source_name_set
    missing_columns = [name for name in source_names if name not in model_names]

    return {
        "linked": True,
        "model_item_id": model_item_id,
        "model_name": model_item.get("displayName", ""),
        "columns": model_columns,
        "missing_columns": missing_columns,
    }


def create_semantic_model(client: Any, item_id: str) -> Dict[str, Any]:
    """Creates a brand-new, single-table DirectLake semantic model for this
    Lakehouse table -- columns auto-detected from the table's real schema,
    never typed by hand -- links it to this catalog item, and returns the
    same shape as get_semantic_model_state(). Raises ValueError if a model
    is already linked (unlink/delete it first rather than silently creating
    a second one for the same table)."""
    parsed = parse_lakehouse_table_id(item_id)
    if parsed is None:
        raise ValueError(f"'{item_id}' no es una tabla de Lakehouse -- no puede tener un modelo semántico.")
    lakehouse_id, schema, table = parsed
    if get_metadata(item_id).get("semantic_model_item_id", ""):
        raise ValueError("Esta tabla ya tiene un modelo semántico vinculado.")

    source_columns = _lakehouse_table_source_columns(client, lakehouse_id, schema, table)
    if not source_columns:
        raise ValueError(f"No se encontraron columnas para {schema}.{table} -- ¿existe todavía en el Lakehouse?")

    parts = build_new_model_parts(
        display_name=table,
        workspace_id=client.workspace_id,
        lakehouse_id=lakehouse_id,
        schema=schema,
        table=table,
        columns=source_columns,
    )
    model_item_id = client.create_item(table, "SemanticModel", parts)
    set_semantic_model_link(item_id, model_item_id)
    return get_semantic_model_state(client, item_id)


def update_semantic_model_descriptions(client: Any, item_id: str, descriptions: Dict[str, str]) -> Dict[str, Any]:
    """Pushes column description edits to the linked semantic model --
    surgically (see semantic_model_tmdl.set_column_description()), so
    anything else on the model (measures, hierarchies, other columns) is
    left untouched. Raises ValueError if there's no linked model, or if a
    description targets a column the model doesn't have (stale UI state)."""
    model_item_id = get_metadata(item_id).get("semantic_model_item_id", "")
    if not model_item_id:
        raise ValueError("Esta tabla todavía no tiene un modelo semántico vinculado.")

    defn = client.get_definition(model_item_id)
    parts = defn.get("definition", {}).get("parts", [])
    table_part = _table_tmdl_part(parts)
    table_tmdl = base64.b64decode(table_part["payload"]).decode("utf-8")
    for column_name, description in descriptions.items():
        table_tmdl = set_column_description(table_tmdl, column_name, description)

    updated_parts = [
        {**part, "payload": base64.b64encode(table_tmdl.encode("utf-8")).decode("ascii")}
        if part is table_part
        else part
        for part in parts
    ]
    client.update_item_definition(model_item_id, updated_parts)
    return get_semantic_model_state(client, item_id)


def sync_semantic_model_columns(client: Any, item_id: str) -> Dict[str, Any]:
    """Adds any column the real source table has that the linked semantic
    model doesn't yet (schema drift -- e.g. a pipeline started landing a
    new column after the model was created), auto-detected the same way
    creation is, so nobody has to add them by hand."""
    parsed = parse_lakehouse_table_id(item_id)
    if parsed is None:
        raise ValueError(f"'{item_id}' no es una tabla de Lakehouse -- no puede tener un modelo semántico.")
    lakehouse_id, schema, table = parsed
    model_item_id = get_metadata(item_id).get("semantic_model_item_id", "")
    if not model_item_id:
        raise ValueError("Esta tabla todavía no tiene un modelo semántico vinculado.")

    source_columns = _lakehouse_table_source_columns(client, lakehouse_id, schema, table)

    defn = client.get_definition(model_item_id)
    parts = defn.get("definition", {}).get("parts", [])
    table_part = _table_tmdl_part(parts)
    table_tmdl = base64.b64decode(table_part["payload"]).decode("utf-8")
    model_names = {c["name"] for c in parse_table_columns(table_tmdl)}
    missing = [c for c in source_columns if c["name"] not in model_names]
    if not missing:
        return get_semantic_model_state(client, item_id)

    patched_tmdl = append_missing_columns(table_tmdl, missing)
    updated_parts = [
        {**part, "payload": base64.b64encode(patched_tmdl.encode("utf-8")).decode("ascii")}
        if part is table_part
        else part
        for part in parts
    ]
    client.update_item_definition(model_item_id, updated_parts)
    return get_semantic_model_state(client, item_id)
