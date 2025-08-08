"""Map storage abstraction.

Provides simple async CRUD style access for boundaries, no‑go zones and home
locations with a pluggable backend (JSON file fallback if Redis not present).

Design goals (Raspberry Pi constraints):
 - Avoid keeping large polygons in memory unnecessarily (but current expected
   counts are small < 200 so simple caching acceptable)
 - Non‑blocking file IO using asyncio.to_thread
 - Defensive validation & versioning metadata for future migrations
"""
from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any
import json
import asyncio
from pathlib import Path
from datetime import datetime

from pydantic import ValidationError

from web_api.models import Boundary, NoGoZone, HomeLocation  # absolute import: web_api is sibling top-level package

DATA_DIR = Path("data")
DATA_FILE = DATA_DIR / "maps_state.json"

_LOCK = asyncio.Lock()


@dataclass
class _State:  # internal representation
    version: int
    updated_at: str
    boundaries: List[Dict[str, Any]]
    no_go_zones: List[Dict[str, Any]]
    home_locations: List[Dict[str, Any]]

    @staticmethod
    def empty() -> "_State":
        return _State(
            version=1,
            updated_at=datetime.utcnow().isoformat(),
            boundaries=[],
            no_go_zones=[],
            home_locations=[],
        )


_cache: Optional[_State] = None


async def _ensure_loaded() -> _State:
    global _cache
    if _cache is not None:
        return _cache
    async with _LOCK:
        if _cache is not None:
            return _cache
        if not DATA_FILE.exists():
            DATA_DIR.mkdir(parents=True, exist_ok=True)
            _cache = _State.empty()
            await _persist_locked()
            return _cache
        raw = await asyncio.to_thread(DATA_FILE.read_text, encoding="utf-8")
        try:
            data = json.loads(raw)
            _cache = _State(
                version=data.get("version", 1),
                updated_at=data.get("updated_at", datetime.utcnow().isoformat()),
                boundaries=data.get("boundaries", []),
                no_go_zones=data.get("no_go_zones", []),
                home_locations=data.get("home_locations", []),
            )
        except Exception:  # noqa: BLE001
            # Corrupt file – start fresh (do NOT delete original for forensics; rename)
            backup = DATA_FILE.with_suffix(".corrupt")
            try:
                DATA_FILE.rename(backup)
            except Exception:  # noqa: BLE001
                pass
            _cache = _State.empty()
            await _persist_locked()
        return _cache


async def _persist_locked() -> None:
    """Persist the cache to disk (call with _LOCK held)."""
    assert _cache is not None
    payload = json.dumps(asdict(_cache), separators=(",", ":"))
    await asyncio.to_thread(DATA_FILE.write_text, payload, "utf-8")


async def get_boundaries() -> List[Boundary]:
    state = await _ensure_loaded()
    out: List[Boundary] = []
    for b in state.boundaries:
        try:
            out.append(Boundary(**b))
        except ValidationError:
            continue
    return out


async def replace_boundaries(boundaries: List[Boundary]) -> None:
    global _cache
    async with _LOCK:
        state = await _ensure_loaded()
        state.boundaries = [b.model_dump() for b in boundaries]
        state.updated_at = datetime.utcnow().isoformat()
        await _persist_locked()


async def add_boundary(boundary: Boundary) -> None:
    async with _LOCK:
        state = await _ensure_loaded()
        state.boundaries.append(boundary.model_dump())
        state.updated_at = datetime.utcnow().isoformat()
        await _persist_locked()


async def delete_boundary_by_name(name: str) -> bool:
    async with _LOCK:
        state = await _ensure_loaded()
        before = len(state.boundaries)
        state.boundaries = [b for b in state.boundaries if b.get("name") != name]
        changed = len(state.boundaries) != before
        if changed:
            state.updated_at = datetime.utcnow().isoformat()
            await _persist_locked()
        return changed


async def get_no_go_zones() -> List[NoGoZone]:
    state = await _ensure_loaded()
    out: List[NoGoZone] = []
    for z in state.no_go_zones:
        try:
            out.append(NoGoZone(**z))
        except ValidationError:
            continue
    return out


async def add_no_go_zone(zone: NoGoZone) -> None:
    async with _LOCK:
        state = await _ensure_loaded()
        state.no_go_zones.append(zone.model_dump())
        state.updated_at = datetime.utcnow().isoformat()
        await _persist_locked()


async def update_no_go_zone(name: str, updates: Dict[str, Any]) -> bool:
    async with _LOCK:
        state = await _ensure_loaded()
        changed = False
        for z in state.no_go_zones:
            if z.get("name") == name:
                z.update(updates)
                changed = True
                break
        if changed:
            state.updated_at = datetime.utcnow().isoformat()
            await _persist_locked()
        return changed


async def delete_no_go_zone(name: str) -> bool:
    async with _LOCK:
        state = await _ensure_loaded()
        before = len(state.no_go_zones)
        state.no_go_zones = [z for z in state.no_go_zones if z.get("name") != name]
        changed = len(state.no_go_zones) != before
        if changed:
            state.updated_at = datetime.utcnow().isoformat()
            await _persist_locked()
        return changed


async def get_home_locations() -> List[HomeLocation]:
    state = await _ensure_loaded()
    out: List[HomeLocation] = []
    for h in state.home_locations:
        try:
            out.append(HomeLocation(**h))
        except ValidationError:
            continue
    return out


async def add_home_location(loc: HomeLocation) -> None:
    async with _LOCK:
        state = await _ensure_loaded()
        state.home_locations.append(loc.model_dump())
        state.updated_at = datetime.utcnow().isoformat()
        await _persist_locked()


async def update_home_location(location_id: str, loc: HomeLocation) -> bool:
    async with _LOCK:
        state = await _ensure_loaded()
        for i, h in enumerate(state.home_locations):
            if h.get("id") == location_id:
                state.home_locations[i] = loc.model_dump()
                state.updated_at = datetime.utcnow().isoformat()
                await _persist_locked()
                return True
        return False


async def delete_home_location(location_id: str) -> bool:
    async with _LOCK:
        state = await _ensure_loaded()
        before = len(state.home_locations)
        state.home_locations = [h for h in state.home_locations if h.get("id") != location_id]
        changed = len(state.home_locations) != before
        if changed:
            state.updated_at = datetime.utcnow().isoformat()
            await _persist_locked()
        return changed


async def set_default_home_location(location_id: str) -> bool:
    async with _LOCK:
        state = await _ensure_loaded()
        found = False
        for h in state.home_locations:
            if h.get("id") == location_id:
                h["is_default"] = True
                h["updated_at"] = datetime.utcnow().isoformat()
                found = True
            else:
                h["is_default"] = False
        if found:
            state.updated_at = datetime.utcnow().isoformat()
            await _persist_locked()
        return found


async def export_state() -> Dict[str, Any]:
    state = await _ensure_loaded()
    return asdict(state)
