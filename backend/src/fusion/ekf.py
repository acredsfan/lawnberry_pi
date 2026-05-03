"""Real PoseFilter: 5-state EKF for planar robot navigation.

State vector: [x_m, y_m, heading_deg, v_mps, omega_dps]

Measurement models
------------------
GPS position:  z = [x_m, y_m]         H = [[1,0,0,0,0],[0,1,0,0,0]]
IMU heading:   z = [heading_deg]       H = [[0,0,1,0,0]]

Motion model (CTRA — constant turn rate and velocity)
-----------------------------------------------------
  heading += omega_dps * dt
  x       += v_mps * cos(heading_rad) * dt
  y       += v_mps * sin(heading_rad) * dt
  v_mps   unchanged (zero acceleration assumption)
  omega_dps unchanged (zero angular-accel assumption)

v_mps and omega_dps are updated by measurement calls (encoder odometry /
IMU angular rate) before predict, not inside the predict Jacobian.

Units: metres, degrees, m/s, deg/s throughout. numpy is used for the
covariance matrix only; scalar state is kept as plain floats.

Innovation gating
-----------------
A measurement is rejected (not applied) when its Mahalanobis distance
exceeds the configured threshold. This prevents GPS jumps from corrupting
the heading estimate and rejects IMU spikes.
"""
from __future__ import annotations

import math
import time

import numpy as np

from backend.src.fusion.pose2d import Pose2D, PoseQuality, STALE_THRESHOLD_S


# Default process noise (Q): tuned for a slow lawn mower.
# Diagonal: [sigma_x^2, sigma_y^2, sigma_heading^2, sigma_v^2, sigma_omega^2]
_Q_DEFAULT = np.diag([0.01, 0.01, 1.0, 0.1, 5.0])

# Default GPS measurement noise (R_gps): [sigma_x^2, sigma_y^2]
_R_GPS_DEFAULT = np.diag([1.0, 1.0])

# Default IMU heading measurement noise (R_imu): [sigma_heading^2]
_R_IMU_DEFAULT = np.array([[5.0]])

# Mahalanobis distance gate (chi-squared, 2 DOF at 99%  = 9.21;
#                              1 DOF at 99% = 6.63)
_GATE_GPS: float = 9.21
_GATE_IMU: float = 6.63

_H_GPS = np.array([[1, 0, 0, 0, 0],
                   [0, 1, 0, 0, 0]], dtype=float)

_H_IMU = np.array([[0, 0, 1, 0, 0]], dtype=float)


class PoseFilter:
    """5-state EKF for planar navigation.

    Typical usage
    -------------
    pf = PoseFilter()
    pf.reset(x_m=0.0, y_m=0.0, heading_deg=90.0)
    pf.predict(dt=0.2, distance_m=0.1, delta_heading_deg=0.5)
    pf.update_gps(x_m=0.09, y_m=0.01, accuracy_m=0.5)
    pf.update_imu_heading(heading_deg=90.3, quality="calibrated")
    pose = pf.get_pose()
    """

    def __init__(
        self,
        Q: np.ndarray | None = None,
        R_gps: np.ndarray | None = None,
        R_imu: np.ndarray | None = None,
    ) -> None:
        self._Q = Q if Q is not None else _Q_DEFAULT.copy()
        self._R_gps = R_gps if R_gps is not None else _R_GPS_DEFAULT.copy()
        self._R_imu = R_imu if R_imu is not None else _R_IMU_DEFAULT.copy()

        # State
        self._x_m: float = 0.0
        self._y_m: float = 0.0
        self._heading_deg: float = 0.0
        self._v_mps: float = 0.0
        self._omega_dps: float = 0.0

        # Covariance — start large (uncertain)
        self._P: np.ndarray = np.diag([100.0, 100.0, 1000.0, 10.0, 100.0])

        # Quality tracking
        self._last_gps_ts: float | None = None
        self._last_imu_ts: float | None = None
        self._last_encoder_ts: float | None = None
        self._last_predict_ts: float = time.monotonic()

        self._gps_accuracy_m: float | None = None

    def reset(
        self,
        x_m: float = 0.0,
        y_m: float = 0.0,
        heading_deg: float = 0.0,
    ) -> None:
        """Reset filter to a known state (call at mission start after ENU origin set)."""
        self._x_m = x_m
        self._y_m = y_m
        self._heading_deg = heading_deg % 360.0
        self._v_mps = 0.0
        self._omega_dps = 0.0
        self._P = np.diag([0.5, 0.5, 10.0, 1.0, 10.0])
        self._last_gps_ts = None
        self._last_imu_ts = None
        self._last_encoder_ts = None
        self._last_predict_ts = time.monotonic()

    def predict(
        self,
        dt: float,
        distance_m: float = 0.0,
        delta_heading_deg: float = 0.0,
    ) -> None:
        """Propagate state forward by dt seconds using encoder odometry.

        distance_m and delta_heading_deg come from OdometryIntegrator.
        When encoders are unavailable pass v_mps * dt and omega_dps * dt.
        dt must be > 0; negative or zero dt is silently ignored.
        """
        if dt <= 0:
            return

        heading_rad = math.radians(self._heading_deg)

        # State update
        self._x_m += distance_m * math.cos(heading_rad)
        self._y_m += distance_m * math.sin(heading_rad)
        self._heading_deg = (self._heading_deg + delta_heading_deg) % 360.0
        if dt > 0:
            self._v_mps = max(0.0, distance_m / dt)
            self._omega_dps = delta_heading_deg / dt

        # Jacobian F (linearised motion model around current heading)
        heading_rad_u = heading_rad  # heading at start of step
        # Exact partial for heading_deg units:
        # dx = dist * cos(h_rad), d(dx)/d(h_deg) = -dist * sin(h_rad) * pi/180
        F = np.eye(5)
        F[0, 2] = -distance_m * math.sin(heading_rad_u) * math.pi / 180.0
        F[1, 2] =  distance_m * math.cos(heading_rad_u) * math.pi / 180.0

        self._P = F @ self._P @ F.T + self._Q * dt
        self._last_predict_ts = time.monotonic()

    def update_gps(
        self,
        x_m: float,
        y_m: float,
        accuracy_m: float = 5.0,
    ) -> bool:
        """Apply GPS ENU position measurement.

        accuracy_m scales the measurement noise covariance:
          R_gps_scaled = R_gps * (accuracy_m^2 / 1.0^2)

        Returns True if the measurement was accepted (within gate), False if rejected.
        """
        self._gps_accuracy_m = accuracy_m
        R = self._R_gps * (accuracy_m ** 2)
        innov = np.array([x_m - self._x_m, y_m - self._y_m])
        S = _H_GPS @ self._P @ _H_GPS.T + R
        # Innovation gate
        mahl2 = float(innov @ np.linalg.solve(S, innov))
        if mahl2 > _GATE_GPS:
            return False  # reject outlier

        K = self._P @ _H_GPS.T @ np.linalg.inv(S)
        state = np.array(
            [self._x_m, self._y_m, self._heading_deg, self._v_mps, self._omega_dps]
        )
        state_new = state + K @ innov
        self._x_m = float(state_new[0])
        self._y_m = float(state_new[1])
        self._heading_deg = float(state_new[2]) % 360.0
        self._v_mps = max(0.0, float(state_new[3]))
        self._omega_dps = float(state_new[4])
        self._P = (np.eye(5) - K @ _H_GPS) @ self._P
        self._last_gps_ts = time.monotonic()
        return True

    def update_imu_heading(
        self,
        heading_deg: float,
        quality: str = "calibrated",
    ) -> bool:
        """Apply IMU heading measurement.

        heading_deg is the adjusted compass heading (after yaw offset + session alignment).
        quality == 'uncalibrated' triples measurement noise and returns False after applying
        to signal degraded trust. Fully rejected only when quality == 'fault'.

        Returns True if measurement was accepted.
        """
        if quality == "fault":
            return False

        R = self._R_imu.copy()
        if quality == "uncalibrated":
            R = R * 9.0  # 3× std dev

        # Wrap-safe heading innovation
        innov_raw = ((heading_deg - self._heading_deg) + 180.0) % 360.0 - 180.0
        innov = np.array([innov_raw])
        S = _H_IMU @ self._P @ _H_IMU.T + R
        mahl2 = float((innov @ np.linalg.solve(S, innov)))
        if mahl2 > _GATE_IMU:
            return False  # outlier

        K = self._P @ _H_IMU.T @ np.linalg.inv(S)
        state = np.array(
            [self._x_m, self._y_m, self._heading_deg, self._v_mps, self._omega_dps]
        )
        state_new = state + K @ innov
        self._x_m = float(state_new[0])
        self._y_m = float(state_new[1])
        self._heading_deg = float(state_new[2]) % 360.0
        self._v_mps = max(0.0, float(state_new[3]))
        self._omega_dps = float(state_new[4])
        self._P = (np.eye(5) - K @ _H_IMU) @ self._P
        self._last_imu_ts = time.monotonic()
        return True

    def set_encoder_timestamp(self, ts: float) -> None:
        """Record that encoder odometry was applied at monotonic time ts."""
        self._last_encoder_ts = ts

    def get_pose(self) -> Pose2D:
        """Return current pose with quality classification."""
        now = time.monotonic()
        quality = self._classify_quality(now)
        return Pose2D(
            x_m=self._x_m,
            y_m=self._y_m,
            heading_deg=self._heading_deg,
            velocity_mps=self._v_mps,
            angular_velocity_dps=self._omega_dps,
            quality=quality,
            gps_timestamp_s=self._last_gps_ts,
            imu_timestamp_s=self._last_imu_ts,
            encoder_timestamp_s=self._last_encoder_ts,
            filter_timestamp_s=self._last_predict_ts,
        )

    def _classify_quality(self, now: float) -> PoseQuality:
        """Map GPS accuracy and sensor freshness to PoseQuality."""
        last_any = max(
            t for t in [self._last_gps_ts, self._last_imu_ts, self._last_encoder_ts]
            if t is not None
        ) if any(
            t is not None
            for t in [self._last_gps_ts, self._last_imu_ts, self._last_encoder_ts]
        ) else None

        if last_any is None or (now - self._last_predict_ts) > STALE_THRESHOLD_S:
            return PoseQuality.STALE

        gps_fresh = (
            self._last_gps_ts is not None
            and (now - self._last_gps_ts) <= STALE_THRESHOLD_S
        )
        if not gps_fresh:
            return PoseQuality.DEAD_RECKONING

        acc = self._gps_accuracy_m
        if acc is None:
            return PoseQuality.GPS_DEGRADED
        if acc <= 0.05:
            return PoseQuality.RTK_FIXED
        if acc <= 1.0:
            return PoseQuality.GPS_FLOAT
        return PoseQuality.GPS_DEGRADED


# ---------------------------------------------------------------------------
# Backward-compat shim: FusedState delegates to Pose2D fields
# ---------------------------------------------------------------------------
from dataclasses import dataclass as _dc


@_dc
class FusedState:
    """Thin compat alias kept for any callers of the old SimpleEKF API."""
    x: float
    y: float
    heading_deg: float
    timestamp_s: float
    quality: str = "unknown"
    sources: tuple[str, ...] = ()


class SimpleEKF:
    """Compatibility wrapper: delegates to PoseFilter.

    New code should use PoseFilter directly. This class exists only to avoid
    breaking any surviving callers of the old scaffold API.
    """

    def __init__(self) -> None:
        self._pf = PoseFilter()
        self._pf.reset()

    def reset(self) -> None:
        self._pf.reset()

    def predict(self, dt: float, v_mps: float = 0.0, omega_dps: float = 0.0) -> None:
        dist = max(0.0, v_mps) * dt
        dh = omega_dps * dt
        self._pf.predict(dt, distance_m=dist, delta_heading_deg=dh)

    def update_gps_xy(self, x: float, y: float, alpha: float = 0.5) -> None:
        self._pf.update_gps(x, y, accuracy_m=1.0)

    def update_heading(self, heading_deg: float, alpha: float = 0.5) -> None:
        self._pf.update_imu_heading(heading_deg)

    def step(self, v_mps: float = 0.0, omega_dps: float = 0.0) -> FusedState:
        now = time.monotonic()
        self.predict(0.1, v_mps, omega_dps)
        p = self._pf.get_pose()
        return FusedState(p.x_m, p.y_m, p.heading_deg, now)

    def get_state(self) -> FusedState:
        p = self._pf.get_pose()
        return FusedState(p.x_m, p.y_m, p.heading_deg, time.monotonic())


__all__ = ["PoseFilter", "FusedState", "SimpleEKF"]
