from pathlib import Path

import yaml

WORKFLOW_DIR = Path(__file__).resolve().parents[2] / ".github" / "workflows"
RUNNER_LABELS = {
    "self-hosted",
    "Linux",
    "X64",
    "self-hosted-linux-lawnberry",
}
FORK_GUARD = (
    "github.event.pull_request.head.repo.full_name == github.repository"
)


def _workflows() -> list[tuple[Path, dict[str, object]]]:
    workflows: list[tuple[Path, dict[str, object]]] = []
    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        parsed = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert isinstance(parsed, dict), f"{path.name} must contain a YAML mapping"
        workflows.append((path, parsed))
    assert workflows, "expected at least one GitHub Actions workflow"
    return workflows


def test_all_jobs_use_the_dedicated_linux_runner_and_reject_fork_prs() -> None:
    for path, workflow in _workflows():
        jobs = workflow.get("jobs")
        assert isinstance(jobs, dict), f"{path.name} must define jobs"
        for job_name, job in jobs.items():
            assert isinstance(job, dict), f"{path.name}:{job_name} must be a mapping"
            assert set(job.get("runs-on", [])) == RUNNER_LABELS, (
                f"{path.name}:{job_name} must use only the dedicated Linux runner"
            )
            assert FORK_GUARD in str(job.get("if", "")), (
                f"{path.name}:{job_name} must skip untrusted fork pull requests"
            )


def test_workflows_do_not_target_hosted_or_non_linux_operating_systems() -> None:
    disallowed = ("ubuntu-latest", "windows-latest", "macos-latest")
    for path, _workflow in _workflows():
        text = path.read_text(encoding="utf-8").lower()
        assert "pull_request_target" not in text
        for target in disallowed:
            assert target not in text, f"{path.name} contains disallowed target {target}"


def test_setup_python_steps_target_python_313() -> None:
    setup_steps = []
    for path, workflow in _workflows():
        jobs = workflow["jobs"]
        for job_name, job in jobs.items():
            for step in job.get("steps", []):
                if str(step.get("uses", "")).startswith("actions/setup-python@"):
                    setup_steps.append((path.name, job_name, step))

    assert setup_steps, "expected at least one actions/setup-python step"
    for path_name, job_name, step in setup_steps:
        assert str(step.get("with", {}).get("python-version")) == "3.13", (
            f"{path_name}:{job_name} must test the supported Python version"
        )
