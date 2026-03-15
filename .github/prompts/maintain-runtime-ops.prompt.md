---
name: "Maintain Runtime Ops Workflow"
description: "Maintain or fix a LawnBerry Pi deployment, service, TLS, backup, or runtime operations workflow using the Deployment Operations Maintainer agent."
argument-hint: "What deployment, runtime, service, or ops workflow should be maintained or fixed?"
agent: "Deployment Operations Maintainer"
---
Use [docs/developer-toolkit.md](../../docs/developer-toolkit.md), `docs/OPERATIONS.md`, and the relevant service/script files before editing.

User input:

$ARGUMENTS

Maintain only the requested operational surface and make the smallest change that restores correctness or maintainability.

Working rules:
- verify systemd units, scripts, config, and docs together before changing runtime behavior
- keep ports, env vars, restart behavior, file paths, timers, and proxy assumptions aligned
- run only targeted validation with careful timeouts
- update matching operator-facing docs in the same pass when the workflow changes

Return:
1. files changed and why
2. runtime or deployment assumptions verified
3. validation performed
4. any operator follow-up or remaining risks
