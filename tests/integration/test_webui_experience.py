"""Repository contracts for a shippable, tested primary UI."""

from pathlib import Path


def test_primary_ui_views_are_real_and_placeholder_free() -> None:
    required_views = (
        "DashboardView.vue",
        "ControlView.vue",
        "MapsView.vue",
        "PlanningView.vue",
        "AIView.vue",
        "SettingsView.vue",
    )
    views = Path("frontend/src/views")

    for filename in required_views:
        contents = (views / filename).read_text(encoding="utf-8").lower()
        assert "coming soon" not in contents
        assert "will be implemented later" not in contents


def test_frontend_ci_runs_typecheck_tests_and_build() -> None:
    workflow = Path(".github/workflows/webui-build.yml").read_text(encoding="utf-8")

    typecheck_index = workflow.index("npm run type-check")
    test_index = workflow.index("npm test")
    build_index = workflow.index("npm run build")
    assert typecheck_index < test_index < build_index
