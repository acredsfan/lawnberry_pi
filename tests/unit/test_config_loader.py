from pathlib import Path
import sys
from pathlib import Path as _Path

# Ensure repository root is on sys.path
ROOT = _Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
  sys.path.insert(0, str(ROOT))

from backend.src.core.config_loader import ConfigLoader


def test_config_loader_minimal(tmp_path: Path):
    # Create minimal YAMLs
    (tmp_path / "hardware.yaml").write_text(
        """
gps:
  type: ZED-F9P
imu:
  type: BNO085
        """
    )
    (tmp_path / "limits.yaml").write_text(
        """
estop_latency_ms: 100
tilt_cutoff_latency_ms: 200
        """
    )

    loader = ConfigLoader(config_dir=str(tmp_path))
    hw, limits = loader.load()

    # Validate selected fields
    assert hw.gps_type is not None
    assert limits.estop_latency_ms == 100
    assert limits.tilt_cutoff_latency_ms == 200
