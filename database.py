"""SQLite schema creation and optional seed hooks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from extensions import db

if TYPE_CHECKING:
    from flask import Flask


def init_database(app: Flask) -> None:
    """Create all ORM tables under the configured SQLite database if missing."""
    db.create_all()


def seed_database(_app: Flask) -> None:
    """Load baseline fixtures after `init-database`; extend when menu/auth seeds exist."""
    pass
