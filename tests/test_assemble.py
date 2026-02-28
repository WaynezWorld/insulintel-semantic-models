"""
Tests for semantic_diff.assemble — assembly logic, orphan/missing detection,
and module concatenation.
"""
from __future__ import annotations

import textwrap
from pathlib import Path

import pytest
import yaml

from semantic_diff.assemble import (
    load_assembly_config,
    read_module_content,
    read_module_data,
    concat_modules,
    assemble_semantic_view_instructions,
    assemble_agent_instructions,
    collect_all_referenced_files,
    find_orphaned_files,
    find_missing_files,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _write_yaml(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.dump(data, default_flow_style=False), encoding="utf-8")


def _make_module(instr_dir: Path, rel_path: str, content: str, **extra) -> None:
    data = {"content": content, **extra}
    _write_yaml(instr_dir / rel_path, data)


def _make_repo(tmp_path: Path, assembly: dict, modules: dict[str, str]) -> Path:
    """Create a minimal repo layout for testing.

    Parameters
    ----------
    assembly : dict
        Contents for ``instructions/assembly.yaml``.
    modules : dict
        Mapping of relative paths → content strings.
    """
    instr_dir = tmp_path / "instructions"
    _write_yaml(instr_dir / "assembly.yaml", assembly)
    for rel, content in modules.items():
        _make_module(instr_dir, rel, content)
    return tmp_path


# ---------------------------------------------------------------------------
# Tests: load_assembly_config
# ---------------------------------------------------------------------------

class TestLoadAssemblyConfig:
    def test_loads_valid_config(self, tmp_path: Path):
        assembly = {
            "semantic_views": {"VIEW_A": {"sql_generation": ["mod_a.yaml"]}},
            "agent": {"AGENT_X": {"orchestration_instructions": ["mod_b.yaml"]}},
        }
        _make_repo(tmp_path, assembly, {"mod_a.yaml": "a", "mod_b.yaml": "b"})
        config = load_assembly_config(tmp_path)
        assert "semantic_views" in config
        assert "agent" in config

    def test_raises_on_missing(self, tmp_path: Path):
        with pytest.raises(FileNotFoundError):
            load_assembly_config(tmp_path)


# ---------------------------------------------------------------------------
# Tests: read_module_data / read_module_content
# ---------------------------------------------------------------------------

class TestReadModule:
    def test_reads_content_field(self, tmp_path: Path):
        _make_module(tmp_path / "instructions", "test.yaml", "hello world")
        data = read_module_data(tmp_path, "test.yaml")
        assert data["content"] == "hello world"

    def test_reads_extra_fields(self, tmp_path: Path):
        _make_module(
            tmp_path / "instructions", "test.yaml", "text",
            version="1.2", module="test_mod",
        )
        data = read_module_data(tmp_path, "test.yaml")
        assert data["version"] == "1.2"
        assert data["module"] == "test_mod"

    def test_content_shortcut(self, tmp_path: Path):
        _make_module(tmp_path / "instructions", "test.yaml", "  spaced  ")
        assert read_module_content(tmp_path, "test.yaml") == "spaced"

    def test_empty_file(self, tmp_path: Path):
        path = tmp_path / "instructions" / "empty.yaml"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("", encoding="utf-8")
        assert read_module_content(tmp_path, "empty.yaml") == ""


# ---------------------------------------------------------------------------
# Tests: concat_modules
# ---------------------------------------------------------------------------

class TestConcatModules:
    def test_concatenates_in_order(self, tmp_path: Path):
        instr_dir = tmp_path / "instructions"
        _make_module(instr_dir, "a.yaml", "AAA")
        _make_module(instr_dir, "b.yaml", "BBB")
        _make_module(instr_dir, "c.yaml", "CCC")
        result = concat_modules(tmp_path, ["a.yaml", "b.yaml", "c.yaml"])
        assert result == "AAA\n\nBBB\n\nCCC"

    def test_skips_empty(self, tmp_path: Path):
        instr_dir = tmp_path / "instructions"
        _make_module(instr_dir, "a.yaml", "AAA")
        _make_module(instr_dir, "b.yaml", "")
        _make_module(instr_dir, "c.yaml", "CCC")
        result = concat_modules(tmp_path, ["a.yaml", "b.yaml", "c.yaml"])
        assert result == "AAA\n\nCCC"

    def test_empty_list(self, tmp_path: Path):
        assert concat_modules(tmp_path, []) == ""


# ---------------------------------------------------------------------------
# Tests: assemble_semantic_view_instructions
# ---------------------------------------------------------------------------

class TestAssembleSemanticViews:
    def test_assembles_all_views(self, tmp_path: Path):
        assembly = {
            "semantic_views": {
                "VIEW_A": {
                    "sql_generation": ["shared.yaml", "view_a.yaml"],
                    "question_categorization": ["qc.yaml"],
                },
            },
        }
        modules = {
            "shared.yaml": "shared text",
            "view_a.yaml": "view A specific",
            "qc.yaml": "categorization rules",
        }
        _make_repo(tmp_path, assembly, modules)
        result = assemble_semantic_view_instructions(tmp_path)
        assert "VIEW_A" in result
        assert "shared text" in result["VIEW_A"]["sql_generation"]
        assert "view A specific" in result["VIEW_A"]["sql_generation"]
        assert result["VIEW_A"]["question_categorization"] == "categorization rules"

    def test_multiple_views(self, tmp_path: Path):
        assembly = {
            "semantic_views": {
                "V1": {"sql_generation": ["m1.yaml"]},
                "V2": {"sql_generation": ["m2.yaml"]},
            },
        }
        _make_repo(tmp_path, assembly, {"m1.yaml": "text1", "m2.yaml": "text2"})
        result = assemble_semantic_view_instructions(tmp_path)
        assert len(result) == 2
        assert result["V1"]["sql_generation"] == "text1"
        assert result["V2"]["sql_generation"] == "text2"


# ---------------------------------------------------------------------------
# Tests: assemble_agent_instructions
# ---------------------------------------------------------------------------

class TestAssembleAgent:
    def test_assembles_agent_fields(self, tmp_path: Path):
        assembly = {
            "semantic_views": {},
            "agent": {
                "MY_AGENT": {
                    "orchestration_instructions": ["orch.yaml"],
                    "response_instructions": ["resp.yaml"],
                },
            },
        }
        modules = {"orch.yaml": "orchestration text", "resp.yaml": "response text"}
        _make_repo(tmp_path, assembly, modules)
        result = assemble_agent_instructions(tmp_path)
        assert result["MY_AGENT"]["orchestration_instructions"] == "orchestration text"
        assert result["MY_AGENT"]["response_instructions"] == "response text"


# ---------------------------------------------------------------------------
# Tests: orphan / missing detection
# ---------------------------------------------------------------------------

class TestOrphanMissing:
    def test_no_orphans_no_missing(self, tmp_path: Path):
        assembly = {"semantic_views": {"V": {"f": ["a.yaml"]}}}
        _make_repo(tmp_path, assembly, {"a.yaml": "content"})
        assert find_orphaned_files(tmp_path) == []
        assert find_missing_files(tmp_path) == []

    def test_detects_orphan(self, tmp_path: Path):
        assembly = {"semantic_views": {"V": {"f": ["a.yaml"]}}}
        _make_repo(tmp_path, assembly, {"a.yaml": "content", "orphan.yaml": "stray"})
        orphans = find_orphaned_files(tmp_path)
        assert "orphan.yaml" in orphans

    def test_detects_missing(self, tmp_path: Path):
        assembly = {"semantic_views": {"V": {"f": ["a.yaml", "gone.yaml"]}}}
        _make_repo(tmp_path, assembly, {"a.yaml": "content"})
        missing = find_missing_files(tmp_path)
        assert "gone.yaml" in missing

    def test_assembly_yaml_not_orphan(self, tmp_path: Path):
        assembly = {"semantic_views": {"V": {"f": ["a.yaml"]}}}
        _make_repo(tmp_path, assembly, {"a.yaml": "content"})
        orphans = find_orphaned_files(tmp_path)
        assert "assembly.yaml" not in orphans


# ---------------------------------------------------------------------------
# Tests: collect_all_referenced_files
# ---------------------------------------------------------------------------

class TestCollectReferenced:
    def test_collects_from_all_sections(self, tmp_path: Path):
        assembly = {
            "semantic_views": {"V": {"f1": ["a.yaml"], "f2": ["b.yaml"]}},
            "agent": {"A": {"f3": ["c.yaml"]}},
        }
        _make_repo(tmp_path, assembly, {"a.yaml": "", "b.yaml": "", "c.yaml": ""})
        refs = collect_all_referenced_files(tmp_path)
        assert refs == {"a.yaml", "b.yaml", "c.yaml"}

    def test_deduplicates_shared_modules(self, tmp_path: Path):
        assembly = {
            "semantic_views": {
                "V1": {"f": ["shared.yaml", "v1.yaml"]},
                "V2": {"f": ["shared.yaml", "v2.yaml"]},
            },
        }
        modules = {"shared.yaml": "", "v1.yaml": "", "v2.yaml": ""}
        _make_repo(tmp_path, assembly, modules)
        refs = collect_all_referenced_files(tmp_path)
        assert len(refs) == 3


# ---------------------------------------------------------------------------
# Integration: use real repo
# ---------------------------------------------------------------------------

class TestRealRepo:
    """Smoke tests against the actual repo layout (skipped in CI if missing)."""

    REPO_ROOT = Path(__file__).resolve().parents[1]

    @pytest.mark.skipif(
        not (Path(__file__).resolve().parents[1] / "instructions" / "assembly.yaml").exists(),
        reason="Real repo not available",
    )
    def test_no_orphans(self):
        assert find_orphaned_files(self.REPO_ROOT) == []

    @pytest.mark.skipif(
        not (Path(__file__).resolve().parents[1] / "instructions" / "assembly.yaml").exists(),
        reason="Real repo not available",
    )
    def test_no_missing(self):
        assert find_missing_files(self.REPO_ROOT) == []

    @pytest.mark.skipif(
        not (Path(__file__).resolve().parents[1] / "instructions" / "assembly.yaml").exists(),
        reason="Real repo not available",
    )
    def test_all_views_assemble(self):
        result = assemble_semantic_view_instructions(self.REPO_ROOT)
        for view in ("SEM_INSULINTEL", "SEM_ACTIVITY", "SEM_NHANES"):
            assert view in result, f"Missing view: {view}"
            assert result[view].get("sql_generation"), f"{view} has empty sql_generation"
