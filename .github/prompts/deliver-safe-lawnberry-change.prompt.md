---
name: "Deliver Safe LawnBerry Change"
description: "Deliver a LawnBerry Pi change with scoped investigation, implementation, doc sync, and targeted validation using the LawnBerry Workflow Orchestrator agent."
argument-hint: "What change should be delivered safely end-to-end?"
agent: "LawnBerry Workflow Orchestrator"
---
Use [docs/developer-toolkit.md](../../docs/developer-toolkit.md) first and treat the task as a safe-change-delivery workflow.

User input:

$ARGUMENTS

Coordinate the requested change from investigation through validation.

Required behavior:
- classify simulation-safe vs hardware-sensitive scope up front
- route to specialist review when frontend flow, hardware safety, runtime drift, or targeted hardening is involved
- implement the smallest reliable change
- sync `docs/developer-toolkit.md` and `docs/code_structure_overview.md` when required
- validate with the smallest meaningful checks for the touched seam

Return:
1. workflow chosen and specialists used
2. files changed and why
3. validation performed
4. remaining risks, assumptions, or follow-up suggestions
