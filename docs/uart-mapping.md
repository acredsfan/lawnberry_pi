# UART Mapping (Pi 4 vs Pi 5)

This document clarifies UART device nodes and header pins used by LawnBerryPi on Raspberry Pi 4/CM4 and Raspberry Pi 5.

## RoboHAT (Motor control)
- Device: `/dev/serial0` (stable alias to primary header UART0)
- Notes: Keep RoboHAT on `serial0` to avoid conflicts with other serial devices.

## GPS (NMEA)
- Typical device: `/dev/ttyACM1` at 115200 baud (CDC-ACM)
- Auto-detect: The GPS plugin scans `/dev/ttyACM*`, `/dev/ttyUSB*`, and `/dev/ttyAMA*` but avoids ports already assigned to RoboHAT.

## IMU (BNO08x over UART @ 3,000,000 baud)
- Default device: `/dev/ttyAMA4`
- Auto-detect: The IMU plugin attempts `/dev/ttyAMA4`, `/dev/ttyAMA1`, and `/dev/ttyAMA0` (in that order) to support different overlay selections without breaking Pi 4.

### Header Pins
- Pi 4/CM4:
  - UART4 appears as `/dev/ttyAMA4` when overlay enabled (pins vary by overlay config; common HATs route to header pins).
- Pi 5:
  - UART4 maps to GPIO12 (TXD4) and GPIO13 (RXD4), physical pins 32 and 33.
  - When enabled via `dtoverlay=uart4`, the device node is `/dev/ttyAMA4`.
  - Some setups may expose UART1 as `/dev/ttyAMA1`; auto-detect supports it, but the canonical default remains `/dev/ttyAMA4`.

### Sample boot overlays
```ini
# Primary UART for RoboHAT
enable_uart=1

# UART4 for IMU (Pi 4 and Pi 5)
dtoverlay=uart4

# Optional additional UART if your wiring requires it
# dtoverlay=uart1
```

### Configuration notes
- `config/hardware.yaml` keeps IMU at `/dev/ttyAMA4` by default for cross-board compatibility.
- Pi 5 wiring: connect IMU to pins 32 (TXD4 / GPIO12) and 33 (RXD4 / GPIO13).
- The IMU plugin now includes `/dev/ttyAMA1` in auto-detect to accommodate alternate overlay choices.
