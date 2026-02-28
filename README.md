# insulintel-semantic-models

Semantic model definitions (YAML) for Insulintel / wellness analytics, designed to be deployed as **Snowflake Semantic Views** from a Git-synced repository.

This repo is primarily configuration (not an application): it stores semantic-view YAML files and a simple deployment script.

> **Disclaimer**
> These models support wellness/education analytics only. They are **not** intended for diagnosis or treatment decisions.

## Repository layout

- `semantic_views/` — Snowflake Semantic View definitions (source of truth)
  - `sem_insulintel.yaml` — **SEM_INSULINTEL** (CGM-focused analytics)
  - `sem_nhanes.yaml` — **SEM_NHANES** (NHANES 2021–2023 population metabolic analytics)
  - `sem_activity.yaml` — **SEM_ACTIVITY** (activity/lifestyle + glucose-context analytics)
- `instructions/` — modular instruction prompts assembled into semantic views + agent
  - `assembly.yaml` — manifest mapping modules → deployment targets
  - `_global/` — shared modules (medical disclaimer, safety, time defaults, response format)
  - `sem_*/` — per-view modules (identity, scope rules, routing keywords)
  - `agent_insulintel/` — agent orchestration and response modules
- `deploy/` — **auto-generated** deployment artefacts (do not edit manually)
  - `sem_*.yaml` — semantic view YAMLs with `custom_instructions` baked in
  - `deploy_agent.sql` — agent SQL with assembled instructions
- `app/` — Streamlit admin panel for editing, previewing, diffing, and deploying
  - `streamlit_app.py` — 5-tab UI (Editor, Preview, Diff, Live, Test)
  - `deployer.py` — Snowflake deployment operations
- `scripts/`
  - `deploy.sql` — Snowflake script to fetch and deploy from `deploy/`
  - `build_deploy.py` — generates `deploy/` artefacts from source
  - `fn_insight_of_the_day.sql` — lifestyle→glucose correlation UDFs
  - `validate_repo.py` — CI repository validator
  - `semantic_diff/` — CLI diff engine for comparing repo vs Snowflake

## Semantic views included

### SEM_INSULINTEL (CGM / glucose analytics)
Defined in: `semantic_views/sem_insulintel.yaml`

Covers:
- Unified CGM readings (dimensions such as dataset source, participant, device, timestamps)
- Daily glucose summaries (mean, variability, time-in-range and related metrics)
- Detected glucose episodes (hypo/hyper episodes with severity and duration)
- Time-in-range rollups (7/14/30 day windows)
- Post-meal glucose response analytics
- Workout sessions with glucose context (pre/post glucose windows, glucose change)

### SEM_ACTIVITY (activity + lifestyle analytics)
Defined in: `semantic_views/sem_activity.yaml`

Covers:
- Exercise sessions, meals, sleep, and blood pressure
- CGM participant summaries
- Statistical associations between candidate factors and outcomes

### SEM_NHANES (population metabolic analytics)
Defined in: `semantic_views/sem_nhanes.yaml`

Covers:
- NHANES 2021–2023 raw metabolic dataset
- Derived “gold” summary analytics (risk categories, HOMA-IR, metabolic syndrome, etc.)
- A declared relationship between summary and raw tables via `PARTICIPANT_ID`

## Deploying to Snowflake (example)

See: `scripts/deploy.sql`

At a high level the script:
1. Fetches the latest repo contents via a Snowflake `GIT REPOSITORY` object
2. Calls `SYSTEM$CREATE_SEMANTIC_VIEW_FROM_YAML` for each model YAML
3. Verifies deployment with `SHOW SEMANTIC VIEWS ...`

You’ll need to adjust database/schema/repo object names to match your Snowflake environment.

## Contributing / updating models

1. Edit or add files under `semantic_views/` and/or `instructions/`
2. Commit and push to `main`
3. CI runs `validate_repo.py` + `build_deploy.py` and commits `deploy/` artefacts
4. In Snowflake: run `scripts/deploy.sql` (or use the Streamlit admin panel)

## Local setup

```bash
# Install editable package (enables `semantic-diff` CLI + clean imports)
pip install -e .

# Copy secrets template and fill in credentials
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
# Edit .streamlit/secrets.toml with your Snowflake account details

# Run the admin panel
streamlit run app/streamlit_app.py

# CLI: build deploy artefacts locally
python scripts/build_deploy.py

# CLI: assemble and view instructions
semantic-diff assemble --target all
```

## CI and branch protection

This repository runs a GitHub Actions workflow at `.github/workflows/ci.yml` that executes:

- `python scripts/validate_repo.py`

The check name shown in GitHub is:

- `CI / validate-repo`

To require this before merge:

1. Open **Settings → Branches** in GitHub
2. Edit the branch protection rule for `main` (or create one)
3. Enable **Require status checks to pass before merging**
4. Select `CI / validate-repo`
5. Save changes

## License

No license file is currently included in this repository. If you intend this repo to be reused externally, consider adding a LICENSE.

## Test Backlog

The following test suites are planned (priority order):

1. **`semantic_diff.assemble`** — assembly logic, orphan/missing detection, module concatenation
2. **`semantic_diff.diff_engine`** — diff classification (BREAKING vs METADATA), edge cases
3. **`semantic_diff.normalize_yaml` / `normalize_sf`** — normalisation correctness, camelCase→snake_case
4. **`app.deployer`** — mock Snowflake connection, verify SQL generation, YAML injection
5. **`scripts.validate_repo`** — repo validation rules, missing file detection
6. **Integration** — end-to-end assemble → build_deploy → deploy round-trip
7. **`scripts.build_deploy`** — verify generated artefacts contain custom_instructions