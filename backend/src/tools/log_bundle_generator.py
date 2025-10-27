"""Log bundle generator (FR-044).

Creates a tar.gz archive including key logs and minimal metadata. Safe to run
on CI where logs may be missing; it will include whatever exists.
"""

import datetime as dt
import io
import os
import tarfile
import uuid
from pathlib import Path

DEFAULT_LOG_DIRS = [
    Path("./logs"),
]

def generate_log_bundle(time_range_minutes: int | None = None) -> tuple[str, bytes, int, list[str]]:
    """Create a tar.gz bundle in-memory.

    Returns: (bundle_id, tar_bytes, size_bytes, included_files)
    """
    bundle_id = uuid.uuid4().hex
    included: list[str] = []
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        # Include known log files if present
        candidates = [
            "backend.log",
            "safety.log",
            "sensors.log",
            "navigation.log",
        ]
        for d in DEFAULT_LOG_DIRS:
            if not d.exists():
                continue
            for name in candidates:
                p = d / name
                if p.exists():
                    data = p.read_bytes()
                    ti = tarfile.TarInfo(name=f"logs/{name}")
                    ti.size = len(data)
                    ti.mtime = int(dt.datetime.now(dt.UTC).timestamp())
                    tar.addfile(ti, io.BytesIO(data))
                    included.append(str(p))
        # Add minimal metadata file
        meta = {
            "bundle_id": bundle_id,
            "created_at": dt.datetime.now(dt.UTC).isoformat(),
            "time_range_minutes": time_range_minutes,
            "host": os.uname().nodename if hasattr(os, "uname") else "unknown",
        }
        import json
        meta_bytes = json.dumps(meta, indent=2).encode()
        ti = tarfile.TarInfo(name="metadata.json")
        ti.size = len(meta_bytes)
        ti.mtime = int(dt.datetime.now(dt.UTC).timestamp())
        tar.addfile(ti, io.BytesIO(meta_bytes))

    buf.seek(0)
    tar_bytes = buf.getvalue()
    return bundle_id, tar_bytes, len(tar_bytes), included
