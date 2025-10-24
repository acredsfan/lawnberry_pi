"""Victron SmartSolar BLE driver via the `victron-ble` CLI.

This driver shells out to the system `victron-ble` command to read the
SmartSolar controller over BLE and converts the returned JSON-like frame
into the same telemetry shape the INA3221 driver provides. Using the
external CLI keeps the Python runtime free of complex BLE deps and
matches the user's environment where only BLE connectivity is available.
"""
from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import time
from typing import Any, Dict, Optional

from ...core.simulation import is_simulation_mode
from ..base import HardwareDriver


logger = logging.getLogger(__name__)


class VictronVeDirectDriver(HardwareDriver):
    """Victron SmartSolar reader that shells out to ``victron-ble read``.

    Only a single JSON frame is captured per poll before terminating the CLI
    process so that concurrent BLE readers are not starved. Historic notes
    about VE.Direct serial access are retained in git history for reference.
    """

    _DEFAULT_CLI = "victron-ble"

    def __init__(self, config: Optional[dict[str, Any]] = None) -> None:
        super().__init__(config=config)
        cfg = config or {}
        self._enabled = bool(cfg.get("enabled", True))
        self._device_id = cfg.get("device_id")
        self._device_key = cfg.get("device_key")
        self._encryption_key = cfg.get("encryption_key")
        self._cli_path = cfg.get("cli_path", self._DEFAULT_CLI)
        self._adapter = cfg.get("adapter")
        self._read_timeout = float(cfg.get("read_timeout_s", 8.0))
        self._sample_limit = int(cfg.get("sample_limit", 1) or 1)
        self._adapter_warned = False
        self._last_payload: Optional[Dict[str, Any]] = None
        self._last_timestamp: Optional[float] = None

    async def initialize(self) -> None:
        self.initialized = True

    async def start(self) -> None:
        self.running = True

    async def stop(self) -> None:
        self.running = False

    async def health_check(self) -> dict[str, Any]:  # noqa: D401
        return {
            "sensor": "victron_vedirect",
            "enabled": self._enabled,
            "initialized": self.initialized,
            "running": self.running,
            "last_timestamp": self._last_timestamp,
            "last_payload": self._last_payload,
        }

    async def read_power(self) -> Optional[Dict[str, Any]]:
        if not self._enabled or not self.initialized:
            return None
        if is_simulation_mode():
            # Deterministic pseudo-data for CI; drift voltage slightly so trend is visible.
            now = time.time()
            base_voltage = 13.1 + 0.05 * ((now // 5) % 3)
            payload = {
                "battery_voltage": round(base_voltage, 3),
                "battery_current_amps": 2.0,
                "battery_power_w": round(base_voltage * 2.0, 3),
                "solar_voltage": 37.5,
                "solar_current_amps": 1.2,
                "solar_power_w": round(37.5 * 1.2, 3),
            }
            self._last_payload = payload
            self._last_timestamp = now
            return payload

        try:
            frame = await asyncio.to_thread(self._read_victron_cli_frame)
        except Exception:
            return self._last_payload

        if not frame:
            return self._last_payload

        parsed = self._convert_frame(frame)
        if not parsed:
            return self._last_payload

        self._last_payload = parsed
        self._last_timestamp = time.time()
        return parsed

    def _resolve_port(self) -> Optional[str]:
        # Deprecated for BLE-based flow
        return None

    def _build_cli_cmd(self) -> list[str]:
        device_key = self._resolve_device_key()
        cmd = [self._cli_path, "read", device_key]
        if self._adapter:
            if not self._adapter_warned:
                logger.warning(
                    "victron-ble read currently ignores custom adapters; set BLEAK_DEVICE env if needed"
                )
                self._adapter_warned = True
        return cmd

    def _resolve_device_key(self) -> str:
        if self._device_key:
            return str(self._device_key)
        if self._device_id and self._encryption_key:
            return f"{self._device_id}@{self._encryption_key}"
        raise RuntimeError(
            "Victron BLE configuration requires either 'device_key' or both 'device_id' and 'encryption_key'"
        )

    def _read_victron_cli_frame(self) -> Optional[Dict[str, Any]]:
        try:
            cmd = self._build_cli_cmd()
        except RuntimeError as exc:
            logger.error("Victron BLE configuration error: %s", exc)
            return None
        try:
            proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
        except FileNotFoundError:
            logger.error("victron-ble CLI not found at '%s'", self._cli_path)
            return None
        except Exception as exc:  # pragma: no cover - defensive
            logger.error("Failed to spawn victron-ble CLI: %s", exc)
            return None

        deadline = time.time() + self._read_timeout
        captured: Optional[dict[str, Any]] = None
        buffer = ""
        lines_read = 0

        try:
            while time.time() < deadline:
                if proc.stdout is None:
                    break
                line = proc.stdout.readline()
                if not line:
                    if proc.poll() is not None:
                        break
                    time.sleep(0.05)
                    continue
                stripped = line.strip()
                if not stripped:
                    continue
                lines_read += 1
                buffer = stripped if self._sample_limit <= 1 else f"{buffer}\n{stripped}".strip()
                try:
                    captured = json.loads(stripped)
                except json.JSONDecodeError:
                    # Attempt to parse full buffer when streaming multiple objects
                    try:
                        captured = json.loads(buffer)
                    except json.JSONDecodeError:
                        continue
                if captured is not None:
                    if lines_read >= self._sample_limit:
                        break
                    # Continue gathering samples until we reach sample_limit
                    captured = None
                    continue
            if captured is None and proc.stdout is not None:
                # Try final buffer if set
                try:
                    captured = json.loads(buffer)
                except Exception:
                    captured = None
            if captured is None:
                stderr_text = ""
                if proc.stderr is not None:
                    try:
                        stderr_text = proc.stderr.read().strip()
                    except Exception:
                        stderr_text = ""
                if stderr_text:
                    logger.debug("victron-ble stderr: %s", stderr_text)
                return None
            return captured
        finally:
            if proc.poll() is None:
                try:
                    proc.terminate()
                except Exception:
                    pass
                try:
                    proc.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    proc.kill()

            # Drain stderr to avoid zombies
            if proc.stderr is not None:
                try:
                    proc.stderr.close()
                except Exception:
                    pass

    # legacy serial reader removed - BLE CLI is used

    @staticmethod
    def _convert_frame(frame: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        payload = frame
        meta: Dict[str, Any] = {}
        if isinstance(frame, dict) and "payload" in frame and isinstance(frame["payload"], dict):
            payload = frame["payload"]
            meta = {k: v for k, v in frame.items() if k != "payload"}

        if not isinstance(payload, dict):
            return None

        def _to_float(value: Any) -> Optional[float]:
            if value is None:
                return None
            if isinstance(value, (int, float)):
                return round(float(value), 3)
            try:
                return round(float(str(value)), 3)
            except (TypeError, ValueError):
                return None

        # Determine if payload is VE.Direct numeric frame (keys like V, I, VPV) or BLE JSON
        is_numeric_frame = any(key in payload for key in ("V", "VPV", "PPV", "I", "IL"))

        if is_numeric_frame:
            def _get_int(key: str) -> Optional[int]:
                try:
                    return int(payload[key])
                except (KeyError, TypeError, ValueError):
                    return None

            battery_mv = _get_int("V")
            battery_ma = _get_int("I")
            panel_mv = _get_int("VPV")
            panel_power_w = _get_int("PPV")
            load_ma = _get_int("IL")

            if battery_mv is None and panel_mv is None and panel_power_w is None:
                return None

            def _scale_mv(value: Optional[int]) -> Optional[float]:
                if value is None:
                    return None
                return round(value / 1000.0, 3)

            def _scale_ma(value: Optional[int]) -> Optional[float]:
                if value is None:
                    return None
                return round(value / 1000.0, 3)

            battery_voltage = _scale_mv(battery_mv)
            battery_current = _scale_ma(battery_ma)
            solar_voltage = _scale_mv(panel_mv)
            solar_power = float(panel_power_w) if panel_power_w is not None else None
            solar_current = None
            if solar_voltage and solar_voltage > 0 and solar_power is not None:
                solar_current = round(solar_power / solar_voltage, 3)

            load_current = _scale_ma(load_ma)

            battery_power = None
            if battery_voltage is not None and battery_current is not None:
                battery_power = round(battery_voltage * battery_current, 3)
            if solar_power is not None:
                solar_power = round(solar_power, 3)

        else:
            battery_voltage = _to_float(payload.get("battery_voltage"))
            battery_current = _to_float(
                payload.get("battery_current") or payload.get("battery_charging_current")
            )
            # BLE JSON frames vary by model/firmware; accept a broad set of aliases
            solar_voltage = _to_float(
                payload.get("solar_voltage")
                or payload.get("panel_voltage")
                or payload.get("pv_voltage")
                or payload.get("input_voltage")
                or payload.get("solar_input_voltage")
            )
            solar_current = _to_float(
                payload.get("solar_current")
                or payload.get("solar_current_amps")
                or payload.get("panel_current")
                or payload.get("pv_current")
                or payload.get("input_current")
                or payload.get("solar_input_current")
            )
            solar_power = _to_float(
                payload.get("solar_power")
                or payload.get("solar_power_w")
                or payload.get("panel_power")
                or payload.get("pv_power")
                or payload.get("input_power")
            )
            load_current = _to_float(
                payload.get("load_current")
                or payload.get("load_current_amps")
                or payload.get("external_device_load")
            )
            battery_power = _to_float(payload.get("battery_power") or payload.get("battery_power_w"))

            if battery_power is None and battery_voltage is not None and battery_current is not None:
                battery_power = round(battery_voltage * battery_current, 3)

            if solar_power is None and solar_voltage is not None and solar_current is not None:
                solar_power = round(solar_voltage * solar_current, 3)

        if (
            battery_voltage is None
            and battery_current is None
            and solar_voltage is None
            and solar_power is None
            and load_current is None
        ):
            return None

        result = {
            "battery_voltage": battery_voltage,
            "battery_current_amps": battery_current,
            "battery_power_w": battery_power,
            "solar_voltage": solar_voltage,
            "solar_current_amps": solar_current,
            "solar_power_w": solar_power,
            "load_current_amps": load_current,
            "raw": payload,
        }

        if meta:
            result["meta"] = meta

        # Optional extended metadata from payload
        for optional_key in ("charge_state", "charger_error", "model_name", "yield_today"):
            if optional_key in payload:
                result.setdefault("meta", {})[optional_key] = payload[optional_key]

        # Surface daily solar yield as Wh if available. Victron sources sometimes
        # report yield_today in kWh; if the numeric value is small, assume kWh
        # and convert to Wh. Otherwise treat as Wh.
        try:
            yt_raw = payload.get("yield_today")
            yt_val = _to_float(yt_raw)
            if yt_val is not None:
                # Heuristic: values <= 10 are very likely kWh
                if yt_val <= 10.0:
                    result["solar_yield_today_wh"] = round(yt_val * 1000.0, 1)
                else:
                    result["solar_yield_today_wh"] = round(yt_val, 1)
        except Exception:
            pass

        return result


__all__ = ["VictronVeDirectDriver"]
