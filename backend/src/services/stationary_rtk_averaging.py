"""Stationary RTK averaging for reference capture.

This service estimates an averaged antenna coordinate from fresh RTK-fixed GPS
samples. It deliberately returns a reference measurement only; it never writes a
global GPS offset or mutates navigation coordinates.
"""

from __future__ import annotations

import asyncio
import math
import time
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from statistics import median
from typing import Any

from ..fusion.enu_frame import ENUFrame
from ..models.sensor_data import GpsReading


def _finite(value: object) -> bool:
    return isinstance(value, (int, float)) and math.isfinite(float(value))


def _is_rtk_fixed(status: str | None) -> bool:
    normalized = str(status or "").strip().lower()
    return normalized in {"rtk_fixed", "rtk fixed", "fixed", "fix_3d_rtk_fixed"}


@dataclass(frozen=True)
class StationaryRtkAverageResult:
    accepted: bool
    averaged_antenna_coordinate: dict[str, float | None] | None
    rmse_m: float | None
    stddev_east_m: float | None
    stddev_north_m: float | None
    sample_count: int
    accepted_count: int
    rejected_count: int
    rejected_reasons: dict[str, int] = field(default_factory=dict)
    rtk_status_distribution: dict[str, int] = field(default_factory=dict)
    elapsed_s: float | None = None
    creates_global_offset: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "accepted": self.accepted,
            "averaged_antenna_coordinate": self.averaged_antenna_coordinate,
            "rmse_m": self.rmse_m,
            "stddev_east_m": self.stddev_east_m,
            "stddev_north_m": self.stddev_north_m,
            "sample_count": self.sample_count,
            "accepted_count": self.accepted_count,
            "rejected_count": self.rejected_count,
            "rejected_reasons": self.rejected_reasons,
            "rtk_status_distribution": self.rtk_status_distribution,
            "elapsed_s": self.elapsed_s,
            "creates_global_offset": self.creates_global_offset,
        }


def compute_stationary_rtk_average(
    readings: Iterable[GpsReading],
    *,
    min_samples: int = 20,
    max_accuracy_m: float = 0.05,
    max_speed_mps: float = 0.03,
    outlier_sigma: float = 3.0,
) -> StationaryRtkAverageResult:
    """Compute a robust average from stationary RTK-fixed antenna samples."""
    samples = list(readings)
    rtk_distribution = Counter(str(getattr(sample, "rtk_status", None) or "unknown") for sample in samples)
    rejected = Counter()
    valid: list[GpsReading] = []
    seen_sample_identities: set[tuple[str, object]] = set()

    for sample in samples:
        sample_id = getattr(sample, "sample_id", None)
        identity: tuple[str, object] = (
            ("sample_id", int(sample_id))
            if isinstance(sample_id, int)
            else ("timestamp", sample.timestamp.isoformat())
        )
        if identity in seen_sample_identities:
            rejected["duplicate_sample"] += 1
            continue
        seen_sample_identities.add(identity)
        if not _finite(sample.latitude) or not _finite(sample.longitude):
            rejected["missing_coordinate"] += 1
            continue
        if bool(getattr(sample, "cached", False)):
            rejected["cached"] += 1
            continue
        if not _is_rtk_fixed(getattr(sample, "rtk_status", None)):
            rejected["not_rtk_fixed"] += 1
            continue
        if sample.accuracy is None or not _finite(sample.accuracy) or float(sample.accuracy) > max_accuracy_m:
            rejected["accuracy"] += 1
            continue
        if sample.speed is not None and _finite(sample.speed) and abs(float(sample.speed)) > max_speed_mps:
            rejected["moving"] += 1
            continue
        valid.append(sample)

    if not valid:
        return StationaryRtkAverageResult(
            accepted=False,
            averaged_antenna_coordinate=None,
            rmse_m=None,
            stddev_east_m=None,
            stddev_north_m=None,
            sample_count=len(samples),
            accepted_count=0,
            rejected_count=len(samples),
            rejected_reasons=dict(rejected),
            rtk_status_distribution=dict(rtk_distribution),
            elapsed_s=None,
        )

    origin = valid[0]
    frame = ENUFrame()
    frame.set_origin(float(origin.latitude), float(origin.longitude))
    local_samples = [
        (
            *frame.to_local(float(sample.latitude), float(sample.longitude)),
            float(sample.altitude) if _finite(sample.altitude) else None,
        )
        for sample in valid
    ]
    median_e = median(point[0] for point in local_samples)
    median_n = median(point[1] for point in local_samples)
    distances = [math.hypot(point[0] - median_e, point[1] - median_n) for point in local_samples]
    median_distance = median(distances)
    mad = median(abs(distance - median_distance) for distance in distances)
    threshold_m = max(0.03, median_distance + outlier_sigma * max(mad, 0.01))

    kept: list[tuple[float, float, float | None]] = []
    for point, distance in zip(local_samples, distances, strict=True):
        if distance <= threshold_m:
            kept.append(point)
        else:
            rejected["outlier"] += 1

    if not kept:
        return StationaryRtkAverageResult(
            accepted=False,
            averaged_antenna_coordinate=None,
            rmse_m=None,
            stddev_east_m=None,
            stddev_north_m=None,
            sample_count=len(samples),
            accepted_count=0,
            rejected_count=len(samples),
            rejected_reasons=dict(rejected),
            rtk_status_distribution=dict(rtk_distribution),
            elapsed_s=None,
        )

    mean_e = sum(point[0] for point in kept) / len(kept)
    mean_n = sum(point[1] for point in kept) / len(kept)
    mean_alt: float | None = None
    altitudes = [point[2] for point in kept if point[2] is not None]
    if altitudes:
        mean_alt = sum(altitudes) / len(altitudes)
    residuals = [math.hypot(point[0] - mean_e, point[1] - mean_n) for point in kept]
    rmse = math.sqrt(sum(distance * distance for distance in residuals) / len(residuals))
    std_e = math.sqrt(sum((point[0] - mean_e) ** 2 for point in kept) / len(kept))
    std_n = math.sqrt(sum((point[1] - mean_n) ** 2 for point in kept) / len(kept))
    lat, lon = frame.to_wgs84(mean_e, mean_n)

    timestamps = [sample.timestamp for sample in valid if sample.timestamp is not None]
    elapsed_s = None
    if timestamps:
        elapsed_s = (max(timestamps) - min(timestamps)).total_seconds()

    accepted = len(kept) >= max(1, min_samples)
    return StationaryRtkAverageResult(
        accepted=accepted,
        averaged_antenna_coordinate={
            "latitude": lat,
            "longitude": lon,
            "altitude": mean_alt,
        },
        rmse_m=rmse,
        stddev_east_m=std_e,
        stddev_north_m=std_n,
        sample_count=len(samples),
        accepted_count=len(kept),
        rejected_count=len(samples) - len(kept),
        rejected_reasons=dict(rejected),
        rtk_status_distribution=dict(rtk_distribution),
        elapsed_s=elapsed_s,
    )


async def collect_live_stationary_rtk_average(
    gps: Any,
    *,
    duration_s: float = 8.0,
    interval_s: float = 0.1,
    min_samples: int = 5,
    max_accuracy_m: float = 0.05,
    max_speed_mps: float = 0.03,
) -> StationaryRtkAverageResult:
    """Observe the canonical GPS owner's cache until enough unique fixes arrive.

    This deliberately does not call ``read_gps``. The sensor manager remains
    the sole serial reader, while this observer keys samples by immutable
    identity so a cached fix cannot be counted repeatedly.
    """

    readings: list[GpsReading] = []
    seen: set[tuple[str, object]] = set()
    deadline = time.monotonic() + max(0.0, float(duration_s))
    while time.monotonic() < deadline:
        reading = getattr(gps, "last_reading", None)
        if isinstance(reading, GpsReading):
            sample_id = getattr(reading, "sample_id", None)
            identity: tuple[str, object] = (
                ("sample_id", int(sample_id))
                if isinstance(sample_id, int)
                else ("timestamp", reading.timestamp.isoformat())
            )
            if identity not in seen:
                seen.add(identity)
                readings.append(reading)
                provisional = compute_stationary_rtk_average(
                    readings,
                    min_samples=min_samples,
                    max_accuracy_m=max_accuracy_m,
                    max_speed_mps=max_speed_mps,
                )
                if provisional.accepted:
                    return provisional
        await asyncio.sleep(max(0.01, float(interval_s)))

    return compute_stationary_rtk_average(
        readings,
        min_samples=min_samples,
        max_accuracy_m=max_accuracy_m,
        max_speed_mps=max_speed_mps,
    )


__all__ = [
    "StationaryRtkAverageResult",
    "collect_live_stationary_rtk_average",
    "compute_stationary_rtk_average",
]
