import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import numpy as np  # noqa: E402
import pytest  # noqa: E402


class StubInterpreter:
    """Stub implementation mimicking the minimal TFLite interpreter API."""

    def __init__(self, *, input_shape, output_details, outputs):
        self._input_details = [
            {
                "shape": np.array(input_shape, dtype=np.int32),
                "dtype": np.float32,
                "index": 0,
            }
        ]
        self._output_details = output_details
        self._outputs = outputs
        self.allocate_called = False
        self.invoke_called = False
        self.set_tensors = []

    def allocate_tensors(self):
        self.allocate_called = True

    def get_input_details(self):
        return self._input_details

    def get_output_details(self):
        return self._output_details

    def set_tensor(self, index, value):
        self.set_tensors.append((index, value))

    def invoke(self):
        self.invoke_called = True

    def get_tensor(self, index):
        return self._outputs[index]


@pytest.fixture
def detection_outputs():
    boxes = np.array([[[0.1, 0.1, 0.3, 0.3], [0.4, 0.4, 0.6, 0.6]]], dtype=np.float32)
    scores = np.array([[0.95, 0.25]], dtype=np.float32)
    classes = np.array([[1, 0]], dtype=np.float32)
    count = np.array([2], dtype=np.float32)
    output_details = [
        {"index": 0, "name": "detection_boxes"},
        {"index": 1, "name": "detection_scores"},
        {"index": 2, "name": "detection_classes"},
        {"index": 3, "name": "num_detections"},
    ]
    outputs = {
        0: boxes,
        1: scores,
        2: classes,
        3: count,
    }
    return output_details, outputs


def test_warmup_runs_single_inference(monkeypatch, detection_outputs):
    output_details, outputs = detection_outputs
    stub = StubInterpreter(
        input_shape=(1, 720, 1280, 3),
        output_details=output_details,
        outputs=outputs,
    )

    from lawnberry.runners.cpu_tflite_runner import CpuTFLiteDetector

    detector = CpuTFLiteDetector(
        model_path="/tmp/model.tflite",
        interpreter_factory=lambda path: stub,
    )

    detector.warmup()

    assert stub.allocate_called is True
    assert stub.invoke_called is True
    assert stub.set_tensors, "Warmup should set an input tensor"
    index, tensor = stub.set_tensors[-1]
    assert index == 0
    assert tensor.shape == (1, 720, 1280, 3)
    assert tensor.dtype == np.float32
    assert np.allclose(tensor, -1.0, atol=1e-6), "Warmup tensor should be normalized"


def test_infer_returns_filtered_detections(monkeypatch, detection_outputs):
    output_details, outputs = detection_outputs
    stub = StubInterpreter(
        input_shape=(1, 300, 300, 3),
        output_details=output_details,
        outputs=outputs,
    )

    from lawnberry.runners.cpu_tflite_runner import CpuTFLiteDetector

    detector = CpuTFLiteDetector(
        model_path="/tmp/model.tflite",
        interpreter_factory=lambda path: stub,
        label_map={0: "background", 1: "rock"},
        score_threshold=0.4,
    )

    frame = np.random.randint(0, 255, (720, 1280, 3), dtype=np.uint8)

    detections = detector.infer(frame)

    assert stub.allocate_called is True
    assert stub.invoke_called is True
    assert len(detections) == 1
    detection = detections[0]
    assert detection["label"] == "rock"
    assert detection["confidence"] == pytest.approx(0.95, rel=1e-3)
    assert detection["bbox"]["xmin"] == pytest.approx(0.1, rel=1e-3)


def test_infer_raises_when_interpreter_missing():
    from lawnberry.runners.cpu_tflite_runner import CpuTFLiteDetector

    def failing_factory(model_path):
        raise ImportError("tflite-runtime not installed")

    detector = CpuTFLiteDetector(
        model_path="/tmp/model.tflite",
        interpreter_factory=failing_factory,
    )

    with pytest.raises(RuntimeError, match="tflite-runtime"):
        detector.warmup()


def test_infer_rejects_invalid_frame_shape(monkeypatch, detection_outputs):
    output_details, outputs = detection_outputs
    stub = StubInterpreter(
        input_shape=(1, 64, 64, 3),
        output_details=output_details,
        outputs=outputs,
    )

    from lawnberry.runners.cpu_tflite_runner import CpuTFLiteDetector

    detector = CpuTFLiteDetector(
        model_path="/tmp/model.tflite",
        interpreter_factory=lambda path: stub,
    )

    with pytest.raises(ValueError):
        detector.infer(np.zeros((720, 1280), dtype=np.uint8))
