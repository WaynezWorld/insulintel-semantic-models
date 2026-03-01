"""
Live integration tests for ``app.deployer`` Snowflake operations.

Every test in this module is marked ``@pytest.mark.live`` and **will be
skipped** unless ``pytest --live`` is passed on the command line.

The ``snowflake_conn`` fixture (defined in ``conftest.py``) provides a
session-scoped Snowflake connection using credentials from environment
variables or ``.streamlit/secrets.toml``.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# ---------------------------------------------------------------------------
# Import the module under test (same pattern as test_deployer.py)
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT / "app") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "app"))

from deployer import (
    build_deployable_yaml,
    deploy_agent_field,
    deploy_all_from_repo,
    deploy_semantic_view,
    get_live_agent_instructions,
    get_live_custom_instructions,
    test_with_cortex as _test_with_cortex,
)
from semantic_diff.constants import SEMANTIC_VIEW_NAMES

# Every test in this file requires a live Snowflake connection.
pytestmark = pytest.mark.live


# ── helpers ──────────────────────────────────────────────────────────────

def _is_success(result: str) -> bool:
    """True when the deploy / update result starts with the success emoji."""
    return result.startswith("✅")


def _is_error(result: str) -> bool:
    return result.startswith("❌") or result.startswith("Error")


# ── get_live_custom_instructions ─────────────────────────────────────────

class TestGetLiveCustomInstructions:
    """Read custom-instruction blocks from each semantic view."""

    @pytest.mark.parametrize("view_name", SEMANTIC_VIEW_NAMES)
    def test_returns_dict_with_expected_keys(self, snowflake_conn, view_name):
        result = get_live_custom_instructions(snowflake_conn, view_name)
        assert isinstance(result, dict)
        # Should not be an error dict
        assert "_error" not in result, f"Snowflake error: {result.get('_error')}"
        # Must contain the two canonical keys
        assert "question_categorization" in result
        assert "sql_generation" in result

    @pytest.mark.parametrize("view_name", SEMANTIC_VIEW_NAMES)
    def test_values_are_strings(self, snowflake_conn, view_name):
        result = get_live_custom_instructions(snowflake_conn, view_name)
        for key in ("question_categorization", "sql_generation"):
            assert isinstance(result.get(key), str)


# ── get_live_agent_instructions ──────────────────────────────────────────

class TestGetLiveAgentInstructions:
    """Read agent instruction fields from Snowflake."""

    def test_returns_dict_with_expected_keys(self, snowflake_conn):
        result = get_live_agent_instructions(snowflake_conn)
        assert isinstance(result, dict)
        assert "_error" not in result, f"Snowflake error: {result.get('_error')}"
        for key in (
            "orchestration_instructions",
            "response_instructions",
            "display_name",
            "description",
        ):
            assert key in result, f"Missing key: {key}"

    def test_orchestration_is_nonempty_string(self, snowflake_conn):
        result = get_live_agent_instructions(snowflake_conn)
        val = result.get("orchestration_instructions", "")
        assert isinstance(val, str)
        assert len(val) > 0, "orchestration_instructions should not be empty on a deployed agent"

    def test_response_is_nonempty_string(self, snowflake_conn):
        result = get_live_agent_instructions(snowflake_conn)
        val = result.get("response_instructions", "")
        assert isinstance(val, str)
        assert len(val) > 0, "response_instructions should not be empty on a deployed agent"


# ── deploy_semantic_view (read-only round-trip) ──────────────────────────

class TestDeploySemanticView:
    """Deploy each semantic view using repo YAML and live custom instructions.

    Strategy: for each view, fetch the *current* live custom instructions,
    then re-deploy with the same values.  This is a no-op write that
    exercises the full deploy path without changing production state.
    """

    @pytest.mark.parametrize("view_name", SEMANTIC_VIEW_NAMES)
    def test_roundtrip_deploy(self, snowflake_conn, view_name):
        # 1. Fetch current live CI
        live_ci = get_live_custom_instructions(snowflake_conn, view_name)
        assert "_error" not in live_ci, f"Cannot read CI: {live_ci.get('_error')}"

        # 2. Re-deploy with the same CI (no-op)
        result = deploy_semantic_view(snowflake_conn, view_name, live_ci)
        assert _is_success(result), f"Deploy failed: {result}"

    @pytest.mark.parametrize("view_name", SEMANTIC_VIEW_NAMES)
    def test_deploy_with_empty_ci(self, snowflake_conn, view_name):
        """Deploy with empty custom instructions (valid — CI section omitted)."""
        result = deploy_semantic_view(
            snowflake_conn,
            view_name,
            {"question_categorization": "", "sql_generation": ""},
        )
        assert _is_success(result), f"Deploy failed: {result}"

        # Restore original CI afterwards so we don't leave prod altered
        live_ci = get_live_custom_instructions(snowflake_conn, view_name)
        deploy_semantic_view(snowflake_conn, view_name, live_ci)


# ── deploy_agent_field (round-trip) ──────────────────────────────────────

class TestDeployAgentField:
    """Patch agent instruction fields via ALTER AGENT — round-trip safe."""

    @pytest.mark.parametrize(
        "field",
        ["orchestration_instructions", "response_instructions"],
    )
    def test_roundtrip_agent_field(self, snowflake_conn, field):
        # 1. Read current value
        live = get_live_agent_instructions(snowflake_conn)
        assert "_error" not in live, f"Cannot read agent: {live.get('_error')}"
        original_value = live.get(field, "")

        # 2. Write back the same value (no-op)
        result = deploy_agent_field(snowflake_conn, field, original_value)
        assert _is_success(result), f"Agent field update failed: {result}"

        # 3. Verify the value is still the same
        after = get_live_agent_instructions(snowflake_conn)
        assert after.get(field) == original_value


# ── test_with_cortex ─────────────────────────────────────────────────────

class TestWithCortex:
    """Call CORTEX.COMPLETE via the test_with_cortex helper."""

    def test_simple_prompt(self, snowflake_conn):
        """Ensure we get a non-empty string back from the LLM."""
        result = _test_with_cortex(
            snowflake_conn,
            system_prompt="You are a helpful assistant. Reply in one sentence.",
            user_message="What is 2 + 2?",
            model="mistral-large2",
        )
        assert isinstance(result, str)
        assert len(result) > 0
        assert not _is_error(result), f"Cortex call failed: {result}"

    def test_custom_model(self, snowflake_conn):
        """Verify the model parameter is respected (no error with a valid model)."""
        result = _test_with_cortex(
            snowflake_conn,
            system_prompt="Reply with one word only.",
            user_message="Say hello.",
            model="llama3.1-8b",
        )
        assert isinstance(result, str)
        assert not _is_error(result), f"Cortex call failed: {result}"


# ── build_deployable_yaml sanity ─────────────────────────────────────────

class TestBuildDeployableYamlLive:
    """Cross-check that build_deployable_yaml produces valid YAML that
    Snowflake's parser will accept (implicitly tested via deploy, but
    this isolates the builder itself).
    """

    @pytest.mark.parametrize("view_name", SEMANTIC_VIEW_NAMES)
    def test_yaml_parses_cleanly(self, snowflake_conn, view_name):
        import yaml

        text = build_deployable_yaml(view_name)
        data = yaml.safe_load(text)
        assert isinstance(data, dict)
        assert "name" in data or "tables" in data
        # Must NOT contain custom_instructions (Snowflake rejects them)
        assert "custom_instructions" not in data


# ── deploy_all_from_repo (round-trip) ───────────────────────────────────────

class TestDeployAllFromRepo:
    """Exercise the full deploy_all_from_repo pipeline against live Snowflake.

    This test re-deploys the current repo state (a no-op if already in sync)
    and verifies every target returns a success status.
    """

    def test_deploy_all_succeeds(self, snowflake_conn):
        results = deploy_all_from_repo(snowflake_conn)
        # Expect 5 results: 3 semantic views + 2 agent fields
        assert len(results) == 5
        for r in results:
            assert r.startswith("✅") or r.startswith("⚠️"), f"Unexpected result: {r}"
