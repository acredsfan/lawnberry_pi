# lawnberry Development Guidelines

Auto-generated from all feature plans. Last updated: 2025-09-28

## Active Technologies
- Python 3.11 (backend), TypeScript + Vue 3 (frontend) + FastAPI, Uvicorn, Pydantic v2, websockets, Vue 3 + Vite, Pinia, Leaflet/Google Maps SDK (001-integrate-hardware-and)
- Python 3.11.x (backend), TypeScript (frontend - existing) + FastAPI, Uvicorn, Pydantic v2, asyncio, python-periphery, lgpio, pyserial, websockets, Vue 3 (existing), Vite, Pinia (002-complete-engineering-plan)
- SQLite for configuration/state, JSON logs with rotation, file-based cache for weather data (002-complete-engineering-plan)

## Project Structure
```
backend/
frontend/
tests/
```

## Commands
cd src [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] pytest [ONLY COMMANDS FOR ACTIVE TECHNOLOGIES][ONLY COMMANDS FOR ACTIVE TECHNOLOGIES] ruff check .

## Code Style
Python 3.11 (backend), TypeScript + Vue 3 (frontend): Follow standard conventions

## Recent Changes
- 002-complete-engineering-plan: Added Python 3.11.x (backend), TypeScript (frontend - existing) + FastAPI, Uvicorn, Pydantic v2, asyncio, python-periphery, lgpio, pyserial, websockets, Vue 3 (existing), Vite, Pinia
- 001-integrate-hardware-and: Added Python 3.11 (backend), TypeScript + Vue 3 (frontend) + FastAPI, Uvicorn, Pydantic v2, websockets, Vue 3 + Vite, Pinia, Leaflet/Google Maps SDK

## Reasoning for problem solving approach
- Think like a developer when solving this issue, when you think you know how to attack the problem, think it through before deploying and make targeted/precise edits to avoid unintentionally causing issues with another part of the program.
- If you are unsure about something, ask for clarification or more information.

## Running CLI Commands
- Always ensure you use timeouts and error handling when running CLI commands from within the codebase to avoid hanging processes or unhandled exceptions.

## When to Ask for Help
- If you encounter unfamiliar technologies or libraries.
- If you are unsure about the architecture or design decisions.

## What to do after completing a task
- Review your code for adherence to style guidelines and best practices.
- Write or update unit tests to cover new functionality or changes.
- Document any new features or changes in the relevant documentation files.
- Restart the backend and frontend servers to ensure all changes are applied.
- Run the full test suite to verify that no existing functionality is broken.

## Tools Available for Agent Use
- Sequential Thinking MCP server
- Server-memory MCP server
- Python 3.11 environment
- TypeScript + Vue 3 environment
- FastAPI framework
- Uvicorn server
- Pydantic v2 for data validation
- Websockets library
- Vue 3 framework
- Vite build tool
- Pinia state management
- Leaflet and Google Maps SDKs for mapping functionalities

## Hardware currently installed
- Raspberry Pi 5 16GB
- Custom RoboHAT MM1
- Cytron MDDRC10 Motor Driver connected to RoboHAT MM1
- Sparkfun ZED-F9P RTK GPS Module connected via USB
- BME280 Environmental Sensor
- 2x VL53L0X Time-of-Flight Distance Sensors
- 2x 12V Worm Gear DC Motors
- 2x Hall Effect Sensors connected to RoboHAT MM1 Encoder Inputs
- BNO085 IMU connected via UART4
- IBT-4 Motor Driver connected to 997 DC Motor for Blade Control
- 12V 30Ah LiFePO4 Battery
- Google Coral USB Accelerator
- Victron SmartSolar MPPT 75/15 Solar Charger connected via victron-ble over BLE
- INA3221 Power Monitor connected via I2C
- RP2040-Zero is the microcontroller on the RoboHAT MM1

## Hardware connections
- GPS Module connected via USB
- BME280 Environmental Sensor connected via I2C
- VL53L0X Distance Sensors connected via I2C
- DC Motors connected to RoboHAT MM1 via the MDDRC10 Motor Driver - RoboHAT sends serial commands to MDDRC10 to control motors
- Hall Effect Sensors connected to RoboHAT MM1 Encoder Inputs
- BNO085 IMU connected via UART4
- IBT-4 Motor Driver connected to GPIO 24 and 25 for PWM control of the Blade Motor
- Google Coral USB Accelerator connected via USB
- RoboHAT MM1 connected to Raspberry Pi via GPIO header and USB to RP2040-Zero

## Additional Notes
- Ensure to follow best practices for both backend and frontend development.
- Regularly update dependencies to maintain security and performance.
