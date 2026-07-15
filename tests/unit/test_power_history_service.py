from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from backend.src.core.persistence import PersistenceLayer
from backend.src.models.navigation_state import NavigationMode
from backend.src.services.energy_service import EnergyState
from backend.src.services.power_history_service import PowerHistoryService


class _Energy:
    def __init__(self) -> None:
        self.calls = 0

    def current_state(self) -> EnergyState:
        self.calls += 1
        return EnergyState(
            available=True,
            fresh=True,
            source="ina3221",
            sampled_at=datetime.now(UTC),
            sample_age_seconds=0.2,
            voltage=13.2,
            battery_current=-1.0,
            battery_power=-13.2,
            solar_power=4.0,
            load_power=13.2,
            soc_percent=70.0,
            capacity_wh=100.0,
            remaining_wh=70.0,
            return_reserve_percent=20.0,
            return_reserve_wh=20.0,
            critical_soc_percent=5.0,
        )


@pytest.mark.asyncio
async def test_history_uses_canonical_cached_energy_state(monkeypatch, tmp_path) -> None:
    from backend.src.services.navigation_service import NavigationService

    persistence = PersistenceLayer(str(tmp_path / "history.db"))
    energy = _Energy()
    service = PowerHistoryService(persistence, energy)
    nav = SimpleNamespace(
        navigation_state=SimpleNamespace(navigation_mode=NavigationMode.IDLE)
    )
    monkeypatch.setattr(NavigationService, "get_instance", classmethod(lambda cls: nav))

    await service._log_sample()

    rows = service.query_raw(hours=1.0)
    assert energy.calls == 1
    assert len(rows) == 1
    assert rows[0]["soc_pct"] == 70.0
    assert rows[0]["source"] == "ina3221"
    assert rows[0]["fresh"] is True


def test_history_migrates_provenance_columns(tmp_path) -> None:
    persistence = PersistenceLayer(str(tmp_path / "migration.db"))
    with persistence.get_connection() as conn:
        conn.execute(
            "CREATE TABLE power_history (id INTEGER PRIMARY KEY, ts REAL NOT NULL, "
            "iso_ts TEXT NOT NULL, batt_v REAL, batt_a REAL, batt_w REAL, solar_w REAL, "
            "load_w REAL, soc_pct REAL, activity TEXT NOT NULL DEFAULT 'idle')"
        )
        conn.commit()

    PowerHistoryService(persistence, _Energy())

    with persistence.get_connection() as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(power_history)")}
    assert {"source", "sample_age_s", "fresh"} <= columns
