"""Legacy authentication security level tests.

This module intentionally skips execution to avoid conflicts with the active
`test_auth_security_levels_unit.py` suite.
"""

import pytest

pytest.skip(
    "Superseded by test_auth_security_levels_unit.py; skipping to avoid name conflict",
    allow_module_level=True,
)