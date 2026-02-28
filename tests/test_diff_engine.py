"""
Tests for semantic_diff.diff_engine — field-level diffing, table diffing,
semantic view diffing, and snapshot diffing.
"""
from __future__ import annotations

import pytest

from semantic_diff.canonical import (
    AgentConfig,
    BaseTable,
    CustomInstructions,
    DiffItem,
    DiffReport,
    Dimension,
    Fact,
    Instruction,
    KeySpec,
    Metric,
    Relationship,
    RelationshipColumn,
    SemanticView,
    Snapshot,
    Table,
)
from semantic_diff.diff_engine import (
    _diff_field,
    _diff_dimensions,
    _diff_facts,
    _diff_metrics,
    _diff_primary_key,
    _diff_unique_keys,
    _diff_tables,
    _diff_relationships,
    _diff_instructions,
    diff_semantic_views,
    diff_snapshots,
)


# ---------------------------------------------------------------------------
# Tests: _diff_field
# ---------------------------------------------------------------------------

class TestDiffField:
    def test_identical_returns_none(self):
        result = _diff_field("path", "cat", "same", "same")
        assert result is None

    def test_different_returns_diff_item(self):
        result = _diff_field("view.field", "dimension", "old", "new")
        assert result is not None
        assert result.path == "view.field"
        assert result.category == "dimension"
        assert result.change_type == "modified"
        assert result.left_value == "old"
        assert result.right_value == "new"

    def test_default_severity_is_breaking(self):
        result = _diff_field("p", "c", "a", "b")
        assert result.severity == "BREAKING"

    def test_custom_severity(self):
        result = _diff_field("p", "c", "a", "b", severity="METADATA")
        assert result.severity == "METADATA"

    def test_coerces_to_string(self):
        result = _diff_field("p", "c", 42, "42")
        assert result is None  # both str("42")

    def test_different_types(self):
        result = _diff_field("p", "c", 42, "43")
        assert result is not None


# ---------------------------------------------------------------------------
# Tests: _diff_dimensions
# ---------------------------------------------------------------------------

class TestDiffDimensions:
    def _dim(self, name="D1", expr="col", data_type="TEXT", desc=""):
        return Dimension(name=name, expr=expr, data_type=data_type, description=desc)

    def test_identical(self):
        dims = [self._dim()]
        assert _diff_dimensions("prefix", dims, dims) == []

    def test_added(self):
        left, right = [], [self._dim("NEW")]
        items = _diff_dimensions("v", left, right)
        assert len(items) == 1
        assert items[0].change_type == "added"
        assert "NEW" in items[0].path

    def test_removed(self):
        left, right = [self._dim("OLD")], []
        items = _diff_dimensions("v", left, right)
        assert len(items) == 1
        assert items[0].change_type == "removed"

    def test_modified_expr_is_breaking(self):
        left = [self._dim(expr="col_a")]
        right = [self._dim(expr="col_b")]
        items = _diff_dimensions("v", left, right)
        assert any(i.severity == "BREAKING" and "expr" in i.path for i in items)

    def test_modified_description_is_metadata(self):
        left = [self._dim(desc="old desc")]
        right = [self._dim(desc="new desc")]
        items = _diff_dimensions("v", left, right)
        assert any(i.severity == "METADATA" and "description" in i.path for i in items)


# ---------------------------------------------------------------------------
# Tests: _diff_facts
# ---------------------------------------------------------------------------

class TestDiffFacts:
    def _fact(self, name="F1", expr="col", data_type="NUMBER", desc="", am=""):
        return Fact(name=name, expr=expr, data_type=data_type,
                    description=desc, access_modifier=am)

    def test_identical(self):
        facts = [self._fact()]
        assert _diff_facts("prefix", facts, facts) == []

    def test_added_and_removed(self):
        left = [self._fact("OLD")]
        right = [self._fact("NEW")]
        items = _diff_facts("v", left, right)
        assert any(i.change_type == "removed" for i in items)
        assert any(i.change_type == "added" for i in items)

    def test_access_modifier_change_is_metadata(self):
        left = [self._fact(am="public")]
        right = [self._fact(am="private")]
        items = _diff_facts("v", left, right)
        assert any(i.severity == "METADATA" and "access_modifier" in i.path for i in items)


# ---------------------------------------------------------------------------
# Tests: _diff_metrics
# ---------------------------------------------------------------------------

class TestDiffMetrics:
    def _metric(self, name="M1", expr="SUM(x)", desc="", am=""):
        return Metric(name=name, expr=expr, description=desc, access_modifier=am)

    def test_identical(self):
        metrics = [self._metric()]
        assert _diff_metrics("prefix", metrics, metrics) == []

    def test_expr_change_is_breaking(self):
        left = [self._metric(expr="SUM(a)")]
        right = [self._metric(expr="AVG(a)")]
        items = _diff_metrics("v", left, right)
        assert any(i.severity == "BREAKING" for i in items)


# ---------------------------------------------------------------------------
# Tests: _diff_primary_key
# ---------------------------------------------------------------------------

class TestDiffPrimaryKey:
    def test_identical(self):
        k = KeySpec(columns=["id"])
        assert _diff_primary_key("v", k, k) == []

    def test_both_none(self):
        assert _diff_primary_key("v", None, None) == []

    def test_pk_added(self):
        items = _diff_primary_key("v", None, KeySpec(columns=["id"]))
        assert len(items) == 1
        assert items[0].severity == "BREAKING"

    def test_pk_removed(self):
        items = _diff_primary_key("v", KeySpec(columns=["id"]), None)
        assert len(items) == 1

    def test_pk_columns_changed(self):
        items = _diff_primary_key(
            "v",
            KeySpec(columns=["a", "b"]),
            KeySpec(columns=["a", "c"]),
        )
        assert len(items) == 1


# ---------------------------------------------------------------------------
# Tests: _diff_unique_keys
# ---------------------------------------------------------------------------

class TestDiffUniqueKeys:
    def test_identical(self):
        k = [KeySpec(columns=["x"])]
        assert _diff_unique_keys("v", k, k) == []

    def test_added(self):
        items = _diff_unique_keys("v", [], [KeySpec(columns=["x"])])
        assert len(items) == 1
        assert items[0].change_type == "added"

    def test_removed(self):
        items = _diff_unique_keys("v", [KeySpec(columns=["x"])], [])
        assert len(items) == 1
        assert items[0].change_type == "removed"


# ---------------------------------------------------------------------------
# Tests: diff_semantic_views
# ---------------------------------------------------------------------------

class TestDiffSemanticViews:
    def _view(self, name="V", desc="", tables=None, ci=None, rels=None):
        return SemanticView(
            name=name,
            description=desc,
            tables=tables or [],
            relationships=rels or [],
            custom_instructions=ci or CustomInstructions(),
        )

    def test_identical_views(self):
        v = self._view()
        assert diff_semantic_views(v, v) == []

    def test_description_change_is_metadata(self):
        left = self._view(desc="old")
        right = self._view(desc="new")
        items = diff_semantic_views(left, right)
        assert len(items) == 1
        assert items[0].severity == "METADATA"

    def test_custom_instructions_change_is_breaking(self):
        left = self._view(ci=CustomInstructions(sql_generation="old"))
        right = self._view(ci=CustomInstructions(sql_generation="new"))
        items = diff_semantic_views(left, right)
        assert any(i.severity == "BREAKING" and "sql_generation" in i.path for i in items)

    def test_table_added_detected(self):
        t = Table(
            name="TBL",
            base_table=BaseTable(database="DB", schema="SCH", table="TBL"),
        )
        left = self._view()
        right = self._view(tables=[t])
        items = diff_semantic_views(left, right)
        assert any(i.change_type == "added" and "TBL" in i.path for i in items)


# ---------------------------------------------------------------------------
# Tests: diff_snapshots
# ---------------------------------------------------------------------------

class TestDiffSnapshots:
    def _snap(self, views=None, instructions=None, agents=None, src="test"):
        return Snapshot(
            source=src,
            semantic_views=views or {},
            instructions=instructions or {},
            agents=agents or {},
        )

    def test_identical_snapshots(self):
        s = self._snap()
        report = diff_snapshots(s, s)
        assert report.is_clean

    def test_view_added(self):
        left = self._snap()
        right = self._snap(views={
            "V1": SemanticView(name="V1"),
        })
        report = diff_snapshots(left, right)
        assert report.breaking_count >= 1
        assert any("V1" in i.path for i in report.items)

    def test_agent_modified(self):
        left = self._snap(agents={
            "A1": AgentConfig(name="A1", orchestration_instructions="old"),
        })
        right = self._snap(agents={
            "A1": AgentConfig(name="A1", orchestration_instructions="new"),
        })
        report = diff_snapshots(left, right)
        assert not report.is_clean
        assert any("orchestration" in i.path for i in report.items)

    def test_instructions_excluded(self):
        left = self._snap(instructions={
            "mod.yaml": Instruction(rel_path="mod.yaml", content="old"),
        })
        right = self._snap(instructions={
            "mod.yaml": Instruction(rel_path="mod.yaml", content="new"),
        })
        report = diff_snapshots(left, right, include_instructions=False)
        assert report.is_clean  # instructions ignored

    def test_instructions_included(self):
        left = self._snap(instructions={
            "mod.yaml": Instruction(rel_path="mod.yaml", content="old"),
        })
        right = self._snap(instructions={
            "mod.yaml": Instruction(rel_path="mod.yaml", content="new"),
        })
        report = diff_snapshots(left, right, include_instructions=True)
        assert not report.is_clean


# ---------------------------------------------------------------------------
# Tests: DiffReport convenience methods
# ---------------------------------------------------------------------------

class TestDiffReport:
    def test_empty_report_is_clean(self):
        r = DiffReport()
        assert r.is_clean
        assert r.breaking_count == 0
        assert r.metadata_count == 0

    def test_summary_no_diffs(self):
        r = DiffReport()
        assert "No differences" in r.summary()

    def test_summary_with_diffs(self):
        r = DiffReport(
            left_label="repo",
            right_label="snowflake",
            items=[
                DiffItem(path="v.tables.T1", category="table",
                         change_type="added", severity="BREAKING",
                         right_value="DB.SCH.TBL"),
            ],
        )
        summary = r.summary()
        assert "BREAKING" in summary or "1 BREAKING" in summary
        assert "T1" in summary

    def test_to_json(self):
        import json
        r = DiffReport(left_label="a", right_label="b")
        parsed = json.loads(r.to_json())
        assert parsed["left_label"] == "a"
        assert parsed["right_label"] == "b"
