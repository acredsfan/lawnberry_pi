"""Unit tests for the UBX-CFG-VALSET builder that enables NMEA-GST on the F9P.

GST carries the receiver's own per-axis 1-sigma position error, which the GPS
driver already parses (``_parse_gst``) and prefers over its fix-type accuracy
heuristic. The receiver does not emit GST by default, so the driver enables it
at startup with a UBX-CFG-VALSET.

The golden vector below was accepted by a live ZED-F9P (it began emitting GST
immediately), so matching it proves the encoder against real hardware.
"""

from __future__ import annotations

from backend.src.drivers.sensors.gps_driver import (
    _UBX_CFG_MSGOUT_NMEA_GST_UART1,
    _UBX_CFG_MSGOUT_NMEA_GST_USB,
    _UBX_LAYER_PERSIST,
    build_enable_gst_message,
    build_ubx_cfg_valset,
)
from backend.src.models.sensor_data import GpsMode


def _fletcher(body: bytes) -> tuple[int, int]:
    ck_a = ck_b = 0
    for b in body:
        ck_a = (ck_a + b) & 0xFF
        ck_b = (ck_b + ck_a) & 0xFF
    return ck_a, ck_b


class TestValsetEncoding:
    # Hardware-accepted RAM-layer enable of GST on USB.
    GOLDEN_RAM_USB = bytes.fromhex("b5 62 06 8a 09 00 00 01 00 00 d6 00 91 20 01 22 53".replace(" ", ""))

    def test_matches_hardware_golden_vector(self):
        msg = build_ubx_cfg_valset(_UBX_CFG_MSGOUT_NMEA_GST_USB, value=1, layers=0x01)
        assert msg == self.GOLDEN_RAM_USB

    def test_sync_and_message_class(self):
        msg = build_ubx_cfg_valset(_UBX_CFG_MSGOUT_NMEA_GST_USB, value=1, layers=_UBX_LAYER_PERSIST)
        assert msg[:2] == b"\xb5\x62"  # UBX sync
        assert msg[2:4] == b"\x06\x8a"  # CFG-VALSET class/id

    def test_declared_length_matches_payload(self):
        msg = build_ubx_cfg_valset(_UBX_CFG_MSGOUT_NMEA_GST_USB, value=1, layers=_UBX_LAYER_PERSIST)
        declared = msg[4] | (msg[5] << 8)
        # frame = 2 sync + 2 class/id + 2 length + payload + 2 checksum
        assert declared == len(msg) - 8

    def test_checksum_is_valid(self):
        msg = build_ubx_cfg_valset(_UBX_CFG_MSGOUT_NMEA_GST_USB, value=1, layers=_UBX_LAYER_PERSIST)
        ck_a, ck_b = _fletcher(msg[2:-2])
        assert (msg[-2], msg[-1]) == (ck_a, ck_b)

    def test_key_is_little_endian_in_payload(self):
        msg = build_ubx_cfg_valset(_UBX_CFG_MSGOUT_NMEA_GST_USB, value=1, layers=_UBX_LAYER_PERSIST)
        # payload: version, layers, res, res, key[4 LE], value
        payload = msg[6:-2]
        key_le = payload[4:8]
        assert key_le == (_UBX_CFG_MSGOUT_NMEA_GST_USB).to_bytes(4, "little")
        assert payload[1] == _UBX_LAYER_PERSIST
        assert payload[8] == 1  # value

    def test_persist_layer_targets_ram_bbr_flash(self):
        # RAM (1) | BBR (2) | Flash (4)
        assert _UBX_LAYER_PERSIST == 0x07


class TestEnableGstSelection:
    def test_usb_mode_uses_usb_key(self):
        msg = build_enable_gst_message(GpsMode.F9P_USB)
        assert msg is not None
        assert msg[6:-2][4:8] == (_UBX_CFG_MSGOUT_NMEA_GST_USB).to_bytes(4, "little")

    def test_uart_mode_uses_uart1_key(self):
        msg = build_enable_gst_message(GpsMode.F9P_UART)
        assert msg is not None
        assert msg[6:-2][4:8] == (_UBX_CFG_MSGOUT_NMEA_GST_UART1).to_bytes(4, "little")

    def test_neo8m_is_unsupported(self):
        # Neo-8M does not use the CFG-VALSET key-value interface; skip cleanly.
        assert build_enable_gst_message(GpsMode.NEO8M_UART) is None

    def test_enable_message_persists(self):
        msg = build_enable_gst_message(GpsMode.F9P_USB)
        assert msg is not None
        assert msg[6:-2][1] == _UBX_LAYER_PERSIST  # layers byte


class _FakeSerialPort:
    def __init__(self):
        self.writes: list[bytes] = []
        self.flushed = False
        self.port = "/dev/lawnberry-gps"

    def write(self, data: bytes) -> int:
        self.writes.append(bytes(data))
        return len(data)

    def flush(self) -> None:
        self.flushed = True


class TestDriverConfiguresReceiver:
    def _driver(self, mode: str):
        from backend.src.drivers.sensors.gps_driver import GPSDriver

        return GPSDriver({"mode": mode})

    def test_configure_writes_enable_gst_for_f9p_usb(self):
        drv = self._driver("f9p_usb")
        drv._serial = _FakeSerialPort()
        drv._configure_receiver()
        assert drv._serial.writes == [build_enable_gst_message(GpsMode.F9P_USB)]
        assert drv._serial.flushed is True

    def test_configure_noop_for_neo8m(self):
        drv = self._driver("neo8m_uart")
        drv._serial = _FakeSerialPort()
        drv._configure_receiver()
        assert drv._serial.writes == []

    def test_configure_survives_write_error(self):
        drv = self._driver("f9p_usb")

        class _Boom(_FakeSerialPort):
            def write(self, data: bytes) -> int:
                raise OSError("port write failed")

        drv._serial = _Boom()
        drv._configure_receiver()  # must not raise

    def test_recovery_close_rearms_configuration(self):
        drv = self._driver("f9p_usb")
        drv._serial = _FakeSerialPort()
        drv._receiver_configured = True
        drv._close_serial_for_recovery("test")
        # After a reopen the receiver must be reconfigured.
        assert drv._receiver_configured is False
