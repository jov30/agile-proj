from __future__ import annotations

from flask import Blueprint, render_template

from models import FULFILLMENT_TYPES, ORDER_STATUS_SEQUENCE, Order


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")


def _serialize_admin_order(order: Order) -> dict:
    is_instant = order.fulfillment_type == FULFILLMENT_TYPES[0]
    queue_display = f"#{order.queue_number:03d}" if order.queue_number else "#PENDING"
    pickup_label = order.pickup_at.strftime("%A, %d %b %Y at %I:%M %p").lstrip("0")
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
        "next_statuses": [
            status
            for status in ORDER_STATUS_SEQUENCE
            if ORDER_STATUS_SEQUENCE.index(status) > ORDER_STATUS_SEQUENCE.index(order.order_status)
        ],
    }


@admin_bp.get("/orders/queue")
def admin_queue() -> str:
    active_orders = (
        Order.query.filter(Order.order_status != ORDER_STATUS_SEQUENCE[-1])
        .order_by(Order.created_at.asc())
        .all()
    )
    instant_source = [order for order in active_orders if order.fulfillment_type == FULFILLMENT_TYPES[0]]
    instant_source.sort(key=lambda order: order.queue_number or 999999)
    instant_orders = [_serialize_admin_order(order) for order in instant_source]

    scheduled_source = [order for order in active_orders if order.fulfillment_type == FULFILLMENT_TYPES[1]]
    scheduled_source.sort(key=lambda order: order.pickup_at)
    scheduled_orders = [_serialize_admin_order(order) for order in scheduled_source]

    return render_template(
        "admin/orders.html",
        instant_orders=instant_orders,
        scheduled_orders=scheduled_orders,
        order_statuses=list(ORDER_STATUS_SEQUENCE),
    )
