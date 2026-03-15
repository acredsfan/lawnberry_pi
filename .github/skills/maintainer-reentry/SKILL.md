---
name: maintainer-reentry
description: 'Use when returning to LawnBerry Pi after time away, starting substantial maintenance, or needing a fast project re-entry workflow. Covers docs to read first, runtime ports, hardware baseline, simulation vs hardware mode, important files by task, and validation planning.'
argument-hint: 'What task or subsystem are you re-entering for?'
user-invocable: true
---

# Maintainer Re-entry

## What this skill does

This skill turns `docs/developer-toolkit.md` into a repeatable re-entry checklist so the agent regains project context before making changes.

## When to use

- starting substantial maintenance after a gap
- planning work on runtime behavior, hardware scope, safety, navigation, mission, or AI
- triaging a bug when you are not yet sure which subsystem owns it
- checking current ports, source-of-truth docs, or supported hardware before implementation

## Procedure

1. Read these sources first, in this order unless the user narrows scope:
   - `README.md`
   - `docs/OPERATIONS.md`
   - `docs/TESTING.md`
   - `docs/hardware-integration.md`
   - `spec/hardware.yaml`
   - `docs/code_structure_overview.md`
   - `docs/RELEASE_NOTES.md`
   - `docs/hallucination-audit.md`
   - `CONTRIBUTING.md`
   - `.github/copilot-instructions.md`
2. Lock in the current runtime contract before assuming old defaults:
   - backend API: `8081`
   - frontend dev/deployed UI: `3000`
   - Playwright preview: `4173`
3. Decide whether the task is simulation-safe or hardware-sensitive.
   - prefer `SIM_MODE=1` for local development, CI, and first-pass validation
   - treat `SIM_MODE=0` as real-hardware mode with Pi/device expectations
4. Map the task to the most relevant subsystem and files.
   - startup/runtime wiring: `backend/src/main.py`, `backend/src/core/config_loader.py`, `config/`, `docs/OPERATIONS.md`
   - safety/manual control: `backend/src/safety/`, `backend/src/services/robohat_service.py`, `backend/src/services/blade_service.py`
   - telemetry/GPS/RTK: `backend/src/services/sensor_manager.py`, `telemetry` services, RTK scripts, NTRIP docs
   - manual control/operator UI: `frontend/src/views/ControlView.vue`, `frontend/src/stores/control.ts`, API and WebSocket services
   - maps/planning/mission: `frontend/src/views/MapsView.vue`, `PlanningView.vue`, `MissionPlannerView.vue`, mission/navigation services
5. Build a short execution checklist before editing.
6. Prefer the smallest change that restores shared reality rather than speculative feature sprawl.

## Decision points

- If docs and code disagree, trust code, config, service units, and `spec/hardware.yaml` over prose.
- If hardware is not explicitly required, stay simulation-safe first.
- If runtime behavior, subsystem maturity, or supported hardware changed, update `docs/developer-toolkit.md` in the same pass.
- If callable interfaces changed in `backend/src/**`, `frontend/src/**`, or `scripts/**`, update `docs/code_structure_overview.md` too.

## Completion checks

- current port contract is stated explicitly
- hardware baseline came from `spec/hardware.yaml`, not assumption
- simulation vs hardware mode was chosen deliberately
- affected files and tests are identified before editing
- follow-up doc sync requirements are known up front
