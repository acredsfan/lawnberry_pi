---
name: "Implement LawnBerry Change"
description: "Implement or fix a LawnBerry Pi code change using the LawnBerry Maintainer agent with repo-aware validation and doc sync."
argument-hint: "What should be implemented, fixed, or maintained?"
agent: "LawnBerry Maintainer"
---
Use [docs/developer-toolkit.md](../../docs/developer-toolkit.md) first as the project re-entry map.

User input:

$ARGUMENTS

Implement or fix the requested change while staying aligned with LawnBerry Pi runtime, safety, and documentation rules.

Required behavior:
- read the closest source-of-truth files before editing
- respect the split between simulation-safe work and real hardware behavior
- keep hardware-sensitive changes conservative around motors, blade control, camera ownership, telemetry, and RoboHAT paths
- update `docs/developer-toolkit.md` when runtime behavior, supported hardware scope, subsystem maturity, immediate focus, the 2-week plan, or high-level next steps changed
- update `docs/code_structure_overview.md` when callable interfaces changed in `backend/src/**`, `frontend/src/**`, `scripts/**`, or `.specify/scripts/**`
- run targeted validation after changes and summarize results

Return:
1. files changed and why
2. validation performed
3. remaining risks, assumptions, or follow-up suggestions
