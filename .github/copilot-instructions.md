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

## Tools Available for Agent Use


## Additional Notes
- Ensure to follow best practices for both backend and frontend development.
- Regularly update dependencies to maintain security and performance.
