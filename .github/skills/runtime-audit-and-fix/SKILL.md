---
name: runtime-audit-and-fix
description: 'Use for LawnBerry Pi runtime contract work that starts with drift audit and ends with aligned docs, config, scripts, service definitions, and targeted validation. Covers ports, startup behavior, proxies, systemd units, and maintainer-facing runtime guidance.'
argument-hint: 'What runtime contract or startup surface should be audited and aligned?'
user-invocable: true
---

# Runtime Audit and Fix

## What this skill does

This skill coordinates a full runtime-contract pass: audit first, fix only where evidence shows drift, and verify the updated contract at the end.

## When to use

- ports, startup commands, proxies, or service behavior disagree
- docs and systemd units tell different stories
- local dev, preview, and deployed runtime instructions have drifted apart
- a runtime change needs both implementation and documentation alignment

## Procedure

1. Re-enter with `docs/developer-toolkit.md` and `maintainer-reentry`.
2. Run the `runtime-contract-audit` skill or equivalent drift investigation first.
3. Compare the strongest sources of truth:
   - `backend/src/main.py`
   - `frontend/vite.config.ts`
   - `frontend/server.mjs`
   - `frontend/playwright.config.ts`
   - `systemd/`
   - `docs/OPERATIONS.md`, `docs/TESTING.md`, `README.md`
4. Fix the smallest set of files needed to restore one coherent contract.
5. Apply `maintainer-doc-sync` if runtime behavior, maintainer guidance, or callable interfaces changed.
6. Validate with the smallest meaningful runtime checks and, if needed, a focused regression plan.

## Guardrails

- do not change canonical ports casually; align the repo unless there is an intentional contract change
- do not trust prose docs over code, config, or service definitions
- avoid broad rewrites when targeted corrections solve the drift
- keep simulation-safe vs hardware-specific steps clearly separated

## Completion checks

- one clear runtime story exists across code, config, systemd, and docs
- strongest source-of-truth files are cited
- edited docs match the actual runtime contract
- validation confirms the aligned behavior or clearly scopes what remains unverified
