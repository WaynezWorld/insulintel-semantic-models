"""
Tests for semantic_diff.normalize_sf — Snowflake DESCRIBE SEMANTIC VIEW
CSV/JSON parsing and canonical conversion.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from semantic_diff.normalize_sf import (
    _read_csv,
    _extract_extension_json,
    _parse_base_table,
    _parse_dimension,
    _parse_fact,
    _parse_metric,
    _parse_key,
    _parse_rel_col,
    _parse_relationship,
    _parse_table,
    _parse_custom_instructions,
    load_snowflake_describe,
    load_snowflake_json,
)
from semantic_diff.canonical import (
    BaseTable,
    CustomInstructions,
    Dimension,
    Fact,
    KeySpec,
    Metric,
    Relationship,
    RelationshipColumn,
    SemanticView,
    Table,
)


# ---------------------------------------------------------------------------
# Helpers — build CSV files that mimic SnowSQL DESCRIBE output
# ---------------------------------------------------------------------------

def _make_describe_csv(
    path: Path,
    extension_json: dict,
    *,
    encoding: str = "utf-8-sig",
    extra_rows: list | None = None,
) -> Path:
    """Write a CSV that mimics ``DESCRIBE SEMANTIC VIEW`` output."""
    rows = extra_rows or []
    rows.append({
        "object_kind": "EXTENSION",
        "object_name": "CA",
        "property": "VALUE",
        "property_value": json.dumps(extension_json),
    })
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding=encoding) as f:
        writer = csv.DictWriter(
            f, fieldnames=["object_kind", "object_name", "property", "property_value"]
        )
        writer.writeheader()
        writer.writerows(rows)
    return path


def _minimal_view_json(*, name: str = "TEST_VIEW", **overrides) -> dict:
    """Return a minimal valid semantic-view JSON dict."""
    base = {
        "name": name,
        "description": "A test view",
        "tables": [],
        "relationships": [],
    }
    base.update(overrides)
    return base


# ===================================================================
# _read_csv
# ===================================================================

class TestReadCsv:
    def test_utf8_sig(self, tmp_path: Path):
        p = _make_describe_csv(tmp_path / "utf8.csv", {"name": "V"}, encoding="utf-8-sig")
        rows = _read_csv(p)
        assert len(rows) == 1
        assert rows[0]["object_kind"] == "EXTENSION"

    def test_utf16(self, tmp_path: Path):
        p = tmp_path / "utf16.csv"
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", newline="", encoding="utf-16") as f:
            writer = csv.DictWriter(
                f, fieldnames=["object_kind", "object_name", "property", "property_value"]
            )
            writer.writeheader()
            writer.writerow({
                "object_kind": "EXTENSION",
                "object_name": "CA",
                "property": "VALUE",
                "property_value": '{"name":"V"}',
            })
        rows = _read_csv(p)
        assert len(rows) == 1

    def test_cp1252(self, tmp_path: Path):
        p = _make_describe_csv(tmp_path / "cp.csv", {"name": "V"}, encoding="cp1252")
        rows = _read_csv(p)
        assert len(rows) == 1

    def test_bad_encoding_raises(self, tmp_path: Path):
        p = tmp_path / "bad.csv"
        # Write bytes that are invalid under all attempted encodings
        p.write_bytes(bytes(range(128, 256)) * 20)
        with pytest.raises((RuntimeError, Exception)):
            _read_csv(p)


# ===================================================================
# _extract_extension_json
# ===================================================================

class TestExtractExtensionJson:
    def test_happy_path(self):
        rows = [
            {"object_kind": "TABLE", "object_name": "X", "property": "Y", "property_value": "Z"},
            {"object_kind": "EXTENSION", "object_name": "CA", "property": "VALUE",
             "property_value": '{"name":"V","tables":[]}'},
        ]
        result = _extract_extension_json(rows)
        assert result["name"] == "V"
        assert result["tables"] == []

    def test_missing_extension_row_raises(self):
        rows = [
            {"object_kind": "TABLE", "object_name": "X", "property": "Y", "property_value": "Z"},
        ]
        with pytest.raises(ValueError, match="No EXTENSION/CA/VALUE row"):
            _extract_extension_json(rows)

    def test_wrong_object_name_ignored(self):
        rows = [
            {"object_kind": "EXTENSION", "object_name": "OTHER", "property": "VALUE",
             "property_value": '{"name":"X"}'},
        ]
        with pytest.raises(ValueError, match="No EXTENSION/CA/VALUE row"):
            _extract_extension_json(rows)

    def test_wrong_property_ignored(self):
        rows = [
            {"object_kind": "EXTENSION", "object_name": "CA", "property": "OTHER",
             "property_value": '{"name":"X"}'},
        ]
        with pytest.raises(ValueError, match="No EXTENSION/CA/VALUE row"):
            _extract_extension_json(rows)

    def test_invalid_json_raises(self):
        rows = [
            {"object_kind": "EXTENSION", "object_name": "CA", "property": "VALUE",
             "property_value": "NOT-JSON"},
        ]
        with pytest.raises(json.JSONDecodeError):
            _extract_extension_json(rows)


# ===================================================================
# Individual parsers
# ===================================================================

class TestParseBaseTable:
    def test_full(self):
        bt = _parse_base_table({"database": "DB", "schema": "SCH", "table": "T1"})
        assert bt == BaseTable(database="DB", schema="SCH", table="T1")

    def test_empty_dict(self):
        bt = _parse_base_table({})
        assert bt == BaseTable()

    def test_partial(self):
        bt = _parse_base_table({"database": "DB"})
        assert bt.database == "DB"
        assert bt.schema == ""
        assert bt.table == ""


class TestParseDimension:
    def test_full(self):
        d = _parse_dimension({
            "name": "D1", "expr": "COL", "data_type": "TEXT", "description": "desc"
        })
        assert d == Dimension(name="D1", expr="COL", data_type="TEXT", description="desc")

    def test_empty(self):
        d = _parse_dimension({})
        assert d == Dimension()

    def test_missing_optional_fields(self):
        d = _parse_dimension({"name": "D1", "expr": "COL"})
        assert d.data_type == ""
        assert d.description == ""


class TestParseFact:
    def test_full(self):
        f = _parse_fact({
            "name": "F1", "expr": "COL", "data_type": "NUMBER",
            "description": "desc", "access_modifier": "PROTECTED",
        })
        assert f == Fact(
            name="F1", expr="COL", data_type="NUMBER",
            description="desc", access_modifier="PROTECTED",
        )

    def test_empty(self):
        f = _parse_fact({})
        assert f == Fact()


class TestParseMetric:
    def test_full(self):
        m = _parse_metric({
            "name": "M1", "expr": "SUM(col)", "description": "total",
            "access_modifier": "PUBLIC",
        })
        assert m == Metric(
            name="M1", expr="SUM(col)", description="total",
            access_modifier="PUBLIC",
        )

    def test_empty(self):
        m = _parse_metric({})
        assert m == Metric()


class TestParseKey:
    def test_columns_sorted(self):
        k = _parse_key({"columns": ["z_col", "a_col"]})
        assert k == KeySpec(columns=["a_col", "z_col"])

    def test_empty(self):
        k = _parse_key({})
        assert k == KeySpec(columns=[])


class TestParseRelCol:
    def test_full(self):
        rc = _parse_rel_col({"left_column": "id", "right_column": "fk_id"})
        assert rc == RelationshipColumn(left_column="id", right_column="fk_id")

    def test_empty(self):
        rc = _parse_rel_col({})
        assert rc == RelationshipColumn()


class TestParseRelationship:
    def test_full(self):
        r = _parse_relationship({
            "name": "R1",
            "left_table": "T1",
            "right_table": "T2",
            "relationship_columns": [
                {"left_column": "id", "right_column": "t1_id"},
            ],
            "relationship_type": "many_to_one",
        })
        assert r.name == "R1"
        assert r.left_table == "T1"
        assert r.right_table == "T2"
        assert len(r.relationship_columns) == 1
        assert r.relationship_type == "many_to_one"

    def test_empty(self):
        r = _parse_relationship({})
        assert r == Relationship()

    def test_multiple_join_columns(self):
        r = _parse_relationship({
            "name": "R2",
            "left_table": "A",
            "right_table": "B",
            "relationship_columns": [
                {"left_column": "id1", "right_column": "fk1"},
                {"left_column": "id2", "right_column": "fk2"},
            ],
            "relationship_type": "one_to_one",
        })
        assert len(r.relationship_columns) == 2


class TestParseTable:
    def test_full_table(self):
        t = _parse_table({
            "name": "T1",
            "description": "test table",
            "base_table": {"database": "DB", "schema": "SCH", "table": "T1"},
            "dimensions": [
                {"name": "D1", "expr": "COL1", "data_type": "TEXT", "description": "dim"},
            ],
            "facts": [
                {"name": "F1", "expr": "COL2", "data_type": "NUMBER", "description": "fact"},
            ],
            "metrics": [
                {"name": "M1", "expr": "SUM(COL2)", "description": "total"},
            ],
            "primary_key": {"columns": ["id"]},
            "unique_keys": [{"columns": ["code"]}],
        })
        assert t.name == "T1"
        assert t.base_table.database == "DB"
        assert len(t.dimensions) == 1
        assert len(t.facts) == 1
        assert len(t.metrics) == 1
        assert t.primary_key == KeySpec(columns=["id"])
        assert len(t.unique_keys) == 1

    def test_no_primary_key(self):
        t = _parse_table({"name": "T"})
        assert t.primary_key is None

    def test_dimensions_sorted(self):
        t = _parse_table({
            "name": "T",
            "dimensions": [
                {"name": "Z_DIM", "expr": "Z"},
                {"name": "A_DIM", "expr": "A"},
            ],
        })
        assert t.dimensions[0].name == "A_DIM"
        assert t.dimensions[1].name == "Z_DIM"

    def test_facts_sorted(self):
        t = _parse_table({
            "name": "T",
            "facts": [
                {"name": "Z_FACT", "expr": "Z"},
                {"name": "A_FACT", "expr": "A"},
            ],
        })
        assert t.facts[0].name == "A_FACT"
        assert t.facts[1].name == "Z_FACT"

    def test_metrics_sorted(self):
        t = _parse_table({
            "name": "T",
            "metrics": [
                {"name": "Z_METRIC", "expr": "Z"},
                {"name": "A_METRIC", "expr": "A"},
            ],
        })
        assert t.metrics[0].name == "A_METRIC"
        assert t.metrics[1].name == "Z_METRIC"

    def test_unique_keys_sorted(self):
        t = _parse_table({
            "name": "T",
            "unique_keys": [
                {"columns": ["z_col"]},
                {"columns": ["a_col"]},
            ],
        })
        assert t.unique_keys[0].columns == ["a_col"]
        assert t.unique_keys[1].columns == ["z_col"]


class TestParseCustomInstructions:
    def test_full(self):
        ci = _parse_custom_instructions({
            "custom_instructions": {
                "question_categorization": "QC text",
                "sql_generation": "SG text",
            }
        })
        assert ci.question_categorization == "QC text"
        assert ci.sql_generation == "SG text"

    def test_missing_custom_instructions(self):
        ci = _parse_custom_instructions({})
        assert ci == CustomInstructions()

    def test_partial(self):
        ci = _parse_custom_instructions({
            "custom_instructions": {"sql_generation": "SG only"}
        })
        assert ci.question_categorization == ""
        assert ci.sql_generation == "SG only"


# ===================================================================
# load_snowflake_json (dict → SemanticView)
# ===================================================================

class TestLoadSnowflakeJson:
    def test_minimal(self):
        data = _minimal_view_json()
        view = load_snowflake_json(data)
        assert view.name == "TEST_VIEW"
        assert view.description == "A test view"
        assert view.tables == []
        assert view.relationships == []
        assert view.custom_instructions == CustomInstructions()

    def test_tables_sorted(self):
        data = _minimal_view_json(tables=[
            {"name": "ZZZ", "base_table": {}},
            {"name": "AAA", "base_table": {}},
        ])
        view = load_snowflake_json(data)
        assert view.tables[0].name == "AAA"
        assert view.tables[1].name == "ZZZ"

    def test_relationships_sorted(self):
        data = _minimal_view_json(relationships=[
            {"name": "R_ZZZ", "left_table": "A", "right_table": "B",
             "relationship_columns": [], "relationship_type": "many_to_one"},
            {"name": "R_AAA", "left_table": "C", "right_table": "D",
             "relationship_columns": [], "relationship_type": "one_to_one"},
        ])
        view = load_snowflake_json(data)
        assert view.relationships[0].name == "R_AAA"
        assert view.relationships[1].name == "R_ZZZ"

    def test_custom_instructions(self):
        data = _minimal_view_json(custom_instructions={
            "question_categorization": "QC",
            "sql_generation": "SG",
        })
        view = load_snowflake_json(data)
        assert view.custom_instructions.question_categorization == "QC"
        assert view.custom_instructions.sql_generation == "SG"

    def test_full_round_trip(self):
        """Comprehensive view with all field types populated."""
        data = {
            "name": "FULL_VIEW",
            "description": "Full integration test",
            "tables": [{
                "name": "PATIENT",
                "description": "Patient demographics",
                "base_table": {"database": "PROD", "schema": "PUBLIC", "table": "PATIENT"},
                "dimensions": [
                    {"name": "AGE", "expr": "AGE_COL", "data_type": "NUMBER", "description": "Patient age"},
                    {"name": "GENDER", "expr": "GENDER_COL", "data_type": "TEXT", "description": "Gender"},
                ],
                "facts": [
                    {"name": "GLUCOSE", "expr": "GLUCOSE_VAL", "data_type": "FLOAT",
                     "description": "Blood glucose", "access_modifier": "PUBLIC"},
                ],
                "metrics": [
                    {"name": "AVG_GLUCOSE", "expr": "AVG(GLUCOSE_VAL)", "description": "Average glucose"},
                ],
                "primary_key": {"columns": ["PATIENT_ID"]},
                "unique_keys": [{"columns": ["SSN"]}],
            }],
            "relationships": [{
                "name": "PATIENT_READINGS",
                "left_table": "PATIENT",
                "right_table": "READINGS",
                "relationship_columns": [
                    {"left_column": "PATIENT_ID", "right_column": "PATIENT_ID"},
                ],
                "relationship_type": "one_to_many",
            }],
            "custom_instructions": {
                "question_categorization": "Categorize questions by clinical domain",
                "sql_generation": "Always filter by active patients",
            },
        }
        view = load_snowflake_json(data)
        assert view.name == "FULL_VIEW"
        assert len(view.tables) == 1
        t = view.tables[0]
        assert t.name == "PATIENT"
        assert t.base_table == BaseTable(database="PROD", schema="PUBLIC", table="PATIENT")
        assert len(t.dimensions) == 2
        assert len(t.facts) == 1
        assert t.facts[0].access_modifier == "PUBLIC"
        assert len(t.metrics) == 1
        assert t.primary_key == KeySpec(columns=["PATIENT_ID"])
        assert len(t.unique_keys) == 1
        assert len(view.relationships) == 1
        assert view.relationships[0].relationship_type == "one_to_many"
        assert view.custom_instructions.sql_generation == "Always filter by active patients"

    def test_empty_name_fallback(self):
        view = load_snowflake_json({})
        assert view.name == ""

    def test_missing_description(self):
        view = load_snowflake_json({"name": "V"})
        assert view.description == ""


# ===================================================================
# load_snowflake_describe (CSV file → SemanticView)
# ===================================================================

class TestLoadSnowflakeDescribe:
    def test_minimal_csv(self, tmp_path: Path):
        data = _minimal_view_json(name="CSV_VIEW")
        p = _make_describe_csv(tmp_path / "desc.csv", data)
        view = load_snowflake_describe(p)
        assert view.name == "CSV_VIEW"
        assert view.tables == []

    def test_view_name_fallback_when_key_missing(self, tmp_path: Path):
        """view_name is used as fallback when 'name' key is absent from JSON."""
        data = {"description": "no name key", "tables": [], "relationships": []}
        p = _make_describe_csv(tmp_path / "desc.csv", data)
        view = load_snowflake_describe(p, view_name="FALLBACK")
        assert view.name == "FALLBACK"

    def test_empty_name_stays_empty(self, tmp_path: Path):
        """When name key exists but is empty, view_name does NOT override."""
        data = _minimal_view_json(name="")
        p = _make_describe_csv(tmp_path / "desc.csv", data)
        view = load_snowflake_describe(p, view_name="IGNORED")
        assert view.name == ""

    def test_view_name_from_json_takes_precedence(self, tmp_path: Path):
        data = _minimal_view_json(name="FROM_JSON")
        p = _make_describe_csv(tmp_path / "desc.csv", data)
        view = load_snowflake_describe(p, view_name="FALLBACK")
        assert view.name == "FROM_JSON"

    def test_full_csv_round_trip(self, tmp_path: Path):
        """End-to-end: write CSV with tables, relationships, instructions → parse."""
        data = {
            "name": "E2E_VIEW",
            "description": "End-to-end test",
            "tables": [
                {
                    "name": "READINGS",
                    "description": "Glucose readings",
                    "base_table": {"database": "DB", "schema": "SCH", "table": "READINGS"},
                    "dimensions": [
                        {"name": "DATE", "expr": "READ_DATE", "data_type": "DATE", "description": "Read date"},
                    ],
                    "facts": [
                        {"name": "VALUE", "expr": "READ_VAL", "data_type": "FLOAT", "description": "Glucose value"},
                    ],
                    "metrics": [
                        {"name": "AVG_VAL", "expr": "AVG(READ_VAL)", "description": "Average reading"},
                    ],
                    "primary_key": {"columns": ["READ_ID"]},
                },
                {
                    "name": "ACTIVITIES",
                    "description": "Activity log",
                    "base_table": {"database": "DB", "schema": "SCH", "table": "ACTIVITIES"},
                    "dimensions": [],
                    "facts": [],
                },
            ],
            "relationships": [{
                "name": "ACT_READ",
                "left_table": "ACTIVITIES",
                "right_table": "READINGS",
                "relationship_columns": [
                    {"left_column": "PATIENT_ID", "right_column": "PATIENT_ID"},
                ],
                "relationship_type": "many_to_one",
            }],
            "custom_instructions": {
                "question_categorization": "Focus on diabetes management",
                "sql_generation": "Use metric aliases when possible",
            },
        }
        p = _make_describe_csv(tmp_path / "e2e.csv", data)
        view = load_snowflake_describe(p)

        assert view.name == "E2E_VIEW"
        assert len(view.tables) == 2
        # Tables sorted alphabetically
        assert view.tables[0].name == "ACTIVITIES"
        assert view.tables[1].name == "READINGS"

        readings = view.tables[1]
        assert len(readings.dimensions) == 1
        assert len(readings.facts) == 1
        assert len(readings.metrics) == 1
        assert readings.primary_key == KeySpec(columns=["READ_ID"])

        assert len(view.relationships) == 1
        assert view.relationships[0].name == "ACT_READ"
        assert view.custom_instructions.question_categorization == "Focus on diabetes management"

    def test_extra_rows_ignored(self, tmp_path: Path):
        """Non-EXTENSION rows in the CSV should be silently skipped."""
        extra = [
            {"object_kind": "TABLE", "object_name": "T1", "property": "NAME", "property_value": "T1"},
            {"object_kind": "COLUMN", "object_name": "COL1", "property": "TYPE", "property_value": "TEXT"},
        ]
        data = _minimal_view_json(name="WITH_EXTRAS")
        p = _make_describe_csv(tmp_path / "extra.csv", data, extra_rows=extra)
        view = load_snowflake_describe(p)
        assert view.name == "WITH_EXTRAS"

    def test_utf16_csv(self, tmp_path: Path):
        """Verify UTF-16 encoded CSVs (common from SnowSQL) are handled."""
        data = _minimal_view_json(name="UTF16_VIEW")
        p = tmp_path / "utf16.csv"
        rows = [{
            "object_kind": "EXTENSION",
            "object_name": "CA",
            "property": "VALUE",
            "property_value": json.dumps(data),
        }]
        with open(p, "w", newline="", encoding="utf-16") as f:
            writer = csv.DictWriter(
                f, fieldnames=["object_kind", "object_name", "property", "property_value"]
            )
            writer.writeheader()
            writer.writerows(rows)
        view = load_snowflake_describe(p)
        assert view.name == "UTF16_VIEW"

    def test_no_extension_row_raises(self, tmp_path: Path):
        """CSV with no EXTENSION/CA/VALUE row should raise ValueError."""
        p = tmp_path / "bad.csv"
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f, fieldnames=["object_kind", "object_name", "property", "property_value"]
            )
            writer.writeheader()
            writer.writerow({
                "object_kind": "TABLE", "object_name": "T",
                "property": "NAME", "property_value": "T",
            })
        with pytest.raises(ValueError, match="No EXTENSION/CA/VALUE row"):
            load_snowflake_describe(p)


# ===================================================================
# Parity: load_snowflake_json == load_snowflake_describe for same data
# ===================================================================

class TestJsonCsvParity:
    """The same semantic-view data should produce identical canonical objects
    whether loaded from JSON dict or from a DESCRIBE CSV."""

    def test_parity_minimal(self, tmp_path: Path):
        data = _minimal_view_json()
        view_json = load_snowflake_json(data)
        p = _make_describe_csv(tmp_path / "par.csv", data)
        view_csv = load_snowflake_describe(p)
        assert view_json == view_csv

    def test_parity_complex(self, tmp_path: Path):
        data = {
            "name": "PARITY",
            "description": "Parity check",
            "tables": [
                {
                    "name": "T2",
                    "description": "Second table",
                    "base_table": {"database": "DB", "schema": "S", "table": "T2"},
                    "dimensions": [
                        {"name": "D1", "expr": "C1", "data_type": "TEXT", "description": "d1"},
                    ],
                    "facts": [
                        {"name": "F1", "expr": "C2", "data_type": "NUMBER",
                         "description": "f1", "access_modifier": ""},
                    ],
                    "metrics": [],
                    "primary_key": {"columns": ["id"]},
                    "unique_keys": [],
                },
                {
                    "name": "T1",
                    "description": "First table",
                    "base_table": {"database": "DB", "schema": "S", "table": "T1"},
                    "dimensions": [],
                    "facts": [],
                    "metrics": [
                        {"name": "M1", "expr": "COUNT(*)", "description": "count"},
                    ],
                },
            ],
            "relationships": [{
                "name": "T1_T2",
                "left_table": "T1",
                "right_table": "T2",
                "relationship_columns": [
                    {"left_column": "id", "right_column": "t1_id"},
                ],
                "relationship_type": "one_to_many",
            }],
            "custom_instructions": {
                "question_categorization": "QC",
                "sql_generation": "SG",
            },
        }
        view_json = load_snowflake_json(data)
        p = _make_describe_csv(tmp_path / "par.csv", data)
        view_csv = load_snowflake_describe(p)
        assert view_json == view_csv
