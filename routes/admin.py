from __future__ import annotations

from flask import Blueprint, render_template, request
from sqlalchemy import func

from models import FULFILLMENT_TYPES, ORDER_STATUS_SEQUENCE, Order, User, db
from routes.auth import admin_required


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _serialize_admin_order(order: Order) -> dict:
    is_instant = order.fulfillment_type == FULFILLMENT_TYPES[0]
    queue_display = f"#{order.queue_number:03d}" if order.queue_number else "#PENDING"
    pickup_label = order.pickup_at.strftime("%A, %d %b %Y at %I:%M %p").lstrip("0")
    current_index = ORDER_STATUS_SEQUENCE.index(order.order_status)
    next_statuses = []
    if current_index < len(ORDER_STATUS_SEQUENCE) - 1:
        next_statuses.append(ORDER_STATUS_SEQUENCE[current_index + 1])
    return {
        "order_number": order.order_number,
        "customer_name": order.customer_name,
        "order_status": order.order_status,
        "fulfillment_type": order.fulfillment_type,
        "is_instant": is_instant,
        "queue_display": queue_display if is_instant else None,
        "counter_label": order.counter_label,
        "pickup_label": pickup_label,
        "total_display": f"${order.total_cents / 100:.2f}",
        "kitchen_notes": order.kitchen_notes,
        "next_statuses": next_statuses,
    }


@admin_bp.get("/orders/queue")
@admin_required
def admin_queue() -> str:
    active_orders = (
        Order.query.filter(Order.order_status != ORDER_STATUS_SEQUENCE[-1])
        .order_by(Order.created_at.asc())
        .all()
    )
    instant_source = [
        order
        for order in active_orders
        if order.fulfillment_type == FULFILLMENT_TYPES[0]
    ]
    instant_source.sort(key=lambda order: order.queue_number or 999999)
    instant_orders = [_serialize_admin_order(order) for order in instant_source]

    scheduled_source = [
        order
        for order in active_orders
        if order.fulfillment_type == FULFILLMENT_TYPES[1]
    ]
    scheduled_source.sort(key=lambda order: order.pickup_at)
    scheduled_orders = [_serialize_admin_order(order) for order in scheduled_source]

    return render_template(
        "admin/orders.html",
        instant_orders=instant_orders,
        scheduled_orders=scheduled_orders,
        order_statuses=list(ORDER_STATUS_SEQUENCE),
    )


@admin_bp.get("/customers")
@admin_required
def admin_customers():
    registered_email_subq = (
        db.session.query(User.email).filter(User.role == "customer").subquery()
    )

    registered_rows = (
        db.session.query(
            User.name,
            User.email,
            User.created_at,
            func.count(Order.id).label("order_count"),
            func.coalesce(func.sum(Order.total_cents), 0).label("total_spent_cents"),
        )
        .outerjoin(Order, User.email == Order.customer_email)
        .filter(User.role == "customer")
        .group_by(User.id)
        .all()
    )

    guest_rows = (
        db.session.query(
            Order.customer_name.label("name"),
            Order.customer_email.label("email"),
            func.count(Order.id).label("order_count"),
            func.sum(Order.total_cents).label("total_spent_cents"),
        )
        .filter(~Order.customer_email.in_(registered_email_subq))
        .group_by(Order.customer_email)
        .all()
    )

    customers = []
    for r in registered_rows:
        customers.append(
            {
                "name": r.name,
                "email": r.email,
                "joined": r.created_at.strftime("%-d %b %Y") if r.created_at else "—",
                "order_count": r.order_count,
                "total_spent": f"${r.total_spent_cents / 100:.2f}",
                "type": "registered",
            }
        )
    for r in guest_rows:
        customers.append(
            {
                "name": r.name,
                "email": r.email,
                "joined": "—",
                "order_count": r.order_count,
                "total_spent": f"${(r.total_spent_cents or 0) / 100:.2f}",
                "type": "guest",
            }
        )

    customers.sort(key=lambda c: c["name"].lower())

    q = request.args.get("q", "").strip()
    if q:
        q_lower = q.lower()
        customers = [
            c
            for c in customers
            if q_lower in c["name"].lower() or q_lower in c["email"].lower()
        ]

    registered_count = sum(1 for c in customers if c["type"] == "registered")
    guest_count = sum(1 for c in customers if c["type"] == "guest")

    return render_template(
        "admin/customers.html",
        customers=customers,
        search_query=q,
        registered_count=registered_count,
        guest_count=guest_count,
    )
