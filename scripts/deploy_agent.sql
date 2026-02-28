-- =============================================================================
-- DEPLOY CORTEX AGENT FROM REPO INSTRUCTION FILES
-- =============================================================================
-- Usage: Run after pushing instruction changes to GitHub.
-- The orchestration and response instruction text below is assembled
-- from modular YAML files under instructions/agent_insulintel/.
--
-- To generate fresh text, run:
--   python scripts/semantic_diff/cli.py assemble --target agent
-- Then paste the output into the $$ blocks below.
-- =============================================================================

-- Step 1: Fetch latest repo contents
ALTER GIT REPOSITORY DB_INSULINTEL.SCH_SEMANTIC.REPO_SEMANTIC_MODELS FETCH;

-- Step 2: Update orchestration instructions
ALTER CORTEX AGENT DB_INSULINTEL.SCH_SEMANTIC.INSULINTEL
SET ORCHESTRATION_INSTRUCTIONS = $$
-- PASTE ASSEMBLED ORCHESTRATION INSTRUCTIONS HERE
-- Run: python scripts/semantic_diff/cli.py assemble --target agent
$$;

-- Step 3: Update response instructions
ALTER CORTEX AGENT DB_INSULINTEL.SCH_SEMANTIC.INSULINTEL
SET RESPONSE_INSTRUCTIONS = $$
-- PASTE ASSEMBLED RESPONSE INSTRUCTIONS HERE
-- Run: python scripts/semantic_diff/cli.py assemble --target agent
$$;

-- Step 4: Verify
DESCRIBE CORTEX AGENT DB_INSULINTEL.SCH_SEMANTIC.INSULINTEL;
