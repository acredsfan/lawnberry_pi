# LAWN-002: Single runtime hardware configuration and honest qualification

Recorded/reviewed: 2026-10-12.
Project/component scope: LawnBerry Pi / hardware configuration, Pi compatibility and safety.
Status: accepted.
Supersedes: [LAWN-001 legacy overlay](001-legacy-hardware-overlay.md).

## Decision or observed outcome

Verified source correction: ignored `config/hardware.yaml` is the runtime hardware source; tracked specification/templates describe support and setup. Legacy overlays are migration input, not a second loaded configuration. Production targets Raspberry Pi Linux; desktop/CI simulation does not establish physical compatibility or mower readiness.

## Reason and alternatives

A single validated configuration prevents hidden precedence and stale wiring. Keeping safety enforced in the existing qualification/motor code avoids treating remembered approval, successful permits, mocks or replay as physical acceptance. Bench, simulation and supervised physical observations must be distinguished and bound to the actual build/configuration/firmware.

## Evidence

- [Hardware specification](../../spec/hardware.yaml), [Pi5 template](../../config/hardware.pi5.example.yaml) and [Pi4 template](../../config/hardware.pi4.example.yaml).
- [Loader](../../backend/src/core/config_loader.py) and [manager specifications](../../tests/unit/test_hardware_config_manager.py).
- [Qualification service](../../backend/src/services/autonomy_qualification_service.py) and [adversarial specifications](../../tests/unit/test_two_phase_qualification_adversarial.py).
- [Motor diagnostics](../motor-diagnostics.md), [operations](../OPERATIONS.md) and [simulation guide](../simulation-vs-hardware-modes.md).

## Environment and limitations

No hardware/bench/simulation test was run here. Bus/UART paths, limits and heading conversion remain in current configuration/code/docs, not copied constants. No permission to bypass interlocks, energize hardware or change user-owned settings is granted.

## Reconsideration

Revisit when supported Pi OS/hardware/wiring/schema changes; require migration tests and current physical qualification for safety-critical changes.
