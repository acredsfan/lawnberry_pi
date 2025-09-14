# Change Summary

This file lists all files modified in this commit and a brief description of the changes.

- `src/communication/client.py`: replaced unused MQTT callback parameters with underscores.
- `src/data_management/cache_manager.py`: removed unused `NavigationData` import.
- `src/data_management/data_manager.py`: removed unused imports and cleaned list.
- `src/data_management/database_manager.py`: fixed indentation and renamed unused `backup` parameter; removed unused model import.
- `src/hardware/managers.py`: removed unused imports.
- `src/hardware/plugin_system.py`: removed unused `Type` import.
- `src/hardware/sensor_service.py`: dropped unused helper import block.
- `src/navigation/ai_pattern_optimizer.py`: removed unused metric imports.
- `src/safety/maintenance_safety.py`: marked unused parameter with leading underscore.
- `src/system_integration/config_validator.py`: removed unused `urlparse` import.
- `src/system_integration/performance_service.py`: renamed unused context manager parameters.
- `src/system_integration/plugin_architecture.py`: removed unused `Type` import.
- `src/system_integration/remote_update_manager.py`: cleaned imports and indentation.
- `src/vision/coral_tpu_manager.py`: removed unused pycoral adapter imports and associated cleanup.
- `src/vision/ml_obstacle_detector.py`: marked unused `frame_shape` parameter.
- `src/vision/object_detector.py`: removed unused `SAFETY_DISTANCES` import.
- `src/weather/weather_mqtt.py`: prefixed unused MQTT callback parameters with underscores.
- `src/weather/weather_service.py`: corrected dummy context manager and marked unused parameters.
- `src/web_api/models.py`: removed unused `ConfigDict` import.
- `src/web_api/routers/enhanced_safety.py`: dropped unused schema imports.
- `src/web_api/routers/enhanced_user_experience.py`: removed unused middleware and auth imports.
- `src/web_api/routers/vision.py`: cleaned unused FastAPI and dashboard imports.
- `src/web_api/routers/websocket.py`: removed unused auth/model imports.
- `src/web_api/services/google_maps_service.py`: renamed unused context manager parameters.
- `src/web_api/test_api.py`: removed unused `MagicMock` import.

## 2025-09-14

- `src/hardware/sensor_service.py`: Publish compatibility alias `power/battery` in addition to canonical `sensors/power/data` to ensure UI and API receive power data.
- `src/web_api/main.py`: `/api/v1/status` now prefers `sensors/power/data` with fallback to `power/battery` when composing power info.
- `src/web_api/routers/power.py`: Battery endpoint reads from `sensors/power/data` with legacy fallback to `power/battery`.
- `web-ui/src/services/sensorDataService.ts`: Subscribe to `sensors/power/data` instead of legacy `power/battery` for real-time power data in UI.
- `src/vision/tpu_dashboard.py`: Made `get_dashboard_data` async to fix a SyntaxError (await used inside a non-async function) and align with callers.
- `scripts/test_advanced_tpu_integration.py`: Await `dashboard.get_dashboard_data()` accordingly.

Notes:
- This alignment establishes `sensors/power/data` as the canonical topic while retaining `power/battery` for backwards compatibility.
- Perform a fast deploy and restart services to see live power data in the UI.

## 2025-09-14 (comm system follow-up)

- `src/communication/service_manager.py`:
	- Instantiate MQTT client via module reference (`src.communication.client.MQTTClient`) to align with test patch target and improve DI/testability.
	- Defer MQTT handler setup from `__init__` to `initialize()` and make handler registration await-safe to avoid coroutine-not-awaited warnings with async mocks.

## 2025-09-14 (data pipeline + ToF)

- `src/web_api/mqtt_bridge.py`: Subscribe/cache per-ToF topics by adding `'sensors/tof/+'` to `_topic_mappings`, enabling API fallback that reads `sensors/tof/left` and `sensors/tof/right`.
- `docs/data-pipeline.md`: New documentation describing the end-to-end data flow (Hardware → MQTT → API/MQTTBridge → WebSocket → UI) for GPS, IMU, ToF, Environmental, Power, RC, and Camera stream.

## 2025-09-14 (auto-redeploy activation)

- `src/system_integration/lawnberry-auto-redeploy.service`: Run as user `pi`, watch `/home/pi/lawnberry`, adjust `WorkingDirectory` and `ExecStart`, and set `ProtectHome=read-only` so inotify can watch the workspace while keeping hardened settings.
- `scripts/auto_rebuild_deploy.sh`: Support `WATCH_ROOT` override via `PROJECT_ROOT=${WATCH_ROOT:-...}` so the watcher can monitor the source workspace while deploying to `/opt/lawnberry`.
- `docs/auto-redeploy.md`: Clarified service user, watch root behavior, and added troubleshooting steps.

## 2025-09-14 (auto-redeploy logging)

- `scripts/auto_rebuild_deploy.sh`: Added structured log markers at detection, initiation, and completion with explicit SUCCESS/FAILURE lines for UI builds/deploys, code fast deploys, service reinstalls, and requirements updates. Actions now return status; the runner logs `ACTION COMPLETE -> SUCCESS|FAILURE` per category.
- `docs/auto-redeploy.md`: Documented new log markers to aid operations.
