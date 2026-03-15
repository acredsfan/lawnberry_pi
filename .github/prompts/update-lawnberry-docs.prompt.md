---
name: "Update LawnBerry Docs"
description: "Update or align LawnBerry Pi documentation against the current implementation using the LawnBerry Docs Maintainer agent."
argument-hint: "What docs should be updated or kept in sync?"
agent: "LawnBerry Docs Maintainer"
---
Use [docs/developer-toolkit.md](../../docs/developer-toolkit.md) first, especially for runtime behavior, hardware scope, subsystem maturity, and maintainer guidance.

User input:

$ARGUMENTS

Update only the requested documentation surface, using the smallest accurate edits that restore clarity and consistency.

While working:
- verify claims against code, config, scripts, or package metadata before editing
- update `docs/developer-toolkit.md` in the same pass if runtime behavior, hardware scope, subsystem maturity, immediate focus, the 2-week plan, or high-level next steps changed
- update `docs/code_structure_overview.md` if callable interfaces changed in `backend/src/**`, `frontend/src/**`, `scripts/**`, or `.specify/scripts/**`
- preserve useful structure unless a small structural improvement clearly helps maintainability

Return:
1. files changed and why
2. source-of-truth files used for verification
3. any remaining drift or assumptions
4. suggested follow-up validation, if needed
