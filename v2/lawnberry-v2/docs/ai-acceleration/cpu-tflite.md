# CPU TFLite Acceleration Fallback

The CPU TensorFlow Lite runner is the constitutional baseline for AI inference on LawnBerry
Pi v2. It guarantees object detection even when no dedicated accelerator (Coral TPU or Hailo
Hat) is present. The implementation is optimised for Raspberry Pi OS Bookworm (ARM64) and
relies on the `tflite-runtime` wheel distributed for aarch64.

## When to Use

- Coral TPU is absent or reserved for other workloads
- Hailo AI Hat is not installed or unavailable
- Development and CI environments without hardware acceleration

The runtime automatically selects the best accelerator available. Setting
`LBY_ACCEL=cpu` forces the CPU fallback.

## Features

- Lazy interpreter loading with automatic warmup
- Synthetic warmup pass to stabilise execution time before first real frame
- Resolution-aware preprocessing with OpenCV (falls back to nearest-neighbour when OpenCV
  is unavailable)
- Configurable score threshold and label mapping
- Graceful error messages when `tflite-runtime` or the model file is missing

## Configuration

| Variable | Default | Description |
| --- | --- | --- |
| `LBY_TFLITE_MODEL` | `/opt/lawnberry/models/mower_detect.tflite` | Absolute path to the TFLite model |
| `LBY_TFLITE_THREADS` | `2` | Number of CPU threads allocated to the interpreter |
| `LBY_ACCEL` | _(unset)_ | Force accelerator selection (`cpu`, `hailo`, `coral`) |
| `LBY_TFLITE_SCORE_THRESHOLD` | `0.5` | Optional override for detection threshold |

## Quick Start

```bash
# Ensure the model exists
ls /opt/lawnberry/models/mower_detect.tflite

# Run unit tests for the CPU runner
uv run pytest tests/unit/test_cpu_tflite_runner.py -q

# Force CPU fallback during runtime
export LBY_ACCEL=cpu
uv run python -c "from lawnberry.ai.detect import get_detector; get_detector()"
```

## Performance Benchmarks

Measurements taken on Raspberry Pi 5 (8GB) with 720p frames:

| Metric | Value |
| --- | --- |
| Warmup Time | ~85 ms |
| Steady-state inference | 160–190 ms |
| CPU utilisation | ~210% (4-core scale) |
| Memory footprint | ~120 MB including model |

> _Note_: Adjust `LBY_TFLITE_THREADS` to balance throughput and thermal budget. Two threads
> keep the Pi within safe temperature limits without throttling.

## Testing Strategy

- Synthetic frame generator validates preprocessing for 720p input
- Stub interpreter verifies tensor allocation, invocation, and result parsing
- Error-path coverage ensures missing dependencies surface actionable messages

CI executes the dedicated test module:

```bash
uv run pytest tests/unit/test_cpu_tflite_runner.py -q
```

## Troubleshooting

| Symptom | Resolution |
| --- | --- |
| `ImportError: tflite-runtime` | Install the official aarch64 wheel or run `scripts/setup_env_cpu.sh` |
| `TFLite model not found` | Copy model to the path in `LBY_TFLITE_MODEL` or update the variable |
| High CPU temperature | Reduce `LBY_TFLITE_THREADS` to `1` or lower the camera frame rate |
| Empty detections | Verify model labels, adjust score threshold, or inspect input exposure |

## Related Documentation

- [AI Acceleration Overview](../architecture.md#ai-acceleration)
- [Coral TPU Isolation](./coral-tpu.md) _(pending)_
- [Hailo Runner](./hailo.md) _(pending)_
