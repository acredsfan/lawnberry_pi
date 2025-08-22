# Dual VL53L0X Setup (0x29 and 0x30)

This guide documents the one-time address assignment and the ongoing “no-GPIO” policy for dual VL53L0X Time-of-Flight sensors on Raspberry Pi OS Bookworm.

Applies to: Raspberry Pi 4/5 aarch64, Python 3.11 venv in this repo, Adafruit Blinka drivers.

## Summary

- One-time assignment sets the right sensor to `0x30` and leaves the left at `0x29`.
- After assignment, the system enforces a "no-GPIO" startup: sensors are accessed directly at `0x29/0x30` without toggling XSHUT.
- The canonical script writes `data/tof_no_gpio.json` to persist the policy.

## Prerequisites

- Use the repo venv: `/home/pi/lawnberry/venv/bin/python` (Python 3.11)
- Required libs are already part of repo requirements: `board`, `busio`, `digitalio`, `adafruit_vl53l0x`.
- Ensure I2C is enabled and wiring for XSHUT is correct (defaults: left BCM22, right BCM23).

## Safe Procedure (timeouts enforced)

1) Stop the sensor service if it is running system-wide:

```bash
sudo systemctl stop lawnberry-sensor.service
```

2) Run the canonical assigner from the repo root using the venv (adds timeouts to avoid hangs):

```bash
timeout 90s venv/bin/python scripts/assign_vl53l0x_adafruit.py
```

Expected output includes:

```
Right sensor set to 0x30
I2C devices now: ['0x29', '0x30', ...]
Persisted flag: /home/pi/lawnberry/data/tof_no_gpio.json
SUCCESS: ToF sensors confirmed at 0x29 and 0x30.
```

3) Verify I2C bus shows both addresses:

```bash
timeout 15s i2cdetect -y 1
```

4) Restart the sensor service and confirm initialization without GPIO sequencing:

```bash
sudo systemctl restart lawnberry-sensor.service
timeout 25s journalctl -u lawnberry-sensor.service -n 80 --no-pager
```

Look for messages like:

```
ToF sensors initialized without GPIO sequencing
I2C device map: {'tof_left': '0x29', 'tof_right': '0x30', ...}
```

## Troubleshooting

- If the assigner fails to find a sensor, double-check XSHUT wiring and power. Try swapping which sensor boots first if your physical orientation differs.
- If Blinka imports fail, reinstall requirements into the venv:

```bash
timeout 60s venv/bin/python -m pip install -r requirements.txt
```

- If another process holds the I2C bus, stop related services (sensor, vision) first.

## Notes

- The no-GPIO policy avoids repeated XSHUT toggling which can lead to bus contention during normal operation. Only the assigner script touches GPIO.
- Pins and addresses are derived from `config/hardware.yaml` when available; defaults are BCM22 (left) and BCM23 (right).
