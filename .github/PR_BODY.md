### Summary
This PR implements and tests the following REST endpoints for LawnBerry Pi v2:
- GET /dashboard/telemetry
- GET/POST /map/zones
- GET/PUT /map/locations

All endpoints are contract-first and validated with passing tests. Tasks T043–T047 are marked complete in tasks.md. See `.specify/memory/AGENT_JOURNAL.md` for details.

### Validation
- Targeted REST contract tests pass for implemented endpoints
- No ARM64-incompatible dependencies added
- Implementation matches project spec and contracts

### Next Steps
- Implement control endpoints (T048–T050), planning/jobs (T051–T053), AI/data/settings (T054–T057)
- Add WebSocket endpoint (T058) and app entrypoint (T059)
- Backend integration tasks T060–T064
