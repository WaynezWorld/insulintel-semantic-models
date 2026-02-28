"""
Tests for semantic_diff.normalize_yaml — YAML loading, key normalisation,
and canonical conversion.
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from semantic_diff.normalize_yaml import (
    _snake,
    _normalize_keys,
    load_yaml_semantic_view,
)


# ---------------------------------------------------------------------------
# Tests: _snake (camelCase → snake_case)
# ---------------------------------------------------------------------------

class TestSnake:
    def test_already_snake(self):
        assert _snake("my_field") == "my_field"

    def test_camel_case(self):
        assert _snake("myField") == "my_field"

    def test_pascal_case(self):
        assert _snake("MyField") == "my_field"  # leading capital stays lowercase

    def test_multiple_humps(self):
        assert _snake("myLongFieldName") == "my_long_field_name"

    def test_all_lowercase(self):
        assert _snake("simple") == "simple"

    def test_adjacent_caps(self):
        assert _snake("getURL") == "get_url"  # regex treats URL as one chunk

    def test_empty_string(self):
        assert _snake("") == ""

    def test_single_char(self):
        assert _snake("x") == "x"


# ---------------------------------------------------------------------------
# Tests: _normalize_keys
# ---------------------------------------------------------------------------

class TestNormalizeKeys:
    def test_dict_keys(self):
        result = _normalize_keys({"dataType": "NUMBER", "baseName": "test"})
        assert "data_type" in result
        assert "base_name" in result

    def test_nested_dict(self):
        result = _normalize_keys({"outer": {"innerKey": "val"}})
        assert "inner_key" in result["outer"]

    def test_list_of_dicts(self):
        result = _normalize_keys([{"myKey": "val"}])
        assert "my_key" in result[0]

    def test_primitive_passthrough(self):
        assert _normalize_keys("hello") == "hello"
        assert _normalize_keys(42) == 42
        assert _normalize_keys(None) is None

    def test_empty_dict(self):
        assert _normalize_keys({}) == {}

    def test_empty_list(self):
        assert _normalize_keys([]) == []


# ---------------------------------------------------------------------------
# Tests: load_yaml_semantic_view
# ---------------------------------------------------------------------------

class TestLoadYamlSemanticView:
    def _write_yaml(self, path: Path, data: dict) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")
        return path

    def test_minimal_view(self, tmp_path: Path):
        data = {
            "name": "TEST_VIEW",
            "description": "Test view",
            "tables": [],
        }
        p = self._write_yaml(tmp_path / "test.yaml", data)
        view = load_yaml_semantic_view(p)
        assert view.name == "TEST_VIEW"
        assert view.description == "Test view"
        assert view.tables == []

    def test_dimensions_parsed(self, tmp_path: Path):
        data = {
            "name": "V",
            "tables": [{
                "name": "T1",
                "base_table": {"database": "DB", "schema": "SCH", "table": "T1"},
                "dimensions": [
                    {"name": "D1", "expr": "COL1", "data_type": "TEXT", "description": "dim1"},
                    {"name": "D2", "expr": "COL2", "data_type": "NUMBER", "description": "dim2"},
                ],
            }],
        }
        p = self._write_yaml(tmp_path / "v.yaml", data)
        view = load_yaml_semantic_view(p)
        assert len(view.tables) == 1
        assert len(view.tables[0].dimensions) == 2
        d1 = next(d for d in view.tables[0].dimensions if d.name == "D1")
        assert d1.expr == "COL1"
        assert d1.data_type == "TEXT"

    def test_facts_parsed(self, tmp_path: Path):
        data = {
            "name": "V",
            "tables": [{
                "name": "T1",
                "base_table": {"database": "DB", "schema": "SCH", "table": "T1"},
                "facts": [
                    {"name": "F1", "expr": "col", "data_type": "NUMBER"},
                ],
            }],
        }
        p = self._write_yaml(tmp_path / "v.yaml", data)
        view = load_yaml_semantic_view(p)
        assert len(view.tables[0].facts) == 1
        assert view.tables[0].facts[0].name == "F1"

    def test_metrics_parsed(self, tmp_path: Path):
        data = {
            "name": "V",
            "tables": [{
                "name": "T1",
                "base_table": {},
                "metrics": [
                    {"name": "M1", "expr": "SUM(col)", "description": "total"},
                ],
            }],
        }
        p = self._write_yaml(tmp_path / "v.yaml", data)
        view = load_yaml_semantic_view(p)
        assert view.tables[0].metrics[0].name == "M1"

    def test_relationships_parsed(self, tmp_path: Path):
        data = {
            "name": "V",
            "tables": [],
            "relationships": [{
                "name": "R1",
                "left_table": "T1",
                "right_table": "T2",
                "relationship_columns": [
                    {"left_column": "id", "right_column": "t1_id"},
                ],
                "relationship_type": "many_to_one",
            }],
        }
        p = self._write_yaml(tmp_path / "v.yaml", data)
        view = load_yaml_semantic_view(p)
        assert len(view.relationships) == 1
        assert view.relationships[0].name == "R1"
        assert view.relationships[0].relationship_type == "many_to_one"
        assert len(view.relationships[0].relationship_columns) == 1

    def test_custom_instructions_parsed(self, tmp_path: Path):
        data = {
            "name": "V",
            "tables": [],
            "custom_instructions": {
                "question_categorization": "QC text",
                "sql_generation": "SG text",
            },
        }
        p = self._write_yaml(tmp_path / "v.yaml", data)
        view = load_yaml_semantic_view(p)
        assert view.custom_instructions.question_categorization == "QC text"
        assert view.custom_instructions.sql_generation == "SG text"

    def test_camel_case_keys_normalized(self, tmp_path: Path):
        """Verify camelCase keys in YAML are converted to snake_case."""
        data = {
            "name": "V",
            "tables": [{
                "name": "T1",
                "baseTable": {"database": "DB", "schema": "SCH", "table": "T"},
                "dimensions": [
                    {"name": "D1", "expr": "COL", "dataType": "TEXT"},
                ],
            }],
        }
        p = self._write_yaml(tmp_path / "v.yaml", data)
        view = load_yaml_semantic_view(p)
        assert view.tables[0].base_table.database == "DB"
        assert view.tables[0].dimensions[0].data_type == "TEXT"

    def test_primary_key(self, tmp_path: Path):
        data = {
            "name": "V",
            "tables": [{
                "name": "T1",
                "base_table": {},
                "primary_key": {"columns": ["id", "type"]},
            }],
        }
        p = self._write_yaml(tmp_path / "v.yaml", data)
        view = load_yaml_semantic_view(p)
        pk = view.tables[0].primary_key
        assert pk is not None
        assert sorted(pk.columns) == ["id", "type"]

    def test_tables_sorted_by_name(self, tmp_path: Path):
        data = {
            "name": "V",
            "tables": [
                {"name": "ZZZ", "base_table": {}},
                {"name": "AAA", "base_table": {}},
            ],
        }
        p = self._write_yaml(tmp_path / "v.yaml", data)
        view = load_yaml_semantic_view(p)
        assert view.tables[0].name == "AAA"
        assert view.tables[1].name == "ZZZ"

    def test_real_repo_views_load(self):
        """Smoke test: load all three real repo semantic view YAMLs."""
        repo_root = Path(__file__).resolve().parents[1]
        views_dir = repo_root / "semantic_views"
        for yaml_file in views_dir.glob("*.yaml"):
            view = load_yaml_semantic_view(yaml_file)
            assert view.name, f"{yaml_file.name} should have a name"
            assert len(view.tables) > 0, f"{yaml_file.name} should have tables"
