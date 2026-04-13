"""
Battery utility functions for LawnBerry Pi.

Provides chemistry-aware voltage-to-SOC estimation using OCV lookup tables
with piecewise linear interpolation. Configure battery specs in hardware.yaml
under the `battery:` section.
"""

from typing import Optional

# LiFePO4 4S OCV (Open Circuit Voltage) vs SOC lookup table.
# Breakpoints represent *resting* pack voltage after equilibration.
# Notes:
#   - Under-load voltage sags below resting OCV → SOC will be understated while
#     driving, which is conservative (safe for a field robot).
#   - During charging, pack voltage rises above resting OCV → SOC will be
#     overstated.  The function clamps at max_voltage before table lookup, so
#     any voltage at or above max_voltage is unconditionally reported as 100 %.
#   - The flat region (20 %–80 %, ~12.88–13.28 V, only ~400 mV span) makes
#     voltage-only SOC inherently imprecise in the midrange.  Coulomb counting
#     (e.g. a Victron SmartShunt) would be more accurate but is not available
#     in the standard LawnBerry Pi build.
# Source: standard LiFePO4 4S cell datasheet OCV characteristics.
_LIFEPO4_4S_OCV_TABLE: list[tuple[float, float]] = [
    (10.0,   0.0),
    (11.0,   1.0),
    (12.0,   5.0),
    (12.5,  10.0),
    (12.8,  15.0),
    (12.88, 20.0),
    (12.96, 30.0),
    (13.04, 40.0),
    (13.08, 50.0),
    (13.12, 60.0),
    (13.2,  70.0),
    (13.28, 80.0),
    (13.4,  90.0),
    (13.6,  98.0),
    # 13.6 V is the practical "full charge resting" point.
    # 14.6 V is only seen during active absorption charging — it is handled
    # via the max_voltage clamp above the table rather than as an OCV entry.
]


def lifepo4_voltage_to_soc(
    voltage: float,
    min_voltage: float = 10.0,
    max_voltage: float = 14.6,
) -> float:
    """Estimate SOC (%) from pack voltage using the LiFePO4 OCV table.

    Args:
        voltage: Measured pack voltage in Volts.
        min_voltage: Absolute discharge cutoff (0 % clamp). Default 10.0 V.
        max_voltage: Full-charge voltage (100 % clamp). Default 14.6 V.

    Returns:
        Estimated SOC as a float in [0.0, 100.0].
    """
    if voltage <= min_voltage:
        return 0.0
    if voltage >= max_voltage:
        return 100.0

    table = _LIFEPO4_4S_OCV_TABLE
    # Clamp table to caller-supplied voltage limits
    v0, s0 = table[0]
    v1, s1 = table[-1]

    for i in range(len(table) - 1):
        v_lo, s_lo = table[i]
        v_hi, s_hi = table[i + 1]
        if v_lo <= voltage <= v_hi:
            if v_hi == v_lo:
                return s_lo
            ratio = (voltage - v_lo) / (v_hi - v_lo)
            return round(s_lo + ratio * (s_hi - s_lo), 1)

    # Fallback: linear clamp (should not reach here)
    ratio = (voltage - min_voltage) / (max_voltage - min_voltage)
    return round(max(0.0, min(100.0, ratio * 100.0)), 1)


def linear_voltage_to_soc(
    voltage: float,
    min_voltage: float,
    max_voltage: float,
) -> float:
    """Simple linear voltage-to-SOC model for non-LiFePO4 chemistries.

    Args:
        voltage: Measured pack voltage.
        min_voltage: Voltage at 0 % SOC.
        max_voltage: Voltage at 100 % SOC.

    Returns:
        Estimated SOC as a float in [0.0, 100.0].
    """
    if voltage <= min_voltage:
        return 0.0
    if voltage >= max_voltage:
        return 100.0
    ratio = (voltage - min_voltage) / (max_voltage - min_voltage)
    return round(ratio * 100.0, 1)


def voltage_to_soc(
    voltage: Optional[float],
    chemistry: str = "lifepo4",
    min_voltage: float = 10.0,
    max_voltage: float = 14.6,
) -> Optional[float]:
    """Estimate battery SOC (%) from voltage, dispatching by chemistry.

    Args:
        voltage: Measured pack voltage, or None if unavailable.
        chemistry: Battery chemistry string. Supported: ``"lifepo4"``.
                   Unknown chemistries fall back to the linear model.
        min_voltage: Absolute discharge cutoff (maps to 0 %).
        max_voltage: Full-charge voltage (maps to 100 %).

    Returns:
        SOC in [0.0, 100.0], or None if voltage is None.
    """
    if voltage is None:
        return None
    try:
        v = float(voltage)
    except (TypeError, ValueError):
        return None

    if chemistry.lower() in ("lifepo4", "lfp"):
        kwargs: dict = {}
        if min_voltage is not None:
            kwargs["min_voltage"] = min_voltage
        if max_voltage is not None:
            kwargs["max_voltage"] = max_voltage
        return lifepo4_voltage_to_soc(v, **kwargs)
    return linear_voltage_to_soc(v, min_voltage, max_voltage)


def battery_health_label(
    voltage: float,
    min_voltage: float = 10.0,
    warn_voltage: float = 12.0,
    healthy_voltage: float = 12.5,
) -> str:
    """Return a health label for a battery voltage reading.

    Thresholds are calibrated for LiFePO4 packs but can be overridden.

    Args:
        voltage: Measured pack voltage.
        min_voltage: Below this → "critical".
        warn_voltage: Below this (but above min) → "warning".
        healthy_voltage: At or above this → "healthy".

    Returns:
        One of "healthy", "warning", or "critical".
    """
    if voltage >= healthy_voltage:
        return "healthy"
    if voltage >= warn_voltage:
        return "warning"
    return "critical"
