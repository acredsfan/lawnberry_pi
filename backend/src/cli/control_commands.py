from __future__ import annotations

import asyncio
import os
from typing import Optional

try:
    import typer  # type: ignore
except Exception:
    typer = None  # type: ignore


async def _get_client(base_url: str, app=None):
    import httpx
    if app is not None:
        transport = httpx.ASGITransport(app=app)
        return httpx.AsyncClient(transport=transport, base_url=base_url)
    return httpx.AsyncClient(base_url=base_url)


async def drive(throttle: float, turn: float, duration_ms: int = 500, app=None, base_url: Optional[str] = None):
    base_url = base_url or os.getenv("LAWNBERRY_API_URL", "http://localhost:8000")
    payload = {
        "session_id": "cli",
        "vector": {"linear": float(throttle), "angular": float(turn)},
        "duration_ms": int(duration_ms),
    }
    async with await _get_client(base_url, app) as client:
        r = await client.post("/api/v2/control/drive", json=payload)
        return {"status_code": r.status_code, "body": r.json() if r.text else {}}


async def blade(active: bool, app=None, base_url: Optional[str] = None):
    base_url = base_url or os.getenv("LAWNBERRY_API_URL", "http://localhost:8000")
    # Legacy-friendly payload to accommodate current endpoint behavior
    payload = {"active": bool(active)}
    async with await _get_client(base_url, app) as client:
        r = await client.post("/api/v2/control/blade", json=payload)
        return {"status_code": r.status_code, "body": r.json() if r.text else {}}


async def emergency_stop(app=None, base_url: Optional[str] = None):
    base_url = base_url or os.getenv("LAWNBERRY_API_URL", "http://localhost:8000")
    async with await _get_client(base_url, app) as client:
        r = await client.post("/api/v2/control/emergency-stop")
        return {"status_code": r.status_code, "body": r.json() if r.text else {}}


def main():  # pragma: no cover - runtime CLI
    if typer is None:
        print("Typer is not installed; CLI not available.")
        return
    app = typer.Typer(help="LawnBerry control commands")

    @app.command()
    def drive_cmd(
        throttle: float = typer.Argument(0.0),
        turn: float = typer.Argument(0.0),
        duration_ms: int = typer.Option(500, help="Command duration in ms"),
        base_url: str = typer.Option("http://localhost:8000", help="API base URL"),
    ):
        from backend.src.main import app as fastapi_app
        res = asyncio.run(drive(throttle, turn, duration_ms, app=fastapi_app, base_url=base_url))
        print(res)

    @app.command()
    def blade_cmd(
        active: bool = typer.Argument(False),
        base_url: str = typer.Option("http://localhost:8000", help="API base URL"),
    ):
        from backend.src.main import app as fastapi_app
        res = asyncio.run(blade(active, app=fastapi_app, base_url=base_url))
        print(res)

    @app.command(name="emergency")
    def emergency_cmd(
        base_url: str = typer.Option("http://localhost:8000", help="API base URL"),
    ):
        from backend.src.main import app as fastapi_app
        res = asyncio.run(emergency_stop(app=fastapi_app, base_url=base_url))
        print(res)

    app()


if __name__ == "__main__":  # pragma: no cover
    main()
