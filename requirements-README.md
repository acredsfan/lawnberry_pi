# LawnBerryPi Requirements Structure

This project uses a modular requirements structure to handle different installation scenarios and optional dependencies.

## Requirements Files

### `requirements.txt` - Core Dependencies
- **Purpose**: Essential packages required for basic LawnBerryPi functionality
- **Installation**: Always installed during setup
- **Contents**: Web API, computer vision, hardware interfaces, data management
- **Platform**: Includes `sys_platform == "linux"` markers for Pi-specific packages

### `requirements-coral.txt` - Coral TPU Dependencies (Fallback Only)
- **Purpose**: Coral Edge TPU packages for pip-based installation
- **Installation**: Only used as fallback when system packages fail
- **Primary Method**: Use system packages instead: `sudo apt-get install python3-pycoral`
- **Compatibility**: Restricted to Python < 3.11 and non-ARM64 platforms for pip packages

### `requirements-dev.txt` - Development Dependencies
- **Purpose**: Testing, code quality, and development tools
- **Installation**: Only installed in development environments
- **Contents**: pytest, black, mypy, coverage tools, documentation generators

### `requirements-optional.txt` - Optional Hardware Dependencies
- **Purpose**: Additional hardware-specific packages for extended functionality
- **Installation**: Installed only when specific hardware is detected or requested
- **Contents**: Advanced sensors, GPS, audio, additional ML libraries

## Installation Guide

### Standard Installation (Pi OS Bookworm)
```bash
# Install core dependencies
pip install -r requirements.txt

# Install Coral packages via system packages (recommended)
sudo apt-get install python3-pycoral python3-tflite-runtime

# Install optional packages if needed
pip install -r requirements-optional.txt
```

#### Verifying ARM64 Wheels
Some heavy dependencies such as `opencv-python`, `scikit-learn`, and `pandas` require ARM64 wheels on Raspberry Pi.
If a prebuilt wheel is unavailable, compile from source using `pip wheel` with the `--no-binary=:all:` option or
install via the `piwheels.org` index:

```bash
pip install --extra-index-url https://www.piwheels.org/simple opencv-python scikit-learn pandas
```

### Development Installation
```bash
# Install all dependencies for development
pip install -r requirements.txt
pip install -r requirements-dev.txt
pip install -r requirements-optional.txt

# Coral packages via system packages
sudo apt-get install python3-pycoral python3-tflite-runtime
```

### Fallback Installation (Non-Bookworm or Development)
```bash
# Install core dependencies
pip install -r requirements.txt

# Fallback Coral installation (limited compatibility)
pip install -r requirements-coral.txt
```

## Key Design Decisions

1. **Coral Packages Excluded from Core**: Coral TPU packages are NOT in requirements.txt to avoid pip installation conflicts on Pi OS Bookworm with Python 3.11+

2. **System Package Priority**: Primary installation method for Coral is system packages (`python3-pycoral`) as recommended by Google

3. **Platform Markers**: Linux-specific packages use `sys_platform == "linux"` markers for cross-platform compatibility

4. **Graceful Fallbacks**: Application code handles missing Coral packages gracefully with CPU fallbacks

5. **Separate Testing Dependencies**: Development tools separated to keep production installations lean

## Troubleshooting

### Coral Installation Issues
- **Problem**: pip installation fails for pycoral on Python 3.11+
- **Solution**: Use system packages: `sudo apt-get install python3-pycoral`

### TensorFlow Lite Runtime
- **Problem**: `tflite-runtime` wheels are only published for ARM64 Linux and specific Python versions.
- **Solution**: Ensure the target is Raspberry Pi OS 64-bit. On other platforms the package is skipped.

### Missing Hardware Packages
- **Problem**: Hardware-specific imports fail
- **Solution**: Install requirements-optional.txt or specific packages as needed

### Development Environment Setup
- **Problem**: Testing tools not available
- **Solution**: Install requirements-dev.txt for complete development environment
