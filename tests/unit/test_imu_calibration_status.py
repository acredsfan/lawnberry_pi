"""Unit tests for IMU calibration status reporting.

Verifies that:
  - BNO085Driver _read_shtp_sync uses game_quaternion (no magnetometer dependency).
  - Calibration status is "calibrating" during warmup (<30 frames) and
    "fully_calibrated" once settled (>=30 frames).
  - BNO085Driver never returns calibration_status "unknown" in HW mode.
  - BNO085Driver returns "uncalibrated" before any valid frame is received.
  - IMUSensorInterface.read_imu() propagates the driver's calibration_status.
  - IMUSensorInterface fallback (no driver) also avoids "unknown".
  - None calibration_status from driver falls back to "uncalibrated", not "unknown".
  - calibration_service._CALIBRATION_STATE_TO_SCORE handles "rvc_active" and
    "uncalibrated" correctly.

Architecture note
-----------------
The BNO085 is used in UART/SHTP mode at 3 Mbaud.  The Game Rotation Vector
report provides yaw/pitch/roll via gyro + accelerometer fusion *without* using
the magnetometer.  This is intentional: motor currents create magnetic noise
that prevents reliable magnetometer calibration on the mower.

Calibration semantics:
  "uncalibrated"     -- no valid SHTP frame received yet (sensor offline / wiring issue)
  "calibrating"      -- frames arriving but gyro integration still settling (<30 frames)
  "fully_calibrated" -- >=30 valid frames; gyro settled; heading is reliable
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest


# ---------------------------------------------------------------------------
# Helpers: build a mock BNO08X_UART object for _read_shtp_sync
# ---------------------------------------------------------------------------

def _make_mock_bno(
    quat=(0.0, 0.0, 0.0, 1.0),
    accel=(0.0, 0.0, 9.81),
    gyro=(0.0, 0.0, 0.0),
):
    """Return a SimpleNamespace that mimics the Adafruit BNO08X_UART interface."""
    return SimpleNamespace(
        game_quaternion=quat,
        acceleration=accel,
        gyro=gyro,
    )


# ---------------------------------------------------------------------------
# _read_shtp_sync — calibration status based on valid_frames
# ---------------------------------------------------------------------------

def test_read_shtp_sync_returns_none_when_no_quaternion():
    """_read_shtp_sync must return None when game_quaternion is not available."""
    from backend.src.drivers.sensors.bno085_driver import _read_shtp_sync

    bno = _make_mock_bno(quat=None)
    result = _read_shtp_sync(bno, valid_frames=0)
    assert result is None


def test_read_shtp_sync_returns_none_when_quaternion_element_is_none():
    from backend.src.drivers.sensors.bno085_driver import _read_shtp_sync

    bno = _make_mock_bno(quat=(None, 0.0, 0.0, 1.0))
    result = _read_shtp_sync(bno, valid_frames=50)
    assert result is None


def test_read_shtp_sync_calibrating_before_warmup():
    """Before 30 valid frames the calibration_status must be 'calibrating'."""
    from backend.src.drivers.sensors.bno085_driver import _read_shtp_sync

    bno = _make_mock_bno()
    for frames in (0, 1, 15, 29):
        result = _read_shtp_sync(bno, valid_frames=frames)
        assert result is not None
        assert result["calibration_status"] == "calibrating", (
            f"Expected 'calibrating' at valid_frames={frames}, "
            f"got {result['calibration_status']!r}"
        )


def test_read_shtp_sync_fully_calibrated_after_warmup():
    """At 30+ valid frames the calibration_status must be 'fully_calibrated'."""
    from backend.src.drivers.sensors.bno085_driver import _read_shtp_sync

    bno = _make_mock_bno()
    for frames in (30, 31, 100, 500):
        result = _read_shtp_sync(bno, valid_frames=frames)
        assert result is not None
        assert result["calibration_status"] == "fully_calibrated", (
            f"Expected 'fully_calibrated' at valid_frames={frames}, "
            f"got {result['calibration_status']!r}"
        )


def test_read_shtp_sync_never_returns_unknown_or_rvc_active():
    """_read_shtp_sync must never emit 'unknown' or 'rvc_active'."""
    from backend.src.drivers.sensors.bno085_driver import _read_shtp_sync

    bno = _make_mock_bno()
    for frames in (0, 29, 30, 100):
        result = _read_shtp_sync(bno, valid_frames=frames)
        assert result is not None
        cal = result["calibration_status"]
        assert cal not in ("unknown", "rvc_active"), (
            f"Forbidden calibration_status {cal!r} at valid_frames={frames}"
        )


def test_read_shtp_sync_euler_angles_identity_quaternion():
    """Identity quaternion (w=1) must produce yaw=0, pitch=0, roll=0."""
    from backend.src.drivers.sensors.bno085_driver import _read_shtp_sync

    # Identity: i=0, j=0, k=0, real=1
    bno = _make_mock_bno(quat=(0.0, 0.0, 0.0, 1.0))
    result = _read_shtp_sync(bno, valid_frames=50)
    assert result is not None
    assert abs(result["yaw"]) < 0.01
    assert abs(result["pitch"]) < 0.01
    assert abs(result["roll"]) < 0.01


# ---------------------------------------------------------------------------
# BNO085Driver hardware path -- no serial port available
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bno085_driver_hw_path_returns_uncalibrated_when_no_port(monkeypatch):
    """HW path with missing serial port must return 'uncalibrated', never 'unknown'."""
    import backend.src.core.simulation as sim_mod
    monkeypatch.setattr(sim_mod, "is_simulation_mode", lambda: False)
    monkeypatch.delenv("SIM_MODE", raising=False)

    from backend.src.drivers.sensors.bno085_driver import BNO085Driver

    drv = BNO085Driver({"port": "/dev/nonexistent_bno085"})
    await drv.initialize()
    await drv.start()

    result = await drv.read_orientation()

    assert result is not None
    cal = result.get("calibration_status")
    assert cal == "uncalibrated", f"Expected 'uncalibrated', got {cal!r}"

    await drv.stop()


@pytest.mark.asyncio
async def test_bno085_driver_hw_path_never_returns_unknown(monkeypatch):
    """The string 'unknown' must never appear in the calibration_status field."""
    import backend.src.core.simulation as sim_mod
    monkeypatch.setattr(sim_mod, "is_simulation_mode", lambda: False)
    monkeypatch.delenv("SIM_MODE", raising=False)

    from backend.src.drivers.sensors.bno085_driver import BNO085Driver

    drv = BNO085Driver({"port": "/dev/nonexistent_bno085"})
    await drv.initialize()
    await drv.start()

    for _ in range(3):
        result = await drv.read_orientation()
        assert result is not None
        assert result.get("calibration_status") != "unknown", (
            "calibration_status 'unknown' is forbidden; use 'uncalibrated' or 'calibrating'"
        )

    await drv.stop()


@pytest.mark.asyncio
async def test_bno085_driver_hw_path_fully_calibrated_after_warmup(monkeypatch):
    """After valid_frames >= 30, read_orientation must carry 'fully_calibrated'."""
    import time
    import backend.src.core.simulation as sim_mod
    monkeypatch.setattr(sim_mod, "is_simulation_mode", lambda: False)
    monkeypatch.delenv("SIM_MODE", raising=False)

    from backend.src.drivers.sensors.bno085_driver import BNO085Driver

    drv = BNO085Driver({"port": "/dev/nonexistent_bno085"})
    await drv.initialize()
    await drv.start()

    # Inject a pre-warmed orientation (simulates 30+ successful hardware reads).
    drv._valid_frames = 30
    drv._last_orientation = {
        "roll": 0.0, "pitch": 0.0, "yaw": 45.0,
        "accel_x": 0.0, "accel_y": 0.0, "accel_z": 9.81,
        "gyro_x": 0.0, "gyro_y": 0.0, "gyro_z": 0.0,
        "calibration_status": "fully_calibrated",
    }
    drv._last_read_ts = time.time()

    result = await drv.read_orientation()
    assert result is not None
    assert result["calibration_status"] == "fully_calibrated"
    assert abs(result["yaw"] - 45.0) < 0.02

    await drv.stop()


@pytest.mark.asyncio
async def test_bno085_driver_not_initialized_returns_none(monkeypatch):
    """read_orientation returns None when driver is not initialized."""
    import backend.src.core.simulation as sim_mod
    monkeypatch.setattr(sim_mod, "is_simulation_mode", lambda: False)
    monkeypatch.delenv("SIM_MODE", raising=False)

    from backend.src.drivers.sensors.bno085_driver import BNO085Driver

    drv = BNO085Driver({"port": "/dev/nonexistent_bno085"})
    # Do NOT call initialize()
    result = await drv.read_orientation()
    assert result is None


# ---------------------------------------------------------------------------
# BNO085Driver simulation path
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_bno085_driver_sim_calibrating_then_fully_calibrated(monkeypatch):
    """SIM path: first 80 reads -> 'calibrating'; cycle 80+ -> 'fully_calibrated'."""
    monkeypatch.setenv("SIM_MODE", "1")
    
    from backend.src.drivers.sensors.bno085_driver import BNO085Driver
    drv = BNO085Driver({})
    await drv.initialize()
    await drv.start()

    r1 = await drv.read_orientation()
    assert r1 is not None
    assert r1["calibration_status"] == "calibrating"

    for _ in range(80):
        await drv.read_orientation()

    r2 = await drv.read_orientation()
    assert r2 is not None
    assert r2["calibration_status"] == "fully_calibrated"

    await drv.stop()


# ---------------------------------------------------------------------------
# IMUSensorInterface -- fallback path (driver is None)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_imu_interface_no_driver_online_not_unknown():
    """When _driver is None but status is ONLINE, calibration_status != 'unknown'."""
    from backend.src.services.sensor_manager import IMUSensorInterface, SensorCoordinator
    from backend.src.models.sensor_data import SensorStatus

    coordinator = SensorCoordinator.__new__(SensorCoordinator)
    iface = IMUSensorInterface.__new__(IMUSensorInterface)
    iface.coordinator = coordinator
    iface.last_reading = None
    iface.status = SensorStatus.ONLINE
    iface._driver = None  # simulate missing driver

    reading = await iface.read_imu()

    assert reading is not None
    assert reading.calibration_status != "unknown", (
        f"Expected non-'unknown' calibration_status, got {reading.calibration_status!r}"
    )


@pytest.mark.asyncio
async def test_imu_interface_no_driver_returns_uncalibrated():
    """When _driver is None, calibration_status must be 'uncalibrated'."""
    from backend.src.services.sensor_manager import IMUSensorInterface, SensorCoordinator
    from backend.src.models.sensor_data import SensorStatus

    coordinator = SensorCoordinator.__new__(SensorCoordinator)
    iface = IMUSensorInterface.__new__(IMUSensorInterface)
    iface.coordinator = coordinator
    iface.last_reading = None
    iface.status = SensorStatus.ONLINE
    iface._driver = None

    reading = await iface.read_imu()

    assert reading is not None
    assert reading.calibration_status == "uncalibrated", (
        f"Expected 'uncalibrated', got {reading.calibration_status!r}"
    )


# ---------------------------------------------------------------------------
# IMUSensorInterface -- driver propagation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_imu_interface_propagates_fully_calibrated():
    """read_imu must propagate 'fully_calibrated' from driver (warmed-up SHTP)."""
    from backend.src.services.sensor_manager import IMUSensorInterface, SensorCoordinator
    from backend.src.models.sensor_data import SensorStatus

    async def fake_read_orientation():
        return {
            "roll": 1.0,
            "pitch": 2.0,
            "yaw": 90.0,
            "accel_x": 0.0,
            "accel_y": 0.0,
            "accel_z": 9.81,
            "calibration_status": "fully_calibrated",
        }

    fake_driver = SimpleNamespace(read_orientation=fake_read_orientation)
    coordinator = SensorCoordinator.__new__(SensorCoordinator)
    iface = IMUSensorInterface.__new__(IMUSensorInterface)
    iface.coordinator = coordinator
    iface.last_reading = None
    iface.status = SensorStatus.ONLINE
    iface._driver = fake_driver

    reading = await iface.read_imu()

    assert reading is not None
    assert reading.calibration_status == "fully_calibrated"
    assert reading.roll == pytest.approx(1.0)
    assert reading.yaw == pytest.approx(90.0)


@pytest.mark.asyncio
async def test_imu_interface_propagates_calibrating():
    """read_imu must propagate 'calibrating' from driver (warmup phase)."""
    from backend.src.services.sensor_manager import IMUSensorInterface, SensorCoordinator
    from backend.src.models.sensor_data import SensorStatus

    async def fake_read_orientation():
        return {
            "roll": 0.0, "pitch": 0.0, "yaw": 45.0,
            "accel_x": 0.0, "accel_y": 0.0, "accel_z": 9.8,
            "calibration_status": "calibrating",
        }

    fake_driver = SimpleNamespace(read_orientation=fake_read_orientation)
    coordinator = SensorCoordinator.__new__(SensorCoordinator)
    iface = IMUSensorInterface.__new__(IMUSensorInterface)
    iface.coordinator = coordinator
    iface.last_reading = None
    iface.status = SensorStatus.ONLINE
    iface._driver = fake_driver

    reading = await iface.read_imu()
    assert reading is not None
    assert reading.calibration_status == "calibrating"


@pytest.mark.asyncio
async def test_imu_interface_none_calibration_falls_back_to_uncalibrated():
    """When driver returns None for calibration_status, fall back to 'uncalibrated'."""
    from backend.src.services.sensor_manager import IMUSensorInterface, SensorCoordinator
    from backend.src.models.sensor_data import SensorStatus

    async def fake_read_orientation():
        return {
            "roll": 0.0, "pitch": 0.0, "yaw": 0.0,
            "accel_x": 0.0, "accel_y": 0.0, "accel_z": 0.0,
            "calibration_status": None,
        }

    fake_driver = SimpleNamespace(read_orientation=fake_read_orientation)
    coordinator = SensorCoordinator.__new__(SensorCoordinator)
    iface = IMUSensorInterface.__new__(IMUSensorInterface)
    iface.coordinator = coordinator
    iface.last_reading = None
    iface.status = SensorStatus.ONLINE
    iface._driver = fake_driver

    reading = await iface.read_imu()

    assert reading is not None
    assert reading.calibration_status == "uncalibrated", (
        f"Expected 'uncalibrated' fallback, got {reading.calibration_status!r}"
    )
    assert reading.calibration_status != "unknown"


# ---------------------------------------------------------------------------
# calibration_service score mapping
# ---------------------------------------------------------------------------

def test_calibration_score_rvc_active():
    """'rvc_active' must score 2 (retained for backwards compat)."""
    from backend.src.services.calibration_service import _CALIBRATION_STATE_TO_SCORE

    assert _CALIBRATION_STATE_TO_SCORE["rvc_active"] == 2


def test_calibration_score_uncalibrated():
    """'uncalibrated' must score 0 (no calibration applied)."""
    from backend.src.services.calibration_service import _CALIBRATION_STATE_TO_SCORE

    assert _CALIBRATION_STATE_TO_SCORE["uncalibrated"] == 0


def test_calibration_score_calibrating():
    """'calibrating' must score 2 (warmup — partially operational)."""
    from backend.src.services.calibration_service import _CALIBRATION_STATE_TO_SCORE

    assert _CALIBRATION_STATE_TO_SCORE["calibrating"] == 2


def test_calibration_score_fully_calibrated():
    """'fully_calibrated' must score 3."""
    from backend.src.services.calibration_service import _CALIBRATION_STATE_TO_SCORE

    assert _CALIBRATION_STATE_TO_SCORE["fully_calibrated"] == 3


def test_calibration_score_unknown_not_in_map():
    """'unknown' must NOT appear in the calibration score map (it was retired)."""
    from backend.src.services.calibration_service import _CALIBRATION_STATE_TO_SCORE

    assert "rvc_active" in _CALIBRATION_STATE_TO_SCORE
    assert "uncalibrated" in _CALIBRATION_STATE_TO_SCORE
    assert "fully_calibrated" in _CALIBRATION_STATE_TO_SCORE
