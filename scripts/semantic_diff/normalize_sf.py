"""
Convert Snowflake DESCRIBE SEMANTIC VIEW output to canonical form.

Expects a CSV file produced by SnowSQL with the DESCRIBE result.
The semantic-view definition lives in the EXTENSION / CA / VALUE row
as a JSON string.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import List, Optional

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
# CSV helpers
# ---------------------------------------------------------------------------

def _read_csv(path: Path) -> list:
    """Read CSV with encoding fallback (SnowSQL may emit UTF-16)."""
    for enc in ("utf-8-sig", "utf-16", "utf-16-le", "cp1252"):
        try:
            with open(path, newline="", encoding=enc) as f:
                return list(csv.DictReader(f))
        except Exception:
            continue
    raise RuntimeError(f"Could not decode CSV: {path}")


def _extract_extension_json(rows: list) -> dict:
    """Extract the EXTENSION VALUE JSON from DESCRIBE output rows."""
    for row in rows:
        if (
            row.get("object_kind") == "EXTENSION"
            and row.get("object_name") == "CA"
            and row.get("property") == "VALUE"
        ):
            return json.loads(row["property_value"])
    raise ValueError("No EXTENSION/CA/VALUE row found in DESCRIBE output")


# ---------------------------------------------------------------------------
# Parsers (mirror normalize_yaml.py but operate on JSON dicts)
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

def _parse_custom_instructions(data: dict) -> CustomInstructions:
    ci = data.get("custom_instructions", {})
    return CustomInstructions(
        question_categorization=str(ci.get("question_categorization", "")),
        sql_generation=str(ci.get("sql_generation", "")),
    )


def load_snowflake_describe(path: Path, view_name: str = "") -> SemanticView:
    """Load a Snowflake DESCRIBE CSV export and return a canonical SemanticView."""
    rows = _read_csv(path)
    data = _extract_extension_json(rows)

    return SemanticView(
        name=data.get("name", view_name),
        description=data.get("description", ""),
        tables=sorted(
            [_parse_table(t) for t in data.get("tables", [])],
            key=lambda t: t.name,
        ),
        relationships=sorted(
            [_parse_relationship(r) for r in data.get("relationships", [])],
            key=lambda r: r.name,
        ),
        custom_instructions=_parse_custom_instructions(data),
    )


def load_snowflake_json(data: dict) -> SemanticView:
    """Load directly from a pre-parsed JSON dict."""
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
        custom_instructions=_parse_custom_instructions(data),
    )
