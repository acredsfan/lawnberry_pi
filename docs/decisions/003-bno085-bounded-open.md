# LAWN-003: Bound IMU transport opens and recover cold-start misses

Recorded/reviewed: 2026-10-12.
Project/component scope: LawnBerry Pi / BNO085 UART/RVC initialization.
Status: accepted.
Supersedes: none.

## Decision or observed outcome

Verified correction contract: transport opens are bounded; an initial unavailable RVC frame can recover through throttled lazy reinitialization. A cold-start miss is not sufficient evidence to declare the sensor or UART mode permanently unusable.

## Reason and alternatives

Blocking opens can freeze initialization, while sensor settling can make the first frame unavailable. The correction bounds waiting and permits controlled recovery instead of an unbounded open, a forced yaw offset, or a blanket ban on one transport. The exact configured transport and hardware evidence still determine diagnosis.

## Evidence

- [IMU driver](../../backend/src/drivers/sensors/bno085_driver.py).
- [Regression specifications](../../tests/unit/test_bno085_rvc.py), `test_initialize_does_not_hang_when_opens_block` and `test_lazy_reinit_recovers_after_boot_miss`.
- [Correction commit](https://github.com/acredsfan/lawnberry_pi/commit/9c83ad8) (2026-07-23).
- [Motor/heading investigation guide](../motor-diagnostics.md).

## Environment and limitations

Source and mocked-test inspection only; these tests force driver paths with fake transports and do not prove physical BNO085/Pi wiring or timing. Current [specification](../../spec/hardware.yaml), ignored runtime config and fresh sensor evidence own interface/settings.

## Reconsideration

Revisit with a reproduced transport-specific failure tied to Pi/OS/firmware/wiring and freshness; preserve safe sensor ownership and avoid indiscriminate UART probing.
