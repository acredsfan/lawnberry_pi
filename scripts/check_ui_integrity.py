#!/usr/bin/env python3
"""UI Asset Integrity Check Script.

Ensures built web UI assets exist before backend starts. Intended for ExecStartPre.
Exit codes:
 0 OK
 1 Missing index.html
 2 Dist directory missing
 3 No hashed JS bundles
 4 No hashed CSS bundles
"""
from __future__ import annotations
import os, sys, re, time
from pathlib import Path

START = time.time()
HASHED = re.compile(r"-[0-9a-f]{6,}\.(?:js|css)$")

def candidates():
    env = os.getenv("LAWNBERY_UI_DIR")
    if env:
        yield Path(env).expanduser()
    yield Path("web-ui")/"dist"
    yield Path("/opt/lawnberry/web-ui/dist")
    yield Path(__file__).resolve().parent.parent/"web-ui"/"dist"

def locate_dist():
    for c in candidates():
        if (c/"index.html").exists():
            return c
    for c in candidates():
        if c.exists():
            return c
    return None

def main()->int:
    dist = locate_dist()
    if not dist or not dist.exists():
        print("[UI-INTEGRITY] FAIL: dist directory not found", flush=True); return 2
    index = dist/"index.html"
    if not index.exists():
        print(f"[UI-INTEGRITY] FAIL: index.html missing in {dist}", flush=True); return 1
    js, css = [], []
    try:
        # scan top level
        for p in dist.iterdir():
            if p.is_file() and HASHED.search(p.name):
                if p.suffix == '.js': js.append(p.name)
                elif p.suffix == '.css': css.append(p.name)
        # scan assets/ subdir (Vite often places hashed assets here)
        assets_dir = dist / 'assets'
        if assets_dir.exists():
            for p in assets_dir.iterdir():
                if p.is_file() and HASHED.search(p.name):
                    if p.suffix == '.js' and p.name not in js:
                        js.append(p.name)
                    elif p.suffix == '.css' and p.name not in css:
                        css.append(p.name)
    except Exception as e:
        print(f"[UI-INTEGRITY] WARN: scan error: {e}", flush=True)
    if not js:
        print(f"[UI-INTEGRITY] FAIL: no hashed JS bundles in {dist}", flush=True); return 3
    if not css:
        print(f"[UI-INTEGRITY] FAIL: no hashed CSS bundles in {dist}", flush=True); return 4
    dur = int((time.time()-START)*1000)
    print(f"[UI-INTEGRITY] OK: index + {len(js)} JS + {len(css)} CSS bundles present ({dur}ms) {dist}", flush=True)
    return 0

if __name__ == '__main__':
    sys.exit(main())
