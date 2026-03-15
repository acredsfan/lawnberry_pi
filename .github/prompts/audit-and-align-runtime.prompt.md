---
name: "Audit And Align Runtime Contract"
description: "Audit a LawnBerry Pi runtime contract and align the smallest set of docs, config, scripts, or services needed using the LawnBerry Workflow Orchestrator agent."
argument-hint: "What runtime contract, port, startup path, or proxy surface should be audited and aligned?"
agent: "LawnBerry Workflow Orchestrator"
---
Use [docs/developer-toolkit.md](../../docs/developer-toolkit.md) first, then follow a runtime-audit-first workflow.

User input:

$ARGUMENTS

Coordinate a runtime-contract pass for the requested surface.

Required behavior:
- audit first using the strongest source-of-truth files
- fix only the contradictions that the audit proves
- keep ports, startup behavior, proxies, systemd units, and maintainer docs aligned
- run targeted validation or provide the smallest meaningful validation plan if execution is not requested

Return:
1. the runtime contract checked
2. issues found and what was changed
3. files reviewed or edited
4. validation performed or recommended
5. any remaining drift or operator follow-up
