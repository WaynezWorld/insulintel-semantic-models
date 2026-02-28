"""
Canonical schema definitions for semantic model diffing.

Every field in these dataclasses is subject to parity comparison between
Snowflake and the repository.  This module is the single source of truth
for what constitutes a "full diff".

Diff scope (all checked by default):
  - Tables:         name, description, base_table (database/schema/table)
  - Dimensions:     name, expr, data_type, description
  - Facts:          name, expr, data_type, description, access_modifier
  - Metrics:        name, expr, description, access_modifier
  - Primary keys:   columns
  - Unique keys:    columns
  - Relationships:  name, left_table, right_table, join columns, type
  - Custom instructions (per semantic view):
      question_categorization, sql_generation
  - Agent definition:
      display_name, description, orchestration_instructions,
      response_instructions, example_questions
  - Instruction modules (repo-only):
      module, version, content, semantic_view, agent
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Semantic view components
# ---------------------------------------------------------------------------

@dataclass
class BaseTable:
    database: str = ""
    schema: str = ""
    table: str = ""


@dataclass
class Dimension:
    name: str = ""
    expr: str = ""
    data_type: str = ""
    description: str = ""


@dataclass
class Fact:
    name: str = ""
    expr: str = ""
    data_type: str = ""
    description: str = ""
    access_modifier: str = ""


@dataclass
class Metric:
    name: str = ""
    expr: str = ""
    description: str = ""
    access_modifier: str = ""


@dataclass
class KeySpec:
    columns: List[str] = field(default_factory=list)


@dataclass
class RelationshipColumn:
    left_column: str = ""
    right_column: str = ""


@dataclass
class Relationship:
    name: str = ""
    left_table: str = ""
    right_table: str = ""
    relationship_columns: List[RelationshipColumn] = field(default_factory=list)
    relationship_type: str = ""


@dataclass
class CustomInstructions:
    """Snowflake semantic-view custom instructions."""
    question_categorization: str = ""
    sql_generation: str = ""


@dataclass
class Table:
    name: str = ""
    description: str = ""
    base_table: BaseTable = field(default_factory=BaseTable)
    dimensions: List[Dimension] = field(default_factory=list)
    facts: List[Fact] = field(default_factory=list)
    metrics: List[Metric] = field(default_factory=list)
    primary_key: Optional[KeySpec] = None
    unique_keys: List[KeySpec] = field(default_factory=list)


@dataclass
class SemanticView:
    name: str = ""
    description: str = ""
    tables: List[Table] = field(default_factory=list)
    relationships: List[Relationship] = field(default_factory=list)
    custom_instructions: CustomInstructions = field(default_factory=CustomInstructions)


# ---------------------------------------------------------------------------
# Instructions
# ---------------------------------------------------------------------------

@dataclass
class Instruction:
    rel_path: str = ""
    module: str = ""
    version: str = ""
    content: str = ""
    semantic_view: str = ""
    agent: str = ""


@dataclass
class AgentConfig:
    """Cortex Agent configuration — mirrors About + Orchestration tabs."""
    name: str = ""
    display_name: str = ""
    description: str = ""
    orchestration_instructions: str = ""
    response_instructions: str = ""


# ---------------------------------------------------------------------------
# Snapshot container
# ---------------------------------------------------------------------------

@dataclass
class Snapshot:
    timestamp: str = ""
    source: str = ""          # "snowflake" | "repo" | "file:<path>"
    semantic_views: Dict[str, SemanticView] = field(default_factory=dict)
    instructions: Dict[str, Instruction] = field(default_factory=dict)
    agents: Dict[str, AgentConfig] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Diff results
# ---------------------------------------------------------------------------

@dataclass
class DiffItem:
    """Single field-level difference."""
    path: str = ""
    category: str = ""        # table | dimension | fact | metric | key | relationship | instruction | view
    change_type: str = ""     # added | removed | modified
    severity: str = ""        # BREAKING | METADATA
    left_value: str = ""
    right_value: str = ""


@dataclass
class DiffReport:
    """Complete diff between two snapshots."""
    left_label: str = ""
    right_label: str = ""
    timestamp: str = ""
    items: List[DiffItem] = field(default_factory=list)

    # -- convenience properties --

    @property
    def breaking_count(self) -> int:
        return sum(1 for i in self.items if i.severity == "BREAKING")

    @property
    def metadata_count(self) -> int:
        return sum(1 for i in self.items if i.severity == "METADATA")

    @property
    def is_clean(self) -> bool:
        return len(self.items) == 0

    # -- output helpers --

    def summary(self) -> str:
        if self.is_clean:
            return "No differences found."
        lines = [
            f"Diff: {self.left_label} vs {self.right_label}",
            f"  {self.breaking_count} BREAKING, {self.metadata_count} METADATA",
            "",
        ]
        for item in self.items:
            marker = "!" if item.severity == "BREAKING" else "~"
            lines.append(f"  [{marker}] {item.change_type.upper():8s}  {item.path}")
            if item.change_type == "added":
                lines.append(f"             + {item.right_value}")
            elif item.change_type == "removed":
                lines.append(f"             - {item.left_value}")
            else:
                lines.append(f"             - {item.left_value}")
                lines.append(f"             + {item.right_value}")
        return "\n".join(lines)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), indent=2, sort_keys=True)
