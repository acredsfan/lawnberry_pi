### Summary
This PR implements and tests the following REST endpoints for LawnBerry Pi v2:
- GET /dashboard/telemetry
- GET/POST /map/zones
- GET/PUT /map/locations

All endpoints are contract-first and validated with passing tests. Tasks T043–T047 are marked complete in tasks.md. See AGENT_JOURNAL.md for details.

### Validation
- All new REST contract tests pass
- No ARM64-incompatible dependencies added
- Implementation matches OpenAPI contract and spec

### Next Steps
- Continue with remaining REST endpoints (T048–T057)
- Proceed to WebSocket endpoint and backend integration per tasks
- Update journal and tasks after each phase