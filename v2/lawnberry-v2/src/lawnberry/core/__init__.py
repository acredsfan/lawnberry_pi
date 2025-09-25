"""Core system components for LawnBerry Pi v2.

This module contains fundamental system components including the WebSocket hub,
configuration management, and system initialization.
"""
from __future__ import annotations

from .websocket_hub import WebSocketHub, websocket_hub

__all__ = ["WebSocketHub", "websocket_hub", "main"]


def main() -> None:
    """Main entry point for LawnBerry core system."""
    # Import here to avoid circular imports
    from lawnberry.api.app import main as api_main
    
    # Start the FastAPI application with WebSocket hub
    api_main()