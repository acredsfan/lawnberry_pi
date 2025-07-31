# LawnBerryPi Development Guide

## Build/Test/Lint Commands

```bash
# Run all tests with coverage
python -m pytest tests/ --cov=src --cov-report=html -v

# Run specific test file or method
python -m pytest tests/test_hardware_interface.py::TestI2CManager -v

# Run tests by category (markers)
python -m pytest -m "unit" tests/
python -m pytest -m "integration" tests/
python -m pytest -m "hardware" tests/

# Linting and formatting
black --line-length=100 src/ tests/
isort --profile=black --line-length=100 src/ tests/
flake8 --max-line-length=100 src/ tests/
mypy src/ --ignore-missing-imports
bandit -r src/ --severity-level medium

# Pre-commit hooks (all checks)
pre-commit run --all-files

# Security and code quality
safety check --json
vulture --min-confidence=80 src/
```

## Architecture Overview

- **Hardware Layer**: `src/hardware/` - Plugin-based system with I2C, Serial, GPIO, Camera managers
- **Navigation**: `src/navigation/` - GPS RTK positioning, boundary detection, path planning
- **Safety Systems**: `src/safety/` - Emergency stops, tilt detection, obstacle avoidance  
- **Vision/AI**: `src/vision/` - Computer vision, TensorFlow Lite object detection
- **Power Management**: `src/power_management/` - Battery monitoring, charging control
- **Web API**: `src/web_api/` - FastAPI backend with WebSocket real-time communication
- **Weather Integration**: `src/weather/` - OpenWeather API for scheduling
- **Configuration**: `config/` directory with YAML files for hardware and system settings

## Code Style Guidelines

- **Formatting**: Black with 100 character line length
- **Imports**: isort with black profile, grouped by stdlib/3rd-party/local
- **Type Hints**: Use where helpful, mypy configured with relaxed settings for hardware libraries
- **Docstrings**: Google-style docstrings for public APIs
- **Error Handling**: Custom exceptions in `hardware/exceptions.py`, proper async error propagation
- **Async/Await**: Heavy use of asyncio throughout, especially for hardware interfaces
- **Testing**: Pytest with fixtures, mocking for hardware, separate unit/integration/hardware markers
- **Security**: Bandit security scanning, no hardcoded secrets, proper API key handling
