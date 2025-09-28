"""Hardware self-test utilities for on-device validation.

Designed to be safe on CI and devices without hardware enabled:
- Imports optional deps (smbus2, pyserial) lazily inside functions
- Catches permission and missing-device errors
- Returns a structured report instead of raising
"""

from __future__ import annotations

import os
import time
import json
import grp
from typing import Dict, Any, List


EXPECTED_I2C = {
    "bme280": [0x76, 0x77],
    "ina3221": [0x40, 0x41],
    "vl53l0x": [0x29, 0x30],
}

SERIAL_CANDIDATES = [
    "/dev/ttyUSB0",
    "/dev/ttyAMA0",
    "/dev/ttyS0",
    "/dev/serial0",
]


def _group_names() -> List[str]:
    try:
        gids = os.getgroups()
        names = []
        for g in gids:
            try:
                names.append(grp.getgrgid(g).gr_name)
            except KeyError:
                continue
        return names
    except Exception:
        return []


def i2c_probe(bus_num: int = 1) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "available": False,
        "bus": f"/dev/i2c-{bus_num}",
        "error": None,
        "present": {},
    }
    dev_path = f"/dev/i2c-{bus_num}"
    if not os.path.exists(dev_path):
        report["error"] = f"missing {dev_path}"
        return report

    try:
        from smbus2 import SMBus  # type: ignore
    except Exception as e:  # ImportError or others
        report["error"] = f"smbus2 unavailable: {e}"
        return report

    try:
        with SMBus(bus_num) as bus:
            report["available"] = True
            # Probe only expected addresses to keep it fast/safe
            present: Dict[str, List[str]] = {}
            for name, addrs in EXPECTED_I2C.items():
                found: List[str] = []
                for addr in addrs:
                    try:
                        # Use read_byte to probe; many devices NACK -> catch
                        bus.read_byte(addr)
                        found.append(hex(addr))
                    except Exception:
                        # Not present or no permission
                        continue
                if found:
                    present[name] = found
            report["present"] = present
    except Exception as e:
        report["error"] = str(e)

    return report


def serial_probe(paths: List[str] | None = None) -> Dict[str, Any]:
    report: Dict[str, Any] = {
        "available": False,
        "candidates": [],
        "opened": None,
        "error": None,
    }
    paths = paths or SERIAL_CANDIDATES
    existing = [p for p in paths if os.path.exists(p)]
    report["candidates"] = existing
    if not existing:
        return report

    try:
        import serial  # type: ignore
    except Exception as e:
        report["error"] = f"pyserial unavailable: {e}"
        return report

    for dev in existing:
        try:
            with serial.Serial(dev, baudrate=9600, timeout=0.2) as ser:  # type: ignore
                # Non-blocking peek
                try:
                    ser.reset_input_buffer()
                except Exception:
                    pass
                _ = ser.read(16)
                report["available"] = True
                report["opened"] = dev
                break
        except Exception:
            continue
    return report


def run_selftest() -> Dict[str, Any]:
    groups = _group_names()
    i2c = i2c_probe(bus_num=1)
    serial = serial_probe()
    summary = {
        "i2c_bus_present": i2c.get("available", False),
        "bme280_present": bool(i2c.get("present", {}).get("bme280")),
        "ina3221_present": bool(i2c.get("present", {}).get("ina3221")),
        "vl53l0x_present": bool(i2c.get("present", {}).get("vl53l0x")),
        "serial_port_present": bool(serial.get("candidates")),
        "serial_open_ok": bool(serial.get("opened")),
        "groups": groups,
        "needs_i2c_group": ("i2c" not in groups),
        "needs_dialout_group": ("dialout" not in groups),
    }
    overall_ok = (
        summary["i2c_bus_present"]
        and (summary["bme280_present"] or summary["ina3221_present"] or summary["vl53l0x_present"])  # noqa: E501
    ) or summary["serial_open_ok"]

    return {
        "i2c": i2c,
        "serial": serial,
        "summary": {
            **summary,
            "overall_ok": overall_ok,
        },
    }
