"""HardwareDriver ABC defining lifecycle methods for all drivers.

Implements T021 requirements: async init/start/stop/health_check with
minimal typing and docstrings. Drivers for sensors, motors, GPS, etc. must
inherit from this base class to ensure consistent behavior and safety.
"""
from __future__ import annotations

import abc
from typing import Any


class HardwareDriver(abc.ABC):
    """Abstract base class for hardware drivers.

    Lifecycle:
    - initialize(): allocate resources, open device handles
    - start(): begin streaming or periodic operations
    - stop(): cease operations and release as needed
    - health_check(): return quick health snapshot
    """

    def __init__(self, config: dict[str, Any] | None = None):
        self.config: dict[str, Any] = config or {}
        self.initialized: bool = False
        self.running: bool = False

    @abc.abstractmethod
    async def initialize(self) -> None:
        """Initialize hardware resources."""

    @abc.abstractmethod
    async def start(self) -> None:
        """Start active operations (if applicable)."""

    @abc.abstractmethod
    async def stop(self) -> None:
        """Stop operations and release transient resources (keep handles if needed)."""

    @abc.abstractmethod
    async def health_check(self) -> dict[str, Any]:
        """Return a health snapshot suitable for /health. Must be non-blocking."""
