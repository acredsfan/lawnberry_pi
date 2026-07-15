# Perception runtime

LawnBerry runs object detection only when a real local ONNX artifact and strict manifest are available. Missing or invalid configuration remains visibly unavailable; the runtime never substitutes color rules, hardcoded detections, sample datasets, training jobs, or export success.

## Install and configure

1. Install the Raspberry Pi OS OpenCV package:

   ```bash
   sudo apt update
   sudo apt install python3-opencv
   ```

2. Place the qualified ONNX artifact under `models/`. Model artifacts are intentionally ignored by Git.
3. Copy `config/ai_detector.example.json` to ignored runtime file `config/ai_detector.json` and edit:
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

Set `AI_MODEL_CONFIG` only when the manifest lives somewhere other than `config/ai_detector.json`. `AI_INFERENCE_ENABLED=0` disables model loading. The power manager also stops camera-owner inference while the mower is dark and idle and re-enables it before a mission.

## Verify truthful state

```bash
curl -s http://127.0.0.1:8081/api/v2/ai/status
curl -s http://127.0.0.1:8081/api/v2/ai/perception/latest
```

A usable live result has:

- `model_ready=true`, runtime `opencv_dnn`, and a 64-character `model_sha256`;
- execution owner `camera_ipc` on hardware;
- an exact `input_frame_id`, `source_frame_timestamp`, inference timestamp, and measured latency;
- `fresh=true` only inside the manifest's bounded result age.

The AI Perception page shows the same model digest, source frame, age, latency, detections, and route-cost count. A missing manifest/artifact/runtime is an operator-visible unavailable state, not a startup blocker for the camera or a fake success.

## Safety boundary

Validated live camera detections may add short-lived semantic obstacles to the local route-cost map. They cannot:

- clear or create the authoritative ToF obstacle interlock;
- reduce obstacle clearance below geometric planning constraints;
- bypass localization, operating-area, energy, qualification, or mission admission;
- send drive/blade commands or bypass `MotorCommandGateway`.

Class-height distance estimates are approximate monocular geometry, not safety ranging. Before unattended mowing, qualify the exact artifact digest, class mapping, field of view, lighting envelope, latency, false-negative behavior, and distance calibration on the physical mower. Software tests alone do not establish that readiness.
