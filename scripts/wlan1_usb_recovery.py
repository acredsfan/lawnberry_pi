#!/usr/bin/env python3
"""Bounded recovery for LawnBerry's external USB WiFi radio.

This service deliberately observes only local USB, interface, NetworkManager,
IPv4, and route state.  Upstream reachability is not a recovery signal: an ISP
or DNS outage must never power-cycle hardware or reboot the mower.
"""

from __future__ import annotations

import json
import logging
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Protocol

LOG = logging.getLogger("lawnberry.wifi_recovery")


@dataclass(frozen=True, slots=True)
class CommandResult:
    returncode: int
    stdout: str
    stderr: str


class Runner(Protocol):
    def run(self, args: tuple[str, ...], timeout_s: float) -> CommandResult: ...


class SubprocessRunner:
    def run(self, args: tuple[str, ...], timeout_s: float) -> CommandResult:
        try:
            result = subprocess.run(
                args,
                capture_output=True,
                text=True,
                check=False,
                timeout=timeout_s,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return CommandResult(124, "", str(exc))
        return CommandResult(result.returncode, result.stdout, result.stderr)


def _env_int(name: str, default: int, *, minimum: int) -> int:
    value = int(os.getenv(name, str(default)))
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


@dataclass(frozen=True, slots=True)
class RecoveryConfig:
    interface: str = "wlan1"
    profile: str = "wlan1-primary"
    usb_id: str = "2357:0138"
    usb_hub_location: str = "3"
    usb_port: str = "1"
    driver_module: str = "88x2bu"
    check_interval_s: int = 15
    connect_cooldown_s: int = 30
    usb_cycle_cooldown_s: int = 300
    max_usb_cycles_per_hour: int = 3
    state_path: Path = Path("/var/lib/lawnberry-wifi-recovery/state.json")
    status_path: Path = Path("/run/lawnberry-wifi-recovery/status.json")

    @classmethod
    def from_env(cls) -> RecoveryConfig:
        return cls(
            interface=os.getenv("LAWNBERRY_WIFI_INTERFACE", "wlan1"),
            profile=os.getenv("LAWNBERRY_WIFI_PROFILE", "wlan1-primary"),
            usb_id=os.getenv("LAWNBERRY_WIFI_USB_ID", "2357:0138").lower(),
            usb_hub_location=os.getenv("LAWNBERRY_WIFI_USB_HUB", "3"),
            usb_port=os.getenv("LAWNBERRY_WIFI_USB_PORT", "1"),
            driver_module=os.getenv("LAWNBERRY_WIFI_DRIVER", "88x2bu"),
            check_interval_s=_env_int("LAWNBERRY_WIFI_CHECK_SECONDS", 15, minimum=5),
            connect_cooldown_s=_env_int(
                "LAWNBERRY_WIFI_CONNECT_COOLDOWN_SECONDS", 30, minimum=10
            ),
            usb_cycle_cooldown_s=_env_int(
                "LAWNBERRY_WIFI_USB_COOLDOWN_SECONDS", 300, minimum=60
            ),
            max_usb_cycles_per_hour=_env_int(
                "LAWNBERRY_WIFI_MAX_USB_CYCLES_PER_HOUR", 3, minimum=1
            ),
            state_path=Path(
                os.getenv(
                    "LAWNBERRY_WIFI_STATE_PATH",
                    "/var/lib/lawnberry-wifi-recovery/state.json",
                )
            ),
            status_path=Path(
                os.getenv(
                    "LAWNBERRY_WIFI_STATUS_PATH",
                    "/run/lawnberry-wifi-recovery/status.json",
                )
            ),
        )


class RecoveryState(str, Enum):
    USB_MISSING = "usb_missing"
    INTERFACE_MISSING = "interface_missing"
    NETWORKMANAGER_TRANSITIONING = "networkmanager_transitioning"
    DISCONNECTED = "disconnected"
    NO_IPV4 = "no_ipv4"
    NO_DEFAULT_ROUTE = "no_default_route"
    HEALTHY = "healthy"


@dataclass(frozen=True, slots=True)
class Observation:
    usb_present: bool
    interface_present: bool
    networkmanager_connected: bool
    ipv4_present: bool
    default_route_present: bool
    networkmanager_transitioning: bool = False

    @property
    def state(self) -> RecoveryState:
        if not self.usb_present:
            return RecoveryState.USB_MISSING
        if not self.interface_present:
            return RecoveryState.INTERFACE_MISSING
        if self.networkmanager_transitioning:
            return RecoveryState.NETWORKMANAGER_TRANSITIONING
        if not self.networkmanager_connected:
            return RecoveryState.DISCONNECTED
        if not self.ipv4_present:
            return RecoveryState.NO_IPV4
        if not self.default_route_present:
            return RecoveryState.NO_DEFAULT_ROUTE
        return RecoveryState.HEALTHY


@dataclass(frozen=True, slots=True)
class RecoveryDecision:
    state: RecoveryState
    action: str
    success: bool | None
    detail: str = ""


def _command_ok(runner: Runner, args: tuple[str, ...], timeout_s: float = 5.0) -> bool:
    result = runner.run(args, timeout_s)
    return result.returncode == 0 and bool(result.stdout.strip())


def _networkmanager_state_code(output: str) -> int | None:
    try:
        return int(output.strip().split(maxsplit=1)[0])
    except (IndexError, ValueError):
        return None


def collect_observation(config: RecoveryConfig, runner: Runner) -> Observation:
    """Collect local radio state without testing internet, DNS, or remote hosts."""
    usb_present = _command_ok(runner, ("lsusb", "-d", config.usb_id))
    if not usb_present:
        return Observation(False, False, False, False, False)

    interface_present = runner.run(
        ("ip", "link", "show", "dev", config.interface), 3.0
    ).returncode == 0
    if not interface_present:
        return Observation(True, False, False, False, False)

    nm_state = runner.run(
        (
            "nmcli",
            "-g",
            "GENERAL.STATE",
            "device",
            "show",
            config.interface,
        ),
        5.0,
    )
    nm_state_code = (
        _networkmanager_state_code(nm_state.stdout) if nm_state.returncode == 0 else None
    )
    connected = nm_state_code == 100
    transitioning = nm_state_code is not None and (
        40 <= nm_state_code < 100 or nm_state_code == 110
    )
    ipv4_present = _command_ok(
        runner,
        (
            "ip",
            "-4",
            "address",
            "show",
            "dev",
            config.interface,
            "scope",
            "global",
        ),
    )
    default_route_present = _command_ok(
        runner,
        ("ip", "-4", "route", "show", "default", "dev", config.interface),
    )
    return Observation(
        True,
        True,
        connected,
        ipv4_present,
        default_route_present,
        networkmanager_transitioning=transitioning,
    )


class RecoveryController:
    _ALLOWED_EXECUTABLES = frozenset({"uhubctl", "udevadm", "modprobe", "nmcli"})

    def __init__(self, config: RecoveryConfig, runner: Runner) -> None:
        self.config = config
        self.runner = runner
        self._usb_cycles = self._load_usb_cycles()
        self._last_connect_attempt = 0.0
        self._interface_missing_count = 0

    def _load_usb_cycles(self) -> list[float]:
        try:
            data = json.loads(self.config.state_path.read_text(encoding="utf-8"))
            values = data.get("usb_cycles", [])
            return [float(value) for value in values if float(value) >= 0]
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            return []

    def _persist_usb_cycles(self) -> None:
        path = self.config.state_path
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(
            json.dumps({"usb_cycles": self._usb_cycles}, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        temporary.replace(path)

    def _run_allowed(self, args: tuple[str, ...], timeout_s: float) -> CommandResult:
        if not args or args[0] not in self._ALLOWED_EXECUTABLES:
            raise ValueError(f"recovery command is not allowlisted: {args!r}")
        return self.runner.run(args, timeout_s)

    def _prune_usb_cycles(self, now: float) -> None:
        self._usb_cycles = [
            timestamp for timestamp in self._usb_cycles if 0 <= now - timestamp < 3600
        ]

    def _cycle_usb_port(self, state: RecoveryState, now: float) -> RecoveryDecision:
        self._prune_usb_cycles(now)
        if self._usb_cycles and now - self._usb_cycles[-1] < self.config.usb_cycle_cooldown_s:
            return RecoveryDecision(state, "usb_cycle_cooldown", None)
        if len(self._usb_cycles) >= self.config.max_usb_cycles_per_hour:
            return RecoveryDecision(state, "usb_cycle_budget_exhausted", False)

        cycle = self._run_allowed(
            (
                "uhubctl",
                "-l",
                self.config.usb_hub_location,
                "-p",
                self.config.usb_port,
                "-a",
                "cycle",
            ),
            15.0,
        )
        settle = self._run_allowed(("udevadm", "settle", "--timeout=10"), 12.0)
        module = self._run_allowed(("modprobe", self.config.driver_module), 10.0)
        self._usb_cycles.append(now)
        self._persist_usb_cycles()
        success = all(result.returncode == 0 for result in (cycle, settle, module))
        detail = "; ".join(
            result.stderr.strip()
            for result in (cycle, settle, module)
            if result.returncode != 0 and result.stderr.strip()
        )
        return RecoveryDecision(state, "usb_port_cycle", success, detail)

    def _load_driver(self, state: RecoveryState) -> RecoveryDecision:
        module = self._run_allowed(("modprobe", self.config.driver_module), 10.0)
        settle = self._run_allowed(("udevadm", "settle", "--timeout=10"), 12.0)
        success = module.returncode == 0 and settle.returncode == 0
        detail = module.stderr.strip() or settle.stderr.strip()
        return RecoveryDecision(state, "load_wifi_driver", success, detail)

    def _activate_profile(self, state: RecoveryState, now: float) -> RecoveryDecision:
        if now - self._last_connect_attempt < self.config.connect_cooldown_s:
            return RecoveryDecision(state, "connect_cooldown", None)
        self._last_connect_attempt = now
        result = self._run_allowed(
            (
                "nmcli",
                "connection",
                "up",
                "id",
                self.config.profile,
                "ifname",
                self.config.interface,
            ),
            35.0,
        )
        return RecoveryDecision(
            state,
            "activate_primary_profile",
            result.returncode == 0,
            result.stderr.strip(),
        )

    def recover(self, observation: Observation, *, now: float) -> RecoveryDecision:
        state = observation.state
        if state is RecoveryState.HEALTHY:
            self._interface_missing_count = 0
            return RecoveryDecision(state, "none", None)
        if state is RecoveryState.NETWORKMANAGER_TRANSITIONING:
            self._interface_missing_count = 0
            return RecoveryDecision(state, "wait_for_networkmanager", None)
        if state is RecoveryState.USB_MISSING:
            self._interface_missing_count = 0
            return self._cycle_usb_port(state, now)
        if state is RecoveryState.INTERFACE_MISSING:
            self._interface_missing_count += 1
            if self._interface_missing_count == 1:
                return self._load_driver(state)
            return self._cycle_usb_port(state, now)
        self._interface_missing_count = 0
        return self._activate_profile(state, now)

    def usb_cycles_last_hour(self, *, now: float) -> int:
        self._prune_usb_cycles(now)
        return len(self._usb_cycles)


def _write_status(
    config: RecoveryConfig,
    observation: Observation,
    decision: RecoveryDecision,
    usb_cycles_last_hour: int,
) -> None:
    path = config.status_path
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "timestamp": time.time(),
        "interface": config.interface,
        "profile": config.profile,
        "usb_id": config.usb_id,
        "state": observation.state.value,
        "usb_present": observation.usb_present,
        "interface_present": observation.interface_present,
        "networkmanager_connected": observation.networkmanager_connected,
        "networkmanager_transitioning": observation.networkmanager_transitioning,
        "ipv4_present": observation.ipv4_present,
        "default_route_present": observation.default_route_present,
        "action": decision.action,
        "success": decision.success,
        "detail": decision.detail,
        "usb_cycles_last_hour": usb_cycles_last_hour,
    }
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def run(config: RecoveryConfig, runner: Runner) -> None:
    stopping = False
    last_log_signature: tuple[RecoveryState, str, bool | None, str] | None = None

    def request_stop(signum: int, _frame: object) -> None:
        nonlocal stopping
        LOG.info("shutdown_requested signal=%s", signum)
        stopping = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    controller = RecoveryController(config, runner)
    LOG.info(
        "wifi_recovery_start interface=%s profile=%s usb_id=%s hub=%s port=%s",
        config.interface,
        config.profile,
        config.usb_id,
        config.usb_hub_location,
        config.usb_port,
    )

    while not stopping:
        started = time.monotonic()
        try:
            observation = collect_observation(config, runner)
            observed_at = time.time()
            decision = controller.recover(observation, now=observed_at)
            _write_status(
                config,
                observation,
                decision,
                controller.usb_cycles_last_hour(now=observed_at),
            )
            signature = (
                observation.state,
                decision.action,
                decision.success,
                decision.detail,
            )
            log_cycle = LOG.info if signature != last_log_signature else LOG.debug
            log_cycle(
                "wifi_recovery_cycle state=%s action=%s success=%s detail=%s",
                observation.state.value,
                decision.action,
                decision.success,
                decision.detail,
            )
            last_log_signature = signature
        except Exception:
            LOG.exception("wifi_recovery_cycle_failed")
        remaining = config.check_interval_s - (time.monotonic() - started)
        time.sleep(max(0.5, remaining))


def main() -> int:
    logging.basicConfig(
        level=os.getenv("LAWNBERRY_WIFI_LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    run(RecoveryConfig.from_env(), SubprocessRunner())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
