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

## **IMPORTANT** Running CLI Commands
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

## Automated code structure documentation sync

To keep our developer docs accurate, the Copilot Agent must automatically update `docs/code_structure_overview.md` whenever structural code changes occur (new/removed files, added/removed functions, or signature changes) in these areas:

- `backend/src/**` (Python services, nav algorithms, CLI, tools)
- `frontend/src/**` (TypeScript/Vue services, composables, utils)
- `scripts/**` and `.specify/scripts/**` (Ops tooling)

Agent workflow requirements:

1) Detect change triggers
	- On any PR or commit that touches the paths above, or when explicitly asked to “regenerate code structure overview,” run the scan.

2) Scan workspace for callable interfaces
	- Python: list module-level functions and public class methods (exclude private names starting with `_` unless necessary for clarity). Capture argument names and defaults from signatures.
	- TypeScript: list exported functions and exported const arrow functions; include argument names and basic types when present.
	- Shell scripts: list defined shell functions when they exist; otherwise mark as CLI entrypoint.

3) Infer subsystem category
	- Use directory and filename hints (e.g., `services/` → backend services; `nav/` → Navigation; `composables/` or `services/` in frontend → Frontend; `scripts/` → Ops/DevOps).

4) Update the document in place
	- Rewrite sections and tables in `docs/code_structure_overview.md` to reflect the current state. Preserve section ordering and headings; replace table rows as needed.
	- Ensure each entry contains: relative path, 1–2 sentence purpose, subsystem category, and callable interfaces with argument signatures.

5) Validate
	- Re-read changed files to confirm the listed signatures match the source.
	- Keep lines <= 120 chars where practical for readability.

6) Commit
	- Include the doc update in the same PR as the code change, or push as a follow-up commit titled: `docs: update code_structure_overview.md (auto)`. 

Template cues the Agent should preserve:
- Group by subsystem with Markdown tables per group.
- Prefer public APIs; mark clearly when listing internal helpers for context.

This directive is persistent. Any code change affecting callable interfaces must be accompanied by an updated `docs/code_structure_overview.md` generated by the Agent.
