"""
Load instruction YAML files into canonical form.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict

import yaml

from .canonical import Instruction


def load_instructions(repo_root: Path) -> Dict[str, Instruction]:
    """Load all instruction YAML files under ``instructions/``.

    Returns a dict keyed by relative POSIX path within the repo.
    """
    instructions: Dict[str, Instruction] = {}
    instr_dir = repo_root / "instructions"
    if not instr_dir.exists():
        return instructions

    for yaml_path in sorted(instr_dir.rglob("*.yaml")):
        rel_path = yaml_path.relative_to(repo_root).as_posix()
        with open(yaml_path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}

        instructions[rel_path] = Instruction(
            rel_path=rel_path,
            module=str(data.get("module", "")),
            version=str(data.get("version", "")),
            content=str(data.get("content", "")),
            semantic_view=str(data.get("semantic_view", "")),
            agent=str(data.get("agent", "")),
        )

    return instructions
