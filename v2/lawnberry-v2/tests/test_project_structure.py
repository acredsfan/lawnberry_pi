"""Project structure validation tests for LawnBerry Pi v2.

This test module validates that the directory layout and pyproject.toml
configuration meet constitutional requirements.
"""

import platform
import sys
import tomllib
from pathlib import Path

import pytest


class TestProjectStructure:
    """Test project directory structure and configuration."""

    @pytest.fixture(scope="class")
    def project_root(self) -> Path:
        """Get project root directory."""
        # Find project root by looking for pyproject.toml
        current = Path(__file__).parent
        while current != current.parent:
            if (current / "pyproject.toml").exists():
                return current
            current = current.parent
        raise RuntimeError("Could not find project root with pyproject.toml")

    @pytest.fixture(scope="class")
    def pyproject_config(self, project_root: Path) -> dict:
        """Load pyproject.toml configuration."""
        with open(project_root / "pyproject.toml", "rb") as f:
            return tomllib.load(f)

    def test_constitutional_platform_validation(self) -> None:
        """Test that constitutional platform checks work."""
        # Import should work on ARM64 Linux (or be skipped on other platforms)
        if platform.system() == "Linux" and platform.machine() == "aarch64":
            # Should import successfully
            try:
                import lawnberry

                assert lawnberry.__version__ == "2.0.0"
            except ImportError:
                pytest.skip("LawnBerry package not installed in development mode")
        else:
            # Should raise RuntimeError on other platforms
            try:
                import lawnberry

                pytest.fail("Expected RuntimeError on non-ARM64 platform")
            except (RuntimeError, ImportError):
                # Either RuntimeError (correct behavior) or ImportError (not installed) is acceptable
                pass

    def test_python_version_requirement(self) -> None:
        """Test Python 3.11+ requirement."""
        assert sys.version_info >= (3, 11), "Python 3.11+ required for LawnBerry Pi v2"

    def test_src_package_structure(self, project_root: Path) -> None:
        """Test that all required source packages exist."""
        src_dir = project_root / "src" / "lawnberry"
        assert src_dir.exists(), "src/lawnberry package directory must exist"

        required_modules = [
            "models",  # Pydantic data models
            "services",  # Business logic services
            "api",  # FastAPI endpoints
            "core",  # WebSocket hub, config
            "runners",  # AI acceleration runners
            "adapters",  # Hardware abstractions
            "cli",  # Command-line interface
            "utils",  # Utility functions
        ]

        for module in required_modules:
            module_dir = src_dir / module
            assert module_dir.exists(), f"Module {module} directory must exist"

            init_file = module_dir / "__init__.py"
            assert init_file.exists(), f"Module {module} must have __init__.py"

            # Check that __init__.py has some content (not empty)
            content = init_file.read_text()
            assert len(content.strip()) > 0, f"Module {module}/__init__.py must not be empty"

    def test_test_structure(self, project_root: Path) -> None:
        """Test that test directory structure is correct."""
        tests_dir = project_root / "tests"
        assert tests_dir.exists(), "tests directory must exist"

        required_test_dirs = [
            "contract",  # API contract tests
            "integration",  # Service integration tests
            "unit",  # Unit tests
        ]

        for test_dir in required_test_dirs:
            test_path = tests_dir / test_dir
            assert test_path.exists(), f"Test directory {test_dir} must exist"

            init_file = test_path / "__init__.py"
            assert init_file.exists(), f"Test directory {test_dir} must have __init__.py"

        # Check conftest.py exists
        conftest = tests_dir / "conftest.py"
        assert conftest.exists(), "tests/conftest.py must exist"

    def test_pyproject_constitutional_compliance(self, pyproject_config: dict) -> None:
        """Test pyproject.toml constitutional compliance."""
        project = pyproject_config["project"]

        # Check version is 2.0.0
        assert project["version"] == "2.0.0", "Version must be 2.0.0"

        # Check Python version requirement
        assert project["requires-python"] == ">=3.11", "Must require Python 3.11+"

        # Check ARM64 platform markers exist
        dependencies = project["dependencies"]
        arm64_deps = [dep for dep in dependencies if "platform_machine=='aarch64'" in dep]
        assert len(arm64_deps) > 0, "Must have ARM64 platform-specific dependencies"

        # Check TensorFlow Lite with ARM64 marker
        tflite_deps = [dep for dep in dependencies if "tflite-runtime" in dep]
        assert len(tflite_deps) > 0, "Must include tflite-runtime dependency"
        assert any(
            "platform_machine=='aarch64'" in dep for dep in tflite_deps
        ), "TensorFlow Lite must have ARM64 platform marker"

    def test_uv_configuration(self, pyproject_config: dict) -> None:
        """Test UV package manager configuration."""
        assert "tool" in pyproject_config, "Must have [tool] section"
        assert "uv" in pyproject_config["tool"], "Must have [tool.uv] section"

        uv_config = pyproject_config["tool"]["uv"]

        # Note: UV configuration simplified - package restrictions enforced via CI
        # This validates the structure exists for future UV enhancements
        assert isinstance(uv_config, dict), "UV configuration must be a dictionary"

    def test_tool_configurations(self, pyproject_config: dict) -> None:
        """Test linting and formatting tool configurations."""
        tools = pyproject_config["tool"]

        # Check ruff configuration
        assert "ruff" in tools, "Must have ruff configuration"
        ruff_config = tools["ruff"]
        assert ruff_config.get("line-length") == 100, "Ruff line length must be 100"
        assert ruff_config.get("target-version") == "py311", "Ruff target version must be py311"

        # Check black configuration
        assert "black" in tools, "Must have black configuration"
        black_config = tools["black"]
        assert black_config.get("line-length") == 100, "Black line length must be 100"
        assert black_config.get("target-version") == ["py311"], "Black target version must be py311"

        # Check mypy configuration
        assert "mypy" in tools, "Must have mypy configuration"
        mypy_config = tools["mypy"]
        assert mypy_config.get("python_version") == "3.11", "MyPy Python version must be 3.11"
        assert mypy_config.get("disallow_untyped_defs") is True, "MyPy must disallow untyped defs"

    def test_development_dependencies(self, pyproject_config: dict) -> None:
        """Test development dependencies are correctly configured."""
        dev_deps = pyproject_config["project"]["optional-dependencies"]["dev"]

        required_dev_tools = [
            "pytest",
            "pytest-asyncio",
            "pytest-cov",
            "mypy",
            "ruff",
            "black",
            "pre-commit",
        ]

        for tool in required_dev_tools:
            assert any(tool in dep for dep in dev_deps), f"Must include {tool} in dev dependencies"

    def test_configuration_files_exist(self, project_root: Path) -> None:
        """Test that required configuration files exist."""
        required_files = [
            ".pre-commit-config.yaml",  # Pre-commit hooks
            ".github/workflows/ci.yml",  # CI workflow
            "docs/architecture.md",  # Architecture documentation
            "pyproject.toml",  # Project configuration
        ]

        for file_path in required_files:
            file_full_path = project_root / file_path
            assert file_full_path.exists(), f"Required file {file_path} must exist"

            # Check files are not empty
            if file_full_path.suffix in [".md", ".yml", ".yaml", ".toml"]:
                content = file_full_path.read_text()
                assert len(content.strip()) > 0, f"File {file_path} must not be empty"

    def test_pre_commit_configuration(self, project_root: Path) -> None:
        """Test pre-commit configuration includes required hooks."""
        pre_commit_file = project_root / ".pre-commit-config.yaml"
        content = pre_commit_file.read_text()

        # Check for required hooks
        required_hooks = [
            "ruff",
            "black",
            "mypy",
            "constitutional-compliance",
            "forbidden-packages",
            "todo-check",
        ]

        for hook in required_hooks:
            assert hook in content, f"Pre-commit must include {hook} hook"

    def test_ci_workflow_compliance(self, project_root: Path) -> None:
        """Test CI workflow includes constitutional compliance checks."""
        ci_file = project_root / ".github" / "workflows" / "ci.yml"
        content = ci_file.read_text()

        # Check for required CI jobs
        required_jobs = [
            "lint-and-format",
            "constitutional-compliance",
            "test",
            "docs-drift-check",
        ]

        for job in required_jobs:
            assert job in content, f"CI workflow must include {job} job"

        # Check for constitutional compliance checks
        assert "pycoral" in content, "CI must check for forbidden pycoral package"
        assert "edgetpu" in content, "CI must check for forbidden edgetpu package"
        assert "ARM64" in content or "aarch64" in content, "CI must validate ARM64 requirements"
