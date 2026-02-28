---
name: deepRepoAuditAndFix
description: Perform a comprehensive repository audit, identify issues, and implement approved fixes.
argument-hint: Optional focus areas (e.g., "security", "duplication", "CI/CD", "workflow gaps")
---
Perform a comprehensive audit and remediation of the current repository:

## Phase 1 — Deep Analysis
1. Map the full repository structure: directories, files, and their relationships
2. Read and understand every configuration file, script, and source module
3. Identify the architecture pattern, tech stack, and deployment model
4. Document all component dependencies and data flow

## Phase 2 — Issue Identification
For each issue found, report:
- **What**: Clear description of the problem
- **Why**: Impact on correctness, maintainability, or reliability
- **Options**: Proposed fix(es) with trade-offs
- **Priority**: Critical / Important / Nice-to-have

Categories to check:
- Code duplication or inconsistency
- Naming convention violations (casing, style)
- Hardcoded values that should be configurable
- Missing or incomplete deployment scripts
- Missing packaging metadata (pyproject.toml, setup.cfg, etc.)
- Orphaned or redundant files
- Schema/model parity gaps
- Missing tests or CI coverage
- Documentation gaps
- Workflow gaps (edit/test/revert cycles, staging vs production)

## Phase 3 — Implementation Plan
After presenting findings, wait for user confirmation on each issue before proceeding. Then:
1. Number each approved fix as a step
2. Execute steps sequentially, validating after each
3. Run any available validators or build scripts to confirm correctness
4. Track progress explicitly — report what's done and what remains

## Phase 4 — Validation & Cleanup
- Run all linters, validators, and build scripts
- Verify generated artefacts are correct
- Remove any redundant files identified during the audit
- Update documentation (README, comments) to reflect changes
- Provide a final summary of all changes with file-level detail
