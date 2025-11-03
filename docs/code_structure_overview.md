# Lawnberry code structure overview

Generated on 2025-11-03. This document summarizes code files, their purpose, subsystem category, and callable interfaces (public functions and exported APIs). Grouped by subsystem for quick orientation.

Tip: Use your editor’s outline and the section links below to jump to an area of interest.

- Backend services (FastAPI/domain services)
- Navigation and planning algorithms
- Backend CLI utilities
- Frontend services and composables
- Frontend views and router
- Operations and maintenance scripts
- Tools and misc.

## Backend services (FastAPI/domain services)

| Path | Purpose | Subsystem | Callable interfaces |
|---|---|---|---|
| `backend/src/services/robohat_service.py` | Serial bridge to RoboHAT RP2040; translates high‑level control into the firmware’s text protocol; maintains health status. | Hardware control | Class `RoboHATService` (key methods): `initialize()`; `get_status() -> RoboHATStatus`. Module-level: `get_robohat_service() -> Optional[RoboHATService]`. |
| `backend/src/services/motor_service.py` | High-level drive and blade coordination, emergency stop, watchdog, and PWM mix helpers. | Hardware control | Class(es) with public methods: `emergency_stop_blade()`; `activate_emergency_stop()`; `reset_emergency_stop()`. |
| `backend/src/services/blade_service.py` | Controls blade motor (start/stop/state) via IBT‑4 driver. | Hardware control | `get_blade_service() -> BladeService`. |
| `backend/src/services/sensor_manager.py` | Aggregates and validates readings (GPS/RTK, BME280, ToF, INA3221, Victron) and computes derived statuses. | Sensors/telemetry | Public helpers (non‑private shown): validation and mapping helpers, e.g., `_map_rtk_fix_type`, `_map_sensor_status` (internal); top‑level API is via service class instance methods. |
| `backend/src/services/navigation_service.py` | Orchestrates navigation lifecycle (missions, return‑to‑base, coverage). | Navigation | Service class public API (see methods exposed via FastAPI); delegates to `nav/*` algorithms. |
| `backend/src/services/mission_service.py` | Mission execution and lifecycle management; integrates with NavigationService. | Missions | `get_mission_service(nav_service: NavigationService) -> MissionService`. |
| `backend/src/services/jobs_service.py` | Lightweight job scheduler for recurring/one‑off tasks with persistence. | Jobs/scheduling | Public methods: `get_job(job_id)`, `update_job(job_id, **updates)`, `delete_job(job_id)`, `start_job(job_id)`, `pause_job(job_id)`, `resume_job(job_id)`, `cancel_job(job_id)`, `get_next_scheduled_jobs(limit=10)` |
| `backend/src/services/websocket_hub.py` | Tracks WebSocket clients and dispatch; lifecycle and disconnect management. | Realtime/websocket | Class with `disconnect(client_id: str)` and related management APIs. |
| `backend/src/services/telemetry_hub.py` | WebSocket telemetry fan‑out per client and hub; health reporting. | Realtime/websocket | `is_healthy() -> bool` and client/session management on service classes. |
| `backend/src/services/camera_stream_service.py` | Captures frames (real or simulated), JPEG encoding, and subscriber callbacks. | Camera/AI | Public methods: `add_frame_callback(callback)`, `remove_frame_callback(callback)`; various internal helpers for frame capture and encoding. |
| `backend/src/services/camera_client.py` | Client wrapper to consume camera stream/frames. | Camera/AI | Service class constructor and stream control methods. |
| `backend/src/services/ai_service.py` | Placeholder/entry for AI features (model training/inference hooks). | AI | Service class with constructor; methods are internal WIP entry points. |
| `backend/src/services/maps_service.py` | Map provider selection (Google/OSM), API key validation, cache, and minimal tile utilities. | Mapping | Public methods: `validate_api_key(api_key: str) -> bool`, `get_usage_stats() -> Dict[str, Any]`, `clear_cache() -> None`, `attempt_provider_fallback() -> bool`. |
| `backend/src/services/timezone_service.py` | Determine timezone via OS or GPS. | Settings/infra | Module helpers: `_read_text_file(path)`, `_detect_os_timezone(base_path)`, `_timezone_from_coordinates(lat, lon)`, `_default_gps_lookup(timeout=2.5)`. |
| `backend/src/services/weather_service.py` | Current weather snapshot and mowing advice; integrates with sensors and OpenWeather. | Mapping/Weather | `get_current(latitude?, longitude?) -> Dict[str, Any]`, `get_planning_advice(current) -> Dict[str, Any]`. |
| `backend/src/services/settings_service.py` | Load/validate/update/export/import settings profiles; adapters for REST layer. | Settings | Public: `load_profile(profile_id='default')`, `update_setting(path,value)`, `validate_profile(profile)`, `get_current_profile()`, `check_version_conflict(expected_version)`, `export_profile(profile_id, export_path)`, `import_profile(import_path, profile_id?)`. Module: `get_settings_service(persist)`. |
| `backend/src/services/remote_access_service.py` | Configure and track remote access providers (e.g., ngrok), write status/config to disk. | Remote access | Top-level helpers: `_atomic_json_dump(path, payload)`, `_load_json(path)`, `load_config_from_disk(path=…)`, `save_config_to_disk(cfg, path=…)`, `save_status_to_disk(status, path=…)`. Service class public: `configure(cfg, persist=True)`, `record_error(message, exc?)`. |
| `backend/src/services/acme_service.py` | ACME client orchestration for TLS certificates (request, renew, revoke), HTTP challenge management. | Security/infra | Public: `initialize()`, `request_certificate(domain, email)`, `create_challenge_file(token, key_auth)`, `get_challenge_content(token)`, `cleanup_challenge(token)`, `list_certificates()`, `get_certificate_info(domain)`, `is_certificate_valid(domain)`, `needs_renewal(domain)`, `renew_certificate(domain)`, `revoke_certificate(domain)`, `get_certificates_needing_renewal()`, `setup_http_challenge_server(port=80)`, `reload_web_server()`, `get_renewal_status()`. |
| `backend/src/services/power_service.py` | Power state querying and safe shutdown hooks. | Power | Service class public methods (see implementation). |
| `backend/src/services/ntrip_client.py` | NTRIP forwarder for RTK corrections; request building and stats. | Navigation/GPS | Public: `from_environment(gps_mode?) -> Optional[NtripForwarder]`, `get_stats() -> dict`. |
| `backend/src/services/calibration_service.py` | Performs drive system calibration routines; exposes last result and state. | Hardware control | Public: `last_result() -> Optional[Dict[str, Any]]`, `is_running() -> bool`. |
| `backend/src/services/hw_selftest.py` | Low-level probes for I2C and serial devices; aggregates a self‑test. | Hardware diagnostics | Public: `i2c_probe(bus_num=1) -> Dict[str, Any]`, `serial_probe(paths?) -> Dict[str, Any]`, `run_selftest() -> Dict[str, Any]`. |

## Navigation and planning algorithms

| Path | Purpose | Subsystem | Callable interfaces |
|---|---|---|---|
| `backend/src/nav/path_planner.py` | Stable API over coverage, avoidance, and utilities used by `NavigationService`. | Navigation | Class `PathPlanner`: `calculate_distance(pos1, pos2)`, `calculate_bearing(pos1, pos2)`, `generate_parallel_lines_path(boundaries, *, cutting_width=0.3, overlap=0.1)`, `boundary_follow(boundary, *, waypoint_speed_ms=0.3)`, `find_path(start, goal, boundary, *, obstacles=None, grid_resolution_m=0.25)`, `return_to_base(current, home, …)`. |
| `backend/src/nav/geofence_validator.py` | Build/inspect geofence geometry and containment tests. | Navigation | `build_shape(geofence) -> GeofenceShape`, `contains(shape, point, use_buffer=True) -> bool`. Internal helpers: `_deg_lat_m()`, `_deg_lon_m_at_lat(lat)`, `_to_xy(...)`, `_to_ll(...)`, `_polygon_from_latlngs(points)`. |
| `backend/src/nav/coverage_patterns.py` | Generate coverage patterns (lawnmower, etc.) with obstacle union helpers. | Navigation | Public helpers include geometry conversions; key API: `generate_lawnmower(boundary, config)` via imported symbol, plus `_obstacles_union` (internal). |
| `backend/src/nav/coverage_planner.py` | Sweep-line utilities for coverage intervals. | Navigation | `_intervals_from_intersections(xs: List[float]) -> List[Interval]` (internal). |
| `backend/src/nav/gps_degradation.py` | Model and inject GPS degradation scenarios (for testing/robustness). | Navigation/GPS | Service class with `_tick()` and constructor; used by tests and navigation. |

## Backend CLI utilities

| Path | Purpose | Subsystem | Callable interfaces |
|---|---|---|---|
| `backend/src/cli/acme_renew.py` | Renew ACME certificates on demand (batch/cron usage). | Security/infra | `main() -> int`. |
| `backend/src/cli/control_commands.py` | Send drive/blade/emergency control commands to the backend. | Hardware control | `main()` (Typer/argparse entry). |
| `backend/src/cli/remote_access_daemon.py` | Run/coordinate remote access status updates. | Remote access | `_config_digest(cfg) -> str`, `_request_shutdown() -> None` (internals). |
| `backend/src/cli/safety_commands.py` | Safety status and commands (HTTP API wrapper). | Safety | `build_app()`, `cmd_status(base_url='http://localhost:8000')`, `main()`. |
| `backend/src/cli/secrets_cli.py` | Secrets management helpers. | Security | `main(argv: list[str] | None = None) -> int`. |
| `backend/src/cli/sensor_commands.py` | Sensor snapshot and formatting utilities. | Sensors | `_format_table(snapshot) -> str` (internal), CLI task(s). |

## Frontend services and composables

| Path | Purpose | Subsystem | Exported API |
|---|---|---|---|
| `frontend/src/services/api.ts` | HTTP API client with auth and client‑id headers; specific control and map endpoints. | Frontend API | `sendControlCommand(command: string, payload: any = {})`, `getRoboHATStatus()`, `getMapConfiguration(configId: string = 'default')`, `saveMapConfiguration(configId: string, config: any)`, `triggerMapProviderFallback()`, `useApiService()`. |
| `frontend/src/services/auth.ts` | Auth helpers (token, login/logout) backed by Pinia store. | Frontend auth | Exported functions from file (see source). |
| `frontend/src/services/websocket.ts` | WebSocket management for telemetry/control with typed handlers. | Frontend realtime | `useWebSocket(type: 'telemetry' | 'control' = 'telemetry', handlers?: { onMessage?: (msg: any) => void })`. |
| `frontend/src/composables/useApi.ts` | Vue composable wrapping API client. | Frontend API | Default/ named exports (see source). |
| `frontend/src/composables/useWebSocket.ts` | Thin composable for WebSocket URL selection. | Frontend realtime | `useWebSocket(url = '/ws')`. |
| `frontend/src/composables/useOfflineMaps.ts` | Manage offline map tiles caching and usage. | Frontend mapping | `useOfflineMaps()`. |
| `frontend/src/utils/mapProviders.ts` | Map provider selection and defaults (OSM/Google). | Frontend mapping | `isSecureMapsContext(location)`, `shouldUseGoogleProvider(...)`, `getOsmTileLayer(style)`. |
| `frontend/src/utils/markdown.ts` | Safe markdown rendering helper. | Frontend utility | `renderMarkdownSafe(src: string): string`. |

## Frontend views and router

These are Vue components and routing; they provide UI and don’t expose reusable function APIs.

- Views: `frontend/src/views/*.vue` (DashboardView, ControlView, MapsView, MissionPlannerView, PlanningView, TelemetryView, RtkDiagnosticsView, AIView, SettingsView, DocsHubView, LoginView)
- App shell: `frontend/src/App.vue`
- Router: `frontend/src/router/index.ts`
- Entrypoint: `frontend/src/main.ts`

## Operations and maintenance scripts

Many Bash and Python scripts automate setup, backups, diagnostics, and validation. Scripts are primarily CLI entrypoints; some define internal shell functions for structure. Highlights:

| Path | Purpose | Subsystem | Callable interfaces |
|---|---|---|---|
| `scripts/backup_system.sh` | Create and rotate system backups; manifests and retention. | Ops | Shell functions: `ensure_dirs`, `permissions_safe`, `collect_meta`, `backup_sqlite`, `copy_tree`, `create_snapshot`, `make_manifest`, `create_archive`, `enforce_retention`, `cleanup`, `main`. |
| `scripts/restore_system.sh` | Restore from backup snapshot safely; stops/starts services. | Ops | Shell functions: `usage`, `verify_inputs`, `verify_checksum`, `extract_archive`, `stop_services`, `start_services`, `pre_backup_current`, `restore_files`, `cleanup`, `main`. |
| `scripts/renew_certificates.sh` | Renew/issue certificates; fallback to self‑signed and nginx reconfig. | Security/infra | Shell functions: `generate_self_signed`, `switch_nginx_to_self_signed`, `check_cert_expiry`, `renew`, `main`. |
| `scripts/rebuild_frontend_and_restart_backend.sh` | Rebuild UI and restart backend services. | DevOps | Shell functions: `require_command`, `info`, `error`. |
| `scripts/validate_https_setup.sh` | Validate HTTPS setup and dependencies. | Security/infra | Shell function: `need_cmd`. |
| `scripts/generate_docs_bundle.py` | Bundle docs for distribution. | Docs | Module CLI (see source). |
| `scripts/rtk_diagnostics_watch.py` | Continuously monitor RTK status/output. | Navigation/GPS | Module CLI (see source). |
| Other helpers under `.specify/scripts/bash/` | Internal feature plan tooling for agent context updates. | Meta/tooling | Many small shell functions; see sources. |

## Tools and misc.

| Path | Purpose | Subsystem | Callable interfaces |
|---|---|---|---|
| `backend/src/tools/log_bundle_generator.py` | Build downloadable log bundles (bytes payload, filename, size). | Ops | `generate_log_bundle(time_range_minutes: int | None = None) -> tuple[str, bytes, int, list[str]]`. |

## Notes and scope

- This overview focuses on production code (backend services, nav algorithms, frontend services/composables, and ops scripts). Tests and generated artifacts are not enumerated exhaustively.
- Function lists prioritize public or exported APIs. Internal helpers (leading underscore) are omitted or labeled as internal where helpful.
- If you add or modify files, functions, or their signatures, please follow the update instructions in `/.github/copilot-instructions.md` to keep this document in sync.
