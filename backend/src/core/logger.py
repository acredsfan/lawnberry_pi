"""Thin wrapper exposing structured JSON logging with rotation.

Backed by core.observability and privacy filter; this module provides a
stable import path for other modules and tests.
"""
from __future__ import annotations
import logging
from .observability import observability


def get_logger(name: str | None = None) -> logging.Logger:
    return observability.get_logger(name or __name__)
