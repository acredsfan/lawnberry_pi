---
name: "Coordinate Hardening Pass"
description: "Coordinate a LawnBerry Pi hardening pass for navigation, mission recovery, control/camera, or AI using the LawnBerry Workflow Orchestrator agent."
argument-hint: "Which subsystem should be hardened, and what failure mode or quality issue should be addressed?"
agent: "LawnBerry Workflow Orchestrator"
---
Use [docs/developer-toolkit.md](../../docs/developer-toolkit.md) first and route the work through the matching hardening workflow.

User input:

$ARGUMENTS

Coordinate a focused hardening pass for the requested subsystem.

Routing expectations:
- navigation -> feedback audit, stop/fault hardening, targeted regression coverage
- mission recovery -> persistence contract, restart semantics, recovery tests
- control/camera -> RoboHAT/camera regression review, safety/fallback checks
- AI -> quality improvement behind the current backend contract

Required behavior:
- choose one leading subsystem unless evidence forces a cross-subsystem pass
- begin with a defect or risk audit before editing
- keep docs and targeted validation aligned with the claimed hardening outcome

Return:
1. subsystem chosen and why
2. leading hardening workflow used
3. files changed or reviewed
4. validation performed or recommended
5. remaining limitations after the pass
