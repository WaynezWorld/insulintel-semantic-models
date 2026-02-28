"""
Export Snowflake semantic-view metadata via SnowSQL.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import List, Optional


from .constants import SEMANTIC_VIEW_FQNS

SEMANTIC_VIEWS = SEMANTIC_VIEW_FQNS

SNOWSQL_PATH = os.environ.get("SNOWSQL_PATH", shutil.which("snowsql") or "snowsql")


def export_describe(
    view_fqn: str,
    output_path: Path,
    connection: str = "",
    snowsql_path: str = SNOWSQL_PATH,
) -> None:
    """Run ``DESCRIBE SEMANTIC VIEW`` and save output as CSV."""
    query = f"DESCRIBE SEMANTIC VIEW {view_fqn};"
    cmd = [snowsql_path]
    if connection:
        cmd.extend(["-c", connection])
    cmd.extend([
        "-q", query,
        "-o", "output_format=csv",
        "-o", "header=true",
        "-o", "timing=false",
        "-o", "friendly=false",
        "-o", f"output_file={output_path}",
    ])
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(
            f"SnowSQL failed for {view_fqn}: {result.stderr.strip()}"
        )


def export_all(
    output_dir: Path,
    connection: str = "",
    views: Optional[List[str]] = None,
    snowsql_path: str = SNOWSQL_PATH,
) -> List[Path]:
    """Export ``DESCRIBE`` output for all (or specified) semantic views."""
    views = views or SEMANTIC_VIEWS
    paths: List[Path] = []
    for fqn in views:
        short_name = fqn.split(".")[-1].lower()
        out_path = output_dir / f"{short_name}_describe.csv"
        export_describe(
            fqn, out_path,
            connection=connection,
            snowsql_path=snowsql_path,
        )
        paths.append(out_path)
    return paths
