from __future__ import annotations

from datetime import datetime
from pathlib import Path

from flask import Blueprint, current_app, jsonify, render_template, request, session

from extensions import db
from menu_catalog import find_item, load_enriched_menu, price_to_cents
from models import Order, OrderItem, User
from routes.helpers import render_feature_page


orders_bp = Blueprint("orders", __name__)
SESSION_LINES_KEY = "cart_lines"
SESSION_USER_ID_KEY = "user_id"


def _menu_path() -> Path:
    return Path(current_app.root_path) / "static" / "data" / "menu.json"


def _current_user() -> User | None:
    user_id = session.get(SESSION_USER_ID_KEY)
    if not isinstance(user_id, int):
        return None
    return User.query.get(user_id)


@orders_bp.get("/cart")
def cart() -> str:
    return render_template("menu/cart.html")


@orders_bp.get("/checkout")
def checkout() -> str:
    return render_feature_page("checkout")


@orders_bp.get("/payment")
def payment() -> str:
    return render_feature_page("payment")


@orders_bp.get("/pickup-planner")
def pickup_planner() -> str:
    return render_feature_page("pickup_planner")


@orders_bp.get("/receipt")
def receipt() -> str:
    return render_feature_page("receipt")


@orders_bp.get("/orders")
def orders() -> str:
    return render_feature_page("orders")


@orders_bp.post("/api/orders/checkout")
def checkout_api():
    user = _current_user()
    if not user:
        return jsonify({"error": "authentication required"}), 401

    raw_lines = session.get(SESSION_LINES_KEY)
    lines = raw_lines if isinstance(raw_lines, list) else []
    if not lines:
        return jsonify({"error": "cart is empty"}), 400

    body = request.get_json(silent=True) or {}
    pickup_at_raw = str(body.get("pickup_at", "")).strip()
    pickup_at = None
    if pickup_at_raw:
        try:
            pickup_at = datetime.fromisoformat(pickup_at_raw)
        except ValueError:
            return jsonify({"error": "pickup_at must be ISO-8601 datetime"}), 400

    menu = load_enriched_menu(_menu_path())
    order = Order(user_id=user.id, pickup_at=pickup_at, status="Pending", total_cents=0)
    db.session.add(order)

    total = 0
    created_items = 0
    for row in lines:
        item_id = row.get("id")
        qty = int(row.get("qty", 0))
        if not item_id or qty < 1:
            continue
        found = find_item(menu, item_id)
        if not found:
            continue
        _, item = found
        unit = price_to_cents(item.get("price"))
        total += unit * qty
        db.session.add(
            OrderItem(
                order=order,
                item_id=item_id,
                item_name=item.get("name") or item_id,
                unit_price_cents=unit,
                quantity=qty,
            )
        )
        created_items += 1

    if created_items == 0:
        db.session.rollback()
        return jsonify({"error": "cart does not contain valid items"}), 400

    order.total_cents = total
    db.session.commit()
    session[SESSION_LINES_KEY] = []
    session.modified = True
    return jsonify({"order_id": order.id, "status": order.status, "total_cents": order.total_cents}), 201


@orders_bp.get("/api/orders/my")
def my_orders_api():
    user = _current_user()
    if not user:
        return jsonify({"error": "authentication required"}), 401
    rows = Order.query.filter_by(user_id=user.id).order_by(Order.created_at.desc()).all()
    return jsonify(
        {
            "orders": [
                {
                    "id": row.id,
                    "status": row.status,
                    "pickup_at": row.pickup_at.isoformat() if row.pickup_at else None,
                    "total_cents": row.total_cents,
                    "created_at": row.created_at.isoformat(),
                    "items": [
                        {
                            "item_id": item.item_id,
                            "item_name": item.item_name,
                            "unit_price_cents": item.unit_price_cents,
                            "quantity": item.quantity,
                        }
                        for item in row.items
                    ],
                }
                for row in rows
            ]
        }
    )
