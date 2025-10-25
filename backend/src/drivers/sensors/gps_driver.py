"""GPS Driver (T058)

Supports u-blox ZED-F9P via USB or UART and Neo-8M via UART. This driver follows the
HardwareDriver lifecycle and returns GPS positions at ~1Hz when polled.

SIM_MODE notes:
- When SIM_MODE=1 (default in CI), returns deterministic positions without
  touching hardware. Accuracy reflects module class (F9P <1m, Neo-8M ~3m).

Platform notes:
- Real hardware access is guarded by lazy imports and not exercised in tests.
- UART/USB device paths are configurable via config or environment variables.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any, Optional
import math
import glob
import socket
import json

from ...core.simulation import is_simulation_mode
from ...models.sensor_data import GpsMode, GpsReading
from ..base import HardwareDriver


@dataclass
class GPSDriverConfig:
    mode: GpsMode = GpsMode.NEO8M_UART
    # Serial/USB configuration (used when not in SIM_MODE)
    usb_device: str = "/dev/ttyACM1"  # detected on Pi: ACM1 shows NMEA in probe
    uart_device: str = "/dev/ttyAMA0"  # common UART on Pi
    baudrate: int = 9600


class GPSDriver(HardwareDriver):
    """GPS hardware driver.

    Methods:
    - read_position() -> GpsReading | None
    """

    def __init__(self, config: dict[str, Any] | None = None):
        super().__init__(config=config)
        cfg = config or {}
        self.cfg = GPSDriverConfig(
            mode=GpsMode(cfg.get("mode", GpsMode.NEO8M_UART)),
            usb_device=cfg.get("usb_device", "/dev/ttyACM0"),
            uart_device=cfg.get("uart_device", "/dev/ttyAMA0"),
            baudrate=int(cfg.get("baudrate", 9600)),
        )
        self._last_read: GpsReading | None = None
        self._last_read_ts: float | None = None
        self._sim_counter: int = 0
        # Real hardware handles (lazy)
        self._serial = None
        self._first_read_done = False
        # Last observed NMEA sentences (for diagnostics)
        self._last_nmea: dict[str, str] = {}
        # Cached baudrates to try for different modules
        self._baud_candidates = [self.cfg.baudrate]
        if self.cfg.mode in (GpsMode.F9P_USB, GpsMode.F9P_UART):
            # F9P often uses higher baud
            for b in (115200, 38400, 9600):
                if b not in self._baud_candidates:
                    self._baud_candidates.append(b)
        else:
            for b in (9600, 38400):
                if b not in self._baud_candidates:
                    self._baud_candidates.append(b)

    async def initialize(self) -> None:  # noqa: D401
        # In SIM_MODE, we don't touch hardware
        if is_simulation_mode() or os.environ.get("SIM_MODE") == "1":
            self.initialized = True
            return
        # Lazy import serial only when needed
        try:
            import serial  # type: ignore  # noqa: F401
        except Exception:
            # If pyserial isn't available, keep initialized False to avoid runtime errors
            self.initialized = True  # allow running even without serial in CI
            return
        # Defer opening until start(); some platforms require permissions
        self.initialized = True

    async def start(self) -> None:  # noqa: D401
        if not self.initialized:
            await self.initialize()
        # In real mode, we could open serial here; keep it lazy to avoid CI issues
        self.running = True

    async def stop(self) -> None:  # noqa: D401
        self.running = False
        if self._serial is not None:
            try:
                self._serial.close()
            except Exception:
                pass
            self._serial = None

    async def health_check(self) -> dict[str, Any]:  # noqa: D401
        return {
            "driver": "gps",
            "mode": self.cfg.mode.value,
            "initialized": self.initialized,
            "running": self.running,
            "last_read_age_s": (time.time() - self._last_read_ts) if self._last_read_ts else None,
            "simulation": is_simulation_mode() or os.environ.get("SIM_MODE") == "1",
        }

    async def read_position(self) -> GpsReading | None:
        """Read current GPS position.

        Returns a GpsReading or None if not available. In SIM_MODE this
        generates a deterministic position around a fixed coordinate suitable
        for tests and local development.
        """
        if not self.initialized:
            return None

        if is_simulation_mode() or os.environ.get("SIM_MODE") == "1":
            # Deterministic walking pattern near Googleplex-like coords
            base_lat = 37.4220
            base_lon = -122.0841
            # Small oscillation to emulate movement
            d = (self._sim_counter % 20) * 0.000001
            lat = base_lat + d
            lon = base_lon - d
            self._sim_counter += 1
            is_f9p = self.cfg.mode in (GpsMode.F9P_USB, GpsMode.F9P_UART)
            acc = 0.6 if is_f9p else 3.0
            sats = 18 if is_f9p else 8
            rtk = "RTK_FIXED" if is_f9p else None
            hdop = 0.5 if is_f9p else 2.5
            reading = GpsReading(
                latitude=lat,
                longitude=lon,
                altitude=10.0,
                accuracy=acc,
                satellites=sats,
                mode=self.cfg.mode,
                rtk_status=rtk,
                hdop=hdop,
            )
            self._last_read = reading
            self._last_read_ts = time.time()
            return reading

        # Real hardware path (not exercised in CI/tests). Keep resilient.
        try:
            if self._serial is None:
                # Lazy open serial port based on mode with simple autodetect
                import serial  # type: ignore

                candidates: list[str] = []
                # Env overrides
                env_dev = os.environ.get("GPS_DEVICE")
                if env_dev:
                    candidates.append(env_dev)
                # Configured default
                default_dev = (
                    self.cfg.usb_device if self.cfg.mode == GpsMode.F9P_USB else self.cfg.uart_device
                )
                candidates.append(default_dev)
                # Common fallbacks on Raspberry Pi
                candidates.extend([
                    "/dev/ttyACM0", "/dev/ttyACM1", "/dev/ttyUSB0", "/dev/ttyUSB1",
                    "/dev/ttyAMA0", "/dev/ttyS0", "/dev/serial0",
                ])
                # Add ACM/USB globbed devices if present
                for pat in ("/dev/ttyACM*", "/dev/ttyUSB*"):
                    for p in glob.glob(pat):
                        if p not in candidates:
                            candidates.append(p)

                last_err: Optional[Exception] = None
                for dev in candidates:
                    for baud in self._baud_candidates:
                        try:
                            ser = serial.Serial(dev, baud, timeout=0.25)  # type: ignore
                            # Try a few reads to confirm NMEA stream presence
                            has_nmea = False
                            for _ in range(3):
                                line = ser.readline()
                                if not line:
                                    continue
                                try:
                                    s = line.decode("ascii", errors="ignore")
                                except Exception:
                                    s = ""
                                if s.startswith("$"):
                                    has_nmea = True
                                    break
                            if has_nmea:
                                self._serial = ser
                                self.cfg.baudrate = baud
                                break
                            else:
                                try:
                                    ser.close()
                                except Exception:
                                    pass
                        except Exception as e:  # pragma: no cover - hardware dependent
                            last_err = e
                            try:
                                ser.close()  # type: ignore
                            except Exception:
                                pass
                            continue
                    if self._serial is not None:
                        break
                # If not opened, keep last reading
                if self._serial is None:
                    return self._last_read

            # Read NMEA lines for a short window and parse
            # Allow a bit more time on first acquisition
            deadline = time.time() + (1.5 if not self._first_read_done else 0.75)
            got_lat = got_lon = False
            acc: Optional[float] = None
            acc_source: Optional[str] = None  # 'gst' | 'hdop'
            hdop_val: Optional[float] = None
            sats: Optional[int] = None
            alt: Optional[float] = None
            spd: Optional[float] = None
            hdg: Optional[float] = None
            lat: Optional[float] = None
            lon: Optional[float] = None
            rtk_status: Optional[str] = None

            while time.time() < deadline:
                raw = self._serial.readline().decode("ascii", errors="ignore")  # type: ignore
                if not raw or "$GP" not in raw and "$GN" not in raw and "$G" not in raw:
                    continue
                raw = raw.strip()
                if raw.startswith(("$GPGGA", "$GNGGA")):
                    try:
                        self._last_nmea["GGA"] = raw
                    except Exception:
                        pass
                    gga = self._parse_gga(raw)
                    if gga:
                        lat, lon, alt_gga, sats_gga, hdop, fix_quality = gga
                        if lat is not None and lon is not None:
                            got_lat = got_lon = True
                        if alt_gga is not None:
                            alt = alt_gga
                        if sats_gga is not None:
                            sats = sats_gga
                        # Approximate accuracy from HDOP (rough scale)
                        if hdop is not None:
                            hdop_val = hdop
                            # HDOP is a dilution-of-precision multiplier, not an accuracy by itself.
                            # Historically we used "max(0.5, hdop)" which masked RTK improvements
                            # (HDOP ~0.5) even when the fix was RTK_FIXED. Keep an HDOP-derived fallback
                            # but allow heuristics/real accuracy sources (GST/UBX) to override it later.
                            hdop_based = max(0.2, hdop * 1.0)
                            if acc is None or hdop_based < acc:
                                acc = hdop_based
                                acc_source = "hdop"
                        status = self._map_fix_quality(fix_quality)
                        if status is not None:
                            rtk_status = status
                elif raw.startswith(("$GPRMC", "$GNRMC")):
                    try:
                        self._last_nmea["RMC"] = raw
                    except Exception:
                        pass
                    rmc = self._parse_rmc(raw)
                    if rmc:
                        lat_r, lon_r, spd_knots, course = rmc
                        if lat_r is not None and lon_r is not None:
                            lat, lon = lat_r, lon_r
                            got_lat = got_lon = True
                        if spd_knots is not None:
                            spd = spd_knots * 0.514444  # knots -> m/s
                        if course is not None:
                            hdg = course
                elif raw.startswith(("$GPGST", "$GNGST")):
                    try:
                        self._last_nmea["GST"] = raw
                    except Exception:
                        pass
                    gst_accuracy = self._parse_gst(raw)
                    if gst_accuracy is not None:
                        if acc is None or gst_accuracy < acc:
                            acc = max(0.005, gst_accuracy)
                            acc_source = "gst"

                if got_lat and got_lon:
                    break

            if got_lat and got_lon:
                # If we have an RTK status but no explicit accuracy from GST/EHP,
                # provide a reasonable heuristic so the UI reflects the improved fix.
                # Typical 1-sigma horiz. accuracy: RTK_FIXED ~2-3cm, RTK_FLOAT ~10-30cm.
                # If our current accuracy is only HDOP-derived (or missing), tighten it using
                # RTK heuristics. Never loosen values coming from GST.
                if rtk_status:
                    if rtk_status == "RTK_FIXED":
                        heuristic = 0.03  # 3 cm
                    elif rtk_status == "RTK_FLOAT":
                        heuristic = 0.20  # 20 cm
                    else:
                        heuristic = None
                    if heuristic is not None:
                        if acc is None:
                            acc = heuristic
                            acc_source = "heuristic"
                        elif acc_source != "gst":
                            acc = min(acc, heuristic)
                reading = GpsReading(
                    latitude=lat,
                    longitude=lon,
                    altitude=alt,
                    accuracy=acc,
                    speed=spd,
                    satellites=sats,
                    mode=self.cfg.mode,
                    rtk_status=rtk_status,
                    hdop=hdop_val,
                )
                self._last_read = reading
                self._last_read_ts = time.time()
                self._first_read_done = True
                return reading

            # Optional gpsd fallback (if service is present on localhost:2947)
            gd = self._read_from_gpsd(timeout_sec=0.5 if self._first_read_done else 1.0)
            if gd is not None:
                self._last_read = gd
                self._last_read_ts = time.time()
                self._first_read_done = True
                return gd

            # If parsing failed, return last known
            return self._last_read
        except Exception:
            # On errors, keep last reading and mark running
            return self._last_read

    def get_last_nmea(self) -> dict[str, str]:
        """Return a shallow copy of last seen NMEA sentences for diagnostics."""
        try:
            return dict(self._last_nmea)
        except Exception:
            return {}

    @staticmethod
    def _parse_nmea_coord(val: str, hemi: str) -> Optional[float]:
        """Convert NMEA ddmm.mmmm (lat) / dddmm.mmmm (lon) to decimal degrees.

        hemi is 'N'/'S' or 'E'/'W'. Returns None if invalid.
        """
        try:
            if not val or not hemi:
                return None
            # Split degrees and minutes
            if "." not in val:
                return None
            dot = val.find(".")
            deg_len = dot - 2  # two digits of minutes before dot
            deg = int(val[:deg_len])
            mins = float(val[deg_len:])
            dec = deg + mins / 60.0
            if hemi in ("S", "W"):
                dec = -dec
            return dec
        except Exception:
            return None

    def _parse_gga(
        self, line: str
    ) -> Optional[tuple[Optional[float], Optional[float], Optional[float], Optional[int], Optional[float], Optional[int]]]:
        """Parse GGA: returns (lat, lon, altitude_m, satellites, hdop, fix_quality)."""
        try:
            parts = line.split(",")
            # GGA fields: 2=lat,3=N/S,4=lon,5=E/W,6=fix,7=sats,8=HDOP,9=altitude
            lat = self._parse_nmea_coord(parts[2], parts[3]) if len(parts) > 4 else None
            lon = self._parse_nmea_coord(parts[4], parts[5]) if len(parts) > 6 else None
            fix_quality = parts[6] if len(parts) > 6 else "0"
            sats = int(parts[7]) if len(parts) > 7 and parts[7].isdigit() else None
            hdop = float(parts[8]) if len(parts) > 8 and parts[8] not in ("", None) else None
            alt = float(parts[9]) if len(parts) > 9 and parts[9] not in ("", None) else None
            if fix_quality in {"0", ""}:  # no fix
                # Keep lat/lon if parser produced values but no fix -> treat as unreliable
                pass
            try:
                fix_int = int(fix_quality)
            except (TypeError, ValueError):
                fix_int = None
            return (lat, lon, alt, sats, hdop, fix_int)
        except Exception:
            return None

    def _parse_rmc(self, line: str) -> Optional[tuple[Optional[float], Optional[float], Optional[float], Optional[float]]]:
        """Parse RMC: returns (lat, lon, speed_knots, course_deg)."""
        try:
            parts = line.split(",")
            # RMC fields: 3=lat,4=N/S,5=lon,6=E/W,7=speed(knots),8=track/course
            lat = self._parse_nmea_coord(parts[3], parts[4]) if len(parts) > 4 else None
            lon = self._parse_nmea_coord(parts[5], parts[6]) if len(parts) > 6 else None
            spd = float(parts[7]) if len(parts) > 7 and parts[7] not in ("", None) else None
            course = float(parts[8]) if len(parts) > 8 and parts[8] not in ("", None) else None
            return (lat, lon, spd, course)
        except Exception:
            return None

    def _parse_gst(self, line: str) -> Optional[float]:
        """Parse GST sentence to estimate horizontal accuracy (1-sigma meters)."""
        try:
            parts = line.split(",")
            if len(parts) < 9:
                return None
            sd_lat = float(parts[6]) if parts[6] not in ("", None) else None
            sd_lon = float(parts[7]) if parts[7] not in ("", None) else None
            if sd_lat is None or sd_lon is None:
                return None
            # Combine latitude/longitude deviation into horizontal 1-sigma accuracy
            return math.sqrt(sd_lat * sd_lat + sd_lon * sd_lon)
        except Exception:
            return None

    @staticmethod
    def _map_fix_quality(fix_quality: Optional[int]) -> Optional[str]:
        if fix_quality is None:
            return None
        mapping = {
            0: "NO_FIX",
            1: "GPS_FIX",
            2: "DGPS",
            4: "RTK_FIXED",
            5: "RTK_FLOAT",
            6: "DEAD_RECKONING",
            7: "MANUAL",
            8: "SIMULATION",
        }
        return mapping.get(fix_quality)

    def _read_from_gpsd(self, timeout_sec: float = 0.5) -> Optional[GpsReading]:
        """Try reading a TPV report from gpsd if available.

        Uses a raw TCP socket to 127.0.0.1:2947 to avoid external deps.
        Returns a GpsReading if lat/lon are present, else None.
        """
        host = os.environ.get("GPSD_HOST", "127.0.0.1")
        port = int(os.environ.get("GPSD_PORT", "2947"))
        try:
            with socket.create_connection((host, port), timeout=0.3) as s:
                s.settimeout(timeout_sec)
                # Issue WATCH command
                s.sendall(b'?WATCH={"enable":true,"json":true}\n')
                start = time.time()
                buf = b""
                while time.time() - start < timeout_sec:
                    chunk = s.recv(4096)
                    if not chunk:
                        break
                    buf += chunk
                    # gpsd streams JSON objects delimited by newlines
                    while b"\n" in buf:
                        line, buf = buf.split(b"\n", 1)
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            obj = json.loads(line.decode("utf-8", errors="ignore"))
                        except Exception:
                            continue
                        if obj.get("class") == "TPV":
                            lat = obj.get("lat")
                            lon = obj.get("lon")
                            if isinstance(lat, (int, float)) and isinstance(lon, (int, float)):
                                alt = obj.get("alt") if isinstance(obj.get("alt"), (int, float)) else None
                                spd = obj.get("speed") if isinstance(obj.get("speed"), (int, float)) else None
                                crs = obj.get("track") if isinstance(obj.get("track"), (int, float)) else None
                                eph = obj.get("eph") if isinstance(obj.get("eph"), (int, float)) else None
                                return GpsReading(
                                    latitude=float(lat),
                                    longitude=float(lon),
                                    altitude=float(alt) if alt is not None else None,
                                    accuracy=float(eph) if eph is not None else None,
                                    speed=float(spd) if spd is not None else None,
                                    heading=float(crs) if crs is not None else None,
                                    mode=self.cfg.mode,
                                    hdop=float(eph) if eph is not None else None,
                                )
                return None
        except Exception:
            return None


__all__ = ["GPSDriver", "GPSDriverConfig"]
