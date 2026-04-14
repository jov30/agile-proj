from __future__ import annotations

from datetime import UTC, datetime

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text


db = SQLAlchemy()

ORDER_STATUS_SEQUENCE = (
    "Confirmed",
    "Preparing",
    "Ready for Pickup",
    "Completed",
)
PAYMENT_ATTEMPT_STATUS_SEQUENCE = (
    "Processing",
    "Succeeded",
    "Failed",
)


def utc_now_naive() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Order(db.Model):
    __tablename__ = "orders"

    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(32), unique=True, nullable=False, index=True)
    confirmation_code = db.Column(db.String(16), nullable=False, index=True)
    customer_name = db.Column(db.String(120), nullable=False)
    customer_email = db.Column(db.String(255), nullable=False, index=True)
    customer_phone = db.Column(db.String(40), nullable=False)
    pickup_at = db.Column(db.DateTime, nullable=False, index=True)
    payment_method = db.Column(db.String(40), nullable=False)
    payment_status = db.Column(
        db.String(40),
        nullable=False,
        default=PAYMENT_ATTEMPT_STATUS_SEQUENCE[1],
    )
    payment_reference = db.Column(db.String(40), nullable=False, index=True)
    card_last4 = db.Column(db.String(4), nullable=True)
    order_status = db.Column(
        db.String(40),
        nullable=False,
        default=ORDER_STATUS_SEQUENCE[0],
    )
    kitchen_notes = db.Column(db.Text, nullable=True)
    special_instructions = db.Column(db.Text, nullable=True)
    subtotal_cents = db.Column(db.Integer, nullable=False)
    service_fee_cents = db.Column(db.Integer, nullable=False, default=0)
    total_cents = db.Column(db.Integer, nullable=False)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now_naive,
        index=True,
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now_naive,
        onupdate=utc_now_naive,
        index=True,
    )

    line_items = db.relationship(
        "OrderLineItem",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderLineItem.id",
    )
    payment_attempts = db.relationship(
        "PaymentAttempt",
        back_populates="order",
        cascade="all, delete-orphan",
    )


class OrderLineItem(db.Model):
    __tablename__ = "order_line_items"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    item_id = db.Column(db.String(120), nullable=False)
    item_name = db.Column(db.String(255), nullable=False)
    category_title = db.Column(db.String(120), nullable=False)
    unit_price_cents = db.Column(db.Integer, nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    line_total_cents = db.Column(db.Integer, nullable=False)

    order = db.relationship("Order", back_populates="line_items")


class PaymentAttempt(db.Model):
    __tablename__ = "payment_attempts"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=True, index=True)
    checkout_token = db.Column(db.String(40), nullable=True, index=True)
    attempt_number = db.Column(db.Integer, nullable=False, default=1)
    payment_method = db.Column(db.String(40), nullable=False)
    amount_cents = db.Column(db.Integer, nullable=False)
    status = db.Column(
        db.String(20),
        nullable=False,
        default=PAYMENT_ATTEMPT_STATUS_SEQUENCE[0],
        index=True,
    )
    reference = db.Column(db.String(40), nullable=False, index=True)
    customer_email = db.Column(db.String(255), nullable=False, index=True)
    card_last4 = db.Column(db.String(4), nullable=True)
    failure_code = db.Column(db.String(40), nullable=True)
    failure_message = db.Column(db.String(255), nullable=True)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now_naive,
        index=True,
    )
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now_naive,
        onupdate=utc_now_naive,
        index=True,
    )

    order = db.relationship("Order", back_populates="payment_attempts")


def _sync_legacy_schema() -> None:
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())
    if "orders" not in tables:
        return

    order_columns = {column["name"] for column in inspector.get_columns("orders")}
    with db.engine.begin() as conn:
        if "updated_at" not in order_columns:
            conn.execute(text("ALTER TABLE orders ADD COLUMN updated_at DATETIME"))
            conn.execute(text("UPDATE orders SET updated_at = created_at WHERE updated_at IS NULL"))


def init_db(app: Flask) -> None:
    db.init_app(app)
    with app.app_context():
        db.create_all()
        _sync_legacy_schema()
