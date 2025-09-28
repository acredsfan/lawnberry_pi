# Research Notes — LawnBerry Pi v2 Complete Rebuild

## Decisions & Open Items

- MFA specifics: Use TOTP (RFC 6238), 6-digit, 30s window; 10 one-time backup codes.
- ACME HTTP-01: Use port 80 challenge with automatic renewal; document router/NAT requirements and fail-closed behavior.
- Map cost controls: Adaptive tile throttling and update frequency; threshold triggers automatic OSM fallback; expose setting in Settings page.
- Dead reckoning: Reduced speed cap (e.g., 30% of normal), stricter obstacle thresholds; 2-minute max grace period.
- Camera service ownership: Single owner process publishes frames via IPC; other consumers subscribe; no direct device access.

## Alternatives Considered

- ACME DNS-01: More resilient behind NAT, but requires DNS API creds; out of scope for default path.
- Password-only auth: Rejected due to remote access threat model; MFA mandated.
- Persistent dead reckoning: Rejected; bounded grace period improves safety.

## References

- Constitution v1.4.0 (package isolation, resource coordination, TDD)
- Spec FR-010, FR-018, FR-027, FR-028; Clarifications (2025-09-27)
