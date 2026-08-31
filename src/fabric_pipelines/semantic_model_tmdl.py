# -*- coding: utf-8 -*-
"""
Building and surgically patching TMDL ("Tabular Model Definition Language")
text for a single-table, DirectLake Fabric semantic model.

Every shape here was reverse-engineered from a real semantic model already
in production (get_definition() against "transacciones_pyg"), then
confirmed live end-to-end against the real workspace: creating a
throwaway single-table model, adding a column description to it, reading
it back, then deleting it. See FabricPipelineClient.create_item()/
update_item_definition() in api.py for the HTTP side.

Patching (add_description / append_missing_columns) is deliberately
surgical -- string insertion at a located anchor line, never a full
parse-and-regenerate of the table's TMDL -- because a real semantic model
can carry hand-written measures/hierarchies (again, see
"transacciones_pyg") that this feature never touches and must not risk
corrupting.
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


class ModelColumn(TypedDict):
    name: str
    description: str


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
    summarize = "sum" if dt in _SUMMARIZABLE_TYPES else "none"
    ident = tmdl_ident(column["name"])
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


_COLUMN_LINE_RE = re.compile(r"^\tcolumn\s+(.+?)\s*$")
_DOC_COMMENT_RE = re.compile(r"^\t///\s?(.*)$")
_PARTITION_LINE_RE = re.compile(r"^\tpartition\s")


def parse_table_columns(table_tmdl: str) -> List[ModelColumn]:
    """Every `column` this table's TMDL declares, each with its current
    description (the `///` doc-comment line(s) immediately above it, joined
    with newlines -- empty string if there is none). Read-only: used to show
    the semantic-model tab's current state, never to regenerate the file."""
    columns: List[ModelColumn] = []
    pending_doc_lines: List[str] = []
    for line in table_tmdl.splitlines():
        doc_match = _DOC_COMMENT_RE.match(line)
        if doc_match:
            pending_doc_lines.append(doc_match.group(1))
            continue
        col_match = _COLUMN_LINE_RE.match(line)
        if col_match:
            columns.append(
                {
                    "name": _unquote_tmdl_ident(col_match.group(1)),
                    "description": "\n".join(pending_doc_lines),
                }
            )
            pending_doc_lines = []
            continue
        # Any other top-level (single-tab-indented) line -- e.g. `measure`,
        # `hierarchy` -- means a doc-comment right above it wasn't for a
        # column and shouldn't leak onto the next one found later.
        if line.startswith("\t") and not line.startswith("\t\t") and line.strip():
            pending_doc_lines = []
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
