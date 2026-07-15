from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from backend.src.services.detector_runtime import DetectorManifest
from scripts import provision_ai_detector as provisioner


def _write_template(root: Path) -> Path:
    template = root / provisioner.MANIFEST_TEMPLATE_RELATIVE_PATH
    template.parent.mkdir(parents=True)
    template.write_text(
        json.dumps(
            {
                "model_name": "baseline",
                "model_path": "../models/lawnberry-obstacle-detector.onnx",
                "model_format": "onnx",
                "runtime": "opencv_dnn",
                "input_width": 32,
                "input_height": 32,
                "class_labels": ["person"],
                "output_format": "yolov5",
            }
        ),
        encoding="utf-8",
    )
    return template


class _FakeRuntime:
    validated_manifests: list[Path] = []

    def __init__(self, manifest_path: Path) -> None:
        self.manifest_path = Path(manifest_path)
        payload = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        configured_model = Path(payload["model_path"])
        self.model_path = (self.manifest_path.parent / configured_model).resolve()
        self.manifest = DetectorManifest.model_validate(payload)
        self.model_sha256 = ""
        self.ready = False

    def initialize(self) -> None:
        self.model_sha256 = hashlib.sha256(self.model_path.read_bytes()).hexdigest()
        self.ready = True

    def infer(self, _image, confidence_threshold: float):
        assert confidence_threshold == 1.0
        self.validated_manifests.append(self.manifest_path)
        return []


@pytest.fixture(autouse=True)
def _fake_runtime(monkeypatch):
    _FakeRuntime.validated_manifests = []
    monkeypatch.setattr(provisioner, "OpenCVDnnDetectorRuntime", _FakeRuntime)


def test_existing_manifest_and_model_are_verified_without_overwrite(
    tmp_path: Path,
    monkeypatch,
) -> None:
    template = _write_template(tmp_path)
    manifest = tmp_path / provisioner.MANIFEST_RELATIVE_PATH
    manifest.write_bytes(template.read_bytes())
    model = tmp_path / provisioner.MODEL_RELATIVE_PATH
    model.parent.mkdir(parents=True)
    original_model = b"existing-pinned-model"
    model.write_bytes(original_model)
    original_manifest = manifest.read_bytes()
    monkeypatch.setattr(provisioner, "MODEL_SHA256", hashlib.sha256(original_model).hexdigest())

    def unexpected_download(_url: str, _destination: Path) -> None:
        raise AssertionError("an existing model must not trigger a download")

    result = provisioner.provision_detector(root=tmp_path, downloader=unexpected_download)

    assert result.model_created is False
    assert result.manifest_created is False
    assert model.read_bytes() == original_model
    assert manifest.read_bytes() == original_manifest
    assert _FakeRuntime.validated_manifests == [manifest]


def test_checksum_failure_discards_download_and_creates_no_manifest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_template(tmp_path)
    monkeypatch.setattr(provisioner, "MODEL_SHA256", hashlib.sha256(b"expected").hexdigest())

    def corrupt_download(_url: str, destination: Path) -> None:
        destination.write_bytes(b"corrupt")

    with pytest.raises(provisioner.ProvisionError, match="checksum mismatch"):
        provisioner.provision_detector(
            root=tmp_path,
            accept_gpl_3=True,
            downloader=corrupt_download,
        )

    assert not (tmp_path / provisioner.MODEL_RELATIVE_PATH).exists()
    assert not (tmp_path / provisioner.MANIFEST_RELATIVE_PATH).exists()
    assert list((tmp_path / "models").iterdir()) == []
    assert _FakeRuntime.validated_manifests == []


def test_missing_files_are_installed_after_acknowledgement(
    tmp_path: Path,
    monkeypatch,
) -> None:
    template = _write_template(tmp_path)
    downloaded_model = b"downloaded-pinned-model"
    monkeypatch.setattr(
        provisioner,
        "MODEL_SHA256",
        hashlib.sha256(downloaded_model).hexdigest(),
    )

    def local_download(url: str, destination: Path) -> None:
        assert url == provisioner.MODEL_URL
        destination.write_bytes(downloaded_model)

    result = provisioner.provision_detector(
        root=tmp_path,
        accept_gpl_3=True,
        downloader=local_download,
    )

    assert result.model_created is True
    assert result.manifest_created is True
    assert result.model_path.read_bytes() == downloaded_model
    assert result.manifest_path.read_bytes() == template.read_bytes()
    assert _FakeRuntime.validated_manifests == [template, result.manifest_path]
    assert not list((tmp_path / "models").glob(".*.tmp"))


def test_missing_model_requires_explicit_license_acknowledgement(tmp_path: Path) -> None:
    _write_template(tmp_path)

    def unexpected_download(_url: str, _destination: Path) -> None:
        raise AssertionError("download must not start before license acknowledgement")

    with pytest.raises(provisioner.ProvisionError, match="--accept-gpl-3.0"):
        provisioner.provision_detector(root=tmp_path, downloader=unexpected_download)

    assert not (tmp_path / provisioner.MODEL_RELATIVE_PATH).exists()
    assert not (tmp_path / provisioner.MANIFEST_RELATIVE_PATH).exists()


def test_verify_only_has_no_side_effects_when_runtime_files_are_missing(tmp_path: Path) -> None:
    _write_template(tmp_path)

    with pytest.raises(provisioner.ProvisionError, match="missing"):
        provisioner.provision_detector(root=tmp_path, verify_only=True)

    assert not (tmp_path / "models").exists()
    assert not (tmp_path / provisioner.MANIFEST_RELATIVE_PATH).exists()
