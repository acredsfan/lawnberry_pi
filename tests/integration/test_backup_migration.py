import os
import subprocess
import tempfile
from pathlib import Path


def test_backup_and_restore_roundtrip():
    # Create a temporary source directory with sample data
    with tempfile.TemporaryDirectory() as src_dir:
        with tempfile.TemporaryDirectory() as dest_dir:
            with tempfile.TemporaryDirectory() as restore_dir:
                src = Path(src_dir)
                (src / "config").mkdir()
                (src / "config" / "system.json").write_text(
                    '{"telemetry": {"cadence_hz": 5}}'
                )
                (src / "db").mkdir()
                (src / "db" / "lawnberry.db").write_text("dummy-sqlite")

                # Run backup script pointing at our temp dirs
                backup_script = str(
                    Path(__file__).resolve().parents[2] / "scripts" / "backup.sh"
                )
                proc = subprocess.run(
                    [
                        backup_script,
                        "--src",
                        src_dir,
                        "--dest",
                        dest_dir,
                        "--name",
                        "test-archive.tar.gz",
                    ],
                    capture_output=True,
                    text=True,
                    check=True,
                )
                archive_path = proc.stdout.strip()
                assert os.path.isfile(archive_path)

                # Restore to a clean directory
                restore_script = str(
                    Path(__file__).resolve().parents[2] / "scripts" / "restore.sh"
                )
                subprocess.run(
                    [
                        restore_script,
                        "--archive",
                        archive_path,
                        "--target",
                        restore_dir,
                    ],
                    check=True,
                )

                # Verify files restored
                r = Path(restore_dir)
                assert (r / "config" / "system.json").exists()
                assert (r / "db" / "lawnberry.db").exists()
                restored_config = (r / "config" / "system.json").read_text().strip()
                assert restored_config == '{"telemetry": {"cadence_hz": 5}}'
