---
name: "Regenerate Code Structure Overview"
description: "Refresh docs/code_structure_overview.md for LawnBerry Pi structural code changes using the Code Structure Regenerator agent."
argument-hint: "What structural changes should be reflected in docs/code_structure_overview.md?"
agent: "Code Structure Regenerator"
---
Use [docs/developer-toolkit.md](../../docs/developer-toolkit.md) and [copilot instructions](../copilot-instructions.md) before starting.

User input:

$ARGUMENTS

Refresh only the sections and rows needed to bring `docs/code_structure_overview.md` back in sync with the current source.

Required behavior:
- read the changed source files first
- inventory public Python callables, exported frontend APIs, and relevant script entrypoints/functions
- preserve subsystem grouping and section ordering already used in the document
- verify every documented signature against the source after editing

Return:
1. source files scanned
2. rows added or updated
3. signatures verified
4. any remaining ambiguity or follow-up needed
