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

### PR #6 (MERGED) — `normalize_sf.py` Tests

| # | Fix | Key Files |
|---|-----|-----------|
| 1 | **52 unit tests for `normalize_sf.py`** — CSV reading (UTF-8/UTF-16/CP1252), JSON extraction, all individual parsers (base_table, dimension, fact, metric, key, relationship, table, custom_instructions), `load_snowflake_json`, `load_snowflake_describe`, JSON/CSV parity | `tests/test_normalize_sf.py` |

### PR #7 (MERGED) — `validate_repo.py` Tests

| # | Fix | Key Files |
|---|-----|-----------|
| 1 | **58 unit tests for `validate_repo.py`** — Finding dataclass, SQL comment stripping, CTE collection, FQDN validation (13 cases incl. CTEs, stages, TABLE(), LATERAL, subqueries), expected model checks, deploy wiring, SQL file scanning, instruction assembly (missing/orphan/null handling), print_findings output, real-repo smoke test | `tests/test_validate_repo.py` |

### PR #8 (IN PROGRESS) — `build_deploy.py` Tests

| # | Fix | Key Files |
|---|-----|-----------|
| 1 | **28 unit tests for `build_deploy.py`** — `_indent` helper, `build_semantic_view_yamls` (file generation, YAML validity, custom_instructions injection, idempotency), `build_agent_sql` (SQL content, no CORTEX in commands, FQN refs, MODIFY LIVE VERSION, dollar quoting, idempotency), `main()` (default/custom/new out-dir), real-repo smoke + deploy/ parity check | `tests/test_build_deploy.py` |

### Validation (all passing)
- `python scripts/validate_repo.py` ✅
- `python scripts/build_deploy.py` ✅
- `pytest tests/ -q` → **255 passed** ✅ (227 prior + 28 new build_deploy)

## Key Architecture Notes

- **Snowflake Agent SQL (2026)**: Commands are `CREATE AGENT`, `ALTER AGENT`, `DESCRIBE AGENT`, `SHOW AGENTS`, `DROP AGENT` — NO "CORTEX" keyword. `ALTER AGENT` uses `MODIFY LIVE VERSION SET SPECIFICATION = $$yaml$$`. `DESCRIBE AGENT` returns `agent_spec` JSON column.
- **Instruction pipeline**: `instructions/` → `assembly.yaml` manifest → `build_deploy.py` → `deploy/` artefacts
- **Constants**: `scripts/semantic_diff/constants.py` — `SCHEMA_FQN`, `AGENT_FQN`, `SEMANTIC_VIEW_NAMES`
- **Snowflake auth**: PROGRAMMATIC_ACCESS_TOKEN (PAT), account `LIYWRBM-JZC37138`
- **Streamlit secrets**: project-level `.streamlit/secrets.toml` (NOT `app/.streamlit/`)
- **Block YAML dumper**: `app/deployer.py` — `_BlockDumper` forces `|` style for multiline strings

## Next Phase — Improvements (not bugs)

Everything works. These are prioritized future improvements:

### High Priority (both done)
1. ~~**Live Snowflake validation**~~ ✅ DONE — `ALTER AGENT ... MODIFY LIVE VERSION SET SPECIFICATION` confirmed working against `LIYWRBM-JZC37138`. Deploy + revert cycle tested via Streamlit admin panel. Persona change ("Rudy") visible in Snowflake console.
2. ~~**Streamlit app smoke test**~~ ✅ DONE — app starts cleanly on port 8501, health endpoint OK, all 5 tabs functional (Editor, Preview, Diff, Live, Test). Full edit → save → preview → deploy → revert cycle tested.

### Medium Priority
3. ~~**`normalize_sf.py` tests**~~ ✅ DONE — 52 tests covering CSV encoding fallback, JSON extraction, all parsers, public API (`load_snowflake_describe`, `load_snowflake_json`), and JSON/CSV parity. Branch: `test/normalize-sf-tests`.
4. ~~**`validate_repo.py` tests**~~ ✅ DONE — 58 tests covering Finding, utilities (comment stripping, CTE collection, token cleaning), SQL FQDN validation, model checks, deploy wiring, instruction assembly, print_findings, real-repo smoke test. Branch: `test/validate-repo-tests`.
5. ~~**`build_deploy.py` tests**~~ ✅ DONE — 28 tests covering `_indent`, view YAML generation, agent SQL generation, `main()` CLI, real-repo smoke + deploy/ parity. Branch: `test/build-deploy-tests`.
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
