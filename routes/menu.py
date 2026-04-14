from __future__ import annotations

from pathlib import Path

from flask import Blueprint, abort, jsonify, redirect, render_template, request, url_for

from menu_catalog import find_item, load_enriched_menu
from models import Order

public_bp = Blueprint("public", __name__)

_ROOT_DIR = Path(__file__).resolve().parent.parent


def _menu_path() -> Path:
    return _ROOT_DIR / "static" / "data" / "menu.json"


def _home_context(*, track_error: str | None = None, track_value: str = "") -> dict:
    from routes.orders import public_ordering_snapshot

    return {
        "ordering_snapshot": public_ordering_snapshot(),
        "track_error": track_error,
        "track_value": track_value,
    }


@public_bp.get("/")
def home() -> str:
    return render_template("index.html", **_home_context())


@public_bp.post("/track-order")
def track_order():
    raw_order_number = request.form.get("order_number", "").strip().upper()
    destination = request.form.get("destination", "detail").strip().lower()
    if not raw_order_number:
        return render_template(
            "index.html",
            **_home_context(track_error="Enter an order number to continue.", track_value=""),
        ), 400

    order = Order.query.filter_by(order_number=raw_order_number).first()
    if order is None:
        return render_template(
            "index.html",
            **_home_context(
                track_error=f"Order {raw_order_number} was not found. Check the number on your receipt.",
                track_value=raw_order_number,
            ),
        ), 404

    if destination == "receipt":
        return redirect(url_for("orders.receipt", order=raw_order_number))
    return redirect(url_for("orders.order_detail", order_number=raw_order_number))


@public_bp.get("/menu")
def menu() -> str:
    return render_template("menu/menu.html")


@public_bp.get("/api/menu")
def api_menu():
    data = load_enriched_menu(_menu_path())
    return jsonify(data)


@public_bp.get("/menu/item/<item_id>")
def menu_item_detail(item_id: str) -> str:
    data = load_enriched_menu(_menu_path())
    found = find_item(data, item_id)
    if not found:
        abort(404)
    category, item = found
    return render_template("menu/item_detail.html", item=item, category=category)
