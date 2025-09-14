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
- System service: `lawnberry-auto-redeploy.service` runs the watcher at boot from `/opt/lawnberry`.
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

Manual one-off run
```bash
# from source tree
bash scripts/auto_rebuild_deploy.sh
```

Security and platform notes
- Runs as user `pi` with hardened systemd settings.
- Uses inotify; installer ensures `inotify-tools` is present.
- All builds and syncs adhere to Raspberry Pi OS Bookworm constraints.
