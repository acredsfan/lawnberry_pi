from pathlib import Path
from textwrap import dedent

from backend.src.core.config_loader import ConfigLoader


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
