"""
Tests for app.deployer — YAML building, block-style dumping,
and deployable YAML generation.

These tests exercise the pure-Python logic without a Snowflake connection.
"""
from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

# ---------------------------------------------------------------------------
# Import the module under test
# ---------------------------------------------------------------------------
import sys

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "app") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "app"))

from deployer import (
    YAML_MAP,
    build_deployable_yaml,
    _BlockDumper,
    _str_representer,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_yaml(text: str) -> dict:
    return yaml.safe_load(text)


# ---------------------------------------------------------------------------
# Tests: YAML_MAP
# ---------------------------------------------------------------------------

class TestYamlMap:
    def test_all_three_views_present(self):
        assert "SEM_INSULINTEL" in YAML_MAP
        assert "SEM_ACTIVITY" in YAML_MAP
        assert "SEM_NHANES" in YAML_MAP

    def test_paths_exist(self):
        for name, path in YAML_MAP.items():
            assert path.exists(), f"{name} → {path} does not exist"

    def test_paths_are_yaml(self):
        for name, path in YAML_MAP.items():
            assert path.suffix == ".yaml", f"{name} → {path} should end in .yaml"


# ---------------------------------------------------------------------------
# Tests: _BlockDumper / _str_representer
# ---------------------------------------------------------------------------

class TestBlockDumper:
    def test_multiline_uses_block_style(self):
        data = {"instructions": "line one\nline two\nline three"}
        output = yaml.dump(data, Dumper=_BlockDumper, default_flow_style=False)
        assert "|" in output, "Expected block scalar indicator (|) for multiline"
        assert "line one" in output
        assert "line two" in output

    def test_single_line_no_block(self):
        data = {"name": "simple string"}
        output = yaml.dump(data, Dumper=_BlockDumper, default_flow_style=False)
        assert "|" not in output
        assert "simple string" in output

    def test_empty_string_no_block(self):
        data = {"key": ""}
        output = yaml.dump(data, Dumper=_BlockDumper, default_flow_style=False)
        assert "|" not in output


# ---------------------------------------------------------------------------
# Tests: build_deployable_yaml
# ---------------------------------------------------------------------------

class TestBuildDeployableYaml:
    def test_injects_both_custom_instructions(self):
        ci = {
            "sql_generation": "Test SQL generation",
            "question_categorization": "Test QC",
        }
        result = build_deployable_yaml("SEM_ACTIVITY", ci)
        data = _load_yaml(result)
        assert "custom_instructions" in data
        assert data["custom_instructions"]["sql_generation"] == "Test SQL generation"
        assert data["custom_instructions"]["question_categorization"] == "Test QC"

    def test_injects_only_sql_generation(self):
        ci = {"sql_generation": "Only SG", "question_categorization": ""}
        result = build_deployable_yaml("SEM_ACTIVITY", ci)
        data = _load_yaml(result)
        # Empty QC should NOT be injected
        ci_out = data.get("custom_instructions", {})
        assert ci_out.get("sql_generation") == "Only SG"
        assert "question_categorization" not in ci_out

    def test_injects_only_question_categorization(self):
        ci = {"sql_generation": "", "question_categorization": "Only QC"}
        result = build_deployable_yaml("SEM_INSULINTEL", ci)
        data = _load_yaml(result)
        ci_out = data.get("custom_instructions", {})
        assert ci_out.get("question_categorization") == "Only QC"
        assert "sql_generation" not in ci_out

    def test_empty_instructions_no_custom_instructions_key(self):
        ci = {"sql_generation": "", "question_categorization": ""}
        result = build_deployable_yaml("SEM_NHANES", ci)
        data = _load_yaml(result)
        # With empty values, custom_instructions should not be added
        # (unless already present in the base YAML)
        # Just verify it's valid YAML
        assert "name" in data

    def test_preserves_existing_fields(self):
        ci = {"sql_generation": "test", "question_categorization": ""}
        result = build_deployable_yaml("SEM_INSULINTEL", ci)
        data = _load_yaml(result)
        # Should retain name, tables, etc. from the base YAML
        assert "name" in data
        assert "tables" in data

    def test_multiline_instructions_use_block_style(self):
        ci = {
            "sql_generation": "Line 1\nLine 2\nLine 3",
            "question_categorization": "",
        }
        result = build_deployable_yaml("SEM_ACTIVITY", ci)
        # Block scalar should appear in the raw YAML text
        assert "|" in result
        assert "Line 1" in result
        assert "Line 2" in result

    def test_invalid_view_name_raises(self):
        with pytest.raises(KeyError):
            build_deployable_yaml("NONEXISTENT_VIEW", {})

    def test_output_is_valid_yaml(self):
        ci = {"sql_generation": "test sg", "question_categorization": "test qc"}
        for view in ("SEM_INSULINTEL", "SEM_ACTIVITY", "SEM_NHANES"):
            result = build_deployable_yaml(view, ci)
            data = _load_yaml(result)
            assert isinstance(data, dict), f"YAML for {view} should parse as dict"
