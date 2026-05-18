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


# ---------------------------------------------------------------------------
# Fix 5: Bootstrap multi-sample snap
# ---------------------------------------------------------------------------

def _make_sensor_fix5(gps_cog: float, imu_yaw: float = 90.0) -> SensorData:
    """Build a SensorData tick with a controlled GPS COG (receiver-reported)."""
    return SensorData(
        gps=GpsReading(
            latitude=37.0,
            longitude=-122.0,
            accuracy=0.03,
            heading=gps_cog,
            speed=1.0,
        ),
        imu=ImuReading(yaw=imu_yaw, calibration_status="fully_calibrated"),
    )


def _make_sensor_no_imu(gps_cog: float) -> SensorData:
    """Build a SensorData tick with GPS COG but no IMU reading."""
    return SensorData(
        gps=GpsReading(
            latitude=37.0,
            longitude=-122.0,
            accuracy=0.03,
            heading=gps_cog,
            speed=1.0,
        ),
    )


@pytest.mark.asyncio
async def test_bootstrap_snap_uses_cog_mean_not_spike_reading():
    """Snap delta uses mean of consistent COG buffer, rejecting a spike reading.

    Sequence design:
      Ticks 1-7 COG values: [210, 355(spike), 210, 210, 210, 225, 225]

      - Tick 3: buffer=[210,355,210] — spike present, going_straight=False
      - Ticks 4-5: spike still in buffer, no snap
      - Tick 6: pop(0)=210 → buffer=[355,210,210,210,225] — spike still, no snap
      - Tick 7: pop(0)=355 → buffer=[210,210,210,225,225]
        cog_mean ≈ 216°, max_dev ≤ 9° → going_straight=True → SNAP fires.
        current_tick cog=225, but cog_mean≈216°.

    With the bug (uses current cog=225): heading ends up near 225°.
    With the fix (uses cog_mean≈216°): heading ends up near 216°.
    """
    from backend.src.services.localization_service import LocalizationService

    loc = LocalizationService(alignment_file=None)
    loc.reset_for_mission()
    loc.begin_bootstrap()

    cog_sequence = [210.0, 355.0, 210.0, 210.0, 210.0, 225.0, 225.0]
    for cog in cog_sequence:
        await loc.update(_make_sensor_fix5(gps_cog=cog))

    assert loc._heading_alignment_sample_count == 1, (
        "Snap should have fired exactly once during the 7-tick sequence"
    )
    assert loc.alignment_ready is True
    assert loc.state.heading is not None

    from backend.src.nav.localization_helpers import heading_delta as hd

    # cog_mean of [210,210,210,225,225] ≈ 216°.  Allow ±8° for circular mean
    # rounding; the key is the heading must NOT be near 225° (the spike-tick cog).
    assert abs(hd(loc.state.heading, 216.0)) < 8.0, (
        f"Heading {loc.state.heading:.1f}° should be near cog_mean 216° "
        f"(not the spike-tick cog 225°)"
    )


@pytest.mark.asyncio
async def test_end_bootstrap_fallback_commits_mean_when_no_snap():
    """If bootstrap ends without a consistent snap, mean of buffer is committed."""
    from backend.src.services.localization_service import LocalizationService

    loc = LocalizationService(alignment_file=None)
    loc.reset_for_mission()
    loc.begin_bootstrap()

    # Feed only 2 ticks — fewer than 3 required for going_straight → no snap fires.
    for cog in [210.0, 211.0]:
        await loc.update(_make_sensor_no_imu(gps_cog=cog))

    assert loc._heading_alignment_sample_count == 0, "No snap should have fired yet"

    # Call end_bootstrap() — fallback should commit the mean of [210, 211]
    loc.end_bootstrap()

    assert loc._heading_alignment_sample_count == 1
    assert loc.alignment_ready is True
    assert loc.state.heading is not None

    from backend.src.nav.localization_helpers import heading_delta as hd

    assert abs(hd(loc.state.heading, 210.5)) < 10.0, (
        f"Heading {loc.state.heading:.1f}° should be near fallback mean 210.5°"
    )


@pytest.mark.asyncio
async def test_end_bootstrap_fallback_logs_warning_when_spread_high(caplog):
    """end_bootstrap() fallback logs WARNING when buffer spread exceeds 15°."""
    import logging
    from backend.src.services.localization_service import LocalizationService

    loc = LocalizationService(alignment_file=None)
    loc.reset_for_mission()
    loc.begin_bootstrap()

    # High-spread readings — 60° spread → never going_straight
    for cog in [180.0, 220.0, 240.0]:
        await loc.update(_make_sensor_no_imu(gps_cog=cog))

    assert loc._heading_alignment_sample_count == 0

    with caplog.at_level(logging.WARNING, logger="backend.src.services.localization_service"):
        loc.end_bootstrap()

    assert any("bootstrap" in r.message.lower() for r in caplog.records), (
        "Expected bootstrap warning when spread > 15°"
    )
    assert loc._heading_alignment_sample_count == 1


@pytest.mark.asyncio
async def test_reset_for_mission_clears_cog_buffer():
    """reset_for_mission() flushes the COG buffer so each mission starts clean."""
    from backend.src.services.localization_service import LocalizationService

    loc = LocalizationService(alignment_file=None)
    loc.begin_bootstrap()
    for cog in [180.0, 181.0, 182.0]:
        await loc.update(_make_sensor_no_imu(gps_cog=cog))

    assert len(loc._gps_cog_history) > 0

    loc.reset_for_mission()
    assert loc._gps_cog_history == [], "COG history should be cleared by reset_for_mission"
