"""
Save and load snapshots (point-in-time and full-repo bundles).
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from .canonical import (
    AgentConfig,
    BaseTable,
    CustomInstructions,
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


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

def save_snapshot(snapshot: Snapshot, path: Path) -> None:
    """Serialise a snapshot to a JSON file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(asdict(snapshot), f, indent=2, sort_keys=True)


# ---------------------------------------------------------------------------
# Deserialization helpers
# ---------------------------------------------------------------------------

def _rebuild_base_table(d: dict) -> BaseTable:
    return BaseTable(**d)


def _rebuild_dimension(d: dict) -> Dimension:
    return Dimension(**d)


def _rebuild_fact(d: dict) -> Fact:
    return Fact(**d)


def _rebuild_metric(d: dict) -> Metric:
    return Metric(**d)


def _rebuild_key(d: dict) -> KeySpec:
    return KeySpec(columns=d.get("columns", []))


def _rebuild_rel_col(d: dict) -> RelationshipColumn:
    return RelationshipColumn(**d)


def _rebuild_relationship(d: dict) -> Relationship:
    return Relationship(
        name=d["name"],
        left_table=d["left_table"],
        right_table=d["right_table"],
        relationship_columns=[
            _rebuild_rel_col(rc) for rc in d.get("relationship_columns", [])
        ],
        relationship_type=d.get("relationship_type", ""),
    )


def _rebuild_table(d: dict) -> Table:
    return Table(
        name=d["name"],
        description=d.get("description", ""),
        base_table=_rebuild_base_table(d["base_table"]),
        dimensions=[_rebuild_dimension(dim) for dim in d.get("dimensions", [])],
        facts=[_rebuild_fact(f) for f in d.get("facts", [])],
        metrics=[_rebuild_metric(m) for m in d.get("metrics", [])],
        primary_key=_rebuild_key(d["primary_key"]) if d.get("primary_key") else None,
        unique_keys=[_rebuild_key(uk) for uk in d.get("unique_keys", [])],
    )


def _rebuild_semantic_view(d: dict) -> SemanticView:
    ci = d.get("custom_instructions", {})
    return SemanticView(
        name=d["name"],
        description=d.get("description", ""),
        tables=[_rebuild_table(t) for t in d.get("tables", [])],
        relationships=[_rebuild_relationship(r) for r in d.get("relationships", [])],
        custom_instructions=CustomInstructions(
            question_categorization=ci.get("question_categorization", ""),
            sql_generation=ci.get("sql_generation", ""),
        ),
    )


def _rebuild_instruction(d: dict) -> Instruction:
    return Instruction(**d)


def _rebuild_agent(d: dict) -> AgentConfig:
    return AgentConfig(**d)


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------

def load_snapshot(path: Path) -> Snapshot:
    """Deserialise a snapshot from a JSON file."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    return Snapshot(
        timestamp=data["timestamp"],
        source=data["source"],
        semantic_views={
            k: _rebuild_semantic_view(v)
            for k, v in data.get("semantic_views", {}).items()
        },
        instructions={
            k: _rebuild_instruction(v)
            for k, v in data.get("instructions", {}).items()
        },
        agents={
            k: _rebuild_agent(v)
            for k, v in data.get("agents", {}).items()
        },
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def create_timestamp_label() -> str:
    """ISO-ish label safe for filenames."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
