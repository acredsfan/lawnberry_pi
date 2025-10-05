#!/usr/bin/env python3
"""
Initialize LawnBerry database by importing the persistence layer
so migrations run. Prints a confirmation message on success.
"""
from backend.src.core.persistence import persistence  # noqa: F401

print("Database initialized")
