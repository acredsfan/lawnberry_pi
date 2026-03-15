---
name: "Review Hardware Safety"
description: "Review a LawnBerry Pi hardware-sensitive change or control path for fail-safe behavior using the Hardware Safety Reviewer agent."
argument-hint: "What hardware-sensitive change, path, or proposal should be reviewed?"
agent: "Hardware Safety Reviewer"
---
Use [docs/developer-toolkit.md](../../docs/developer-toolkit.md), `docs/constitution.md`, and `spec/hardware.yaml` before making conclusions.

User input:

$ARGUMENTS

Review only the specified hardware-sensitive path and stay review-first unless the user explicitly asks for implementation work.

Focus on:
- motor, blade, RoboHAT, watchdog, E-stop, and startup sequencing implications
- simulation-vs-hardware boundaries and accidental hardware activation risks
- fail-safe behavior, interlocks, authorization, and ownership assumptions
- concrete unsafe defaults, missing checks, or ambiguous control flow

Return:
1. risk summary
2. files and safety paths reviewed
3. specific failure modes or missing protections
4. recommended safe next steps or validation
