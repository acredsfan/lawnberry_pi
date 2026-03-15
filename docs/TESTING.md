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
SIM_MODE=1 pytest -q
```

- Contract tests validate the FastAPI REST + WebSocket API.
- Integration tests include backups/migration and more.
- Placeholder integration tests (future work) are skipped by default.

## 1a) Simulation mode vs hardware mode

Use simulation mode for laptops, CI, and general backend development:

```bash
SIM_MODE=1 python -m uvicorn backend.src.main:app --host 0.0.0.0 --port 8081
```

Use hardware mode only when validating on the Raspberry Pi or attached bench hardware:

```bash
SIM_MODE=0 python -m uvicorn backend.src.main:app --host 0.0.0.0 --port 8081
```

Important behavior note:

- `SIM_MODE=1` is the pure simulation path
- `SIM_MODE=0` attempts real hardware initialization
- leaving `SIM_MODE` unset currently behaves like hardware mode because startup checks `os.getenv("SIM_MODE", "0")`

See `docs/simulation-vs-hardware-modes.md` for the full explanation.

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
SIM_MODE=0 uvicorn backend.src.main:app --host 0.0.0.0 --port 8081
# Then from another shell on the Pi:
curl http://localhost:8081/api/v2/system/selftest | jq
```

Enable the hardware self-test integration test:

```bash
RUN_HW_TESTS=1 pytest -q tests/integration/test_hardware_selftest.py
```

Notes:
- Use `SIM_MODE=0` for on-device hardware validation so the backend initializes real hardware paths instead of staying simulation-safe.
- Use `SIM_MODE=1` for local development and CI if you want to avoid hardware-init warnings entirely.
- The self-test is safe on systems without hardware: it catches missing devices and returns a report.
- For I2C/serial access, ensure the user is in groups `i2c` and `dialout`.

## 5) Troubleshooting

- Ensure you’re on Raspberry Pi OS (64-bit) Bookworm.
- Avoid non-ARM64 dependencies. If needed, propose a Pi-compatible alternative first.
- If placeholder tests fail intentionally, run them only when implementing the corresponding features.
