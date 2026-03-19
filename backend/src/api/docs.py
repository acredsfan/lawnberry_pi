from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from functools import lru_cache
from hashlib import sha256
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

router = APIRouter()

ROOT_DIR = Path(os.getcwd())
DOCS_DIR = ROOT_DIR / "docs"
VERIFICATION_DIR = ROOT_DIR / "verification_artifacts"
DOCS_BUNDLE_DIR = VERIFICATION_DIR / "docs-bundle"
ARTIFACT_REGISTRY_DIR = VERIFICATION_DIR / "registry"
REQUIREMENTS_SOURCES = (
    ROOT_DIR / ".specify" / "out" / "spec_005.md",
    ROOT_DIR / "docs" / "OPERATIONS.md",
)
_REQUIREMENT_RE = re.compile(r"\bFR-\d{3}\b")


class VerificationArtifactCreateRequest(BaseModel):
    type: str
    location: str
    summary: str = ""
    linked_requirements: list[str] = Field(default_factory=list)
    created_by: str = "automation"
    metadata: dict[str, Any] = Field(default_factory=dict)


@lru_cache(maxsize=1)
def _known_requirements() -> frozenset[str]:
    known: set[str] = set()
    for path in REQUIREMENTS_SOURCES:
        try:
            if path.exists():
                known.update(_REQUIREMENT_RE.findall(path.read_text(encoding="utf-8")))
        except Exception:
            continue
    if not known:
        known.update({"FR-001", "FR-016", "FR-047"})
    return frozenset(known)


def _checksum_for_path(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def _doc_title(path: Path) -> str:
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if stripped.startswith("# "):
                return stripped[2:].strip()
    except Exception:
        pass
    return path.stem.replace("-", " ").replace("_", " ").title()


def _doc_version(path: Path) -> str:
    modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return modified.strftime("%Y.%m.%d")


def _docs_offline_ready() -> bool:
    return DOCS_BUNDLE_DIR.exists() and any(DOCS_BUNDLE_DIR.iterdir())


def _docs_bundle_items() -> list[dict[str, Any]]:
    if not DOCS_DIR.exists():
        return []
    items: list[dict[str, Any]] = []
    for path in sorted(DOCS_DIR.glob("*.md")):
        modified = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
        items.append(
            {
                "doc_id": path.stem,
                "title": _doc_title(path),
                "version": _doc_version(path),
                "last_updated": modified.isoformat(),
                "checksum": _checksum_for_path(path),
                "offline_available": _docs_offline_ready(),
            }
        )
    return items


def _write_artifact_record(payload: dict[str, Any]) -> None:
    ARTIFACT_REGISTRY_DIR.mkdir(parents=True, exist_ok=True)
    target = ARTIFACT_REGISTRY_DIR / f"{payload['artifact_id']}.json"
    target.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


@router.get("/api/v2/docs/list")
def get_docs_list() -> dict[str, Any]:
    items = _docs_bundle_items()
    return {
        "items": [
            {
                "doc_id": item["doc_id"],
                "title": item["title"],
                "last_updated": item["last_updated"],
            }
            for item in items
        ]
    }


@router.get("/api/v2/docs/bundle")
def get_docs_bundle(simulate_checksum_mismatch: str | None = Query(default=None)) -> JSONResponse:
    items = _docs_bundle_items()
    headers = {
        "x-docs-offline-ready": "true" if _docs_offline_ready() else "false",
    }
    doc_ids = {item["doc_id"] for item in items}
    if simulate_checksum_mismatch and simulate_checksum_mismatch in doc_ids:
        headers["x-docs-checksum-warning"] = simulate_checksum_mismatch
    return JSONResponse(content={"items": items}, headers=headers)


@router.post("/api/v2/verification-artifacts", status_code=201)
def create_verification_artifact(payload: VerificationArtifactCreateRequest) -> JSONResponse:
    linked_requirements = [req.strip().upper() for req in payload.linked_requirements if req and req.strip()]
    if not linked_requirements:
        return JSONResponse(
            status_code=422,
            content={
                "error_code": "MISSING_REQUIREMENTS",
                "detail": "At least one linked requirement is required",
                "remediation_url": "/docs/OPERATIONS.md#verification-artifacts",
            },
        )

    unknown = sorted(set(linked_requirements) - set(_known_requirements()))
    if unknown:
        return JSONResponse(
            status_code=422,
            content={
                "error_code": "UNKNOWN_REQUIREMENT",
                "detail": f"Unknown requirement IDs: {', '.join(unknown)}",
                "unknown_requirements": unknown,
            },
        )

    created_at = datetime.now(timezone.utc).isoformat()
    artifact_id = str(uuid.uuid4())
    record = {
        "artifact_id": artifact_id,
        "type": payload.type,
        "location": payload.location,
        "summary": payload.summary,
        "linked_requirements": linked_requirements,
        "created_by": payload.created_by,
        "metadata": payload.metadata,
        "created_at": created_at,
    }
    _write_artifact_record(record)
    return JSONResponse(status_code=201, content=record)
