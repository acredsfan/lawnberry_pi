"""Safety CLI commands (T037).

Supports:
- lawnberry safety status
- lawnberry safety clear-estop --force

The module exposes async helper functions for unit testing without a running
HTTP server by accepting an optional FastAPI app instance and using ASGITransport.
"""

from __future__ import annotations

import asyncio
import os
from typing import Any

try:
    import typer  # type: ignore
except Exception:  # pragma: no cover - typer not required for tests
    typer = None  # minimal fallback if CLI not installed in test env


async def _get_client(base_url: str, app=None):
    import httpx
    if app is not None:
        transport = httpx.ASGITransport(app=app)
        return httpx.AsyncClient(transport=transport, base_url=base_url)
    return httpx.AsyncClient(base_url=base_url)


async def safety_status(app=None, base_url: str | None = None) -> dict[str, Any]:
    """Fetch safety status via API. Uses RoboHAT status endpoint for safety_state."""
    base_url = base_url or os.getenv("LAWNBERRY_API_URL", "http://localhost:8000")
    async with await _get_client(base_url, app) as client:
        resp = await client.get("/api/v2/hardware/robohat")
        if resp.status_code >= 400:
            return {"ok": False, "status_code": resp.status_code, "error": resp.text}
        data = resp.json()
        return {
            "ok": True,
            "safety_state": data.get("safety_state", "unknown"),
            "watchdog_heartbeat_ms": data.get("watchdog_heartbeat_ms"),
        }


async def clear_estop(app=None, force: bool = False, base_url: str | None = None) -> dict[str, Any]:
    """Clear E-stop via API with confirmation flag."""
    base_url = base_url or os.getenv("LAWNBERRY_API_URL", "http://localhost:8000")
    async with await _get_client(base_url, app) as client:
        payload = {"confirmation": bool(force)}
        resp = await client.post("/api/v2/control/emergency_clear", json=payload)
        return {"status_code": resp.status_code, "body": resp.json() if resp.text else {}}


def _run(coro):  # pragma: no cover - tiny wrapper for real CLI
    return asyncio.run(coro)


def build_app():  # pragma: no cover - only used when typer available
    app = typer.Typer(help="LawnBerry safety commands")

    @app.command("status")
    def cmd_status(base_url: str = typer.Option("http://localhost:8000", help="API base URL")):
        from backend.src.main import app as fastapi_app
        res = _run(safety_status(app=fastapi_app, base_url=base_url))
        if not res.get("ok"):
            typer.echo(f"ERROR: {res}")
            raise typer.Exit(code=1)
        typer.echo(f"Safety: {res['safety_state']} (watchdog={res['watchdog_heartbeat_ms']})")

    @app.command("clear-estop")
    def cmd_clear_estop(
        force: bool = typer.Option(False, "--force", help="Required to clear E-stop"),
        base_url: str = typer.Option("http://localhost:8000", help="API base URL"),
    ):
        if not force:
            typer.echo("Refusing to clear E-stop without --force")
            raise typer.Exit(code=2)
        from backend.src.main import app as fastapi_app
        res = _run(clear_estop(app=fastapi_app, force=force, base_url=base_url))
        if res["status_code"] >= 400:
            typer.echo(f"ERROR: {res}")
            raise typer.Exit(code=1)
        typer.echo(res["body"].get("status", "UNKNOWN"))

    return app


def main():  # pragma: no cover
    if typer is None:
        print("Typer is not installed; CLI not available.")
        return
    build_app()()


if __name__ == "__main__":  # pragma: no cover
    main()
