from pathlib import Path

WORKFLOW = Path(__file__).resolve().parents[2] / ".github" / "workflows" / "dep-audit.yml"


def test_dependency_audits_fail_closed_on_known_vulnerabilities() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "|| true" not in workflow
    assert "python -m pip_audit -r requirements.txt" in workflow
    assert "- run: npm audit\n" in workflow


def test_python_audit_export_contains_only_auditable_third_party_requirements() -> None:
    workflow = WORKFLOW.read_text(encoding="utf-8")

    assert "uv export --frozen" in workflow
    assert "--all-extras" in workflow
    assert "--no-emit-project" in workflow
    assert "--no-hashes" in workflow
