import threading
from pathlib import Path
from textwrap import dedent

import pytest

import backend.src.core.config_loader as _cl_mod
from backend.src.core.config_loader import ConfigLoader, get_config_loader
from backend.src.models.safety_limits import SafetyLimits, heading_bootstrap_stop_reserve_m


@pytest.fixture(autouse=True)
def _reset_config_loader_singleton():
    """Reset the module-level singleton before and after every test in this
    file so that tests that call get_config_loader() cannot bleed state into
    later tests and always exercise the first-construction code path."""
    _cl_mod._config_loader_instance = None
    yield
    _cl_mod._config_loader_instance = None


def test_config_loader_minimal(tmp_path: Path):
    (tmp_path / "hardware.yaml").write_text(
        dedent(
            """\
            gps:
              type: ZED-F9P
            imu:
              type: BNO085
            """
        )
    )
    (tmp_path / "limits.yaml").write_text(
        dedent(
            """\
            estop_latency_ms: 100
            tilt_cutoff_latency_ms: 200
            """
        )
    )

    loader = ConfigLoader(config_dir=str(tmp_path))
    hw, limits = loader.load()

    assert hw.gps_type is not None
    assert limits.estop_latency_ms == 100
    assert limits.tilt_cutoff_latency_ms == 200


def test_default_heading_bootstrap_budget_has_stop_headroom():
    limits = SafetyLimits()
    reserve_m = heading_bootstrap_stop_reserve_m(
        speed_mps=limits.bootstrap_speed_mps,
        command_ttl_ms=limits.autonomous_command_ttl_ms,
        braking_decel_mps2=limits.autonomous_braking_decel_mps2,
    )

    assert limits.bootstrap_min_travel_m == pytest.approx(0.25)
    assert limits.bootstrap_max_travel_m == pytest.approx(0.60)
    assert reserve_m == pytest.approx(0.15)
    assert limits.bootstrap_min_travel_m + reserve_m < limits.bootstrap_max_travel_m


def test_heading_bootstrap_budget_rejects_impossible_minimum():
    with pytest.raises(ValueError, match="lease/braking reserve"):
        SafetyLimits(bootstrap_min_travel_m=0.45, bootstrap_max_travel_m=0.60)


def test_config_loader_maps_gps_position_offsets(tmp_path: Path):
    (tmp_path / "hardware.yaml").write_text(
        dedent(
            """\
            gps:
              type: ZED-F9P
              antenna_offset_forward_m: -0.46
              antenna_offset_right_m: 0.08
            """
        )
    )
    (tmp_path / "limits.yaml").write_text("")

    loader = ConfigLoader(config_dir=str(tmp_path))
    hardware, _limits = loader.load()

    assert hardware.gps_antenna_offset_forward_m == pytest.approx(-0.46)
    assert hardware.gps_antenna_offset_right_m == pytest.approx(0.08)


def test_config_loader_maps_typed_blade_block(tmp_path: Path):
    (tmp_path / "hardware.yaml").write_text(
        dedent(
            """\
            blade:
              controller: ibt-4
              allow_autonomous: true
              spinup_seconds: 2.5
              shutdown_timeout_seconds: 1.2
              command_ack_timeout_seconds: 0.6
              pins:
                in1: 26
                in2: 27
            """
        )
    )
    (tmp_path / "limits.yaml").write_text("")

    loader = ConfigLoader(config_dir=str(tmp_path))
    hardware, _limits = loader.load()

    assert hardware.blade_controller.value == "ibt-4"
    assert hardware.blade.allow_autonomous is True
    assert hardware.blade.pins.in1 == 26
    assert hardware.blade.pins.in2 == 27


def test_config_loader_preserves_legacy_blade_controller_key(tmp_path: Path):
    (tmp_path / "hardware.yaml").write_text("blade_controller: robohat-rp2040\n")
    (tmp_path / "limits.yaml").write_text("")

    loader = ConfigLoader(config_dir=str(tmp_path))
    hardware, _limits = loader.load()

    assert hardware.blade_controller.value == "robohat-rp2040"
    assert hardware.blade.controller.value == "robohat-rp2040"


def test_config_loader_rejects_legacy_hardware_local_in_hardware_mode(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("SIM_MODE", "0")
    (tmp_path / "hardware.yaml").write_text(
        dedent(
            """\
            victron:
              enabled: true
              encryption_key: "placeholder"
            """
        )
    )
    (tmp_path / "hardware.local.yaml").write_text(
        dedent(
            """\
            victron:
              encryption_key: "super-secret"
            """
        )
    )
    (tmp_path / "limits.yaml").write_text("")

    loader = ConfigLoader(config_dir=str(tmp_path))

    with pytest.raises(RuntimeError, match="migrate-legacy"):
        loader.load()


def test_config_loader_ignores_legacy_hardware_local_in_simulation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("SIM_MODE", "1")
    (tmp_path / "hardware.yaml").write_text(
        dedent(
            """\
            victron:
              enabled: true
              encryption_key: "placeholder"
            """
        )
    )
    (tmp_path / "hardware.local.yaml").write_text(
        dedent(
            """\
            victron:
              encryption_key: "super-secret"
            """
        )
    )
    (tmp_path / "limits.yaml").write_text("")

    loader = ConfigLoader(config_dir=str(tmp_path))
    hardware, _limits = loader.load()

    assert hardware.victron_config is not None
    assert hardware.victron_config.encryption_key == "placeholder"
    assert loader.source_metadata()["hardware_legacy_present"] is True


def test_config_loader_preserves_limits_local_override(tmp_path: Path):
    (tmp_path / "hardware.yaml").write_text("gps:\n  type: ZED-F9P\n")
    (tmp_path / "limits.yaml").write_text(
        dedent(
            """\
            estop_latency_ms: 100
            tilt_cutoff_latency_ms: 200
            """
        )
    )
    (tmp_path / "limits.local.yaml").write_text(
        dedent(
            """\
            estop_latency_ms: 90
            tilt_cutoff_latency_ms: 180
            """
        )
    )

    loader = ConfigLoader(config_dir=str(tmp_path))
    _hardware, limits = loader.load()

    assert limits.estop_latency_ms == 90
    assert limits.tilt_cutoff_latency_ms == 180


def test_config_loader_missing_hardware_allowed_only_in_simulation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    (tmp_path / "limits.yaml").write_text("")
    monkeypatch.setenv("SIM_MODE", "1")

    loader = ConfigLoader(config_dir=str(tmp_path))
    hardware, _limits = loader.load()

    assert hardware.gps_type is None
    assert loader.source_metadata()["hardware_loaded"] is False
    assert loader.source_metadata()["hardware_missing_allowed"] is True

    monkeypatch.setenv("SIM_MODE", "0")
    loader = ConfigLoader(config_dir=str(tmp_path))
    with pytest.raises(FileNotFoundError, match="manage_hardware_config.py ensure"):
        loader.load()


def test_config_loader_unknown_top_level_key_fails(tmp_path: Path):
    (tmp_path / "hardware.yaml").write_text("motor_controler_port: /dev/ttyACM0\n")
    (tmp_path / "limits.yaml").write_text("")

    loader = ConfigLoader(config_dir=str(tmp_path))

    with pytest.raises(ValueError, match="unsupported top-level setting 'motor_controler_port'"):
        loader.load()


def test_config_loader_unknown_nested_key_fails(tmp_path: Path):
    (tmp_path / "hardware.yaml").write_text("victron:\n  foo_bar: true\n")
    (tmp_path / "limits.yaml").write_text("")

    loader = ConfigLoader(config_dir=str(tmp_path))

    with pytest.raises(ValueError, match="unknown setting 'victron.foo_bar'"):
        loader.load()


def test_config_loader_maps_robohat_and_bme280_runtime_fields(tmp_path: Path):
    (tmp_path / "hardware.yaml").write_text(
        dedent(
            """\
            motor_controller_port: /dev/robohat
            bme280:
              enabled: true
              bus: 1
              address: 118
              sea_level_hpa: 1010.0
            victron:
              enabled: false
              yield_today_unit: kwh
              solar_panel_max_wh: 1200.0
            """
        )
    )
    (tmp_path / "limits.yaml").write_text("")

    loader = ConfigLoader(config_dir=str(tmp_path))
    hardware, _limits = loader.load()

    assert hardware.motor_controller_port == "/dev/robohat"
    assert hardware.env_sensor is True
    assert hardware.bme280_config is not None
    assert hardware.bme280_config.sea_level_hpa == pytest.approx(1010.0)
    assert hardware.victron_config is not None
    assert hardware.victron_config.yield_today_unit == "kwh"


def test_get_config_loader_returns_same_instance():
    """get_config_loader() must always return the exact same object."""
    first = get_config_loader()
    second = get_config_loader()
    assert first is second


def test_get_config_loader_thread_safe():
    """All threads must receive the identical singleton instance even when
    they all race to construct it at the same time."""
    _cl_mod._config_loader_instance = None  # ensure fresh construction under contention

    barrier = threading.Barrier(10)
    results: list = []

    def _fetch():
        barrier.wait()  # all 10 threads release together to maximise lock contention
        results.append(get_config_loader())

    threads = [threading.Thread(target=_fetch) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 10
    assert all(inst is results[0] for inst in results)
