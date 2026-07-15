from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from backend.src.models import (
    BoundingBox,
    DetectedObject,
    InferenceResult,
    InferenceTask,
    Obstacle,
    Position,
)
from backend.src.nav.path_planner import PathPlanner
from backend.src.services.navigation_service import NavigationService, ObstacleDetector


def _result(*, age_seconds: float = 0.0, digest: str = "d" * 64) -> InferenceResult:
    return InferenceResult(
        inference_id="inference-1",
        task=InferenceTask.OBSTACLE_DETECTION,
        model_name="detector",
        model_version="1.0",
        model_runtime="opencv_dnn",
        model_sha256=digest,
        timestamp=datetime.now(UTC) - timedelta(seconds=age_seconds),
        source_frame_timestamp=datetime.now(UTC) - timedelta(seconds=age_seconds),
        input_frame_id="frame-1",
        input_width=640,
        input_height=480,
        confidence_threshold=0.5,
        detected_objects=[
            DetectedObject(
                object_id="object-1",
                class_name="person",
                confidence=0.9,
                bounding_box=BoundingBox(x=0.4, y=0.2, width=0.2, height=0.6),
                distance_estimate=2.0,
                relative_bearing=0.0,
                semantic_cost_multiplier=3.0,
            )
        ],
    )


def _navigation() -> NavigationService:
    navigation = NavigationService.__new__(NavigationService)
    navigation.obstacle_detector = ObstacleDetector()
    navigation.navigation_state = SimpleNamespace(
        current_position=Position(latitude=40.0, longitude=-75.0),
        heading=0.0,
        obstacle_map=[],
    )
    assert navigation.configure_perception_source(
        {
            "model_name": "detector",
            "model_version": "1.0",
            "model_runtime": "opencv_dnn",
            "model_sha256": "d" * 64,
            "max_result_age_seconds": 2.0,
        }
    )
    return navigation


def test_fresh_provenance_bound_ai_result_adds_route_cost_not_safety_stop() -> None:
    navigation = _navigation()

    count = navigation.apply_perception_result(_result())

    assert count == 1
    obstacle = navigation.navigation_state.obstacle_map[0]
    assert obstacle.detection_source == "camera_ai"
    assert obstacle.semantic_class == "person"
    assert obstacle.cost_multiplier == 3.0
    assert navigation.obstacle_detector.has_active_obstacle is False


def test_stale_or_unproven_ai_result_cannot_change_navigation_costs() -> None:
    navigation = _navigation()

    assert navigation.apply_perception_result(_result(age_seconds=3.0)) == 0
    assert navigation.apply_perception_result(_result(digest="e" * 64)) == 0
    assert (
        navigation.apply_perception_result(
            _result().model_copy(update={"model_name": "different-detector"})
        )
        == 0
    )
    assert (
        navigation.apply_perception_result(
            _result().model_copy(update={"source_frame_timestamp": None})
        )
        == 0
    )
    assert navigation.navigation_state.obstacle_map == []


def test_semantic_multiplier_only_increases_detour_geometry() -> None:
    navigation = _navigation()
    center = Position(latitude=40.0, longitude=-75.0)
    navigation.navigation_state.obstacle_map = [
        Obstacle(
            id="ai:person:0",
            position=center,
            size_x=0.2,
            detection_source="camera_ai",
            cost_multiplier=3.0,
        )
    ]
    navigation.coverage_endpoint_clearance_m = 0.1
    navigation.get_operating_area_snapshot = lambda: SimpleNamespace(
        valid=True,
        safe_boundary=[
            Position(latitude=39.999, longitude=-75.001),
            Position(latitude=40.001, longitude=-75.001),
            Position(latitude=40.001, longitude=-74.999),
        ],
        path_is_safe=lambda *_args: True,
    )
    captured: dict[str, object] = {}

    class _Planner:
        @staticmethod
        def find_path(_current, _goal, _boundary, **kwargs):
            captured.update(kwargs)
            return []

    navigation.path_planner = _Planner()

    navigation._plan_obstacle_detour(center, Position(latitude=40.0005, longitude=-75.0))

    polygon = captured["obstacles"][0]
    diagonal = PathPlanner.calculate_distance(polygon[0], polygon[2])
    assert diagonal > 0.8  # 0.2 m object radius inflated by the 3x semantic cost.
