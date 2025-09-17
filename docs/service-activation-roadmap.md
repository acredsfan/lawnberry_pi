# Service Activation Roadmap

Purpose: Structured plan for bringing currently inactive or optional services online safely (power_management, weather, system_integration, sensor_fusion, vision) while maintaining telemetry stability and resource headroom on Raspberry Pi OS Bookworm.

## Current Status Snapshot

| Service | Unit | Enabled | Running | Critical (system.yaml) | Notes |
|---------|------|---------|---------|------------------------|-------|
| Power Management | lawnberry-power.service | no | no | false | INA3221 data presently published via sensor service only; SoC & solar modeling inactive |
| Weather | lawnberry-weather.service | no | no | false | Needs API key; scheduling & solar prediction features unused |
| System Integration | lawnberry-system.service | yes? (enabled flag) | no | orchestrator | Placeholder logic in API; full orchestrator idle |
| Sensor Fusion | lawnberry-sensor-fusion.service | no | no | false | Safety running without fused localization; Kalman & obstacle fusion idle |
| Vision | lawnberry-vision.service | no | no | false | Camera + Coral pipeline disabled to save CPU/memory |

## Activation Priorities

1. Power Management (adds structured metrics & modes; low incremental risk once channel mapping fixed)
2. Weather (adds predictive scheduling & solar synergy; requires valid API key env var)
3. System Integration (only if consolidating supervision; otherwise keep disabled to avoid conflict)
4. Sensor Fusion (after reliable raw telemetry + GPS fix quality; start in observe-only mode)
5. Vision (after confirming thermal/cpu headroom and Coral availability)

## Prerequisites per Service

### Power Management
- Correct INA3221 channel mapping (battery vs solar) and current scaling validated
- LiFePO4 SoC estimation implemented (voltage window 10.0–14.6V, OCV-based smoothing)
- Distinct MQTT fields: `battery_voltage`, `battery_current`, `solar_voltage`, `solar_current`, `battery_soc` (0–1 or %) and no overlap with legacy fields

### Weather
- `OPENWEATHER_API_KEY` present in `/opt/lawnberry/.env` and loaded by runtime
- MQTT topics: `weather/current`, `weather/forecast`, `weather/alerts`, `weather/mowing_conditions` verify publishing without spamming rate limit

### System Integration
- Decide single orchestration layer (either enable or explicitly disable) to avoid duplicated restarts
- Health & restart policies in `system.yaml` aligned with actual unit dependencies

### Sensor Fusion
- Stable GPS (≥6 sats, RTK optional) & IMU timing; ToF stable
- CPU idle margin > 30%; memory free > 400MB
- Dry-run: subscribe & compute fused pose without driving actuators; publish to `sensors/localization` & `sensors/obstacles` after burn-in

### Vision
- Camera `/dev/video0` accessible; Coral TPU detection (if used) logged
- Model paths exist; fallback CPU model performance acceptable
- Cap FPS dynamically by CPU load (future improvement)

## Activation Procedure (Incremental)

### Phase A: Fix Power Metrics
1. Implement INA3221 channel mapping with config override:
   ```yaml
   power_management:
     channels:
       battery: 1  # INA3221 channel index
       solar: 2
   ```
2. Add raw diagnostic topic (optional): `power/raw` with per-channel voltage/current
3. Compute SoC using smoothed voltage + optional coulomb counter placeholder
4. Verify with:
   ```bash
   timeout 8s mosquitto_sub -t 'lawnberry/power/#' -C 5 -W 6 -v
   ```
5. Enable service: `sudo systemctl enable --now lawnberry-power.service`

### Phase B: Weather
1. Ensure `/opt/lawnberry/.env` contains `OPENWEATHER_API_KEY`
2. Log key detection (do NOT log key value) at startup
3. Enable and verify one publish cycle after ~5–10s

### Phase C: System Integration (Optional Adoption)
1. Disable any overlapping watchdog logic in ad-hoc scripts
2. Enable `lawnberry-system.service` and observe restart orchestration logs

### Phase D: Sensor Fusion
1. Start service with reduced rates (config override) if CPU near threshold
2. Monitor latency logs; if stable, increase to target rates

### Phase E: Vision
1. Start with `enable_tpu: false` to validate CPU path
2. Once stable, enable TPU and compare FPS + latency metrics

## Rollback Strategy
For any instability (latency spikes, missed sensor cycles, thermal alarms):
```bash
sudo systemctl stop lawnberry-vision.service lawnberry-sensor-fusion.service lawnberry-power.service lawnberry-weather.service lawnberry-system.service || true
sudo systemctl disable lawnberry-vision.service lawnberry-sensor-fusion.service lawnberry-power.service lawnberry-weather.service lawnberry-system.service || true
```

## Open Tasks (Tracking)
- [x] Implement INA3221 channel mapping & SoC calculation (Phase A)
- [x] Add environment loader verification for map provider (multi-var runtime resolution) & weather service
- [ ] Decide orchestration ownership (system_integration vs individual units)
- [ ] Provide sensor fusion dry-run mode flag
- [ ] Add dynamic FPS adaptation for vision service (future)

## Verification Commands Quick Block
```bash
# Power metrics
timeout 8s mosquitto_sub -t 'lawnberry/power/#' -C 5 -W 6 -v
# Weather current conditions
timeout 8s mosquitto_sub -t 'lawnberry/weather/current' -C 1 -W 6 -v
# Fusion localization (after enabling)
timeout 8s mosquitto_sub -t 'lawnberry/sensors/localization' -C 1 -W 6 -v
# Vision detections
timeout 12s mosquitto_sub -t 'lawnberry/vision/detections' -C 1 -W 10 -v

# Runtime Google Maps key resolution
timeout 5s curl -fsS :8000/api/v1/public/config | jq '.google_maps'
```

## Activation Command Snippets (Safe Sequence)

```bash
# 1. Power management (after verifying new INA3221 fields appear)
sudo systemctl enable --now lawnberry-power.service

# 2. Weather (ensure OPENWEATHER_API_KEY present)
grep -q OPENWEATHER_API_KEY /opt/lawnberry/.env && sudo systemctl enable --now lawnberry-weather.service

# 3. Sensor fusion (dry-run / observe mode if supported by config flag)
sudo systemctl enable --now lawnberry-sensor-fusion.service

# 4. Vision (start without TPU first)
sudo systemctl enable --now lawnberry-vision.service
```

## Auto-Redeploy Heartbeat Troubleshooting

If deployments appear stalled:

```bash
sudo journalctl -u lawnberry-auto-redeploy -n 200 --no-pager | grep HEARTBEAT | tail
```

Expected every ~300s (unless `HEARTBEAT_INTERVAL` overridden). If missing:
1. Check service status: `systemctl --user status lawnberry-auto-redeploy || sudo systemctl status lawnberry-auto-redeploy`
2. Restart: `sudo systemctl restart lawnberry-auto-redeploy`
3. Confirm first lines show: `Starting watcher using inotifywait` and path classifications.

## Map Provider Runtime Key Notes

Public config endpoint (`/api/v1/public/config`) now resolves Google Maps API key from the first non-empty of:
`GOOGLE_MAPS_API_KEY`, `REACT_APP_GOOGLE_MAPS_API_KEY`, `VITE_GOOGLE_MAPS_API_KEY`, `VITE_REACT_APP_GOOGLE_MAPS_API_KEY`, `MAPS_API_KEY`.

Add one to `/opt/lawnberry/.env` and restart `lawnberry-api`:

```bash
echo 'GOOGLE_MAPS_API_KEY=YOUR_KEY_HERE' | sudo tee -a /opt/lawnberry/.env
sudo systemctl restart lawnberry-api
timeout 5s curl -fsS :8000/api/v1/public/config | jq '.google_maps.available'
```

---
Document will be updated as each phase is implemented.
