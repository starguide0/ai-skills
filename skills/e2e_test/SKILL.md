---
name: e2e_test
description: Enterprise test orchestration skill suite for planning, data prep, scheduling, execution, and reporting. (Platform-Agnostic)
allowed-tools:
  - run_command, Bash, Bash(git:*)
  - list_dir, Glob
  - view_file, Read
  - write_to_file, Write
  - multi_replace_file_content, replace_file_content, Edit
  - grep_search, Grep
  - search_web, WebSearch
---

# Test Skill

Use this skill when the user asks to create test plans, prepare test data, execute tests, or build final test reports.

## Project-Relative Runtime Rule (Required)

- Read and follow `test-workspace-conventions.md` first.
- Use project root relative paths only.
- Resolve `ctx.service_metadata` first. The skill may consume file, CLI, RAG, or MCP-based service metadata providers, but must not depend on a specific implementation skill.
- Load rules from `$CLAUDE_PLUGIN_ROOT/skills/e2e_test/rules/`.
- Write outputs under `./test/<feature-or-ticket>/`.
- Do not write final outputs into `./test/_*`.

## Workflow (Single Pipeline)

All test requests are handled by `test-run` as the single orchestrator:

1. **Step 0: Init** — Validate workspace (`test-init.md`) + load shared resources (`test-workspace-conventions.md`)
2. **Step 1: Verify** — 이슈(IMS) vs 구현 비교 + 사용자 의사결정 + 서비스 탐색 (Remote Reconnaissance) + 범위 판단 + 서버 접속 확인 (Skip/Abort Routine) (`test-gate.md`)
   - Features: Platform-Agnostic IMS/Report, Remote Reconnaissance, Analysis mode selection
3. **Step 2: Sheet Check** — Compare baseline with existing sheet → REUSE / REPLAN / NEW
4. **Step 3: Plan** — Generate test sheet with issue_digest + code_digest (`test-plan.md`)
5. **Step 4: Data** — Map test data per TC, cross-workplace discovery with Phase-based query execution (`test-data.md`)
   - Features: Structural Signature Mapping, Smart Recycling, Platform-Agnostic constraints
6. **Step 5: Execute** — Run TC stimuli, collect partial results, verify evidence (`test-run.md` Step 5)
7. **Step 6: Report** — Merge partial results into final Test Report (`test-reporter.md`)
8. **Step 7: Post** — Execute post-test actions like report publishing or issue commenting (`test-post.md`)

Steps 3-4 auto-skip when conditions are met (baseline unchanged, data mapping exists).

## References

- `README.md` — Architecture overview and full flow documentation
- `test-workspace-conventions.md` — Project structure and naming conventions
- `test-init.md` — Workspace initialization (folder/file validation, boilerplate/scaffold)
- `test-run.md` — Single orchestrator (Step 0~6)
- `test-gate.md` — Reference data confirmation + 이슈(IMS) vs implementation comparison, baseline decision
- `test-plan.md` — Impact analysis, test sheet generation (with baseline storage)
- `test-data.md` — TC data mapping and discovery
- `test-provisioning.md` — API-based data creation (Worker)
- `test-scheduler.md` — DAG-based execution planning
- `test-reporter.md` — Result aggregation and Test Report 문항 생성
- `test-evidence.md` — Pass/Fail evidence writing guide
