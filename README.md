# insulintel-semantic-models

Semantic model definitions (YAML) for Insulintel / wellness analytics, designed to be deployed as **Snowflake Semantic Views** from a Git-synced repository.

This repo is primarily configuration (not an application): it stores semantic-view YAML files and a simple deployment script.

> **Disclaimer**
> These models support wellness/education analytics only. They are **not** intended for diagnosis or treatment decisions.

## Repository layout

- `semantic_views/` — Snowflake Semantic View definitions
  - `sem_insulintel.yaml` — **SEM_INSULINTEL** (CGM-focused analytics)
  - `sem_nhanes.yaml` — **SEM_NHANES** (NHANES 2021–2023 population metabolic analytics)
  - `sem_activity.yaml` — **SEM_ACTIVITY** (activity/lifestyle + glucose-context analytics)
- `scripts/`
  - `deploy.sql` — example Snowflake script to fetch this Git repo and deploy semantic views
- `instructions/` — supplemental guidance / prompts per semantic model (folder structure present)

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

1. Edit or add files under `semantic_views/`
2. Commit and push to `main`
3. Re-run the Snowflake deploy script (or your CI/CD equivalent)

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