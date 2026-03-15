---
name: control-camera-regression-review
description: 'Review regression-sensitive LawnBerry Pi manual control and camera paths: RoboHAT USB handoff, watchdog feeding, motor authorization, joystick responsiveness, MJPEG and snapshot fallback, camera ownership, and stream backpressure handling.'
argument-hint: 'What manual-control or camera change should be reviewed or hardened?'
user-invocable: true
---

# Control and Camera Regression Review

## What this skill does

This skill provides a conservative review workflow for the two highest-regression surfaces called out in the maintainer handbook: manual control and camera streaming.

## Read first

- `docs/developer-toolkit.md`
- `docs/RELEASE_NOTES.md`
- `backend/src/services/robohat_service.py`
- `backend/src/services/camera_stream_service.py`
- relevant frontend control/camera views, stores, and services
- focused tests for RoboHAT and camera streaming

## Review procedure

1. Identify whether the change touches drive control, USB control handoff, blade-related UI coupling, live stream delivery, snapshots, or operator responsiveness.
2. Trace the backend path end to end.
   - control commands and safety gates
   - watchdog heartbeat feeding
   - motor authorization and interlock checks
   - RoboHAT RC vs USB ownership behavior
   - camera backend selection, simulation fallback, and client delivery path
3. Trace the frontend/operator path.
   - rate or debounce behavior
   - API and WebSocket interaction
   - reconnect or fallback handling
   - user-visible fault states
4. Review tests before refactoring and extend focused coverage instead of relying on happy-path smoke tests.
5. Validate in simulation-safe mode first.

## Non-negotiable checks

- control changes fail closed when safety state is uncertain
- USB control loss does not get hand-waved away as transient noise
- camera changes respect centralized device ownership
- fallback behavior is explicit, not accidental
- performance or responsiveness claims are backed by actual targeted checks from this session

## Completion checks

- changed control/camera path was traced across API, services, and UI if applicable
- regression tests exist or were updated near the sensitive seam
- the summary calls out any remaining hardware-sensitive risk clearly
