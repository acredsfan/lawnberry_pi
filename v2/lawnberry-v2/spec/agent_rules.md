# Agent Rules (Hard Requirements)

- Target ONLY Linux/ARM64 (RPi OS Bookworm). No Windows/macOS-only packages or steps.
- BAN `pycoral`/`edgetpu` in the main env. Coral uses its own venv only.
- Use Picamera2 + GStreamer; GPIO via python-periphery + lgpio; serial via pyserial.
- Every code change updates /docs and /spec (CI fails if drift).
- No TODOs unless `TODO(v3):` with a linked GitHub issue.
