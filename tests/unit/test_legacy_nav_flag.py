"""Tests for the LAWN_LEGACY_NAV environment-variable routing flag.

The flag must be read fresh on each update_navigation_state() call so that
toggling it during a process restart takes effect without code changes.

These tests do NOT test localization correctness — that belongs in replay
parity tests.  They test only that the flag routes to the right internal
method and that both paths return a NavigationState.
"""
from __future__ import annotations

import importlib
import os
from unittest.mock import AsyncMock, patch

import pytest

from backend.src.models.sensor_data import SensorData
from backend.src.services.navigation_service import NavigationService


def _minimal_sensor_data() -> SensorData:
    return SensorData()


@pytest.mark.asyncio
async def test_legacy_path_called_when_flag_set(monkeypatch: pytest.MonkeyPatch) -> None:
    """When LAWN_LEGACY_NAV=1, update_navigation_state delegates to _legacy path."""
    monkeypatch.setenv("LAWN_LEGACY_NAV", "1")
    nav = NavigationService()

    with patch.object(
        nav,
        "_update_navigation_state_legacy",
        new_callable=AsyncMock,
        return_value=nav.navigation_state,
    ) as mock_legacy, patch.object(
        nav,
        "_update_navigation_state_impl",
        new_callable=AsyncMock,
        return_value=nav.navigation_state,
    ) as mock_impl:
        await nav.update_navigation_state(_minimal_sensor_data())

    mock_legacy.assert_awaited_once()
    mock_impl.assert_not_awaited()


@pytest.mark.asyncio
async def test_refactored_path_called_when_flag_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """When LAWN_LEGACY_NAV is absent/0, update_navigation_state delegates to _impl."""
    monkeypatch.delenv("LAWN_LEGACY_NAV", raising=False)
    nav = NavigationService()

    with patch.object(
        nav,
        "_update_navigation_state_legacy",
        new_callable=AsyncMock,
        return_value=nav.navigation_state,
    ) as mock_legacy, patch.object(
        nav,
        "_update_navigation_state_impl",
        new_callable=AsyncMock,
        return_value=nav.navigation_state,
    ) as mock_impl:
        await nav.update_navigation_state(_minimal_sensor_data())

    mock_impl.assert_awaited_once()
    mock_legacy.assert_not_awaited()


@pytest.mark.asyncio
async def test_flag_value_zero_uses_refactored_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """LAWN_LEGACY_NAV=0 is treated as unset — refactored path is used."""
    monkeypatch.setenv("LAWN_LEGACY_NAV", "0")
    nav = NavigationService()

    with patch.object(
        nav,
        "_update_navigation_state_legacy",
        new_callable=AsyncMock,
        return_value=nav.navigation_state,
    ) as mock_legacy, patch.object(
        nav,
        "_update_navigation_state_impl",
        new_callable=AsyncMock,
        return_value=nav.navigation_state,
    ) as mock_impl:
        await nav.update_navigation_state(_minimal_sensor_data())

    mock_impl.assert_awaited_once()
    mock_legacy.assert_not_awaited()


@pytest.mark.asyncio
async def test_legacy_path_returns_navigation_state() -> None:
    """_update_navigation_state_legacy must return a NavigationState (not crash)."""
    from backend.src.models import NavigationState

    nav = NavigationService()
    result = await nav._update_navigation_state_legacy(_minimal_sensor_data())
    assert isinstance(result, NavigationState)
