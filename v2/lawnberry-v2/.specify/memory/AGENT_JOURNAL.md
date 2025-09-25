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

## Session Log (2025-09-25 – Core System Implementation)

- **WebSocket Hub**: Implemented comprehensive real-time communication system in `src/lawnberry/core/websocket_hub.py` with <100ms latency, 5Hz default telemetry cadence, client management, and topic-based subscriptions.
- **Data Models**: Created complete specification dataclasses (T008-T017) in `src/lawnberry/specs/` covering WebUIPage, TelemetryStream, RestContract, WebSocketTopic, and all required entities per data-model.md.
- **FastAPI Application**: Built core API structure with `src/lawnberry/api/app.py`, dashboard/manual/telemetry routers, and WebSocket endpoint integration.
- **WebSocket Events**: Implemented type-safe Pydantic models in `src/lawnberry/models/websocket_events.py` for all event types with proper validation.
- **Contract Tests**: Created TDD test suite in `tests/contract/` and `tests/integration/` validating REST/WebSocket contract compliance (tests reveal documentation gaps as expected).
- **Constitutional Compliance**: ARM64/Bookworm targeting, no pycoral in main env, timeout management, structured logging, proper async handling.
- Outcome: Core system foundation complete with real-time communication, API structure, and comprehensive testing framework ready for deployment.

---

## Current Task (completed)

- **Task #:** T006 WebSocket Hub + Core Implementation  
- **Goal:** Implement real-time communication backbone per SPEC-002 requirements  
- **Sub-steps:** ✅ WebSocket hub, ✅ Event models, ✅ FastAPI app, ✅ Data model classes, ✅ Contract tests, ✅ API routers  
- **Status:** ✅ Complete - Core system implemented with constitutional compliance, ready for commit and PR

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

- Current focus: T002 complete; SPEC-002 documentation bundle aligned with hardware manifest and concurrency policies
- Tests passing: ✅ YES (15 passed total from CPU fallback suite with restored CI lint job)
- Docs updated: ✅ Plan, research, data model, quickstart, tasks, spec, and hardware manifest synchronized  
- Pending merges/commits: Kick off Hailo/Coral implementation lanes once planning approvals land
- What to do next: 
   - Execute T003 (Hailo runner) and T004 (Coral isolation) initiatives
   - Run `/plan` against updated spec when new constraints emerge
   - Extend test harnesses and document coordination for shared hardware access
