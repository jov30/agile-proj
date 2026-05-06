from __future__ import annotations

import io
import re
import secrets
import socket
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import qrcode
from flask import Blueprint, Response, current_app, jsonify, redirect, render_template, request, session, url_for
from sqlalchemy.exc import IntegrityError

from menu_catalog import format_aud
from models import (
    ORDER_NOTIFICATION_CHANNELS,
    FULFILLMENT_TYPES,
    ORDER_STATUS_SEQUENCE,
    PAYMENT_ATTEMPT_STATUS_SEQUENCE,
    DailyQueueCounter,
    Order,
    OrderLineItem,
    OrderNotification,
    PaymentAttempt,
    User,
    db,
)
from receipt_pdf import build_receipt_pdf
from routes.api_errors import api_error_response
from routes.auth import admin_required
from routes.cart_api import SESSION_LINES_KEY, _build_cart_payload, _menu, _save_lines


orders_bp = Blueprint("orders", __name__)
SESSION_LAST_ORDER_KEY = "last_order_number"
SESSION_ORDER_HISTORY_KEY = "order_history_numbers"
SESSION_CHECKOUT_TOKEN_KEY = "checkout_payment_token"
SESSION_CHECKOUT_PREFILL_KEY = "checkout_prefill"

FULFILLMENT_LABELS = {
    "instant": "Instant counter pickup",
    "scheduled": "Scheduled pickup",
}

PAYMENT_METHODS = {
    "card": {
        "label": "Secure card gateway",
        "description": "Simulated Visa, Mastercard, or Amex payment with encrypted confirmation.",
        "requires_card": True,
    },
    "apple_pay": {
        "label": "Apple Pay",
        "description": "One-click simulated wallet checkout for mobile pickup orders.",
        "requires_card": False,
    },
    "paypal": {
        "label": "PayPal",
        "description": "Simulated off-site approval before the order is confirmed.",
        "requires_card": False,
    },
}

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CARD_RE = re.compile(r"^\d{13,19}$")
EXPIRY_RE = re.compile(r"^(0[1-9]|1[0-2])\/(\d{2})$")
CVV_RE = re.compile(r"^\d{3,4}$")
PHONE_RE = re.compile(r"\d")


@orders_bp.get("/cart")
def cart() -> str:
    return render_template("menu/cart.html", preferred_fulfillment=_preferred_fulfillment_hint())


def _timezone() -> ZoneInfo:
    return ZoneInfo(current_app.config["APP_TIMEZONE"])


def _now_local() -> datetime:
    return datetime.now(_timezone())


def _to_local_naive(value: datetime) -> datetime:
    return value.astimezone(_timezone()).replace(tzinfo=None)


def _combine_pickup(date_text: str, time_text: str) -> datetime | None:
    if not date_text or not time_text:
        return None
    try:
        pickup_date = datetime.strptime(date_text, "%Y-%m-%d").date()
        pickup_time = datetime.strptime(time_text, "%H:%M").time()
    except ValueError:
        return None
    return datetime.combine(pickup_date, pickup_time, tzinfo=_timezone())


def _pickup_slot_counts() -> dict[str, int]:
    now = _now_local()
    start_naive = datetime.combine(now.date(), time.min)
    end_naive = datetime.combine(
        now.date() + timedelta(days=current_app.config["PICKUP_MAX_DAYS_AHEAD"] + 1),
        time.min,
    )
    counts: dict[str, int] = {}
    active_orders = (
        Order.query.filter(Order.pickup_at >= start_naive, Order.pickup_at < end_naive)
        .filter(Order.fulfillment_type == FULFILLMENT_TYPES[1])
        .filter(Order.order_status != ORDER_STATUS_SEQUENCE[-1])
        .all()
    )
    for order in active_orders:
        slot_key = order.pickup_at.strftime("%Y-%m-%d %H:%M")
        counts[slot_key] = counts.get(slot_key, 0) + 1
    return counts


def _first_available_pickup(windows: list[dict]) -> dict | None:
    for window in windows:
        for slot in window["slots"]:
            if slot["is_available"]:
                return {
                    "date": window["date"],
                    "date_label": window["label"],
                    "time": slot["value"],
                    "time_label": slot["label"],
                }
    return None


def _pickup_windows() -> list[dict]:
    now = _now_local()
    lead = timedelta(minutes=current_app.config["PICKUP_MIN_LEAD_MINUTES"])
    slot_minutes = current_app.config["PICKUP_SLOT_MINUTES"]
    capacity = current_app.config["PICKUP_SLOT_CAPACITY"]
    opening = time(
        hour=current_app.config["PICKUP_OPEN_HOUR"],
        minute=current_app.config["PICKUP_OPEN_MINUTE"],
    )
    closing = time(
        hour=current_app.config["PICKUP_CLOSE_HOUR"],
        minute=current_app.config["PICKUP_CLOSE_MINUTE"],
    )
    slot_counts = _pickup_slot_counts()
    windows: list[dict] = []

    for day_offset in range(current_app.config["PICKUP_MAX_DAYS_AHEAD"] + 1):
        date_value = (now + timedelta(days=day_offset)).date()
        current_slot = datetime.combine(date_value, opening, tzinfo=_timezone())
        closing_slot = datetime.combine(date_value, closing, tzinfo=_timezone())
        slots = []
        while current_slot <= closing_slot:
            slot_key = f"{date_value.isoformat()} {current_slot.strftime('%H:%M')}"
            reserved_count = slot_counts.get(slot_key, 0)
            remaining_capacity = max(0, capacity - reserved_count)
            is_available = True
            reason = ""
            if current_slot < now + lead:
                is_available = False
                reason = "Too soon for kitchen lead time"
            elif remaining_capacity < 1:
                is_available = False
                reason = "Pickup slot is full"
            elif remaining_capacity == 1:
                reason = "1 spot left"
            else:
                reason = f"{remaining_capacity} spots left"

            slots.append(
                {
                    "value": current_slot.strftime("%H:%M"),
                    "label": current_slot.strftime("%I:%M %p").lstrip("0"),
                    "slot_key": slot_key,
                    "is_available": is_available,
                    "availability_reason": reason,
                    "remaining_capacity": remaining_capacity,
                    "reserved_count": reserved_count,
                    "capacity": capacity,
                }
            )
            current_slot += timedelta(minutes=slot_minutes)
        if slots:
            windows.append(
                {
                    "date": date_value.isoformat(),
                    "label": date_value.strftime("%A, %d %b"),
                    "slots": slots,
                    "available_count": sum(1 for slot in slots if slot["is_available"]),
                }
            )
    return windows


def _instant_ordering_enabled() -> bool:
    return bool(current_app.config.get("ENABLE_INSTANT_ORDERING", False))


def _instant_demo_override_enabled() -> bool:
    return bool(current_app.config.get("DEMO_ALLOW_AFTER_HOURS_INSTANT_ORDERING", False))


def _service_hours_for(day_value) -> tuple[datetime, datetime]:
    opening = datetime.combine(
        day_value,
        time(
            hour=current_app.config["PICKUP_OPEN_HOUR"],
            minute=current_app.config["PICKUP_OPEN_MINUTE"],
        ),
        tzinfo=_timezone(),
    )
    closing = datetime.combine(
        day_value,
        time(
            hour=current_app.config["PICKUP_CLOSE_HOUR"],
            minute=current_app.config["PICKUP_CLOSE_MINUTE"],
        ),
        tzinfo=_timezone(),
    )
    return opening, closing


def _current_instant_queue_counter(day_value) -> int:
    counter_value = 0
    counter = DailyQueueCounter.query.filter_by(counter_date=day_value).first()
    if counter is not None:
        counter_value = max(0, int(counter.last_number))

    latest_order = (
        Order.query.filter(
            Order.fulfillment_type == FULFILLMENT_TYPES[0],
            Order.queue_number.isnot(None),
            Order.queue_date == day_value,
        )
        .order_by(Order.queue_number.desc())
        .first()
    )
    latest_value = latest_order.queue_number if latest_order and latest_order.queue_number else 0
    return max(counter_value, latest_value)


def _reserve_next_instant_queue_number(day_value) -> int:
    # Keep queue assignment in a dedicated counter row so increments stay deterministic.
    for _ in range(3):
        counter = DailyQueueCounter.query.filter_by(counter_date=day_value).with_for_update().first()
        if counter is None:
            counter = DailyQueueCounter(counter_date=day_value, last_number=_current_instant_queue_counter(day_value))
            db.session.add(counter)
            try:
                db.session.flush()
            except IntegrityError:
                db.session.rollback()
                continue
        counter.last_number = _current_instant_queue_counter(day_value) + 1
        db.session.flush()
        return counter.last_number
    raise RuntimeError("Could not reserve instant queue number after retries.")


def _minutes_ceil(delta: timedelta) -> int:
    return max(0, int((delta.total_seconds() + 59) // 60))


def _instant_eta_payload(order: Order) -> dict | None:
    fulfillment_type = order.fulfillment_type if order.fulfillment_type in FULFILLMENT_TYPES else FULFILLMENT_TYPES[1]
    if fulfillment_type != FULFILLMENT_TYPES[0]:
        return None

    pickup_local = order.pickup_at.replace(tzinfo=_timezone())
    service_day = order.queue_date or pickup_local.date()
    queue_number = order.queue_number or 0
    current_eta = pickup_local
    backlog_ahead_count = 0
    active_queue_count = 0

    if order.order_status not in {ORDER_STATUS_SEQUENCE[2], ORDER_STATUS_SEQUENCE[3]}:
        active_statuses = ORDER_STATUS_SEQUENCE[:2]
        backlog_ahead_count = (
            Order.query.filter(
                Order.fulfillment_type == FULFILLMENT_TYPES[0],
                Order.queue_date == service_day,
                Order.queue_number.isnot(None),
                Order.queue_number < queue_number,
                Order.order_status.in_(active_statuses),
            )
            .count()
        )
        active_queue_count = (
            Order.query.filter(
                Order.fulfillment_type == FULFILLMENT_TYPES[0],
                Order.queue_date == service_day,
                Order.order_status.in_(active_statuses),
            )
            .count()
        )
        item_units = max(1, sum(line.quantity for line in order.line_items))
        base_wait = max(1, int(current_app.config["INSTANT_ORDERING_BASE_PREP_MINUTES"]))
        per_active_wait = max(0, int(current_app.config["INSTANT_ORDERING_PER_ACTIVE_ORDER_MINUTES"]))
        per_item_wait = max(0, int(current_app.config["INSTANT_ORDERING_PER_ITEM_MINUTES"]))
        remaining_prep_minutes = base_wait + (max(0, item_units - 1) * per_item_wait)
        if order.order_status == ORDER_STATUS_SEQUENCE[1]:
            remaining_prep_minutes = max(4, remaining_prep_minutes // 2)
        live_minutes = remaining_prep_minutes + (backlog_ahead_count * per_active_wait)
        current_eta = max(pickup_local, _now_local() + timedelta(minutes=live_minutes))

    eta_delay_minutes = _minutes_ceil(current_eta - pickup_local)
    is_eta_delayed = eta_delay_minutes > 0
    if order.order_status == ORDER_STATUS_SEQUENCE[2]:
        status_message = "Ready now at the pickup counter."
    elif order.order_status == ORDER_STATUS_SEQUENCE[3]:
        status_message = "Collected from the pickup counter."
    elif is_eta_delayed:
        status_message = f"Kitchen is running about {eta_delay_minutes} minutes behind the original ETA."
    else:
        status_message = "Kitchen is on track for the quoted instant ETA."

    return {
        "current_eta_at": current_eta.strftime("%A, %d %b %Y at %I:%M %p").lstrip("0"),
        "current_eta_time": current_eta.strftime("%I:%M %p").lstrip("0"),
        "eta_delay_minutes": eta_delay_minutes,
        "is_eta_delayed": is_eta_delayed,
        "eta_status_message": status_message,
        "backlog_ahead_count": backlog_ahead_count,
        "active_queue_count": active_queue_count,
    }


def _instant_queue_snapshot(cart: dict | None = None) -> dict:
    now = _now_local()
    opening, closing = _service_hours_for(now.date())

    active_orders = (
        Order.query.filter(
            Order.fulfillment_type == FULFILLMENT_TYPES[0],
            Order.order_status != ORDER_STATUS_SEQUENCE[-1],
            Order.queue_date == now.date(),
        )
        .order_by(Order.created_at.asc())
        .all()
    )
    active_count = len(active_orders)
    kitchen_active_count = sum(1 for order in active_orders if order.order_status in ORDER_STATUS_SEQUENCE[:2])
    max_active = max(1, int(current_app.config["INSTANT_ORDERING_MAX_ACTIVE_ORDERS"]))
    remaining_capacity = max(0, max_active - active_count)
    item_units = sum(line.get("quantity", 0) for line in (cart or {}).get("lines", []))

    base_wait = max(1, int(current_app.config["INSTANT_ORDERING_BASE_PREP_MINUTES"]))
    per_active_wait = max(0, int(current_app.config["INSTANT_ORDERING_PER_ACTIVE_ORDER_MINUTES"]))
    per_item_wait = max(0, int(current_app.config["INSTANT_ORDERING_PER_ITEM_MINUTES"]))
    quoted_wait = base_wait + (kitchen_active_count * per_active_wait) + (max(0, item_units - 1) * per_item_wait)
    estimated_ready = now + timedelta(minutes=quoted_wait)

    next_queue_number = _current_instant_queue_counter(now.date()) + 1

    enabled = _instant_ordering_enabled()
    is_open = opening <= now <= closing
    is_after_hours_demo = enabled and _instant_demo_override_enabled() and not is_open
    kitchen_can_finish = estimated_ready <= closing
    can_accept = enabled and remaining_capacity > 0 and ((is_open and kitchen_can_finish) or is_after_hours_demo)
    opening_label = opening.strftime("%I:%M %p").lstrip("0")
    closing_label = closing.strftime("%I:%M %p").lstrip("0")

    if not enabled:
        status_message = "Instant ordering is currently disabled."
    elif is_after_hours_demo:
        status_message = (
            f"Demo mode keeps instant ordering open outside the normal {opening_label} to {closing_label} window. "
            f"Queue #{next_queue_number} is estimated ready in about {quoted_wait} minutes."
        )
    elif not is_open:
        status_message = "Instant ordering opens during trading hours only."
    elif remaining_capacity < 1:
        status_message = "Instant queue is full right now. Choose a scheduled pickup slot."
    elif not kitchen_can_finish:
        status_message = "Kitchen is close to closing. Choose a scheduled pickup slot."
    else:
        status_message = f"Queue #{next_queue_number} is estimated ready in about {quoted_wait} minutes."

    return {
        "enabled": enabled,
        "counter_label": current_app.config["INSTANT_ORDERING_COUNTER_LABEL"],
        "active_count": active_count,
        "kitchen_active_count": kitchen_active_count,
        "max_active_orders": max_active,
        "remaining_capacity": remaining_capacity,
        "next_queue_number": next_queue_number,
        "quoted_wait_minutes": quoted_wait,
        "estimated_ready_at": estimated_ready,
        "estimated_ready_label": estimated_ready.strftime("%I:%M %p").lstrip("0"),
        "is_open": is_open,
        "is_after_hours_demo": is_after_hours_demo,
        "service_window_label": f"{opening_label} to {closing_label}",
        "can_accept": can_accept,
        "status_message": status_message,
    }


def _default_checkout_form() -> dict[str, str]:
    windows = _pickup_windows()
    first_available = _first_available_pickup(windows)
    default_fulfillment = FULFILLMENT_TYPES[0] if _instant_ordering_enabled() else FULFILLMENT_TYPES[1]
    form = {
        "customer_name": "",
        "customer_email": "",
        "customer_phone": "",
        "fulfillment_type": default_fulfillment,
        "pickup_date": first_available["date"] if first_available else "",
        "pickup_time": first_available["time"] if first_available else "",
        "payment_method": "card",
        "card_name": "",
        "card_number": "",
        "card_expiry": "",
        "card_cvv": "",
        "special_instructions": "",
    }
    prefill = _checkout_prefill()
    for key in (
        "customer_name",
        "customer_email",
        "customer_phone",
        "payment_method",
        "special_instructions",
    ):
        if prefill.get(key):
            form[key] = prefill[key]
    if prefill.get("fulfillment_type") in FULFILLMENT_TYPES:
        form["fulfillment_type"] = prefill["fulfillment_type"]

    slot_lookup = {
        (window["date"], slot["value"]): slot
        for window in windows
        for slot in window["slots"]
    }
    prefill_date = prefill.get("pickup_date")
    prefill_time = prefill.get("pickup_time")
    slot = slot_lookup.get((prefill_date, prefill_time))
    if slot and slot["is_available"]:
        form["pickup_date"] = prefill_date or form["pickup_date"]
        form["pickup_time"] = prefill_time or form["pickup_time"]
    return form


def _payment_options() -> list[dict]:
    return [
        {"key": key, **value}
        for key, value in PAYMENT_METHODS.items()
    ]


def _fulfillment_options() -> list[dict]:
    options = [
        {
            "key": FULFILLMENT_TYPES[0],
            "label": FULFILLMENT_LABELS[FULFILLMENT_TYPES[0]],
            "description": "Pay now, get a live queue number, then collect at the counter when ready.",
            "is_enabled": _instant_ordering_enabled(),
        },
        {
            "key": FULFILLMENT_TYPES[1],
            "label": FULFILLMENT_LABELS[FULFILLMENT_TYPES[1]],
            "description": "Book a pickup date and time slot ahead of time.",
            "is_enabled": True,
        },
    ]
    return options


def _status_timeline(order_status: str, fulfillment_type: str) -> list[dict]:
    try:
        active_index = ORDER_STATUS_SEQUENCE.index(order_status)
    except ValueError:
        active_index = 0

    if fulfillment_type == FULFILLMENT_TYPES[0]:
        labels = {
            "Confirmed": "Order has been accepted and added to the instant pickup queue.",
            "Preparing": "Kitchen is currently preparing your order.",
            "Ready for Pickup": "Order is ready at the pickup counter.",
            "Completed": "Order has been collected from the counter.",
        }
    else:
        labels = {
            "Confirmed": "Order has been accepted and queued for kitchen prep.",
            "Preparing": "Kitchen is actively preparing the dishes for pickup.",
            "Ready for Pickup": "Order is packed and ready for customer collection.",
            "Completed": "Pickup has been collected and the order is closed.",
        }
    return [
        {
            "label": label,
            "description": labels[label],
            "is_active": index <= active_index,
            "is_current": index == active_index,
        }
        for index, label in enumerate(ORDER_STATUS_SEQUENCE)
    ]


def _next_order_status(current_status: str) -> str | None:
    try:
        current_index = ORDER_STATUS_SEQUENCE.index(current_status)
    except ValueError:
        return None
    if current_index >= len(ORDER_STATUS_SEQUENCE) - 1:
        return None
    return ORDER_STATUS_SEQUENCE[current_index + 1]


def _qr_base_url() -> str:
    configured = str(current_app.config.get("PUBLIC_BASE_URL", "")).strip()
    if configured:
        return configured.rstrip("/")

    host = request.host.split(":", 1)[0].strip().lower()
    request_base = request.host_url.rstrip("/")
    if host not in {"127.0.0.1", "localhost", "0.0.0.0"}:
        return request_base

    port = request.host.split(":", 1)[1] if ":" in request.host else ""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("8.8.8.8", 80))
            lan_ip = probe.getsockname()[0]
        if lan_ip and not lan_ip.startswith("127."):
            return f"{request.scheme}://{lan_ip}:{port}" if port else f"{request.scheme}://{lan_ip}"
    except OSError:
        pass
    return request_base


def _qr_destination_url(order_number: str) -> str:
    return f"{_qr_base_url()}{url_for('orders.order_detail', order_number=order_number)}"


def _serialize_payment_attempt(attempt: PaymentAttempt) -> dict:
    local_created = attempt.created_at.replace(tzinfo=ZoneInfo("UTC")).astimezone(_timezone())
    return {
        "reference": attempt.reference,
        "status": attempt.status,
        "payment_method": attempt.payment_method,
        "amount_cents": attempt.amount_cents,
        "amount_display": format_aud(attempt.amount_cents),
        "attempt_number": attempt.attempt_number,
        "card_last4": attempt.card_last4,
        "failure_code": attempt.failure_code,
        "failure_message": attempt.failure_message,
        "created_at": local_created.strftime("%A, %d %b %Y at %I:%M %p").lstrip("0"),
    }


def _notification_message(order: Order, channel: str) -> str:
    pickup_label = order.pickup_at.replace(tzinfo=_timezone()).strftime("%I:%M %p").lstrip("0")
    if order.fulfillment_type == FULFILLMENT_TYPES[0]:
        queue_code = f"#{order.queue_number:03d}" if order.queue_number else "#PENDING"
        base = (
            f"MCQ update: Order {order.order_number} is ready for pickup at "
            f"{order.counter_label or current_app.config['INSTANT_ORDERING_COUNTER_LABEL']}. "
            f"Queue {queue_code}, target {pickup_label}."
        )
    else:
        base = (
            f"MCQ update: Order {order.order_number} is ready for pickup at your scheduled time "
            f"({pickup_label})."
        )
    return f"[{channel.upper()}] {base}"


def _ensure_ready_notifications(order: Order) -> None:
    sent_channels = {
        note.channel
        for note in order.notifications
        if note.event_type == "ready_for_pickup" and note.delivery_status == "Sent"
    }
    for channel in ORDER_NOTIFICATION_CHANNELS:
        if channel in sent_channels:
            continue
        order.notifications.append(
            OrderNotification(
                event_type="ready_for_pickup",
                channel=channel,
                delivery_status="Sent",
                message=_notification_message(order, channel),
            )
        )


def _serialize_notification(notification: OrderNotification) -> dict:
    created_local = notification.created_at.replace(tzinfo=ZoneInfo("UTC")).astimezone(_timezone())
    return {
        "event_type": notification.event_type,
        "event_label": notification.event_type.replace("_", " ").title(),
        "channel": notification.channel,
        "channel_label": notification.channel.upper(),
        "delivery_status": notification.delivery_status,
        "message": notification.message,
        "created_at": created_local.strftime("%A, %d %b %Y at %I:%M %p").lstrip("0"),
        "created_at_iso": created_local.isoformat(),
    }


def _history_numbers() -> list[str]:
    values = session.get(SESSION_ORDER_HISTORY_KEY)
    if isinstance(values, list):
        return [value for value in values if isinstance(value, str)]
    return []


def _remember_order(order_number: str) -> None:
    history = [value for value in _history_numbers() if value != order_number]
    history.insert(0, order_number)
    session[SESSION_ORDER_HISTORY_KEY] = history[:20]
    session[SESSION_LAST_ORDER_KEY] = order_number
    session.modified = True


def _checkout_token() -> str:
    token = session.get(SESSION_CHECKOUT_TOKEN_KEY)
    if not isinstance(token, str) or not token:
        token = secrets.token_hex(8).upper()
        session[SESSION_CHECKOUT_TOKEN_KEY] = token
        session.modified = True
    return token


def _clear_checkout_token() -> None:
    session.pop(SESSION_CHECKOUT_TOKEN_KEY, None)
    session.modified = True


def _latest_checkout_attempt() -> PaymentAttempt | None:
    token = session.get(SESSION_CHECKOUT_TOKEN_KEY)
    if not isinstance(token, str) or not token:
        return None
    return (
        PaymentAttempt.query.filter_by(checkout_token=token)
        .order_by(PaymentAttempt.created_at.desc())
        .first()
    )


def _checkout_prefill() -> dict[str, str]:
    payload = session.get(SESSION_CHECKOUT_PREFILL_KEY)
    if not isinstance(payload, dict):
        return {}
    return {
        key: value
        for key, value in payload.items()
        if isinstance(key, str) and isinstance(value, str)
    }


def _save_checkout_prefill(prefill: dict[str, str]) -> None:
    session[SESSION_CHECKOUT_PREFILL_KEY] = prefill
    session.modified = True


def _clear_checkout_prefill() -> None:
    session.pop(SESSION_CHECKOUT_PREFILL_KEY, None)
    session.modified = True


def _preferred_fulfillment_hint(default: str = FULFILLMENT_TYPES[0]) -> str:
    raw_value = request.args.get("fulfillment", "").strip().lower()
    if raw_value in FULFILLMENT_TYPES:
        session["preferred_fulfillment"] = raw_value
        session.modified = True
        return raw_value

    session_value = session.get("preferred_fulfillment")
    if session_value in FULFILLMENT_TYPES:
        return session_value
    return default


def _apply_checkout_fulfillment_hint(default: str | None = None) -> None:
    hint = _preferred_fulfillment_hint(default or FULFILLMENT_TYPES[0])
    if hint not in FULFILLMENT_TYPES:
        return

    prefill = _checkout_prefill()
    if prefill.get("fulfillment_type") == hint:
        return

    prefill["fulfillment_type"] = hint
    if hint == FULFILLMENT_TYPES[0]:
        prefill.pop("pickup_date", None)
        prefill.pop("pickup_time", None)
    _save_checkout_prefill(prefill)


def _get_checkout_context(
    *,
    form_data: dict[str, str] | None = None,
    errors: list[str] | None = None,
    field_errors: dict[str, str] | None = None,
    entry_step: str = "checkout",
) -> dict:
    cart = _build_cart_payload(_menu())
    resolved_form = form_data or _default_checkout_form()
    if resolved_form.get("fulfillment_type") not in FULFILLMENT_TYPES:
        resolved_form["fulfillment_type"] = FULFILLMENT_TYPES[0] if _instant_ordering_enabled() else FULFILLMENT_TYPES[1]
    subtotal = cart["total_cents"]
    service_fee = current_app.config["ORDER_SERVICE_FEE_CENTS"] if cart["lines"] else 0
    total = subtotal + service_fee
    windows = _pickup_windows()
    selected_date = resolved_form.get("pickup_date")
    selected_slots = []
    for window in windows:
        if window["date"] == selected_date:
            selected_slots = window["slots"]
            break
    if not selected_slots and windows:
        selected_slots = windows[0]["slots"]
    next_available_pickup = _first_available_pickup(windows)
    instant_queue = _instant_queue_snapshot(cart)
    payment_feedback = _latest_checkout_attempt() if cart["lines"] else None

    return {
        "entry_step": entry_step,
        "errors": errors or [],
        "field_errors": field_errors or {},
        "form_data": resolved_form,
        "cart": cart,
        "service_fee_cents": service_fee,
        "service_fee_display": format_aud(service_fee),
        "grand_total_cents": total,
        "grand_total_display": format_aud(total),
        "pickup_windows": windows,
        "selected_slots": selected_slots,
        "fulfillment_options": _fulfillment_options(),
        "payment_options": _payment_options(),
        "pickup_lead_minutes": current_app.config["PICKUP_MIN_LEAD_MINUTES"],
        "pickup_slot_capacity": current_app.config["PICKUP_SLOT_CAPACITY"],
        "next_available_pickup": next_available_pickup,
        "instant_queue": instant_queue,
        "payment_feedback": _serialize_payment_attempt(payment_feedback) if payment_feedback else None,
        "restaurant_phone": current_app.config["RESTAURANT_PHONE"],
    }


def _normalize_form() -> dict[str, str]:
    fields = [
        "customer_name",
        "customer_email",
        "customer_phone",
        "fulfillment_type",
        "pickup_date",
        "pickup_time",
        "payment_method",
        "card_name",
        "card_number",
        "card_expiry",
        "card_cvv",
        "special_instructions",
    ]
    return {field: request.form.get(field, "").strip() for field in fields}


def _push_error(
    errors: list[str],
    field_errors: dict[str, str],
    field_name: str | None,
    message: str,
) -> None:
    if message not in errors:
        errors.append(message)
    if field_name and field_name not in field_errors:
        field_errors[field_name] = message


def _validate_checkout(form_data: dict[str, str], cart: dict) -> tuple[list[str], dict[str, str], dict | None]:
    errors: list[str] = []
    field_errors: dict[str, str] = {}
    if not cart["lines"]:
        _push_error(errors, field_errors, "cart", "Your cart is empty. Add at least one item before checking out.")

    if len(form_data["customer_name"]) < 2:
        _push_error(errors, field_errors, "customer_name", "Please enter the pickup contact name.")
    if not EMAIL_RE.match(form_data["customer_email"]):
        _push_error(errors, field_errors, "customer_email", "Please enter a valid email address.")
    if len(PHONE_RE.findall(form_data["customer_phone"])) < 8:
        _push_error(errors, field_errors, "customer_phone", "Please enter a valid phone number.")

    payment = PAYMENT_METHODS.get(form_data["payment_method"])
    if payment is None:
        _push_error(errors, field_errors, "payment_method", "Choose a valid payment method.")

    if payment and payment["requires_card"]:
        card_number = re.sub(r"\D", "", form_data["card_number"])
        if len(form_data["card_name"]) < 2:
            _push_error(errors, field_errors, "card_name", "Cardholder name is required for card payments.")
        if not CARD_RE.match(card_number):
            _push_error(errors, field_errors, "card_number", "Enter a valid card number for the simulated payment.")
        expiry_match = EXPIRY_RE.match(form_data["card_expiry"])
        if not expiry_match:
            _push_error(errors, field_errors, "card_expiry", "Enter a card expiry in MM/YY format.")
        else:
            month = int(expiry_match.group(1))
            year = 2000 + int(expiry_match.group(2))
            now = _now_local()
            if (year, month) < (now.year, now.month):
                _push_error(errors, field_errors, "card_expiry", "The simulated card expiry cannot be in the past.")
        if not CVV_RE.match(re.sub(r"\D", "", form_data["card_cvv"])):
            _push_error(errors, field_errors, "card_cvv", "Enter a valid 3 or 4 digit security code.")

    fulfillment_type = form_data.get("fulfillment_type") or FULFILLMENT_TYPES[1]
    form_data["fulfillment_type"] = fulfillment_type
    if fulfillment_type not in FULFILLMENT_TYPES:
        _push_error(errors, field_errors, "fulfillment_type", "Choose how you want to receive this order.")
        return errors, field_errors, None

    if fulfillment_type == FULFILLMENT_TYPES[0]:
        instant_queue = _instant_queue_snapshot(cart)
        if not instant_queue["enabled"]:
            _push_error(
                errors,
                field_errors,
                "fulfillment_type",
                "Instant ordering is currently unavailable. Use scheduled pickup instead.",
            )
            return errors, field_errors, None
        if not instant_queue["can_accept"]:
            _push_error(errors, field_errors, "fulfillment_type", instant_queue["status_message"])
            return errors, field_errors, None
        return (
            errors,
            field_errors,
            {
                "fulfillment_type": FULFILLMENT_TYPES[0],
                "pickup_at": instant_queue["estimated_ready_at"],
                "queue_number": instant_queue["next_queue_number"],
                "quoted_wait_minutes": instant_queue["quoted_wait_minutes"],
                "counter_label": instant_queue["counter_label"],
            },
        )

    pickup_at = _combine_pickup(form_data["pickup_date"], form_data["pickup_time"])
    windows = _pickup_windows()
    slot_lookup = {
        (window["date"], slot["value"]): slot
        for window in windows
        for slot in window["slots"]
    }
    if pickup_at is None:
        _push_error(errors, field_errors, "pickup_time", "Choose a valid pickup date and time.")
    else:
        now = _now_local()
        lead = timedelta(minutes=current_app.config["PICKUP_MIN_LEAD_MINUTES"])
        opening = pickup_at.replace(
            hour=current_app.config["PICKUP_OPEN_HOUR"],
            minute=current_app.config["PICKUP_OPEN_MINUTE"],
            second=0,
            microsecond=0,
        )
        closing = pickup_at.replace(
            hour=current_app.config["PICKUP_CLOSE_HOUR"],
            minute=current_app.config["PICKUP_CLOSE_MINUTE"],
            second=0,
            microsecond=0,
        )
        slot = slot_lookup.get((form_data["pickup_date"], form_data["pickup_time"]))
        if pickup_at < now + lead:
            _push_error(
                errors,
                field_errors,
                "pickup_time",
                f"Pickup time must be at least {current_app.config['PICKUP_MIN_LEAD_MINUTES']} minutes from now.",
            )
        if pickup_at < opening or pickup_at > closing:
            _push_error(errors, field_errors, "pickup_time", "Pickup time must be within MCQ trading hours.")
        if pickup_at.date() > (now.date() + timedelta(days=current_app.config["PICKUP_MAX_DAYS_AHEAD"])):
            _push_error(errors, field_errors, "pickup_date", "Pickup time is too far in advance for this schedule.")
        if slot is None:
            _push_error(errors, field_errors, "pickup_time", "Choose one of the available pickup slots.")
        elif not slot["is_available"]:
            next_available = _first_available_pickup(windows)
            message = f"That pickup slot is unavailable: {slot['availability_reason']}."
            if next_available:
                message += f" Next available pickup is {next_available['date_label']} at {next_available['time_label']}."
            _push_error(errors, field_errors, "pickup_time", message)
    if errors or pickup_at is None:
        return errors, field_errors, None
    return (
        errors,
        field_errors,
        {
            "fulfillment_type": FULFILLMENT_TYPES[1],
            "pickup_at": pickup_at,
            "queue_number": None,
            "quoted_wait_minutes": None,
            "counter_label": None,
        },
    )


def _build_order_from_cart(form_data: dict[str, str], fulfillment_plan: dict, cart: dict) -> Order:
    subtotal = cart["total_cents"]
    service_fee = current_app.config["ORDER_SERVICE_FEE_CENTS"]
    total = subtotal + service_fee
    payment_key = form_data["payment_method"]
    card_number = re.sub(r"\D", "", form_data["card_number"])

    fulfillment_type = fulfillment_plan["fulfillment_type"]
    pickup_at = fulfillment_plan["pickup_at"]
    queue_number = fulfillment_plan["queue_number"]
    quoted_wait = fulfillment_plan["quoted_wait_minutes"]
    counter_label = fulfillment_plan["counter_label"]
    queue_date = None
    if fulfillment_type == FULFILLMENT_TYPES[0]:
        service_day = _now_local().date()
        queue_number = _reserve_next_instant_queue_number(service_day)
        instant_snapshot = _instant_queue_snapshot(cart)
        quoted_wait = instant_snapshot["quoted_wait_minutes"]
        pickup_at = instant_snapshot["estimated_ready_at"]
        counter_label = instant_snapshot["counter_label"]
        queue_date = service_day
        kitchen_notes = (
            f"Instant queue #{queue_number} at {counter_label}. "
            f"Target ready around {instant_snapshot['estimated_ready_label']}."
        )
    else:
        kitchen_notes = "Scheduled pickup order queued for the kitchen."

    order = Order(
        order_number=f"MCQ-{_now_local().strftime('%Y%m%d')}-{secrets.token_hex(2).upper()}",
        confirmation_code=f"PK-{secrets.token_hex(2).upper()}",
        customer_name=form_data["customer_name"],
        customer_email=form_data["customer_email"],
        customer_phone=form_data["customer_phone"],
        fulfillment_type=fulfillment_type,
        pickup_at=pickup_at.astimezone(_timezone()).replace(tzinfo=None),
        queue_date=queue_date,
        queue_number=queue_number,
        quoted_wait_minutes=quoted_wait,
        counter_label=counter_label,
        payment_method=PAYMENT_METHODS[payment_key]["label"],
        payment_status=PAYMENT_ATTEMPT_STATUS_SEQUENCE[1],
        payment_reference=f"SIM-{secrets.token_hex(4).upper()}",
        card_last4=card_number[-4:] if card_number else None,
        order_status=ORDER_STATUS_SEQUENCE[0],
        kitchen_notes=kitchen_notes,
        special_instructions=form_data["special_instructions"] or None,
        subtotal_cents=subtotal,
        service_fee_cents=service_fee,
        total_cents=total,
    )

    for line in cart["lines"]:
        order.line_items.append(
            OrderLineItem(
                item_id=line["item_id"],
                item_name=line["name"],
                category_title=line["category_title"],
                unit_price_cents=line["unit_cents"],
                quantity=line["quantity"],
                line_total_cents=line["line_cents"],
            )
        )

    db.session.add(order)
    return order


def _is_queue_number_conflict(error: IntegrityError) -> bool:
    message = str(getattr(error, "orig", error)).lower()
    return "orders.queue_date, orders.queue_number" in message or "uq_orders_queue_date_number" in message


def _create_order_with_retries(
    form_data: dict[str, str],
    fulfillment_plan: dict,
    cart: dict,
    payment_attempt: PaymentAttempt,
) -> Order:
    checkout_token = session.get(SESSION_CHECKOUT_TOKEN_KEY)
    payment_attempt_id = payment_attempt.id

    for attempt_number in range(3):
        try:
            payment_record = db.session.get(PaymentAttempt, payment_attempt_id)
            if payment_record is None:
                raise RuntimeError("Payment attempt record could not be reloaded.")

            order = _build_order_from_cart(form_data, fulfillment_plan, cart)
            order.payment_reference = payment_record.reference
            order.payment_status = payment_record.status
            if isinstance(checkout_token, str) and checkout_token:
                attempts = PaymentAttempt.query.filter_by(checkout_token=checkout_token).all()
                for attempt in attempts:
                    attempt.order = order
                    attempt.checkout_token = None
            else:
                payment_record.order = order
                payment_record.checkout_token = None
            db.session.flush()
            return order
        except IntegrityError as error:
            db.session.rollback()
            is_retryable = (
                fulfillment_plan["fulfillment_type"] == FULFILLMENT_TYPES[0]
                and _is_queue_number_conflict(error)
                and attempt_number < 2
            )
            if not is_retryable:
                raise

    raise RuntimeError("Could not store the instant order after retrying queue assignment.")

def _update_user_order_stats(order: Order) -> None:
    """Increment stored order stats on the User row when an order is placed."""
    db_user = User.query.filter_by(email=order.customer_email.lower()).first()
    if not db_user:
        return
    earned_points = order.total_cents // 100
    db_user.points_balance += earned_points
    db_user.total_spend_cents += order.total_cents
    db_user.total_orders += 1
    if order.fulfillment_type == FULFILLMENT_TYPES[0]:
        db_user.instant_orders += 1
    else:
        db_user.scheduled_orders += 1

def _finalize_successful_order(order: Order) -> None:
    _update_user_order_stats(order)
    db.session.commit()
    _save_lines([])
    session[SESSION_LINES_KEY] = []
    _remember_order(order.order_number)
    _clear_checkout_token()
    _clear_checkout_prefill()


def _payment_failure_for(form_data: dict[str, str], card_last4: str | None) -> tuple[str, str] | None:
    method = form_data["payment_method"]
    email = form_data["customer_email"].lower()
    phone_digits = re.sub(r"\D", "", form_data["customer_phone"])

    if method == "card" and card_last4 == "0002":
        return (
            "card_declined",
            "The test card ending in 0002 is configured to decline. Retry with another card or payment method.",
        )
    if method == "card" and card_last4 == "9995":
        return (
            "authentication_failed",
            "The simulated bank could not authenticate this card. Retry the payment or choose a different method.",
        )
    if method == "paypal" and "decline" in email:
        return (
            "paypal_denied",
            "The PayPal simulation declined approval for this checkout. Update the email or retry payment.",
        )
    if method == "apple_pay" and phone_digits.endswith("0000"):
        return (
            "device_auth_failed",
            "Apple Pay simulation failed device authentication. Retry or switch payment method.",
        )
    return None


def _run_payment_attempt(form_data: dict[str, str], total_cents: int) -> tuple[PaymentAttempt, str | None]:
    payment_key = form_data["payment_method"]
    card_number = re.sub(r"\D", "", form_data["card_number"])
    attempt = PaymentAttempt(
        checkout_token=_checkout_token(),
        attempt_number=(
            PaymentAttempt.query.filter_by(checkout_token=session[SESSION_CHECKOUT_TOKEN_KEY]).count() + 1
        ),
        payment_method=PAYMENT_METHODS[payment_key]["label"],
        amount_cents=total_cents,
        status=PAYMENT_ATTEMPT_STATUS_SEQUENCE[0],
        reference=f"SIMPAY-{secrets.token_hex(4).upper()}",
        customer_email=form_data["customer_email"],
        card_last4=card_number[-4:] if card_number else None,
    )
    db.session.add(attempt)
    db.session.commit()

    failure = _payment_failure_for(form_data, attempt.card_last4)
    if failure:
        failure_code, failure_message = failure
        attempt.status = PAYMENT_ATTEMPT_STATUS_SEQUENCE[2]
        attempt.failure_code = failure_code
        attempt.failure_message = failure_message
        db.session.commit()
        return attempt, failure_message

    attempt.status = PAYMENT_ATTEMPT_STATUS_SEQUENCE[1]
    attempt.failure_code = None
    attempt.failure_message = None
    db.session.commit()
    return attempt, None


def _serialize_order(order: Order) -> dict:
    created_local = order.created_at.replace(tzinfo=ZoneInfo("UTC")).astimezone(_timezone())
    updated_local = order.updated_at.replace(tzinfo=ZoneInfo("UTC")).astimezone(_timezone())
    pickup_local = order.pickup_at.replace(tzinfo=_timezone())
    fulfillment_type = order.fulfillment_type if order.fulfillment_type in FULFILLMENT_TYPES else FULFILLMENT_TYPES[1]
    is_instant = fulfillment_type == FULFILLMENT_TYPES[0]
    queue_display = f"#{order.queue_number:03d}" if order.queue_number else ("#PENDING" if is_instant else None)
    quoted_wait = order.quoted_wait_minutes if order.quoted_wait_minutes is not None else None
    live_eta = _instant_eta_payload(order)
    if is_instant:
        if live_eta and live_eta["is_eta_delayed"]:
            fulfillment_summary = (
                f"Queue {queue_display} at {order.counter_label or current_app.config['INSTANT_ORDERING_COUNTER_LABEL']} "
                f"· delayed ETA {live_eta['current_eta_time']} ({live_eta['eta_delay_minutes']} min later)"
            )
        else:
            fulfillment_summary = (
                f"Queue {queue_display} at {order.counter_label or current_app.config['INSTANT_ORDERING_COUNTER_LABEL']} "
                f"· ready around {pickup_local.strftime('%I:%M %p').lstrip('0')}"
            )
    else:
        fulfillment_summary = f"Scheduled pickup on {pickup_local.strftime('%A, %d %b')} at {pickup_local.strftime('%I:%M %p').lstrip('0')}"
    attempts = sorted(order.payment_attempts, key=lambda attempt: attempt.created_at, reverse=True)
    notifications = sorted(order.notifications, key=lambda note: note.created_at, reverse=True)
    serialized_notifications = [_serialize_notification(note) for note in notifications]
    ready_notifications = [note for note in serialized_notifications if note["event_type"] == "ready_for_pickup"]
    return {
        "order_number": order.order_number,
        "confirmation_code": order.confirmation_code,
        "customer_name": order.customer_name,
        "customer_email": order.customer_email,
        "customer_phone": order.customer_phone,
        "created_at": created_local.strftime("%A, %d %b %Y at %I:%M %p").lstrip("0"),
        "created_at_iso": created_local.isoformat(),
        "created_relative_date": created_local.strftime("%d %b %Y"),
        "updated_at": updated_local.strftime("%A, %d %b %Y at %I:%M %p").lstrip("0"),
        "updated_at_iso": updated_local.isoformat(),
        "fulfillment_type": fulfillment_type,
        "fulfillment_label": FULFILLMENT_LABELS[fulfillment_type],
        "is_instant": is_instant,
        "counter_label": order.counter_label or current_app.config["INSTANT_ORDERING_COUNTER_LABEL"],
        "queue_number": order.queue_number,
        "queue_display": queue_display,
        "queue_date": (order.queue_date or pickup_local.date()).isoformat() if is_instant else None,
        "quoted_wait_minutes": quoted_wait,
        "quoted_wait_display": f"{quoted_wait} minutes" if quoted_wait is not None else None,
        "fulfillment_summary": fulfillment_summary,
        "pickup_at": pickup_local.strftime("%A, %d %b %Y at %I:%M %p").lstrip("0"),
        "pickup_date_iso": pickup_local.strftime("%Y-%m-%d"),
        "pickup_day": pickup_local.strftime("%A, %d %b"),
        "pickup_time": pickup_local.strftime("%I:%M %p").lstrip("0"),
        "payment_method": order.payment_method,
        "payment_status": order.payment_status,
        "payment_reference": order.payment_reference,
        "card_last4": order.card_last4,
        "order_status": order.order_status,
        "kitchen_notes": order.kitchen_notes,
        "special_instructions": order.special_instructions,
        "subtotal_cents": order.subtotal_cents,
        "service_fee_cents": order.service_fee_cents,
        "total_cents": order.total_cents,
        "subtotal_display": format_aud(order.subtotal_cents),
        "service_fee_display": format_aud(order.service_fee_cents),
        "total_display": format_aud(order.total_cents),
        "available_statuses": list(ORDER_STATUS_SEQUENCE),
        "status_timeline": _status_timeline(order.order_status, fulfillment_type),
        "payment_attempt_count": len(attempts),
        "latest_payment_attempt": _serialize_payment_attempt(attempts[0]) if attempts else None,
        "payment_attempts": [_serialize_payment_attempt(attempt) for attempt in attempts],
        "current_eta_at": live_eta["current_eta_at"] if live_eta else None,
        "current_eta_time": live_eta["current_eta_time"] if live_eta else None,
        "eta_delay_minutes": live_eta["eta_delay_minutes"] if live_eta else 0,
        "is_eta_delayed": live_eta["is_eta_delayed"] if live_eta else False,
        "eta_status_message": live_eta["eta_status_message"] if live_eta else None,
        "queue_backlog_count": live_eta["backlog_ahead_count"] if live_eta else 0,
        "active_queue_count": live_eta["active_queue_count"] if live_eta else 0,
        "notification_count": len(serialized_notifications),
        "notifications": serialized_notifications,
        "ready_notification_count": len(ready_notifications),
        "latest_ready_notification": ready_notifications[0] if ready_notifications else None,
        "lines": [
            {
                "item_id": line.item_id,
                "name": line.item_name,
                "category": line.category_title,
                "quantity": line.quantity,
                "unit_price_display": format_aud(line.unit_price_cents),
                "line_total_display": format_aud(line.line_total_cents),
            }
            for line in order.line_items
        ],
    }


def _parse_date_filter(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except ValueError:
        return None


def _filter_serialized_orders(orders: list[dict]) -> tuple[list[dict], dict[str, str]]:
    status = request.args.get("status", "").strip()
    date_from = request.args.get("date_from", "").strip()
    date_to = request.args.get("date_to", "").strip()
    from_value = _parse_date_filter(date_from)
    to_value = _parse_date_filter(date_to)

    filtered = orders
    if status in ORDER_STATUS_SEQUENCE:
        filtered = [order for order in filtered if order["order_status"] == status]
    if from_value:
        filtered = [
            order
            for order in filtered
            if datetime.strptime(order["pickup_date_iso"], "%Y-%m-%d").date() >= from_value
        ]
    if to_value:
        filtered = [
            order
            for order in filtered
            if datetime.strptime(order["pickup_date_iso"], "%Y-%m-%d").date() <= to_value
        ]

    return filtered, {"status": status, "date_from": date_from, "date_to": date_to}


def _ready_notification_banners(orders: list[dict]) -> list[dict]:
    banners: list[dict] = []
    for order in orders:
        latest = order.get("latest_ready_notification")
        if not latest:
            continue
        if order.get("order_status") not in {ORDER_STATUS_SEQUENCE[2], ORDER_STATUS_SEQUENCE[3]}:
            continue
        banners.append(
            {
                "order_number": order["order_number"],
                "fulfillment_label": order["fulfillment_label"],
                "queue_display": order.get("queue_display"),
                "counter_label": order.get("counter_label"),
                "pickup_time": order["pickup_time"],
                "message": latest["message"],
                "notified_at": latest["created_at"],
            }
        )
    return banners[:4]


def public_ordering_snapshot() -> dict:
    windows = _pickup_windows()
    next_available = _first_available_pickup(windows)
    instant_queue = _instant_queue_snapshot()
    ready_count = Order.query.filter(Order.order_status == ORDER_STATUS_SEQUENCE[2]).count()
    return {
        "instant_queue": instant_queue,
        "next_available_pickup": next_available,
        "ready_count": ready_count,
        "scheduled_capacity": current_app.config["PICKUP_SLOT_CAPACITY"],
    }


def _session_orders() -> list[Order]:
    order_numbers = _history_numbers()
    if not order_numbers:
        return []
    orders = Order.query.filter(Order.order_number.in_(order_numbers)).order_by(Order.created_at.desc()).all()
    order_lookup = {order.order_number: order for order in orders}
    return [order_lookup[number] for number in order_numbers if number in order_lookup]


def _reorder_prefill(order: Order) -> dict[str, str]:
    windows = _pickup_windows()
    fulfillment_type = order.fulfillment_type if order.fulfillment_type in FULFILLMENT_TYPES else FULFILLMENT_TYPES[1]
    original_date = order.pickup_at.strftime("%Y-%m-%d")
    original_time = order.pickup_at.strftime("%H:%M")
    slot_lookup = {
        (window["date"], slot["value"]): slot
        for window in windows
        for slot in window["slots"]
    }
    slot = slot_lookup.get((original_date, original_time))
    if slot and slot["is_available"]:
        pickup_date = original_date
        pickup_time = original_time
    else:
        fallback = _first_available_pickup(windows)
        pickup_date = fallback["date"] if fallback else ""
        pickup_time = fallback["time"] if fallback else ""

    prefill = {
        "customer_name": order.customer_name,
        "customer_email": order.customer_email,
        "customer_phone": order.customer_phone,
        "fulfillment_type": fulfillment_type,
        "payment_method": "card",
        "special_instructions": order.special_instructions or "",
    }
    if fulfillment_type == FULFILLMENT_TYPES[1]:
        prefill["pickup_date"] = pickup_date
        prefill["pickup_time"] = pickup_time
    return prefill


@orders_bp.route("/checkout", methods=["GET", "POST"])
def checkout() -> str | Response:
    if request.method == "POST":
        form_data = _normalize_form()
        cart = _build_cart_payload(_menu())
        errors, field_errors, fulfillment_plan = _validate_checkout(form_data, cart)
        if errors or fulfillment_plan is None:
            context = _get_checkout_context(
                form_data=form_data,
                errors=errors,
                field_errors=field_errors,
                entry_step="checkout",
            )
            return render_template("menu/checkout.html", **context), 400
        payment_attempt, failure_message = _run_payment_attempt(form_data, cart["total_cents"] + current_app.config["ORDER_SERVICE_FEE_CENTS"])
        if failure_message:
            payment_field = "card_number" if form_data["payment_method"] == "card" else "payment_method"
            field_errors[payment_field] = failure_message
            context = _get_checkout_context(
                form_data=form_data,
                errors=[failure_message],
                field_errors=field_errors,
                entry_step="payment",
            )
            return render_template("menu/checkout.html", **context), 402

        try:
            order = _create_order_with_retries(form_data, fulfillment_plan, cart, payment_attempt)
        except (IntegrityError, RuntimeError):
            db.session.rollback()
            retry_message = (
                "The live queue changed while this order was being saved. Please submit checkout again to refresh the queue."
            )
            context = _get_checkout_context(
                form_data=form_data,
                errors=[retry_message],
                field_errors={"fulfillment_type": retry_message},
                entry_step="checkout",
            )
            return render_template("menu/checkout.html", **context), 409
        _finalize_successful_order(order)
        return redirect(url_for("orders.receipt", order=order.order_number))

    if _build_cart_payload(_menu())["lines"]:
        _checkout_token()
    if request.method == "GET":
        raw_hint = request.args.get("fulfillment", "").strip().lower()
        if raw_hint in FULFILLMENT_TYPES:
            _apply_checkout_fulfillment_hint(raw_hint)
    return render_template("menu/checkout.html", **_get_checkout_context(entry_step="checkout"))


@orders_bp.get("/payment")
def payment() -> str:
    if _build_cart_payload(_menu())["lines"]:
        _checkout_token()
    raw_hint = request.args.get("fulfillment", "").strip().lower()
    if raw_hint in FULFILLMENT_TYPES:
        _apply_checkout_fulfillment_hint(raw_hint)
    return render_template("menu/checkout.html", **_get_checkout_context(entry_step="payment"))


@orders_bp.get("/pickup-planner")
def pickup_planner() -> str:
    if _build_cart_payload(_menu())["lines"]:
        _checkout_token()
    _apply_checkout_fulfillment_hint(request.args.get("fulfillment", "").strip().lower() or FULFILLMENT_TYPES[1])
    return render_template("menu/checkout.html", **_get_checkout_context(entry_step="pickup"))


def _lookup_receipt_order() -> Order | None:
    order_number = request.args.get("order") or session.get(SESSION_LAST_ORDER_KEY)
    if not order_number or not isinstance(order_number, str):
        return None
    return Order.query.filter_by(order_number=order_number).first()


@orders_bp.get("/receipt")
def receipt() -> str:
    order = _lookup_receipt_order()
    if order is None:
        return render_template("menu/receipt.html", order=None)
    return render_template("menu/receipt.html", order=_serialize_order(order))


@orders_bp.get("/orders")
def orders() -> str:
    session_orders = [_serialize_order(order) for order in _session_orders()]
    filtered_orders, filters = _filter_serialized_orders(session_orders)
    total_spend = sum(order["total_cents"] for order in filtered_orders)
    ready_banners = _ready_notification_banners(filtered_orders if filtered_orders else session_orders)
    return render_template(
        "user/orders.html",
        orders=filtered_orders,
        order_count=len(filtered_orders),
        total_order_count=len(session_orders),
        total_spend_display=format_aud(total_spend),
        latest_order=filtered_orders[0] if filtered_orders else (session_orders[0] if session_orders else None),
        filters=filters,
        available_statuses=list(ORDER_STATUS_SEQUENCE),
        ready_banners=ready_banners,
    )


@orders_bp.get("/api/orders")
def api_orders():
    orders = [_serialize_order(order) for order in _session_orders()]
    filtered_orders, filters = _filter_serialized_orders(orders)
    return jsonify({"orders": filtered_orders, "count": len(filtered_orders), "filters": filters})


@orders_bp.get("/orders/<order_number>")
def order_detail(order_number: str):
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    return render_template("user/order_detail.html", order=_serialize_order(order))


@orders_bp.get("/api/orders/<order_number>")
def api_order_detail(order_number: str):
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    return jsonify(_serialize_order(order))


@orders_bp.patch("/api/orders/<order_number>/status")
@admin_required
def api_update_order_status(order_number: str):
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    body = request.get_json(silent=True) or {}
    next_status = body.get("status")
    kitchen_notes = body.get("kitchen_notes")

    if next_status not in ORDER_STATUS_SEQUENCE:
        return api_error_response(
            "status must be one of the supported order states",
            status=400,
            code="invalid_order_status",
            details={"allowed_statuses": list(ORDER_STATUS_SEQUENCE)},
            extra={"allowed_statuses": list(ORDER_STATUS_SEQUENCE)},
        )
    if kitchen_notes is not None and not isinstance(kitchen_notes, str):
        return api_error_response(
            "kitchen_notes must be a string when provided",
            status=400,
            code="invalid_kitchen_notes",
        )
    allowed_next_status = _next_order_status(order.order_status)
    if next_status != allowed_next_status:
        return api_error_response(
            "status transitions must move forward one step at a time",
            status=400,
            code="invalid_status_transition",
            details={
                "current_status": order.order_status,
                "allowed_next_status": allowed_next_status,
            },
            extra={
                "current_status": order.order_status,
                "allowed_next_status": allowed_next_status,
            },
        )

    order.order_status = next_status
    if kitchen_notes is not None:
        order.kitchen_notes = kitchen_notes.strip() or None
    if next_status == ORDER_STATUS_SEQUENCE[2]:
        _ensure_ready_notifications(order)
    db.session.commit()
    return jsonify(_serialize_order(order))


@orders_bp.post("/orders/<order_number>/reorder")
def reorder(order_number: str):
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    lines = [{"id": line.item_id, "qty": line.quantity} for line in order.line_items]
    _save_lines(lines)
    _clear_checkout_token()
    _save_checkout_prefill(_reorder_prefill(order))
    return redirect(url_for("orders.checkout"))


@orders_bp.get("/orders/<order_number>/receipt.pdf")
def receipt_pdf(order_number: str):
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    payload = _serialize_order(order)
    pdf_bytes = build_receipt_pdf(payload)
    return Response(
        pdf_bytes,
        mimetype="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{order.order_number.lower()}-receipt.pdf"',
        },
    )


@orders_bp.get("/orders/<order_number>/qr.png")
def receipt_qr(order_number: str):
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    qr = qrcode.QRCode(
        version=3,
        border=1,
        box_size=8,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
    )
    qr.add_data(_qr_destination_url(order.order_number))
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return Response(buffer.getvalue(), mimetype="image/png")
