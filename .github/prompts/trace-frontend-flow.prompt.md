---
name: "Trace Frontend Flow"
description: "Trace or repair a LawnBerry Pi frontend state, API, or WebSocket flow using the Frontend Flow Specialist agent."
argument-hint: "What frontend flow should be traced or fixed?"
agent: "Frontend Flow Specialist"
---
Use [docs/developer-toolkit.md](../../docs/developer-toolkit.md) before tracing the requested flow.

User input:

$ARGUMENTS

Trace the specified UI action or stateful frontend path end-to-end across views, stores, services, composables, and backend contracts.

Behavior:
- keep the work read-only unless the user clearly asks for a fix
- verify request and event shapes against real backend contracts before blaming either side
- treat auth, reconnect, control-lockout, and stale-state side effects as part of the same flow
- if a fix is requested, implement the smallest reliable change and run targeted validation

Return:
1. flow traced end-to-end
2. files reviewed or changed
3. mismatch, bug, or root cause found
4. validation performed or recommended next steps
