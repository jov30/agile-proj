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
    username = db.Column(db.String(40), nullable=True, unique=True, index=True)
    phone = db.Column(db.String(40), nullable=True)
    date_of_birth = db.Column(db.Date, nullable=True)
    dietary_preferences = db.Column(db.String(255), nullable=True)
    default_pickup_mode = db.Column(db.String(20), nullable=True, default="scheduled")
    notification_email = db.Column(db.Boolean, nullable=False, default=True)
    notification_sms = db.Column(db.Boolean, nullable=False, default=False)
    marketing_opt_in = db.Column(db.Boolean, nullable=False, default=False)
    points_balance = db.Column(db.Integer, nullable=False, default=0)
    total_spend_cents = db.Column(db.Integer, nullable=False, default=0)
    total_orders = db.Column(db.Integer, nullable=False, default=0)
    instant_orders = db.Column(db.Integer, nullable=False, default=0)
    scheduled_orders = db.Column(db.Integer, nullable=False, default=0)
    posts_shared = db.Column(db.Integer, nullable=False, default=0)
    likes_received = db.Column(db.Integer, nullable=False, default=0)
    most_shared_dish = db.Column(db.String(255), nullable=True)
    favorite_combo = db.Column(db.String(255), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)

class Voucher(db.Model):
    __tablename__ = "vouchers"

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(32), nullable=False, unique=True, index=True)
    value_cents = db.Column(db.Integer, nullable=False)
    label = db.Column(db.String(120), nullable=False)
    description = db.Column(db.Text, nullable=True)
    subtitle = db.Column(db.String(180), nullable=True)
    terms = db.Column(db.Text, nullable=True)
    included_items = db.Column(db.Text, nullable=True)
    expires_at = db.Column(db.String(40), nullable=True)
    footer_note = db.Column(db.Text, nullable=True)
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


class CommunityPost(db.Model):
    __tablename__ = "community_posts"

    id = db.Column(db.Integer, primary_key=True)
    author_name = db.Column(db.String(120), nullable=False)
    author_email = db.Column(db.String(255), nullable=True, index=True)
    identity_key = db.Column(db.String(80), nullable=False, index=True)
    post_type = db.Column(db.String(40), nullable=False, default="meal_review", index=True)
    meal_name = db.Column(db.String(255), nullable=False)
    meal_items = db.Column(db.Text, nullable=True)
    caption = db.Column(db.Text, nullable=False)
    tip = db.Column(db.String(255), nullable=True)
    photo_url = db.Column(db.String(500), nullable=True)
    order_number = db.Column(db.String(32), db.ForeignKey("orders.order_number"), nullable=True, index=True)
    order_total_cents = db.Column(db.Integer, nullable=True)
    pickup_type = db.Column(db.String(40), nullable=True)
    spice_level = db.Column(db.String(40), nullable=True)
    portion_note = db.Column(db.String(120), nullable=True)
    drink_pairing = db.Column(db.String(120), nullable=True)
    pickup_timing_note = db.Column(db.String(160), nullable=True)
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

    order = db.relationship("Order")
    reactions = db.relationship(
        "CommunityReaction",
        back_populates="post",
        cascade="all, delete-orphan",
    )
    comments = db.relationship(
        "CommunityComment",
        back_populates="post",
        cascade="all, delete-orphan",
        order_by="CommunityComment.created_at.asc()",
    )
    saves = db.relationship(
        "CommunitySave",
        back_populates="post",
        cascade="all, delete-orphan",
    )


class CommunityReaction(db.Model):
    __tablename__ = "community_reactions"
    __table_args__ = (
        db.UniqueConstraint("post_id", "identity_key", "reaction_type", name="uq_community_reaction_identity_type"),
    )

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("community_posts.id"), nullable=False, index=True)
    identity_key = db.Column(db.String(80), nullable=False, index=True)
    author_name = db.Column(db.String(120), nullable=False)
    reaction_type = db.Column(db.String(40), nullable=False, index=True)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now_naive,
        index=True,
    )

    post = db.relationship("CommunityPost", back_populates="reactions")


class CommunityComment(db.Model):
    __tablename__ = "community_comments"

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("community_posts.id"), nullable=False, index=True)
    identity_key = db.Column(db.String(80), nullable=False, index=True)
    author_name = db.Column(db.String(120), nullable=False)
    focus = db.Column(db.String(40), nullable=False, default="taste", index=True)
    body = db.Column(db.Text, nullable=False)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now_naive,
        index=True,
    )

    post = db.relationship("CommunityPost", back_populates="comments")
    votes = db.relationship(
        "CommunityCommentVote",
        back_populates="comment",
        cascade="all, delete-orphan",
    )


class CommunityCommentVote(db.Model):
    __tablename__ = "community_comment_votes"
    __table_args__ = (
        db.UniqueConstraint("comment_id", "identity_key", "vote_type", name="uq_community_comment_vote_identity_type"),
    )

    id = db.Column(db.Integer, primary_key=True)
    comment_id = db.Column(db.Integer, db.ForeignKey("community_comments.id"), nullable=False, index=True)
    identity_key = db.Column(db.String(80), nullable=False, index=True)
    author_name = db.Column(db.String(120), nullable=False)
    vote_type = db.Column(db.String(40), nullable=False, index=True)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now_naive,
        index=True,
    )

    comment = db.relationship("CommunityComment", back_populates="votes")


class CommunitySave(db.Model):
    __tablename__ = "community_saves"
    __table_args__ = (
        db.UniqueConstraint("post_id", "identity_key", name="uq_community_save_identity"),
    )

    id = db.Column(db.Integer, primary_key=True)
    post_id = db.Column(db.Integer, db.ForeignKey("community_posts.id"), nullable=False, index=True)
    identity_key = db.Column(db.String(80), nullable=False, index=True)
    author_name = db.Column(db.String(120), nullable=False)
    save_type = db.Column(db.String(40), nullable=False, default="saved_for_later", index=True)
    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now_naive,
        index=True,
    )

    post = db.relationship("CommunityPost", back_populates="saves")


class ChecklistSession(db.Model):
    __tablename__ = "checklist_sessions"
    __table_args__ = (
        db.UniqueConstraint(
            "checklist_type",
            "section",
            "session_date",
            name="uq_checklist_session_type_section_date",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    checklist_type = db.Column(db.String(40), nullable=False, index=True)
    section = db.Column(db.String(20), nullable=False, index=True)
    session_date = db.Column(db.Date, nullable=False, index=True)
    day_of_week = db.Column(db.String(20), nullable=True)
    responsible = db.Column(db.String(120), nullable=True)
    submitted_by = db.Column(db.String(120), nullable=True)
    general_done_by = db.Column(db.String(120), nullable=True)
    manager_submit = db.Column(db.String(120), nullable=True)
    general_note = db.Column(db.Text, nullable=True)
    is_late = db.Column(db.Boolean, nullable=False, default=False)
    submitted_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive, index=True)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now_naive,
        onupdate=utc_now_naive,
    )
    verified = db.Column(db.Boolean, nullable=False, default=False, index=True)
    verified_by = db.Column(db.String(120), nullable=True)
    verified_at = db.Column(db.DateTime, nullable=True)
    overall_result = db.Column(db.String(40), nullable=True)
    issues_found = db.Column(db.Text, nullable=True)
    action_responsible = db.Column(db.String(255), nullable=True)
    manager_notes = db.Column(db.Text, nullable=True)

    tasks = db.relationship(
        "ChecklistTask",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChecklistTask.task_order",
    )
    photos = db.relationship(
        "ChecklistPhoto",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="ChecklistPhoto.photo_number",
    )


class ChecklistTask(db.Model):
    __tablename__ = "checklist_tasks"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer,
        db.ForeignKey("checklist_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    task_order = db.Column(db.Integer, nullable=False)
    task_name = db.Column(db.String(500), nullable=False)
    done = db.Column(db.Boolean, nullable=False, default=False)
    note = db.Column(db.String(255), nullable=True)

    session = db.relationship("ChecklistSession", back_populates="tasks")


class ChecklistPhoto(db.Model):
    __tablename__ = "checklist_photos"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer,
        db.ForeignKey("checklist_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filename = db.Column(db.String(255), nullable=False)
    original_name = db.Column(db.String(255), nullable=True)
    photo_number = db.Column(db.Integer, nullable=False, default=0)
    file_size = db.Column(db.Integer, nullable=True)
    uploaded_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    uploaded_by = db.Column(db.String(120), nullable=True)

    session = db.relationship("ChecklistSession", back_populates="photos")


class TemperatureSession(db.Model):
    __tablename__ = "temperature_sessions"
    __table_args__ = (
        db.UniqueConstraint(
            "record_type",
            "session_date",
            name="uq_temperature_session_type_date",
        ),
    )

    id = db.Column(db.Integer, primary_key=True)
    record_type = db.Column(db.String(40), nullable=False, index=True)
    session_date = db.Column(db.Date, nullable=False, index=True)
    recorded_by = db.Column(db.String(120), nullable=True)
    checked_by = db.Column(db.String(120), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    submitted_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive, index=True)
    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=utc_now_naive,
        onupdate=utc_now_naive,
    )

    readings = db.relationship(
        "TemperatureReading",
        back_populates="session",
        cascade="all, delete-orphan",
        order_by="TemperatureReading.food_order",
    )


class TemperatureReading(db.Model):
    __tablename__ = "temperature_readings"

    id = db.Column(db.Integer, primary_key=True)
    session_id = db.Column(
        db.Integer,
        db.ForeignKey("temperature_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    food_order = db.Column(db.Integer, nullable=False)
    food_name = db.Column(db.String(255), nullable=False)
    c1_time = db.Column(db.String(20), nullable=True)
    c1_temp = db.Column(db.Float, nullable=True)
    c2_time = db.Column(db.String(20), nullable=True)
    c2_temp = db.Column(db.Float, nullable=True)
    c3_time = db.Column(db.String(20), nullable=True)
    c3_temp = db.Column(db.Float, nullable=True)
    c4_time = db.Column(db.String(20), nullable=True)
    c4_temp = db.Column(db.Float, nullable=True)
    c5_time = db.Column(db.String(20), nullable=True)
    c5_temp = db.Column(db.Float, nullable=True)
    discarded = db.Column(db.String(2), nullable=False, default="N")

    session = db.relationship("TemperatureSession", back_populates="readings")


class ChecklistAuditLog(db.Model):
    __tablename__ = "checklist_audit_log"

    id = db.Column(db.Integer, primary_key=True)
    action = db.Column(db.String(60), nullable=False, index=True)
    record_type = db.Column(db.String(40), nullable=True)
    record_id = db.Column(db.Integer, nullable=True)
    user_name = db.Column(db.String(120), nullable=True)
    details = db.Column(db.String(500), nullable=True)
    created_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive, index=True)


class IssueReport(db.Model):
    __tablename__ = "issue_reports"

    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(40), nullable=False, index=True)
    title = db.Column(db.String(255), nullable=False)
    description = db.Column(db.Text, nullable=False)
    reported_by = db.Column(db.String(120), nullable=False)
    priority = db.Column(db.String(20), nullable=False, default="normal")
    status = db.Column(db.String(20), nullable=False, default="open", index=True)
    photo = db.Column(db.String(255), nullable=True)
    report_date = db.Column(db.Date, nullable=False, default=lambda: date.today(), index=True)
    submitted_at = db.Column(db.DateTime, nullable=False, default=utc_now_naive)
    admin_notes = db.Column(db.Text, nullable=True)
    resolved_by = db.Column(db.String(120), nullable=True)
    resolved_at = db.Column(db.DateTime, nullable=True)


def _sync_legacy_schema() -> None:
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())

    if "users" in tables:
        user_cols = {col["name"] for col in inspector.get_columns("users")}
        with db.engine.begin() as conn:
            for col, typedef in [
                ("points_balance",   "INTEGER NOT NULL DEFAULT 0"),
                ("total_spend_cents","INTEGER NOT NULL DEFAULT 0"),
                ("total_orders",     "INTEGER NOT NULL DEFAULT 0"),
                ("instant_orders",   "INTEGER NOT NULL DEFAULT 0"),
                ("scheduled_orders", "INTEGER NOT NULL DEFAULT 0"),
                ("posts_shared",     "INTEGER NOT NULL DEFAULT 0"),
                ("likes_received",   "INTEGER NOT NULL DEFAULT 0"),
                ("most_shared_dish", "VARCHAR(255)"),
                ("favorite_combo",   "VARCHAR(255)"),
            ]:
                if col not in user_cols:
                    conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} {typedef}"))

    if "vouchers" in tables:
        voucher_columns = {column["name"] for column in inspector.get_columns("vouchers")}
        with db.engine.begin() as conn:
            for col, typedef in [
                ("description",   "TEXT"),
                ("subtitle",      "VARCHAR(180)"),
                ("terms",         "TEXT"),
                ("included_items","TEXT"),
                ("expires_at",    "VARCHAR(40)"),
                ("footer_note",   "TEXT"),
            ]:
                if col not in voucher_columns:
                    conn.execute(text(f"ALTER TABLE vouchers ADD COLUMN {col} {typedef}"))

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

def _sync_users_schema() -> None:
    inspector = inspect(db.engine)
    tables = set(inspector.get_table_names())
    if "users" not in tables:
        return
    user_cols = {col["name"] for col in inspector.get_columns("users")}
    with db.engine.begin() as conn:
        for col, typedef in [
            ("username",             "VARCHAR(40)"),
            ("phone",                "VARCHAR(40)"),
            ("date_of_birth",        "DATE"),
            ("dietary_preferences",  "VARCHAR(255)"),
            ("default_pickup_mode",  "VARCHAR(20)"),
            ("notification_email",   "BOOLEAN NOT NULL DEFAULT 1"),
            ("notification_sms",     "BOOLEAN NOT NULL DEFAULT 0"),
            ("marketing_opt_in",     "BOOLEAN NOT NULL DEFAULT 0"),
        ]:
            if col not in user_cols:
                conn.execute(text(f"ALTER TABLE users ADD COLUMN {col} {typedef}"))

def init_db(app: Flask) -> None:
    db.init_app(app)
    with app.app_context():
        db.create_all()
        _sync_legacy_schema()
        _sync_users_schema()
        _seed_demo_users()


def _seed_demo_users() -> None:
    demo_users = [
        {
            "name": "Linh Nguyen", "email": "linh@gmail.com", "password": "demo123",
            "points": 270, "spend": 27000, "orders": 9, "instant": 5, "scheduled": 4,
            "posts": 4, "likes": 11,
            "dish": "Pho Bo Dac Biet", "combo": "Pho Bo + Goi Cuon",
        },
        {
            "name": "Minh Tran", "email": "minh@demo.local", "password": "demo123",
            "points": 620, "spend": 62000, "orders": 21, "instant": 8, "scheduled": 13,
            "posts": 9, "likes": 34,
            "dish": "Banh Mi Thit Nuong", "combo": "Banh Mi + Ca Phe Sua Da",
        },
        {
            "name": "Anh Pham", "email": "anh@demo.local", "password": "demo123",
            "points": 85, "spend": 8500, "orders": 3, "instant": 3, "scheduled": 0,
            "posts": 1, "likes": 2,
            "dish": "Com Tam Suon Bi", "combo": "Com Tam + Che Ba Mau",
        },
    ]
    for data in demo_users:
        existing = User.query.filter_by(email=data["email"]).first()
        if not existing:
            db.session.add(User(
                name=data["name"],
                email=data["email"],
                password_hash=generate_password_hash(data["password"]),
                role="customer",
                points_balance=data["points"],
                total_spend_cents=data["spend"],
                total_orders=data["orders"],
                instant_orders=data["instant"],
                scheduled_orders=data["scheduled"],
                posts_shared=data["posts"],
                likes_received=data["likes"],
                most_shared_dish=data["dish"],
                favorite_combo=data["combo"],
            ))
        else:
            if existing.points_balance == 0:
                existing.points_balance = data["points"]
            if existing.total_orders == 0:
                existing.total_orders = data["orders"]
                existing.total_spend_cents = data["spend"]
                existing.instant_orders = data["instant"]
                existing.scheduled_orders = data["scheduled"]
                existing.posts_shared = data["posts"]
                existing.likes_received = data["likes"]
                existing.most_shared_dish = data["dish"]
                existing.favorite_combo = data["combo"]
    db.session.commit()
