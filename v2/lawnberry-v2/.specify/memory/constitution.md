<!--
Sync Impact Report - LawnBerry Pi v2 Constitution v1.2.0
===============================================================
Version change: 1.1.0 → 1.2.0
Modified principles:
- AI Acceleration Hierarchy → AI Acceleration Hierarchy (official pycoral install guidance)
- Hardware Compliance → Hardware Compliance (INA3221 channel enforcement)
Added sections: None
Removed sections: None
Templates requiring updates:
✅ .specify/templates/plan-template.md
⚠️ docs/optional-hardware.md (create catalog for non-core peripherals)
Follow-up TODOs:
- TODO(DOCS_OPTIONAL_HARDWARE): Author docs/optional-hardware.md describing approved but non-core peripherals.
-->

# LawnBerry Pi v2 Constitution

## Core Principles

### I. Platform Exclusivity (NON-NEGOTIABLE)
Only Raspberry Pi OS Bookworm (64-bit) on Raspberry Pi 5 (8GB) or Pi 4B (2–8GB) may run LawnBerry Pi v2.
Python 3.11 is the sole runtime—no alternate interpreters, containers, or cross-platform wrappers.
Build scripts MUST assume on-device execution; desktop cross-compilation, Windows/macOS tooling, and x86-specific packages are forbidden.
**Rationale**: Singular platform focus delivers predictable performance, simplifies validation, and keeps support surface minimized.

### II. AI Acceleration Hierarchy
Inference engines MUST execute in the order Coral USB (isolated virtual environment) → Hailo AI Hat (single HAT) → CPU fallback (TFLite/OpenCV).
`pycoral` and `edgetpu` MUST remain banned from the primary uv environment; Coral assets live only inside the dedicated `venv-coral` runtime.
`pycoral` MUST NEVER be installed via `pip install pycoral`; that PyPI package targets reef mapping and is not the Google Coral accelerator runtime. Only follow the official Coral instructions at https://coral.ai/docs/accelerator/get-started/ using the Google-provided `python3-pycoral` packages or the upstream repository.
RoboHAT RP2040 fully occupies the 40-pin header; only one additional HAT (Hailo) may be attached. Coral accelerators MUST connect over USB.
Graceful degradation between tiers is mandatory. Failure to detect an accelerator MUST automatically fall back without manual toggles.
**Rationale**: Enforces deterministic packaging, prevents hat stacking conflicts, and keeps fallback behavior reliable in the field.

### III. Code Quality Gates (NON-NEGOTIABLE)
All merges require green `uv lock`, `ruff`, `black`, `mypy`, and `pytest` checks; local workflows MUST match CI configuration.
Repository layout MUST retain the `src/` packaging pattern. TODOs are only allowed as `TODO(v3): <issue-url>` entries tied to tracked work.
CI pipelines MUST fail on drift or lint violations; bypasses are not permitted without constitutional amendments.
**Rationale**: Sustains code health and enforces measurable quality discipline across contributors.

### IV. Documentation-as-Contract
`/spec/hardware.yaml` is the single source of truth for active hardware. Every PR MUST demonstrate alignment with that manifest.
Non-core or future hardware belongs in `docs/optional-hardware.md` only; it MUST NOT appear in code, manifests, or specs until promoted.
Each change that alters behavior, configuration, or hardware support MUST update `/docs` and `/spec` artifacts, and CI MUST block drift.
Agent rules (`/spec/agent_rules.md`) MUST be loaded for every task and PR and kept synchronized with the constitution.
**Rationale**: Treating documentation as law keeps implementation honest and stops divergence between intent and code.

### V. Runtime & Communications Standards
Process management MUST use systemd units; configuration MUST flow through `.env` (python-dotenv) with committed samples.
Camera pipelines MUST use Picamera2 + GStreamer. GPIO MUST use python-periphery + lgpio. Serial comms MUST use pyserial.
Operational networking assumes onboard Wi-Fi. Ethernet connectivity is for bench work only; runtime logic MUST NOT depend on wired links.
**Rationale**: Shared runtime contracts simplify deployments, reduce operational surprises, and respect mower field realities.

### VI. Hardware Compliance
Implementations MUST exactly match `/spec/hardware.yaml` definitions. Divergence requires updating the manifest first.
Navigation stack: primary GPS is SparkFun GPS-RTK-SMA (u-blox ZED-F9P) over USB with NTRIP corrections; backup GPS is u-blox Neo-8M on UART; IMU is BNO085 on UART4 (/dev/ttyAMA4).
Sensors MUST include VL53L0X left/right at I2C 0x29/0x30, BME280 at 0x76, SSD1306 OLED at 0x3C, and INA3221 at 0x40.
INA3221 channel assignments are immutable: Channel 1 = Battery, Channel 2 = Unused, Channel 3 = Solar Panel. Agents MUST reject any attempt to remap or repurpose these channels.
Drive and cutting systems MUST use Cytron MDDRC10 via RoboHAT RP2040 with hall encoders per wheel, and the blade MUST be driven through the IBT-4 H-Bridge on GPIO 24/25.
RoboHAT RP2040 occupies the 40-pin header—no additional GPIO HATs allowed. RC receiver support is FUTURE ONLY; document RoboHAT pin mappings but do not implement behavior.
**Rationale**: Strict hardware alignment prevents field regressions and keeps electronic interfaces safe and supportable.

### VII. Test-Driven Development
Work MUST follow TDD: author tests, observe failure, implement features, then achieve passing suites before merge.
Integration coverage MUST exercise hardware abstraction layers, acceleration tiers, and service-to-service interactions.
Contract and unit tests MUST accompany every measurable behavior. Skipped tests require documented constitutional justification.
**Rationale**: Complex mechatronics demand proactive verification to avoid costly on-device failures.

## Platform Constraints

**Hardware Requirements:**
- Raspberry Pi 5 (8 OR 16GB) primary, Raspberry Pi 4B (4–8GB) compatible
- RoboHAT RP2040 motor controller on GPIO
- Optional acceleration: Coral USB device OR single Hailo HAT (not both simultaneously)
- Sensors and actuators enumerated in `/spec/hardware.yaml`

**Software Stack:**
- OS: Raspberry Pi OS Bookworm (64-bit) ONLY
- Python: 3.11.x (no alternate runtimes)
- Package management: uv with committed `uv.lock`
- Forbidden packages (main env): `pycoral`, `edgetpu`

## Development Standards

**Quality Gates:**
- Pre-commit hooks MUST run ruff, black, and mypy
- CI/CD MUST execute full pytest suite plus documentation drift checks
- PR reviews MUST confirm compliance with `/spec/hardware.yaml` and `/spec/agent_rules.md`

**Repository Structure:**
- Source: `src/lawnberry/`
- Tests: `tests/` with `contract/`, `integration/`, and `unit/` subpackages
- Services: `systemd/` definitions
- Tooling & setup: `scripts/`

## Governance

This constitution overrides all other process documents. Code reviews MUST verify every principle and reject non-compliant changes.
Any requested deviation requires an issue, architectural discussion, and explicit constitutional amendment prior to implementation.
Hardware or spec changes MUST update `/spec/hardware.yaml` first, with supporting documentation in `/docs`.
Amendments follow semantic versioning: MAJOR for redefined principles, MINOR for new mandates or material expansions, PATCH for clarifications.

**Version**: 1.2.0 | **Ratified**: 2025-09-24 | **Last Amended**: 2025-09-24