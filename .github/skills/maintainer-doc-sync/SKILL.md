---
name: maintainer-doc-sync
description: 'Keep LawnBerry Pi maintainer documentation synchronized with implementation. Use when runtime behavior, supported hardware scope, subsystem maturity, immediate focus, two-week plan, release notes, or callable interfaces have changed and docs must be updated in the same pass.'
argument-hint: 'What implementation change needs maintainer doc synchronization?'
user-invocable: true
---

# Maintainer Doc Sync

## What this skill does

This skill keeps the maintainer-facing documentation honest after implementation changes.

## Trigger conditions

Use this skill when a change affects any of the following:

- runtime behavior, ports, startup expectations, or deployment workflow
- supported hardware scope or fallback story
- subsystem maturity or practical limitations
- immediate-focus priorities or high-level next steps
- callable interfaces in `backend/src/**`, `frontend/src/**`, `scripts/**`, or `.specify/scripts/**`

## Required docs to consider

- `docs/developer-toolkit.md`
- `docs/RELEASE_NOTES.md`
- `docs/code_structure_overview.md`
- `README.md`, `docs/OPERATIONS.md`, or `docs/TESTING.md` when runtime behavior changed
- hardware docs and `spec/hardware.yaml` when supported hardware claims changed

## Procedure

1. Determine which source-of-truth files changed behavior.
2. Update the matching maintainer docs in the same pass.
3. For callable-interface changes, regenerate the relevant sections of `docs/code_structure_overview.md` and verify signatures against source.
4. Re-read edited docs to confirm they match code and config, not wishful thinking.
5. If using the docs drift checker, remember its known environment quirk: `scripts/check_docs_drift.sh` may print `fatal: depth 0 is not a positive number` while still exiting `0`; trust the exit status.

## Editing rules

- prefer precise factual updates over broad prose rewrites
- keep subsystem maturity labels honest
- keep supported hardware grounded in `spec/hardware.yaml`
- never leave a code change behind without the maintainer-doc update it requires

## Completion checks

- every behavior or interface change has a matching doc update
- `docs/code_structure_overview.md` matches callable signatures after structural changes
- no stale port, hardware, or maturity statements remain in touched docs
