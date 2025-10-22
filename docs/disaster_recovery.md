# Disaster Recovery and Backups

This guide explains how LawnBerry Pi creates backups, how to verify them, and how to restore the system after a failure.

## What gets backed up

The automated backup includes:

- Configuration files: `config/*.json`, `config/*.yaml`
- Data JSON state: selected `data/*.json`
- SQLite database: `data/lawnberry.db` (consistent snapshot)
- Environment file: `.env` (if present; stored with 0600 permissions)
- Metadata: system info and systemd statuses
- Manifest: `MANIFEST.json` listing files with sizes and SHA256 checksums

Backups are stored under `/home/pi/lawnberry/backups/` as compressed archives named `lawnberry-backup-YYYYmmdd_HHMMSS.tar.gz` with a companion `.sha256` file.

Retention keeps the last 14 days by default. Adjust via `BACKUP_RETENTION_DAYS` when running the backup.

## Enabling scheduled backups

1. Install the service and timer:

```bash
sudo cp systemd/lawnberry-backup.service /etc/systemd/system/
sudo cp systemd/lawnberry-backup.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now lawnberry-backup.timer
```

2. Check timer status:

```bash
systemctl list-timers --all | grep lawnberry-backup
journalctl -u lawnberry-backup.service -e
```

## Run a manual backup

```bash
/home/pi/lawnberry/scripts/backup_system.sh
```

Optional environment variables:

- `BACKUP_ROOT_DIR` — target directory (default: `/home/pi/lawnberry/backups`)
- `BACKUP_RETENTION_DAYS` — retention in days (default: `14`)

## Verify a backup

```bash
cd /home/pi/lawnberry/backups
sha256sum -c lawnberry-backup-YYYYmmdd_HHMMSS.tar.gz.sha256
```

You can also inspect `MANIFEST.json` inside the archive:

```bash
mkdir -p /tmp/lb-verify && tar -xzf lawnberry-backup-YYYYmmdd_HHMMSS.tar.gz -C /tmp/lb-verify MANIFEST.json
jq . /tmp/lb-verify/MANIFEST.json
```

## Restore from a backup

WARNING: Restoring will overwrite configuration and database. Prefer running this during maintenance windows.

1. Stop application services and run restore:

```bash
# Dry run (shows actions only)
DRY_RUN=1 /home/pi/lawnberry/scripts/restore_system.sh /home/pi/lawnberry/backups/lawnberry-backup-YYYYmmdd_HHMMSS.tar.gz

# Execute restore
/home/pi/lawnberry/scripts/restore_system.sh /home/pi/lawnberry/backups/lawnberry-backup-YYYYmmdd_HHMMSS.tar.gz
```

By default, the script will stop and start LawnBerry services via systemd. To skip service control (e.g., inside a container), set `SKIP_SYSTEMCTL=1`.

During restore, the current state is saved at `/home/pi/lawnberry/backups/restore-pre-<timestamp>/` for safety.

## Security considerations

- Backup archives and checksums are created with owner-only permissions (0600).
- Archives may contain credentials in `.env`. Protect the backups (e.g., store on encrypted media if exported off-device).

## Troubleshooting

- Ensure `sqlite3` is installed for consistent database snapshots. The backup script will fall back to a plain copy if missing.
- Check logs:

```bash
journalctl -u lawnberry-backup.service -e
```

- Verify disk space: Backups require enough free space for a temporary snapshot and the compressed archive.

---

For production deployments, consider syncing `/home/pi/lawnberry/backups/` to an external storage or NAS with `rsync` or `rclone` and encrypting archives at rest.
