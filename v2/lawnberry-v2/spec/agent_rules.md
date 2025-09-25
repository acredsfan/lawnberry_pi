# Agent Rules (Hard Requirements)

- Target ONLY Linux/ARM64 (RPi OS Bookworm). No Windows/macOS-only packages or steps.
- BAN `pycoral`/`edgetpu` in the main env. Coral uses its own venv only.
- Use Picamera2 + GStreamer; GPIO via python-periphery + lgpio; serial via pyserial.
- Every code change updates /docs and /spec (CI fails if drift).
- No TODOs unless `TODO(v3):` with a linked GitHub issue.
- Treat camera, sensors, and motor controllers as single-owner resources.
  - Camera access is brokered through `camera-stream.service`; other services must subscribe to its feed and MUST NOT open the device directly.
  - Hardware interfaces shared across processes require an explicit coordinator (locks, IPC queue, or dedicated daemon) to prevent concurrent access attempts.
