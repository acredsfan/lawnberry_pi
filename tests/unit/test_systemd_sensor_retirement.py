from pathlib import Path


def test_inert_sensor_unit_is_retired_by_installer() -> None:
    unit = Path("systemd/lawnberry-sensors.service")
    installer = Path("systemd/install_services.sh").read_text(encoding="utf-8")

    assert not unit.exists()
    assert 'cp "$SCRIPT_DIR/lawnberry-sensors.service"' not in installer
    assert "systemctl enable lawnberry-sensors.service" not in installer
    assert "systemctl start lawnberry-sensors" not in installer
    assert "systemctl disable --now lawnberry-sensors.service" in installer
    assert 'rm -f "$SYSTEMD_DIR/lawnberry-sensors.service"' in installer


def test_backup_and_restore_do_not_manage_retired_sensor_unit() -> None:
    backup = Path("scripts/backup_system.sh").read_text(encoding="utf-8")
    restore = Path("scripts/restore_system.sh").read_text(encoding="utf-8")

    assert "lawnberry-sensors.service" not in backup
    assert "lawnberry-sensors.service" not in restore
