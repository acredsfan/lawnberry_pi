# Coral TPU Installation Test Framework

## Overview

This directory contains a comprehensive test framework for validating Coral TPU package installation scenarios on Raspberry Pi OS Bookworm with Python 3.11+. The framework is designed to run in various environments, from CI/CD pipelines to physical hardware, with automatic hardware detection and graceful fallback behavior.

## Test Components

### 1. Core Test Framework (`test_coral_installation_framework.py`)

The main test framework covering:

- **Installation Tests**:
  - Core package installation without Coral
  - System package (apt) Coral installation 
  - Pip fallback installation when system packages fail
  - Migration from old pip-based to new system package installations

- **Runtime Tests**:
  - Application startup with various Coral configurations
  - ML inference with Coral acceleration (hardware-dependent)
  - CPU fallback inference (always available)
  - Hardware detection accuracy
  - Graceful degradation when hardware is removed

- **Integration Tests**:
  - Web UI status indicators for different Coral states
  - API endpoints in both Coral and CPU modes
  - Performance monitoring and logging
  - System health checks

### 2. CI/CD Automation (`test_coral_ci_automation.py`)

Automated testing support for different environments:

- **Environment Detection**: Automatically detects GitHub Actions, GitLab CI, Docker, Pi OS Bookworm, or local development
- **Mock Framework**: Comprehensive mocking for hardware, OS environment, and package installation
- **Test Matrix**: Runs tests across multiple scenarios (hardware present/absent, software installed/missing)
- **Configuration Generation**: Generates GitHub Actions workflows and Docker configurations

### 3. Performance Benchmarks (`test_coral_performance_benchmarks.py`)

Performance testing and comparison:

- **Installation Performance**: Timing for package installation operations
- **Inference Performance**: Coral TPU vs CPU inference speed comparison
- **Startup Performance**: Application startup time with different configurations
- **Memory Usage**: Memory consumption patterns
- **Comprehensive Reporting**: Detailed performance reports with statistics

## Usage

### Running Tests Locally

```bash
# Run all Coral tests
pytest tests/coral/ -v

# Run only installation tests
pytest tests/coral/ -v -k "installation"

# Run without hardware-dependent tests
pytest tests/coral/ -v -m "not real_hardware"

# Run with performance benchmarks
pytest tests/coral/ -v -m "performance"

# Run comprehensive test suite
pytest tests/coral/test_coral_installation_framework.py::test_complete_coral_installation_framework -v
```

### Running in CI/CD

```bash
# GitHub Actions / GitLab CI
python tests/coral/test_coral_ci_automation.py

# Generate GitHub Actions workflow
python tests/coral/test_coral_ci_automation.py --generate-github-actions

# Run comprehensive test matrix
python tests/coral/test_coral_ci_automation.py --comprehensive-matrix
```

### Docker Testing

```bash
# Build test container
docker build -t coral-tests -f Dockerfile.coral-tests .

# Run tests in container
docker run --rm coral-tests

# Run with specific scenario
docker run --rm -e MOCK_CORAL_PRESENT=true -e MOCK_PYCORAL_AVAILABLE=true coral-tests
```

## Test Markers

The framework uses pytest markers to categorize tests:

- `integration`: Integration tests
- `coral_installation`: Coral installation-specific tests
- `performance`: Performance benchmarks
- `coral_benchmarks`: Coral-specific performance tests  
- `real_hardware`: Tests requiring actual Coral TPU hardware
- `hardware`: Hardware-dependent tests
- `mock`: Tests using mocked components

## Environment Variables

Control test behavior with environment variables:

```bash
# Mock Coral hardware presence
export MOCK_CORAL_PRESENT=true

# Mock PyCoral software availability  
export MOCK_PYCORAL_AVAILABLE=true

# Mock apt package installation success
export MOCK_APT_SUCCESS=true

# Force specific test environment
export CORAL_TEST_ENV=pi_os_bookworm_mock
```

## Test Scenarios

The framework automatically tests multiple scenarios:

1. **No Coral (Baseline)**: No hardware, no software - CPU fallback only
2. **Software Only**: PyCoral installed but no hardware detected
3. **Hardware Only**: Coral hardware present but software not installed
4. **Full Coral**: Both hardware and software available
5. **Installation Failure**: System package installation fails, triggers pip fallback
6. **Migration**: Upgrading from old pip-based to new system package installation

## Hardware Detection

The framework includes robust hardware detection:

- **USB Detection**: Scans for Coral USB Accelerator (Vendor ID: 18d1, Product ID: 9302)
- **PCIe Detection**: Detects Coral PCIe cards
- **Device Nodes**: Checks for `/dev/apex_*` device nodes
- **Software Detection**: Verifies PyCoral and TensorFlow Lite availability
- **OS Compatibility**: Validates Pi OS Bookworm and Python 3.11+ compatibility

## Performance Benchmarking

Comprehensive performance testing includes:

- **Installation Timing**: Package installation speed
- **Inference Speed**: Coral vs CPU inference comparison
- **Startup Time**: Application initialization performance
- **Memory Usage**: Resource consumption patterns
- **Success Rates**: Reliability metrics across operations

### Sample Performance Report

```
====================================================================
CORAL TPU PERFORMANCE BENCHMARK REPORT
====================================================================

ENVIRONMENT:
  Python Version: 3.11.2
  Platform: aarch64
  Coral TPU Available: ✅ Yes
  System Packages Available: ✅ Yes

INSTALLATION PERFORMANCE:
  Core Packages: 45.2ms avg
  System Packages: 1250.8ms avg
  Hardware Detection: 12.3ms avg

INFERENCE PERFORMANCE:
  CPU Inference: 120.5ms avg
  Coral Inference: 15.2ms avg
  Performance Improvement: 87.4%
  Speedup Factor: 7.9x

STARTUP PERFORMANCE:
  With Coral: 450.2ms avg
  CPU Only: 320.1ms avg

MEMORY USAGE:
  Baseline: 45.2 MB
  After Coral Import: 52.8 MB
  During Inference: 48.1 MB
====================================================================
```

## Success Criteria

The test framework validates:

1. **Coverage**: Tests all major Coral installation and runtime scenarios on Pi OS Bookworm
2. **CI/CD Compatibility**: Runs in automated environments without hardware dependencies
3. **Clear Results**: Provides detailed pass/fail results with error reporting
4. **Performance Metrics**: Includes benchmarks for Coral vs CPU processing when hardware available
5. **Graceful Degradation**: Skips hardware-specific tests when no hardware detected

## Verification Plan

The framework should be tested on:

1. **Physical Pi OS Bookworm hardware** with Coral device
2. **Pi OS Bookworm without Coral** hardware  
3. **CI/CD environments** without hardware
4. **Docker containers** with mocked Pi OS environment

## Integration with Existing Tests

The Coral test framework integrates with the existing test suite:

- Uses existing `conftest.py` fixtures and mock infrastructure
- Follows established pytest conventions and markers
- Leverages existing hardware detection components from `scripts/hardware_detection.py`
- Builds on existing Coral compatibility tests in `tests/integration/test_coral_compatibility.py`

## Troubleshooting

### Common Issues

1. **Tests Skip in CI**: Normal behavior - hardware tests are automatically skipped in CI environments

2. **Import Errors**: Make sure all dependencies are installed:
   ```bash
   pip install -r requirements-dev.txt
   ```

3. **Hardware Not Detected**: Check USB connection and run:
   ```bash
   lsusb | grep 18d1:9302
   ```

4. **Performance Tests Fail**: Performance benchmarks may vary by system load. Run multiple times for consistency.

### Debug Mode

Run tests with detailed logging:

```bash
pytest tests/coral/ -v -s --log-cli-level=DEBUG
```

## Contributing

When adding new Coral-related tests:

1. Use appropriate pytest markers
2. Include both hardware and mocked versions
3. Add performance benchmarks for timing-critical operations
4. Ensure tests work in CI environments without hardware
5. Update this README with new test descriptions

## Related Documentation

- [Coral TPU Compatibility Analysis](../../docs/coral-tpu-compatibility-analysis.md)
- [Installation Guide](../../docs/installation-guide.md)
- [Hardware Detection Script](../../scripts/hardware_detection.py)
- [Coral Migration Guide](../../docs/coral-migration-guide.md)
