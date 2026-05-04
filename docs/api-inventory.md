# LawnBerry API Endpoint Inventory

Last updated: 2026-05-01  
Status labels: `canonical` | `compatibility` | `deprecated` | `debug-only`

Canonical surface is `/api/v2/*`. All new frontend code must use canonical endpoints only.

## Control

| Method | Path | Label | Router file | Notes |
|---|---|---|---|---|
| POST | `/api/v2/control/drive` | `canonical` | `api/rest.py` | Gateway-wired |
| POST | `/api/v2/control/blade` | `canonical` | `api/rest.py` | |
| POST | `/api/v2/control/emergency` | `canonical` | `api/rest.py` | Gateway-wired |
| POST | `/api/v2/control/emergency-stop` | `canonical` | `api/rest.py` | Alias for /emergency; consolidate in future |
| POST | `/api/v2/control/emergency_clear` | `canonical` | `api/safety.py` | Gateway-wired |
| POST | `/api/v2/control/start` | `canonical` | `api/rest.py` | |
| POST | `/api/v2/control/pause` | `canonical` | `api/rest.py` | |
| POST | `/api/v2/control/resume` | `canonical` | `api/rest.py` | |
| POST | `/api/v2/control/stop` | `canonical` | `api/rest.py` | |
| POST | `/api/v2/control/return-home` | `canonical` | `api/rest.py` | |
| GET  | `/api/v2/control/status` | `canonical` | `api/rest.py` | |
| GET  | `/api/v2/control/manual-unlock/status` | `canonical` | `api/routers/auth.py` | |
| POST | `/api/v2/control/manual-unlock` | `canonical` | `api/routers/auth.py` | |
| POST | `/api/v2/control/diagnose/stiffness` | `canonical` | `api/rest.py` | |
| POST | `/api/v2/control/diagnose/heading-validation` | `canonical` | `api/rest.py` | |

## Missions

| Method | Path | Label | Router file | Notes |
|---|---|---|---|---|
| POST | `/api/v2/missions/create` | `canonical` | `api/mission.py` | |
| POST | `/api/v2/missions/{id}/start` | `canonical` | `api/mission.py` | |
| POST | `/api/v2/missions/{id}/pause` | `canonical` | `api/mission.py` | |
| POST | `/api/v2/missions/{id}/resume` | `canonical` | `api/mission.py` | |
| POST | `/api/v2/missions/{id}/abort` | `canonical` | `api/mission.py` | |
| GET  | `/api/v2/missions/{id}/status` | `canonical` | `api/mission.py` | |
| GET  | `/api/v2/missions/list` | `canonical` | `api/mission.py` | |

## Navigation

| Method | Path | Label | Router file | Notes |
|---|---|---|---|---|
| POST | `/api/v2/nav/waypoints` | `canonical` | `api/navigation.py` | |
| POST | `/api/v2/nav/mode` | `canonical` | `api/navigation.py` | |
| GET  | `/api/v2/nav/status` | `canonical` | `api/navigation.py` | |
| GET  | `/api/v2/nav/coverage-plan` | `canonical` | `api/navigation.py` | |

## Maps

| Method | Path | Label | Router file | Notes |
|---|---|---|---|---|
| GET  | `/api/v2/map/zones` | `canonical` | `api/rest.py` | In-memory store; migrate to MapRepository (§5) |
| POST | `/api/v2/map/zones` | `canonical` | `api/rest.py` | |
| GET  | `/api/v2/map/locations` | `canonical` | `api/rest.py` | |
| PUT  | `/api/v2/map/locations` | `canonical` | `api/rest.py` | |
| GET  | `/api/v2/map/configuration` | `canonical` | `api/rest.py` | |
| PUT  | `/api/v2/map/configuration` | `canonical` | `api/rest.py` | |
| POST | `/api/v2/map/provider-fallback` | `canonical` | `api/rest.py` | |

## Planning

| Method | Path | Label | Router file | Notes |
|---|---|---|---|---|
| GET  | `/api/v2/planning/jobs` | `canonical` | `api/rest.py` | In-memory store; migrate to MissionRepository (§5) |
| POST | `/api/v2/planning/jobs` | `canonical` | `api/rest.py` | |
| DELETE | `/api/v2/planning/jobs/{id}` | `canonical` | `api/rest.py` | |

## Telemetry & Dashboard

| Method | Path | Label | Router file | Notes |
|---|---|---|---|---|
| GET  | `/api/v2/telemetry/stream` | `canonical` | `api/routers/telemetry.py` | |
| GET  | `/api/v2/telemetry/export` | `canonical` | `api/routers/telemetry.py` | |
| POST | `/api/v2/telemetry/ping` | `canonical` | `api/routers/telemetry.py` | |
| GET  | `/api/v2/dashboard/telemetry` | `canonical` | `api/routers/telemetry.py` | |
| GET  | `/api/v2/dashboard/status` | `canonical` | `api/routers/sensors.py` | |
| GET  | `/api/v2/dashboard/metrics` | `canonical` | `api/dashboard.py` | |
| GET  | `/api/v2/status` | `canonical` | `api/status.py` | |
| WS   | `/api/v2/ws/telemetry` | `canonical` | `api/routers/telemetry.py` | |
| WS   | `/api/v2/ws/control` | `canonical` | `api/routers/telemetry.py` | |
| WS   | `/api/v2/ws/status` | `canonical` | `api/status.py` | |
| GET  | `/api/v2/ws/telemetry` (HTTP) | `canonical` | `api/routers/telemetry.py` | WS upgrade handshake GET |
| GET  | `/api/v2/ws/control` (HTTP) | `canonical` | `api/routers/telemetry.py` | WS upgrade handshake GET |
| GET  | `/api/v2/ws/settings` (HTTP) | `canonical` | `api/routers/telemetry.py` | |
| GET  | `/api/v2/ws/notifications` (HTTP) | `canonical` | `api/routers/telemetry.py` | |

## Legacy WebSocket (bare paths — no `/api/v2/` prefix)

| Method | Path | Label | Router file | Notes |
|---|---|---|---|---|
| WS   | `/ws/telemetry` | `compatibility` | `api/rest.py` (`legacy_router`) | Mirrors `/api/v2/ws/telemetry`; deprecation header added in Task 2; remove when frontend migrated |
| WS   | `/ws/control` | `compatibility` | `api/rest.py` (`legacy_router`) | Mirrors `/api/v2/ws/control` |
| GET  | `/ws/telemetry` (HTTP) | `compatibility` | `api/rest.py` (`legacy_router`) | WS upgrade handshake |
| GET  | `/ws/control` (HTTP) | `compatibility` | `api/rest.py` (`legacy_router`) | |

## Sensors

| Method | Path | Label | Router file | Notes |
|---|---|---|---|---|
| GET  | `/api/v2/sensors/health` | `canonical` | `api/routers/sensors.py` | |
| GET  | `/api/v2/sensors/tof/status` | `canonical` | `api/routers/sensors.py` | |
| GET  | `/api/v2/sensors/gps/status` | `canonical` | `api/routers/sensors.py` | |
| GET  | `/api/v2/sensors/gps/rtk/diagnostics` | `canonical` | `api/routers/sensors.py` | |
| GET  | `/api/v2/sensors/imu/status` | `canonical` | `api/routers/sensors.py` | |
| GET  | `/api/v2/sensors/environmental/status` | `canonical` | `api/routers/sensors.py` | |
| GET  | `/api/v2/sensors/power/status` | `canonical` | `api/routers/sensors.py` | |

## Settings

| Method | Path | Label | Router file | Notes |
|---|---|---|---|---|
| GET  | `/api/v2/settings` | `canonical` | `api/routers/settings.py` | |
| PUT  | `/api/v2/settings` | `canonical` | `api/routers/settings.py` | |
| GET  | `/api/v2/settings/system` | `canonical` | `api/routers/settings.py` | |
| PUT  | `/api/v2/settings/system` | `canonical` | `api/routers/settings.py` | |
| GET  | `/api/v2/settings/security` | `canonical` | `api/routers/settings.py` | |
| PUT  | `/api/v2/settings/security` | `canonical` | `api/routers/settings.py` | |
| GET  | `/api/v2/settings/remote-access` | `canonical` | `api/routers/settings.py` | |
| PUT  | `/api/v2/settings/remote-access` | `canonical` | `api/routers/settings.py` | |
| GET  | `/api/v2/settings/maps` | `canonical` | `api/routers/settings.py` | |
| PUT  | `/api/v2/settings/maps` | `canonical` | `api/routers/settings.py` | |
| GET  | `/api/v2/settings/gps-policy` | `canonical` | `api/routers/settings.py` | |
| PUT  | `/api/v2/settings/gps-policy` | `canonical` | `api/routers/settings.py` | |
| GET  | `/api/v2/settings/telemetry` | `canonical` | `api/routers/settings.py` | |
| PUT  | `/api/v2/settings/telemetry` | `canonical` | `api/routers/settings.py` | |
| GET  | `/api/v2/settings/safety` | `canonical` | `api/routers/settings.py` | |
| PUT  | `/api/v2/settings/safety` | `canonical` | `api/routers/settings.py` | |

## Auth

| Method | Path | Label | Router file | Notes |
|---|---|---|---|---|
| POST | `/api/v2/auth/login` | `canonical` | `api/routers/auth.py` | |
| POST | `/api/v2/auth/refresh` | `canonical` | `api/routers/auth.py` | |
| POST | `/api/v2/auth/logout` | `canonical` | `api/routers/auth.py` | |
| POST | `/api/v2/auth/configure/password` | `canonical` | `api/routers/auth.py` | |
| GET  | `/api/v2/auth/profile` | `canonical` | `api/routers/auth.py` | |

## Camera

| Method | Path | Label | Router file | Notes |
|---|---|---|---|---|
| GET  | `/api/v2/camera/status` | `canonical` | `api/routers/camera.py` | |
| POST | `/api/v2/camera/start` | `canonical` | `api/routers/camera.py` | |
| POST | `/api/v2/camera/stop` | `canonical` | `api/routers/camera.py` | |
| GET  | `/api/v2/camera/frame` | `canonical` | `api/routers/camera.py` | |
| GET  | `/api/v2/camera/stream.mjpeg` | `canonical` | `api/routers/camera.py` | |

## Maintenance & Health

| Method | Path | Label | Router file | Notes |
|---|---|---|---|---|
| GET  | `/api/v2/system/selftest` | `canonical` | `api/routers/maintenance.py` | |
| GET  | `/api/v2/health/liveness` | `canonical` | `api/routers/maintenance.py` | Preferred health probe path |
| GET  | `/api/v2/health/readiness` | `canonical` | `api/routers/maintenance.py` | Preferred health probe path |
| GET  | `/api/v2/system/timezone` | `canonical` | `api/routers/maintenance.py` | |
| POST | `/api/v2/maintenance/imu/calibrate` | `canonical` | `api/routers/maintenance.py` | |
| GET  | `/api/v2/maintenance/imu/calibrate` | `canonical` | `api/routers/maintenance.py` | |
| GET  | `/health` | `compatibility` | `api/health.py` | Used by systemd/Docker probes; keep alive; add deprecation header |
| GET  | `/api/v2/health` | `compatibility` | `api/health.py` | Redundant with /liveness + /readiness; keep for existing probes |
| GET  | `/healthz` | `compatibility` | `api/health.py` | Kubernetes alias; keep alive; add deprecation header pointing to /api/v2/health/liveness |
| GET  | `/metrics` | `canonical` | `api/metrics.py` | Prometheus scrape endpoint; not a user-facing path |

## Motors (direct PWM — internal)

| Method | Path | Label | Router file | Notes |
|---|---|---|---|---|
| POST | `/api/v2/motors/drive` | `canonical` | `api/motors.py` | Dry-run arcade mix; no gateway wiring yet; internal use |

## Other

| Method | Path | Label | Router file | Notes |
|---|---|---|---|---|
| GET  | `/api/v2/fusion/state` | `canonical` | `api/fusion.py` | |
| GET  | `/api/v2/hardware/robohat` | `canonical` | `api/rest.py` | |
| GET  | `/api/v2/weather/current` | `canonical` | `api/routers/weather.py` | |
| GET  | `/api/v2/weather/planning` | `canonical` | `api/routers/weather.py` | |
| GET  | `/api/v2/weather/planning-advice` | `canonical` | `api/routers/weather.py` | |

## Debug endpoints (never called from production frontend)

| Method | Path | Label | Router file | Notes |
|---|---|---|---|---|
| POST | `/api/v2/debug/gps/inject` | `debug-only` | `api/navigation.py` | Simulation/test only |
| POST | `/api/v2/debug/geofence` | `debug-only` | `api/navigation.py` | Simulation/test only |
| POST | `/api/v2/debug/sensors/inject-tof` | `debug-only` | `api/routers/sensors.py` | Simulation/test only |
| POST | `/api/v2/debug/sensors/inject-tilt` | `debug-only` | `api/routers/sensors.py` | Simulation/test only |

## Deprecated (REST v1 — removal target: 2026-Q3)

All endpoints below already carry `deprecated=True` in FastAPI. They will gain `Deprecation` response headers in Task 2 and be removed once frontend migration is verified.

| Method | Path | Label | Router file | Canonical replacement |
|---|---|---|---|---|
| GET  | `/api/v1/status` | `deprecated` | `api/rest_v1.py` | `/api/v2/dashboard/status` |
| POST | `/api/v1/auth/login` | `deprecated` | `api/rest_v1.py` | `/api/v2/auth/login` |
| GET  | `/api/v1/maps/zones` | `deprecated` | `api/rest_v1.py` | `/api/v2/map/zones` |
| POST | `/api/v1/maps/zones` | `deprecated` | `api/rest_v1.py` | `/api/v2/map/zones` |
| GET  | `/api/v1/mow/jobs` | `deprecated` | `api/rest_v1.py` | `/api/v2/planning/jobs` |
| POST | `/api/v1/mow/jobs` | `deprecated` | `api/rest_v1.py` | `/api/v2/planning/jobs` |

## Removal plan

| Group | Target removal | Precondition |
|---|---|---|
| `/api/v1/*` | 2026-Q3 | All frontend references removed; contract test suite confirms no usage |
| Bare `/ws/telemetry`, `/ws/control` | 2026-Q3 | Frontend WebSocket client uses `/api/v2/ws/*` paths |
| `/health`, `/healthz` bare paths | 2026-Q4 | systemd unit file and any Docker health-check configs updated to `/api/v2/health/liveness` |
