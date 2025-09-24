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

## Current Task (in progress)

- **Task #:** Preparing for T003/T004  
- **Goal:** Begin accelerator hierarchy completion after CPU fallback  
- **Sub-steps:** Plan Hailo runner scaffolding, outline Coral isolation strategy
- **Status:** ✅ T002 delivered - ready to branch into remaining AI runner tasks

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

- Current task: T002 COMPLETED successfully
- Tests passing: ✅ YES (15 passed total)
- Docs updated: ✅ YES (`docs/ai-acceleration/cpu-tflite.md` added)  
- Pending merges/commits: Ready to commit AI runner baseline
- What to do next: 
   - Execute T003 (Hailo runner) and T004 (Coral isolation) in parallel
   - Extend test harnesses for hardware-detection fallbacks
   - Coordinate docs updates for remaining acceleration tiers  
