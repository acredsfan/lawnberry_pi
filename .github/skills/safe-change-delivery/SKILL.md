---
name: safe-change-delivery
description: 'Use for delivering a LawnBerry Pi code change with re-entry, scoped investigation, safe implementation, maintainer doc sync, and targeted validation. Covers general backend/frontend work plus hardware-aware guardrails when the change is safety sensitive.'
argument-hint: 'What change should be delivered safely end-to-end?'
user-invocable: true
---

# Safe Change Delivery

## What this skill does

This skill turns a change request into a disciplined end-to-end workflow: re-enter, investigate, implement, sync docs, validate, and report honestly.

## When to use

- implementing a backend or frontend fix
- making a change that may affect runtime behavior, tests, or docs
- handling user requests that are broader than a single-file edit
- delivering a change that should not skip validation or maintainer updates

## Procedure

1. Start with `maintainer-reentry` and classify the change as simulation-safe or hardware-sensitive.
2. Investigate the exact subsystem before editing.
3. Insert special passes when needed:
   - hardware-sensitive paths -> `sim-hardware-validation`
   - manual control or camera -> `control-camera-regression-review`
   - navigation logic -> `navigation-hardening-pass`
   - mission persistence/recovery -> `mission-recovery-pass`
   - AI quality improvement -> `ai-model-quality-pass`
4. Implement the smallest reliable change.
5. Apply `maintainer-doc-sync` if behavior, maturity, hardware scope, or interfaces changed.
6. Run targeted tests or checks that match the touched seam.
7. Summarize both verified outcomes and anything still unverified.

## Working rules

- investigation before editing
- simulation-safe first unless live hardware is explicitly required
- small diffs beat sprawling refactors
- docs sync is part of delivery, not an optional dessert course

## Completion checks

- changed seam was understood before editing
- validation matched the actual risk of the change
- required docs were updated in the same pass
- final notes distinguish tested behavior from assumptions
