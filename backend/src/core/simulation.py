from __future__ import annotations

import os


def is_simulation_mode() -> bool:
    return os.environ.get("SIM_MODE", "0") in ("1", "true", "True")
