#!/usr/bin/env python3
"""Replay a captured navigation telemetry stream offline.

Usage (single-path, existing behaviour):
    python scripts/replay_navigation.py <capture.jsonl> [--heading-tol 0.01]
                                        [--latlon-tol 1e-7]
                                        [--velocity-tol 0.001]
                                        [--verbose]

Usage (compare-run mode, §13 rollback strategy):
    python scripts/replay_navigation.py <capture.jsonl> --compare
                                        [--report-json <path>]
                                        [--heading-tol 0.01]
                                        [--latlon-tol 1e-7]
                                        [--velocity-tol 0.001]
                                        [--verbose]

compare-run replays the same JSONL fixture through both paths:
  - Legacy path:      NavigationService with LAWN_LEGACY_NAV=1
  - Refactored path:  NavigationService with LAWN_LEGACY_NAV=0 (default)

Per-step divergence in heading (degrees), position (lat/lon degrees), and
velocity (m/s) is reported.  Exit 0 when all steps are within tolerance,
exit 1 on divergence, exit 2 on missing fixture or parse error.

Reads a JSONL capture produced by TelemetryCapture.  Exits 0 on parity,
non-zero on any threshold breach.

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
import dataclasses
import json
import os
import sys
from pathlib import Path
from typing import Any

# Repo root on sys.path so we can import backend.src.* without installing.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# Default to SIM_MODE so the script never touches hardware.
os.environ.setdefault("SIM_MODE", "1")

from backend.src.diagnostics.replay import ReplayLoader  # noqa: E402
from backend.src.services.navigation_service import NavigationService  # noqa: E402


@dataclasses.dataclass
class StepDivergence:
    """Divergence between legacy and refactored paths at one replay step."""

    step: int
    field: str
    legacy_value: float | None
    refactored_value: float | None
    delta: float | None


@dataclasses.dataclass
class DivergenceReport:
    """Full compare-run output for one fixture file."""

    fixture: str
    steps: int
    divergences: list[StepDivergence]
    heading_tol: float
    latlon_tol: float
    velocity_tol: float

    @property
    def summary(self) -> str:
        if not self.divergences:
            return f"no divergence — {self.steps} steps identical within tolerances"
        return (
            f"{len(self.divergences)} divergence(s) across {self.steps} steps"
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "fixture": self.fixture,
            "steps": self.steps,
            "divergences": [dataclasses.asdict(d) for d in self.divergences],
            "summary": self.summary,
            "heading_tol": self.heading_tol,
            "latlon_tol": self.latlon_tol,
            "velocity_tol": self.velocity_tol,
        }


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
    p.add_argument(
        "--compare",
        action="store_true",
        help=(
            "compare-run mode (§13): replay fixture through both legacy "
            "(LAWN_LEGACY_NAV=1) and refactored (LAWN_LEGACY_NAV=0) paths "
            "and report per-step divergence"
        ),
    )
    p.add_argument(
        "--report-json",
        type=Path,
        default=None,
        metavar="PATH",
        help="write machine-readable divergence report as JSON to PATH (compare mode only)",
    )
    return p


async def _run_compare(args: argparse.Namespace) -> int:
    """Run both legacy and refactored paths against the same fixture.

    Returns 0 when all steps are within tolerance, 1 on divergence,
    2 on fixture-load error.
    """
    if not args.capture.exists():
        print(f"error: capture file not found: {args.capture}", file=sys.stderr)
        return 2

    print(
        f"compare-run: fixture={args.capture}\n"
        f"  tolerances: heading={args.heading_tol}° "
        f"latlon={args.latlon_tol:g} velocity={args.velocity_tol} m/s"
    )

    # Build two independent NavigationService instances.
    # Force the env var before construction so any __init__-time reads see it.
    os.environ["LAWN_LEGACY_NAV"] = "1"
    nav_legacy = NavigationService()
    os.environ["LAWN_LEGACY_NAV"] = "0"
    nav_refactored = NavigationService()
    # Restore to unset so the flag is read dynamically per-call.
    del os.environ["LAWN_LEGACY_NAV"]

    divergences: list[StepDivergence] = []
    step = 0

    # We must iterate the fixture twice (once per path) because NavigationService
    # is stateful — accumulated dead-reckoning, GPS COG history, waypoint index,
    # etc. would diverge if we interleaved steps.  Two passes on the same JSONL
    # file are cheap (≤5 MB for a yard run) and deterministic.
    legacy_states = []
    os.environ["LAWN_LEGACY_NAV"] = "1"
    for record in ReplayLoader(args.capture):
        state = await nav_legacy.update_navigation_state(record.sensor_data)
        legacy_states.append(state)
    del os.environ["LAWN_LEGACY_NAV"]

    refactored_states = []
    for record in ReplayLoader(args.capture):
        state = await nav_refactored.update_navigation_state(record.sensor_data)
        refactored_states.append(state)

    total_steps = len(legacy_states)
    if len(refactored_states) != total_steps:
        print(
            f"error: step count mismatch — legacy={total_steps} "
            f"refactored={len(refactored_states)}",
            file=sys.stderr,
        )
        return 2

    for step, (leg, ref) in enumerate(zip(legacy_states, refactored_states)):
        # Heading
        if leg.heading is not None and ref.heading is not None:
            d = abs(leg.heading - ref.heading)
            if d > args.heading_tol:
                divergences.append(
                    StepDivergence(
                        step=step,
                        field="heading",
                        legacy_value=leg.heading,
                        refactored_value=ref.heading,
                        delta=d,
                    )
                )
        elif leg.heading != ref.heading:
            divergences.append(
                StepDivergence(
                    step=step,
                    field="heading_nullness",
                    legacy_value=leg.heading,
                    refactored_value=ref.heading,
                    delta=None,
                )
            )

        # Position
        if leg.current_position is not None and ref.current_position is not None:
            dlat = abs(
                leg.current_position.latitude - ref.current_position.latitude
            )
            dlon = abs(
                leg.current_position.longitude - ref.current_position.longitude
            )
            if dlat > args.latlon_tol:
                divergences.append(
                    StepDivergence(
                        step=step,
                        field="latitude",
                        legacy_value=leg.current_position.latitude,
                        refactored_value=ref.current_position.latitude,
                        delta=dlat,
                    )
                )
            if dlon > args.latlon_tol:
                divergences.append(
                    StepDivergence(
                        step=step,
                        field="longitude",
                        legacy_value=leg.current_position.longitude,
                        refactored_value=ref.current_position.longitude,
                        delta=dlon,
                    )
                )
        elif (leg.current_position is None) != (ref.current_position is None):
            divergences.append(
                StepDivergence(
                    step=step,
                    field="position_nullness",
                    legacy_value=None,
                    refactored_value=None,
                    delta=None,
                )
            )

        # Velocity
        if leg.velocity is not None and ref.velocity is not None:
            d = abs(leg.velocity - ref.velocity)
            if d > args.velocity_tol:
                divergences.append(
                    StepDivergence(
                        step=step,
                        field="velocity",
                        legacy_value=leg.velocity,
                        refactored_value=ref.velocity,
                        delta=d,
                    )
                )
        elif (leg.velocity is None) != (ref.velocity is None):
            divergences.append(
                StepDivergence(
                    step=step,
                    field="velocity_nullness",
                    legacy_value=leg.velocity,
                    refactored_value=ref.velocity,
                    delta=None,
                )
            )

        if args.verbose:
            leg_pos = leg.current_position
            ref_pos = ref.current_position
            leg_pos_str = (
                f"({leg_pos.latitude:.7f},{leg_pos.longitude:.7f})" if leg_pos else "None"
            )
            ref_pos_str = (
                f"({ref_pos.latitude:.7f},{ref_pos.longitude:.7f})" if ref_pos else "None"
            )
            leg_hdg = f"{leg.heading:.2f}" if leg.heading is not None else "None"
            ref_hdg = f"{ref.heading:.2f}" if ref.heading is not None else "None"
            print(
                f"step {step}: legacy heading={leg_hdg} pos={leg_pos_str} | "
                f"refactored heading={ref_hdg} pos={ref_pos_str}"
            )

    report = DivergenceReport(
        fixture=str(args.capture),
        steps=total_steps,
        divergences=divergences,
        heading_tol=args.heading_tol,
        latlon_tol=args.latlon_tol,
        velocity_tol=args.velocity_tol,
    )

    print(f"compare-run complete: {total_steps} steps")
    print(report.summary)

    if divergences:
        print("\nDIVERGENCES (legacy vs. refactored):")
        for div in divergences:
            if div.delta is not None:
                print(
                    f"  step {div.step} {div.field}: "
                    f"legacy={div.legacy_value} refactored={div.refactored_value} "
                    f"delta={div.delta:.6g}"
                )
            else:
                print(
                    f"  step {div.step} {div.field}: "
                    f"legacy={div.legacy_value} refactored={div.refactored_value}"
                )

    if args.report_json is not None:
        args.report_json.write_text(
            json.dumps(report.to_dict(), indent=2), encoding="utf-8"
        )
        print(f"report written: {args.report_json}")

    return 1 if divergences else 0


async def _run(args: argparse.Namespace) -> int:
    if args.compare:
        return await _run_compare(args)

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
