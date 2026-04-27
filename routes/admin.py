from __future__ import annotations

import json
import secrets
from pathlib import Path

from flask import Blueprint, redirect, render_template, request, url_for
from sqlalchemy import func, or_, select

from menu_catalog import load_enriched_menu
from models import FULFILLMENT_TYPES, ORDER_STATUS_SEQUENCE, Order, User, Voucher, db
from routes.auth import admin_required


admin_bp = Blueprint("admin", __name__, url_prefix="/admin")
_ROOT_DIR = Path(__file__).resolve().parent.parent
VOUCHER_VALUES = (10, 20, 30, 40, 50, 80, 100, 150, 200)


def _menu_path() -> Path:
    return _ROOT_DIR / "static" / "data" / "menu.json"


def _read_menu_raw() -> dict:
    with _menu_path().open(encoding="utf-8") as f:
        return json.load(f)


def _write_menu_raw(data: dict) -> None:
    with _menu_path().open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")


def _ingredients_section(ingredients: str) -> dict:
    return {
        "label": "Ingredients",
        "items": [item.strip() for item in ingredients.split(",") if item.strip()],
    }


def _item_ingredients(item: dict) -> str:
    for section in item.get("sections", []):
        if str(section.get("label", "")).lower() == "ingredients":
            return ", ".join(section.get("items", []))
    return ""


def _set_ingredients(item: dict, ingredients: str) -> None:
    sections = list(item.get("sections", []))
    cleaned = _ingredients_section(ingredients)
    for index, section in enumerate(sections):
        if str(section.get("label", "")).lower() == "ingredients":
            sections[index] = cleaned
            break
    else:
        sections.insert(0, cleaned)
    item["sections"] = sections


def _find_raw_menu_item(data: dict, item_id: str) -> tuple[dict, dict] | None:
    enriched = load_enriched_menu(_menu_path())
    for category_index, category in enumerate(enriched.get("categories", [])):
        for item_index, item in enumerate(category.get("items", [])):
            if item.get("id") == item_id:
                raw_category = data["categories"][category_index]
                return raw_category, raw_category["items"][item_index]
    return None


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


def _voucher_payload(voucher: Voucher) -> dict:
    dollars = voucher.value_cents // 100
    banh_mi_count = max(1, voucher.value_cents // 1000)
    coffee_count = max(1, voucher.value_cents // 600)
    combo_count = max(1, voucher.value_cents // 1600)
    return {
        "code": voucher.code,
        "label": voucher.label,
        "description": voucher.description
        or "Use this voucher for MCQ street-food favourites such as banh mi, Vietnamese coffee, pho, rice bowls, and pickup combos.",
        "value_display": f"${dollars}",
        "created_label": voucher.created_at.strftime("%d %b %Y"),
        "banh_mi_count": banh_mi_count,
        "coffee_count": coffee_count,
        "combo_count": combo_count,
    }


def _new_voucher_code() -> str:
    while True:
        code = f"MCQ-{secrets.token_hex(3).upper()}"
        if Voucher.query.filter_by(code=code).first() is None:
            return code


def _income_rows(period_expr, *, limit: int) -> list[dict]:
    rows = (
        db.session.query(
            period_expr.label("period"),
            func.count(Order.id).label("order_count"),
            func.coalesce(func.sum(Order.total_cents), 0).label("revenue_cents"),
        )
        .group_by("period")
        .order_by(period_expr.desc())
        .limit(limit)
        .all()
    )
    rows = list(reversed(rows))
    max_revenue = max((row.revenue_cents for row in rows), default=0) or 1
    return [
        {
            "period": row.period,
            "order_count": row.order_count,
            "revenue_display": f"${row.revenue_cents / 100:.2f}",
            "bar_height": max(6, round((row.revenue_cents / max_revenue) * 100)),
            "bar_width": max(4, round((row.revenue_cents / max_revenue) * 100)),
        }
        for row in rows
    ]


@admin_bp.get("/")
@admin_required
def admin_dashboard() -> str:
    recent_orders = (
        Order.query.order_by(Order.created_at.desc())
        .limit(8)
        .all()
    )
    total_orders = Order.query.count()
    completed_orders = Order.query.filter(Order.order_status == ORDER_STATUS_SEQUENCE[-1]).count()
    active_orders = Order.query.filter(Order.order_status != ORDER_STATUS_SEQUENCE[-1]).count()
    revenue_cents = db.session.query(func.coalesce(func.sum(Order.total_cents), 0)).scalar() or 0

    return render_template(
        "admin/dashboard.html",
        total_orders=total_orders,
        completed_orders=completed_orders,
        active_orders=active_orders,
        revenue_display=f"${revenue_cents / 100:.2f}",
        daily_report=_income_rows(func.strftime("%Y-%m-%d", Order.created_at), limit=14),
        monthly_report=_income_rows(func.strftime("%Y-%m", Order.created_at), limit=8),
        yearly_report=_income_rows(func.strftime("%Y", Order.created_at), limit=5),
        recent_orders=[_serialize_admin_order(order) for order in recent_orders],
    )


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


@admin_bp.get("/orders")
@admin_required
def admin_orders() -> str:
    q = request.args.get("q", "").strip()
    status = request.args.get("status", "").strip()
    fulfillment = request.args.get("fulfillment", "").strip().lower()

    query = Order.query
    if status in ORDER_STATUS_SEQUENCE:
        query = query.filter(Order.order_status == status)
    if fulfillment in FULFILLMENT_TYPES:
        query = query.filter(Order.fulfillment_type == fulfillment)
    if q:
        like = f"%{q.lower()}%"
        query = query.filter(
            or_(
                func.lower(Order.order_number).like(like),
                func.lower(Order.customer_name).like(like),
                func.lower(Order.customer_email).like(like),
            )
        )

    orders = query.order_by(Order.created_at.desc()).limit(100).all()
    total_cents = sum(order.total_cents for order in orders)
    return render_template(
        "admin/order_list.html",
        orders=[_serialize_admin_order(order) for order in orders],
        filters={"q": q, "status": status, "fulfillment": fulfillment},
        available_statuses=list(ORDER_STATUS_SEQUENCE),
        fulfillment_types=list(FULFILLMENT_TYPES),
        total_display=f"${total_cents / 100:.2f}",
    )


@admin_bp.route("/menu", methods=["GET", "POST"])
@admin_required
def admin_menu():
    data = _read_menu_raw()
    if request.method == "POST":
        action = request.form.get("action", "").strip()
        if action == "add":
            category_id = request.form.get("category_id", "").strip()
            category = next((cat for cat in data.get("categories", []) if cat.get("id") == category_id), None)
            if category is not None:
                item = {
                    "name": request.form.get("name", "").strip() or "New menu item",
                    "price": request.form.get("price", "").strip() or "$0",
                    "summary": request.form.get("summary", "").strip(),
                    "image": request.form.get("image", "").strip(),
                    "available": request.form.get("available") == "on",
                    "sections": [_ingredients_section(request.form.get("ingredients", ""))],
                }
                category.setdefault("items", []).append(item)
                _write_menu_raw(data)
        elif action == "edit":
            found = _find_raw_menu_item(data, request.form.get("item_id", ""))
            if found is not None:
                _, item = found
                item["name"] = request.form.get("name", "").strip() or item.get("name", "Menu item")
                item["price"] = request.form.get("price", "").strip() or item.get("price", "$0")
                item["summary"] = request.form.get("summary", "").strip()
                item["image"] = request.form.get("image", "").strip()
                item["available"] = request.form.get("available") == "on"
                _set_ingredients(item, request.form.get("ingredients", ""))
                _write_menu_raw(data)
        elif action == "delete":
            found = _find_raw_menu_item(data, request.form.get("item_id", ""))
            if found is not None:
                category, item = found
                category["items"] = [row for row in category.get("items", []) if row is not item]
                _write_menu_raw(data)
        data = _read_menu_raw()

    enriched = load_enriched_menu(_menu_path())
    categories = enriched.get("categories", [])
    items = []
    for category in categories:
        for item in category.get("items", []):
            items.append(
                {
                    "id": item.get("id"),
                    "name": item.get("name", ""),
                    "category_id": category.get("id"),
                    "category_title": category.get("title", ""),
                    "price": item.get("price", ""),
                    "summary": item.get("summary", ""),
                    "image": item.get("image", ""),
                    "available": item.get("available", True),
                    "ingredients": _item_ingredients(item),
                }
            )
    return render_template(
        "admin/menu_manage.html",
        categories=categories,
        items=items,
        available_count=sum(1 for item in items if item["available"]),
    )


@admin_bp.route("/vouchers", methods=["GET", "POST"])
@admin_required
def admin_vouchers():
    if request.method == "POST":
        raw_value = request.form.get("value", "").strip()
        try:
            dollars = int(raw_value)
        except ValueError:
            dollars = 10
        if dollars not in VOUCHER_VALUES:
            dollars = 10
        description = request.form.get("description", "").strip()
        voucher = Voucher(
            code=_new_voucher_code(),
            value_cents=dollars * 100,
            label=f"MCQ ${dollars} Digital Voucher",
            description=description
            or "Use this voucher for MCQ street-food favourites such as banh mi, Vietnamese coffee, pho, rice bowls, and pickup combos.",
        )
        db.session.add(voucher)
        db.session.commit()
        return redirect(url_for("admin.admin_vouchers", code=voucher.code))

    vouchers = Voucher.query.order_by(Voucher.created_at.desc()).limit(24).all()
    selected_code = request.args.get("code", "").strip()
    selected = next((voucher for voucher in vouchers if voucher.code == selected_code), None)
    if selected is None and vouchers:
        selected = vouchers[0]
    return render_template(
        "admin/vouchers.html",
        values=VOUCHER_VALUES,
        vouchers=[_voucher_payload(voucher) for voucher in vouchers],
        selected_voucher=_voucher_payload(selected) if selected else None,
    )


@admin_bp.get("/customers")
@admin_required
def admin_customers():
    # NOTE: queries all customers into memory for simplicity.
    # TODO: refactor pagination at scale.

    registered_email_subq = select(User.email).where(User.role == "customer")

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
                "profile_href": url_for("admin.admin_customer_detail", email=r.email),
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
                "profile_href": url_for("admin.admin_customer_detail", email=r.email),
            }
        )

    customers.sort(key=lambda c: c["name"].lower())

    q = request.args.get("q", "").strip()
    account_type = request.args.get("account_type", "all").strip().lower()
    if account_type not in {"all", "registered", "guest"}:
        account_type = "all"

    if account_type != "all":
        customers = [c for c in customers if c["type"] == account_type]

    if q:
        q_lower = q.lower()
        customers = [
            c
            for c in customers
            if q_lower in c["name"].lower() or q_lower in c["email"].lower()
        ]

    registered_count = sum(1 for c in customers if c["type"] == "registered")
    guest_count = sum(1 for c in customers if c["type"] == "guest")
    # TODO: optimise customer stats aggregation (e.g. compute registered/guest counts in the DB
    # or in the initial query instead of iterating over the full customers list in Python)

    return render_template(
        "admin/customers.html",
        customers=customers,
        search_query=q,
        account_type=account_type,
        registered_count=registered_count,
        guest_count=guest_count,
    )


@admin_bp.route("/customers/<path:email>", methods=["GET", "POST"])
@admin_required
def admin_customer_detail(email: str):
    normalized_email = email.strip().lower()
    user = User.query.filter(func.lower(User.email) == normalized_email).first()
    if request.method == "POST" and user is not None:
        user.name = request.form.get("name", "").strip() or user.name
        new_email = request.form.get("email", "").strip().lower()
        if new_email and new_email != user.email:
            Order.query.filter(func.lower(Order.customer_email) == user.email.lower()).update(
                {"customer_email": new_email},
                synchronize_session=False,
            )
            user.email = new_email
            normalized_email = new_email
        db.session.commit()
        return redirect(url_for("admin.admin_customer_detail", email=normalized_email))

    orders = (
        Order.query.filter(func.lower(Order.customer_email) == normalized_email)
        .order_by(Order.created_at.desc())
        .all()
    )
    total_cents = sum(order.total_cents for order in orders)
    customer_name = user.name if user else (orders[0].customer_name if orders else normalized_email)
    return render_template(
        "admin/customer_detail.html",
        customer={
            "name": customer_name,
            "email": normalized_email,
            "type": "registered" if user else "guest",
            "joined": user.created_at.strftime("%-d %b %Y") if user else "Guest customer",
            "order_count": len(orders),
            "total_spent": f"${total_cents / 100:.2f}",
        },
        user=user,
        orders=[_serialize_admin_order(order) for order in orders],
    )
