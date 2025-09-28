# Quickstart — LawnBerry Pi v2

## Prereqs
- Raspberry Pi OS Bookworm 64-bit, Python 3.11.x
- Wi‑Fi network
- Google Maps API key (optional)
- Domain for remote access (ACME HTTP-01)

## Steps
1) Install services via `systemd/install_services.sh`
2) Configure settings in Settings page (zones, locations, API key, ACME domain)
3) Start backend and frontend services
4) Verify Dashboard telemetry at 5 Hz (<100ms latency)
5) Enable remote access (ACME) and complete MFA setup
6) Test GPS-loss behavior by sim toggle (grace period, stop/alert)
