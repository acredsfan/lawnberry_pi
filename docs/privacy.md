# Privacy and Logging Policy

This document describes how LawnBerry Pi v2 handles user and system data with a privacy-first mindset.

- Logging is structured (JSON by default) and privacy-filtered. Sensitive fields such as tokens, credentials, passwords, and API keys are redacted as `[REDACTED]` both when present in log messages and when attached via `extra` fields.
- Log rotation is enabled by default with size limits and backups to prevent long-term data accumulation.
- Network integrations (e.g., weather providers) are disabled by default and require explicit configuration. The system operates offline without transmitting data externally.
- Hardware telemetry can be enabled in non-simulation mode. When enabled, only the minimum necessary technical data is stored for diagnostics and performance.
- Audit logs record control actions and configuration changes but avoid storing secrets.
- Developers and operators should avoid logging personal identifiable information (PII). Use structured logs and rely on the privacy filter.

For more details, see `backend/src/core/observability.py` and `backend/src/core/logging.py`.