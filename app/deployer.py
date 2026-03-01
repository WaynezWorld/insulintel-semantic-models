"""
Snowflake deployment and query operations for the Instruction Manager.

All functions accept pre-assembled instruction text — the Streamlit app
is responsible for assembling from editor state or files.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Dict

import yaml

# ---------------------------------------------------------------------------
# Path setup
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[1]

try:
    import semantic_diff  # noqa: F401  — package is pip-installed
except ImportError:
    if str(REPO_ROOT / "scripts") not in sys.path:
        sys.path.insert(0, str(REPO_ROOT / "scripts"))

from semantic_diff.assemble import (
    assemble_semantic_view_instructions,
    assemble_agent_instructions,
)
from semantic_diff.constants import SCHEMA_FQN, AGENT_FQN, SEMANTIC_VIEW_NAMES

YAML_MAP: Dict[str, Path] = {
    "SEM_INSULINTEL": REPO_ROOT / "semantic_views" / "sem_insulintel.yaml",
    "SEM_ACTIVITY": REPO_ROOT / "semantic_views" / "sem_activity.yaml",
    "SEM_NHANES": REPO_ROOT / "semantic_views" / "sem_nhanes.yaml",
}


# ---------------------------------------------------------------------------
# YAML dumper — forces block style (|) for multiline strings
# ---------------------------------------------------------------------------
class _BlockDumper(yaml.SafeDumper):
    pass


def _str_representer(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_BlockDumper.add_representer(str, _str_representer)


# ---------------------------------------------------------------------------
# Deploy helpers
# ---------------------------------------------------------------------------

def build_deployable_yaml(
    view_name: str,
    custom_instructions: Dict[str, str] | None = None,
) -> str:
    """Read a semantic-view YAML from repo — **without** custom_instructions.

    Snowflake Semantic Views do not support ``custom_instructions`` in the
    YAML spec passed to ``SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML``.
    Custom instructions must be set via ``AI_SQL_GENERATION`` /
    ``AI_QUESTION_CATEGORIZATION`` clauses in ``CREATE SEMANTIC VIEW``.

    Returns the full YAML text (structure only, no AI instructions).
    """
    yaml_path = YAML_MAP[view_name]
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    # Strip custom_instructions if they leaked into the base YAML
    data.pop("custom_instructions", None)

    return yaml.dump(
        data,
        Dumper=_BlockDumper,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
        width=10000,
    )


# ---------------------------------------------------------------------------
# Deploy operations
# ---------------------------------------------------------------------------

def deploy_semantic_view(
    conn,
    view_name: str,
    custom_instructions: Dict[str, str],
) -> str:
    """Deploy a semantic view with custom instructions.

    Two-step process (required by Snowflake's Semantic View architecture):
    1. Deploy the base YAML via ``SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML``
    2. Set ``AI_SQL_GENERATION`` / ``AI_QUESTION_CATEGORIZATION`` via
       ``CREATE OR REPLACE SEMANTIC VIEW`` (using ``GET_DDL`` as the base).
    """
    fqn = f"{SCHEMA_FQN}.{view_name}"
    yaml_text = build_deployable_yaml(view_name)
    cursor = conn.cursor()
    try:
        # Step 1: Deploy base YAML (structure, tables, metrics, etc.)
        cursor.execute(
            "CALL SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML(%s, %s)",
            (SCHEMA_FQN, yaml_text),
        )
        cursor.fetchone()

        # Step 2: Set AI instructions via CREATE OR REPLACE
        sg = custom_instructions.get("sql_generation", "").strip()
        qc = custom_instructions.get("question_categorization", "").strip()

        if sg or qc:
            # Get current DDL and inject AI clauses
            cursor.execute(
                f"SELECT GET_DDL('SEMANTIC_VIEW', '{fqn}', TRUE)"
            )
            ddl_row = cursor.fetchone()
            if ddl_row:
                import re

                ddl = ddl_row[0].rstrip().rstrip(";")

                # Remove existing AI clauses if present
                ddl = re.sub(
                    r"\s+AI_SQL_GENERATION\s+'(?:[^']|'')*'",
                    "", ddl, flags=re.IGNORECASE,
                )
                ddl = re.sub(
                    r"\s+AI_QUESTION_CATEGORIZATION\s+'(?:[^']|'')*'",
                    "", ddl, flags=re.IGNORECASE,
                )

                # Remove the 'with extension (...)' clause — Snowflake
                # auto-generates it and it conflicts with AI clauses
                ddl = re.sub(
                    r"\s*with\s+extension\s*\([^)]*\)\s*$",
                    "", ddl, flags=re.IGNORECASE,
                )

                # Build AI clauses
                ai_clauses = ""
                if sg:
                    escaped_sg = sg.replace("'", "''")
                    ai_clauses += f"\n  AI_SQL_GENERATION '{escaped_sg}'"
                if qc:
                    escaped_qc = qc.replace("'", "''")
                    ai_clauses += f"\n  AI_QUESTION_CATEGORIZATION '{escaped_qc}'"

                # Ensure COPY GRANTS is present
                if "COPY GRANTS" not in ddl.upper():
                    ai_clauses += "\n  COPY GRANTS"

                full_sql = ddl + ai_clauses + ";"
                cursor.execute(full_sql)

        return f"✅ {view_name} deployed"
    except Exception as e:
        return f"❌ Deploy failed: {e}"
    finally:
        cursor.close()


def deploy_agent_field(conn, field_name: str, instruction_text: str) -> str:
    """Update a single agent instruction field via ``ALTER AGENT``.

    Reads the current spec, patches the requested instruction field,
    and writes back the full spec (Snowflake's ALTER AGENT requires
    a complete specification replacement).
    """
    import snowflake.connector

    cursor = conn.cursor(snowflake.connector.DictCursor)
    try:
        # 1. Fetch current spec
        cursor.execute(f"DESCRIBE AGENT {AGENT_FQN}")
        rows = cursor.fetchall()
        if not rows:
            return "❌ Agent not found"

        spec_raw = _row_get(rows[0], "agent_spec")
        try:
            spec = json.loads(spec_raw) if spec_raw else {}
        except (json.JSONDecodeError, TypeError):
            spec = {}

        # 2. Patch the instruction field
        instructions = spec.setdefault("instructions", {})
        # Map our field names to the spec keys
        field_map = {
            "orchestration_instructions": "orchestration",
            "response_instructions": "response",
        }
        spec_key = field_map.get(field_name, field_name)
        instructions[spec_key] = instruction_text

        # 3. Write back the full spec as YAML
        spec_yaml = yaml.dump(
            spec, Dumper=_BlockDumper, default_flow_style=False,
            sort_keys=False, allow_unicode=True, width=10000,
        )
        cursor2 = conn.cursor()
        try:
            sql = (
                f"ALTER AGENT {AGENT_FQN} "
                f"MODIFY LIVE VERSION SET SPECIFICATION = $${spec_yaml}$$"
            )
            cursor2.execute(sql)
            return f"✅ Agent {field_name} updated"
        except Exception as e:
            return f"❌ Agent update failed: {e}"
        finally:
            cursor2.close()
    except Exception as e:
        return f"❌ Agent update failed: {e}"
    finally:
        cursor.close()


# ---------------------------------------------------------------------------
# Fetch live state
# ---------------------------------------------------------------------------

def _row_get(row: dict, key: str) -> str:
    """Get a value from a DictCursor row, trying both cases."""
    return str(
        row.get(key, "")
        or row.get(key.upper(), "")
        or row.get(key.lower(), "")
        or ""
    )


def get_live_custom_instructions(conn, view_name: str) -> Dict[str, str]:
    """Return ``{question_categorization, sql_generation}`` from Snowflake.

    Reads from DESCRIBE SEMANTIC VIEW rows where
    ``object_kind='CUSTOM_INSTRUCTION'`` and ``property`` is one of
    ``AI_SQL_GENERATION`` or ``AI_QUESTION_CATEGORIZATION``.
    """
    import snowflake.connector

    fqn = f"{SCHEMA_FQN}.{view_name}"
    cursor = conn.cursor(snowflake.connector.DictCursor)
    result: Dict[str, str] = {"question_categorization": "", "sql_generation": ""}
    try:
        cursor.execute(f"DESCRIBE SEMANTIC VIEW {fqn}")
        rows = cursor.fetchall()
        for row in rows:
            ok = _row_get(row, "object_kind")
            prop = _row_get(row, "property")
            val = _row_get(row, "property_value")
            if ok == "CUSTOM_INSTRUCTION":
                if prop == "AI_SQL_GENERATION":
                    result["sql_generation"] = val
                elif prop == "AI_QUESTION_CATEGORIZATION":
                    result["question_categorization"] = val
    except Exception as e:
        return {"_error": str(e)}
    finally:
        cursor.close()
    return result


def get_live_agent_instructions(conn) -> Dict[str, str]:
    """Return agent instruction fields from Snowflake.

    Uses ``DESCRIBE AGENT`` (primary) or ``SHOW AGENTS`` (fallback).
    The DESCRIBE output contains an ``agent_spec`` column with the
    full specification as a JSON string.
    """
    import snowflake.connector

    cursor = conn.cursor(snowflake.connector.DictCursor)

    # Try DESCRIBE first — returns agent_spec as JSON
    try:
        cursor.execute(f"DESCRIBE AGENT {AGENT_FQN}")
        rows = cursor.fetchall()
        if rows:
            spec_raw = _row_get(rows[0], "agent_spec")
            profile_raw = _row_get(rows[0], "profile")
            try:
                spec = json.loads(spec_raw) if spec_raw else {}
            except (json.JSONDecodeError, TypeError):
                spec = {}
            instructions = spec.get("instructions", {})

            # Extract display_name from profile JSON
            display_name = ""
            try:
                profile = json.loads(profile_raw) if profile_raw else {}
                display_name = profile.get("display_name", "")
            except (json.JSONDecodeError, TypeError):
                pass

            return {
                "orchestration_instructions": str(
                    instructions.get("orchestration", "")
                ),
                "response_instructions": str(
                    instructions.get("response", "")
                ),
                "display_name": display_name,
                "description": _row_get(rows[0], "comment"),
            }
    except Exception:
        pass

    # Fallback: SHOW AGENTS
    try:
        cursor.execute(
            f"SHOW AGENTS LIKE 'INSULINTEL' IN SCHEMA {SCHEMA_FQN}"
        )
        rows = cursor.fetchall()
        if rows:
            row = rows[0]
            display_name = ""
            try:
                profile = json.loads(_row_get(row, "profile") or "{}")
                display_name = profile.get("display_name", "")
            except (json.JSONDecodeError, TypeError):
                pass
            return {
                "orchestration_instructions": "",
                "response_instructions": "",
                "display_name": display_name,
                "description": _row_get(row, "comment"),
            }
    except Exception as e:
        return {"_error": str(e)}
    finally:
        cursor.close()
    return {}


# ---------------------------------------------------------------------------
# Deploy All
# ---------------------------------------------------------------------------

def deploy_all_from_repo(
    conn,
) -> list[str]:
    """Deploy all semantic views + agent instructions from repo files.

    Assembles instructions from the instruction modules (via assembly.yaml),
    injects them into the semantic view YAMLs, and deploys everything.
    Returns a list of status messages.
    """
    results: list[str] = []

    # ── Semantic views ────────────────────────────────────────────────
    sv_instructions = assemble_semantic_view_instructions(REPO_ROOT)
    for view_name in SEMANTIC_VIEW_NAMES:
        ci = sv_instructions.get(view_name, {})
        result = deploy_semantic_view(conn, view_name, ci)
        results.append(result)

    # ── Agent instructions ────────────────────────────────────────────
    agent_instructions = assemble_agent_instructions(REPO_ROOT)
    agent = agent_instructions.get("INSULINTEL", {})
    for field_name in ("orchestration_instructions", "response_instructions"):
        text = agent.get(field_name, "")
        if text:
            result = deploy_agent_field(conn, field_name, text)
            results.append(result)
        else:
            results.append(f"⚠️ Agent {field_name}: no assembled content, skipped")

    return results


# ---------------------------------------------------------------------------
# Test via CORTEX.COMPLETE
# ---------------------------------------------------------------------------

def test_with_cortex(
    conn,
    system_prompt: str,
    user_message: str,
    model: str = "mistral-large2",
) -> str:
    """Call ``CORTEX.COMPLETE`` with assembled instructions as system prompt."""
    prompt_obj = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_message},
    ]
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT SNOWFLAKE.CORTEX.COMPLETE(%s, %s) AS response",
            (model, json.dumps(prompt_obj)),
        )
        row = cursor.fetchone()
        if not row:
            return "No response from Snowflake."
        raw = row[0]
        try:
            parsed = json.loads(raw)
            choices = parsed.get("choices", [])
            if choices:
                return choices[0].get("messages", choices[0].get("message", raw))
            return parsed.get("message", str(raw))
        except (json.JSONDecodeError, IndexError, KeyError):
            return str(raw)
    except Exception as e:
        return f"Error: {e}"
    finally:
        cursor.close()
