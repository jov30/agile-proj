from __future__ import annotations

from datetime import UTC, datetime

from flask import Flask
from flask_sqlalchemy import SQLAlchemy


db = SQLAlchemy()


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
    payment_status = db.Column(db.String(40), nullable=False, default="Paid")
    payment_reference = db.Column(db.String(40), nullable=False, index=True)
    card_last4 = db.Column(db.String(4), nullable=True)
    order_status = db.Column(db.String(40), nullable=False, default="Confirmed")
    kitchen_notes = db.Column(db.Text, nullable=True)
    special_instructions = db.Column(db.Text, nullable=True)
    subtotal_cents = db.Column(db.Integer, nullable=False)
    service_fee_cents = db.Column(db.Integer, nullable=False, default=0)
    total_cents = db.Column(db.Integer, nullable=False)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=lambda: datetime.now(UTC).replace(tzinfo=None),
        index=True,
    )

    line_items = db.relationship(
        "OrderLineItem",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderLineItem.id",
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


def init_db(app: Flask) -> None:
    db.init_app(app)
    with app.app_context():
        db.create_all()
