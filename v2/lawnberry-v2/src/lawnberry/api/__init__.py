"""FastAPI endpoints and REST API implementation.

This module contains all API endpoints implementing the contracts defined in
contracts/rest-api.md, providing HTTP access to system functionality.
"""

__all__ = ["app"]

from .app import create_app, main

app = create_app()
