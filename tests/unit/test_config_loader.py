import threading
from pathlib import Path
from textwrap import dedent

from backend.src.core.config_loader import ConfigLoader, get_config_loader


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
    """All threads must receive the identical singleton instance."""
    results: list = []

    def _fetch():
        results.append(get_config_loader())

    threads = [threading.Thread(target=_fetch) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(results) == 10
    assert all(inst is results[0] for inst in results)
