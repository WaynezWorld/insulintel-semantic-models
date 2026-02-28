"""
Convert repo YAML semantic-view files to canonical form.

Handles camelCase → snake_case normalisation so that files using either
convention (e.g. sem_activity.yaml uses camelCase relationship keys,
sem_insulintel.yaml uses snake_case) produce identical canonical output.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, List

import yaml

from .canonical import (
    BaseTable,
    CustomInstructions,
    Dimension,
    Fact,
    KeySpec,
    Metric,
    Relationship,
    RelationshipColumn,
    SemanticView,
    Table,
)


# ---------------------------------------------------------------------------
# Key normalisation
# ---------------------------------------------------------------------------

def _snake(name: str) -> str:
    """Convert camelCase to snake_case."""
    return re.sub(r"(?<=[a-z0-9])([A-Z])", r"_\1", name).lower()


def _normalize_keys(obj: Any) -> Any:
    """Recursively convert all dict keys to snake_case."""
    if isinstance(obj, dict):
        return {_snake(k): _normalize_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_normalize_keys(i) for i in obj]
    return obj


# ---------------------------------------------------------------------------
# Parsers for individual YAML stanzas
# ---------------------------------------------------------------------------

def _parse_base_table(d: dict) -> BaseTable:
    return BaseTable(
        database=d.get("database", ""),
        schema=d.get("schema", ""),
        table=d.get("table", ""),
    )


def _parse_dimension(d: dict) -> Dimension:
    return Dimension(
        name=d.get("name", ""),
        expr=d.get("expr", ""),
        data_type=d.get("data_type", ""),
        description=d.get("description", ""),
    )


def _parse_fact(f: dict) -> Fact:
    return Fact(
        name=f.get("name", ""),
        expr=f.get("expr", ""),
        data_type=f.get("data_type", ""),
        description=f.get("description", ""),
        access_modifier=f.get("access_modifier", ""),
    )


def _parse_metric(m: dict) -> Metric:
    return Metric(
        name=m.get("name", ""),
        expr=m.get("expr", ""),
        description=m.get("description", ""),
        access_modifier=m.get("access_modifier", ""),
    )


def _parse_key(k: dict) -> KeySpec:
    return KeySpec(columns=sorted(k.get("columns", [])))


def _parse_rel_col(rc: dict) -> RelationshipColumn:
    return RelationshipColumn(
        left_column=rc.get("left_column", ""),
        right_column=rc.get("right_column", ""),
    )


def _parse_relationship(r: dict) -> Relationship:
    return Relationship(
        name=r.get("name", ""),
        left_table=r.get("left_table", ""),
        right_table=r.get("right_table", ""),
        relationship_columns=[
            _parse_rel_col(rc) for rc in r.get("relationship_columns", [])
        ],
        relationship_type=r.get("relationship_type", ""),
    )


def _parse_table(t: dict) -> Table:
    pk_raw = t.get("primary_key")
    return Table(
        name=t.get("name", ""),
        description=t.get("description", ""),
        base_table=_parse_base_table(t.get("base_table", {})),
        dimensions=sorted(
            [_parse_dimension(d) for d in t.get("dimensions", [])],
            key=lambda d: d.name,
        ),
        facts=sorted(
            [_parse_fact(f) for f in t.get("facts", [])],
            key=lambda f: f.name,
        ),
        metrics=sorted(
            [_parse_metric(m) for m in t.get("metrics", [])],
            key=lambda m: m.name,
        ),
        primary_key=_parse_key(pk_raw) if pk_raw else None,
        unique_keys=sorted(
            [_parse_key(uk) for uk in t.get("unique_keys", [])],
            key=lambda k: tuple(k.columns),
        ),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def load_yaml_semantic_view(path: Path) -> SemanticView:
    """Load a repo YAML file and return a canonical SemanticView."""
    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    data = _normalize_keys(raw)

    ci_raw = data.get("custom_instructions", {})
    custom_instructions = CustomInstructions(
        question_categorization=str(ci_raw.get("question_categorization", "")),
        sql_generation=str(ci_raw.get("sql_generation", "")),
    )

    return SemanticView(
        name=data.get("name", ""),
        description=data.get("description", ""),
        tables=sorted(
            [_parse_table(t) for t in data.get("tables", [])],
            key=lambda t: t.name,
        ),
        relationships=sorted(
            [_parse_relationship(r) for r in data.get("relationships", [])],
            key=lambda r: r.name,
        ),
        custom_instructions=custom_instructions,
    )
