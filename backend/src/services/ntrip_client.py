"""Async NTRIP client for forwarding RTK corrections to the rover GPS."""
from __future__ import annotations

import asyncio
import base64
import logging
import os
from contextlib import suppress
from dataclasses import dataclass
from typing import Optional

try:  # pyserial is optional in CI/staging environments
    import serial  # type: ignore
except Exception:  # pragma: no cover - pyserial absent on CI
    serial = None  # type: ignore

from ..models.sensor_data import GpsMode

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class NtripSettings:
    host: str
    port: int
    mountpoint: str
    serial_device: str
    baudrate: int
    username: Optional[str] = None
    password: Optional[str] = None
    gga_sentence: Optional[bytes] = None
    gga_interval: float = 10.0


class NtripForwarder:
    """Maintain an NTRIP connection and stream RTCM to the GPS receiver.

    The forwarder connects to a caster, authenticates, and forwards correction
    data to the GPS receiver over a serial link. Configuration is sourced from
    environment variables so deployments can inject secrets without persisting
    them on disk.
    """

    def __init__(self, settings: NtripSettings):
        self._settings = settings
        self._task: Optional[asyncio.Task[None]] = None
        self._stop_event = asyncio.Event()
        self._serial = None
        self._serial_lock = asyncio.Lock()

    @classmethod
    def from_environment(cls, gps_mode: GpsMode | None = None) -> Optional["NtripForwarder"]:
        host = os.getenv("NTRIP_HOST")
        mountpoint = os.getenv("NTRIP_MOUNTPOINT")
        if not host or not mountpoint:
            return None

        port = int(os.getenv("NTRIP_PORT", "2101"))
        username = os.getenv("NTRIP_USERNAME")
        password = os.getenv("NTRIP_PASSWORD")
        serial_device = (
            os.getenv("NTRIP_SERIAL_DEVICE")
            or os.getenv("GPS_DEVICE")
            or "/dev/ttyAMA0"
        )
        default_baud = 115200 if gps_mode in {GpsMode.F9P_USB, GpsMode.F9P_UART} else 9600
        baudrate = int(os.getenv("NTRIP_SERIAL_BAUD", str(default_baud)))

        gga_sentence = os.getenv("NTRIP_STATIC_GGA")
        if not gga_sentence:
            gga_sentence = cls._build_gga_from_env()
        gga_bytes = gga_sentence.encode("ascii") + b"\r\n" if gga_sentence else None
        gga_interval = float(os.getenv("NTRIP_GGA_INTERVAL", "10"))

        settings = NtripSettings(
            host=host,
            port=port,
            mountpoint=mountpoint,
            serial_device=serial_device,
            baudrate=baudrate,
            username=username,
            password=password,
            gga_sentence=gga_bytes,
            gga_interval=gga_interval,
        )
        return cls(settings)

    @staticmethod
    def _build_gga_from_env() -> Optional[str]:
        lat_str = os.getenv("NTRIP_GGA_LAT")
        lon_str = os.getenv("NTRIP_GGA_LON")
        if not lat_str or not lon_str:
            return None
        try:
            lat = float(lat_str)
            lon = float(lon_str)
            alt = float(os.getenv("NTRIP_GGA_ALT", "0"))
        except ValueError:
            logger.warning("Invalid NTRIP_GGA_* values provided; skipping static GGA")
            return None
        lat_ddmm, lat_hemi = NtripForwarder._decimal_to_ddmm(lat, is_lat=True)
        lon_ddmm, lon_hemi = NtripForwarder._decimal_to_ddmm(lon, is_lat=False)
        alt_field = f"{alt:.1f}"
        # Simple fixed GGA payload with quality=1 and 12 satellites
        fields = [
            "$GPGGA",
            "000000",
            lat_ddmm,
            lat_hemi,
            lon_ddmm,
            lon_hemi,
            "1",
            "12",
            "1.0",
            alt_field,
            "M",
            "0.0",
            "M",
            "",
            "",
        ]
        sentence = ",".join(fields)
        checksum = 0
        for char in sentence[1:]:  # skip '$'
            checksum ^= ord(char)
        return f"{sentence}*{checksum:02X}"

    @staticmethod
    def _decimal_to_ddmm(value: float, *, is_lat: bool) -> tuple[str, str]:
        hemi = "N" if (value >= 0 and is_lat) else "E"
        if is_lat and value < 0:
            hemi = "S"
        elif not is_lat and value < 0:
            hemi = "W"
        abs_value = abs(value)
        degrees = int(abs_value)
        minutes = (abs_value - degrees) * 60.0
        if is_lat:
            return f"{degrees:02d}{minutes:06.3f}", hemi
        return f"{degrees:03d}{minutes:06.3f}", hemi

    async def start(self) -> None:
        if self._task is not None:
            return
        if serial is None:
            raise RuntimeError("pyserial is required for NTRIP forwarding but is not installed")
        self._stop_event.clear()
        self._task = asyncio.create_task(self._run(), name="ntrip-forwarder")
        logger.info(
            "Started NTRIP forwarder to %s:%s mountpoint %s → %s",
            self._settings.host,
            self._settings.port,
            self._settings.mountpoint,
            self._settings.serial_device,
        )

    async def stop(self) -> None:
        if self._task is None:
            return
        self._stop_event.set()
        self._task.cancel()
        with suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        await self._close_serial()
        logger.info("Stopped NTRIP forwarder")

    async def _run(self) -> None:
        backoff = 2.0
        while not self._stop_event.is_set():
            try:
                await self._pump_once()
                backoff = 2.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("NTRIP forwarder error: %s", exc)
                await self._close_serial()
                if self._stop_event.is_set():
                    break
                await asyncio.sleep(min(backoff, 60.0))
                backoff = min(backoff * 2.0, 60.0)
        await self._close_serial()

    async def _pump_once(self) -> None:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(self._settings.host, self._settings.port),
            timeout=10.0,
        )
        request = self._build_request()
        writer.write(request)
        await writer.drain()

        header = await reader.readuntil(b"\r\n\r\n")
        if b"200" not in header:
            writer.close()
            await writer.wait_closed()
            raise RuntimeError(f"NTRIP caster rejected connection: {header.decode('ascii', errors='ignore').strip()}")

        await self._open_serial()
        gga_task: Optional[asyncio.Task[None]] = None
        if self._settings.gga_sentence:
            gga_task = asyncio.create_task(self._send_gga(writer))

        try:
            while not self._stop_event.is_set():
                chunk = await reader.read(4096)
                if not chunk:
                    break
                await self._write_serial(chunk)
        finally:
            if gga_task is not None:
                gga_task.cancel()
                with suppress(asyncio.CancelledError):
                    await gga_task
            writer.close()
            with suppress(Exception):
                await writer.wait_closed()

    def _build_request(self) -> bytes:
        mount = self._settings.mountpoint
        if not mount.startswith("/"):
            mount = "/" + mount
        headers = [
            f"GET {mount} HTTP/1.1",
            f"Host: {self._settings.host}",
            "Ntrip-Version: Ntrip/2.0",
            "User-Agent: LawnBerry-NTRIP/1.0",
        ]
        if self._settings.username and self._settings.password:
            auth_raw = f"{self._settings.username}:{self._settings.password}".encode("utf-8")
            headers.append("Authorization: Basic " + base64.b64encode(auth_raw).decode("ascii"))
        headers.append("Connection: keep-alive")
        headers.append("")
        headers.append("")
        return "\r\n".join(headers).encode("ascii")

    async def _open_serial(self) -> None:
        async with self._serial_lock:
            if self._serial is not None:
                return
            loop = asyncio.get_running_loop()
            self._serial = await loop.run_in_executor(
                None,
                lambda: serial.Serial(  # type: ignore[attr-defined]
                    self._settings.serial_device,
                    self._settings.baudrate,
                    timeout=0,
                ),
            )

    async def _close_serial(self) -> None:
        async with self._serial_lock:
            if self._serial is None:
                return
            serial_handle = self._serial
            self._serial = None
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, serial_handle.close)

    async def _write_serial(self, payload: bytes) -> None:
        if not payload:
            return
        async with self._serial_lock:
            serial_handle = self._serial
        if serial_handle is None:
            raise RuntimeError("Serial port not available for NTRIP forwarding")
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(None, serial_handle.write, payload)

    async def _send_gga(self, writer: asyncio.StreamWriter) -> None:
        try:
            while not self._stop_event.is_set():
                writer.write(self._settings.gga_sentence or b"")
                await writer.drain()
                await asyncio.sleep(max(self._settings.gga_interval, 1.0))
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug("GGA send loop ended: %s", exc)