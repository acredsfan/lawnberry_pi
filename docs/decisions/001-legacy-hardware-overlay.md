# LAWN-001: Legacy hardware overlay is historical migration input

Recorded/reviewed: 2026-10-12.
Project/component scope: LawnBerry Pi / hardware configuration.
Status: superseded.
Supersedes: none (historical mechanism; replacement is LAWN-002).

## Decision or observed outcome

Historical observed mechanism: `hardware.local.yaml` existed as an overlay/migration source. It is no longer a runtime overlay. This record does not assert that every historical deployment used it or that an owner formally approved it.

## Reason and alternatives

The current loader explicitly detects legacy input and directs migration. Continuing to rely on a remembered overlay silently separates expected wiring from effective runtime settings. Use [LAWN-002](002-single-hardware-config-and-safety-evidence.md) for the accepted current correction.

## Evidence

- [Loader legacy detection](../../backend/src/core/config_loader.py), `_load_hardware_raw`.
- [Migration/ensure/validate helper](../../scripts/manage_hardware_config.py).
- [Migration regression specifications](../../tests/unit/test_hardware_config_manager.py).
- [Simulation/hardware guide](../simulation-vs-hardware-modes.md).

## Environment and limitations

Source inspection only. Historical configuration values and user-owned files are not included. Superseded by [LAWN-002](002-single-hardware-config-and-safety-evidence.md); do not restore old overlay loading based on this note.

## Reconsideration

Reconsider only after an explicit reviewed configuration architecture change with precedence, migration and safety acceptance.
