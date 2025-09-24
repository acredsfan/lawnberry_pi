# LawnBerry Pi v2 – Agent Journal

This document is the running memory for LawnBerry Pi v2.  
**Always update this after completing a task or investigation.**  
Think of it as a pilot’s logbook: short, precise, handoff-friendly.

---

## Project Status

- **Branch:** 002-update-spec-to  
- **Environment:** Raspberry Pi OS Bookworm (64-bit, ARM64)
- **Current focus:** Foundation scaffolding complete, ready for AI runners
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

---

## Current Task (in progress)

- **Task #:** T003/T004 prep  
- **Goal:** Finalize accelerator hierarchy plan following CPU fallback and SPEC-002 updates  
- **Sub-steps:** Plan Hailo runner scaffolding, outline Coral isolation strategy, cascade spec-driven REST/WS contracts  
- **Status:** ✅ CPU fallback landed; SPEC-002 doc refresh awaiting stakeholder sign-off

---

## Key Decisions (ADR-style summaries)

- **Acceleration order:** Coral (venv-coral) → Hailo (extra) → CPU (TFLite).  
- **Dependency manager:** uv (linux/arm64 default target).  
- **GPIO lib:** python-periphery + lgpio.  
- **Docs enforcement:** CI fails on drift.  
- **TODO rule:** only `TODO(v3):` with issue link.  

---

## Known Issues / Next Debug Steps

- [ ] Example: Need to test INA3221 I2C driver on mower Pi.  
- [ ] Example: Check Coral TPU wheel compatibility for Python 3.11.  

---

## Handoff Notes

For the next session / agent:

- Current focus: T002 complete; SPEC-002 spec refresh drafted and published
- Tests passing: ✅ YES (15 passed total from CPU fallback suite)
- Docs updated: ✅ YES (`docs/ai-acceleration/cpu-tflite.md`, spec, hardware manifest)  
- Pending merges/commits: Integrate accelerator planning commits post-review
- What to do next: 
   - Execute T003 (Hailo runner) and T004 (Coral isolation) initiatives
   - Run `/plan` against updated spec to refresh planning artifacts
   - Extend test harnesses and document coordination for shared hardware access
