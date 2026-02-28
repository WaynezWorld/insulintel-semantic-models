---
name: continueAuditWork
description: Continue work on the insulintel-semantic-models repo — all audit PRs merged, ready for next phase
argument-hint: Optional focus (e.g., "Streamlit app testing", "Snowflake live validation", "normalize_sf tests", "new feature")
---

## Context — What Has Been Done

Two rounds of repo audit have been completed and **merged to `main`**.

### PR #2 (MERGED) — Initial Audit

| # | Fix | Key Files |
|---|-----|-----------|
| 1 | Centralized constants (`SCHEMA_FQN`, `AGENT_FQN`, view lists) | `scripts/semantic_diff/constants.py` |
| 2 | CI workflow — path triggers, `pip install -e .` | `.github/workflows/ci.yml` |
| 3 | Deleted redundant `requirements.txt` | (deleted) |
| 4 | Removed hardcoded DB defaults from Streamlit | `app/streamlit_app.py` |
| 5 | Fixed git staging (stages `semantic_views/` too) | `app/streamlit_app.py` |
| 6 | Added `app/__init__.py` | `app/__init__.py` |
| 7 | 21 unit tests for `assemble.py` | `tests/test_assemble.py` |
| 8 | Fixed Streamlit secrets resolution | `app/.streamlit/` (deleted) |

### PR #3 (MERGED) — SQL Syntax Fix + Tests + Docs

| # | Fix | Key Files |
|---|-----|-----------|
| 1 | **Snowflake Agent SQL syntax** — `SHOW/DESCRIBE/ALTER CORTEX AGENT` → `SHOW/DESCRIBE/ALTER AGENT` | `app/deployer.py`, `scripts/build_deploy.py`, `deploy/deploy_agent.sql` |
| 2 | **`deploy_agent_field()` rewrite** — fetch spec via DESCRIBE, patch field, write back full YAML via `ALTER AGENT ... MODIFY LIVE VERSION SET SPECIFICATION` | `app/deployer.py` |
| 3 | **`get_live_agent_instructions()` rewrite** — parses `agent_spec` JSON column from DESCRIBE AGENT, extracts `instructions.orchestration` / `instructions.response`, `profile` for display_name | `app/deployer.py` |
| 4 | **96 new tests** (117 total across 5 files) | `tests/test_deployer.py`, `tests/test_snapshot_manager.py`, `tests/test_diff_engine.py`, `tests/test_normalize_yaml.py` |
| 5 | **README expanded** — instruction pipeline, Streamlit admin panel docs, test coverage table | `README.md` |

### Validation (all passing on `main`)
- `python scripts/validate_repo.py` ✅
- `python scripts/build_deploy.py` ✅
- `pytest tests/ -q` → **117 passed** ✅

## Key Architecture Notes

- **Snowflake Agent SQL (2026)**: Commands are `CREATE AGENT`, `ALTER AGENT`, `DESCRIBE AGENT`, `SHOW AGENTS`, `DROP AGENT` — NO "CORTEX" keyword. `ALTER AGENT` uses `MODIFY LIVE VERSION SET SPECIFICATION = $$yaml$$`. `DESCRIBE AGENT` returns `agent_spec` JSON column.
- **Instruction pipeline**: `instructions/` → `assembly.yaml` manifest → `build_deploy.py` → `deploy/` artefacts
- **Constants**: `scripts/semantic_diff/constants.py` — `SCHEMA_FQN`, `AGENT_FQN`, `SEMANTIC_VIEW_NAMES`
- **Snowflake auth**: PROGRAMMATIC_ACCESS_TOKEN (PAT), account `LIYWRBM-JZC37138`
- **Streamlit secrets**: project-level `.streamlit/secrets.toml` (NOT `app/.streamlit/`)
- **Block YAML dumper**: `app/deployer.py` — `_BlockDumper` forces `|` style for multiline strings

## Next Phase — Improvements (not bugs)

Everything works. These are prioritized future improvements:

### High Priority
1. **Live Snowflake validation** — Run `SHOW AGENTS`, `DESCRIBE AGENT`, and `ALTER AGENT` against the real account (`LIYWRBM-JZC37138`) to confirm end-to-end correctness
2. **Streamlit app smoke test** — `streamlit run app/streamlit_app.py` — verify it starts cleanly and each tab renders

### Medium Priority
3. **`normalize_sf.py` tests** — normalises Snowflake `DESCRIBE SEMANTIC VIEW` output; currently untested
4. **`validate_repo.py` tests** — unit tests for the repo validation script
5. **`build_deploy.py` tests** — unit tests for the build/deploy pipeline script
6. **Integration test harness** — `pytest` fixtures with a `--live` flag for tests that need a Snowflake connection

### Lower Priority
7. **CI enhancements** — test coverage reporting, badge in README
8. **Pre-commit hooks** — `ruff` linting, YAML validation
9. **Semantic view diffing improvements** — enhanced diff display in Streamlit

## Instructions

1. Read this context to understand current state
2. Run `git checkout main && git pull` to ensure you're on latest
3. Run `git log --oneline -5` to verify both PR merge commits are present
4. Address the user's request, or propose improvements from the list above
5. Always validate: `validate_repo.py`, `build_deploy.py`, `pytest tests/ -q`
6. Create a feature branch for any changes, push, and create a PR
7. **Always update this prompt file** before ending a session so the next chat has full context
