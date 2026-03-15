---
name: navigation-hardening-pass
description: 'Use for LawnBerry Pi navigation hardening work: feedback audit, waypoint progress validation, stop and fault behavior, obstacle gating, interrupted traversal handling, and targeted regression coverage in navigation and mission flows.'
argument-hint: 'What navigation behavior, failure mode, or contract needs hardening?'
user-invocable: true
---

# Navigation Hardening Pass

## What this skill does

This skill packages the navigation/runtime credibility workflow from the maintainer handbook into a repeatable implementation sequence.

## Best use cases

- waypoint progress advancing too optimistically
- pause, abort, interrupt, or fault paths not stopping cleanly
- obstacle hold or lost-position behavior uncertainty
- mission execution depending on navigation behavior without enough feedback evidence

## Procedure

1. Start with a navigation feedback audit.
   - trace where the system assumes movement succeeded
   - identify where encoder, GPS, controller, or other feedback actually confirms motion
   - list state transitions that can advance without enough evidence
2. Harden stop and fault behavior.
   - ensure controller failures, obstacle holds, interrupts, and aborts fail closed
   - verify pause and abort paths route through a clean stop path
3. Tighten regression coverage.
   - prioritize service-level and contract-level tests around interrupted waypoint traversal, lost position, obstacle gating, and command-delivery failures
4. Re-run the focused navigation and mission validation slice.
5. Update maintainer docs if subsystem maturity, behavior, or limitations changed materially.

## Working rules

- prefer concrete field-feedback evidence over optimistic state updates
- keep behavior deterministic when control or position confidence drops
- do not broaden scope into unrelated autonomy work during a hardening pass
- if navigation service signatures or public helpers changed, sync `docs/code_structure_overview.md`

## Completion checks

- a defect list or risk list exists before edits begin
- stop and interruption semantics are explicit after the change
- regression coverage matches the specific failure mode addressed
- final notes distinguish hardened behavior from remaining field limitations
