#!/usr/bin/env python3
"""
Minimal repository validator for insulintel-semantic-models.

Checks:
1) Expected semantic model YAML files exist under semantic_views/
2) scripts/deploy.sql references all expected model YAML files
3) SQL FROM/JOIN table references in scripts/*.sql are FQDN (DB.SCHEMA.OBJECT),
   excluding CTE names, stage references, and common table-function patterns.
4) instructions/assembly.yaml references all instruction files (no orphans)
5) All files referenced in assembly.yaml exist on disk (no missing)
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Set


EXPECTED_MODELS = {
    "sem_insulintel.yaml",
    "sem_activity.yaml",
    "sem_nhanes.yaml",
}


@dataclass
class Finding:
    level: str  # ERROR | WARN
    message: str
    path: Optional[Path] = None
    line: Optional[int] = None

    def format(self) -> str:
        location = ""
        if self.path:
            location = str(self.path)
            if self.line:
                location += f":{self.line}"
            location += ": "
        return f"[{self.level}] {location}{self.message}"


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def line_number(text: str, index: int) -> int:
    return text.count("\n", 0, index) + 1


def strip_sql_comments(sql: str) -> str:
    def _block_replacer(match: re.Match[str]) -> str:
        return "\n" * match.group(0).count("\n")

    sql = re.sub(r"/\*.*?\*/", _block_replacer, sql, flags=re.DOTALL)
    sql = re.sub(r"--[^\n]*", "", sql)
    return sql


def collect_cte_names(sql_no_comments: str) -> Set[str]:
    cte_names: Set[str] = set()
    pattern = re.compile(r"(?:WITH|,)\s*([A-Z_][A-Z0-9_$]*)\s+AS\s*\(", re.IGNORECASE)
    for match in pattern.finditer(sql_no_comments):
        cte_names.add(match.group(1).upper())
    return cte_names


def clean_table_token(token: str) -> str:
    token = token.strip()
    token = token.rstrip(",;")
    token = token.strip('"')
    return token


def validate_sql_fqdn(sql_path: Path) -> List[Finding]:
    findings: List[Finding] = []
    raw = read_text(sql_path)
    text = strip_sql_comments(raw)
    cte_names = collect_cte_names(text)

    ref_pattern = re.compile(r"\b(?:FROM|JOIN)\s+([^\s\n]+)", re.IGNORECASE)

    for match in ref_pattern.finditer(text):
        token = clean_table_token(match.group(1))
        token_upper = token.upper()

        if not token:
            continue

        if token.startswith("("):
            continue

        if token.startswith("@"):
            continue

        if token_upper in cte_names:
            continue

        if token_upper.startswith("TABLE("):
            continue

        if token_upper.startswith("LATERAL"):
            continue

        if "(" in token or ")" in token:
            continue

        parts = [p for p in token.split(".") if p]
        if len(parts) != 3:
            findings.append(
                Finding(
                    "ERROR",
                    f"Non-FQDN table reference in SQL: {token} (expected DB.SCHEMA.OBJECT)",
                    sql_path,
                    line_number(text, match.start(1)),
                )
            )

    return findings


def validate_expected_models(root: Path) -> List[Finding]:
    findings: List[Finding] = []
    semantic_dir = root / "semantic_views"

    for model_file in sorted(EXPECTED_MODELS):
        path = semantic_dir / model_file
        if not path.exists():
            findings.append(Finding("ERROR", f"Missing semantic model file: semantic_views/{model_file}", path))

    existing_models = {p.name for p in semantic_dir.glob("*.yaml")} if semantic_dir.exists() else set()
    extras = sorted(existing_models - EXPECTED_MODELS)
    for model_file in extras:
        findings.append(
            Finding(
                "WARN",
                f"Model YAML exists but is not in expected set: semantic_views/{model_file}",
                semantic_dir / model_file,
            )
        )

    return findings


def validate_deploy_wiring(root: Path) -> List[Finding]:
    findings: List[Finding] = []
    deploy_path = root / "scripts" / "deploy.sql"
    if not deploy_path.exists():
        return [Finding("ERROR", "Missing deployment script: scripts/deploy.sql", deploy_path)]

    deploy_sql = read_text(deploy_path)
    for model_file in sorted(EXPECTED_MODELS):
        if model_file not in deploy_sql:
            findings.append(
                Finding(
                    "ERROR",
                    f"scripts/deploy.sql is missing semantic model reference: {model_file}",
                    deploy_path,
                )
            )

    return findings


def validate_sql_files(root: Path) -> List[Finding]:
    findings: List[Finding] = []
    sql_files = sorted((root / "scripts").glob("*.sql"))
    for sql_path in sql_files:
        findings.extend(validate_sql_fqdn(sql_path))
    return findings


def validate_instruction_assembly(root: Path) -> List[Finding]:
    """Check that assembly.yaml covers all instruction files and vice-versa."""
    findings: List[Finding] = []
    assembly_path = root / "instructions" / "assembly.yaml"
    if not assembly_path.exists():
        findings.append(Finding("ERROR", "Missing instructions/assembly.yaml", assembly_path))
        return findings

    # Import assembly helpers (same repo)
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "assemble",
        root / "scripts" / "semantic_diff" / "assemble.py",
        submodule_search_locations=[str(root / "scripts")],
    )
    # Fallback: inline check using yaml
    try:
        import yaml
        with open(assembly_path, encoding="utf-8") as f:
            config = yaml.safe_load(f)

        # Collect all referenced paths
        referenced: Set[str] = set()
        for _view, targets in (config.get("semantic_views") or {}).items():
            for _field, modules in (targets or {}).items():
                referenced.update(modules or [])
        for _agent, targets in (config.get("agent") or {}).items():
            for _field, modules in (targets or {}).items():
                referenced.update(modules or [])

        instr_dir = root / "instructions"

        # Check for missing files
        for rel in sorted(referenced):
            if not (instr_dir / rel).exists():
                findings.append(Finding(
                    "ERROR",
                    f"assembly.yaml references missing file: instructions/{rel}",
                    instr_dir / rel,
                ))

        # Check for orphaned files
        for yaml_path in sorted(instr_dir.rglob("*.yaml")):
            rel = yaml_path.relative_to(instr_dir).as_posix()
            if rel == "assembly.yaml":
                continue
            if rel not in referenced:
                findings.append(Finding(
                    "ERROR",
                    f"Instruction file not in assembly.yaml (orphaned): instructions/{rel}",
                    yaml_path,
                ))

    except ImportError:
        findings.append(Finding("WARN", "pyyaml not installed — skipping assembly validation"))

    return findings


def print_findings(findings: Iterable[Finding]) -> int:
    findings = list(findings)
    warns = [f for f in findings if f.level == "WARN"]
    errors = [f for f in findings if f.level == "ERROR"]

    for finding in warns + errors:
        print(finding.format())

    if errors:
        print(f"\nValidation failed: {len(errors)} error(s), {len(warns)} warning(s).")
        return 1

    if warns:
        print(f"\nValidation passed with {len(warns)} warning(s).")
    else:
        print("\nValidation passed with no findings.")
    return 0


def main() -> int:
    root = repo_root()
    findings: List[Finding] = []

    findings.extend(validate_expected_models(root))
    findings.extend(validate_deploy_wiring(root))
    findings.extend(validate_sql_files(root))
    findings.extend(validate_instruction_assembly(root))

    return print_findings(findings)


if __name__ == "__main__":
    raise SystemExit(main())
