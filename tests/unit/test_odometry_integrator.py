"""Unit tests for OdometryIntegrator."""
from __future__ import annotations

import pytest
from backend.src.nav.odometry import OdometryIntegrator, WheelParams


@pytest.fixture
def integrator() -> OdometryIntegrator:
    # Small wheel for convenient round numbers:
    # radius=0.05 m, base=0.30 m, 1024 ticks/rev
    return OdometryIntegrator(WheelParams(wheel_radius_m=0.05, wheel_base_m=0.30, ticks_per_rev=1024))


def test_first_call_returns_zero(integrator: OdometryIntegrator):
    dist, dhdg = integrator.step_ticks(0, 0)
    assert dist == 0.0
    assert dhdg == 0.0


def test_first_call_nonzero_ticks_still_zero(integrator: OdometryIntegrator):
    """Absolute counters on first call set reference; no odometry yet."""
    dist, dhdg = integrator.step_ticks(1000, 1000)
    assert dist == 0.0 and dhdg == 0.0


def test_straight_movement(integrator: OdometryIntegrator):
    integrator.step_ticks(0, 0)  # set reference
    # One full revolution each wheel = 2π × 0.05 m ≈ 0.3142 m
    dist, dhdg = integrator.step_ticks(1024, 1024)
    import math
    expected = 2 * math.pi * 0.05
    assert abs(dist - expected) < 1e-6
    assert abs(dhdg) < 1e-6  # straight, no rotation


def test_left_turn_negative_heading_delta(integrator: OdometryIntegrator):
    """Right wheel faster than left → CW → positive delta_heading_deg."""
    integrator.step_ticks(0, 0)
    dist, dhdg = integrator.step_ticks(0, 512)  # right only
    assert dhdg > 0  # CW turn


def test_velocity_fallback_nonzero(integrator: OdometryIntegrator):
    dist, dhdg = integrator.step_velocity(0.5, 10.0, 1.0)
    assert dist == pytest.approx(0.5)
    assert dhdg == pytest.approx(10.0)


def test_velocity_fallback_zero_time(integrator: OdometryIntegrator):
    dist, dhdg = integrator.step_velocity(0.5, 10.0, 0.0)
    assert dist == 0.0 and dhdg == 0.0


def test_velocity_fallback_never_constant():
    """The dead-reckoning fallback must scale with velocity and time, never fixed."""
    oi = OdometryIntegrator()
    d1, _ = oi.step_velocity(1.0, 0.0, 0.5)
    d2, _ = oi.step_velocity(0.5, 0.0, 0.5)
    assert d1 != d2  # different velocity → different distance


def test_reset_clears_tick_state(integrator: OdometryIntegrator):
    integrator.step_ticks(100, 100)
    integrator.reset_ticks()
    # After reset, next call is a new reference → distance = 0
    dist, _ = integrator.step_ticks(200, 200)
    assert dist == 0.0
