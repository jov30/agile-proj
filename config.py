from __future__ import annotations

import os
from pathlib import Path


_BASE_DIR = Path(__file__).resolve().parent


def _bool_env(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


class Config:
    """Application configuration."""

    # Required for Flask session support (cart uses session).
    SECRET_KEY = os.environ.get("FLASK_SECRET_KEY", "dev-secret-key-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"sqlite:///{_BASE_DIR / 'instance' / 'app.db'}",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    ADMIN_NAME = os.environ.get("ADMIN_NAME", "MCQ Admin")
    ADMIN_EMAIL = os.environ.get("ADMIN_EMAIL", "admin@mcq.local")
    ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "Admin@123")

    APP_TIMEZONE = os.environ.get("APP_TIMEZONE", "Australia/Perth")
    PICKUP_OPEN_HOUR = int(os.environ.get("PICKUP_OPEN_HOUR", "10"))
    PICKUP_OPEN_MINUTE = int(os.environ.get("PICKUP_OPEN_MINUTE", "30"))
    PICKUP_CLOSE_HOUR = int(os.environ.get("PICKUP_CLOSE_HOUR", "20"))
    PICKUP_CLOSE_MINUTE = int(os.environ.get("PICKUP_CLOSE_MINUTE", "30"))
    PICKUP_SLOT_MINUTES = int(os.environ.get("PICKUP_SLOT_MINUTES", "30"))
    PICKUP_MIN_LEAD_MINUTES = int(os.environ.get("PICKUP_MIN_LEAD_MINUTES", "45"))
    PICKUP_MAX_DAYS_AHEAD = int(os.environ.get("PICKUP_MAX_DAYS_AHEAD", "7"))
    PICKUP_SLOT_CAPACITY = int(os.environ.get("PICKUP_SLOT_CAPACITY", "4"))
    ENABLE_INSTANT_ORDERING = _bool_env("ENABLE_INSTANT_ORDERING", True)
    INSTANT_ORDERING_COUNTER_LABEL = os.environ.get("INSTANT_ORDERING_COUNTER_LABEL", "Front Pickup Counter")
    INSTANT_ORDERING_BASE_PREP_MINUTES = int(os.environ.get("INSTANT_ORDERING_BASE_PREP_MINUTES", "12"))
    INSTANT_ORDERING_PER_ACTIVE_ORDER_MINUTES = int(
        os.environ.get("INSTANT_ORDERING_PER_ACTIVE_ORDER_MINUTES", "4")
    )
    INSTANT_ORDERING_PER_ITEM_MINUTES = int(os.environ.get("INSTANT_ORDERING_PER_ITEM_MINUTES", "2"))
    INSTANT_ORDERING_MAX_ACTIVE_ORDERS = int(os.environ.get("INSTANT_ORDERING_MAX_ACTIVE_ORDERS", "8"))
    ORDER_SERVICE_FEE_CENTS = int(os.environ.get("ORDER_SERVICE_FEE_CENTS", "150"))
    RESTAURANT_PHONE = os.environ.get("RESTAURANT_PHONE", "08 9248 5623")
