"""Unit tests configuration for pytest.

This file ignores legacy or superseded test modules that conflict with
integration tests due to identical module basenames.
"""

# Prevent pytest from collecting this legacy file, which conflicts in module
# name with tests/integration/test_auth_security_levels.py
import sys
from pathlib import Path

# Ensure compat stubs are importable for optional deps (bcrypt, pyotp, google, psutil)
stub_path = Path(__file__).resolve().parents[2] / "backend" / "src" / "compat_stubs"
if str(stub_path) not in sys.path:
    sys.path.insert(0, str(stub_path))

collect_ignore = [
    "test_auth_security_levels.py",
]
