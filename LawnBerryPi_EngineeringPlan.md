# **LawnBerry Pi — Engineering Plan (Updated)**

## **Guiding Principles**

\- Safety first → motion only with hard/soft failsafes.  
\- Modular architecture → hardware-agnostic drivers \+ clean interfaces.  
\- Debuggability → rich logs, CLIs, simulators, and fault isolation.  
\- User first → DIY-friendly workflows, polished retro-neon UI.

Target platform: Raspberry Pi 5 (8/16GB) on Raspberry Pi OS Lite (Bookworm); graceful degradation on Pi 4B 8GB.

## **Phase 0 — Foundation & Tooling**

Objectives  
\- Reproducible setup, CI, code quality, and configuration.

Deliverables  
\- ansible/ or scripts/setup.sh to provision Bookworm, users, swap, GPU mem, system deps.  
\- pyproject.toml (or requirements.txt) \+ pre-commit (ruff/black/mypy).  
\- CI: lint, type-check, unit tests; release workflow for versioned Docker image.  
\- Central config: config/hardware.yaml (declares which modules are present) \+ config/limits.yaml (safety limits/thresholds).  
\- Logging & metrics: structured logs (JSON), rotating files, log levels; /metrics (Prometheus) optional.

Definition of Done (DoD)  
\- Fresh Pi to 'hello world' in \<20 min.  
\- CI green on every PR; branch protection on main.

## **Phase 1 — Core Abstractions & Process Layout**

Objectives  
\- Establish process model and interfaces.

Key Modules & Contracts  
\- bus/: pub/sub (MQTT or in-proc event bus).  
\- drivers/: per-hardware shims.  
\- safety/contract.py: shared safety API.  
\- state/: canonical robot state.  
\- api/: REST \+ WebSocket.

DoD  
\- 'Null robot' runs with mocked drivers; state updates & API live.

## **Phase 2 — Safety & Motor Control (Minimum Viable Safety)**

Implements motion with safety, without IMU yet.

Hardware/Software in Scope  
\- Emergency Stop: physical \+ GPIO.  
\- Motor Control Abstractions: drive \+ blade.  
\- Software Watchdog: heartbeat enforced.  
\- Startup/Shutdown: OFF by default.  
\- Basic Teleop: manual control endpoints.

Acceptance Tests  
\- E-stop stops motors \<100ms.  
\- Watchdog enforced.

DoD  
\- Field test with chassis on stands: manual motion \+ e-stop drills.

## **Phase 3 — Sensors & Extended Safety (IMU-backed)**

Adds perception and IMU-based safety to interlock layer.

Drivers  
\- IMU, ToF, Env, Power.

Extended Safety Triggers  
\- Tilt, impact, power, range.

Sensor Fusion  
\- Time sync, health model.

CLIs  
\- Live sensor test tools.

DoD  
\- Bench tests show triggers work, recovery requires operator.

## **Phase 4 — Navigation Core**

Objectives  
\- Localisation, geofencing, point-to-point motion.

Work Items  
\- GPS/RTK, odometry, geofencing, waypoint following, mode manager.

DoD  
\- Drive to Home/AM/PM waypoints safely.

## **Phase 5 — Web UI (Retro-Neon) & Remote Access**

Objectives  
\- Real-time UI aligned with branding \+ remote access.

UI Scope  
\- Dashboard, controls, maps, settings, notifications, style.

Remote Access  
\- Cloudflare Tunnel preferred, Tailscale/ngrok alternatives, LAN mode.

DoD  
\- UI controls all phases \+ map edit persists.

## **Phase 6 — Scheduling & Autonomy**

Objectives  
\- Full autonomous mowing.

Features  
\- Calendar schedules, weather-aware, coverage patterns, solar-smart docking.

DoD  
\- Schedule triggers, respects geofence, returns to sun waypoints.

## **Phase 7 — Reliability, Testing, & Polish**

Objectives  
\- Harden for DIY and long-term use.

Work Items  
\- Fault injection, log bundles, dashboards, docs.

DoD  
\- 8-hour soak test passes with no unsafe events.

## **Module Map (Who Builds What)**

\- drivers/: motors, blade, imu, tof, env, power, gps.  
\- safety/: interlocks, triggers, watchdog, e-stop glue.  
\- fusion/: state estimation.  
\- nav/: geofence, planner, controller.  
\- api/: REST \+ WS.  
\- ui/: React app (retro-neon).  
\- scheduler/: calendar, weather, charge.  
\- tools/: CLIs, analyzers, calibration.

## **Acceptance Criteria (Core)**

\- E-stop latency \<100ms.  
\- IMU tilt cutoff \<200ms.  
\- UI telemetry ≤1s.  
\- Nav fence: 0 incursions.  
\- Graceful degradation: missing GPS → manual stays safe.

## **Developer Workflow**

\- Small PRs with tests.  
\- Feature flags per module.  
\- Mockable drivers.  
\- Simulation traces for bug repro.

## **What Starts First (Actionable Day-1)**

1\. Phase 0 setup \+ CI.  
2\. Phase 1 bus/contracts \+ mock drivers.  
3\. Phase 2 motor \+ blade drivers, E-stop, watchdog, teleop.  
4\. Then: Phase 3 IMU/ToF and extended safety.