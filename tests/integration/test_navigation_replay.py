"""Replay-parity integration test.

Loads the committed golden fixture, replays each captured SensorData through a
fresh NavigationService, and asserts the produced state matches the recorded
state within tolerances. A failure here means navigation behavior has drifted
from the fixture — either an intentional change (regenerate the fixture) or a
regression (fix the code).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from backend.src.diagnostics.replay import ReplayLoader
from backend.src.services.navigation_service import NavigationService

FIXTURE = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "navigation"
    / "synthetic_straight_drive.jsonl"
)

HEADING_TOL_DEG = 0.01
LATLON_TOL = 1e-7
VELOCITY_TOL_MPS = 0.001


@pytest.mark.asyncio
async def test_synthetic_straight_drive_replays_with_parity():
    assert FIXTURE.exists(), f"missing golden fixture: {FIXTURE}"
    nav = NavigationService()

    deltas: list[str] = []
    step = 0
    for record in ReplayLoader(FIXTURE):
        result = await nav.update_navigation_state(record.sensor_data)
        expected = record.navigation_state_after

        if expected.heading is not None and result.heading is not None:
            d = abs(result.heading - expected.heading)
            if d > HEADING_TOL_DEG:
                deltas.append(
                    f"step {step} heading: got {result.heading:.6f}, "
                    f"expected {expected.heading:.6f}, delta={d:.6f}"
                )
        elif expected.heading != result.heading:
            deltas.append(
                f"step {step} heading nullness: got {result.heading}, "
                f"expected {expected.heading}"
            )

        if expected.current_position is not None and result.current_position is not None:
            dlat = abs(result.current_position.latitude - expected.current_position.latitude)
            dlon = abs(result.current_position.longitude - expected.current_position.longitude)
            if dlat > LATLON_TOL or dlon > LATLON_TOL:
                deltas.append(
                    f"step {step} position: got "
                    f"({result.current_position.latitude},{result.current_position.longitude}), "
                    f"expected "
                    f"({expected.current_position.latitude},{expected.current_position.longitude})"
                )
        elif (expected.current_position is None) != (result.current_position is None):
            deltas.append(
                f"step {step} position nullness mismatch: "
                f"got {result.current_position}, expected {expected.current_position}"
            )

        if expected.velocity is not None and result.velocity is not None:
            d = abs(result.velocity - expected.velocity)
            if d > VELOCITY_TOL_MPS:
                deltas.append(
                    f"step {step} velocity: got {result.velocity:.6f}, "
                    f"expected {expected.velocity:.6f}"
                )

        step += 1

    assert step == 5, f"expected 5 fixture records, got {step}"
    assert not deltas, "Replay parity broke:\n" + "\n".join(deltas)
