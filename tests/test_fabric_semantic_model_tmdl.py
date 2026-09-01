# -*- coding: utf-8 -*-
"""
src.fabric_pipelines.semantic_model_tmdl -- building a new single-table
DirectLake model's TMDL parts, and surgically patching an existing table's
TMDL (description edits, missing-column additions) without disturbing
anything else in the file (measures, hierarchies, other columns).

REAL_TABLE_TMDL below is the exact text of a production semantic model's
table part ("transacciones_pyg", read live via get_definition() in an
earlier session) -- used to make sure the surgical patch functions behave
correctly against a table that has real measures and a hierarchy, not just
the bare-bones tables this module itself generates.
"""

from __future__ import annotations

import base64
import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.fabric_pipelines.semantic_model_tmdl import (  # noqa: E402
    append_missing_columns,
    build_new_manual_model_parts,
    build_new_model_parts,
    parse_table_columns,
    parse_table_name,
    set_column_description,
    set_manual_table_columns,
    sql_type_to_tmdl,
    tmdl_ident,
)

REAL_TABLE_TMDL = """table transacciones_pyg
\tlineageTag: a812d92d-c587-41ea-b700-14290aff65cf
\tsourceLineageTag: [silver].[transacciones_pyg]

\tmeasure 'Importe Real' = CALCULATE(SUM(transacciones_pyg[importe]), transacciones_pyg[origen] = "movimientos_contables")
\t\tlineageTag: 0d0ef777-22d1-4aa8-93a1-ec0b62ff4186

\t\tchangedProperty = Name

\tcolumn cuenta_contable
\t\tdataType: string
\t\tlineageTag: 709f53c5-fe18-4547-b042-0610fe7f9a12
\t\tsourceLineageTag: cuenta_contable
\t\tsummarizeBy: none
\t\tsourceColumn: cuenta_contable

\t\tannotation SummarizationSetBy = Automatic

\tcolumn importe
\t\tdataType: double
\t\tlineageTag: 19d3a653-4f83-40fe-bebd-3255b4946bd0
\t\tsourceLineageTag: importe
\t\tsummarizeBy: sum
\t\tsourceColumn: importe

\t\tannotation SummarizationSetBy = Automatic

\thierarchy 'Jerarquía PyG'
\t\tlineageTag: afe40d6f-5160-4b8f-b85b-d2bb304b9877

\t\tlevel cuenta_contable
\t\t\tlineageTag: 578a6bb1-dc15-4165-91f1-bb6f9ef3fe31
\t\t\tcolumn: cuenta_contable

\tpartition transacciones_pyg = entity
\t\tmode: directLake
\t\tsource
\t\t\tentityName: transacciones_pyg
\t\t\tschemaName: silver
\t\t\texpressionSource: 'DirectLake - Lakehouse'
"""


# --------------------------------------------------------------------------------------
# sql_type_to_tmdl / tmdl_ident
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "sql_type,expected",
    [
        ("varchar", "string"),
        ("NVARCHAR", "string"),
        ("int", "int64"),
        ("bigint", "int64"),
        ("float", "double"),
        ("decimal", "double"),
        ("bit", "boolean"),
        ("datetime2", "dateTime"),
        ("some_exotic_type", "string"),
    ],
)
def test_sql_type_to_tmdl_maps_known_types_and_falls_back_to_string(sql_type, expected):
    assert sql_type_to_tmdl(sql_type) == expected


def test_tmdl_ident_leaves_plain_words_unquoted():
    assert tmdl_ident("IdEmpresa") == "IdEmpresa"


def test_tmdl_ident_quotes_names_with_spaces_or_punctuation():
    assert tmdl_ident("Endeudamiento (1)") == "'Endeudamiento (1)'"


def test_tmdl_ident_escapes_embedded_quotes():
    assert tmdl_ident("a'b") == "'a''b'"


# --------------------------------------------------------------------------------------
# build_new_model_parts
# --------------------------------------------------------------------------------------


def test_build_new_model_parts_returns_the_six_expected_parts():
    parts = build_new_model_parts(
        display_name="ventas_por_dia",
        workspace_id="ws-1",
        lakehouse_id="lh-1",
        schema="gold",
        table="ventas_por_dia",
        columns=[{"name": "fecha", "sql_type": "date"}, {"name": "importe", "sql_type": "decimal"}],
    )
    paths = {p["path"] for p in parts}
    assert paths == {
        ".platform",
        "definition.pbism",
        "definition/database.tmdl",
        "definition/model.tmdl",
        "definition/expressions.tmdl",
        "definition/tables/ventas_por_dia.tmdl",
    }
    assert all(p["payloadType"] == "InlineBase64" for p in parts)


def test_build_new_model_parts_table_tmdl_declares_directlake_partition_and_columns():
    parts = build_new_model_parts(
        display_name="ventas_por_dia",
        workspace_id="ws-1",
        lakehouse_id="lh-1",
        schema="gold",
        table="ventas_por_dia",
        columns=[{"name": "fecha", "sql_type": "date"}, {"name": "importe", "sql_type": "decimal"}],
    )
    table_part = next(p for p in parts if p["path"] == "definition/tables/ventas_por_dia.tmdl")
    text = base64.b64decode(table_part["payload"]).decode("utf-8")
    assert "column fecha" in text
    assert "dataType: dateTime" in text
    assert "column importe" in text
    assert "dataType: double" in text
    assert "summarizeBy: sum" in text
    assert "mode: directLake" in text
    assert "entityName: ventas_por_dia" in text
    assert "schemaName: gold" in text


def test_build_new_model_parts_quotes_column_names_that_need_it():
    parts = build_new_model_parts(
        display_name="m",
        workspace_id="ws-1",
        lakehouse_id="lh-1",
        schema="bronze",
        table="custom_cat_bs",
        columns=[{"name": "Endeudamiento (1)", "sql_type": "float"}],
    )
    table_part = next(p for p in parts if p["path"] == "definition/tables/custom_cat_bs.tmdl")
    text = base64.b64decode(table_part["payload"]).decode("utf-8")
    assert "column 'Endeudamiento (1)'" in text
    assert "sourceColumn: 'Endeudamiento (1)'" in text


def test_build_new_model_parts_expressions_point_at_the_right_lakehouse_onelake_path():
    parts = build_new_model_parts(
        display_name="m", workspace_id="WSID", lakehouse_id="LHID", schema="s", table="t",
        columns=[{"name": "a", "sql_type": "int"}],
    )
    expr_part = next(p for p in parts if p["path"] == "definition/expressions.tmdl")
    text = base64.b64decode(expr_part["payload"]).decode("utf-8")
    assert "https://onelake.dfs.fabric.microsoft.com/WSID/LHID" in text


# --------------------------------------------------------------------------------------
# parse_table_columns
# --------------------------------------------------------------------------------------


def test_parse_table_columns_reads_names_and_empty_descriptions_from_the_real_model():
    columns = parse_table_columns(REAL_TABLE_TMDL)
    names = [c["name"] for c in columns]
    assert names == ["cuenta_contable", "importe"]
    assert all(c["description"] == "" for c in columns)


def test_parse_table_columns_reads_a_description_from_a_doc_comment():
    tmdl = "table t\n\n\t/// Identificador de la cuenta contable.\n\tcolumn cuenta_contable\n\t\tdataType: string\n"
    columns = parse_table_columns(tmdl)
    assert columns == [
        {"name": "cuenta_contable", "description": "Identificador de la cuenta contable.", "data_type": "string"}
    ]


def test_parse_table_columns_joins_multiline_doc_comments():
    tmdl = "table t\n\n\t/// Línea uno.\n\t/// Línea dos.\n\tcolumn c\n\t\tdataType: string\n"
    columns = parse_table_columns(tmdl)
    assert columns[0]["description"] == "Línea uno.\nLínea dos."


def test_parse_table_columns_does_not_leak_a_measures_doc_comment_onto_the_next_column():
    tmdl = (
        "table t\n\n"
        "\t/// Not a column description.\n"
        "\tmeasure 'X' = SUM(t[a])\n"
        "\t\tlineageTag: x\n\n"
        "\tcolumn a\n"
        "\t\tdataType: int64\n"
    )
    columns = parse_table_columns(tmdl)
    assert columns == [{"name": "a", "description": "", "data_type": "int64"}]


def test_parse_table_columns_unquotes_quoted_identifiers():
    tmdl = "table t\n\n\tcolumn 'Endeudamiento (1)'\n\t\tdataType: double\n"
    columns = parse_table_columns(tmdl)
    assert columns == [{"name": "Endeudamiento (1)", "description": "", "data_type": "double"}]


# --------------------------------------------------------------------------------------
# set_column_description
# --------------------------------------------------------------------------------------


def test_set_column_description_inserts_a_new_doc_comment():
    patched = set_column_description(REAL_TABLE_TMDL, "importe", "Importe en euros.")
    columns = parse_table_columns(patched)
    by_name = {c["name"]: c["description"] for c in columns}
    assert by_name["importe"] == "Importe en euros."
    assert by_name["cuenta_contable"] == ""  # untouched


def test_set_column_description_replaces_an_existing_doc_comment():
    once = set_column_description(REAL_TABLE_TMDL, "importe", "Primera versión.")
    twice = set_column_description(once, "importe", "Segunda versión.")
    columns = {c["name"]: c["description"] for c in parse_table_columns(twice)}
    assert columns["importe"] == "Segunda versión."
    # Only one doc-comment line survives, not both stacked.
    assert twice.count("/// Primera versión.") == 0


def test_set_column_description_leaves_measures_and_hierarchy_byte_for_byte_untouched():
    patched = set_column_description(REAL_TABLE_TMDL, "importe", "Importe en euros.")
    assert "measure 'Importe Real' = CALCULATE(SUM(transacciones_pyg[importe])" in patched
    assert "hierarchy 'Jerarquía PyG'" in patched
    assert "level cuenta_contable" in patched
    assert "partition transacciones_pyg = entity" in patched


def test_set_column_description_empty_string_clears_an_existing_description():
    with_desc = set_column_description(REAL_TABLE_TMDL, "importe", "Algo.")
    cleared = set_column_description(with_desc, "importe", "")
    columns = {c["name"]: c["description"] for c in parse_table_columns(cleared)}
    assert columns["importe"] == ""


def test_set_column_description_raises_for_a_column_that_does_not_exist():
    with pytest.raises(ValueError, match="no existe"):
        set_column_description(REAL_TABLE_TMDL, "no_such_column", "x")


def test_set_column_description_works_on_a_quoted_identifier_column():
    tmdl = "table t\n\n\tcolumn 'Endeudamiento (1)'\n\t\tdataType: double\n\n\tpartition t = entity\n\t\tmode: directLake\n"
    patched = set_column_description(tmdl, "Endeudamiento (1)", "Ratio de endeudamiento.")
    columns = {c["name"]: c["description"] for c in parse_table_columns(patched)}
    assert columns["Endeudamiento (1)"] == "Ratio de endeudamiento."


# --------------------------------------------------------------------------------------
# append_missing_columns
# --------------------------------------------------------------------------------------


def test_append_missing_columns_adds_new_columns_before_the_partition_clause():
    patched = append_missing_columns(REAL_TABLE_TMDL, [{"name": "nueva_col", "sql_type": "varchar"}])
    names = [c["name"] for c in parse_table_columns(patched)]
    assert names == ["cuenta_contable", "importe", "nueva_col"]
    # Still declared before the partition, i.e. still inside the table block.
    assert patched.index("column nueva_col") < patched.index("partition transacciones_pyg = entity")


def test_append_missing_columns_leaves_existing_columns_and_measures_untouched():
    patched = append_missing_columns(REAL_TABLE_TMDL, [{"name": "nueva_col", "sql_type": "int"}])
    assert "measure 'Importe Real'" in patched
    assert "column cuenta_contable" in patched
    assert "column importe" in patched


def test_append_missing_columns_with_no_missing_columns_returns_input_unchanged():
    assert append_missing_columns(REAL_TABLE_TMDL, []) == REAL_TABLE_TMDL


def test_append_missing_columns_multiple_at_once():
    patched = append_missing_columns(
        REAL_TABLE_TMDL, [{"name": "a", "sql_type": "int"}, {"name": "b", "sql_type": "varchar"}]
    )
    names = [c["name"] for c in parse_table_columns(patched)]
    assert names == ["cuenta_contable", "importe", "a", "b"]


# --------------------------------------------------------------------------------------
# build_new_manual_model_parts / set_manual_table_columns -- no real data
# source (BC/HubSpot/Factorial/custom catalog items), columns typed by hand.
# --------------------------------------------------------------------------------------


def test_build_new_manual_model_parts_has_no_lakehouse_dependent_parts():
    parts = build_new_manual_model_parts(
        display_name="m",
        table="mi_tabla",
        columns=[{"name": "nombre", "data_type": "string"}, {"name": "edad", "data_type": "int64"}],
    )
    paths = {p["path"] for p in parts}
    # No definition/expressions.tmdl -- that's the DirectLake-only OneLake pointer.
    assert paths == {
        ".platform",
        "definition.pbism",
        "definition/database.tmdl",
        "definition/model.tmdl",
        "definition/tables/mi_tabla.tmdl",
    }


def test_build_new_manual_model_parts_table_tmdl_uses_a_datatable_partition():
    parts = build_new_manual_model_parts(
        display_name="m",
        table="mi_tabla",
        columns=[{"name": "nombre", "data_type": "string"}, {"name": "edad", "data_type": "int64"}],
    )
    table_part = next(p for p in parts if p["path"] == "definition/tables/mi_tabla.tmdl")
    text = base64.b64decode(table_part["payload"]).decode("utf-8")
    assert "column nombre" in text
    assert "dataType: string" in text
    assert "column edad" in text
    assert "dataType: int64" in text
    assert "mode: import" in text
    assert 'source = DATATABLE("nombre", STRING, "edad", INTEGER, {})' in text


def test_build_new_manual_model_parts_quotes_column_names_that_need_it():
    parts = build_new_manual_model_parts(
        display_name="m", table="t", columns=[{"name": "Fecha de alta", "data_type": "dateTime"}]
    )
    table_part = next(p for p in parts if p["path"] == "definition/tables/t.tmdl")
    text = base64.b64decode(table_part["payload"]).decode("utf-8")
    assert "column 'Fecha de alta'" in text
    assert 'DATATABLE("Fecha de alta", DATETIME, {})' in text


def test_build_new_manual_model_parts_rejects_no_columns():
    with pytest.raises(ValueError, match="al menos una columna"):
        build_new_manual_model_parts(display_name="m", table="t", columns=[])


def test_build_new_manual_model_parts_rejects_duplicate_column_names():
    with pytest.raises(ValueError, match="repetida"):
        build_new_manual_model_parts(
            display_name="m",
            table="t",
            columns=[{"name": "a", "data_type": "string"}, {"name": "a", "data_type": "int64"}],
        )


def test_set_manual_table_columns_adds_a_column_and_rebuilds_the_datatable_signature():
    parts = build_new_manual_model_parts(
        display_name="m", table="t", columns=[{"name": "a", "data_type": "string"}]
    )
    table_tmdl = base64.b64decode(next(p for p in parts if p["path"] == "definition/tables/t.tmdl")["payload"]).decode(
        "utf-8"
    )

    updated = set_manual_table_columns(
        table_tmdl, "t", [{"name": "a", "data_type": "string"}, {"name": "b", "data_type": "double"}]
    )

    names = [c["name"] for c in parse_table_columns(updated)]
    assert names == ["a", "b"]
    assert 'source = DATATABLE("a", STRING, "b", DOUBLE, {})' in updated


def test_set_manual_table_columns_removes_a_column_and_rebuilds_the_datatable_signature():
    parts = build_new_manual_model_parts(
        display_name="m",
        table="t",
        columns=[{"name": "a", "data_type": "string"}, {"name": "b", "data_type": "double"}],
    )
    table_tmdl = base64.b64decode(next(p for p in parts if p["path"] == "definition/tables/t.tmdl")["payload"]).decode(
        "utf-8"
    )

    updated = set_manual_table_columns(table_tmdl, "t", [{"name": "a", "data_type": "string"}])

    names = [c["name"] for c in parse_table_columns(updated)]
    assert names == ["a"]
    assert 'source = DATATABLE("a", STRING, {})' in updated


def test_set_manual_table_columns_preserves_an_existing_description():
    parts = build_new_manual_model_parts(
        display_name="m", table="t", columns=[{"name": "a", "data_type": "string"}]
    )
    table_tmdl = base64.b64decode(next(p for p in parts if p["path"] == "definition/tables/t.tmdl")["payload"]).decode(
        "utf-8"
    )
    with_desc = set_column_description(table_tmdl, "a", "Columna A.")

    updated = set_manual_table_columns(
        with_desc, "t", [{"name": "a", "data_type": "string"}, {"name": "b", "data_type": "int64"}]
    )

    by_name = {c["name"]: c["description"] for c in parse_table_columns(updated)}
    assert by_name["a"] == "Columna A."
    assert by_name["b"] == ""


def test_set_manual_table_columns_rejects_no_columns():
    with pytest.raises(ValueError, match="al menos una columna"):
        set_manual_table_columns("table t\n", "t", [])


def test_set_manual_table_columns_rejects_duplicate_column_names():
    with pytest.raises(ValueError, match="repetida"):
        set_manual_table_columns(
            "table t\n", "t", [{"name": "a", "data_type": "string"}, {"name": "a", "data_type": "int64"}]
        )


def test_build_new_manual_model_parts_rejects_a_blank_column_name():
    with pytest.raises(ValueError, match="no puede estar vacío"):
        build_new_manual_model_parts(display_name="m", table="t", columns=[{"name": "  ", "data_type": "string"}])


def test_build_new_manual_model_parts_rejects_an_unknown_data_type():
    with pytest.raises(ValueError, match="Tipo de dato desconocido"):
        build_new_manual_model_parts(display_name="m", table="t", columns=[{"name": "a", "data_type": "money"}])


def test_parse_table_name_reads_the_table_line():
    parts = build_new_manual_model_parts(display_name="m", table="mi_tabla", columns=[{"name": "a", "data_type": "string"}])
    table_tmdl = base64.b64decode(next(p for p in parts if p["path"] == "definition/tables/mi_tabla.tmdl")["payload"]).decode(
        "utf-8"
    )
    assert parse_table_name(table_tmdl) == "mi_tabla"


def test_parse_table_name_unquotes_a_quoted_table_name():
    parts = build_new_manual_model_parts(display_name="m", table="Mi Tabla", columns=[{"name": "a", "data_type": "string"}])
    table_tmdl = base64.b64decode(next(p for p in parts if p["path"] == "definition/tables/Mi Tabla.tmdl")["payload"]).decode(
        "utf-8"
    )
    assert parse_table_name(table_tmdl) == "Mi Tabla"
