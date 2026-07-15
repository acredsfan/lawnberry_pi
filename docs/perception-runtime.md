# Perception runtime

LawnBerry runs object detection only when a real local ONNX artifact and strict manifest are available. Missing or invalid configuration remains visibly unavailable; the runtime never substitutes color rules, hardcoded detections, sample datasets, training jobs, or export success.

## Install and configure

1. Install the hardware dependency set. It pins an OpenCV build new enough to
   load the supported YOLOv5 v7 ONNX export on Raspberry Pi OS:

   ```bash
   uv sync --extra hardware
   ```

2. Provision the baseline CPU detector. The model and runtime manifest are
   intentionally ignored by Git, while the matching manifest template is tracked:

   ```bash
   uv run python scripts/provision_ai_detector.py --accept-gpl-3.0
   ```

   This baseline is Ultralytics YOLOv5n v7.0 trained on the 80 COCO classes
   and distributed under GPL-3.0. The acknowledgement flag is required before
   the script makes a network download. It verifies the pinned SHA-256 digest,
   atomically installs missing files, and proves that OpenCV can load and run the
   manifest/model pair. It never overwrites an existing manifest or model.

   Recheck an existing installation without downloading or creating files:

   ```bash
   uv run python scripts/provision_ai_detector.py --verify-only
   ```
3. For a different qualified ONNX artifact, edit the ignored runtime manifest:
   - `model_path`, resolved relative to the manifest;
   - exact class order used by the exported model;
   - `output_format` (`xyxy`, `yolov5`, or `yolov8`);
   - confidence-independent `nms_threshold` for duplicate suppression;
   - model input dimensions and camera horizontal field of view;
   - physically measured class heights used for approximate distance;
   - semantic multipliers, which must never be used to reduce geometric clearance.
4. Restart both owners so they validate the same artifact:

   ```bash
   sudo systemctl restart lawnberry-camera.service lawnberry-backend.service
   ```

Set `AI_MODEL_CONFIG` only when the manifest lives somewhere other than `config/ai_detector.json`. `AI_INFERENCE_ENABLED=0` disables model loading. The power manager stops camera-owner inference while the mower is dark and truly idle, but an active Control-page viewer holds a bounded capture lease so the camera is not paused underneath the live UI.

## Runtime ownership and API behavior

On hardware, `lawnberry-camera.service` is the sole camera and inference owner.
It samples exact captured frames at a bounded rate, runs the configured model,
and publishes typed results over camera IPC. Inference is single-flight and
off the frame-delivery path: the Pi 5 CPU baseline uses a 3-second owner deadline
for measured 1.0-1.95-second YOLOv5n runs, while the manifest's 5-second source-frame
freshness bound leaves a bounded 2-second IPC and consumer margin. Over-deadline
work is discarded after its sole worker exits; it never queues a replacement or
stalls the Control camera stream. FastAPI loads only matching model
metadata, ingests those results, and exposes the latest hardware result at
`GET /api/v2/ai/perception/latest`.

Owner status separates `ai_model_loaded` from `ai_runtime_ready`. Loading and
hashing the model is not operational proof: readiness begins false, becomes true
only after one automatic exact-frame inference finishes within the deadline,
and returns false after a timeout, runtime/provenance error, stopped stream, or
the five-second freshness bound. Mission admission waits within a bounded
deadline for that first proof after waking capture and inference.

`POST /api/v2/ai/inference` and `POST /api/v2/ai/inference/latest` are
embedded-runtime diagnostics for `SIM_MODE=1` and CI. They intentionally return
`503` in hardware mode instead of loading a second detector or forwarding large
images through the camera-control IPC channel. They are not the production
trigger for object detection; hardware inference runs automatically while the
camera owner and its AI power gate are active.

## Verify truthful state

```bash
curl -s http://127.0.0.1:8081/api/v2/ai/status
curl -s http://127.0.0.1:8081/api/v2/ai/perception/latest
```

A usable live result has:

- `model_ready=true`, runtime `opencv_dnn`, and a 64-character `model_sha256`;
- owner-reported detector readiness and digest matching the backend metadata;
- execution owner `camera_ipc` on hardware;
- an exact `input_frame_id`, `source_frame_timestamp`, inference timestamp, and measured latency;
- `fresh=true` only inside the manifest's bounded result age.

The AI Perception page shows the same model digest, source frame, age, latency, detections, and route-cost count. A missing manifest/artifact/runtime is an operator-visible unavailable state, not a startup blocker for the camera or a fake success.

If hardware camera initialization fails, the owner may expose an explicit
simulation fallback for UI diagnostics, but it disables detector execution and
publishes no perception. Synthetic fallback frames are never accepted as live
hardware results.

The tracked example manifest must match the exact artifact. Do not shorten or
reorder its 80 labels: ONNX outputs use numeric class positions, so a mismatched
list produces confidently wrong object names even when inference succeeds.

## Safety boundary

Validated live camera detections may add short-lived semantic obstacles to the local route-cost map. They cannot:

- clear or create the authoritative ToF obstacle interlock;
- reduce obstacle clearance below geometric planning constraints;
- bypass localization, operating-area, energy, qualification, or mission admission;
- send drive/blade commands or bypass `MotorCommandGateway`.

Class-height distance estimates are approximate monocular geometry, not safety ranging. Before unattended mowing, qualify the exact artifact digest, class mapping, field of view, lighting envelope, latency, false-negative behavior, and distance calibration on the physical mower. Software tests alone do not establish that readiness.
