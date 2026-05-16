"""Unit tests for LocalizationService.

All tests are runnable with no hardware. Use:
    SIM_MODE=1 uv run pytest tests/unit/test_localization_service.py -v
"""


# --- Task 2: model imports ---------------------------------------------------

def test_pose_quality_enum_members():
    from backend.src.services.localization_service import PoseQuality
    members = {q.value for q in PoseQuality}
    assert members == {"rtk_fixed", "gps_float", "gps_degraded", "dead_reckoning", "stale"}


def test_localization_state_defaults():
    from backend.src.services.localization_service import LocalizationState
    state = LocalizationState()
    assert state.current_position is None
    assert state.heading is None
    assert state.gps_cog is None
    assert state.velocity is None
    assert state.quality.value == "stale"
    assert state.dead_reckoning_active is False
    assert state.dead_reckoning_drift is None
    assert state.last_gps_fix is None


# --- Task 3: LocalizationService core behavior ------------------------------

from datetime import UTC, datetime, timedelta

import pytest

from backend.src.models import GpsReading, ImuReading, SensorData


@pytest.fixture()
def loc():
    """LocalizationService with no config file (defaults to zero offsets)."""
    from backend.src.services.localization_service import LocalizationService
    return LocalizationService(
        imu_yaw_offset=0.0,
        antenna_forward_m=0.0,
        antenna_right_m=0.0,
        max_fix_age_seconds=2.0,
        max_accuracy_m=5.0,
        alignment_file=None,
    )


@pytest.mark.asyncio
async def test_update_with_gps_sets_position(loc):
    state = await loc.update(
        SensorData(gps=GpsReading(latitude=37.0, longitude=-122.0, accuracy=1.0))
    )
    assert state.current_position is not None
    assert state.current_position.latitude == pytest.approx(37.0)
    assert state.dead_reckoning_active is False
    assert state.last_gps_fix is not None


@pytest.mark.asyncio
async def test_update_with_imu_sets_heading(loc):
    state = await loc.update(
        SensorData(
            gps=GpsReading(latitude=37.0, longitude=-122.0, accuracy=1.0),
            imu=ImuReading(yaw=45.0, calibration_status="fully_calibrated"),
        )
    )
    assert state.heading is not None


@pytest.mark.asyncio
async def test_update_with_stale_gps_sets_dead_reckoning(loc):
    # First give a GPS fix
    await loc.update(
        SensorData(gps=GpsReading(latitude=37.0, longitude=-122.0, accuracy=1.0))
    )
    # Then provide IMU only (no GPS) — should activate dead reckoning
    state = await loc.update(
        SensorData(imu=ImuReading(yaw=0.0, calibration_status="fully_calibrated"))
    )
    assert state.dead_reckoning_active is True


@pytest.mark.asyncio
async def test_gps_fix_is_fresh_false_when_no_fix(loc):
    assert loc.gps_fix_is_fresh() is False


@pytest.mark.asyncio
async def test_gps_fix_is_fresh_true_after_update(loc):
    await loc.update(
        SensorData(gps=GpsReading(latitude=37.0, longitude=-122.0, accuracy=1.0))
    )
    assert loc.gps_fix_is_fresh() is True


@pytest.mark.asyncio
async def test_position_is_verified_false_without_gps(loc):
    assert loc.position_is_verified() is False


@pytest.mark.asyncio
async def test_position_is_verified_false_when_dead_reckoning(loc):
    await loc.update(
        SensorData(gps=GpsReading(latitude=37.0, longitude=-122.0, accuracy=1.0))
    )
    loc.state.dead_reckoning_active = True
    assert loc.position_is_verified() is False


@pytest.mark.asyncio
async def test_antenna_offset_applied_when_configured():
    from backend.src.services.localization_service import LocalizationService
    loc = LocalizationService(
        imu_yaw_offset=0.0,
        antenna_forward_m=-0.46,
        antenna_right_m=0.0,
        max_fix_age_seconds=2.0,
        max_accuracy_m=5.0,
        alignment_file=None,
    )
    # heading north, antenna 0.46m behind center → center is north of antenna
    loc.state.heading = 0.0
    state = await loc.update(
        SensorData(gps=GpsReading(latitude=40.0, longitude=-75.0, accuracy=0.03))
    )
    assert state.current_position is not None
    expected_lat = 40.0 + 0.46 / 111_320.0
    assert state.current_position.latitude == pytest.approx(expected_lat)


@pytest.mark.asyncio
async def test_pose_quality_rtk_fixed_when_high_accuracy(loc):
    state = await loc.update(
        SensorData(gps=GpsReading(latitude=37.0, longitude=-122.0, accuracy=0.02))
    )
    from backend.src.services.localization_service import PoseQuality
    assert state.quality == PoseQuality.RTK_FIXED


@pytest.mark.asyncio
async def test_pose_quality_gps_degraded_when_poor_accuracy(loc):
    state = await loc.update(
        SensorData(gps=GpsReading(latitude=37.0, longitude=-122.0, accuracy=8.0))
    )
    from backend.src.services.localization_service import PoseQuality
    assert state.quality == PoseQuality.GPS_DEGRADED


@pytest.mark.asyncio
async def test_pose_quality_stale_when_no_data(loc):
    from backend.src.services.localization_service import PoseQuality
    assert loc.state.quality == PoseQuality.STALE


# --- Heading bootstrap -------------------------------------------------------

@pytest.mark.asyncio
async def test_bootstrap_alignment_snaps_from_gps_cog():
    """Replay the GPS-COG bootstrap sequence verified in test_navigation_service.py."""
    from backend.src.services.localization_service import LocalizationService

    loc = LocalizationService(
        imu_yaw_offset=0.0,
        antenna_forward_m=0.0,
        antenna_right_m=0.0,
        max_fix_age_seconds=2.0,
        max_accuracy_m=5.0,
        alignment_file=None,
    )
    loc.begin_bootstrap()
    assert loc.bootstrap_active is True

    started_at = datetime.now(UTC)
    # 6 ticks: tick 0 has no previous position, ticks 1-5 each produce a COG
    # reading.  The snap fires when _gps_cog_history reaches 5 entries and
    # going_straight is confirmed (requires >= 5 samples in history).
    for index in range(6):
        await loc.update(
            SensorData(
                gps=GpsReading(
                    latitude=37.0 + index * 0.000005,
                    longitude=-122.0,
                    accuracy=0.03,
                    timestamp=started_at + timedelta(seconds=index),
                ),
                imu=ImuReading(yaw=90.0, calibration_status="fully_calibrated"),
            )
        )

    assert loc.alignment_sample_count == 1
    assert loc.alignment_ready is True
    # session alignment should have been snapped so that heading ≈ 0° (north)
    assert loc.state.heading == pytest.approx(0.0, abs=1.0)
    assert loc.state.gps_cog == pytest.approx(0.0, abs=1.0)


@pytest.mark.asyncio
async def test_bootstrap_end_clears_active_flag():
    from backend.src.services.localization_service import LocalizationService

    loc = LocalizationService(
        imu_yaw_offset=0.0,
        antenna_forward_m=0.0,
        antenna_right_m=0.0,
        max_fix_age_seconds=2.0,
        max_accuracy_m=5.0,
        alignment_file=None,
    )
    loc.begin_bootstrap()
    loc.end_bootstrap()
    assert loc.bootstrap_active is False


@pytest.mark.asyncio
async def test_reset_clears_alignment():
    from backend.src.services.localization_service import LocalizationService

    loc = LocalizationService(
        imu_yaw_offset=0.0,
        antenna_forward_m=0.0,
        antenna_right_m=0.0,
        max_fix_age_seconds=2.0,
        max_accuracy_m=5.0,
        alignment_file=None,
    )
    loc._session_heading_alignment = 45.0
    loc._heading_alignment_sample_count = 3
    loc.reset_for_mission()
    assert loc._session_heading_alignment == pytest.approx(0.0)
    assert loc._heading_alignment_sample_count == 0
    assert loc.alignment_ready is False


# --- Alignment persistence ---------------------------------------------------

def test_load_alignment_from_file(tmp_path):
    import json

    from backend.src.services.localization_service import LocalizationService

    align_file = tmp_path / "imu_alignment.json"
    align_file.write_text(json.dumps({
        "session_heading_alignment": 123.4,
        "sample_count": 5,
        "source": "test",
    }))
    loc = LocalizationService(
        imu_yaw_offset=0.0,
        antenna_forward_m=0.0,
        antenna_right_m=0.0,
        max_fix_age_seconds=2.0,
        max_accuracy_m=5.0,
        alignment_file=align_file,
    )
    assert loc._session_heading_alignment == pytest.approx(123.4)
    assert loc._heading_alignment_sample_count == 5


def test_save_alignment_to_file(tmp_path):
    import json

    from backend.src.services.localization_service import LocalizationService

    align_file = tmp_path / "imu_alignment.json"
    loc = LocalizationService(
        imu_yaw_offset=0.0,
        antenna_forward_m=0.0,
        antenna_right_m=0.0,
        max_fix_age_seconds=2.0,
        max_accuracy_m=5.0,
        alignment_file=align_file,
    )
    loc._session_heading_alignment = 77.5
    loc._heading_alignment_sample_count = 2
    loc.save_alignment(source="test_save")

    data = json.loads(align_file.read_text())
    assert data["session_heading_alignment"] == pytest.approx(77.5, abs=0.01)
    assert data["sample_count"] == 2
    assert data["source"] == "test_save"


# --- reset_for_mission with saved_alignment -----------------------------------

def test_reset_for_mission_applies_saved_alignment():
    """reset_for_mission(saved_alignment=...) restores heading instead of resetting to 0°."""
    from backend.src.services.localization_service import LocalizationService

    loc = LocalizationService(
        imu_yaw_offset=0.0,
        antenna_forward_m=0.0,
        antenna_right_m=0.0,
        max_fix_age_seconds=2.0,
        max_accuracy_m=5.0,
        alignment_file=None,
    )
    loc._session_heading_alignment = 99.9
    loc._heading_alignment_sample_count = 10

    loc.reset_for_mission(saved_alignment=(33.3, 2, 1800.0))

    assert loc._session_heading_alignment == pytest.approx(33.3, abs=0.01)
    assert loc._heading_alignment_sample_count == 2
    assert loc._require_gps_heading_alignment is True
    # alignment_ready: not require OR samples>0 → True
    assert loc.alignment_ready is True


def test_reset_for_mission_saved_alignment_enforces_min_one_sample():
    """reset_for_mission clamps sample_count to at least 1 when saved is 0."""
    from backend.src.services.localization_service import LocalizationService

    loc = LocalizationService(
        imu_yaw_offset=0.0,
        antenna_forward_m=0.0,
        antenna_right_m=0.0,
        max_fix_age_seconds=2.0,
        max_accuracy_m=5.0,
        alignment_file=None,
    )
    loc.reset_for_mission(saved_alignment=(45.0, 0, 600.0))

    assert loc._heading_alignment_sample_count == 1
    assert loc.alignment_ready is True


def test_reset_for_mission_none_still_resets_to_zero():
    """reset_for_mission(saved_alignment=None) behaves like the original reset."""
    from backend.src.services.localization_service import LocalizationService

    loc = LocalizationService(
        imu_yaw_offset=0.0,
        antenna_forward_m=0.0,
        antenna_right_m=0.0,
        max_fix_age_seconds=2.0,
        max_accuracy_m=5.0,
        alignment_file=None,
    )
    loc._session_heading_alignment = 55.0
    loc._heading_alignment_sample_count = 5

    loc.reset_for_mission(saved_alignment=None)

    assert loc._session_heading_alignment == pytest.approx(0.0)
    assert loc._heading_alignment_sample_count == 0
    assert loc.alignment_ready is False


def test_reset_for_mission_saved_alignment_does_not_overwrite_disk(tmp_path):
    """When saved_alignment is applied, the disk file is NOT overwritten with a reset record."""
    import json
    from backend.src.services.localization_service import LocalizationService

    align_file = tmp_path / "imu_alignment.json"
    align_file.write_text(json.dumps({
        "session_heading_alignment": 11.1,
        "sample_count": 1,
        "source": "gps_cog_snap",
    }))
    loc = LocalizationService(
        imu_yaw_offset=0.0,
        antenna_forward_m=0.0,
        antenna_right_m=0.0,
        max_fix_age_seconds=2.0,
        max_accuracy_m=5.0,
        alignment_file=align_file,
    )

    loc.reset_for_mission(saved_alignment=(11.1, 1, 100.0))

    data = json.loads(align_file.read_text())
    assert data.get("source") == "gps_cog_snap", (
        "Disk source should remain gps_cog_snap, not be overwritten with mission_start_reset"
    )
