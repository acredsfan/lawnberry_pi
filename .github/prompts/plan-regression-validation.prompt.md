---
name: "Plan Regression Validation"
description: "Produce the smallest meaningful LawnBerry Pi validation plan for a specific change using the Regression Test Planner agent."
argument-hint: "What change should be mapped to a minimal validation plan?"
agent: "Regression Test Planner"
---
Use [docs/developer-toolkit.md](../../docs/developer-toolkit.md) and `docs/TESTING.md` before making recommendations.

User input:

$ARGUMENTS

Produce a focused validation plan for the requested change or risk area.

Working rules:
- keep the plan simulation-safe first unless the user explicitly needs live hardware validation
- map recommendations to touched files, behavior, and regression risks
- prefer the smallest high-confidence validation set over broad full-suite suggestions
- do not run tests unless the user explicitly asks for execution

Return:
1. recommended test commands or targets
2. why each item matters
3. uncovered risks or missing tests
4. overall confidence level
