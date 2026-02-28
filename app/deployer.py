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

from semantic_diff.constants import SCHEMA_FQN, AGENT_FQN

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
    custom_instructions: Dict[str, str],
) -> str:
    """Read a semantic-view YAML from repo and inject ``custom_instructions``.

    Returns the full YAML text ready for
    ``SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML``.
    """
    yaml_path = YAML_MAP[view_name]
    with open(yaml_path, encoding="utf-8") as f:
        data = yaml.safe_load(f)

    ci: dict = {}
    if custom_instructions.get("question_categorization"):
        ci["question_categorization"] = custom_instructions["question_categorization"]
    if custom_instructions.get("sql_generation"):
        ci["sql_generation"] = custom_instructions["sql_generation"]
    if ci:
        data["custom_instructions"] = ci

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
    """Deploy a semantic view with the provided ``custom_instructions``."""
    yaml_text = build_deployable_yaml(view_name, custom_instructions)
    cursor = conn.cursor()
    try:
        cursor.execute(
            "CALL SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML(%s, %s)",
            (SCHEMA_FQN, yaml_text),
        )
        result = cursor.fetchone()
        return f"✅ {view_name} deployed ({result[0] if result else 'OK'})"
    except Exception as e:
        return f"❌ Deploy failed: {e}"
    finally:
        cursor.close()


def deploy_agent_field(conn, field_name: str, instruction_text: str) -> str:
    """Update a single agent instruction field via ``ALTER CORTEX AGENT``."""
    field_upper = field_name.upper()
    cursor = conn.cursor()
    try:
        # $$ delimiters avoid quoting issues in instruction text
        sql = (
            f"ALTER CORTEX AGENT {AGENT_FQN} "
            f"SET {field_upper} = $${instruction_text}$$"
        )
        cursor.execute(sql)
        return f"✅ Agent {field_name} updated"
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
    """Return ``{question_categorization, sql_generation}`` from Snowflake."""
    import snowflake.connector

    fqn = f"{SCHEMA_FQN}.{view_name}"
    cursor = conn.cursor(snowflake.connector.DictCursor)
    try:
        cursor.execute(f"DESCRIBE SEMANTIC VIEW {fqn}")
        rows = cursor.fetchall()
        for row in rows:
            ok = _row_get(row, "object_kind")
            on = _row_get(row, "object_name")
            prop = _row_get(row, "property")
            val = _row_get(row, "property_value")
            if ok == "EXTENSION" and on == "CA" and prop == "VALUE":
                data = json.loads(val)
                ci = data.get("custom_instructions") or {}
                return {
                    "question_categorization": str(
                        ci.get("question_categorization", "")
                    ),
                    "sql_generation": str(ci.get("sql_generation", "")),
                }
    except Exception as e:
        return {"_error": str(e)}
    finally:
        cursor.close()
    return {"question_categorization": "", "sql_generation": ""}


def get_live_agent_instructions(conn) -> Dict[str, str]:
    """Return agent instruction fields from Snowflake."""
    import snowflake.connector

    cursor = conn.cursor(snowflake.connector.DictCursor)

    # Try DESCRIBE first
    try:
        cursor.execute(f"DESCRIBE CORTEX AGENT {AGENT_FQN}")
        rows = cursor.fetchall()
        result: Dict[str, str] = {}
        for row in rows:
            prop = _row_get(row, "property").lower()
            val = _row_get(row, "property_value")
            if "orchestration" in prop:
                result["orchestration_instructions"] = val
            elif "response" in prop:
                result["response_instructions"] = val
            elif "display" in prop and "name" in prop:
                result["display_name"] = val
            elif prop == "description":
                result["description"] = val
        if result:
            return result
    except Exception:
        pass

    # Fallback: SHOW
    try:
        cursor.execute(
            f"SHOW CORTEX AGENTS LIKE 'INSULINTEL' IN SCHEMA {SCHEMA_FQN}"
        )
        rows = cursor.fetchall()
        if rows:
            row = rows[0]
            return {
                "orchestration_instructions": _row_get(
                    row, "orchestration_instructions"
                ),
                "response_instructions": _row_get(row, "response_instructions"),
                "display_name": _row_get(row, "display_name"),
                "description": _row_get(row, "description"),
            }
    except Exception as e:
        return {"_error": str(e)}
    finally:
        cursor.close()
    return {}


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
    messages = json.dumps(
        [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
    )
    cursor = conn.cursor()
    try:
        cursor.execute(
            "SELECT SNOWFLAKE.CORTEX.COMPLETE(%s, PARSE_JSON(%s)) AS response",
            (model, messages),
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
