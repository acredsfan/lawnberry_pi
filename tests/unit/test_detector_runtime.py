from __future__ import annotations

import builtins
import time

import numpy as np
import pytest

from backend.src.services.detector_runtime import (
    DetectorManifest,
    DetectorRuntimeError,
    OpenCVDnnDetectorRuntime,
    parse_detector_output,
)


def _manifest(**overrides) -> DetectorManifest:
    values = {
        "model_name": "detector",
        "model_path": "detector.onnx",
        "input_width": 640,
        "input_height": 640,
        "class_labels": ["person", "obstacle"],
    }
    values.update(overrides)
    return DetectorManifest.model_validate(values)


def test_yolov8_output_is_typed_normalized_and_nms_filtered() -> None:
    manifest = _manifest(output_format="yolov8")
    # [x, y, w, h, person score, obstacle score], transposed model layout.
    output = np.asarray(
        [
            [320, 322],
            [320, 322],
            [200, 200],
            [200, 200],
            [0.92, 0.80],
            [0.08, 0.20],
        ],
        dtype=np.float32,
    )[None, ...]

    detections = parse_detector_output(
        output,
        manifest=manifest,
        confidence_threshold=0.5,
        nms_threshold=0.4,
    )

    assert len(detections) == 1
    assert detections[0].class_name == "person"
    assert detections[0].confidence == pytest.approx(0.92)
    assert detections[0].x == pytest.approx(220 / 640)


def test_yolov5_full_output_filters_in_vectorized_pi_budget() -> None:
    manifest = DetectorManifest(
        model_name="yolov5n",
        model_path="detector.onnx",
        input_width=640,
        input_height=640,
        class_labels=[f"class-{index}" for index in range(80)],
        output_format="yolov5",
    )
    output = np.zeros((1, 25_200, 85), dtype=np.float32)
    output[0, 123, :4] = [320.0, 320.0, 100.0, 100.0]
    output[0, 123, 4] = 0.9
    output[0, 123, 5] = 0.8

    started = time.perf_counter()
    detections = parse_detector_output(
        output,
        manifest=manifest,
        confidence_threshold=0.5,
        nms_threshold=0.4,
    )
    elapsed = time.perf_counter() - started

    assert len(detections) == 1
    assert detections[0].class_name == "class-0"
    # Target-Pi regression budget. Vectorized filtering is ~20 ms on this Pi;
    # 250 ms leaves broad CI load headroom while catching a 25,200-row Python loop.
    assert elapsed < 0.25


def test_xyxy_output_rejects_unknown_class_and_invalid_shape() -> None:
    manifest = _manifest(output_format="xyxy")
    detections = parse_detector_output(
        np.asarray([[10, 20, 110, 220, 0.8, 99]], dtype=np.float32),
        manifest=manifest,
        confidence_threshold=0.5,
        nms_threshold=0.4,
    )
    assert detections == []

    with pytest.raises(DetectorRuntimeError, match="shape"):
        parse_detector_output(
            np.zeros((2, 2, 2), dtype=np.float32),
            manifest=manifest,
            confidence_threshold=0.5,
            nms_threshold=0.4,
        )


def test_runtime_missing_artifact_is_explicitly_unavailable(tmp_path) -> None:
    manifest_path = tmp_path / "detector.json"
    manifest_path.write_text(
        _manifest(model_path="missing.onnx").model_dump_json(),
        encoding="utf-8",
    )
    runtime = OpenCVDnnDetectorRuntime(manifest_path)

    with pytest.raises(DetectorRuntimeError, match="not found"):
        runtime.initialize()
    assert runtime.ready is False


def test_runtime_missing_opencv_names_supported_hardware_install(monkeypatch, tmp_path) -> None:
    model_path = tmp_path / "detector.onnx"
    model_path.write_bytes(b"not-read-when-opencv-is-missing")
    manifest_path = tmp_path / "detector.json"
    manifest_path.write_text(
        _manifest(model_path=model_path.name).model_dump_json(),
        encoding="utf-8",
    )
    runtime = OpenCVDnnDetectorRuntime(manifest_path)
    real_import = builtins.__import__

    def reject_cv2(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "cv2":
            raise ImportError("cv2 unavailable")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", reject_cv2)

    with pytest.raises(DetectorRuntimeError, match=r"uv sync --extra hardware"):
        runtime.initialize()


def test_manifest_rejects_unknown_or_cost_reducing_semantic_classes() -> None:
    with pytest.raises(ValueError, match="unknown labels"):
        _manifest(semantic_cost_multipliers={"not-a-model-class": 2.0})

    with pytest.raises(ValueError, match="cannot reduce"):
        _manifest(semantic_cost_multipliers={"person": 0.5})
