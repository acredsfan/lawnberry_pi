# LawnBerry Pi v2 – Agent Journal

This document is the running memory for LawnBerry Pi v2.  
**Always update this after completing a task or investigation.**  
Think of it as a pilot’s logbook: short, precise, handoff-friendly.

---

## Project Status

- **Branch:** 002-update-spec-to  
- **Environment:** Raspberry Pi OS Bookworm (64-bit, ARM64)
- **Current focus:** WebUI specification alignment (docs, data models, quickstart, tasks)
- **Last validated on hardware:** 2025-09-24 (CI passing)

---

## Completed Tasks

1. [x] Scaffold v2 layout, pyproject, CI  
   ↳ Complete 8-module structure, constitutional compliance, CI pipeline, architecture docs
2. [x] CPU TFLite runner  
   ↳ Implemented CPU fallback with synthetic test harness and docs page
3. [ ] Hailo runner  
4. [ ] Coral integration  
5. [ ] Camera pipeline  
6. [ ] WebSocket hub  
7. [ ] Safety & motion control  
8. [ ] Sensor integration  
9. [ ] WebUI  
10. [ ] Deployment scripts + systemd  
11. [ ] Docs site + ADRs  
12. [ ] Migration guide  

> Tick each `[ ]` → `[x]` as tasks finish. Add a one-liner summary below each.

---

## Session Log (2025-09-24 – Spec Update)

- Created feature branch `002-update-spec-to` through `/specify` automation.
- Authored spec draft enumerating all seven WebUI pages, their goals, and associated REST/WebSocket obligations.
- Synchronized hardware requirements with `spec/hardware.yaml`, covering preferred vs. alternative components and conflict notes.
- Outcome: Spec is ready for planning artifacts to incorporate new page inventory and contract expectations.

## Session Log (2025-09-24 – Planning & Tasks)

- Consumed `plan.md`, `research.md`, `data-model.md`, `quickstart.md`, and new contract specs to scope implementation work.
- Generated `/specs/002-update-spec-to/tasks.md` with 29 dependency-ordered tasks covering setup, TDD contract checks, datamodel scaffolding, documentation updates, integration alignment, and polish gates.
- Logged contract and integration test placeholders (T003–T007) to enforce spec coverage before implementation, and added dataclass tasks (T008–T014) to keep documentation and code models in lockstep.
- Outcome: Feature is ready for `/tasks` execution with clear sequencing, parallel lanes, and constitution-aligned quality gates.

## Session Log (2025-09-24 – Spec Cascade Refresh)

- Brought `spec.md` in sync with LawnBerry Pi v2 platform guidance: 5–10 Hz telemetry cadence, retro branding assets, REST/WebSocket route map, and hardware hierarchy reminders.
- Updated `plan.md`, `research.md`, `data-model.md`, `quickstart.md`, and `tasks.md` to mirror the expanded scope—adding telemetry cadence policies, mow job events, brand assets, and refreshed validation steps.
- Ran `uv run pytest`; repo structure tests flagged missing `lint-and-format` job in `.github/workflows/ci.yml` (no fix applied yet).
- Outcome: Documentation and planning artifacts now reflect the authoritative 001-build-lawnberry-pi content, with CI follow-up required.

---

## Current Task (in progress)

- **Task #:** SPEC-002  
- **Goal:** Deliver updated specification + planning bundle capturing WebUI scope, cadence policies, and hardware alignment  
- **Sub-steps:** Keep spec/docs synced with hardware manifest, prep follow-up to restore CI lint job
- **Status:** ✅ Documentation cascade complete; CI remediation pending

---

## Key Decisions (ADR-style summaries)

- **Acceleration order:** Coral (venv-coral) → Hailo (extra) → CPU (TFLite).  
- **Dependency manager:** uv (linux/arm64 default target).  
- **GPIO lib:** python-periphery + lgpio.  
- **Docs enforcement:** CI fails on drift.  
- **TODO rule:** only `TODO(v3):` with issue link.  

---

## Known Issues / Next Debug Steps

- [ ] Restore `lint-and-format` job (or equivalent) in `.github/workflows/ci.yml` to satisfy `tests/test_project_structure.py`.
- [ ] Re-run `uv run pytest` after CI workflow update to confirm compliance.
- [ ] Example: Need to test INA3221 I2C driver on mower Pi.  
- [ ] Example: Check Coral TPU wheel compatibility for Python 3.11.  

---

## Handoff Notes

For the next session / agent:

- Current task: SPEC-002 documentation bundle aligned; address CI workflow gap
- Tests passing: ⚠️ `uv run pytest` currently fails (`lint-and-format` job missing in CI workflow)
- Docs updated: ✅ Plan, research, data model, quickstart, tasks, and spec now synchronized with 001-build-lawnberry-pi guidance  
- Pending merges/commits: Stage documentation changes, then fix CI workflow to unblock pytest
- What to do next: 
   - Update `.github/workflows/ci.yml` to add the required lint job, rerun `uv run pytest`
   - Proceed with contract/test tasks once CI passes
   - Keep hardware manifest as single source while implementing follow-on tasks  
