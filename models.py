from __future__ import annotations

from datetime import UTC, date, datetime

from flask import Flask
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import inspect, text

from werkzeug.security import generate_password_hash, check_password_hash


db = SQLAlchemy()

ORDER_STATUS_SEQUENCE = (
    "Confirmed",
    "Preparing",
    "Ready for Pickup",
    "Completed",
)
ORDER_NOTIFICATION_CHANNELS = (
    "email",
    "sms",
)
FULFILLMENT_TYPES = (
    "instant",
    "scheduled",
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
    __table_args__ = (
        db.UniqueConstraint("queue_date", "queue_number", name="uq_orders_queue_date_number"),
    )

    id = db.Column(db.Integer, primary_key=True)
    order_number = db.Column(db.String(32), unique=True, nullable=False, index=True)
    confirmation_code = db.Column(db.String(16), nullable=False, index=True)
    customer_name = db.Column(db.String(120), nullable=False)
    customer_email = db.Column(db.String(255), nullable=False, index=True)
    customer_phone = db.Column(db.String(40), nullable=False)
    fulfillment_type = db.Column(
        db.String(20),
        nullable=False,
        default=FULFILLMENT_TYPES[1],
        index=True,
    )
    pickup_at = db.Column(db.DateTime, nullable=False, index=True)
    queue_date = db.Column(db.Date, nullable=True, index=True)
    queue_number = db.Column(db.Integer, nullable=True, index=True)
    quoted_wait_minutes = db.Column(db.Integer, nullable=True)
    counter_label = db.Column(db.String(120), nullable=True)
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
    notifications = db.relationship(
        "OrderNotification",
        back_populates="order",
        cascade="all, delete-orphan",
        order_by="OrderNotification.created_at.desc()",
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


class DailyQueueCounter(db.Model):
    __tablename__ = "daily_queue_counters"

    id = db.Column(db.Integer, primary_key=True)
    counter_date = db.Column(db.Date, nullable=False, unique=True, index=True)
    last_number = db.Column(db.Integer, nullable=False, default=0)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now_naive,
        onupdate=utc_now_naive,
    )

class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(255), nullable=False, unique=True, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(20), nullable=False, default="customer")
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now_naive,
    )


class Voucher(db.Model):
    __tablename__ = "vouchers"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), nullable=False, unique=True, index=True)
    value_cents = db.Column(db.Integer, nullable=False)
    label = db.Column(db.String(120), nullable=False)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now_naive,
        index=True,
    )


class OrderNotification(db.Model):
    __tablename__ = "order_notifications"

    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("orders.id"), nullable=False, index=True)
    event_type = db.Column(db.String(40), nullable=False, default="ready_for_pickup", index=True)
    channel = db.Column(db.String(20), nullable=False, index=True)
    delivery_status = db.Column(db.String(20), nullable=False, default="Sent", index=True)
    message = db.Column(db.Text, nullable=False)
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

    order = db.relationship("Order", back_populates="notifications")


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
        if "fulfillment_type" not in order_columns:
            conn.execute(text("ALTER TABLE orders ADD COLUMN fulfillment_type VARCHAR(20)"))
        if "queue_number" not in order_columns:
            conn.execute(text("ALTER TABLE orders ADD COLUMN queue_number INTEGER"))
        if "queue_date" not in order_columns:
            conn.execute(text("ALTER TABLE orders ADD COLUMN queue_date DATE"))
        if "quoted_wait_minutes" not in order_columns:
            conn.execute(text("ALTER TABLE orders ADD COLUMN quoted_wait_minutes INTEGER"))
        if "counter_label" not in order_columns:
            conn.execute(text("ALTER TABLE orders ADD COLUMN counter_label VARCHAR(120)"))
        conn.execute(text("UPDATE orders SET fulfillment_type = 'scheduled' WHERE fulfillment_type IS NULL"))
        conn.execute(
            text(
                "UPDATE orders SET queue_date = DATE(pickup_at) "
                "WHERE queue_number IS NOT NULL AND queue_date IS NULL"
            )
        )
        duplicate_days = [
            row[0]
            for row in conn.execute(
                text(
                    "SELECT queue_date "
                    "FROM orders "
                    "WHERE queue_date IS NOT NULL AND queue_number IS NOT NULL "
                    "GROUP BY queue_date, queue_number "
                    "HAVING COUNT(*) > 1"
                )
            ).fetchall()
        ]
        for queue_date in sorted(set(duplicate_days)):
            ordered_rows = conn.execute(
                text(
                    "SELECT id "
                    "FROM orders "
                    "WHERE queue_date = :queue_date AND queue_number IS NOT NULL "
                    "ORDER BY created_at ASC, id ASC"
                ),
                {"queue_date": queue_date},
            ).fetchall()
            for index, row in enumerate(ordered_rows, start=1):
                conn.execute(
                    text("UPDATE orders SET queue_number = :queue_number WHERE id = :order_id"),
                    {"queue_number": index, "order_id": row[0]},
                )
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_orders_fulfillment_type ON orders (fulfillment_type)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_orders_queue_number ON orders (queue_number)"))
        conn.execute(text("CREATE INDEX IF NOT EXISTS ix_orders_queue_date ON orders (queue_date)"))
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_orders_queue_date_number "
                "ON orders (queue_date, queue_number)"
            )
        )
        if "daily_queue_counters" in tables:
            queue_days = conn.execute(
                text(
                    "SELECT queue_date, MAX(queue_number) "
                    "FROM orders "
                    "WHERE queue_date IS NOT NULL AND queue_number IS NOT NULL "
                    "GROUP BY queue_date"
                )
            ).fetchall()
            for queue_date, max_number in queue_days:
                conn.execute(
                    text(
                        "INSERT INTO daily_queue_counters (counter_date, last_number, updated_at) "
                        "VALUES (:counter_date, :last_number, CURRENT_TIMESTAMP) "
                        "ON CONFLICT(counter_date) DO UPDATE SET "
                        "last_number = excluded.last_number, updated_at = CURRENT_TIMESTAMP"
                    ),
                    {"counter_date": queue_date, "last_number": max_number or 0},
                )


def init_db(app: Flask) -> None:
    db.init_app(app)
    with app.app_context():
        db.create_all()
        _sync_legacy_schema()
        _seed_demo_users()


def _seed_demo_users() -> None:
    """Insert demo customer accounts if they don't already exist."""
    demo_users = [
        {"name": "Linh Nguyen",   "email": "linh@gmail.com",   "password": "demo123"},
        {"name": "Minh Tran",     "email": "minh@demo.local",   "password": "demo123"},
        {"name": "Anh Pham",      "email": "anh@demo.local",    "password": "demo123"},
    ]
    for data in demo_users:
        if not User.query.filter_by(email=data["email"]).first():
            db.session.add(User(
                name=data["name"],
                email=data["email"],
                password_hash=generate_password_hash(data["password"]),
                role="customer",
            ))
    db.session.commit()
