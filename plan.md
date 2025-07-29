LawnBerry Pi Autonomous Lawn Mower
==================================

This project is a lawn mower that is controlled by a Raspberry Pi.
It uses various sensors to navigate and mow the lawn autonomously.
It is designed to be efficient, safe, and easy to use.

## Features
- Efficient
- Safe
- Easy to use
- Autonomous navigation using sensors:
    - 2x VL53L0X ToF Sensors (Front Left and Front Right)
    - 1x BNO085 IMU
    - 1x Raspberry Pi Camera
    - 1x SparkFun GPS-RTK-SMA kit (RTK corrections via ODOT's Ohio Real Time Network)
- Environment awareness via 1x BME280
- Movement control via modified RoboHAT:
    - RP2040-Zero on HAT receives signals from Raspberry Pi
    - RP204 sends commands to 1x Cytron MDDRC10 motor driver
    - MDDRC10 drives 2x 12V Worm Gear DC Motors
    - RoboHAT monitors 2x Hall Effect Sensors and Magenets on Wheeels
    - MakerFocus SSD1306 integrated on RoboHAT for displaying status
- Blade control via 997 DC Motor with IBT-4 driver
- Power provided by 30ah LiFePO4 battery
- Charging via 30W Solar Panel and 20A Solar Charge Controller
- Power monitoring via 1x INA3221
- Optional RC control via RoboHAT and External RC Receiver
- Obstacle detection and identification via 1x Raspberry Pi Camera and OpenCV
- Enhanced obstacle detection/identification with Google Coral TPU Accelerator

## Hardware
- Raspberry Pi 4 Model B 16GB RAM
- RoboHAT
- 2x VL53L0X ToF Sensors (Front Left and Front Right)
- 1x BNO085 IMU
- 1x Raspberry Pi Camera
- 1x SparkFun GPS-RTK-SMA kit (RTK corrections via ODOT's Ohio Real Time Network)
- 1x BME280
- 2x Cytron MDDRC10 motor driver
- 2x 12V Worm Gear DC Motors
- 2x Hall Effect Sensors and Magenets on Wheeels
- MakerFocus SSD1306 integrated on RoboHAT for displaying status
- 997 DC Motor with IBT-4 driver
- 30ah LiFePO4 battery
- 30W Solar Panel and 20A Solar Charge Controller
- Optional RC control via RoboHAT and External RC Receiver
- 1x INA3221 for power monitoring
- 1x 12/24V to 5V DC-DC Converter to Power RPi

## Software
- Raspberry Pi OS (64-bit)
- Modular Design using sudo and --break-system-packages when using pip (Pi is dedicated to this project)
- Python 3 for main control logic
- OpenCV for image processing and obstacle detection
- Google Coral TPU for enhanced processing capabilities
- Microservices design for sensor access and data processing
- Ensure i2c, camera, and serial devices are accessed only once and data shared to avoid locking
- Use asyncio for non-blocking I/O operations
- Use of Flask or FastAPI or similar for web interface
- Use of MQTT for communication between components
- Use of Redis or similar for caching and state management
- Keep software highly modular and maintainable to allow for easy updates and maintenance
- Design the system to allow for more sensors and components to be added in the future without major changes to the codebase
- Implement logging and error handling to ensure robustness
- Use of Git for version control
- code.py for RoboHAT designed to process movement, and location to control drive motors and adjust as needed

## Raspberry Pi Pin Mapping
| Physical Pin | Connected To              | Use       |
|--------------|---------------------------|------------|
| 1            | RoboHAT                   | 3.3V       |
| 2            | RoboHAT                   | 5V         |
| 3            | RoboHAT                   | GPIO 2     |
| 4            | RoboHAT                   | 5V         |
| 5            | RoboHAT                   | GPIO 3     |
| 6            | RoboHAT                   | GND        |
| 7            | RoboHAT                   | GPIO 4     |
| 8            | RoboHAT                   | GPIO 14    |
| 9            | RoboHAT                   | GND        |
| 10           | RoboHAT                   | GPIO 15    |
| 11           | RoboHAT                   | GPIO 17    |
| 12           | RoboHAT                   | GPIO 18    |
| 13           | RoboHAT                   | GPIO 27    |
| 14           | RoboHAT                   | GND        |
| 15           | Left VL53L0X Shutdown     | GPIO 22    |
| 16           | Right VL53L0X Shutdown    | GPIO 23    |
| 17           | BNO085 VCC & PS1          | 3.3V       |
| 18           | Blade Controller IN1      | GPIO 24    |
| 19           | OPEN                      | GPIO 10    |
| 20           | OPEN                      | GND        |
| 21           | BNO085 RX                 | RXD 4      |
| 22           | Blade Controller IN2      | GPIO 25    |
| 23           | OPEN                      | GPIO 11    |
| 24           | BNO085 TX                 | TXD 4      |
| 25           | OPEN                      | GND        |
| 26           | OPEN                      | GPIO 7     |
| 27           | OPEN                      | ID SD      |
| 28           | OPEN                      | ID SC      |
| 29           | OPEN                      | GPIO 5     |
| 30           | BNO085 GND                | GND        |
| 31           | Left VL53L0X Interrupt    | GPIO 6     |
| 32           | Right VL53L0X Interrupt   | GPIO 12    |
| 33           | RoboHAT                   | GPIO 13    |
| 34           | RoboHAT                   | GND        |
| 35           | RoboHAT                   | GPIO 19    |
| 36           | RoboHAT                   | GPIO 16    |
| 37           | RoboHAT                   | GPIO 26    |
| 38           | RoboHAT                   | GPIO 20    |
| 39           | RoboHAT                   | GND        |
| 40           | RoboHAT                   | GPIO 21    |

## Component Connections
| Component             | Connection | Port/Address     | Baud Rate |
|-----------------------|------------|------------------|-----------|
| RoboHAT              | USB/Serial | /dev/ttyACM1     | 115200    |
| GPS                  | USB        | /dev/ttyACM0     | 38400     |
| BNO085 IMU           | UART       | /dev/ttyAMA4     | 3000000   |
| Left ToF             | i2c        | 0x29             | n/a       |
| Right ToF            | i2c        | 0x30             | n/a       |
| INA3221              | i2c        | 0x40             | n/a       |
| BME280               | i2c        | 0x76             | n/a       |
| MakerFocus SSD1306   | i2c        | 0x3c             | n/a       |
| Raspberry Pi Camera  | CSI        | /dev/video0      | n/a       |

## UI Features
- Monitor Camera Feed and All Sensor Data
- Monitor Battery Status
- Monitor Location and Mowing Progess via Google Maps JS API and GPS location
- Select mowing patterns: Parallel Lines, Checkerboard, Spiral, Waves, Crosshatch, etc. and render on Google Map
- Set Mowing Schedule (Days and Times)
- Start/Stop Mowing
- Image collection for vision model training
- Yard mapping and visualization
- Yard boundary, robot home location (point to return after mowing), and no-go zone setting via Google Maps JS API
- Settings page: Switch between metric and imperial units and C/F for temperature.  Set obstacle detection tolerances, set autonomous mowing speed, etc.

## Safety Features
- Tilt and slope detection via IMU
- Drop detection via IMU, TOF, and camera
- Sensor Fusion to enable accurate detection of obstacles
- Weather aware scheduling to avoid rain and snow
- Obstacle avoidance via TOF and camera
- Collision detection via IMU
- Geofenced operation via UI yard boundary setting and RTK GPS
- Emergency shutdown if anomolies detected

## Future Additions
- Power management via RP2040 power shutdown when battery is low
- Low battery detection will trigger the mower to find a sunny spot to charge
- Integration with smart home systems (e.g., Home Assistant)
- Mobile web compatibility