#!/usr/bin/env python3
"""Provision and verify LawnBerry's pinned baseline ONNX detector."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import sys
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import httpx
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.src.services.detector_runtime import OpenCVDnnDetectorRuntime  # noqa: E402

MODEL_URL = "https://github.com/ultralytics/yolov5/releases/download/v7.0/yolov5n.onnx"
MODEL_SHA256 = "04f0e55c26f58d17145b36045780fe1250d5bd2187543e11568e5141d05b3262"
MODEL_SIZE_BYTES = 3_981_910
MODEL_RELATIVE_PATH = Path("models/lawnberry-obstacle-detector.onnx")
MANIFEST_TEMPLATE_RELATIVE_PATH = Path("config/ai_detector.example.json")
MANIFEST_RELATIVE_PATH = Path("config/ai_detector.json")

Downloader = Callable[[str, Path], None]
BASELINE_COMPATIBILITY_FIELDS = (
    "model_name",
    "model_path",
    "model_format",
    "runtime",
    "version",
    "task",
    "input_width",
    "input_height",
    "class_labels",
    "output_format",
)


class ProvisionError(RuntimeError):
    """Raised when the baseline detector cannot be provisioned truthfully."""


@dataclass(frozen=True, slots=True)
class ProvisionResult:
    manifest_path: Path
    model_path: Path
    model_sha256: str
    manifest_created: bool
    model_created: bool


def _entry_exists(path: Path) -> bool:
    """Return true for every directory entry, including a broken symlink."""
    return os.path.lexists(path)


def _require_regular_file(path: Path, description: str) -> None:
    if path.is_symlink() or not path.is_file():
        raise ProvisionError(f"{description} must be a regular file: {path}")


def _sha256_file(path: Path) -> str:
    try:
        with path.open("rb") as artifact:
            return hashlib.file_digest(artifact, "sha256").hexdigest()
    except OSError as exc:
        raise ProvisionError(f"Failed to hash {path}: {exc}") from exc


def _verify_pinned_model(path: Path) -> str:
    _require_regular_file(path, "Detector model")
    digest = _sha256_file(path)
    if digest != MODEL_SHA256:
        raise ProvisionError(
            f"Detector model checksum mismatch at {path}; refusing to replace the existing file"
        )
    return digest


def _download_to_path(url: str, destination: Path) -> None:
    """Download the pinned artifact to an already-private temporary path."""
    try:
        with (
            httpx.stream(
                "GET",
                url,
                follow_redirects=True,
                headers={"User-Agent": "LawnBerry-AI-Provisioner/1.0"},
                timeout=httpx.Timeout(180.0, connect=30.0),
            ) as response,
            destination.open("wb") as artifact,
        ):
            response.raise_for_status()
            downloaded_bytes = 0
            for chunk in response.iter_bytes():
                downloaded_bytes += len(chunk)
                if downloaded_bytes > MODEL_SIZE_BYTES:
                    raise ProvisionError(
                        "Downloaded detector exceeds the pinned artifact size; aborting"
                    )
                artifact.write(chunk)
            artifact.flush()
            os.fsync(artifact.fileno())
    except (httpx.HTTPError, OSError) as exc:
        raise ProvisionError(f"Failed to download the baseline detector: {exc}") from exc


def _link_without_overwrite(source: Path, destination: Path) -> bool:
    """Atomically install a completed file without ever replacing a destination."""
    try:
        source.chmod(0o644)
        os.link(source, destination)
    except FileExistsError:
        return False
    except OSError as exc:
        raise ProvisionError(f"Failed to install {destination}: {exc}") from exc
    return True


def _copy_without_overwrite(source: Path, destination: Path) -> bool:
    destination.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.install-",
        dir=destination.parent,
    )
    temporary_path = Path(temporary_name)
    try:
        with os.fdopen(file_descriptor, "wb") as target_file, source.open("rb") as source_file:
            shutil.copyfileobj(source_file, target_file)
            target_file.flush()
            os.fsync(target_file.fileno())
        return _link_without_overwrite(temporary_path, destination)
    finally:
        temporary_path.unlink(missing_ok=True)


def _load_runtime_manifest(
    manifest_path: Path,
    expected_model_path: Path,
) -> OpenCVDnnDetectorRuntime:
    try:
        runtime = OpenCVDnnDetectorRuntime(manifest_path)
    except Exception as exc:
        raise ProvisionError(f"Invalid detector manifest {manifest_path}: {exc}") from exc

    if runtime.model_path.resolve() != expected_model_path.resolve():
        raise ProvisionError(
            f"Detector manifest must reference the pinned model at {expected_model_path}"
        )
    return runtime


def _validate_manifest_compatibility(
    manifest_path: Path,
    template_path: Path,
    expected_model_path: Path,
) -> None:
    runtime = _load_runtime_manifest(manifest_path, expected_model_path)
    baseline = _load_runtime_manifest(template_path, expected_model_path)
    mismatches = [
        field
        for field in BASELINE_COMPATIBILITY_FIELDS
        if getattr(runtime.manifest, field) != getattr(baseline.manifest, field)
    ]
    if mismatches:
        raise ProvisionError(
            "Detector manifest is incompatible with the pinned baseline model; "
            f"mismatched fields: {', '.join(mismatches)}"
        )


def _validate_runtime(manifest_path: Path, expected_model_path: Path) -> str:
    runtime = _load_runtime_manifest(manifest_path, expected_model_path)

    try:
        runtime.initialize()
        blank_frame = np.zeros(
            (runtime.manifest.input_height, runtime.manifest.input_width, 3),
            dtype=np.uint8,
        )
        runtime.infer(blank_frame, confidence_threshold=1.0)
    except Exception as exc:
        raise ProvisionError(f"Detector runtime validation failed: {exc}") from exc

    if not runtime.ready:
        raise ProvisionError("Detector runtime did not report ready after validation")
    if runtime.model_sha256 != MODEL_SHA256:
        raise ProvisionError(
            "Detector runtime loaded an artifact whose checksum does not match the pinned baseline"
        )
    return runtime.model_sha256


def provision_detector(
    *,
    root: Path = ROOT,
    accept_gpl_3: bool = False,
    verify_only: bool = False,
    downloader: Downloader = _download_to_path,
) -> ProvisionResult:
    """Provision missing baseline files and prove the configured runtime is usable."""
    root = root.resolve()
    template_path = root / MANIFEST_TEMPLATE_RELATIVE_PATH
    manifest_path = root / MANIFEST_RELATIVE_PATH
    model_path = root / MODEL_RELATIVE_PATH

    if not _entry_exists(template_path):
        raise ProvisionError(f"Tracked detector manifest template is missing: {template_path}")
    _require_regular_file(template_path, "Detector manifest template")

    manifest_exists = _entry_exists(manifest_path)
    model_exists = _entry_exists(model_path)
    if verify_only and (not manifest_exists or not model_exists):
        missing = [
            str(path)
            for path, exists in ((manifest_path, manifest_exists), (model_path, model_exists))
            if not exists
        ]
        raise ProvisionError(f"Detector verification failed; missing: {', '.join(missing)}")

    validation_manifest = manifest_path if manifest_exists else template_path
    if manifest_exists:
        _require_regular_file(manifest_path, "Detector manifest")
    _validate_manifest_compatibility(validation_manifest, template_path, model_path)

    model_created = False
    manifest_created = False
    if model_exists:
        _verify_pinned_model(model_path)
    else:
        if not accept_gpl_3:
            raise ProvisionError(
                "The baseline model is GPL-3.0; pass --accept-gpl-3.0 to acknowledge "
                "the license before downloading it"
            )
        model_path.parent.mkdir(parents=True, exist_ok=True)
        file_descriptor, temporary_name = tempfile.mkstemp(
            prefix=f".{model_path.name}.download-",
            suffix=".tmp",
            dir=model_path.parent,
        )
        os.close(file_descriptor)
        temporary_path = Path(temporary_name)
        try:
            downloader(MODEL_URL, temporary_path)
            downloaded_digest = _sha256_file(temporary_path)
            if downloaded_digest != MODEL_SHA256:
                raise ProvisionError(
                    "Downloaded detector checksum mismatch; the temporary artifact was discarded"
                )
            model_created = _link_without_overwrite(temporary_path, model_path)
        finally:
            temporary_path.unlink(missing_ok=True)
        _verify_pinned_model(model_path)

    digest = _validate_runtime(validation_manifest, model_path)

    if not manifest_exists:
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        manifest_created = _copy_without_overwrite(template_path, manifest_path)
        _require_regular_file(manifest_path, "Detector manifest")
        digest = _validate_runtime(manifest_path, model_path)
    return ProvisionResult(
        manifest_path=manifest_path,
        model_path=model_path,
        model_sha256=digest,
        manifest_created=manifest_created,
        model_created=model_created,
    )


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Provision and verify LawnBerry's pinned YOLOv5n v7 ONNX detector."
    )
    parser.add_argument(
        "--accept-gpl-3.0",
        action="store_true",
        dest="accept_gpl_3",
        help="acknowledge the model's GPL-3.0 license before a network download",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="validate existing files without downloading or creating anything",
    )
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        result = provision_detector(
            root=args.root,
            accept_gpl_3=args.accept_gpl_3,
            verify_only=args.verify_only,
        )
    except ProvisionError as exc:
        print(f"[ai-detector] {exc}", file=sys.stderr)
        return 1

    action = "verified" if args.verify_only else "ready"
    print(f"[ai-detector] {action}: {result.manifest_path}")
    print(f"[ai-detector] model: {result.model_path}")
    print(f"[ai-detector] sha256: {result.model_sha256}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
