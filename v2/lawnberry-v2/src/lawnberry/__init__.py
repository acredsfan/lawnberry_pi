"""LawnBerry Pi v2 - Autonomous Mower Controller.

Constitutional compliance:
- Platform Exclusivity: Raspberry Pi OS Bookworm (ARM64) only
- AI Acceleration Hierarchy: Coral TPU → Hailo → CPU TFLite
- Code Quality Gates: uv, ruff, black, mypy, pytest
- Documentation-as-Contract: All changes update /docs and /spec
- Runtime Standards: systemd, .env, Picamera2, periphery+lgpio
- Hardware Compliance: BNO085, INA3221, VL53L0X, Cytron MDDRC10
- Test-Driven Development: TDD with contract/integration/unit tests
"""

__version__ = "2.0.0"

# Constitutional validation - ensure we're running on correct platform
import platform
import sys

if platform.system() != "Linux" or platform.machine() != "aarch64":
    raise RuntimeError(
        "LawnBerry Pi v2 requires Raspberry Pi OS Bookworm (ARM64). "
        f"Current platform: {platform.system()}/{platform.machine()}"
    )

if sys.version_info < (3, 11):
    raise RuntimeError(
        "LawnBerry Pi v2 requires Python 3.11+. "
        f"Current version: {sys.version_info.major}.{sys.version_info.minor}"
    )

__all__ = []
