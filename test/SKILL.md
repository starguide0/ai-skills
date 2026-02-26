---
name: test
description: Enterprise test orchestration skill suite for planning, data prep, scheduling, execution, and reporting.
---

# Test Skill

Use this skill when the user asks to create test plans, prepare test data, execute tests, or build final test reports.

## Project-Relative Runtime Rule (Required)

- Read and follow `test-workspace-conventions.md` first.
- Use project root relative paths only.
- Load rules from `.claude/skills/test/rules/`.
- Write outputs under `./test/<feature-or-ticket>/`.
- Do not write final outputs into `./test/_*`.

## Workflow (Single Pipeline)

All test requests are handled by `test-run` as the single orchestrator:

1. **Step 0: Init** — Validate workspace (`test-init.md` v1.2.1) + load shared resources (`test-workspace-conventions.md`)
2. **Step 1: Verify** — Jira vs 구현 비교 + 사용자 의사결정 + 서비스 탐색 + 범위 판단 + 서버 접속 확인 (`test-gate.md` v4.1)
   - v4.1 features: Server connectivity check, Analysis mode selection (METADATA/HYBRID/SOURCE_DIRECT)
3. **Step 2: Sheet Check** — Compare baseline with existing sheet → REUSE / REPLAN / NEW
4. **Step 3: Plan** — Generate test sheet with jira_digest + code_digest (`test-plan.md` v2.3)
5. **Step 4: Data** — Map test data per TC, cross-workplace discovery with Phase-based query execution (`test-data.md` v2.2)
   - v2.2 features: Phase-based query dependency analysis, STATIC/DERIVED groups, cross-DB query coordination
6. **Step 5: Execute** — DAG scheduling + tiered parallel execution incl. mobile API simulation (`test-scheduler.md` v1.1, `test-provisioning.md` v1.0)
7. **Step 6: Report** — Merge partial results into final Confluence report (`test-reporter.md` v4.1)

Steps 3-4 auto-skip when conditions are met (baseline unchanged, data mapping exists).

## References

- `README.md` — Architecture overview and full flow documentation
- `test-workspace-conventions.md` — Project structure and naming conventions
- `test-init.md` — Workspace initialization (folder/file validation, boilerplate/scaffold)
- `test-run.md` — Single orchestrator (Step 0~6)
- `test-gate.md` — Reference data confirmation + Jira vs implementation comparison, baseline decision
- `test-plan.md` — Impact analysis, test sheet generation (with baseline storage)
- `test-data.md` — TC data mapping and discovery
- `test-provisioning.md` — API-based data creation (Worker)
- `test-scheduler.md` — DAG-based execution planning
- `test-reporter.md` — Result aggregation and Confluence report
- `test-evidence.md` — Pass/Fail evidence writing guide
