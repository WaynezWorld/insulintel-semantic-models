"""Quick script to verify custom instructions were deployed."""
import sys
import tomllib

sys.path.insert(0, "scripts")
sys.path.insert(0, "app")
from semantic_diff.constants import SCHEMA_FQN
from deployer import get_live_custom_instructions, get_live_agent_instructions
import snowflake.connector

with open(".streamlit/secrets.toml", "rb") as f:
    cfg = tomllib.load(f)
sf = cfg["snowflake"]
params = {
    k: str(sf[k])
    for k in ("account", "user", "password", "role", "warehouse", "database", "schema", "authenticator", "token")
    if k in sf and sf[k]
}
conn = snowflake.connector.connect(**params)

for vn in ("SEM_INSULINTEL", "SEM_ACTIVITY", "SEM_NHANES"):
    ci = get_live_custom_instructions(conn, vn)
    sg_len = len(ci.get("sql_generation", ""))
    qc_len = len(ci.get("question_categorization", ""))
    print(f"{vn:20s}  sg={sg_len:,} chars  qc={qc_len:,} chars")

agent = get_live_agent_instructions(conn)
for fld in ("orchestration_instructions", "response_instructions"):
    print(f"Agent:{fld:30s}  {len(agent.get(fld, '')):,} chars")

conn.close()
