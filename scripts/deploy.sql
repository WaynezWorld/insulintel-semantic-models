-- =============================================================================
-- DEPLOY SEMANTIC VIEWS FROM GIT REPOSITORY
-- =============================================================================
-- Usage: Run after pushing changes to GitHub
-- Repository: https://github.com/WaynezWorld/insulintel-semantic-models
-- =============================================================================

-- Step 1: Fetch latest changes from GitHub
ALTER GIT REPOSITORY DB_INSULINTEL.SCH_SEMANTIC.REPO_SEMANTIC_MODELS FETCH;

-- Step 2: List files to verify sync
LIST @DB_INSULINTEL.SCH_SEMANTIC.REPO_SEMANTIC_MODELS/branches/main/;

-- Step 3: Deploy SEM_NHANES
SELECT 'Deploying SEM_NHANES...' AS status;
CALL SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML(
  'DB_INSULINTEL.SCH_SEMANTIC',
  (SELECT $1 FROM @DB_INSULINTEL.SCH_SEMANTIC.REPO_SEMANTIC_MODELS/branches/main/semantic_views/sem_nhanes.yaml (FILE_FORMAT => 'DB_INSULINTEL.SCH_SEMANTIC.FF_YAML'))
);

-- Step 4: Deploy SEM_INSULINTEL
SELECT 'Deploying SEM_INSULINTEL...' AS status;
CALL SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML(
  'DB_INSULINTEL.SCH_SEMANTIC',
  (SELECT $1 FROM @DB_INSULINTEL.SCH_SEMANTIC.REPO_SEMANTIC_MODELS/branches/main/semantic_views/sem_insulintel.yaml (FILE_FORMAT => 'DB_INSULINTEL.SCH_SEMANTIC.FF_YAML'))
);

-- Step 5: Verification
SELECT 'Deployment complete. Verifying...' AS status;
SHOW SEMANTIC VIEWS IN SCHEMA DB_INSULINTEL.SCH_SEMANTIC;
