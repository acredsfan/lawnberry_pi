from __future__ import annotations

from backend.src.nav.odometry import WheelParams, integrate_from_ticks, integrate_velocity


def test_integrate_from_ticks_symmetrical_wheels_moves_forward():
    params = WheelParams(wheel_radius_m=0.05, wheel_base_m=0.3, ticks_per_rev=1000)
    dist, dhead = integrate_from_ticks(500, 500, params)
    assert dist > 0
    assert abs(dhead) < 1e-6


def test_integrate_from_ticks_turn_in_place():
    params = WheelParams(wheel_radius_m=0.05, wheel_base_m=0.3, ticks_per_rev=1000)
    dist, dhead = integrate_from_ticks(-250, 250, params)
    assert abs(dist) < 1e-6
    assert dhead != 0.0


def test_integrate_velocity_linear_and_angular():
    dist, dhead = integrate_velocity(0.5, 10.0, 2.0)
    assert dist == 1.0
    assert dhead == 20.0
