#!/usr/bin/env python3
"""
CLI for semantic model diff operations.

Usage
-----
  python scripts/semantic_diff/cli.py export   [--connection NAME]
  python scripts/semantic_diff/cli.py snapshot  --source repo|snowflake
  python scripts/semantic_diff/cli.py diff      --left FILE --right FILE
  python scripts/semantic_diff/cli.py diff-live --connection NAME
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Bootstrap: prefer pip-installed package; fall back to relative path.
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).resolve().parent
_REPO_ROOT = _SCRIPT_DIR.parents[1]

try:
    import semantic_diff  # noqa: F401
except ImportError:
    if str(_SCRIPT_DIR.parent) not in sys.path:
        sys.path.insert(0, str(_SCRIPT_DIR.parent))

from semantic_diff.canonical import AgentConfig, Snapshot
from semantic_diff.normalize_yaml import load_yaml_semantic_view
from semantic_diff.normalize_sf import load_snowflake_describe
from semantic_diff.instructions import load_instructions
from semantic_diff.assemble import (
    assemble_semantic_view_instructions,
    assemble_agent_instructions,
    find_orphaned_files,
    find_missing_files,
)
from semantic_diff.diff_engine import diff_snapshots
from semantic_diff.snapshot import save_snapshot, load_snapshot, create_timestamp_label
from semantic_diff.export_sf import export_all, SEMANTIC_VIEWS


# ---------------------------------------------------------------------------
# YAML ↔ Snowflake view mapping
# ---------------------------------------------------------------------------
YAML_MAP = {
    "SEM_INSULINTEL": "semantic_views/sem_insulintel.yaml",
    "SEM_ACTIVITY":   "semantic_views/sem_activity.yaml",
    "SEM_NHANES":     "semantic_views/sem_nhanes.yaml",
}


# ---------------------------------------------------------------------------
# Snapshot builders
# ---------------------------------------------------------------------------

def build_repo_snapshot(repo_root: Path) -> Snapshot:
    """Build a canonical snapshot from repo YAML + assembled instructions + agent."""
    views = {}
    assembled_ci = assemble_semantic_view_instructions(repo_root)

    for view_name, rel_path in YAML_MAP.items():
        yaml_path = repo_root / rel_path
        if yaml_path.exists():
            sv = load_yaml_semantic_view(yaml_path)
            # Overlay assembled custom_instructions from modules
            if view_name in assembled_ci:
                sv.custom_instructions.sql_generation = (
                    assembled_ci[view_name].get("sql_generation", "")
                )
                sv.custom_instructions.question_categorization = (
                    assembled_ci[view_name].get("question_categorization", "")
                )
            views[view_name] = sv

    instructions = load_instructions(repo_root)

    # Agent config from assembled modules
    agents = {}
    assembled_agents = assemble_agent_instructions(repo_root)
    for agent_name, fields in assembled_agents.items():
        agents[agent_name] = AgentConfig(
            name=agent_name,
            orchestration_instructions=fields.get("orchestration_instructions", ""),
            response_instructions=fields.get("response_instructions", ""),
        )

    return Snapshot(
        timestamp=datetime.now(timezone.utc).isoformat(),
        source="repo",
        semantic_views=views,
        instructions=instructions,
        agents=agents,
    )


def build_sf_snapshot(describe_dir: Path) -> Snapshot:
    """Build a canonical snapshot from exported Snowflake DESCRIBE CSVs."""
    views = {}
    for fqn in SEMANTIC_VIEWS:
        short = fqn.split(".")[-1]
        csv_path = describe_dir / f"{short.lower()}_describe.csv"
        if csv_path.exists():
            views[short] = load_snowflake_describe(csv_path, view_name=short)

    return Snapshot(
        timestamp=datetime.now(timezone.utc).isoformat(),
        source="snowflake",
        semantic_views=views,
        instructions={},          # instructions don't exist in Snowflake
    )


# ---------------------------------------------------------------------------
# CLI sub-commands
# ---------------------------------------------------------------------------

def cmd_export(args: argparse.Namespace) -> int:
    """Export DESCRIBE CSVs from Snowflake."""
    output_dir = Path(args.output_dir)
    paths = export_all(output_dir, connection=args.connection)
    for p in paths:
        print(f"  {p}")
    print(f"Exported {len(paths)} DESCRIBE CSV(s) to {output_dir}/")
    return 0


def cmd_snapshot(args: argparse.Namespace) -> int:
    """Create and persist a canonical JSON snapshot."""
    if args.source == "repo":
        snap = build_repo_snapshot(_REPO_ROOT)
    elif args.source == "snowflake":
        describe_dir = Path(args.describe_dir or ".tmp_sync")
        snap = build_sf_snapshot(describe_dir)
    else:
        print(f"Unknown source: {args.source}", file=sys.stderr)
        return 1

    out = Path(
        args.output
        or f"snapshots/{args.source}_{create_timestamp_label()}.json"
    )
    save_snapshot(snap, out)
    print(f"Snapshot saved: {out}")
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    """Diff two previously-saved snapshot files."""
    left = load_snapshot(Path(args.left))
    right = load_snapshot(Path(args.right))
    report = diff_snapshots(left, right)
    print(report.summary())

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(report.to_json(), encoding="utf-8")
        print(f"\nFull report saved: {args.output}")

    return 1 if not report.is_clean else 0


def cmd_diff_live(args: argparse.Namespace) -> int:
    """Export from Snowflake, build both snapshots, diff semantics."""
    describe_dir = Path(args.describe_dir or ".tmp_sync")

    print("Exporting from Snowflake...")
    export_all(describe_dir, connection=args.connection)

    print("Building snapshots...")
    sf_snap = build_sf_snapshot(describe_dir)
    repo_snap = build_repo_snapshot(_REPO_ROOT)

    # Snowflake has no instructions → skip instruction diff
    report = diff_snapshots(sf_snap, repo_snap, include_instructions=False)

    print()
    print(report.summary())

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(report.to_json(), encoding="utf-8")
        print(f"\nFull report saved: {args.output}")

    return 1 if not report.is_clean else 0


def cmd_diff_repo(args: argparse.Namespace) -> int:
    """Diff current repo state against a saved snapshot (includes instructions)."""
    saved = load_snapshot(Path(args.baseline))
    current = build_repo_snapshot(_REPO_ROOT)

    report = diff_snapshots(saved, current, include_instructions=True)

    print()
    print(report.summary())

    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(report.to_json(), encoding="utf-8")
        print(f"\nFull report saved: {args.output}")

    return 1 if not report.is_clean else 0


def cmd_assemble(args: argparse.Namespace) -> int:
    """Show assembled instruction text for a target."""
    if args.target in ("views", "all"):
        assembled = assemble_semantic_view_instructions(_REPO_ROOT)
        for view_name, fields in sorted(assembled.items()):
            print(f"\n{'='*60}")
            print(f"  {view_name}")
            print(f"{'='*60}")
            for field_name, text in sorted(fields.items()):
                print(f"\n--- {field_name} ---")
                print(text)

    if args.target in ("agent", "all"):
        assembled = assemble_agent_instructions(_REPO_ROOT)
        for agent_name, fields in sorted(assembled.items()):
            print(f"\n{'='*60}")
            print(f"  AGENT: {agent_name}")
            print(f"{'='*60}")
            for field_name, text in sorted(fields.items()):
                print(f"\n--- {field_name} ---")
                print(text)

    # Orphan check
    orphaned = find_orphaned_files(_REPO_ROOT)
    missing = find_missing_files(_REPO_ROOT)
    if orphaned:
        print(f"\nWARNING: {len(orphaned)} orphaned instruction file(s):")
        for f in orphaned:
            print(f"  {f}")
    if missing:
        print(f"\nERROR: {len(missing)} missing instruction file(s):")
        for f in missing:
            print(f"  {f}")
        return 1

    return 0


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        prog="semantic_diff",
        description="Semantic model diff engine for insulintel-semantic-models",
    )
    sub = parser.add_subparsers(dest="command")

    # ── export ──────────────────────────────────────────────────────────
    p_export = sub.add_parser("export", help="Export Snowflake DESCRIBE CSVs")
    p_export.add_argument("--connection", default="", help="SnowSQL connection name")
    p_export.add_argument("--output-dir", default=".tmp_sync", help="Output directory")

    # ── snapshot ────────────────────────────────────────────────────────
    p_snap = sub.add_parser("snapshot", help="Create a canonical snapshot")
    p_snap.add_argument("--source", required=True, choices=["repo", "snowflake"])
    p_snap.add_argument(
        "--describe-dir", default=".tmp_sync",
        help="Dir with DESCRIBE CSVs (for snowflake source)",
    )
    p_snap.add_argument("--output", help="Output JSON path")

    # ── diff ────────────────────────────────────────────────────────────
    p_diff = sub.add_parser("diff", help="Diff two snapshot files")
    p_diff.add_argument("--left", required=True, help="Left snapshot JSON")
    p_diff.add_argument("--right", required=True, help="Right snapshot JSON")
    p_diff.add_argument("--output", help="Save full report JSON")

    # ── diff-live ───────────────────────────────────────────────────────
    p_live = sub.add_parser("diff-live", help="Export + diff Snowflake vs repo")
    p_live.add_argument("--connection", default="", help="SnowSQL connection name")
    p_live.add_argument("--describe-dir", default=".tmp_sync")
    p_live.add_argument("--output", help="Save full report JSON")

    # ── diff-repo ───────────────────────────────────────────────────────
    p_repo = sub.add_parser(
        "diff-repo",
        help="Diff current repo against a saved baseline (includes instructions)",
    )
    p_repo.add_argument("--baseline", required=True, help="Baseline snapshot JSON")
    p_repo.add_argument("--output", help="Save full report JSON")

    # ── assemble ────────────────────────────────────────────────────────
    p_asm = sub.add_parser(
        "assemble",
        help="Show assembled instruction text for views or agent",
    )
    p_asm.add_argument(
        "--target", required=True, choices=["views", "agent", "all"],
        help="Which instructions to assemble",
    )

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        return 1

    handlers = {
        "export": cmd_export,
        "snapshot": cmd_snapshot,
        "diff": cmd_diff,
        "diff-live": cmd_diff_live,
        "diff-repo": cmd_diff_repo,
        "assemble": cmd_assemble,
    }
    return handlers[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
