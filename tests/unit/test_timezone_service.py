import json
import os
import tempfile
import shutil
from datetime import datetime, timezone as dt_timezone

from backend.src.services.timezone_service import TimezoneInfo, detect_system_timezone


def test_detect_timezone_from_etc_timezone_file():
    base = tempfile.mkdtemp(prefix="tztest-")
    try:
        etc = os.path.join(base, "etc")
        os.makedirs(etc, exist_ok=True)
        with open(os.path.join(etc, "timezone"), "w", encoding="utf-8") as f:
            f.write("America/New_York\n")
        os.environ["LAWN_BERRY_DISABLE_GPS_TZ"] = "1"
        info = detect_system_timezone(base)
        assert info.timezone == "America/New_York"
        assert info.source == "system"
    finally:
        os.environ.pop("LAWN_BERRY_DISABLE_GPS_TZ", None)
        shutil.rmtree(base, ignore_errors=True)


def test_detect_timezone_from_localtime_symlink():
    base = tempfile.mkdtemp(prefix="tztest-")
    try:
        etc = os.path.join(base, "etc")
        share = os.path.join(base, "usr", "share", "zoneinfo")
        os.makedirs(etc, exist_ok=True)
        os.makedirs(os.path.join(share, "Europe"), exist_ok=True)
        # Create a dummy target to link to
        target = os.path.join(share, "Europe", "Paris")
        with open(target, "wb") as f:
            f.write(b"dummy")
        # Point localtime to target
        os.symlink(target, os.path.join(etc, "localtime"))
        os.environ["LAWN_BERRY_DISABLE_GPS_TZ"] = "1"
        info = detect_system_timezone(base)
        assert info.timezone == "Europe/Paris"
        assert info.source == "system"
    finally:
        os.environ.pop("LAWN_BERRY_DISABLE_GPS_TZ", None)
        shutil.rmtree(base, ignore_errors=True)


def test_detect_timezone_prefers_gps():
    info = detect_system_timezone(
        base_path="/",
        gps_lookup=lambda: (37.7749, -122.4194),
        cache=False,
    )
    assert info.timezone == "America/Los_Angeles"
    assert info.source == "gps"


def test_system_settings_endpoint_auto_sets_timezone(monkeypatch):
    from backend.src.api import rest

    monkeypatch.setattr(rest, "_system_settings", rest.SystemSettings())
    monkeypatch.setattr(rest, "_settings_last_modified", datetime.now(dt_timezone.utc))
    monkeypatch.setattr(
        rest,
        "detect_system_timezone",
        lambda: TimezoneInfo(timezone="Pacific/Honolulu", source="gps"),
    )

    class DummyRequest:
        headers = {}

    response = rest.get_settings_system(DummyRequest())
    payload = json.loads(response.body)
    assert payload["timezone"] == "Pacific/Honolulu"
    assert payload["timezone_source"] == "gps"
