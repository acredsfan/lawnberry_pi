---
name: "Audit Runtime Drift"
description: "Audit LawnBerry Pi docs, config, scripts, or runtime drift for a specific surface using the Drift Auditor agent."
argument-hint: "What should be audited? e.g. ports, SIM_MODE docs, hardware claims, test instructions"
agent: "Drift Auditor"
---
Use [docs/developer-toolkit.md](../../docs/developer-toolkit.md) as the maintainer re-entry map before starting.

User input:

$ARGUMENTS

Audit only the requested surface and keep the work read-only unless the user explicitly asks for fixes.

Focus on:
- strongest source-of-truth files first
- contradictions across docs, config, scripts, and runtime code
- concrete evidence with file paths
- practical remediation steps in priority order

Return:
1. the contract or workflow you checked
2. findings grouped by severity
3. files compared
4. recommended alignment actions
5. the best next agent or prompt to use, if follow-up work is needed
