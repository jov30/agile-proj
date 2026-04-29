from __future__ import annotations

import os


class Config:
    """Application configuration."""

    # Required for Flask session support (cart uses session).
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///app.db")
    SQLALCHEMY_TRACK_MODIFICATIONS = False

