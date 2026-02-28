"""
Assemble modular instruction files into deployable blocks.

Reads instructions/assembly.yaml and concatenates the 'content' field
from each referenced module in order, producing:

  - custom_instructions.sql_generation / question_categorization
    for each semantic view
  - orchestration_instructions / response_instructions for each agent
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Set, Tuple

import yaml


def _load_assembly_config(repo_root: Path) -> dict:
    path = repo_root / "instructions" / "assembly.yaml"
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _read_module_content(repo_root: Path, rel_path: str) -> str:
    """Read the 'content' field from an instruction module."""
    full = repo_root / "instructions" / rel_path
    with open(full, encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return str(data.get("content", "")).strip()


def _concat_modules(repo_root: Path, module_paths: List[str]) -> str:
    """Concatenate content from multiple module files, separated by newlines."""
    parts = []
    for rel in module_paths:
        content = _read_module_content(repo_root, rel)
        if content:
            parts.append(content)
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def assemble_semantic_view_instructions(
    repo_root: Path,
) -> Dict[str, Dict[str, str]]:
    """Assemble custom_instructions for each semantic view.

    Returns::

        {
            "SEM_INSULINTEL": {
                "sql_generation": "...",
                "question_categorization": "...",
            },
            ...
        }
    """
    config = _load_assembly_config(repo_root)
    result: Dict[str, Dict[str, str]] = {}

    for view_name, targets in config.get("semantic_views", {}).items():
        result[view_name] = {}
        for target_field, modules in targets.items():
            result[view_name][target_field] = _concat_modules(
                repo_root, modules or []
            )
    return result


def assemble_agent_instructions(
    repo_root: Path,
) -> Dict[str, Dict[str, str]]:
    """Assemble instructions for each agent.

    Returns::

        {
            "INSULINTEL": {
                "orchestration_instructions": "...",
                "response_instructions": "...",
            },
        }
    """
    config = _load_assembly_config(repo_root)
    result: Dict[str, Dict[str, str]] = {}

    for agent_name, targets in config.get("agent", {}).items():
        result[agent_name] = {}
        for target_field, modules in targets.items():
            result[agent_name][target_field] = _concat_modules(
                repo_root, modules or []
            )
    return result


def collect_all_referenced_files(repo_root: Path) -> Set[str]:
    """Return the set of all module paths referenced in assembly.yaml."""
    config = _load_assembly_config(repo_root)
    referenced: Set[str] = set()

    for _view, targets in config.get("semantic_views", {}).items():
        for _field, modules in targets.items():
            referenced.update(modules or [])

    for _agent, targets in config.get("agent", {}).items():
        for _field, modules in targets.items():
            referenced.update(modules or [])

    return referenced


def find_orphaned_files(repo_root: Path) -> List[str]:
    """Return instruction files that exist but are NOT in assembly.yaml."""
    instr_dir = repo_root / "instructions"
    referenced = collect_all_referenced_files(repo_root)

    orphaned = []
    for yaml_path in sorted(instr_dir.rglob("*.yaml")):
        rel = yaml_path.relative_to(instr_dir).as_posix()
        if rel == "assembly.yaml":
            continue
        if rel not in referenced:
            orphaned.append(rel)
    return orphaned


def find_missing_files(repo_root: Path) -> List[str]:
    """Return files referenced in assembly.yaml that don't exist on disk."""
    instr_dir = repo_root / "instructions"
    referenced = collect_all_referenced_files(repo_root)

    missing = []
    for rel in sorted(referenced):
        if not (instr_dir / rel).exists():
            missing.append(rel)
    return missing
