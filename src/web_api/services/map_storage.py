"""
Map storage service
Provides async helpers to persist and retrieve boundaries, no-go zones, and home locations.
Backed by a JSON file on disk to survive restarts.
"""
from __future__ import annotations

from pathlib import Path
from typing import List, Dict, Any, Optional
import json
import os
import asyncio

from ..models import Boundary, NoGoZone, HomeLocation, Position, HomeLocationType


class _MapStorage:
    def __init__(self) -> None:
        # Determine storage path with robust fallbacks (prefer writable locations)
        # Note: env var name spelled correctly as LAWNBERRY_MAPS_STATE_PATH
        path_env = os.getenv("LAWNBERRY_MAPS_STATE_PATH") or os.getenv("LAWNBERY_MAPS_STATE_PATH")
        candidates: List[Path] = []
        if path_env:
            candidates.append(Path(path_env).expanduser())
        # Primary runtime location under /opt
        candidates.append(Path("/opt/lawnberry/data/maps_state.json"))
        # Repository workspace fallback (useful for dev/testing)
        candidates.append(Path(__file__).resolve().parents[3] / "data" / "maps_state.json")

        chosen: Optional[Path] = None
        for c in candidates:
            try:
                c.parent.mkdir(parents=True, exist_ok=True)
                # If directory is creatable, accept and break
                chosen = c
                break
            except Exception:
                continue
        # As a last resort, just take the first candidate (will likely error on write, but avoids None)
        self._state_path = chosen or candidates[0]

        # Ensure parent directory exists (best effort)
        try:
            self._state_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception:
            pass

        # Async lock to serialize writes
        self._lock = asyncio.Lock()

    def _load_raw(self) -> Dict[str, Any]:
        p = self._state_path
        if not p.exists():
            return {"boundaries": [], "no_go_zones": [], "home_locations": []}
        try:
            with p.open("r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {"boundaries": [], "no_go_zones": [], "home_locations": []}

    def _save_raw(self, data: Dict[str, Any]) -> None:
        tmp = self._state_path.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        tmp.replace(self._state_path)

    async def get_boundaries(self) -> List[Boundary]:
        data = self._load_raw()
        result: List[Boundary] = []
        for b in data.get("boundaries", []):
            try:
                pts = [Position(**pt) for pt in b.get("points", [])]
                result.append(Boundary(points=pts, name=b.get("name", "boundary")))
            except Exception:
                continue
        return result

    async def get_no_go_zones(self) -> List[NoGoZone]:
        data = self._load_raw()
        result: List[NoGoZone] = []
        for z in data.get("no_go_zones", []):
            try:
                pts = [Position(**pt) for pt in z.get("points", [])]
                result.append(NoGoZone(points=pts, name=z.get("name", "no_go"), priority=z.get("priority", "high")))
            except Exception:
                continue
        return result

    async def get_home_locations(self) -> List[HomeLocation]:
        data = self._load_raw()
        result: List[HomeLocation] = []
        for h in data.get("home_locations", []):
            try:
                pos = Position(**h.get("position", {}))
                t = h.get("type", HomeLocationType.CHARGING_STATION)
                result.append(HomeLocation(
                    id=h.get("id", "home-1"),
                    name=h.get("name", "Home"),
                    type=t,
                    custom_type=h.get("custom_type"),
                    position=pos,
                    is_default=bool(h.get("is_default", False)),
                    description=h.get("description")
                ))
            except Exception:
                continue
        return result

    async def add_boundary(self, boundary: Boundary) -> None:
        async with self._lock:
            data = self._load_raw()
            b = {"name": boundary.name, "points": [p.dict() for p in boundary.points]}
            items = data.get("boundaries", [])
            # Replace by name if exists
            for i, existing in enumerate(items):
                if existing.get("name") == boundary.name:
                    items[i] = b
                    break
            else:
                items.append(b)
            data["boundaries"] = items
            self._save_raw(data)

    async def delete_boundary_by_name(self, name: str) -> bool:
        async with self._lock:
            data = self._load_raw()
            items = data.get("boundaries", [])
            new_items = [b for b in items if b.get("name") != name]
            deleted = len(new_items) != len(items)
            data["boundaries"] = new_items
            self._save_raw(data)
            return deleted

    # ---- No-go zones CRUD to align with router usage ----
    async def add_no_go_zone(self, zone: NoGoZone) -> None:
        async with self._lock:
            data = self._load_raw()
            z = {
                "name": zone.name,
                "priority": zone.priority,
                "points": [p.dict() for p in zone.points],
            }
            items = data.get("no_go_zones", [])
            # Replace by name if exists
            for i, existing in enumerate(items):
                if existing.get("name") == zone.name:
                    items[i] = z
                    break
            else:
                items.append(z)
            data["no_go_zones"] = items
            self._save_raw(data)

    async def update_no_go_zone(self, name: str, updates: Dict[str, Any]) -> bool:
        async with self._lock:
            data = self._load_raw()
            items = data.get("no_go_zones", [])
            changed = False
            for i, existing in enumerate(items):
                if existing.get("name") == name:
                    # Only allow specific fields to be updated
                    allowed = {k: v for k, v in updates.items() if k in {"name", "priority", "points"}}
                    # Normalize points if provided
                    if "points" in allowed and isinstance(allowed["points"], list):
                        try:
                            allowed["points"] = [Position(**pt).dict() for pt in allowed["points"]]
                        except Exception:
                            # If validation fails, skip points update
                            allowed.pop("points", None)
                    items[i].update(allowed)
                    changed = True
                    break
            if changed:
                data["no_go_zones"] = items
                self._save_raw(data)
            return changed

    async def delete_no_go_zone(self, name: str) -> bool:
        async with self._lock:
            data = self._load_raw()
            items = data.get("no_go_zones", [])
            new_items = [z for z in items if z.get("name") != name]
            changed = len(new_items) != len(items)
            data["no_go_zones"] = new_items
            self._save_raw(data)
            return changed


# Singleton instance for easy import
map_storage = _MapStorage()
