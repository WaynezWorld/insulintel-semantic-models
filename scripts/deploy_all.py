#!/usr/bin/env python3
"""
Deploy all semantic views + agent instructions from repo to Snowflake.

This script reads Snowflake credentials from .streamlit/secrets.toml and
deploys everything assembled from the instruction modules (via assembly.yaml).

Usage:
    python scripts/deploy_all.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]

# Bootstrap imports
if str(_REPO_ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "scripts"))
if str(_REPO_ROOT / "app") not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT / "app"))

from deployer import deploy_all_from_repo  # noqa: E402


def _connect():
    """Create a Snowflake connection from .streamlit/secrets.toml."""
    import tomllib

    import snowflake.connector

    secrets_path = _REPO_ROOT / ".streamlit" / "secrets.toml"
    if not secrets_path.exists():
        print(f"ERROR: {secrets_path} not found")
        sys.exit(1)

    with open(secrets_path, "rb") as f:
        cfg = tomllib.load(f)

    sf = cfg["snowflake"]
    params = {}
    for key in (
        "account", "user", "password", "role", "warehouse",
        "database", "schema", "authenticator", "token",
    ):
        val = sf.get(key)
        if val:
            params[key] = str(val)

    return snowflake.connector.connect(**params)


def main() -> int:
    print("Connecting to Snowflake…")
    conn = _connect()
    print("Connected.\n")

    print("Deploying all targets from repo…")
    results = deploy_all_from_repo(conn)

    print()
    ok = 0
    for r in results:
        icon = "✅" if "✅" in r else "❌" if "❌" in r else "⚠️"
        print(f"  {icon} {r}")
        if "✅" in r:
            ok += 1

    print(f"\nDone: {ok}/{len(results)} succeeded.")
    conn.close()
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
