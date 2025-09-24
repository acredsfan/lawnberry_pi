# LawnBerry Pi v2 – Agent Journal

This document is the running memory for LawnBerry Pi v2.  
**Always update this after completing a task or investigation.**  
Think of it as a pilot’s logbook: short, precise, handoff-friendly.

---

## Project Status

- **Branch:** v2-spec-rebuild
- **Environment:** Raspberry Pi OS Bookworm (64-bit, ARM64)
- **Current focus:** [Fill in latest task]
- **Last validated on hardware:** [date]

---

## Completed Tasks

1. [ ] Scaffold v2 layout, pyproject, CI  
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

- **Task #:**  
- **Goal:**  
- **Sub-steps:**  
- **Status:**  

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

- Current task: [fill in]  
- Tests passing: [yes/no]  
- Docs updated: [yes/no]  
- Pending merges/commits: [list]  
- What to do next: [bullet list]  
