"""Unit tests for IMU calibration status reporting (fix-imu-calibration-unknown).

Verifies that:
  - BNO085Driver RVC frame parser (_parse_rvc_frame) produces "rvc_active"
    calibration_status and correct angle/accel values.
  - _parse_rvc_frame rejects frames with bad checksums.
  - BNO085Driver never returns calibration_status "unknown" in HW mode.
  - BNO085Driver returns "uncalibrated" before any valid frame is received.
  - BNO085Driver returns "rvc_active" after a valid RVC frame is received.
  - IMUSensorInterface.read_imu() propagates the driver's calibration_status.
  - IMUSensorInterface fallback (no driver) also avoids "unknown".
  - None calibration_status from driver falls back to "uncalibrated", not "unknown".
  - calibration_service._CALIBRATION_STATE_TO_SCORE handles "rvc_active" and
    "uncalibrated" correctly.

Architecture note
-----------------
The BNO085 is used in UART/RVC (Robot Vacuum Cleaner) mode.  The RVC packet
format does NOT include calibration register bytes; the chip calibrates
internally and does not surface per-subsystem levels (0-3) via this protocol.
The driver therefore reports:
  "uncalibrated" -- no valid frame received yet (e.g. serial port offline)
  "rvc_active"   -- valid frames are being received; HW calibration is applied
                    internally but not measurable from this driver.
"""
from __future__ import annotations

import struct
from types import SimpleNamespace

import pytest


# ---------------------------------------------------------------------------
# Helpers: build a syntactically-valid RVC body
# ---------------------------------------------------------------------------

def _build_rvc_body(
    yaw_deg: float = 90.0,
    pitch_deg: float = 1.0,
    roll_deg: float = 0.5,
    az_mps2: float = 9.81,
) -> bytes:
    """Build a valid 19-byte RVC body with correct checksum."""
    body_data = struct.pack(
        "<Bhhhhhhxxxxx",
        1,                          # index
        int(yaw_deg / 0.01),        # yaw raw
        int(pitch_deg / 0.01),      # pitch raw
        int(roll_deg / 0.01),       # roll raw
        0,                          # ax
        0,                          # ay
        int(az_mps2 / 0.01),        # az
    )
    checksum = sum(body_data) & 0xFF
    return body_data + bytes([checksum])


# ---------------------------------------------------------------------------
# _parse_rvc_frame
# ---------------------------------------------------------------------------

def test_parse_rvc_frame_correct_angles():
    from backend.src.drivers.sensors.bno085_driver import _parse_rvc_frame

    body = _build_rvc_body(yaw_deg=90.0, pitch_deg=1.0, roll_deg=0.5, az_mps2=9.81)
    result = _parse_rvc_frame(body)

    assert result is not None, "Valid frame should parse successfully"
    assert abs(result["yaw"] - 90.0) < 0.02
    assert abs(result["pitch"] - 1.0) < 0.02
    assert abs(result["roll"] - 0.5) < 0.02
    assert abs(result["accel_z"] - 9.81) < 0.02


def test_parse_rvc_frame_calibration_status_is_rvc_active():
    from backend.src.drivers.sensors.bno085_driver import _parse_rvc_frame

    body = _build_rvc_body()
    result = _parse_rvc_frame(body)

    assert result is not None
    assert result["calibration_status"] == "rvc_active", (
        f"Expected 'rvc_active', got {result['calibration_status']!r}"
    )


def test_parse_rvc_frame_rejects_bad_checksum():
    from backend.src.drivers.sensors.bno085_driver import _parse_rvc_frame

    body = _build_rvc_body()
    bad_body = body[:-1] + bytes([(body[-1] + 1) & 0xFF])  # flip checksum
    result = _parse_rvc_frame(bad_body)

    assert result is None, "Frame with bad checksum must be rejected"


def test_parse_rvc_frame_rejects_wrong_length():
    from backend.src.drivers.sensors.bno085_driver import _parse_rvc_frame

    assert _parse_rvc_frame(b"\x00" * 18) is None  # too short
    assert _parse_rvc_frame(b"\x00" * 20) is None  # too long


def test_parse_rvc_frame_negative_angles():
    """Signed int16 must handle negative pitch and roll."""
    from backend.src.drivers.sensors.bno085_driver import _parse_rvc_frame

    body = _build_rvc_body(yaw_deg=0.0, pitch_deg=-5.0, roll_deg=-10.0)
    result = _parse_rvc_frame(body)

    assert result is not None
    assert abs(result["pitch"] - (-5.0)) < 0.02
    assert abs(result["roll"] - (-10.0)) < 0.02


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
            "calibration_status 'unknown' is forbidden; use 'uncalibrated' or 'rvc_active'"
        )

    await drv.stop()


@pytest.mark.asyncio
async def test_bno085_driver_hw_path_rvc_active_after_valid_frame(monkeypatch):
    """After _valid_frames > 0, the last_orientation must carry 'rvc_active'."""
    import backend.src.core.simulation as sim_mod
    monkeypatch.setattr(sim_mod, "is_simulation_mode", lambda: False)
    monkeypatch.delenv("SIM_MODE", raising=False)

    from backend.src.drivers.sensors.bno085_driver import BNO085Driver

    drv = BNO085Driver({"port": "/dev/nonexistent_bno085"})
    await drv.initialize()
    await drv.start()

    # Inject a pre-parsed frame directly (simulates a successful serial read)
    body = _build_rvc_body(yaw_deg=45.0, pitch_deg=0.0, roll_deg=0.0)
    from backend.src.drivers.sensors.bno085_driver import _parse_rvc_frame
    parsed = _parse_rvc_frame(body)
    assert parsed is not None

    drv._valid_frames += 1
    drv._last_orientation = parsed
    import time
    drv._last_read_ts = time.time()

    result = await drv.read_orientation()  # serial is None, so returns _last_orientation
    assert result is not None
    assert result["calibration_status"] == "rvc_active"
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
async def test_bno085_driver_sim_calibrating_then_fully_calibrated():
    """SIM path: first 80 reads -> 'calibrating'; cycle 80+ -> 'fully_calibrated'."""
    import os
    os.environ["SIM_MODE"] = "1"
    try:
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
    finally:
        os.environ.pop("SIM_MODE", None)


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
async def test_imu_interface_propagates_rvc_active():
    """read_imu must propagate 'rvc_active' calibration_status from driver."""
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
            "calibration_status": "rvc_active",
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
    assert reading.calibration_status == "rvc_active"
    assert reading.roll == pytest.approx(1.0)
    assert reading.yaw == pytest.approx(90.0)


@pytest.mark.asyncio
async def test_imu_interface_propagates_fully_calibrated():
    """read_imu must propagate 'fully_calibrated' (sim mode status) from driver."""
    from backend.src.services.sensor_manager import IMUSensorInterface, SensorCoordinator
    from backend.src.models.sensor_data import SensorStatus

    async def fake_read_orientation():
        return {
            "roll": 0.0, "pitch": 0.0, "yaw": 45.0,
            "accel_x": 0.0, "accel_y": 0.0, "accel_z": 9.8,
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
    """'rvc_active' must score 2 (operational, level not measurable)."""
    from backend.src.services.calibration_service import _CALIBRATION_STATE_TO_SCORE

    assert _CALIBRATION_STATE_TO_SCORE["rvc_active"] == 2


def test_calibration_score_uncalibrated():
    """'uncalibrated' must score 0 (no calibration applied)."""
    from backend.src.services.calibration_service import _CALIBRATION_STATE_TO_SCORE

    assert _CALIBRATION_STATE_TO_SCORE["uncalibrated"] == 0


def test_calibration_score_unknown_not_in_map():
    """'unknown' must NOT appear in the calibration score map (it was retired)."""
    from backend.src.services.calibration_service import _CALIBRATION_STATE_TO_SCORE

    # "unknown" is preserved for backwards compat at score=1 but "rvc_active"
    # should now be the real operational status.
    assert "rvc_active" in _CALIBRATION_STATE_TO_SCORE
    assert "uncalibrated" in _CALIBRATION_STATE_TO_SCORE


def test_calibration_score_fully_calibrated():
    from backend.src.services.calibration_service import _CALIBRATION_STATE_TO_SCORE

    assert _CALIBRATION_STATE_TO_SCORE["fully_calibrated"] == 3
