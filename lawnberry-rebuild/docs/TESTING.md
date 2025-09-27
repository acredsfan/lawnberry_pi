# Testing Guide (ARM64/Raspberry Pi OS Bookworm)

This project prioritizes TDD and ARM64 compatibility. Below are the common workflows to run tests locally on a Raspberry Pi.

## 1) Python backend tests

Create a virtual environment and install dependencies:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -e .
```

Run the full test suite:

```bash
pytest -q
```

- Contract tests validate the FastAPI REST + WebSocket API.
- Integration tests include backups/migration and more.
- Placeholder integration tests (future work) are skipped by default.

Run placeholder integration tests explicitly:

```bash
RUN_PLACEHOLDER_INTEGRATION=1 pytest -q tests/integration
```

## 2) Frontend tests and lint (optional)

From `frontend/`:

```bash
npm ci
npm run lint
npm run test
npm run build
```

All frontend dependencies are compatible with ARM64.

## 3) Docs drift guard

CI will fail if code changes without corresponding documentation or journal updates. You can run the check locally:

```bash
bash scripts/check_docs_drift.sh
```

Update one of the following to satisfy the guard:
- `docs/**`
- `spec/**`
- `README.md`
- `.specify/memory/AGENT_JOURNAL.md`

## 4) On-device hardware testing (RPi)

Run the backend and call the hardware self-test endpoint:

```bash
uvicorn backend.src.main:app --host 0.0.0.0 --port 8001
# Then from another shell on the Pi:
curl http://localhost:8001/api/v2/system/selftest | jq
```

Enable the hardware self-test integration test:

```bash
RUN_HW_TESTS=1 pytest -q tests/integration/test_hardware_selftest.py
```

Notes:
- The self-test is safe on systems without hardware: it catches missing devices and returns a report.
- For I2C/serial access, ensure the user is in groups `i2c` and `dialout`.

## 5) Troubleshooting

- Ensure you’re on Raspberry Pi OS (64-bit) Bookworm.
- Avoid non-ARM64 dependencies. If needed, propose a Pi-compatible alternative first.
- If placeholder tests fail intentionally, run them only when implementing the corresponding features.
