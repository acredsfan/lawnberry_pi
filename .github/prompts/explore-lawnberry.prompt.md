---
name: "Explore LawnBerry"
description: "Do a fast, read-only exploration of a LawnBerry Pi topic using the LawnBerry Workflow Orchestrator agent."
argument-hint: "What should be explored? Include thoroughness: quick, medium, or thorough."
agent: "LawnBerry Workflow Orchestrator"
---
Use [docs/developer-toolkit.md](../../docs/developer-toolkit.md) first to orient the investigation.

User input:

$ARGUMENTS

Perform a read-only exploration of the requested topic. Treat the argument as including both the subject and desired thoroughness.

If helpful, delegate discovery to the fast exploration specialist, but keep the overall workflow read-only.

Focus on:
- locating the most relevant files, symbols, and docs
- building a concise mental model of how the area works
- calling out likely source-of-truth files and adjacent risk areas
- recommending the best next prompt or agent if deeper work is needed

Return:
1. the key files and symbols to read next
2. a concise explanation of how the area works
3. important constraints or drift risks
4. the best next prompt or agent for follow-up work
