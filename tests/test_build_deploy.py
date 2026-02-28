"""
Tests for scripts/build_deploy.py — deployment artefact generation.
"""
from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
import yaml

# ---------------------------------------------------------------------------
# Import build_deploy.py (not a package — use importlib)
# ---------------------------------------------------------------------------
_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
_spec = importlib.util.spec_from_file_location("build_deploy", _SCRIPTS_DIR / "build_deploy.py")
build_deploy = importlib.util.module_from_spec(_spec)
sys.modules["build_deploy"] = build_deploy
_spec.loader.exec_module(build_deploy)

_indent = build_deploy._indent
build_semantic_view_yamls = build_deploy.build_semantic_view_yamls
build_agent_sql = build_deploy.build_agent_sql
main = build_deploy.main
VIEWS = build_deploy.VIEWS


# ===================================================================
# _indent helper
# ===================================================================

class TestIndent:
    def test_single_line(self):
        assert _indent("hello", 4) == "    hello"

    def test_multi_line(self):
        result = _indent("line1\nline2\nline3", 2)
        lines = result.split("\n")
        assert len(lines) == 3
        assert all(line.startswith("  ") for line in lines)

    def test_zero_indent(self):
        assert _indent("hello", 0) == "hello"

    def test_empty_string(self):
        # splitlines() on "" returns [], so _indent("", 4) returns ""
        assert _indent("", 4) == ""

    def test_preserves_internal_spacing(self):
        result = _indent("  already indented", 2)
        assert result == "    already indented"


# ===================================================================
# build_semantic_view_yamls
# ===================================================================

class TestBuildSemanticViewYamls:
    def test_generates_all_view_files(self, tmp_path: Path):
        """Should produce one YAML file per SEMANTIC_VIEW_NAMES entry."""
        paths = build_semantic_view_yamls(tmp_path)
        assert len(paths) == len(VIEWS)
        for p in paths:
            assert p.exists()
            assert p.suffix == ".yaml"

    def test_filenames_lowercase(self, tmp_path: Path):
        paths = build_semantic_view_yamls(tmp_path)
        for p in paths:
            assert p.name == p.name.lower()

    def test_output_is_valid_yaml(self, tmp_path: Path):
        paths = build_semantic_view_yamls(tmp_path)
        for p in paths:
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
            assert isinstance(data, dict)
            assert "name" in data

    def test_custom_instructions_injected(self, tmp_path: Path):
        """Built YAMLs should contain custom_instructions from assembly."""
        paths = build_semantic_view_yamls(tmp_path)
        for p in paths:
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
            # All views have at least sql_generation in assembly.yaml
            assert "custom_instructions" in data, f"{p.name} missing custom_instructions"
            ci = data["custom_instructions"]
            assert "sql_generation" in ci or "question_categorization" in ci

    def test_view_names_match(self, tmp_path: Path):
        paths = build_semantic_view_yamls(tmp_path)
        generated_names = {p.stem.upper() for p in paths}
        expected_names = {v.lower() for v in VIEWS}
        assert {p.stem for p in paths} == expected_names

    def test_idempotent(self, tmp_path: Path):
        """Running twice produces identical output."""
        paths1 = build_semantic_view_yamls(tmp_path)
        contents1 = {p.name: p.read_text(encoding="utf-8") for p in paths1}
        paths2 = build_semantic_view_yamls(tmp_path)
        contents2 = {p.name: p.read_text(encoding="utf-8") for p in paths2}
        assert contents1 == contents2


# ===================================================================
# build_agent_sql
# ===================================================================

class TestBuildAgentSql:
    def test_generates_file(self, tmp_path: Path):
        path = build_agent_sql(tmp_path)
        assert path.exists()
        assert path.name == "deploy_agent.sql"

    def test_contains_alter_agent(self, tmp_path: Path):
        path = build_agent_sql(tmp_path)
        sql = path.read_text(encoding="utf-8")
        assert "ALTER AGENT" in sql

    def test_no_cortex_keyword_in_commands(self, tmp_path: Path):
        """Snowflake 2026 SQL commands must not use CORTEX keyword.
        Note: the comment header says 'DEPLOY CORTEX AGENT' — that's cosmetic.
        The actual SQL commands (ALTER/DESCRIBE/SHOW) must NOT have CORTEX."""
        path = build_agent_sql(tmp_path)
        sql = path.read_text(encoding="utf-8")
        # Strip comments before checking
        lines = [l for l in sql.splitlines() if not l.strip().startswith("--")]
        code = "\n".join(lines)
        assert "CORTEX AGENT" not in code
        assert "CORTEX_AGENT" not in code

    def test_contains_schema_fqn(self, tmp_path: Path):
        from semantic_diff.constants import SCHEMA_FQN
        path = build_agent_sql(tmp_path)
        sql = path.read_text(encoding="utf-8")
        assert SCHEMA_FQN in sql

    def test_contains_agent_fqn(self, tmp_path: Path):
        from semantic_diff.constants import AGENT_FQN
        path = build_agent_sql(tmp_path)
        sql = path.read_text(encoding="utf-8")
        assert AGENT_FQN in sql

    def test_contains_modify_live_version(self, tmp_path: Path):
        path = build_agent_sql(tmp_path)
        sql = path.read_text(encoding="utf-8")
        assert "MODIFY LIVE VERSION SET SPECIFICATION" in sql

    def test_contains_orchestration_instructions(self, tmp_path: Path):
        path = build_agent_sql(tmp_path)
        sql = path.read_text(encoding="utf-8")
        assert "orchestration:" in sql

    def test_contains_response_instructions(self, tmp_path: Path):
        path = build_agent_sql(tmp_path)
        sql = path.read_text(encoding="utf-8")
        assert "response:" in sql

    def test_contains_describe_agent(self, tmp_path: Path):
        path = build_agent_sql(tmp_path)
        sql = path.read_text(encoding="utf-8")
        assert "DESCRIBE AGENT" in sql

    def test_contains_git_fetch(self, tmp_path: Path):
        path = build_agent_sql(tmp_path)
        sql = path.read_text(encoding="utf-8")
        assert "ALTER GIT REPOSITORY" in sql
        assert "FETCH" in sql

    def test_dollar_quoting(self, tmp_path: Path):
        """Specification should be wrapped in $$ dollar quotes."""
        path = build_agent_sql(tmp_path)
        sql = path.read_text(encoding="utf-8")
        assert sql.count("$$") >= 2

    def test_idempotent(self, tmp_path: Path):
        path1 = build_agent_sql(tmp_path)
        content1 = path1.read_text(encoding="utf-8")
        path2 = build_agent_sql(tmp_path)
        content2 = path2.read_text(encoding="utf-8")
        assert content1 == content2


# ===================================================================
# main() with --out-dir
# ===================================================================

class TestMain:
    def test_default_out_dir(self, tmp_path: Path, monkeypatch):
        """main() with default args writes to deploy/."""
        monkeypatch.chdir(tmp_path)
        # Create a fake deploy/ dir that main would write to
        # But main uses the real repo, so we just test it doesn't crash
        # by patching sys.argv
        monkeypatch.setattr(sys, "argv", ["build_deploy.py", "--out-dir", str(tmp_path / "out")])
        rc = main()
        assert rc == 0
        out = tmp_path / "out"
        assert out.exists()
        # Should have view YAMLs + agent SQL
        files = list(out.iterdir())
        assert len(files) == len(VIEWS) + 1  # 3 YAMLs + 1 SQL

    def test_custom_out_dir(self, tmp_path: Path, monkeypatch):
        custom = tmp_path / "custom" / "nested"
        monkeypatch.setattr(sys, "argv", ["build_deploy.py", "--out-dir", str(custom)])
        rc = main()
        assert rc == 0
        assert custom.exists()
        yaml_files = list(custom.glob("*.yaml"))
        sql_files = list(custom.glob("*.sql"))
        assert len(yaml_files) == len(VIEWS)
        assert len(sql_files) == 1

    def test_creates_out_dir(self, tmp_path: Path, monkeypatch):
        """main() should create the output directory if it doesn't exist."""
        new_dir = tmp_path / "brand_new"
        assert not new_dir.exists()
        monkeypatch.setattr(sys, "argv", ["build_deploy.py", "--out-dir", str(new_dir)])
        rc = main()
        assert rc == 0
        assert new_dir.exists()


# ===================================================================
# Real repo smoke test
# ===================================================================

class TestRealRepoBuild:
    """Run build against the real repo to verify artefacts match expectations."""

    def test_real_build_produces_valid_artefacts(self, tmp_path: Path):
        paths = build_semantic_view_yamls(tmp_path)
        sql_path = build_agent_sql(tmp_path)

        # All view YAMLs valid
        for p in paths:
            data = yaml.safe_load(p.read_text(encoding="utf-8"))
            assert data.get("name"), f"{p.name} should have a name"

        # Agent SQL is non-empty and well-formed
        sql = sql_path.read_text(encoding="utf-8")
        assert len(sql) > 100
        assert "ALTER AGENT" in sql
        assert "DESCRIBE AGENT" in sql

    def test_generated_matches_deploy_dir(self, tmp_path: Path):
        """Generated artefacts should match what's already in deploy/."""
        repo_root = Path(__file__).resolve().parents[1]
        deploy_dir = repo_root / "deploy"

        # Build fresh
        fresh_paths = build_semantic_view_yamls(tmp_path)
        fresh_sql = build_agent_sql(tmp_path)

        # Compare each YAML
        for fp in fresh_paths:
            existing = deploy_dir / fp.name
            if existing.exists():
                fresh_data = yaml.safe_load(fp.read_text(encoding="utf-8"))
                deploy_data = yaml.safe_load(existing.read_text(encoding="utf-8"))
                assert fresh_data == deploy_data, (
                    f"{fp.name} differs from deploy/ version"
                )

        # Compare agent SQL
        existing_sql = deploy_dir / "deploy_agent.sql"
        if existing_sql.exists():
            assert (
                fresh_sql.read_text(encoding="utf-8")
                == existing_sql.read_text(encoding="utf-8")
            ), "deploy_agent.sql differs from deploy/ version"
