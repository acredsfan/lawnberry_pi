# LawnBerry Pi project state

Reviewed: 2026-10-12. Scope: Git-tracked source/document inspection at `035ffa036c53f74187fa1f75d1decfd76adabcaf`; this is a snapshot, not a live monitor.

## Verified source state

- [Supported hardware specification](../spec/hardware.yaml), Pi example templates and the loader define supported/runtime configuration.
- Current loader rejects legacy hardware overlays in hardware mode; simulation can tolerate absent user-owned hardware configuration.
- Safety qualification and motor authorization remain implemented in code/config/tests; neither a memory entry nor an API response is physical qualification.
- Historical [.specify journal](../.specify/memory/AGENT_JOURNAL.md) is retained as dated evidence, not a current run log or configuration source.

## Unresolved and next action

Live Pi access was unavailable during inventory; no service, sensor or motor was controlled. Hypothesis (uncertain): the deployed mower matches this Git baseline. That hypothesis is not supported by current evidence and cannot authorize motion or blade use. Bench/simulation evidence must not be promoted to physical acceptance.

Recommendation: verify the deployed commit, ignored hardware configuration, firmware and current physical evidence with the existing operator/qualification workflow before any hardware claim.

## Recovery sources

- [Developer re-entry guide](developer-toolkit.md)
- [Operations](OPERATIONS.md)
- [Simulation/hardware boundaries](simulation-vs-hardware-modes.md)
- [Hardware integration](hardware-integration.md)
Start with [decisions and lessons](decisions/README.md). Verify the relevant source and fresh status before acting. Update this snapshot when material status changes; preserve durable reasoning in decision records.

No application, deployment, bench or hardware tests were run for this documentation change. Linked tests establish source contracts, not a new execution pass.
