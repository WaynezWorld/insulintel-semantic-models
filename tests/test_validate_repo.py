"""
Tests for scripts/validate_repo.py — repository structure validation.
"""
from __future__ import annotations

import textwrap
from pathlib import Path
from typing import List

import pytest
import yaml

# validate_repo.py lives in scripts/ (not a package), so we import via importlib
import importlib.util
import sys

_SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
_spec = importlib.util.spec_from_file_location("validate_repo", _SCRIPTS_DIR / "validate_repo.py")
validate_repo = importlib.util.module_from_spec(_spec)
sys.modules["validate_repo"] = validate_repo
_spec.loader.exec_module(validate_repo)

Finding = validate_repo.Finding
strip_sql_comments = validate_repo.strip_sql_comments
collect_cte_names = validate_repo.collect_cte_names
clean_table_token = validate_repo.clean_table_token
validate_sql_fqdn = validate_repo.validate_sql_fqdn
validate_expected_models = validate_repo.validate_expected_models
validate_deploy_wiring = validate_repo.validate_deploy_wiring
validate_sql_files = validate_repo.validate_sql_files
validate_instruction_assembly = validate_repo.validate_instruction_assembly
print_findings = validate_repo.print_findings
line_number = validate_repo.line_number
EXPECTED_MODELS = validate_repo.EXPECTED_MODELS


# ===================================================================
# Finding dataclass
# ===================================================================

class TestFinding:
    def test_format_message_only(self):
        f = Finding("ERROR", "something broke")
        assert f.format() == "[ERROR] something broke"

    def test_format_with_path(self):
        f = Finding("WARN", "missing file", path=Path("foo/bar.yaml"))
        assert "[WARN]" in f.format()
        assert "foo" in f.format()
        assert "bar.yaml" in f.format()

    def test_format_with_path_and_line(self):
        f = Finding("ERROR", "bad ref", path=Path("test.sql"), line=42)
        formatted = f.format()
        assert ":42:" in formatted or ":42 " in formatted


# ===================================================================
# Utility functions
# ===================================================================

class TestLineNumber:
    def test_first_line(self):
        assert line_number("hello\nworld", 0) == 1

    def test_second_line(self):
        assert line_number("hello\nworld", 6) == 2

    def test_third_line(self):
        assert line_number("a\nb\nc", 4) == 3


class TestStripSqlComments:
    def test_line_comments(self):
        sql = "SELECT 1 -- this is a comment\nFROM DB.SCH.T"
        result = strip_sql_comments(sql)
        assert "--" not in result
        assert "FROM DB.SCH.T" in result

    def test_block_comments(self):
        sql = "SELECT /* comment */ 1 FROM DB.SCH.T"
        result = strip_sql_comments(sql)
        assert "/*" not in result
        assert "FROM DB.SCH.T" in result

    def test_multiline_block_preserves_line_count(self):
        sql = "SELECT\n/*\ncomment\n*/\n1"
        result = strip_sql_comments(sql)
        # Block comment replaced with newlines to preserve line numbers
        assert result.count("\n") == sql.count("\n")

    def test_no_comments(self):
        sql = "SELECT 1 FROM DB.SCH.T"
        assert strip_sql_comments(sql) == sql


class TestCollectCteNames:
    def test_single_cte(self):
        sql = "WITH my_cte AS (SELECT 1) SELECT * FROM my_cte"
        names = collect_cte_names(sql)
        assert "MY_CTE" in names

    def test_multiple_ctes(self):
        sql = "WITH cte1 AS (SELECT 1), cte2 AS (SELECT 2) SELECT * FROM cte1"
        names = collect_cte_names(sql)
        assert "CTE1" in names
        assert "CTE2" in names

    def test_no_ctes(self):
        sql = "SELECT 1 FROM DB.SCH.T"
        names = collect_cte_names(sql)
        assert len(names) == 0

    def test_case_insensitive(self):
        sql = "with MixedCase AS (SELECT 1) SELECT * FROM MixedCase"
        names = collect_cte_names(sql)
        assert "MIXEDCASE" in names


class TestCleanTableToken:
    def test_strips_whitespace(self):
        assert clean_table_token("  DB.SCH.T  ") == "DB.SCH.T"

    def test_strips_trailing_comma(self):
        assert clean_table_token("DB.SCH.T,") == "DB.SCH.T"

    def test_strips_trailing_semicolon(self):
        assert clean_table_token("DB.SCH.T;") == "DB.SCH.T"

    def test_strips_quotes(self):
        assert clean_table_token('"DB"."SCH"."T"') == 'DB"."SCH"."T'

    def test_empty(self):
        assert clean_table_token("") == ""


# ===================================================================
# validate_sql_fqdn
# ===================================================================

class TestValidateSqlFqdn:
    def _write_sql(self, tmp_path: Path, sql: str, name: str = "test.sql") -> Path:
        p = tmp_path / name
        p.write_text(sql, encoding="utf-8")
        return p

    def test_fqdn_passes(self, tmp_path: Path):
        sql = "SELECT * FROM DB.SCHEMA.TABLE1 JOIN DB.SCHEMA.TABLE2 ON 1=1"
        p = self._write_sql(tmp_path, sql)
        findings = validate_sql_fqdn(p)
        assert len(findings) == 0

    def test_non_fqdn_fails(self, tmp_path: Path):
        sql = "SELECT * FROM SCHEMA.TABLE1"
        p = self._write_sql(tmp_path, sql)
        findings = validate_sql_fqdn(p)
        assert len(findings) == 1
        assert "Non-FQDN" in findings[0].message
        assert "SCHEMA.TABLE1" in findings[0].message

    def test_bare_table_fails(self, tmp_path: Path):
        sql = "SELECT * FROM MY_TABLE"
        p = self._write_sql(tmp_path, sql)
        findings = validate_sql_fqdn(p)
        assert len(findings) == 1

    def test_cte_excluded(self, tmp_path: Path):
        sql = "WITH my_cte AS (SELECT 1 FROM DB.SCH.T) SELECT * FROM my_cte"
        p = self._write_sql(tmp_path, sql)
        findings = validate_sql_fqdn(p)
        assert len(findings) == 0

    def test_subquery_excluded(self, tmp_path: Path):
        sql = "SELECT * FROM (SELECT 1 FROM DB.SCH.T)"
        p = self._write_sql(tmp_path, sql)
        findings = validate_sql_fqdn(p)
        assert len(findings) == 0

    def test_stage_reference_excluded(self, tmp_path: Path):
        sql = "COPY INTO DB.SCH.T FROM @my_stage"
        p = self._write_sql(tmp_path, sql)
        findings = validate_sql_fqdn(p)
        # @my_stage starts with @ so it's skipped
        assert all("@" not in f.message for f in findings)

    def test_table_function_excluded(self, tmp_path: Path):
        sql = "SELECT * FROM TABLE(GENERATOR(ROWCOUNT => 10))"
        p = self._write_sql(tmp_path, sql)
        findings = validate_sql_fqdn(p)
        assert len(findings) == 0

    def test_lateral_excluded(self, tmp_path: Path):
        sql = "SELECT * FROM DB.SCH.T, LATERAL FLATTEN(input => col)"
        p = self._write_sql(tmp_path, sql)
        findings = validate_sql_fqdn(p)
        assert len(findings) == 0

    def test_comment_lines_ignored(self, tmp_path: Path):
        sql = "-- FROM bad_table\nSELECT 1 FROM DB.SCH.T"
        p = self._write_sql(tmp_path, sql)
        findings = validate_sql_fqdn(p)
        assert len(findings) == 0

    def test_block_comment_ignored(self, tmp_path: Path):
        sql = "/* FROM bad_table */ SELECT 1 FROM DB.SCH.T"
        p = self._write_sql(tmp_path, sql)
        findings = validate_sql_fqdn(p)
        assert len(findings) == 0

    def test_multiple_violations(self, tmp_path: Path):
        sql = "SELECT * FROM bad1 JOIN bad2 ON 1=1"
        p = self._write_sql(tmp_path, sql)
        findings = validate_sql_fqdn(p)
        assert len(findings) == 2

    def test_join_fqdn_passes(self, tmp_path: Path):
        sql = "SELECT * FROM DB.SCH.A JOIN DB.SCH.B ON A.id = B.id"
        p = self._write_sql(tmp_path, sql)
        findings = validate_sql_fqdn(p)
        assert len(findings) == 0

    def test_parenthesized_token_excluded(self, tmp_path: Path):
        """Tokens containing parens (e.g. function calls) are skipped."""
        sql = "SELECT * FROM FLATTEN(input => col)"
        p = self._write_sql(tmp_path, sql)
        findings = validate_sql_fqdn(p)
        assert len(findings) == 0


# ===================================================================
# validate_expected_models
# ===================================================================

class TestValidateExpectedModels:
    def _make_repo(self, tmp_path: Path, model_files: set) -> Path:
        sv_dir = tmp_path / "semantic_views"
        sv_dir.mkdir(parents=True)
        for f in model_files:
            (sv_dir / f).write_text("name: test", encoding="utf-8")
        return tmp_path

    def test_all_present(self, tmp_path: Path):
        root = self._make_repo(tmp_path, EXPECTED_MODELS)
        findings = validate_expected_models(root)
        assert len(findings) == 0

    def test_missing_model(self, tmp_path: Path):
        root = self._make_repo(tmp_path, {"sem_insulintel.yaml", "sem_activity.yaml"})
        findings = validate_expected_models(root)
        errors = [f for f in findings if f.level == "ERROR"]
        assert len(errors) == 1
        assert "sem_nhanes.yaml" in errors[0].message

    def test_all_missing(self, tmp_path: Path):
        root = self._make_repo(tmp_path, set())
        findings = validate_expected_models(root)
        errors = [f for f in findings if f.level == "ERROR"]
        assert len(errors) == 3

    def test_extra_model_warns(self, tmp_path: Path):
        root = self._make_repo(tmp_path, EXPECTED_MODELS | {"sem_extra.yaml"})
        findings = validate_expected_models(root)
        warns = [f for f in findings if f.level == "WARN"]
        assert len(warns) == 1
        assert "sem_extra.yaml" in warns[0].message

    def test_no_semantic_views_dir(self, tmp_path: Path):
        findings = validate_expected_models(tmp_path)
        errors = [f for f in findings if f.level == "ERROR"]
        assert len(errors) == 3  # all 3 missing


# ===================================================================
# validate_deploy_wiring
# ===================================================================

class TestValidateDeployWiring:
    def _make_deploy(self, tmp_path: Path, content: str) -> Path:
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "deploy.sql").write_text(content, encoding="utf-8")
        return tmp_path

    def test_all_referenced(self, tmp_path: Path):
        content = "-- deploy script\nsem_insulintel.yaml\nsem_activity.yaml\nsem_nhanes.yaml\n"
        root = self._make_deploy(tmp_path, content)
        findings = validate_deploy_wiring(root)
        assert len(findings) == 0

    def test_missing_reference(self, tmp_path: Path):
        content = "-- deploy script\nsem_insulintel.yaml\nsem_activity.yaml\n"
        root = self._make_deploy(tmp_path, content)
        findings = validate_deploy_wiring(root)
        assert len(findings) == 1
        assert "sem_nhanes.yaml" in findings[0].message

    def test_deploy_sql_missing(self, tmp_path: Path):
        (tmp_path / "scripts").mkdir(parents=True)
        findings = validate_deploy_wiring(tmp_path)
        assert len(findings) == 1
        assert "Missing deployment script" in findings[0].message

    def test_no_scripts_dir(self, tmp_path: Path):
        findings = validate_deploy_wiring(tmp_path)
        assert len(findings) == 1
        assert "Missing" in findings[0].message


# ===================================================================
# validate_sql_files
# ===================================================================

class TestValidateSqlFiles:
    def test_scans_all_sql_in_scripts(self, tmp_path: Path):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "good.sql").write_text(
            "SELECT 1 FROM DB.SCH.T", encoding="utf-8"
        )
        (scripts_dir / "bad.sql").write_text(
            "SELECT 1 FROM BARE_TABLE", encoding="utf-8"
        )
        findings = validate_sql_files(tmp_path)
        assert len(findings) == 1
        assert "BARE_TABLE" in findings[0].message

    def test_no_sql_files(self, tmp_path: Path):
        (tmp_path / "scripts").mkdir(parents=True)
        findings = validate_sql_files(tmp_path)
        assert len(findings) == 0

    def test_ignores_non_sql(self, tmp_path: Path):
        scripts_dir = tmp_path / "scripts"
        scripts_dir.mkdir(parents=True)
        (scripts_dir / "readme.md").write_text("FROM bad_table", encoding="utf-8")
        findings = validate_sql_files(tmp_path)
        assert len(findings) == 0


# ===================================================================
# validate_instruction_assembly
# ===================================================================

class TestValidateInstructionAssembly:
    def _make_assembly(
        self,
        tmp_path: Path,
        assembly: dict,
        instruction_files: list[str] | None = None,
    ) -> Path:
        instr_dir = tmp_path / "instructions"
        instr_dir.mkdir(parents=True)
        with open(instr_dir / "assembly.yaml", "w", encoding="utf-8") as f:
            yaml.dump(assembly, f)
        for rel in instruction_files or []:
            p = instr_dir / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text("content: test", encoding="utf-8")
        return tmp_path

    def test_all_referenced_and_present(self, tmp_path: Path):
        assembly = {
            "semantic_views": {
                "VIEW1": {
                    "sql_generation": ["mod1.yaml"],
                }
            },
            "agent": {
                "AGENT1": {
                    "orchestration_instructions": ["agent/orch.yaml"],
                }
            },
        }
        root = self._make_assembly(
            tmp_path, assembly,
            instruction_files=["mod1.yaml", "agent/orch.yaml"],
        )
        findings = validate_instruction_assembly(root)
        assert len(findings) == 0

    def test_missing_file_errors(self, tmp_path: Path):
        assembly = {
            "semantic_views": {
                "VIEW1": {
                    "sql_generation": ["missing.yaml"],
                }
            },
        }
        root = self._make_assembly(tmp_path, assembly, instruction_files=[])
        findings = validate_instruction_assembly(root)
        errors = [f for f in findings if f.level == "ERROR"]
        assert any("missing.yaml" in e.message for e in errors)

    def test_orphaned_file_errors(self, tmp_path: Path):
        assembly = {
            "semantic_views": {
                "VIEW1": {
                    "sql_generation": ["used.yaml"],
                }
            },
        }
        root = self._make_assembly(
            tmp_path, assembly,
            instruction_files=["used.yaml", "orphan.yaml"],
        )
        findings = validate_instruction_assembly(root)
        errors = [f for f in findings if f.level == "ERROR"]
        assert any("orphan.yaml" in e.message for e in errors)

    def test_no_assembly_yaml(self, tmp_path: Path):
        findings = validate_instruction_assembly(tmp_path)
        assert len(findings) == 1
        assert "Missing" in findings[0].message

    def test_agent_section(self, tmp_path: Path):
        assembly = {
            "agent": {
                "AGENT1": {
                    "orchestration_instructions": ["a/orch.yaml"],
                    "response_instructions": ["a/resp.yaml"],
                }
            },
        }
        root = self._make_assembly(
            tmp_path, assembly,
            instruction_files=["a/orch.yaml", "a/resp.yaml"],
        )
        findings = validate_instruction_assembly(root)
        assert len(findings) == 0

    def test_empty_assembly(self, tmp_path: Path):
        root = self._make_assembly(tmp_path, {}, instruction_files=[])
        findings = validate_instruction_assembly(root)
        assert len(findings) == 0

    def test_null_modules_handled(self, tmp_path: Path):
        """assembly.yaml with null values for modules should not crash."""
        assembly = {
            "semantic_views": {
                "VIEW1": {
                    "sql_generation": None,
                }
            },
        }
        root = self._make_assembly(tmp_path, assembly, instruction_files=[])
        # Should not raise
        findings = validate_instruction_assembly(root)
        assert isinstance(findings, list)

    def test_null_targets_handled(self, tmp_path: Path):
        """assembly.yaml with null targets should not crash."""
        assembly = {
            "semantic_views": {
                "VIEW1": None,
            },
        }
        root = self._make_assembly(tmp_path, assembly, instruction_files=[])
        findings = validate_instruction_assembly(root)
        assert isinstance(findings, list)


# ===================================================================
# print_findings
# ===================================================================

class TestPrintFindings:
    def test_no_findings(self, capsys):
        rc = print_findings([])
        assert rc == 0
        assert "no findings" in capsys.readouterr().out.lower()

    def test_warnings_only(self, capsys):
        rc = print_findings([Finding("WARN", "something")])
        assert rc == 0
        out = capsys.readouterr().out
        assert "1 warning" in out.lower()

    def test_errors_fail(self, capsys):
        rc = print_findings([Finding("ERROR", "broken")])
        assert rc == 1
        out = capsys.readouterr().out
        assert "1 error" in out.lower()

    def test_mixed(self, capsys):
        rc = print_findings([
            Finding("WARN", "minor"),
            Finding("ERROR", "major"),
        ])
        assert rc == 1
        out = capsys.readouterr().out
        assert "1 error" in out.lower()
        assert "1 warning" in out.lower()

    def test_warnings_printed_before_errors(self, capsys):
        print_findings([
            Finding("ERROR", "an error"),
            Finding("WARN", "a warning"),
        ])
        out = capsys.readouterr().out
        warn_pos = out.index("[WARN]")
        error_pos = out.index("[ERROR]")
        assert warn_pos < error_pos


# ===================================================================
# Real repo smoke test
# ===================================================================

class TestRealRepoValidation:
    """Run the real validator against the actual repo to ensure it passes."""

    def test_real_repo_passes(self):
        root = Path(__file__).resolve().parents[1]
        findings: list = []
        findings.extend(validate_expected_models(root))
        findings.extend(validate_deploy_wiring(root))
        findings.extend(validate_sql_files(root))
        findings.extend(validate_instruction_assembly(root))
        errors = [f for f in findings if f.level == "ERROR"]
        assert len(errors) == 0, "\n".join(f.format() for f in errors)
