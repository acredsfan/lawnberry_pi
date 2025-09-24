<!--
Sync Impact Report - LawnBerry Pi v2 Constitution v1.0.0
===============================================================
Version change: NEW → 1.0.0 (initial constitution creation)
Modified principles: N/A (new constitution)
Added sections: 
- Core Principles (7 principles covering platform, AI acceleration, code quality, documentation, runtime, hardware compliance, development workflow)
- Platform Constraints (hardware and software requirements)
- Development Standards (quality gates and standards)
Templates requiring updates:
✅ plan-template.md - already aligned with constitution check section
✅ spec-template.md - requirement standards compatible
✅ tasks-template.md - TDD approach aligns with Code Quality principle
✅ agent-file-template.md - no conflicts with new constitution
Follow-up TODOs: None - all placeholders filled
-->

# LawnBerry Pi v2 Constitution

## Core Principles

### I. Platform Exclusivity (NON-NEGOTIABLE)
Target ONLY Raspberry Pi OS Bookworm (ARM64) with Python 3.11. Pi 5 is primary target, Pi 4B compatible.
NO Windows/macOS packages, cross-platform abstractions, or compatibility layers.
Platform constraints ensure reliability, optimize for ARM64 performance, and eliminate cross-platform complexity.
**Rationale**: Focus resources on single platform excellence rather than diluted multi-platform support.

### II. AI Acceleration Hierarchy
AI acceleration MUST follow strict priority: Coral TPU (isolated venv) → Hailo AI Hat (optional) → CPU fallback (TFLite/OpenCV).
BAN `pycoral`/`edgetpu` packages in main environment - Coral uses dedicated isolated virtual environment only.
Each acceleration method runs independently with graceful degradation to next tier.
**Rationale**: Prevents package conflicts while ensuring AI capabilities across hardware configurations.

### III. Code Quality Gates (NON-NEGOTIABLE)
All code MUST pass: uv lock (dependency management), ruff (linting), black (formatting), mypy (type checking), pytest (testing).
Source code MUST use `src/` layout pattern. NO unlinked TODOs - use `TODO(v3):` with GitHub issue links only.
Quality gates run in CI/CD and block merges on failures.
**Rationale**: Maintains codebase health, prevents technical debt, ensures type safety and consistency.

### IV. Documentation-as-Contract
ANY code change MUST update `/docs` and `/spec` directories. CI MUST fail on documentation drift.
Specifications in `/spec/hardware.yaml` and `/spec/agent_rules.md` MUST be loaded for every task and PR.
Documentation changes are not optional addenda but mandatory contract updates.
**Rationale**: Prevents documentation rot, ensures specifications drive development decisions.

### V. Runtime Standards
Use systemd service units for process management. Environment configuration via `.env` files loaded through python-dotenv.
Camera operations via Picamera2 + GStreamer. GPIO access via python-periphery + lgpio. Serial communication via pyserial.
NO alternative runtime patterns - consistency enables reliable deployment and debugging.
**Rationale**: Standardized runtime reduces operational complexity and improves system reliability.

### VI. Hardware Compliance
ALL implementations MUST verify compatibility with `/spec/hardware.yaml` specifications.
Support sensor configurations: BNO085 IMU, INA3221 power monitoring, VL53L0X ToF, hall effect encoders.
Motor control via Cytron MDDRC10 through RoboHAT RP2040 bridge. Picamera2 for vision processing.
**Rationale**: Ensures software-hardware integration reliability across supported hardware configurations.

### VII. Test-Driven Development
TDD mandatory: Write tests → Validate requirements → Tests fail → Implement → Tests pass.
Integration tests required for hardware interfaces, AI acceleration tiers, and inter-service communication.
Contract tests validate API boundaries. Unit tests verify isolated component behavior.
**Rationale**: Hardware integration complexity requires comprehensive testing to prevent field failures.

## Platform Constraints

**Hardware Requirements:**
- Raspberry Pi 5 (8GB) primary, Pi 4B (2-8GB) compatible
- Optional: USB Coral TPU, Hailo AI Hat
- Required sensors per `/spec/hardware.yaml`

**Software Stack:**
- OS: Raspberry Pi OS Bookworm (64-bit) ONLY
- Python: 3.11.x (no version drift)
- Package management: uv with lockfile discipline
- Forbidden packages: pycoral, edgetpu (in main environment)

## Development Standards

**Quality Gates:**
- Pre-commit: ruff, black, mypy checks
- CI/CD: pytest suite, documentation sync validation
- PR requirements: `/spec/hardware.yaml` and `/spec/agent_rules.md` compliance verification

**Repository Structure:**
- Source: `src/lawnberry/` package layout
- Tests: `tests/` with contract/integration/unit subdivision
- Services: `systemd/` for service definitions
- Scripts: `scripts/` for environment setup

## Governance

Constitution supersedes all other development practices. All PRs and code reviews MUST verify constitutional compliance.
Principle violations require explicit justification in PR descriptions with complexity tracking documentation.
Hardware and specification files (`/spec/hardware.yaml`, `/spec/agent_rules.md`) are loaded for every development task.

Amendment process: Major changes require issue discussion, minor changes for clarifications only.
Version increments follow semantic versioning: MAJOR (principle changes), MINOR (additions), PATCH (clarifications).

**Version**: 1.0.0 | **Ratified**: 2025-09-24 | **Last Amended**: 2025-09-24