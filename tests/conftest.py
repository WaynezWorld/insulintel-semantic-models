"""
Shared pytest configuration and fixtures.

Provides:
  --live       CLI flag to enable Snowflake integration tests
  snowflake_conn   session-scoped fixture for a live Snowflake connection
  live           marker to tag tests requiring Snowflake connectivity

Usage:
  pytest tests/ -q                  # unit tests only (default)
  pytest tests/ -q --live           # unit + integration tests
  pytest tests/ -q -m live          # integration tests only
  pytest tests/ -q -m "not live"    # unit tests only (explicit)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import pytest


# ---------------------------------------------------------------------------
# CLI option
# ---------------------------------------------------------------------------

def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--live",
        action="store_true",
        default=False,
        help="Run integration tests that require a live Snowflake connection.",
    )


# ---------------------------------------------------------------------------
# Auto-skip tests marked @pytest.mark.live unless --live is passed
# ---------------------------------------------------------------------------

def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "live: mark test as requiring a live Snowflake connection (deselected by default, use --live to run)",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    if config.getoption("--live"):
        return  # --live passed → run everything
    skip_live = pytest.mark.skip(reason="Need --live flag to run Snowflake integration tests")
    for item in items:
        if "live" in item.keywords:
            item.add_marker(skip_live)


# ---------------------------------------------------------------------------
# Snowflake connection fixture
# ---------------------------------------------------------------------------

def _load_streamlit_secrets() -> dict:
    """Load Snowflake credentials from .streamlit/secrets.toml."""
    repo_root = Path(__file__).resolve().parent.parent
    secrets_path = repo_root / ".streamlit" / "secrets.toml"
    if not secrets_path.exists():
        return {}
    # Parse TOML (Python 3.11+ has tomllib, fall back to toml package)
    try:
        import tomllib
    except ImportError:
        try:
            import tomli as tomllib  # type: ignore[no-redef]
        except ImportError:
            # Manual minimal parse for [connections.snowflake] section
            return _parse_secrets_minimal(secrets_path)
    with open(secrets_path, "rb") as f:
        data = tomllib.load(f)
    return data.get("connections", {}).get("snowflake", {})


def _parse_secrets_minimal(path: Path) -> dict:
    """Minimal TOML parser — extracts key = "value" pairs after [connections.snowflake]."""
    result = {}
    in_section = False
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped == "[connections.snowflake]":
            in_section = True
            continue
        if stripped.startswith("[") and in_section:
            break  # new section
        if in_section and "=" in stripped:
            key, _, val = stripped.partition("=")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            result[key] = val
    return result


@pytest.fixture(scope="session")
def snowflake_conn(request: pytest.FixtureRequest):
    """Session-scoped Snowflake connection.

    Credentials are resolved in order:
      1. Environment variables: SNOWFLAKE_ACCOUNT, SNOWFLAKE_USER, SNOWFLAKE_TOKEN
      2. .streamlit/secrets.toml (project root)

    Yields a ``snowflake.connector.Connection`` and closes it after the session.
    """
    if not request.config.getoption("--live"):
        pytest.skip("--live flag not provided")

    import snowflake.connector

    # Try env vars first (CI-friendly)
    account = os.environ.get("SNOWFLAKE_ACCOUNT", "")
    user = os.environ.get("SNOWFLAKE_USER", "")
    token = os.environ.get("SNOWFLAKE_TOKEN", "")
    database = os.environ.get("SNOWFLAKE_DATABASE", "")
    schema = os.environ.get("SNOWFLAKE_SCHEMA", "")
    warehouse = os.environ.get("SNOWFLAKE_WAREHOUSE", "")

    # Fall back to Streamlit secrets
    if not (account and user and token):
        secrets = _load_streamlit_secrets()
        account = account or secrets.get("account", "")
        user = user or secrets.get("user", "")
        token = token or secrets.get("token", "") or secrets.get("authenticator_token", "")
        database = database or secrets.get("database", "")
        schema = schema or secrets.get("schema", "")
        warehouse = warehouse or secrets.get("warehouse", "")

    if not account:
        pytest.skip("No Snowflake credentials found (set env vars or .streamlit/secrets.toml)")

    conn = snowflake.connector.connect(
        account=account,
        user=user,
        token=token,
        authenticator="oauth",
        database=database,
        schema=schema,
        warehouse=warehouse,
    )
    yield conn
    conn.close()
