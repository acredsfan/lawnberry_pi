---
title: Phase 8 + Phase 9 Interleaved Execution Design
date: 2026-05-04
status: approved
---

# Phase 8 + Phase 9 Interleaved Execution Design

## Context

Phase 8 (frontend view decomposition) and Phase 9 (observability events) are largely
independent — Phase 8 is pure frontend restructuring, Phase 9 is mostly backend — but
share one conflict: both modify `frontend/src/views/MissionPlannerView.vue`.

This document specifies the execution ordering that lets both phases progress in the same
session without merge conflicts, using a single branch (`main`).

## Approach: Sequential interleaving, backend-first

All work lands on `main` in four sequential waves. No git worktrees. Each wave has a
test gate before the next begins.

### Wave 1 — Phase 9 backend (Tasks 1–9)

Build the entire observability event system before touching any frontend file.

| Step | Deliverable | Source plan |
|------|-------------|-------------|
| 9.1 | `backend/src/observability/events.py` — 7 event dataclasses | Phase 9, Task 1 |
| 9.2 | `backend/src/observability/event_store.py` — EventStore + DB migration 6 | Phase 9, Task 2 |
| 9.3 | `RuntimeContext.event_store` wired in `main.py` lifespan | Phase 9, Task 3 |
| 9.4 | `NavigationService` emits `GpsFixAcquired`, `GpsFixLost` | Phase 9, Task 4 |
| 9.5 | `MotorCommandGateway` emits `MotorCommandIssued` | Phase 9, Task 5 |
| 9.6 | `MissionService` emits `MissionStateChanged`, `SafetyGateBlocked`, `ObstacleDetected`, `BoundaryViolation` | Phase 9, Task 6 |
| 9.7 | `GET /api/v2/missions/{id}/run-summary` endpoint | Phase 9, Task 7 |
| 9.8 | WebSocket broadcast of events | Phase 9, Task 8 |
| 9.9 | Backend CI budget test (event count assertions) | Phase 9, Task 9 |

**Gate:** Full unit test suite passes (SIM_MODE=1, excluding known pre-existing failures).

### Wave 2 — Phase 8 Parts B, C, D (frontend, no MissionPlannerView)

Decompose the three views that have no overlap with Phase 9's frontend work.

| Part | View | Key extractions |
|------|------|-----------------|
| B | ControlView | `useControlSession`, `useJoystickDrive` composables; `ControlLockoutGate`, `SessionStatusBar` components |
| C | DashboardView | `useDashboardTelemetry` composable; `PowerSystemCard`, `OrientationCard`, `GpsCard`, `EnvironmentalCard`, `SystemStatusCard` components |
| D | BoundaryEditorView | map-editing composable; `BoundaryToolbar` component |

**Gate:** `npm run type-check && npm test` passes inside `frontend/`.

### Wave 3 — Phase 8 Part A (MissionPlannerView decomposition)

Refactor `MissionPlannerView.vue` into its orchestration shell and extract:
- Composables: `useMowerTelemetry`, `useMissionMapSettings`, `useCameraFeed`
- Components: `MissionControls.vue`, `MissionStatusPanel.vue`, `CameraPanel.vue`

This wave produces the stable `MissionPlannerView.vue` shell that Wave 4 extends.

**Gate:** `npm run type-check && npm test` passes.

### Wave 4 — Phase 9 Tasks 10–13 (frontend observability)

Mount the diagnostics panel into the now-stable `MissionPlannerView.vue` shell.

| Step | Deliverable | Source plan |
|------|-------------|-------------|
| 9.10 | `frontend/src/composables/useMissionDiagnostics.ts` | Phase 9, Task 10 |
| 9.11 | `MissionDiagnosticsPanel.vue` mounted in `MissionPlannerView.vue` | Phase 9, Task 11 |
| 9.12 | Frontend CI budget test | Phase 9, Task 12 |
| 9.13 | Documentation update | Phase 9, Task 13 |

**Gate:** Full unit suite + type-check + contract tests pass; final push.

## Conflict resolution

`MissionPlannerView.vue` is touched twice:
- Wave 3 (Phase 8 Part A, Task A-5): produces the orchestration shell
- Wave 4 (Phase 9 Task 11.2): adds `<MissionDiagnosticsPanel>` mount to that shell

By ordering Wave 3 before Wave 4, Task 11.2 receives a known stable base and performs a
targeted additive change — no merge conflict or rebasing required.

## Execution method

Use `superpowers:subagent-driven-development` as the execution skill. Within each wave,
dispatch one implementation subagent per task, followed by spec compliance review and
code quality review, before moving to the next task.

Do not dispatch multiple implementation subagents in parallel within a wave (git conflict
risk on shared test infrastructure).

## Constraints (from session CLAUDE.md)

- `SIM_MODE=1` on every test run
- Never commit `docs/superpowers/plans/`
- Never use `git add -A` or `git add .`
- Never bypass pre-commit hooks (`--no-verify`)
- TDD order: failing test → confirm failure → implement → confirm pass
- Commit and push at each task boundary
