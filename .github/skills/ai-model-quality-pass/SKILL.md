---
name: ai-model-quality-pass
description: 'Use for improving LawnBerry Pi AI result quality without breaking the existing backend contract. Covers ai_service review, model artifact or rule improvement, conservative evaluation, performance notes, and avoiding premature accelerator-specific churn.'
argument-hint: 'What AI quality improvement should be made behind the current backend contract?'
user-invocable: true
---

# AI Model Quality Pass

## What this skill does

This skill focuses AI work on better quality behind the existing API rather than reopening the contract every time perception needs improvement.

## Use it for

- swapping or improving the baseline CPU model artifact
- tuning inference rules or post-processing
- tightening result reporting while preserving API compatibility
- documenting realistic subsystem maturity and limitations

## Procedure

1. Read the current contract and tests first.
   - `backend/src/services/ai_service.py`
   - AI API routes and models
   - `tests/test_ai_api.py`
   - `tests/unit/test_ai_service.py`
   - repo memory or docs describing the AI contract
2. Preserve the existing backend surface unless the task explicitly requires contract change.
3. Improve quality inside the seam.
   - better model artifact
   - better thresholds or heuristics
   - better result normalization or error reporting
4. Validate with focused tests and any available representative inputs.
5. Report performance and quality notes honestly from this session only.
6. Update docs if subsystem maturity or operating caveats changed.

## Guardrails

- do not oversell the subsystem as production-grade perception unless evidence supports it
- avoid accelerator-specific churn unless it clearly improves reliability
- keep model-quality work conservative and reversible

## Completion checks

- API compatibility was preserved or explicitly documented as changed
- tests still pass for the existing AI contract
- performance or quality claims are tied to actual validation in this session
- limitations remain visible in the final notes
