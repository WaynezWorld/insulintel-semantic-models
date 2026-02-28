"""
Shared constants for Snowflake object references.

Single source of truth — all Python code imports from here.
SQL files (deploy.sql, fn_insight_of_the_day.sql) necessarily use
literal values and must be updated manually if these change.
"""

SCHEMA_FQN = "DB_INSULINTEL.SCH_SEMANTIC"
AGENT_FQN = f"{SCHEMA_FQN}.INSULINTEL"

SEMANTIC_VIEW_NAMES = ["SEM_INSULINTEL", "SEM_ACTIVITY", "SEM_NHANES"]

SEMANTIC_VIEW_FQNS = [f"{SCHEMA_FQN}.{name}" for name in SEMANTIC_VIEW_NAMES]
