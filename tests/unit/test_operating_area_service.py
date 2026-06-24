from __future__ import annotations

import json
from datetime import UTC, datetime
from unittest.mock import MagicMock

import pytest

from backend.src.models import Position
from backend.src.services.boundary_paths import (
    MOWING_BOUNDARY_CONFIRMED,
    MOWING_BOUNDARY_SAFE,
    boundary_file,
)
from backend.src.services.geofence_buffer import boundary_revision_hash
from backend.src.services.operating_area_service import (
    OperatingAreaError,
    load_operating_area_snapshot,
)


def _write_json(name: str, payload: dict) -> None:
    path = boundary_file(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _square(lat: float = 40.0, lon: float = -75.0, size_deg: float = 0.0002) -> list[dict]:
    return [
        {"latitude": lat, "longitude": lon},
        {"latitude": lat, "longitude": lon + size_deg},
        {"latitude": lat + size_deg, "longitude": lon + size_deg},
        {"latitude": lat + size_deg, "longitude": lon},
    ]


def test_snapshot_loads_safe_boundary_and_exclusions(tmp_path, monkeypatch):
    monkeypatch.setenv("LAWN_DATA_DIR", str(tmp_path))
    confirmed = _square()
    _write_json(
        MOWING_BOUNDARY_CONFIRMED,
        {"source": "user_confirmed", "created_at": datetime.now(UTC).isoformat(), "coordinates": confirmed},
    )
    _write_json(
        MOWING_BOUNDARY_SAFE,
        {
            "source": "user_confirmed",
            "created_at": datetime.now(UTC).isoformat(),
            "buffer_meters": 0.5,
            "confirmed_boundary_hash": boundary_revision_hash(confirmed),
            "coordinates": confirmed,
        },
    )
    repo = MagicMock()
    repo.list_zones.return_value = [
        {
            "id": "bed",
            "zone_kind": "exclusion",
            "polygon": [
                {"latitude": 40.00008, "longitude": -74.99992},
                {"latitude": 40.00008, "longitude": -74.99988},
                {"latitude": 40.00012, "longitude": -74.99988},
                {"latitude": 40.00012, "longitude": -74.99992},
            ],
        }
    ]

    snapshot = load_operating_area_snapshot(map_repository=repo)

    assert snapshot.valid
    assert len(snapshot.exclusions) == 1
    assert not snapshot.segment_is_safe(
        Position(latitude=40.00010, longitude=-74.99995),
        Position(latitude=40.00010, longitude=-74.99985),
        margin_m=0.05,
    )


def test_stale_safe_boundary_is_not_valid(tmp_path, monkeypatch):
    monkeypatch.setenv("LAWN_DATA_DIR", str(tmp_path))
    confirmed = _square()
    _write_json(
        MOWING_BOUNDARY_CONFIRMED,
        {"source": "user_confirmed", "created_at": datetime.now(UTC).isoformat(), "coordinates": confirmed},
    )
    _write_json(
        MOWING_BOUNDARY_SAFE,
        {
            "source": "user_confirmed",
            "created_at": datetime.now(UTC).isoformat(),
            "buffer_meters": 0.5,
            "coordinates": confirmed,
        },
    )

    snapshot = load_operating_area_snapshot()

    assert not snapshot.valid
    assert snapshot.validity_state == "SAFE_BOUNDARY_STALE"


def test_concave_segment_with_inside_endpoints_can_be_unsafe(tmp_path, monkeypatch):
    monkeypatch.setenv("LAWN_DATA_DIR", str(tmp_path))
    concave = [
        {"latitude": 40.0, "longitude": -75.0},
        {"latitude": 40.0, "longitude": -74.9997},
        {"latitude": 40.0003, "longitude": -74.9997},
        {"latitude": 40.0003, "longitude": -74.9999},
        {"latitude": 40.0001, "longitude": -74.9999},
        {"latitude": 40.0001, "longitude": -75.0},
    ]
    _write_json(
        MOWING_BOUNDARY_SAFE,
        {
            "source": "test",
            "created_at": datetime.now(UTC).isoformat(),
            "buffer_meters": 0.0,
            "coordinates": concave,
        },
    )
    snapshot = load_operating_area_snapshot()
    start = Position(latitude=40.00005, longitude=-74.99997)
    end = Position(latitude=40.00020, longitude=-74.99978)

    assert snapshot.contains_center(start)
    assert snapshot.contains_center(end)
    assert not snapshot.segment_is_safe(start, end, margin_m=0.01)


def test_ready_for_autonomy_requires_rtk_fresh_position(tmp_path, monkeypatch):
    monkeypatch.setenv("LAWN_DATA_DIR", str(tmp_path))
    coords = _square()
    _write_json(
        MOWING_BOUNDARY_SAFE,
        {
            "source": "test",
            "created_at": datetime.now(UTC).isoformat(),
            "buffer_meters": 0.0,
            "coordinates": coords,
        },
    )
    snapshot = load_operating_area_snapshot()

    with pytest.raises(OperatingAreaError) as exc:
        snapshot.validate_ready_for_autonomy(
            position=Position(latitude=40.0001, longitude=-74.9999, accuracy=1.0),
            last_gps_fix=datetime.now(UTC),
            dead_reckoning_active=False,
            max_fix_age_s=2.0,
            max_accuracy_m=0.25,
            footprint_radius_m=0.1,
            fixed_allowance_m=0.05,
        )

    assert exc.value.reason_code == "LOCALIZATION_NOT_RTK_GRADE"


def test_ready_for_autonomy_rejects_center_inside_but_footprint_outside(tmp_path, monkeypatch):
    monkeypatch.setenv("LAWN_DATA_DIR", str(tmp_path))
    coords = _square()
    _write_json(
        MOWING_BOUNDARY_SAFE,
        {
            "source": "test",
            "created_at": datetime.now(UTC).isoformat(),
            "buffer_meters": 0.0,
            "coordinates": coords,
        },
    )
    snapshot = load_operating_area_snapshot()
    pose = Position(latitude=40.0001, longitude=-74.999999, accuracy=0.02)

    assert snapshot.contains_center(pose)
    with pytest.raises(OperatingAreaError) as exc:
        snapshot.validate_ready_for_autonomy(
            position=pose,
            last_gps_fix=datetime.now(UTC),
            dead_reckoning_active=False,
            max_fix_age_s=2.0,
            max_accuracy_m=0.25,
            footprint_radius_m=0.35,
            fixed_allowance_m=0.10,
        )

    assert exc.value.reason_code == "CURRENT_FOOTPRINT_OUTSIDE_FREE_SPACE"


def test_ready_for_autonomy_rejects_exclusion_penetration(tmp_path, monkeypatch):
    monkeypatch.setenv("LAWN_DATA_DIR", str(tmp_path))
    coords = _square()
    _write_json(
        MOWING_BOUNDARY_SAFE,
        {
            "source": "test",
            "created_at": datetime.now(UTC).isoformat(),
            "buffer_meters": 0.0,
            "coordinates": coords,
        },
    )
    repo = MagicMock()
    repo.list_zones.return_value = [
        {
            "id": "bed",
            "zone_kind": "exclusion",
            "polygon": [
                {"latitude": 40.00008, "longitude": -74.99992},
                {"latitude": 40.00008, "longitude": -74.99988},
                {"latitude": 40.00012, "longitude": -74.99988},
                {"latitude": 40.00012, "longitude": -74.99992},
            ],
        }
    ]
    snapshot = load_operating_area_snapshot(map_repository=repo)

    with pytest.raises(OperatingAreaError) as exc:
        snapshot.validate_ready_for_autonomy(
            position=Position(latitude=40.00010, longitude=-74.99990, accuracy=0.02),
            last_gps_fix=datetime.now(UTC),
            dead_reckoning_active=False,
            max_fix_age_s=2.0,
            max_accuracy_m=0.25,
            footprint_radius_m=0.05,
            fixed_allowance_m=0.02,
        )

    assert exc.value.reason_code == "CURRENT_FOOTPRINT_OUTSIDE_FREE_SPACE"


def test_predictive_guard_blocks_outward_near_edge(tmp_path, monkeypatch):
    monkeypatch.setenv("LAWN_DATA_DIR", str(tmp_path))
    coords = _square()
    _write_json(
        MOWING_BOUNDARY_SAFE,
        {
            "source": "test",
            "created_at": datetime.now(UTC).isoformat(),
            "buffer_meters": 0.0,
            "coordinates": coords,
        },
    )
    snapshot = load_operating_area_snapshot()
    pose = Position(latitude=40.0001, longitude=-74.99982, accuracy=0.02)

    assert not snapshot.swept_motion_is_safe(
        pose,
        90.0,
        0.8,
        0.8,
        footprint_radius_m=0.3,
        uncertainty_m=0.02,
        fixed_allowance_m=0.05,
        horizon_s=1.0,
        command_latency_s=0.35,
        wheelbase_m=0.30,
        braking_decel_mps2=0.5,
    )
    assert snapshot.swept_motion_is_safe(
        pose,
        270.0,
        0.1,
        0.1,
        footprint_radius_m=0.05,
        uncertainty_m=0.02,
        fixed_allowance_m=0.02,
        horizon_s=0.2,
        command_latency_s=0.1,
        wheelbase_m=0.30,
        braking_decel_mps2=0.5,
    )
