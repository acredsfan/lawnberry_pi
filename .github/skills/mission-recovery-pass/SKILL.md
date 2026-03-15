---
name: mission-recovery-pass
description: 'Use for LawnBerry Pi mission persistence and recovery work. Covers what mission state should survive restart, safe restart semantics, paused vs running recovery behavior, lifecycle validation, and persistence-backed tests.'
argument-hint: 'What mission persistence or restart/recovery behavior should be designed or implemented?'
user-invocable: true
---

# Mission Recovery Pass

## What this skill does

This skill guides conservative mission durability work so missions survive process restarts without pretending the mower is still actively moving.

## When to use

- mission state is in-memory only
- restart behavior is ambiguous or unsafe
- pause/resume semantics are under-specified
- recovery logic needs persistence-backed tests

## Procedure

1. Define the persistence contract before coding.
   - mission metadata
   - lifecycle state
   - current waypoint or progress index
   - pause, abort, or failure details
2. Decide restart semantics with fail-safe defaults.
   - do not silently restore an active-moving state after backend restart
   - prefer resumable paused or stopped state unless fresh evidence justifies more
3. Implement the smallest safe persistence path first.
4. Add tests for:
   - restart during running mission
   - restart during paused mission
   - abort and failure detail retention
   - invalid or stale recovered state
5. Sync docs if runtime behavior or maturity changed.

## Decision rules

- recoverability beats cleverness
- explicit restart rules beat inferred behavior
- persistence should make state inspectable, not magical
- mission logic changes often require checking adjacent navigation assumptions too

## Completion checks

- persisted fields are defined explicitly
- restart behavior is fail-safe and documented
- tests cover both valid and invalid recovery scenarios
- final summary explains what survives restart and what intentionally does not
