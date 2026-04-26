import threading
from pathlib import Path
from textwrap import dedent

import pytest

import backend.src.core.config_loader as _cl_mod
from backend.src.core.config_loader import ConfigLoader, get_config_loader


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


def test_config_loader_maps_gps_position_offsets(tmp_path: Path):
    (tmp_path / "hardware.yaml").write_text(
        dedent(
            """\
            gps:
              type: ZED-F9P
              antenna_offset_forward_m: -0.46
              antenna_offset_right_m: 0.08
              map_display_offset_north_m: 0.2
              map_display_offset_east_m: -0.1
            """
        )
    )
    (tmp_path / "limits.yaml").write_text("")

    loader = ConfigLoader(config_dir=str(tmp_path))
    hardware, _limits = loader.load()

    assert hardware.gps_antenna_offset_forward_m == pytest.approx(-0.46)
    assert hardware.gps_antenna_offset_right_m == pytest.approx(0.08)
    assert hardware.gps_map_display_offset_north_m == pytest.approx(0.2)
    assert hardware.gps_map_display_offset_east_m == pytest.approx(-0.1)


def test_config_loader_local_override(tmp_path: Path):
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
    (tmp_path / "limits.yaml").write_text(
        dedent(
            """\
            estop_latency_ms: 90
            tilt_cutoff_latency_ms: 180
            """
        )
    )

    loader = ConfigLoader(config_dir=str(tmp_path))
    hardware, limits = loader.load()

    assert hardware.victron_config is not None
    assert hardware.victron_config.encryption_key == "super-secret"
    assert limits.estop_latency_ms == 90
    assert limits.tilt_cutoff_latency_ms == 180


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
