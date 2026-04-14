from __future__ import annotations

import os
from pathlib import Path


_BASE_DIR = Path(__file__).resolve().parent


class Config:
    """Application configuration."""

    # Required for Flask session support (cart uses session).
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{_BASE_DIR / 'instance' / 'app.db'}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    APP_TIMEZONE = os.environ.get("APP_TIMEZONE", "Australia/Perth")
    PICKUP_OPEN_HOUR = int(os.environ.get("PICKUP_OPEN_HOUR", "10"))
    PICKUP_OPEN_MINUTE = int(os.environ.get("PICKUP_OPEN_MINUTE", "30"))
    PICKUP_CLOSE_HOUR = int(os.environ.get("PICKUP_CLOSE_HOUR", "20"))
    PICKUP_CLOSE_MINUTE = int(os.environ.get("PICKUP_CLOSE_MINUTE", "30"))
    PICKUP_SLOT_MINUTES = int(os.environ.get("PICKUP_SLOT_MINUTES", "30"))
    PICKUP_MIN_LEAD_MINUTES = int(os.environ.get("PICKUP_MIN_LEAD_MINUTES", "45"))
    PICKUP_MAX_DAYS_AHEAD = int(os.environ.get("PICKUP_MAX_DAYS_AHEAD", "7"))
    PICKUP_SLOT_CAPACITY = int(os.environ.get("PICKUP_SLOT_CAPACITY", "4"))
    ORDER_SERVICE_FEE_CENTS = int(os.environ.get("ORDER_SERVICE_FEE_CENTS", "150"))
    RESTAURANT_PHONE = os.environ.get("RESTAURANT_PHONE", "08 9248 5623")
