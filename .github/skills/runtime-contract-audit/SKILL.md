---
name: runtime-contract-audit
description: 'Audit LawnBerry Pi runtime contract drift across ports, startup behavior, systemd units, frontend proxies, docs, scripts, and config. Use for port mismatches, startup confusion, README vs runtime checks, and source-of-truth comparison work.'
argument-hint: 'What runtime surface or port/startup behavior should be audited?'
user-invocable: true
---

# Runtime Contract Audit

## What this skill does

This skill performs a focused drift audit for ports, startup wiring, proxy behavior, and maintainer-facing runtime instructions.

## Use it for

- port mismatch reports
- startup command confusion
- frontend-to-backend proxy drift
- systemd/runtime/docs inconsistency checks
- validating that a change did not silently break the established contract

## Source-of-truth files

Read and compare these first:

- `docs/developer-toolkit.md`
- `README.md`
- `docs/OPERATIONS.md`
- `docs/TESTING.md`
- `frontend/vite.config.ts`
- `frontend/server.mjs`
- `frontend/playwright.config.ts`
- `systemd/`
- `backend/src/main.py`
- relevant scripts under `scripts/`

## Procedure

1. Capture the claimed runtime contract from maintainer docs.
2. Verify the canonical ports and behavior in code and service units.
3. Compare these surfaces explicitly:
   - backend bind port and path prefix
   - frontend dev port, preview port, and production server behavior
   - proxy target for `/api`
   - local development commands vs deployed service commands
   - docs examples vs actual service wiring
4. Produce a concise mismatch table grouped by severity.
5. If fixing drift, update the smallest set of docs/config files needed to restore a single consistent story.
6. Re-check all touched surfaces after the edit.

## Decision rules

- treat `backend/src/main.py`, service units, and active frontend config as stronger truth than prose docs
- keep `8081`, `3000`, and `4173` unless intentionally changing the contract everywhere
- avoid broad rewrites; prioritize contradictions that would mislead maintainers or operators

## Completion checks

- strongest source of truth is cited for each finding
- any port mismatch is resolved or clearly documented
- startup instructions match actual runtime behavior
- no stale proxy or service-unit references remain in edited files
