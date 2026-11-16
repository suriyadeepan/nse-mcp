# AGENTS.md

- **Security:** Never access, expose, modify, or transmit secrets, `.env` files, credentials, SSH keys, tokens, or personal data without explicit permission.
- **Exclusions:** Respect `.clineignore`; never bypass file exclusions.
- **Token economy:** Minimize input/output tokens, tool calls, context consumption, and verbose reasoning.
- **Targeted reads:** Inspect only relevant files, code sections, and bounded command outputs. Never dump entire codebases.
- **Concise responses:** Use short bullet points. No unnecessary explanations, repetition, or walkthroughs.
- **Minimal changes:** Modify only what the task requires. Avoid unrelated refactoring, abstractions, and dependencies.
- **Context management:** Preserve essential decisions and progress. Summarize before context exhaustion.
- **Execution:** Inspect → Plan → Implement → Validate. Avoid unnecessary intermediate steps.
- **Testing:** Run relevant tests only. Report actual results and failures; never fabricate success.
- **Final report:** Summarize changes, affected files, test results, and blockers in 3–5 bullets.
