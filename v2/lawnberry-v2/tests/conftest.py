"""Test configuration and fixtures for LawnBerry Pi v2."""

import platform
import sys

import pytest


@pytest.fixture(scope="session")
def platform_check():
    """Ensure tests run on correct platform."""
    if platform.system() != "Linux" or platform.machine() != "aarch64":
        pytest.skip("Tests require Raspberry Pi OS Bookworm (ARM64)")
    if sys.version_info < (3, 11):
        pytest.skip("Tests require Python 3.11+")


@pytest.fixture
def mock_hardware():
    """Mock hardware interfaces for testing."""
    # This will be expanded in later tasks
    return {"mock": True}
