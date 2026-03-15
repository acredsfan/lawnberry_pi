# LawnBerry project skills

This workspace includes reusable Copilot skills tailored to the workflows documented in `docs/developer-toolkit.md`.

## Available skills

- `maintainer-reentry` — fast project re-orientation for returning maintainers before substantial work
- `runtime-contract-audit` — audit ports, startup behavior, docs, config, and service-unit drift
- `sim-hardware-validation` — keep simulation-safe and real-hardware validation paths explicit
- `control-camera-regression-review` — review manual-control, RoboHAT USB handoff, and camera-stream changes safely
- `navigation-hardening-pass` — harden navigation feedback, stop/fault behavior, and regression coverage
- `mission-recovery-pass` — design or implement persistence and safe restart/recovery semantics for missions
- `ai-model-quality-pass` — improve AI result quality without breaking the existing backend contract
- `maintainer-doc-sync` — keep maintainer docs, release notes, and code structure docs aligned with implementation

These skills are workspace-scoped and live under `.github/skills/` so the whole project can share them.
