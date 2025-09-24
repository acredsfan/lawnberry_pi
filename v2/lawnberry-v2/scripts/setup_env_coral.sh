#!/usr/bin/env bash
set -euo pipefail
python3 -m venv venv-coral
./venv-coral/bin/pip install --upgrade pip
# Keep Coral deps inside venv-coral only (add after you validate versions on your Pi image)
# e.g., sudo apt install -y libedgetpu1-std && ./venv-coral/bin/pip install tflite-runtime==<good_version>
echo "LBY_ACCEL=coral" | sudo tee -a /etc/environment >/devNull
