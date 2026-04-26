#!/usr/bin/env python3
"""Replay a captured navigation telemetry stream offline.

Usage:
    python scripts/replay_navigation.py <capture.jsonl> [--heading-tol 0.01]
                                        [--latlon-tol 1e-7]
                                        [--velocity-tol 0.001]
                                        [--verbose]

Reads a JSONL capture produced by TelemetryCapture, replays each captured
SensorData through a fresh NavigationService (in SIM_MODE), and reports
per-step deltas vs. the recorded ground truth. Exits 0 on parity, non-zero
on any threshold breach.

Default tolerances are non-zero (heading 0.01 deg, lat/lon 1e-7, velocity
0.001 m/s) because the CLI is for ad-hoc debugging where the captured
fixture may have been produced by a previous version of the code with
expected drift. For an exact-match parity check (e.g., the synthetic
golden fixture's pytest target), pass --heading-tol 0 --latlon-tol 0
--velocity-tol 0.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Repo root on sys.path so we can import backend.src.* without installing.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Default to SIM_MODE so the script never touches hardware.
os.environ.setdefault("SIM_MODE", "1")

from backend.src.diagnostics.replay import ReplayLoader  # noqa: E402
from backend.src.services.navigation_service import NavigationService  # noqa: E402


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="replay_navigation",
        description="Replay a captured navigation telemetry stream offline.",
    )
    p.add_argument("capture", type=Path, help="path to captured JSONL file")
    p.add_argument("--heading-tol", type=float, default=0.01, help="degrees")
    p.add_argument("--latlon-tol", type=float, default=1e-7, help="degrees")
    p.add_argument("--velocity-tol", type=float, default=0.001, help="m/s")
    p.add_argument(
        "-v", "--verbose", action="store_true",
        help="print one line per replay step (default: summary + deltas only)",
    )
    return p


async def _run(args: argparse.Namespace) -> int:
    if not args.capture.exists():
        print(f"error: capture file not found: {args.capture}", file=sys.stderr)
        return 2

    print(
        f"replay tolerances: heading={args.heading_tol}° "
        f"latlon={args.latlon_tol:g} velocity={args.velocity_tol} m/s"
    )
    nav = NavigationService()
    deltas: list[str] = []
    step = 0
    for record in ReplayLoader(args.capture):
        result = await nav.update_navigation_state(record.sensor_data)
        expected = record.navigation_state_after

        if expected.heading is not None and result.heading is not None:
            d = abs(result.heading - expected.heading)
            if d > args.heading_tol:
                deltas.append(
                    f"step {step} heading: got {result.heading:.6f} "
                    f"expected {expected.heading:.6f} delta={d:.6f}"
                )

        if expected.current_position and result.current_position:
            dlat = abs(
                result.current_position.latitude - expected.current_position.latitude
            )
            dlon = abs(
                result.current_position.longitude - expected.current_position.longitude
            )
            if dlat > args.latlon_tol or dlon > args.latlon_tol:
                deltas.append(
                    f"step {step} position: dlat={dlat:.2e} dlon={dlon:.2e}"
                )

        if expected.velocity is not None and result.velocity is not None:
            d = abs(result.velocity - expected.velocity)
            if d > args.velocity_tol:
                deltas.append(
                    f"step {step} velocity: got {result.velocity:.6f} "
                    f"expected {expected.velocity:.6f}"
                )

        if args.verbose:
            pos = result.current_position
            pos_str = (
                f"({pos.latitude:.7f},{pos.longitude:.7f})" if pos else "None"
            )
            hdg_str = (
                f"{result.heading:.2f}" if result.heading is not None else "None"
            )
            print(f"step {step}: heading={hdg_str} pos={pos_str}")
        step += 1

    print(f"replay complete: {step} steps")
    if deltas:
        print("DELTAS:")
        for d in deltas:
            print(f"  {d}")
        return 1
    print("OK — replay parity within tolerances")
    return 0


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return asyncio.run(_run(args))


if __name__ == "__main__":
    sys.exit(main())
