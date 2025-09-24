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

## 2. Cross-check Telemetry Cadence
1. Ensure `spec.md` states a 1 Hz default cadence with operator overrides.
2. Confirm `contracts/webui-websocket.yaml` exposes a `settings/cadence` action and heartbeat fields for critical topics.
3. For simulation mode, verify quickstart instructions mention mock publishers (include reference to `src/lawnberry` simulation services).

## 3. Validate Authentication Narrative
1. Check that `spec.md` highlights the single shared operator credential and that Manual Control endpoints in `webui-openapi.yaml` require it.
2. Confirm `data-model.md` and `spec.md` agree on gating manual actions and dataset exports with the credential.

## 4. Align Hardware Section with Manifest
1. Compare the `HardwareProfile` entries in `data-model.md` with `/spec/hardware.yaml`.
2. Ensure INA3221 channel assignments, AI accelerator hierarchy, and conflict notes are carried into the spec hardware section.
3. Document any drift directly in `spec.md` (do not defer to README files).

## 5. Dataset Export Validation
1. Confirm the AI Training section references both COCO JSON and YOLO TXT outputs.
2. Check `POST /api/ai/datasets/export` contract for combined format support.
3. Ensure WebSocket progress events include job ID, status, and completion URLs.

## 6. Final Review Checklist
- Diff `spec.md` for seven WebUI pages, contracts, telemetry cadence, and authentication updates.
- Ensure `plan.md`, `research.md`, `data-model.md`, and contracts are committed.
- Run repository quality gates (`uv lock`, `ruff`, `black`, `mypy`, `pytest`) to satisfy the constitution before opening a PR.
