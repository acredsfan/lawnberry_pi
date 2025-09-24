# Quickstart — Validating WebUI & Hardware Specification Alignment

## Prerequisites
- Feature branch `002-update-spec-to` checked out on the mower repository.
- `uv` toolchain available with project dependencies installed.
- Access to the generated contracts in `specs/002-update-spec-to/contracts/`.

## 1. Verify REST & WebSocket Contracts
1. Run OpenAPI validation:
   ```bash
   spectacular lint specs/002-update-spec-to/contracts/webui-openapi.yaml
   ```
2. Run AsyncAPI validation:
   ```bash
   asyncapi validate specs/002-update-spec-to/contracts/webui-websocket.yaml
   ```
3. Confirm every WebUI page in `spec.md` references the matching endpoint(s) and topic(s) from the validated specs.
4. Cross-check that each page’s `route_path` in `data-model.md` aligns with router definitions and that the `linked_topics` array in `webui-openapi.yaml` mirrors the WebSocket topics documented in `spec.md`.

## 2. Cross-check Telemetry Cadence
1. Ensure `spec.md` and `data-model.md` state a 5 Hz default cadence, 10 Hz ceiling, and 1 Hz diagnostic floor with operator overrides.
2. Confirm `contracts/webui-websocket.yaml` exposes a `settings/cadence` action, heartbeat fields for critical topics, and includes `settings/cadence` broadcasts tied to `TelemetryCadencePolicy`.
3. For simulation mode, verify quickstart instructions mention mock publishers (include reference to `src/lawnberry` simulation services) and cover cadence override emulation.

## 3. Validate Authentication Narrative
1. Check that `spec.md` highlights the single shared operator credential and that Manual Control endpoints in `webui-openapi.yaml` require it.
2. Confirm `data-model.md` and `spec.md` agree on gating manual actions and dataset exports with the credential.

## 4. Align Hardware Section with Manifest
1. Compare the `HardwareProfile` entries in `data-model.md` with `/spec/hardware.yaml`.
2. Ensure INA3221 channel assignments, AI accelerator hierarchy, GPS exclusivity rules, and conflict notes are carried into the spec hardware section.
3. Document any drift directly in `spec.md` (do not defer to README files).

## 5. Dataset Export Validation
1. Confirm the AI Training section references both COCO JSON and YOLO TXT outputs.
2. Check `POST /api/ai/datasets/export` contract for combined format support.
3. Ensure WebSocket progress events include job ID, status, and completion URLs.

## 6. Branding & Route Consistency
1. Verify `spec.md` and `data-model.md` reference `LawnBerryPi_logo.png`, `LawnBerryPi_icon2.png`, and the robot pin marker across Dashboard, Manual Control, and Docs Hub.
2. Ensure `BrandAsset` entries include usage contexts for each page and that the Docs Hub section lists downloadable assets.
3. Confirm map pin styling is mirrored in telemetry overlays (check `Map Setup` and `Manual Control` subsections).

## 7. Final Review Checklist
- Diff `spec.md` for seven WebUI pages, contracts, telemetry cadence, branding, and authentication updates.
- Ensure `plan.md`, `research.md`, `data-model.md`, and contracts are committed.
- Run repository quality gates (`uv lock`, `ruff`, `black`, `mypy`, `pytest`) to satisfy the constitution before opening a PR.
