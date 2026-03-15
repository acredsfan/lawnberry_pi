---
name: subsystem-hardening-orchestration
description: 'Use for coordinating a LawnBerry Pi hardening pass across high-risk subsystems such as navigation, mission recovery, manual control/camera, and AI quality. Covers routing to the right hardening skill, sequencing focused changes, and keeping validation and docs aligned.'
argument-hint: 'Which subsystem should be hardened: navigation, mission recovery, control/camera, or AI?'
user-invocable: true
---

# Subsystem Hardening Orchestration

## What this skill does

This skill routes hardening work to the right specialized pass so risk-heavy subsystems get focused treatment instead of generic maintenance.

## When to use

- the task is a hardening pass rather than a one-off bug fix
- you need to improve runtime credibility or safety for a known subsystem
- the work spans code changes, regression coverage, and maintainer documentation

## Routing guide

Choose the leading pass based on the subsystem:

- navigation behavior, movement confirmation, stop/fault handling -> `navigation-hardening-pass`
- mission persistence, restart, pause/resume recovery -> `mission-recovery-pass`
- manual control, RoboHAT USB handoff, joystick responsiveness, camera streaming -> `control-camera-regression-review`
- AI quality improvement behind the current API -> `ai-model-quality-pass`

## Procedure

1. Start with `maintainer-reentry`.
2. Choose one primary hardening pass; do not mix several unless evidence demands it.
3. Perform a focused defect or risk audit before editing.
4. Make the smallest credible hardening changes for that subsystem.
5. Extend targeted regression coverage close to the seam.
6. Apply `maintainer-doc-sync` if maturity, limitations, or interfaces changed.
7. End with a concise statement of what was hardened versus what remains field-limited.

## Guardrails

- avoid turning a hardening pass into broad feature work
- keep evidence and validation close to the claimed improvement
- prefer deterministic failure handling over optimistic state advancement

## Completion checks

- one subsystem led the pass
- focused regression coverage exists or was explicitly planned
- maintainer docs reflect any changed maturity or runtime behavior
- remaining limitations are stated plainly
