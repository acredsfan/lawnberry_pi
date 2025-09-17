# Auto Rebuild & Deploy

This utility watches the workspace and automatically rebuilds and redeploys only what changed, then syncs updates to the canonical runtime at `/opt/lawnberry`.

What it does
- Web UI changes (`web-ui/src`, `public`, `vite.config.*`):
  - Runs a bounded, conditional Vite production build (`scripts/auto_rebuild_web_ui.sh`) only when sources changed.
  - Syncs `web-ui/dist/` to `/opt/lawnberry/web-ui/dist/` using the fast deploy path.
- Web UI dependency changes (`web-ui/package.json` or lockfiles):
  - Reinstalls dependencies and performs a full `dist` sync.
- Python or config changes (`src/**`, `config/**`, `pyproject.toml`):
  - Runs fast deploy to `/opt/lawnberry` and restarts core services.
- Service unit changes (`*.service` in `src/**`):
  - Reinstalls and replaces systemd units (no appending), reloads daemon, restarts services.
- Requirements changes (`requirements*.txt`):
  - Ensures `/opt/lawnberry/venv` has updated dependencies via the deploy script.

How it runs
- Watcher script: `scripts/auto_rebuild_deploy.sh` (inotify-based, debounced)
- System service: `lawnberry-auto-redeploy.service` runs the watcher at boot as user `pi` and watches the editable workspace at `/home/pi/lawnberry`.
- The watcher deploys changes to the canonical runtime at `/opt/lawnberry` using the repo scripts.
- Timeouts are enforced throughout to prevent hangs; long commands are bounded.

Enable or disable
- Installed and enabled by the installer. To manage manually:
```bash
# enable and start
sudo systemctl enable lawnberry-auto-redeploy
sudo systemctl start lawnberry-auto-redeploy

# stop and disable
sudo systemctl stop lawnberry-auto-redeploy
sudo systemctl disable lawnberry-auto-redeploy
```

Environment knobs
- `DEBOUNCE_SECONDS`: debounce bursty events (default 2).
- `FAST_DEPLOY_MAX_SECONDS`: cap per-deploy duration (default 70).
- `FAST_DEPLOY_SERVICE_TIMEOUT`: per-service restart timeout (default 10).
- `SKIP_AUTO_REBUILD=1`: causes web UI auto rebuild script to skip builds.
- `WATCH_ROOT`: override the root directory the watcher monitors. Default is the repo root when running manually; the systemd unit sets this effectively by running in `/home/pi/lawnberry`.

Manual one-off run
```bash
# from source tree
bash scripts/auto_rebuild_deploy.sh
```

Troubleshooting
- Service not activating on file changes:
  - Ensure it runs as user `pi` and watches `/home/pi/lawnberry` (unit file updated accordingly).
  - Check logs: `sudo journalctl -u lawnberry-auto-redeploy -n 200 --no-pager`
  - Verify inotify-tools: `which inotifywait || sudo apt-get install -y inotify-tools`
  - Confirm the watch set includes your paths (script logs “Starting watcher …”).
  - Verify deploy scripts exist: `scripts/lawnberry-deploy.sh`, `scripts/auto_rebuild_web_ui.sh`.

Security and platform notes
- Runs as user `pi` with hardened systemd settings.
- Uses inotify; installer ensures `inotify-tools` is present.
- All builds and syncs adhere to Raspberry Pi OS Bookworm constraints.

Log markers (what to look for in `journalctl`)
- Detection lines (trigger):
  - `DETECT: UI source/assets changed -> <path>`
  - `DETECT: UI pkg/lock changed -> <path>`
  - `DETECT: code/config changed -> <path>`
  - `DETECT: service unit changed -> <path>`
  - `DETECT: requirements/pyproject changed -> <path>`
- Action initiation lines:
  - `UI: DETECTED change -> INIT build & minimal dist deploy`
  - `UI: DETECTED pkg/lock change -> INIT build & FULL dist deploy`
  - `CODE: DETECTED src/config change -> INIT fast deploy`
  - `SERVICE: DETECTED *.service change -> INIT reinstall & replace`
  - `REQS: DETECTED requirements/pyproject change -> INIT venv update deploy`
- Completion lines (success/failure):
  - `UI: DEPLOY SUCCESS (dist minimal|dist full)` or `UI: DEPLOY FAILED (...)`
  - `CODE: DEPLOY SUCCESS` or `CODE: DEPLOY FAILED`
  - `SERVICE: REINSTALL SUCCESS` or `SERVICE: REINSTALL FAILED`
  - `REQS: DEPLOY SUCCESS (venv deps ensured)` or `REQS: DEPLOY FAILED (venv deps)`
  - Summary markers: `ACTION COMPLETE -> SUCCESS|FAILURE` per category

Heartbeat lines:
  - Every `HEARTBEAT_INTERVAL` seconds (default 300) the watcher emits:
    - `[2025-09-17T12:34:56Z] [auto-redeploy] HEARTBEAT: watcher alive (pid=XXXX)`
  - Absence of heartbeat for > 2 × interval suggests the watcher is stalled or service stopped.

Adjust heartbeat interval (e.g. 180s):
```bash
sudo systemctl edit lawnberry-auto-redeploy
# Add under [Service]:
# Environment="HEARTBEAT_INTERVAL=180"
sudo systemctl daemon-reload
sudo systemctl restart lawnberry-auto-redeploy
```
