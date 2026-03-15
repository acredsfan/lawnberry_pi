---
name: "Re-enter And Triage LawnBerry"
description: "Re-enter the LawnBerry Pi codebase, classify a task, and choose the best specialist workflow using the LawnBerry Workflow Orchestrator agent."
argument-hint: "What task or subsystem are you re-entering for?"
agent: "LawnBerry Workflow Orchestrator"
---
Use [docs/developer-toolkit.md](../../docs/developer-toolkit.md) as the first source of truth.

User input:

$ARGUMENTS

Re-enter the codebase for the requested task and produce a tight triage result before any major implementation work.

Required outcome:
- identify the subsystem and risk level
- state whether the work is simulation-safe or hardware-sensitive
- list the key files and docs to inspect next
- recommend the best specialist agent, skill, or prompt to use next
- create a concise execution checklist if follow-up work is multi-step
