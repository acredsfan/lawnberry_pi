"""Unit tests for BNO085 UART-RVC frame parsing.

RVC mode (PS1 HIGH) auto-streams 19-byte frames at 115200 baud, 100 Hz:

    byte  0     0xAA          header
    byte  1     0xAA          header
    byte  2     index         rolling 0-255
    bytes 3-4   yaw           int16 LE, 0.01 deg
    bytes 5-6   pitch         int16 LE, 0.01 deg
    bytes 7-8   roll          int16 LE, 0.01 deg
    bytes 9-10  accel X       int16 LE, 0.0098 m/s^2
    bytes 11-12 accel Y       int16 LE, 0.0098 m/s^2
    bytes 13-14 accel Z       int16 LE, 0.0098 m/s^2
    bytes 15-17 reserved
    byte  18    checksum      sum(bytes 2..17) & 0xFF

These tests exercise the pure parser and the resynchronising stream reader,
so they require no hardware and run under SIM_MODE.
"""

from __future__ import annotations

import struct

import pytest

from backend.src.drivers.sensors.bno085_driver import (
    _RVC_FRAME_LEN,
    RvcStream,
    parse_rvc_frame,
)


def build_rvc_frame(
    yaw_deg: float = 0.0,
    pitch_deg: float = 0.0,
    roll_deg: float = 0.0,
    accel: tuple[float, float, float] = (0.0, 0.0, 9.8),
    index: int = 0,
    bad_checksum: bool = False,
) -> bytes:
    """Construct a well-formed (or deliberately corrupt) RVC frame."""
    body = bytearray()
    body.append(index & 0xFF)
    body += struct.pack(
        "<hhh",
        int(round(yaw_deg * 100)),
        int(round(pitch_deg * 100)),
        int(round(roll_deg * 100)),
    )
    body += struct.pack("<hhh", *(int(round(a / 0.0098)) for a in accel))
    body += b"\x00\x00\x00"  # reserved
    checksum = sum(body) & 0xFF
    if bad_checksum:
        checksum = (checksum + 1) & 0xFF
    return b"\xaa\xaa" + bytes(body) + bytes([checksum])


class TestFrameShape:
    def test_builder_produces_expected_length(self):
        assert len(build_rvc_frame()) == _RVC_FRAME_LEN == 19

    def test_rejects_wrong_length(self):
        assert parse_rvc_frame(build_rvc_frame()[:-1]) is None

    def test_rejects_bad_header(self):
        frame = bytearray(build_rvc_frame())
        frame[1] = 0xAB
        assert parse_rvc_frame(bytes(frame)) is None

    def test_rejects_bad_checksum(self):
        assert parse_rvc_frame(build_rvc_frame(bad_checksum=True)) is None


class TestOrientationDecoding:
    def test_zero_frame(self):
        out = parse_rvc_frame(build_rvc_frame())
        assert out is not None
        assert out["yaw"] == pytest.approx(0.0, abs=0.02)
        assert out["pitch"] == pytest.approx(0.0, abs=0.02)
        assert out["roll"] == pytest.approx(0.0, abs=0.02)

    @pytest.mark.parametrize("yaw", [0.0, 45.5, 90.0, 179.99, -90.0, -179.99])
    def test_yaw_normalised_to_0_360(self, yaw):
        out = parse_rvc_frame(build_rvc_frame(yaw_deg=yaw))
        assert out is not None
        assert 0.0 <= out["yaw"] < 360.0
        assert out["yaw"] == pytest.approx(yaw % 360.0, abs=0.02)

    def test_pitch_and_roll_keep_sign(self):
        """Pitch/roll are signed tilt angles and must NOT be wrapped to [0,360)."""
        out = parse_rvc_frame(build_rvc_frame(pitch_deg=-12.5, roll_deg=-33.25))
        assert out is not None
        assert out["pitch"] == pytest.approx(-12.5, abs=0.02)
        assert out["roll"] == pytest.approx(-33.25, abs=0.02)

    def test_tilt_beyond_safety_threshold_is_representable(self):
        """FR-022 tilt cutoff is 30 deg; the parser must report it faithfully."""
        out = parse_rvc_frame(build_rvc_frame(roll_deg=35.0))
        assert out is not None
        assert out["roll"] == pytest.approx(35.0, abs=0.02)

    def test_acceleration_scaled_to_m_s2(self):
        out = parse_rvc_frame(build_rvc_frame(accel=(0.0, 0.0, 9.8)))
        assert out is not None
        assert out["accel_z"] == pytest.approx(9.8, abs=0.02)

    def test_rvc_reports_no_gyro(self):
        """RVC carries no angular rate; the contract keys must still exist as 0.0."""
        out = parse_rvc_frame(build_rvc_frame())
        assert out is not None
        for key in ("gyro_x", "gyro_y", "gyro_z"):
            assert out[key] == 0.0

    def test_contract_keys_present(self):
        """Keys consumed by sensor_manager must all be present."""
        out = parse_rvc_frame(build_rvc_frame())
        assert out is not None
        for key in (
            "roll", "pitch", "yaw",
            "accel_x", "accel_y", "accel_z",
            "gyro_x", "gyro_y", "gyro_z",
        ):
            assert key in out


class TestStreamResync:
    def test_single_clean_frame(self):
        stream = RvcStream()
        frames = stream.feed(build_rvc_frame(yaw_deg=12.0))
        assert len(frames) == 1
        assert frames[0]["yaw"] == pytest.approx(12.0, abs=0.02)

    def test_multiple_frames_in_one_read(self):
        stream = RvcStream()
        data = b"".join(build_rvc_frame(yaw_deg=y, index=i) for i, y in enumerate([1.0, 2.0, 3.0]))
        frames = stream.feed(data)
        assert [round(f["yaw"]) for f in frames] == [1, 2, 3]

    def test_recovers_from_leading_garbage(self):
        """A mid-frame connection must resync on the next 0xAAAA header."""
        stream = RvcStream()
        frames = stream.feed(b"\x01\x02\x03garbage" + build_rvc_frame(yaw_deg=77.0))
        assert len(frames) == 1
        assert frames[0]["yaw"] == pytest.approx(77.0, abs=0.02)

    def test_frame_split_across_reads(self):
        """Serial reads chop frames arbitrarily; state must persist across feeds."""
        stream = RvcStream()
        frame = build_rvc_frame(yaw_deg=200.0)
        assert stream.feed(frame[:8]) == []
        frames = stream.feed(frame[8:])
        assert len(frames) == 1
        assert frames[0]["yaw"] == pytest.approx(200.0, abs=0.02)

    def test_corrupt_frame_does_not_stall_stream(self):
        """A bad-checksum frame is dropped without swallowing the following good one."""
        stream = RvcStream()
        data = build_rvc_frame(yaw_deg=5.0, bad_checksum=True) + build_rvc_frame(yaw_deg=6.0)
        frames = stream.feed(data)
        assert len(frames) == 1
        assert frames[0]["yaw"] == pytest.approx(6.0, abs=0.02)

    def test_buffer_does_not_grow_without_bound(self):
        """Pure garbage must not accumulate indefinitely."""
        stream = RvcStream()
        for _ in range(200):
            stream.feed(b"\x00" * 64)
        assert len(stream._buf) < 1024


class TestDriverModeConfig:
    """The transport must be selectable from config, not just auto-probed."""

    def test_mode_defaults_to_auto(self):
        from backend.src.drivers.sensors.bno085_driver import BNO085Driver

        assert BNO085Driver({})._cfg.mode == "auto"

    @pytest.mark.parametrize("mode", ["rvc", "shtp", "auto"])
    def test_mode_honoured_from_config(self, mode):
        from backend.src.drivers.sensors.bno085_driver import BNO085Driver

        assert BNO085Driver({"mode": mode})._cfg.mode == mode

    def test_rvc_baudrate_default(self):
        from backend.src.drivers.sensors.bno085_driver import BNO085Driver

        assert BNO085Driver({})._cfg.rvc_baudrate == 115_200

    def test_no_transport_open_before_initialize(self):
        """A freshly constructed driver must not claim a working transport.

        ``_mode`` is set only after a transport opens, which is what makes it (and
        the hardware ``imu_epoch_id``) a trustworthy health signal, unlike
        ``initialized``.  Simulation assigns its own stable epoch at construction,
        so only ``_mode`` is asserted here.
        """
        from backend.src.drivers.sensors.bno085_driver import BNO085Driver

        assert BNO085Driver({})._mode is None
