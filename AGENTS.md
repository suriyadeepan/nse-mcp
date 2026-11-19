- Workflow: Inspect existing plan/TODO and Git state → Plan → Implement → Validate. Identify gaps, dependencies and risks. Get approval for scope changes. Minimize unrelated changes, refactoring and dependencies.

- Architecture: Before coding, verify runtime, CPU, native dependencies and deployment compatibility. Record VERIFIED / ASSUMED / UNKNOWN with evidence in the plan. Identify automated compatibility checks.

- Branch/docs: One feature branch at a time. Maintain all four documents in `docs/`:
  - `docs/00x-<feature>-plan.md` — Approved implementation plan; create before TODO.
  - `docs/00x-<feature>.md` — Implementation journal: decisions, facts, changes, failures, configuration and evidence.
  - `docs/00x-<feature>-todo.md` — Created after planning; canonical living TODO. Every item, including nested items, MUST have a unique ID and acceptance criteria. Update status immediately upon completion.
  - `docs/tutorial-00x-<feature>.md` — Spoon-fed user-facing tutorial. Create on request or feature completion. Append; never overwrite.

- Project state: Feature TODO is the sole task-status source. Never duplicate task status across documents. Keep plan/TODO aligned. Implementation journal stores durable implementation history, not duplicated task status.

- Testing/verification: Maintain unit, integration and deployment smoke tests. Track implementation, automated testing and real-world verification separately. Run relevant tests in the prescribed environment (`uv` for Python). Convert repeatable manual checks/fixes into regression tests. Record commands, results and evidence in the implementation journal. Never mark partially verified tasks complete or claim unverified success.

- Git: Inspect `git status` before each top-level TODO, not nested items. If dirty, inspect changes and ask how to handle them before proceeding. Never silently carry, overwrite or discard changes. Stage only task files; review staged diffs and run `git diff --cached --check`. Recommend committing verified task-specific changes. No commit/push without approval.

- Infrastructure/security: Terraform/Pulumi plan allowed. Human approval REQUIRED for apply, destroy, IAM/security changes and destructive operations. Document resources and exact IAM actions, grouped by resource. Never expose, modify or transmit secrets, credentials, tokens or personal data without permission.

- Debugging: State failure, hypothesis, supporting evidence, smallest experiment and expected result before troubleshooting. One hypothesis per experiment. Preserve useful logs/reproductions; avoid speculative fixes.

- Efficiency: Minimize tokens/tool calls. Read only relevant files. Keep responses concise.
