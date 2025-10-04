from __future__ import annotations

import asyncio
import os
from typing import Any

try:
    import typer  # type: ignore
    _HAS_TYPER = True
except Exception:  # keep CLI optional in tests
    typer = None  # type: ignore
    _HAS_TYPER = False


async def _collect_snapshot() -> dict[str, Any]:
    # For now, pull from debug overrides and health endpoint patterns
    # In future, integrate with SensorManager.
    from ..api.rest import _debug_overrides
    snapshot = {
        "tof_left": {
            "value": _debug_overrides.get("tof_left_distance_m"),
            "unit": "m",
            "status": "ok",
        },
        "tof_right": {
            "value": _debug_overrides.get("tof_right_distance_m"),
            "unit": "m",
            "status": "ok",
        },
        "imu_roll": {
            "value": _debug_overrides.get("imu_roll_deg"),
            "unit": "deg",
            "status": "ok",
        },
        "imu_pitch": {
            "value": _debug_overrides.get("imu_pitch_deg"),
            "unit": "deg",
            "status": "ok",
        },
    }
    return snapshot


def _format_table(snapshot: dict[str, Any]) -> str:
    lines = ["SENSOR            VALUE     UNIT   STATUS"]
    for name, entry in snapshot.items():
        val = entry.get("value")
        unit = entry.get("unit", "")
        status = entry.get("status", "unknown")
        lines.append(f"{name:<16} {str(val):<8} {unit:<5} {status}")
    return "\n".join(lines)


async def sensors_live_loop(interval_s: float = 1.0) -> None:
    try:
        while True:
            snap = await _collect_snapshot()
            table = _format_table(snap)
            os.system("clear")
            print(table)
            await asyncio.sleep(interval_s)
    except KeyboardInterrupt:
        return


if _HAS_TYPER:
    @typer.command()
    def test(live: bool = True):
        """Run sensor diagnostics live table (1 Hz)."""
        if live:
            asyncio.run(sensors_live_loop())
        else:
            snap = asyncio.run(_collect_snapshot())
            print(_format_table(snap))
