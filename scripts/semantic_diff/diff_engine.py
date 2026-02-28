"""
Full-parity diff engine for semantic views and instructions.

Compares every field defined in canonical.py between two snapshots.
Produces a structured DiffReport with severity classification.

Severity rules:
  BREAKING  – structural / logic changes (tables, dimensions, facts,
              metrics, expressions, data types, keys, relationships
              added / removed / modified)
  METADATA  – description-only or access_modifier-only changes
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Dict, List, Optional

from .canonical import (
    DiffItem,
    DiffReport,
    AgentConfig,
    CustomInstructions,
    Dimension,
    Fact,
    Instruction,
    KeySpec,
    Metric,
    Relationship,
    SemanticView,
    Snapshot,
    Table,
)


# ---------------------------------------------------------------------------
# Field-level helpers
# ---------------------------------------------------------------------------

def _diff_field(
    path: str,
    category: str,
    left: str,
    right: str,
    severity: str = "BREAKING",
) -> Optional[DiffItem]:
    """Return a DiffItem if *left* and *right* differ, else None."""
    if str(left) != str(right):
        return DiffItem(
            path=path,
            category=category,
            change_type="modified",
            severity=severity,
            left_value=str(left),
            right_value=str(right),
        )
    return None


# ---------------------------------------------------------------------------
# Component diffing
# ---------------------------------------------------------------------------

def _diff_dimensions(
    prefix: str,
    left: List[Dimension],
    right: List[Dimension],
) -> List[DiffItem]:
    items: List[DiffItem] = []
    left_map = {d.name: d for d in left}
    right_map = {d.name: d for d in right}

    for name in sorted(set(left_map) | set(right_map)):
        path = f"{prefix}.dimensions.{name}"
        if name not in right_map:
            items.append(DiffItem(
                path=path, category="dimension", change_type="removed",
                severity="BREAKING",
                left_value=f"expr={left_map[name].expr}, data_type={left_map[name].data_type}",
            ))
        elif name not in left_map:
            items.append(DiffItem(
                path=path, category="dimension", change_type="added",
                severity="BREAKING",
                right_value=f"expr={right_map[name].expr}, data_type={right_map[name].data_type}",
            ))
        else:
            ld, rd = left_map[name], right_map[name]
            for fld, sev in [
                ("expr", "BREAKING"),
                ("data_type", "BREAKING"),
                ("description", "METADATA"),
            ]:
                item = _diff_field(
                    f"{path}.{fld}", "dimension",
                    getattr(ld, fld), getattr(rd, fld), sev,
                )
                if item:
                    items.append(item)
    return items


def _diff_facts(
    prefix: str,
    left: List[Fact],
    right: List[Fact],
) -> List[DiffItem]:
    items: List[DiffItem] = []
    left_map = {f.name: f for f in left}
    right_map = {f.name: f for f in right}

    for name in sorted(set(left_map) | set(right_map)):
        path = f"{prefix}.facts.{name}"
        if name not in right_map:
            items.append(DiffItem(
                path=path, category="fact", change_type="removed",
                severity="BREAKING",
                left_value=f"expr={left_map[name].expr}",
            ))
        elif name not in left_map:
            items.append(DiffItem(
                path=path, category="fact", change_type="added",
                severity="BREAKING",
                right_value=f"expr={right_map[name].expr}",
            ))
        else:
            lf, rf = left_map[name], right_map[name]
            for fld, sev in [
                ("expr", "BREAKING"),
                ("data_type", "BREAKING"),
                ("description", "METADATA"),
                ("access_modifier", "METADATA"),
            ]:
                item = _diff_field(
                    f"{path}.{fld}", "fact",
                    getattr(lf, fld), getattr(rf, fld), sev,
                )
                if item:
                    items.append(item)
    return items


def _diff_metrics(
    prefix: str,
    left: List[Metric],
    right: List[Metric],
) -> List[DiffItem]:
    items: List[DiffItem] = []
    left_map = {m.name: m for m in left}
    right_map = {m.name: m for m in right}

    for name in sorted(set(left_map) | set(right_map)):
        path = f"{prefix}.metrics.{name}"
        if name not in right_map:
            items.append(DiffItem(
                path=path, category="metric", change_type="removed",
                severity="BREAKING",
                left_value=f"expr={left_map[name].expr}",
            ))
        elif name not in left_map:
            items.append(DiffItem(
                path=path, category="metric", change_type="added",
                severity="BREAKING",
                right_value=f"expr={right_map[name].expr}",
            ))
        else:
            lm, rm = left_map[name], right_map[name]
            for fld, sev in [
                ("expr", "BREAKING"),
                ("description", "METADATA"),
                ("access_modifier", "METADATA"),
            ]:
                item = _diff_field(
                    f"{path}.{fld}", "metric",
                    getattr(lm, fld), getattr(rm, fld), sev,
                )
                if item:
                    items.append(item)
    return items


def _diff_primary_key(
    prefix: str,
    left: Optional[KeySpec],
    right: Optional[KeySpec],
) -> List[DiffItem]:
    items: List[DiffItem] = []
    path = f"{prefix}.primary_key"
    lc = sorted(left.columns) if left else []
    rc = sorted(right.columns) if right else []
    if lc != rc:
        items.append(DiffItem(
            path=path, category="key", change_type="modified",
            severity="BREAKING",
            left_value=str(lc), right_value=str(rc),
        ))
    return items


def _diff_unique_keys(
    prefix: str,
    left: List[KeySpec],
    right: List[KeySpec],
) -> List[DiffItem]:
    items: List[DiffItem] = []
    left_set = {tuple(sorted(k.columns)) for k in left}
    right_set = {tuple(sorted(k.columns)) for k in right}
    for cols in sorted(left_set - right_set):
        items.append(DiffItem(
            path=f"{prefix}.unique_keys", category="key",
            change_type="removed", severity="BREAKING",
            left_value=str(list(cols)),
        ))
    for cols in sorted(right_set - left_set):
        items.append(DiffItem(
            path=f"{prefix}.unique_keys", category="key",
            change_type="added", severity="BREAKING",
            right_value=str(list(cols)),
        ))
    return items


# ---------------------------------------------------------------------------
# Table-level diffing
# ---------------------------------------------------------------------------

def _diff_tables(
    view_name: str,
    left: List[Table],
    right: List[Table],
) -> List[DiffItem]:
    items: List[DiffItem] = []
    left_map = {t.name: t for t in left}
    right_map = {t.name: t for t in right}

    for name in sorted(set(left_map) | set(right_map)):
        path = f"{view_name}.tables.{name}"

        if name not in right_map:
            lt = left_map[name]
            items.append(DiffItem(
                path=path, category="table", change_type="removed",
                severity="BREAKING",
                left_value=f"{lt.base_table.database}.{lt.base_table.schema}.{lt.base_table.table}",
            ))
            continue

        if name not in left_map:
            rt = right_map[name]
            items.append(DiffItem(
                path=path, category="table", change_type="added",
                severity="BREAKING",
                right_value=f"{rt.base_table.database}.{rt.base_table.schema}.{rt.base_table.table}",
            ))
            continue

        lt, rt = left_map[name], right_map[name]

        # Base-table location
        for fld in ("database", "schema", "table"):
            item = _diff_field(
                f"{path}.base_table.{fld}", "table",
                getattr(lt.base_table, fld), getattr(rt.base_table, fld),
            )
            if item:
                items.append(item)

        # Description
        item = _diff_field(
            f"{path}.description", "table",
            lt.description, rt.description, "METADATA",
        )
        if item:
            items.append(item)

        # Components
        items.extend(_diff_dimensions(path, lt.dimensions, rt.dimensions))
        items.extend(_diff_facts(path, lt.facts, rt.facts))
        items.extend(_diff_metrics(path, lt.metrics, rt.metrics))
        items.extend(_diff_primary_key(path, lt.primary_key, rt.primary_key))
        items.extend(_diff_unique_keys(path, lt.unique_keys, rt.unique_keys))

    return items


# ---------------------------------------------------------------------------
# Relationship-level diffing
# ---------------------------------------------------------------------------

def _diff_relationships(
    view_name: str,
    left: List[Relationship],
    right: List[Relationship],
) -> List[DiffItem]:
    items: List[DiffItem] = []
    left_map = {r.name: r for r in left}
    right_map = {r.name: r for r in right}

    for name in sorted(set(left_map) | set(right_map)):
        path = f"{view_name}.relationships.{name}"

        if name not in right_map:
            lr = left_map[name]
            items.append(DiffItem(
                path=path, category="relationship", change_type="removed",
                severity="BREAKING",
                left_value=f"{lr.left_table} -> {lr.right_table}",
            ))
            continue

        if name not in left_map:
            rr = right_map[name]
            items.append(DiffItem(
                path=path, category="relationship", change_type="added",
                severity="BREAKING",
                right_value=f"{rr.left_table} -> {rr.right_table}",
            ))
            continue

        lr, rr = left_map[name], right_map[name]

        for fld in ("left_table", "right_table", "relationship_type"):
            item = _diff_field(
                f"{path}.{fld}", "relationship",
                getattr(lr, fld), getattr(rr, fld),
            )
            if item:
                items.append(item)

        # Join columns
        lc = sorted(
            (c.left_column, c.right_column) for c in lr.relationship_columns
        )
        rc = sorted(
            (c.left_column, c.right_column) for c in rr.relationship_columns
        )
        if lc != rc:
            items.append(DiffItem(
                path=f"{path}.relationship_columns",
                category="relationship",
                change_type="modified",
                severity="BREAKING",
                left_value=str(lc),
                right_value=str(rc),
            ))

    return items


# ---------------------------------------------------------------------------
# Instruction diffing
# ---------------------------------------------------------------------------

def _diff_instructions(
    left: Dict[str, Instruction],
    right: Dict[str, Instruction],
) -> List[DiffItem]:
    items: List[DiffItem] = []
    all_keys = sorted(set(left) | set(right))

    for key in all_keys:
        path = f"instructions.{key}"
        if key not in right:
            items.append(DiffItem(
                path=path, category="instruction", change_type="removed",
                severity="BREAKING",
                left_value=f"module={left[key].module}",
            ))
        elif key not in left:
            items.append(DiffItem(
                path=path, category="instruction", change_type="added",
                severity="BREAKING",
                right_value=f"module={right[key].module}",
            ))
        else:
            li, ri = left[key], right[key]
            for fld, sev in [
                ("module", "BREAKING"),
                ("version", "METADATA"),
                ("content", "BREAKING"),
                ("semantic_view", "BREAKING"),
                ("agent", "BREAKING"),
            ]:
                item = _diff_field(
                    f"{path}.{fld}", "instruction",
                    getattr(li, fld), getattr(ri, fld), sev,
                )
                if item:
                    items.append(item)

    return items


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def diff_semantic_views(
    left: SemanticView,
    right: SemanticView,
) -> List[DiffItem]:
    """Full-parity diff between two canonical SemanticView objects."""
    items: List[DiffItem] = []
    view_name = left.name or right.name

    # View-level description
    item = _diff_field(
        f"{view_name}.description", "view",
        left.description, right.description, "METADATA",
    )
    if item:
        items.append(item)

    # Custom instructions
    for ci_field in ("question_categorization", "sql_generation"):
        item = _diff_field(
            f"{view_name}.custom_instructions.{ci_field}", "custom_instructions",
            getattr(left.custom_instructions, ci_field),
            getattr(right.custom_instructions, ci_field),
            "BREAKING",
        )
        if item:
            items.append(item)

    items.extend(_diff_tables(view_name, left.tables, right.tables))
    items.extend(_diff_relationships(view_name, left.relationships, right.relationships))
    return items


def diff_snapshots(
    left: Snapshot,
    right: Snapshot,
    *,
    include_instructions: bool = True,
) -> DiffReport:
    """Full-parity diff between two complete snapshots.

    Parameters
    ----------
    include_instructions : bool
        Set to False when comparing Snowflake vs repo (instructions
        only exist in the repo).
    """
    items: List[DiffItem] = []

    # Semantic views
    all_views = sorted(set(left.semantic_views) | set(right.semantic_views))
    for view_name in all_views:
        lv = left.semantic_views.get(view_name)
        rv = right.semantic_views.get(view_name)
        if lv is None:
            items.append(DiffItem(
                path=view_name, category="view", change_type="added",
                severity="BREAKING", right_value=view_name,
            ))
        elif rv is None:
            items.append(DiffItem(
                path=view_name, category="view", change_type="removed",
                severity="BREAKING", left_value=view_name,
            ))
        else:
            items.extend(diff_semantic_views(lv, rv))

    # Instructions
    if include_instructions:
        items.extend(_diff_instructions(left.instructions, right.instructions))

    # Agents
    all_agents = sorted(set(left.agents) | set(right.agents))
    for agent_name in all_agents:
        la = left.agents.get(agent_name)
        ra = right.agents.get(agent_name)
        if la is None:
            items.append(DiffItem(
                path=f"agent.{agent_name}", category="agent",
                change_type="added", severity="BREAKING",
                right_value=agent_name,
            ))
        elif ra is None:
            items.append(DiffItem(
                path=f"agent.{agent_name}", category="agent",
                change_type="removed", severity="BREAKING",
                left_value=agent_name,
            ))
        else:
            for fld, sev in [
                ("display_name", "METADATA"),
                ("description", "METADATA"),
                ("orchestration_instructions", "BREAKING"),
                ("response_instructions", "BREAKING"),
            ]:
                item = _diff_field(
                    f"agent.{agent_name}.{fld}", "agent",
                    getattr(la, fld), getattr(ra, fld), sev,
                )
                if item:
                    items.append(item)

    return DiffReport(
        left_label=left.source,
        right_label=right.source,
        timestamp=datetime.now(timezone.utc).isoformat(),
        items=items,
    )
