from __future__ import annotations

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


def test_manifest_rejects_unknown_or_cost_reducing_semantic_classes() -> None:
    with pytest.raises(ValueError, match="unknown labels"):
        _manifest(semantic_cost_multipliers={"not-a-model-class": 2.0})

    with pytest.raises(ValueError, match="cannot reduce"):
        _manifest(semantic_cost_multipliers={"person": 0.5})
