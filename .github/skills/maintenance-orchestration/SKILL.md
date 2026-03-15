---
name: maintenance-orchestration
description: 'Use when a LawnBerry Pi task spans re-entry, specialist routing, implementation, documentation sync, and validation. Covers choosing the right specialist workflow and sequencing investigation, changes, doc updates, and test planning.'
argument-hint: 'What multi-step maintenance task should be orchestrated?'
user-invocable: true
---

# Maintenance Orchestration

## What this skill does

This skill coordinates substantial LawnBerry Pi work so the agent starts with project re-entry, picks the right specialist path, and closes the loop with docs sync and validation.

## When to use

- the task touches more than one subsystem
- you are unsure which specialist agent or skill should lead
- the request mixes code, docs, runtime behavior, and validation
- a change risks leaving maintainer docs or regression coverage behind

## Procedure

1. Start with `docs/developer-toolkit.md` and apply the `maintainer-reentry` skill.
2. Classify the request:
   - runtime/docs drift
   - deployment or service operations
   - frontend state or API/WebSocket flow
   - hardware-sensitive safety path
   - general backend/frontend implementation
   - code-structure doc sync
   - validation planning only
3. Route to the best specialist workflow first:
   - drift audit -> `runtime-contract-audit`
   - hardware-sensitive validation split -> `sim-hardware-validation`
   - navigation hardening -> `navigation-hardening-pass`
   - mission durability -> `mission-recovery-pass`
   - control/camera regressions -> `control-camera-regression-review`
   - AI quality work -> `ai-model-quality-pass`
   - maintainer doc alignment -> `maintainer-doc-sync`
4. If implementation is needed, make the smallest safe change after the focused investigation.
5. Sync docs in the same pass when runtime behavior, hardware scope, subsystem maturity, or callable interfaces changed.
6. Finish with targeted validation or a minimal validation plan.

## Decision rules

- prefer specialist depth over broad guessing
- prefer simulation-safe validation first unless the task explicitly requires hardware
- if the task touches motors, blade, RoboHAT, camera, or watchdog paths, insert safety review before trusting the change
- if callable interfaces changed, update `docs/code_structure_overview.md`

## Completion checks

- the leading specialist path was chosen deliberately
- docs sync obligations were identified before finishing
- validation was either executed or explicitly planned
- final summary states what changed, what was checked, and what remains risky
