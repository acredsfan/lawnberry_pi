from __future__ import annotations

from pathlib import Path

import pytest

from scripts.wlan1_usb_recovery import (
    CommandResult,
    Observation,
    RecoveryConfig,
    RecoveryController,
    RecoveryState,
    collect_observation,
)


class FakeRunner:
    def __init__(self, results: dict[tuple[str, ...], CommandResult] | None = None) -> None:
        self.results = results or {}
        self.calls: list[tuple[str, ...]] = []

    def run(self, args: tuple[str, ...], timeout_s: float) -> CommandResult:
        del timeout_s
        self.calls.append(args)
        return self.results.get(args, CommandResult(returncode=0, stdout="", stderr=""))


@pytest.mark.parametrize(
    ("observation", "expected"),
    [
        (Observation(False, False, False, False, False), RecoveryState.USB_MISSING),
        (Observation(True, False, False, False, False), RecoveryState.INTERFACE_MISSING),
        (Observation(True, True, False, False, False), RecoveryState.DISCONNECTED),
        (Observation(True, True, True, False, False), RecoveryState.NO_IPV4),
        (Observation(True, True, True, True, False), RecoveryState.NO_DEFAULT_ROUTE),
        (Observation(True, True, True, True, True), RecoveryState.HEALTHY),
    ],
)
def test_v90_classifies_local_radio_states(
    observation: Observation, expected: RecoveryState
) -> None:
    assert observation.state is expected


def test_v90_observation_never_probes_upstream_connectivity() -> None:
    config = RecoveryConfig()
    runner = FakeRunner(
        {
            ("lsusb", "-d", config.usb_id): CommandResult(0, "adapter", ""),
            ("ip", "link", "show", "dev", config.interface): CommandResult(0, "wlan1", ""),
            (
                "nmcli",
                "-g",
                "GENERAL.STATE",
                "device",
                "show",
                config.interface,
            ): CommandResult(0, "100 (connected)", ""),
            (
                "ip",
                "-4",
                "address",
                "show",
                "dev",
                config.interface,
                "scope",
                "global",
            ): CommandResult(0, "inet 192.168.4.10/22", ""),
            (
                "ip",
                "-4",
                "route",
                "show",
                "default",
                "dev",
                config.interface,
            ): CommandResult(0, "default via 192.168.4.1 dev wlan1", ""),
        }
    )

    assert collect_observation(config, runner).state is RecoveryState.HEALTHY
    assert not any(call[0] in {"ping", "curl", "getent"} for call in runner.calls)


def test_v90_missing_usb_cycles_only_configured_wifi_port_with_cooldown(
    tmp_path: Path,
) -> None:
    config = RecoveryConfig(
        usb_cycle_cooldown_s=300,
        max_usb_cycles_per_hour=3,
        state_path=tmp_path / "state.json",
    )
    runner = FakeRunner()
    controller = RecoveryController(config, runner)
    missing = Observation(False, False, False, False, False)

    first = controller.recover(missing, now=1_000.0)
    second = controller.recover(missing, now=1_100.0)

    assert first.action == "usb_port_cycle"
    assert first.success is True
    assert second.action == "usb_cycle_cooldown"
    assert runner.calls == [
        ("uhubctl", "-l", config.usb_hub_location, "-p", config.usb_port, "-a", "cycle"),
        ("udevadm", "settle", "--timeout=10"),
        ("modprobe", config.driver_module),
    ]
    flattened = " ".join(" ".join(call) for call in runner.calls)
    assert "reboot" not in flattened
    assert "NetworkManager" not in flattened


def test_v90_usb_cycle_budget_survives_controller_restart(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    config = RecoveryConfig(
        state_path=state_path,
        usb_cycle_cooldown_s=0,
        max_usb_cycles_per_hour=1,
    )
    missing = Observation(False, False, False, False, False)

    first = RecoveryController(config, FakeRunner())
    assert first.recover(missing, now=2_000.0).action == "usb_port_cycle"

    restarted = RecoveryController(config, FakeRunner())
    assert restarted.recover(missing, now=2_100.0).action == "usb_cycle_budget_exhausted"
    assert restarted.usb_cycles_last_hour(now=5_601.0) == 0


def test_v90_disconnected_radio_only_activates_primary_profile() -> None:
    config = RecoveryConfig()
    runner = FakeRunner()
    controller = RecoveryController(config, runner)

    decision = controller.recover(
        Observation(True, True, False, False, False),
        now=3_000.0,
    )

    assert decision.action == "activate_primary_profile"
    assert runner.calls == [
        (
            "nmcli",
            "connection",
            "up",
            "id",
            config.profile,
            "ifname",
            config.interface,
        )
    ]


def test_v90_healthy_radio_takes_no_action() -> None:
    runner = FakeRunner()
    controller = RecoveryController(RecoveryConfig(), runner)

    decision = controller.recover(Observation(True, True, True, True, True), now=4_000.0)

    assert decision.action == "none"
    assert runner.calls == []


def test_v90_service_contract_has_no_host_reboot_or_global_network_restart() -> None:
    root = Path(__file__).resolve().parents[2]
    service = (root / "systemd" / "lawnberry-wifi-recovery.service").read_text()

    assert "Type=simple" in service
    assert "scripts/wlan1_usb_recovery.py" in service
    assert "systemctl reboot" not in service
    assert "systemctl restart NetworkManager" not in service
    assert "Restart=always" in service


def test_v90_driver_and_udev_policy_target_only_external_radio() -> None:
    root = Path(__file__).resolve().parents[2]
    module_config = (root / "systemd" / "99-lawnberry-88x2bu.conf").read_text()
    udev_rules = (root / "systemd" / "99-lawnberry-wifi-usb.rules").read_text()
    networkmanager_config = (
        root / "systemd" / "90-lawnberry-wlan1-only.conf"
    ).read_text()

    assert "rtw_switch_usb_mode=2" in module_config
    assert "rtw_power_mgnt=0" in module_config
    assert "rtw_ips_mode=0" in module_config
    assert "rtw_enusbss=0" in module_config
    assert 'ATTR{idVendor}=="2357"' in udev_rules
    assert 'ATTR{idProduct}=="0138"' in udev_rules
    assert "power/control" in udev_rules
    assert "unmanaged-devices=interface-name:wlan0" in networkmanager_config


def test_v90_installer_retires_legacy_watchdog_and_enables_replacement() -> None:
    root = Path(__file__).resolve().parents[2]
    installer = (root / "systemd" / "install_services.sh").read_text()

    assert "systemctl disable --now wifi-watchdog.service" in installer
    assert 'ln -sfn /dev/null "$SYSTEMD_DIR/wifi-watchdog.service"' in installer
    assert "systemctl enable lawnberry-wifi-recovery.service" in installer
    assert "rm -f /etc/NetworkManager/dispatcher.d/90-wifi-failover" in installer
    assert "rm -f /etc/udev/rules.d/100-manage-wlan0.rules" in installer
