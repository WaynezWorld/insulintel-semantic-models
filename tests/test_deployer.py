"""
Tests for app.deployer — YAML building, block-style dumping,
deployable YAML generation, and deploy operations.

These tests exercise the pure-Python logic without a Snowflake connection.
"""
from __future__ import annotations

import re
import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch, call

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
    deploy_semantic_view,
    deploy_agent_field,
    deploy_all_from_repo,
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
    def test_strips_custom_instructions(self):
        """build_deployable_yaml must NOT include custom_instructions —
        Snowflake rejects them in YAML payloads."""
        result = build_deployable_yaml("SEM_ACTIVITY")
        data = _load_yaml(result)
        assert "custom_instructions" not in data

    def test_custom_instructions_param_ignored(self):
        """The optional custom_instructions param is ignored (backward compat)."""
        ci = {
            "sql_generation": "Test SQL generation",
            "question_categorization": "Test QC",
        }
        result = build_deployable_yaml("SEM_ACTIVITY", ci)
        data = _load_yaml(result)
        assert "custom_instructions" not in data

    def test_strips_custom_instructions_all_views(self):
        for view in ("SEM_INSULINTEL", "SEM_ACTIVITY", "SEM_NHANES"):
            result = build_deployable_yaml(view)
            data = _load_yaml(result)
            assert "custom_instructions" not in data, f"{view} still has custom_instructions"

    def test_preserves_existing_fields(self):
        result = build_deployable_yaml("SEM_INSULINTEL")
        data = _load_yaml(result)
        assert "name" in data
        assert "tables" in data

    def test_preserves_name_field(self):
        for view in ("SEM_INSULINTEL", "SEM_ACTIVITY", "SEM_NHANES"):
            result = build_deployable_yaml(view)
            data = _load_yaml(result)
            assert data["name"] == view

    def test_invalid_view_name_raises(self):
        with pytest.raises(KeyError):
            build_deployable_yaml("NONEXISTENT_VIEW")

    def test_output_is_valid_yaml(self):
        for view in ("SEM_INSULINTEL", "SEM_ACTIVITY", "SEM_NHANES"):
            result = build_deployable_yaml(view)
            data = _load_yaml(result)
            assert isinstance(data, dict), f"YAML for {view} should parse as dict"

    def test_no_custom_instructions_param_works(self):
        """Calling without custom_instructions (default None) still works."""
        result = build_deployable_yaml("SEM_NHANES")
        data = _load_yaml(result)
        assert "name" in data
        assert "custom_instructions" not in data


# ---------------------------------------------------------------------------
# Tests: deploy_semantic_view (2-step, mocked Snowflake)
# ---------------------------------------------------------------------------

class TestDeploySemanticView:
    """Test the 2-step deploy logic with a mocked Snowflake connection."""

    def _make_mock_conn(self, ddl_text="CREATE OR REPLACE SEMANTIC VIEW DB.SCH.V1 AS ..."):
        """Build a mock connection with a cursor that returns DDL."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        # fetchone returns DDL for GET_DDL call
        mock_cursor.fetchone.side_effect = [
            ("OK",),   # Step 1: SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML result
            (ddl_text,),  # Step 2: GET_DDL result
        ]
        return mock_conn, mock_cursor

    def test_calls_create_from_yaml_first(self):
        conn, cursor = self._make_mock_conn()
        ci = {"sql_generation": "test sg", "question_categorization": "test qc"}
        result = deploy_semantic_view(conn, "SEM_ACTIVITY", ci)
        assert result.startswith("✅")
        # First execute call should be SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML
        first_call = cursor.execute.call_args_list[0]
        assert "SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML" in first_call[0][0]

    def test_calls_get_ddl_second(self):
        conn, cursor = self._make_mock_conn()
        ci = {"sql_generation": "test sg", "question_categorization": ""}
        deploy_semantic_view(conn, "SEM_ACTIVITY", ci)
        second_call = cursor.execute.call_args_list[1]
        assert "GET_DDL" in second_call[0][0]

    def test_appends_ai_clauses(self):
        ddl = "CREATE OR REPLACE SEMANTIC VIEW DB_INSULINTEL.SCH_SEMANTIC.SEM_ACTIVITY AS ..."
        conn, cursor = self._make_mock_conn(ddl)
        ci = {"sql_generation": "my sg text", "question_categorization": "my qc text"}
        deploy_semantic_view(conn, "SEM_ACTIVITY", ci)
        # Third execute should be the CREATE OR REPLACE with AI clauses
        third_call = cursor.execute.call_args_list[2]
        sql = third_call[0][0]
        assert "AI_SQL_GENERATION" in sql
        assert "AI_QUESTION_CATEGORIZATION" in sql
        assert "my sg text" in sql
        assert "my qc text" in sql

    def test_includes_copy_grants(self):
        ddl = "CREATE OR REPLACE SEMANTIC VIEW DB_INSULINTEL.SCH_SEMANTIC.SEM_ACTIVITY AS ..."
        conn, cursor = self._make_mock_conn(ddl)
        ci = {"sql_generation": "sg", "question_categorization": ""}
        deploy_semantic_view(conn, "SEM_ACTIVITY", ci)
        third_call = cursor.execute.call_args_list[2]
        assert "COPY GRANTS" in third_call[0][0]

    def test_empty_ci_skips_step2(self):
        conn, cursor = self._make_mock_conn()
        ci = {"sql_generation": "", "question_categorization": ""}
        result = deploy_semantic_view(conn, "SEM_ACTIVITY", ci)
        assert result.startswith("✅")
        # Should only have 1 execute call (YAML deploy), no GET_DDL
        assert cursor.execute.call_count == 1

    def test_escapes_single_quotes_in_ci(self):
        ddl = "CREATE OR REPLACE SEMANTIC VIEW DB_INSULINTEL.SCH_SEMANTIC.SEM_ACTIVITY AS ..."
        conn, cursor = self._make_mock_conn(ddl)
        ci = {"sql_generation": "it's a test", "question_categorization": ""}
        deploy_semantic_view(conn, "SEM_ACTIVITY", ci)
        third_call = cursor.execute.call_args_list[2]
        sql = third_call[0][0]
        assert "it''s a test" in sql

    def test_strips_existing_ai_clauses_from_ddl(self):
        ddl = (
            "CREATE OR REPLACE SEMANTIC VIEW DB_INSULINTEL.SCH_SEMANTIC.SEM_ACTIVITY AS ...\n"
            "  AI_SQL_GENERATION 'old sg'\n"
            "  AI_QUESTION_CATEGORIZATION 'old qc'"
        )
        conn, cursor = self._make_mock_conn(ddl)
        ci = {"sql_generation": "new sg", "question_categorization": "new qc"}
        deploy_semantic_view(conn, "SEM_ACTIVITY", ci)
        third_call = cursor.execute.call_args_list[2]
        sql = third_call[0][0]
        assert "old sg" not in sql
        assert "old qc" not in sql
        assert "new sg" in sql
        assert "new qc" in sql

    def test_returns_error_on_exception(self):
        conn = MagicMock()
        cursor = MagicMock()
        conn.cursor.return_value = cursor
        cursor.execute.side_effect = Exception("Snowflake error")
        ci = {"sql_generation": "test", "question_categorization": ""}
        result = deploy_semantic_view(conn, "SEM_ACTIVITY", ci)
        assert result.startswith("❌")


# ---------------------------------------------------------------------------
# Tests: deploy_all_from_repo (mocked)
# ---------------------------------------------------------------------------

class TestDeployAllFromRepo:
    """Test deploy_all_from_repo with mocked deploy functions."""

    @patch("deployer.deploy_agent_field")
    @patch("deployer.deploy_semantic_view")
    def test_deploys_all_three_views(self, mock_sv, mock_af):
        mock_sv.return_value = "✅ deployed"
        mock_af.return_value = "✅ updated"
        conn = MagicMock()
        results = deploy_all_from_repo(conn)
        # 3 semantic views + 2 agent fields = 5 results
        assert len(results) == 5
        assert mock_sv.call_count == 3

    @patch("deployer.deploy_agent_field")
    @patch("deployer.deploy_semantic_view")
    def test_deploys_both_agent_fields(self, mock_sv, mock_af):
        mock_sv.return_value = "✅ deployed"
        mock_af.return_value = "✅ updated"
        conn = MagicMock()
        results = deploy_all_from_repo(conn)
        assert mock_af.call_count == 2
        field_names = [c[0][1] for c in mock_af.call_args_list]
        assert "orchestration_instructions" in field_names
        assert "response_instructions" in field_names

    @patch("deployer.deploy_agent_field")
    @patch("deployer.deploy_semantic_view")
    def test_returns_all_status_messages(self, mock_sv, mock_af):
        mock_sv.return_value = "✅ ok"
        mock_af.return_value = "✅ ok"
        conn = MagicMock()
        results = deploy_all_from_repo(conn)
        assert all(r.startswith("✅") for r in results)
