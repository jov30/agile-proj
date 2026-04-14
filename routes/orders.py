from __future__ import annotations

import io
import re
import secrets
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

import qrcode
from flask import Blueprint, Response, current_app, jsonify, redirect, render_template, request, session, url_for

from menu_catalog import format_aud
from models import (
    ORDER_STATUS_SEQUENCE,
    PAYMENT_ATTEMPT_STATUS_SEQUENCE,
    Order,
    OrderLineItem,
    PaymentAttempt,
    db,
)
from receipt_pdf import build_receipt_pdf
from routes.cart_api import SESSION_LINES_KEY, _build_cart_payload, _menu, _save_lines


orders_bp = Blueprint("orders", __name__)
SESSION_LAST_ORDER_KEY = "last_order_number"
SESSION_ORDER_HISTORY_KEY = "order_history_numbers"
SESSION_CHECKOUT_TOKEN_KEY = "checkout_payment_token"

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
    return render_template("menu/cart.html")


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


def _default_checkout_form() -> dict[str, str]:
    windows = _pickup_windows()
    first_available = _first_available_pickup(windows)
    first_date = first_available["date"] if first_available else ""
    first_slot = first_available["time"] if first_available else ""
    return {
        "customer_name": "",
        "customer_email": "",
        "customer_phone": "",
        "pickup_date": first_date,
        "pickup_time": first_slot,
        "payment_method": "card",
        "card_name": "",
        "card_number": "",
        "card_expiry": "",
        "card_cvv": "",
        "special_instructions": "",
    }


def _payment_options() -> list[dict]:
    return [
        {"key": key, **value}
        for key, value in PAYMENT_METHODS.items()
    ]


def _status_timeline(order_status: str) -> list[dict]:
    try:
        active_index = ORDER_STATUS_SEQUENCE.index(order_status)
    except ValueError:
        active_index = 0

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


def _get_checkout_context(
    *,
    form_data: dict[str, str] | None = None,
    errors: list[str] | None = None,
    field_errors: dict[str, str] | None = None,
    entry_step: str = "checkout",
) -> dict:
    cart = _build_cart_payload(_menu())
    subtotal = cart["total_cents"]
    service_fee = current_app.config["ORDER_SERVICE_FEE_CENTS"] if cart["lines"] else 0
    total = subtotal + service_fee
    windows = _pickup_windows()
    selected_date = (form_data or {}).get("pickup_date")
    selected_slots = []
    for window in windows:
        if window["date"] == selected_date:
            selected_slots = window["slots"]
            break
    if not selected_slots and windows:
        selected_slots = windows[0]["slots"]
    next_available_pickup = _first_available_pickup(windows)
    payment_feedback = _latest_checkout_attempt() if cart["lines"] else None

    return {
        "entry_step": entry_step,
        "errors": errors or [],
        "field_errors": field_errors or {},
        "form_data": form_data or _default_checkout_form(),
        "cart": cart,
        "service_fee_cents": service_fee,
        "service_fee_display": format_aud(service_fee),
        "grand_total_cents": total,
        "grand_total_display": format_aud(total),
        "pickup_windows": windows,
        "selected_slots": selected_slots,
        "payment_options": _payment_options(),
        "pickup_lead_minutes": current_app.config["PICKUP_MIN_LEAD_MINUTES"],
        "pickup_slot_capacity": current_app.config["PICKUP_SLOT_CAPACITY"],
        "next_available_pickup": next_available_pickup,
        "payment_feedback": _serialize_payment_attempt(payment_feedback) if payment_feedback else None,
        "restaurant_phone": current_app.config["RESTAURANT_PHONE"],
    }


def _normalize_form() -> dict[str, str]:
    fields = [
        "customer_name",
        "customer_email",
        "customer_phone",
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


def _validate_checkout(form_data: dict[str, str], cart: dict) -> tuple[list[str], dict[str, str], datetime | None]:
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
    return errors, field_errors, pickup_at


def _build_order_from_cart(form_data: dict[str, str], pickup_at: datetime, cart: dict) -> Order:
    subtotal = cart["total_cents"]
    service_fee = current_app.config["ORDER_SERVICE_FEE_CENTS"]
    total = subtotal + service_fee
    payment_key = form_data["payment_method"]
    card_number = re.sub(r"\D", "", form_data["card_number"])

    order = Order(
        order_number=f"MCQ-{_now_local().strftime('%Y%m%d')}-{secrets.token_hex(2).upper()}",
        confirmation_code=f"PK-{secrets.token_hex(2).upper()}",
        customer_name=form_data["customer_name"],
        customer_email=form_data["customer_email"],
        customer_phone=form_data["customer_phone"],
        pickup_at=pickup_at.astimezone(_timezone()).replace(tzinfo=None),
        payment_method=PAYMENT_METHODS[payment_key]["label"],
        payment_status=PAYMENT_ATTEMPT_STATUS_SEQUENCE[1],
        payment_reference=f"SIM-{secrets.token_hex(4).upper()}",
        card_last4=card_number[-4:] if card_number else None,
        order_status=ORDER_STATUS_SEQUENCE[0],
        kitchen_notes="Pickup order queued for the kitchen.",
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


def _finalize_successful_order(order: Order) -> None:
    db.session.commit()
    _save_lines([])
    session[SESSION_LINES_KEY] = []
    _remember_order(order.order_number)
    _clear_checkout_token()


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
    attempts = sorted(order.payment_attempts, key=lambda attempt: attempt.created_at, reverse=True)
    return {
        "order_number": order.order_number,
        "confirmation_code": order.confirmation_code,
        "customer_name": order.customer_name,
        "customer_email": order.customer_email,
        "customer_phone": order.customer_phone,
        "created_at": created_local.strftime("%A, %d %b %Y at %I:%M %p").lstrip("0"),
        "created_relative_date": created_local.strftime("%d %b %Y"),
        "updated_at": updated_local.strftime("%A, %d %b %Y at %I:%M %p").lstrip("0"),
        "pickup_at": pickup_local.strftime("%A, %d %b %Y at %I:%M %p").lstrip("0"),
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
        "status_timeline": _status_timeline(order.order_status),
        "payment_attempt_count": len(attempts),
        "latest_payment_attempt": _serialize_payment_attempt(attempts[0]) if attempts else None,
        "payment_attempts": [_serialize_payment_attempt(attempt) for attempt in attempts],
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


def _session_orders() -> list[Order]:
    order_numbers = _history_numbers()
    if not order_numbers:
        return []
    orders = Order.query.filter(Order.order_number.in_(order_numbers)).order_by(Order.created_at.desc()).all()
    order_lookup = {order.order_number: order for order in orders}
    return [order_lookup[number] for number in order_numbers if number in order_lookup]


@orders_bp.route("/checkout", methods=["GET", "POST"])
def checkout() -> str | Response:
    if request.method == "POST":
        form_data = _normalize_form()
        cart = _build_cart_payload(_menu())
        errors, field_errors, pickup_at = _validate_checkout(form_data, cart)
        if errors or pickup_at is None:
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

        order = _build_order_from_cart(form_data, pickup_at, cart)
        order.payment_reference = payment_attempt.reference
        order.payment_status = payment_attempt.status
        payment_attempt.order = order
        payment_attempt.checkout_token = None
        _finalize_successful_order(order)
        return redirect(url_for("orders.receipt", order=order.order_number))

    if _build_cart_payload(_menu())["lines"]:
        _checkout_token()
    return render_template("menu/checkout.html", **_get_checkout_context(entry_step="checkout"))


@orders_bp.get("/payment")
def payment() -> str:
    if _build_cart_payload(_menu())["lines"]:
        _checkout_token()
    return render_template("menu/checkout.html", **_get_checkout_context(entry_step="payment"))


@orders_bp.get("/pickup-planner")
def pickup_planner() -> str:
    if _build_cart_payload(_menu())["lines"]:
        _checkout_token()
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
    total_spend = sum(order["total_cents"] for order in session_orders)
    return render_template(
        "user/orders.html",
        orders=session_orders,
        order_count=len(session_orders),
        total_spend_display=format_aud(total_spend),
        latest_order=session_orders[0] if session_orders else None,
    )


@orders_bp.get("/api/orders")
def api_orders():
    orders = [_serialize_order(order) for order in _session_orders()]
    return jsonify({"orders": orders, "count": len(orders)})


@orders_bp.get("/api/orders/<order_number>")
def api_order_detail(order_number: str):
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    return jsonify(_serialize_order(order))


@orders_bp.patch("/api/orders/<order_number>/status")
def api_update_order_status(order_number: str):
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    body = request.get_json(silent=True) or {}
    next_status = body.get("status")
    kitchen_notes = body.get("kitchen_notes")

    if next_status not in ORDER_STATUS_SEQUENCE:
        return (
            jsonify(
                {
                    "error": "status must be one of the supported order states",
                    "allowed_statuses": list(ORDER_STATUS_SEQUENCE),
                }
            ),
            400,
        )
    if kitchen_notes is not None and not isinstance(kitchen_notes, str):
        return jsonify({"error": "kitchen_notes must be a string when provided"}), 400

    order.order_status = next_status
    if kitchen_notes is not None:
        order.kitchen_notes = kitchen_notes.strip() or None
    db.session.commit()
    return jsonify(_serialize_order(order))


@orders_bp.post("/orders/<order_number>/reorder")
def reorder(order_number: str):
    order = Order.query.filter_by(order_number=order_number).first_or_404()
    lines = [{"id": line.item_id, "qty": line.quantity} for line in order.line_items]
    _save_lines(lines)
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
    qr.add_data(
        f"MCQ ORDER\norder_number={order.order_number}\nconfirmation_code={order.confirmation_code}\npickup_at={order.pickup_at.isoformat()}"
    )
    qr.make(fit=True)
    image = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return Response(buffer.getvalue(), mimetype="image/png")
