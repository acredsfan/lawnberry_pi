"""Tests for voltage_current_to_soc tail-current heuristic."""
import pytest
from backend.src.utils.battery import voltage_current_to_soc, voltage_to_soc


def test_high_voltage_settled_resting():
    """Pack at >= 13.40 V with tiny current → 95%+."""
    soc = voltage_current_to_soc(13.45, battery_current_a=0.2, solar_current_a=None)
    assert soc >= 95.0


def test_float_phase_detection():
    """Pack at >= 13.30 V with solar trickling in and no load → 90%+."""
    soc = voltage_current_to_soc(13.32, battery_current_a=0.3, solar_current_a=0.5)
    assert soc >= 90.0


def test_plateau_no_context():
    """At the plateau with no current info → pure OCV table."""
    soc_ours = voltage_current_to_soc(13.06, battery_current_a=None)
    soc_ocv = voltage_to_soc(13.06)
    assert soc_ours == soc_ocv


def test_plateau_heavy_load_no_snap():
    """High current draw means pack not resting → no snap."""
    soc = voltage_current_to_soc(13.40, battery_current_a=5.0)
    assert soc < 95.0


def test_none_voltage_returns_none():
    assert voltage_current_to_soc(None) is None


def test_flat_plateau_user_case():
    """User case: 13.23 V (after calibration offset) → OCV table result, not 45%."""
    # Before calibration, raw was 13.06; after +0.17 offset it's 13.23.
    # 13.23 V is in the 70–80% OCV interpolation band (~73.8%).
    # With modest current (0.2 A) but voltage below the 13.30/13.40 thresholds,
    # no heuristic fires — we trust the OCV table.
    soc = voltage_current_to_soc(13.23, battery_current_a=0.2, solar_current_a=None)
    assert 70.0 <= soc <= 90.0, f"Expected ~74%, got {soc}"
