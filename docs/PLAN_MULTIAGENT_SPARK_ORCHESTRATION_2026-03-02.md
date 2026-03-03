# Action Plan: Spark Test Agent + Main Codex Orchestrator

## Objective
Implement and validate a workflow where:
1. A fast `gpt-5.3-codex-spark` agent runs testing/triage tasks.
2. A main `gpt-5.3-codex` agent consumes that output and performs final implementation decisions.

## Success Criteria
- Test agent runs autonomously and returns structured results.
- Main agent uses those results to apply/fix code with fewer full-model turns.
- Measurable reduction in weekly quota consumption for day-to-day coding.
- No regression in final code quality (tests pass, review quality maintained).

## Session 1 (Setup)
1. Enable multi-agent in Codex config.
2. Define at least two agents:
   - `test_runner` -> `gpt-5.3-codex-spark`, low/medium effort, read-only or restricted write scope.
   - `main_orchestrator` -> `gpt-5.3-codex`, medium/high effort, full implementation role.
3. Add clear developer instructions for each role:
   - Test runner: only collect evidence and propose fix hints.
   - Orchestrator: final decisions, edits, and validation.
4. Create command aliases/scripts for repeatable execution.

## Session 2 (Validation)
Run controlled experiments on 3 task types:
1. Small bugfix (1-2 files).
2. Medium refactor (5-10 files).
3. Test failure triage task.

For each task, compare:
1. Baseline flow (single main model only).
2. Multi-agent flow (Spark test runner + main orchestrator).

Track:
- Total turns
- Wall-clock time
- Approx token/usage impact from `/status`
- First-pass pass rate on tests
- Rework count after first solution

## Session 3 (Implementation Hardening)
1. Standardize output contract from Spark in JSON-like format:
   - `failing_tests`
   - `suspect_files`
   - `root_cause_hypothesis`
   - `proposed_patch_outline`
2. Enforce that main agent validates each claim before applying changes.
3. Add guardrails:
   - Max files Spark can touch (or read-only mode).
   - Timebox Spark passes.
   - Automatic fallback to main-only if Spark confidence is low.

## Session 4 (Production Routine)
1. Define default routing policy:
   - Spark-first for triage, grep-like exploration, and quick diagnostics.
   - Main-first for architecture changes and irreversible edits.
2. Add a lightweight runbook in `docs/`:
   - When to use each model.
   - How to recover from low-quality Spark outputs.
   - How to monitor limits (`/status`) and switch strategy.

## Proposed File Deliverables
- `docs/agents/TEST_RUNNER_SPEC.md`
- `docs/agents/MAIN_ORCHESTRATOR_SPEC.md`
- `scripts/run_multiagent_triage.ps1`
- `scripts/run_main_orchestrator.ps1`
- `docs/MULTIAGENT_RUNBOOK.md`

## Risks and Mitigations
1. Risk: Spark output quality varies.
   - Mitigation: strict schema + mandatory verification by main agent.
2. Risk: Too much orchestration overhead.
   - Mitigation: only invoke Spark for eligible task classes.
3. Risk: Hidden quota burn from retries.
   - Mitigation: per-task max attempts and clear stop conditions.

## Immediate Next Commands (Next Session)
1. Confirm current model limits:
```powershell
/status
```
2. Create/update Codex config for multi-agent roles.
3. Run first A/B task and log metrics in:
`docs/metrics/multiagent_ab_YYYY-MM-DD.md`

## Exit Checklist
- [ ] Multi-agent config active
- [ ] Spark test agent returning structured outputs
- [ ] Main orchestrator consuming outputs correctly
- [ ] A/B metrics captured for at least 3 tasks
- [ ] Go/no-go decision documented

