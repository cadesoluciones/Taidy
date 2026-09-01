# -*- coding: utf-8 -*-
"""
Building and patching TMDL ("Tabular Model Definition Language") text for a
single-table Fabric semantic model, in two modes:

- DirectLake (build_new_model_parts/append_missing_columns): for a real
  Lakehouse table -- columns are always auto-detected, never typed by hand.
  Every shape here was reverse-engineered from a real semantic model
  already in production (get_definition() against "transacciones_pyg"),
  then confirmed live end-to-end against the real workspace: creating a
  throwaway single-table model, adding a column description to it, reading
  it back, then deleting it.
- Manual (build_new_manual_model_parts/set_manual_table_columns): for
  anything with no real table to detect columns from (BC/HubSpot/Factorial/
  custom catalog items) -- columns are typed by hand, and the table has no
  live data connection (confirmed live: Fabric rejects a table with no
  partition at all; a DATATABLE() calculated partition returning zero rows
  is the minimal shape it accepts). This is a data dictionary, not
  something an MCP can query for real values.

See FabricPipelineClient.create_item()/update_item_definition() in api.py
for the HTTP side.

DirectLake column patching (append_missing_columns) is deliberately
surgical -- string insertion at a located anchor line, never a full
parse-and-regenerate of the table's TMDL -- because a real semantic model
can carry hand-written measures/hierarchies (again, see
"transacciones_pyg") that this feature never touches and must not risk
corrupting. Manual tables have no such risk (there's no real data for a
measure to aggregate), so set_manual_table_columns() fully regenerates the
table block instead -- simpler, and DATATABLE()'s signature has to be
rebuilt in lockstep with the column list either way.
"""

from __future__ import annotations

import base64
import json
import re
from typing import Dict, List, Optional, TypedDict

# TMDL identifiers (table/column names) only need single-quoting when they
# aren't a plain word -- confirmed live: unquoted "Endeudamiento (1)" fails
# with a TMDL parse error, plain words like "IdEmpresa" don't need quoting.
_SIMPLE_IDENT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

# SQL Server type name -> TMDL dataType. Anything unrecognized falls back to
# "string" -- safe (Power BI can always display a string) rather than
# raising, since new/exotic SQL types shouldn't block column detection.
_SQL_TO_TMDL_TYPE = {
    "varchar": "string", "nvarchar": "string", "char": "string", "nchar": "string", "text": "string", "ntext": "string",
    "int": "int64", "bigint": "int64", "smallint": "int64", "tinyint": "int64",
    "float": "double", "real": "double", "decimal": "double", "numeric": "double", "money": "double", "smallmoney": "double",
    "bit": "boolean",
    "date": "dateTime", "datetime": "dateTime", "datetime2": "dateTime", "smalldatetime": "dateTime", "datetimeoffset": "dateTime",
}

_SUMMARIZABLE_TYPES = {"int64", "double"}


class SourceColumn(TypedDict):
    name: str
    sql_type: str


class ManualColumn(TypedDict):
    """A column defined by hand (no real source table to detect it from --
    e.g. a BC/HubSpot/Factorial/custom catalog item) -- `data_type` is
    already a TMDL dataType key (see MANUAL_DATA_TYPES), not a SQL type."""

    name: str
    data_type: str


class ModelColumn(TypedDict):
    name: str
    description: str
    data_type: str


# The manual-entry picker's fixed choices -- deliberately small (matches
# what sql_type_to_tmdl() already collapses everything down to for
# auto-detected columns), not the full TMDL/DAX type vocabulary.
MANUAL_DATA_TYPES = ("string", "int64", "double", "boolean", "dateTime")

# TMDL dataType key -> the DAX DATATABLE() function's own type keyword --
# a completely different vocabulary (STRING/INTEGER/DOUBLE/BOOLEAN/DATETIME),
# confirmed live: this is what a manual (no real data source) table's
# partition is built from, see build_new_manual_model_parts().
_TMDL_TO_DATATABLE_TYPE = {
    "string": "STRING",
    "int64": "INTEGER",
    "double": "DOUBLE",
    "boolean": "BOOLEAN",
    "dateTime": "DATETIME",
}


def sql_type_to_tmdl(sql_type: str) -> str:
    return _SQL_TO_TMDL_TYPE.get(sql_type.lower(), "string")


def tmdl_ident(name: str) -> str:
    if _SIMPLE_IDENT_RE.match(name):
        return name
    return "'" + name.replace("'", "''") + "'"


def _unquote_tmdl_ident(raw: str) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == "'" and raw[-1] == "'":
        return raw[1:-1].replace("''", "'")
    return raw


def _b64(text: str) -> str:
    return base64.b64encode(text.encode("utf-8")).decode("ascii")


def _column_block(column: SourceColumn) -> str:
    dt = sql_type_to_tmdl(column["sql_type"])
    return _column_block_for_type(column["name"], dt)


def _column_block_for_type(name: str, dt: str) -> str:
    summarize = "sum" if dt in _SUMMARIZABLE_TYPES else "none"
    ident = tmdl_ident(name)
    return (
        f"\tcolumn {ident}\n"
        f"\t\tdataType: {dt}\n"
        f"\t\tsummarizeBy: {summarize}\n"
        f"\t\tsourceColumn: {ident}\n\n"
        f"\t\tannotation SummarizationSetBy = Automatic\n"
    )


def build_new_model_parts(
    *,
    display_name: str,
    workspace_id: str,
    lakehouse_id: str,
    schema: str,
    table: str,
    columns: List[SourceColumn],
) -> List[Dict[str, str]]:
    """The full set of definition parts for a brand-new, single-table
    DirectLake semantic model -- ready to pass to
    FabricPipelineClient.create_item(display_name, "SemanticModel", parts)."""
    table_ident = tmdl_ident(table)
    table_tmdl = (
        f"table {table_ident}\n\n"
        + "\n".join(_column_block(c) for c in columns)
        + f"\n\tpartition {table_ident} = entity\n"
        f"\t\tmode: directLake\n"
        f"\t\tsource\n"
        f"\t\t\tentityName: {tmdl_ident(table)}\n"
        f"\t\t\tschemaName: {tmdl_ident(schema)}\n"
        f"\t\t\texpressionSource: 'DirectLake - Lakehouse'\n"
    )
    model_tmdl = (
        "model Model\n"
        "\tculture: en-US\n"
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
        "\tsourceQueryCulture: en-US\n"
        "\tdataAccessOptions\n"
        "\t\tlegacyRedirects\n"
        "\t\treturnErrorValuesAsNull\n\n"
        f"ref table {table_ident}\n"
    )
    expressions_tmdl = (
        "expression 'DirectLake - Lakehouse' =\n"
        "\t\tlet\n"
        f'\t\t    Source = AzureStorage.DataLake("https://onelake.dfs.fabric.microsoft.com/{workspace_id}/{lakehouse_id}", [HierarchicalNavigation=true])\n'
        "\t\tin\n"
        "\t\t    Source\n"
        "\tannotation PBI_IncludeFutureArtifacts = False\n"
    )
    database_tmdl = "database\n\tcompatibilityLevel: 1604\n"
    pbism = json.dumps(
        {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
            "version": "4.2",
            "settings": {},
        }
    )
    platform = json.dumps(
        {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {"type": "SemanticModel", "displayName": display_name},
            "config": {"version": "2.0", "logicalId": "00000000-0000-0000-0000-000000000000"},
        }
    )
    return [
        {"path": ".platform", "payload": _b64(platform), "payloadType": "InlineBase64"},
        {"path": "definition.pbism", "payload": _b64(pbism), "payloadType": "InlineBase64"},
        {"path": "definition/database.tmdl", "payload": _b64(database_tmdl), "payloadType": "InlineBase64"},
        {"path": "definition/model.tmdl", "payload": _b64(model_tmdl), "payloadType": "InlineBase64"},
        {"path": "definition/expressions.tmdl", "payload": _b64(expressions_tmdl), "payloadType": "InlineBase64"},
        {"path": f"definition/tables/{table}.tmdl", "payload": _b64(table_tmdl), "payloadType": "InlineBase64"},
    ]


_TABLE_LINE_RE = re.compile(r"^table\s+(.+?)\s*$")
_COLUMN_LINE_RE = re.compile(r"^\tcolumn\s+(.+?)\s*$")
_DATA_TYPE_LINE_RE = re.compile(r"^\t\tdataType:\s*(.+?)\s*$")
_DOC_COMMENT_RE = re.compile(r"^\t///\s?(.*)$")
_PARTITION_LINE_RE = re.compile(r"^\tpartition\s")


def parse_table_name(table_tmdl: str) -> str:
    """The table's own declared name (the `table <ident>` line at the top
    of its TMDL), unquoted -- used when a caller needs the real identifier
    to rebuild a manual table's DATATABLE() partition, rather than assuming
    it matches the file path's name exactly."""
    for line in table_tmdl.splitlines():
        match = _TABLE_LINE_RE.match(line)
        if match:
            return _unquote_tmdl_ident(match.group(1))
    raise ValueError("No se pudo determinar el nombre de la tabla en la definición del modelo.")


def parse_table_columns(table_tmdl: str) -> List[ModelColumn]:
    """Every `column` this table's TMDL declares, each with its current
    description (the `///` doc-comment line(s) immediately above it, joined
    with newlines -- empty string if there is none) and dataType (empty
    string in the unexpected case a column has none). Read-only: used to
    show the semantic-model tab's current state, never to regenerate the
    file -- see set_manual_table_columns() for the one path that does
    regenerate, and reads this first specifically to avoid losing it."""
    columns: List[ModelColumn] = []
    pending_doc_lines: List[str] = []
    current: Optional[ModelColumn] = None
    for line in table_tmdl.splitlines():
        doc_match = _DOC_COMMENT_RE.match(line)
        if doc_match:
            pending_doc_lines.append(doc_match.group(1))
            continue
        col_match = _COLUMN_LINE_RE.match(line)
        if col_match:
            current = {
                "name": _unquote_tmdl_ident(col_match.group(1)),
                "description": "\n".join(pending_doc_lines),
                "data_type": "",
            }
            columns.append(current)
            pending_doc_lines = []
            continue
        if current is not None:
            type_match = _DATA_TYPE_LINE_RE.match(line)
            if type_match:
                current["data_type"] = type_match.group(1)
        # Any other top-level (single-tab-indented) line -- e.g. `measure`,
        # `hierarchy` -- means a doc-comment right above it wasn't for a
        # column and shouldn't leak onto the next one found later, and that
        # we're no longer inside the most recent column's own property block.
        if line.startswith("\t") and not line.startswith("\t\t") and line.strip():
            pending_doc_lines = []
            current = None
    return columns


def set_column_description(table_tmdl: str, column_name: str, description: str) -> str:
    """Surgically inserts/replaces the `///` doc-comment line(s) immediately
    above `column <column_name>` -- every other line (measures, hierarchies,
    other columns, formatting) is left byte-for-byte untouched. Raises
    ValueError if the column isn't declared in this TMDL (a stale UI state
    trying to edit a column Fabric no longer has)."""
    lines = table_tmdl.splitlines(keepends=True)
    target_idx: Optional[int] = None
    for i, line in enumerate(lines):
        match = _COLUMN_LINE_RE.match(line.rstrip("\n"))
        if match and _unquote_tmdl_ident(match.group(1)) == column_name:
            target_idx = i
            break
    if target_idx is None:
        raise ValueError(f"La columna '{column_name}' no existe en este modelo semántico.")

    # Walk upward past any existing doc-comment lines directly above the
    # column line to find where the replacement block should start.
    doc_start = target_idx
    while doc_start > 0 and _DOC_COMMENT_RE.match(lines[doc_start - 1].rstrip("\n")):
        doc_start -= 1

    new_doc_lines = [f"\t/// {segment}\n" for segment in description.splitlines()] if description else []
    return "".join(lines[:doc_start] + new_doc_lines + lines[target_idx:])


def _validate_manual_columns(columns: List[ManualColumn]) -> None:
    seen: set = set()
    for c in columns:
        if not c["name"].strip():
            raise ValueError("El nombre de columna no puede estar vacío.")
        if c["name"] in seen:
            raise ValueError(f"Columna repetida: '{c['name']}'.")
        seen.add(c["name"])
        if c["data_type"] not in MANUAL_DATA_TYPES:
            raise ValueError(f"Tipo de dato desconocido: '{c['data_type']}'.")


def _datatable_partition(table: str, columns: List[ManualColumn]) -> str:
    """A `calculated` partition backed by DAX's DATATABLE() with zero rows
    -- confirmed live this is the minimal shape Fabric accepts for a table
    with no real data source at all (every table needs *some* partition;
    a bare column list with none is rejected). The declared columns here
    must always match the table's own `column` blocks exactly, unlike
    DirectLake's partition (which never lists columns itself) -- see
    set_manual_table_columns(), which regenerates both together."""
    args = ", ".join(
        f'"{c["name"]}", {_TMDL_TO_DATATABLE_TYPE.get(c["data_type"], "STRING")}' for c in columns
    )
    return f"\tpartition {tmdl_ident(table)} = calculated\n\t\tmode: import\n\t\tsource = DATATABLE({args}, {{}})\n"


def build_new_manual_model_parts(
    *,
    display_name: str,
    table: str,
    columns: List[ManualColumn],
) -> List[Dict[str, str]]:
    """The full set of definition parts for a brand-new, single-table
    semantic model with NO real data source (a BC/HubSpot/Factorial/custom
    catalog item -- nothing to auto-detect columns from) -- a data
    dictionary, not something an MCP can query for real values, but the
    column names/types/descriptions are real and editable. Ready to pass to
    FabricPipelineClient.create_item(display_name, "SemanticModel", parts)."""
    if not columns:
        raise ValueError("El modelo necesita al menos una columna.")
    _validate_manual_columns(columns)
    table_ident = tmdl_ident(table)
    table_tmdl = (
        f"table {table_ident}\n\n"
        + "\n".join(_column_block_for_type(c["name"], c["data_type"]) for c in columns)
        + "\n"
        + _datatable_partition(table, columns)
    )
    model_tmdl = (
        "model Model\n"
        "\tculture: en-US\n"
        "\tdefaultPowerBIDataSourceVersion: powerBI_V3\n"
        "\tsourceQueryCulture: en-US\n"
        "\tdataAccessOptions\n"
        "\t\tlegacyRedirects\n"
        "\t\treturnErrorValuesAsNull\n\n"
        f"ref table {table_ident}\n"
    )
    database_tmdl = "database\n\tcompatibilityLevel: 1604\n"
    pbism = json.dumps(
        {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definitionProperties/1.0.0/schema.json",
            "version": "4.2",
            "settings": {},
        }
    )
    platform = json.dumps(
        {
            "$schema": "https://developer.microsoft.com/json-schemas/fabric/gitIntegration/platformProperties/2.0.0/schema.json",
            "metadata": {"type": "SemanticModel", "displayName": display_name},
            "config": {"version": "2.0", "logicalId": "00000000-0000-0000-0000-000000000000"},
        }
    )
    return [
        {"path": ".platform", "payload": _b64(platform), "payloadType": "InlineBase64"},
        {"path": "definition.pbism", "payload": _b64(pbism), "payloadType": "InlineBase64"},
        {"path": "definition/database.tmdl", "payload": _b64(database_tmdl), "payloadType": "InlineBase64"},
        {"path": "definition/model.tmdl", "payload": _b64(model_tmdl), "payloadType": "InlineBase64"},
        {"path": f"definition/tables/{table}.tmdl", "payload": _b64(table_tmdl), "payloadType": "InlineBase64"},
    ]


def set_manual_table_columns(table_tmdl: str, table: str, columns: List[ManualColumn]) -> str:
    """Rebuilds a manual (no real data source) table's TMDL from a full
    desired column list -- used for both adding and removing a column,
    since DATATABLE()'s own signature must always match the declared
    columns exactly (unlike DirectLake, appending a column there is a
    surgical insert -- see append_missing_columns() -- because its
    partition never lists columns to begin with). Unlike that surgical
    path, this DOES fully regenerate the table block, but a manual table by
    definition never carries hand-written measures/hierarchies (there's no
    real data for a measure to aggregate), so there's nothing at risk of
    being clobbered -- existing column descriptions are the only thing
    worth preserving, and are looked up and carried over by name."""
    if not columns:
        raise ValueError("El modelo necesita al menos una columna.")
    _validate_manual_columns(columns)
    existing_descriptions = {c["name"]: c["description"] for c in parse_table_columns(table_tmdl)}
    table_ident = tmdl_ident(table)
    blocks = []
    for c in columns:
        block = _column_block_for_type(c["name"], c["data_type"])
        description = existing_descriptions.get(c["name"], "")
        if description:
            doc_lines = "".join(f"\t/// {segment}\n" for segment in description.splitlines())
            block = doc_lines + block
        blocks.append(block)
    return f"table {table_ident}\n\n" + "\n".join(blocks) + "\n" + _datatable_partition(table, columns)


def append_missing_columns(table_tmdl: str, missing: List[SourceColumn]) -> str:
    """Inserts new `column` blocks for tables the live source table has but
    this TMDL doesn't yet -- appended just before the `partition` clause
    (every real example seen has exactly one, at the end of the table
    block), leaving existing columns/measures/hierarchies untouched."""
    if not missing:
        return table_tmdl
    lines = table_tmdl.splitlines(keepends=True)
    partition_idx = next((i for i, line in enumerate(lines) if _PARTITION_LINE_RE.match(line.rstrip("\n"))), len(lines))
    new_blocks = "".join(_column_block(c) + "\n" for c in missing)
    return "".join(lines[:partition_idx]) + new_blocks + "".join(lines[partition_idx:])
