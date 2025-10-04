"""Minimal Extended Kalman Filter scaffolding (T049).

This lightweight EKF maintains a tiny state vector for planar navigation:
  state = [x, y, heading_deg]

It provides simple predict and measurement updates for GPS (x,y proxy) and
IMU yaw. This is SIM_MODE-safe and avoids heavy numerics; it is sufficient to
support a placeholder fused state endpoint and future tests. Real fusion will
replace the prediction and measurement models and handle lat/lon conversions.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Tuple
import math
import time


@dataclass
class FusedState:
    x: float
    y: float
    heading_deg: float
    timestamp_s: float
    quality: str = "unknown"
    sources: Tuple[str, ...] = ()


class SimpleEKF:
    """A tiny EKF-like scaffold for fused navigation state."""

    def __init__(self) -> None:
        self._x: float = 0.0
        self._y: float = 0.0
        self._heading_deg: float = 0.0
        self._last_ts: float = time.time()
        # Not implementing covariance for the scaffold; add later for real EKF

    def reset(self) -> None:
        self._x, self._y, self._heading_deg = 0.0, 0.0, 0.0
        self._last_ts = time.time()

    def predict(self, dt: float, v_mps: float = 0.0, omega_dps: float = 0.0) -> None:
        """Constant-velocity, constant-turn-rate motion model (scaffold)."""
        if dt <= 0:
            return
        heading_rad = math.radians(self._heading_deg)
        self._x += v_mps * math.cos(heading_rad) * dt
        self._y += v_mps * math.sin(heading_rad) * dt
        self._heading_deg = (self._heading_deg + omega_dps * dt) % 360.0

    def update_gps_xy(self, x: float, y: float, alpha: float = 0.5) -> None:
        """Blend GPS proxy position with simple exponential smoothing."""
        self._x = (1 - alpha) * self._x + alpha * x
        self._y = (1 - alpha) * self._y + alpha * y

    def update_heading(self, heading_deg: float, alpha: float = 0.5) -> None:
        # Blend heading taking wrap-around into account (simplified)
        diff = ((heading_deg - self._heading_deg + 540) % 360) - 180
        self._heading_deg = (self._heading_deg + alpha * diff) % 360

    def step(self, v_mps: float = 0.0, omega_dps: float = 0.0) -> FusedState:
        now = time.time()
        dt = now - self._last_ts
        self.predict(dt, v_mps=v_mps, omega_dps=omega_dps)
        self._last_ts = now
        return FusedState(self._x, self._y, self._heading_deg, now)

    def get_state(self) -> FusedState:
        return FusedState(self._x, self._y, self._heading_deg, time.time())


__all__ = ["SimpleEKF", "FusedState"]
