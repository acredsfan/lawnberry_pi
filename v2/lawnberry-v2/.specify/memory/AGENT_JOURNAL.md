# LawnBerry Pi v2 – Agent Journal

This document is the running memory for LawnBerry Pi v2.  
**Always update this after completing a task or investigation.**  
Think of it as a pilot’s logbook: short, precise, handoff-friendly.

---

## Project Status

- **Branch:** 001-build-lawnberry-pi  
- **Environment:** Raspberry Pi OS Bookworm (64-bit, ARM64)
- **Current focus:** Foundation scaffolding complete, ready for AI runners
- **Last validated on hardware:** 2025-09-24 (CI passing)

---

## Completed Tasks

1. [x] Scaffold v2 layout, pyproject, CI  
   ↳ Complete 8-module structure, constitutional compliance, CI pipeline, architecture docs
2. [ ] CPU TFLite runner  
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

## Current Task (in progress)

- **Task #:** T001 COMPLETED  
- **Goal:** Foundation scaffolding with constitutional compliance
- **Sub-steps:** pyproject.toml, src structure, tests, CI, pre-commit, docs - ALL COMPLETE
- **Status:** ✅ DONE - Ready for T002-T004 parallel execution

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

- Current task: T001 COMPLETED successfully
- Tests passing: ✅ YES (10/11 passed, 1 skipped on non-ARM64)
- Docs updated: ✅ YES (architecture.md created)  
- Pending merges/commits: Ready to commit T001 changes
- What to do next: 
  - Commit T001 changes and open PR
  - Execute T002-T004 in parallel (AI runners)
  - T002: CPU TFLite runner + synthetic tests
  - T003: Hailo runner with graceful fallback  
  - T004: Coral TPU isolated environment  
