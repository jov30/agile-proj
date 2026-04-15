"""Session-backed cart JSON API."""

from __future__ import annotations

from pathlib import Path

from flask import Blueprint, current_app, jsonify, request, session

from menu_catalog import find_item, format_aud, load_enriched_menu, price_to_cents
from models import FULFILLMENT_TYPES

cart_api_bp = Blueprint("cart_api", __name__, url_prefix="/api/cart")

SESSION_LINES_KEY = "cart_lines"


def _menu_path() -> Path:
    return Path(current_app.root_path) / "static" / "data" / "menu.json"


def _menu() -> dict:
    return load_enriched_menu(_menu_path())


def _get_lines() -> list[dict]:
    raw = session.get(SESSION_LINES_KEY)
    if not isinstance(raw, list):
        return []
    return raw


def _save_lines(lines: list[dict]) -> None:
    session[SESSION_LINES_KEY] = lines
    session.modified = True


def _parse_quantity(raw_value, *, default: int | None = None) -> int | None:
    if raw_value is None:
        return default
    try:
        return int(raw_value)
    except (TypeError, ValueError):
        return None


def _preferred_fulfillment_hint() -> str:
    value = session.get("preferred_fulfillment")
    if value in FULFILLMENT_TYPES:
        return value
    return FULFILLMENT_TYPES[0]


def _build_cart_payload(menu: dict) -> dict:
    lines = _get_lines()
    out_lines: list[dict] = []
    total = 0
    item_count = 0
    for row in lines:
        item_id = row.get("id")
        qty = int(row.get("qty", 0))
        if not item_id or qty < 1:
            continue
        found = find_item(menu, item_id)
        if not found:
            continue
        cat, item = found
        unit = price_to_cents(item.get("price"))
        line_total = unit * qty
        total += line_total
        item_count += qty
        out_lines.append(
            {
                "item_id": item_id,
                "name": item.get("name"),
                "category_title": cat.get("title"),
                "price_display": item.get("price") or format_aud(unit),
                "unit_cents": unit,
                "quantity": qty,
                "line_cents": line_total,
                "line_display": format_aud(line_total),
            }
        )
    service_fee = current_app.config["ORDER_SERVICE_FEE_CENTS"] if out_lines else 0
    checkout_total = total + service_fee
    preferred_fulfillment = _preferred_fulfillment_hint()
    return {
        "lines": out_lines,
        "line_count": len(out_lines),
        "item_count": item_count,
        "total_cents": total,
        "total_display": format_aud(total),
        "service_fee_cents": service_fee,
        "service_fee_display": format_aud(service_fee),
        "checkout_total_cents": checkout_total,
        "checkout_total_display": format_aud(checkout_total),
        "preferred_fulfillment": preferred_fulfillment,
        "preferred_checkout_url": f"/checkout?fulfillment={preferred_fulfillment}",
        "alternate_fulfillment": FULFILLMENT_TYPES[1] if preferred_fulfillment == FULFILLMENT_TYPES[0] else FULFILLMENT_TYPES[0],
        "empty": not out_lines,
    }


@cart_api_bp.get("/")
def get_cart():
    menu = _menu()
    return jsonify(_build_cart_payload(menu))


@cart_api_bp.post("/items")
def add_item():
    body = request.get_json(silent=True) or {}
    item_id = body.get("item_id")
    qty = _parse_quantity(body.get("quantity"), default=1)
    if not item_id or not isinstance(item_id, str):
        return jsonify({"error": "item_id is required"}), 400
    if qty is None:
        return jsonify({"error": "quantity must be a whole number"}), 400
    if qty < 1:
        return jsonify({"error": "quantity must be at least 1"}), 400
    menu = _menu()
    if not find_item(menu, item_id):
        return jsonify({"error": "Unknown menu item"}), 404
    lines = _get_lines()
    merged = False
    for row in lines:
        if row.get("id") == item_id:
            row["qty"] = int(row.get("qty", 0)) + qty
            merged = True
            break
    if not merged:
        lines.append({"id": item_id, "qty": qty})
    _save_lines(lines)
    return jsonify(_build_cart_payload(menu))


@cart_api_bp.patch("/items/<item_id>")
def update_line(item_id: str):
    body = request.get_json(silent=True) or {}
    qty = _parse_quantity(body.get("quantity"))
    if qty is None:
        return jsonify({"error": "quantity must be a whole number"}), 400
    lines = _get_lines()
    new_lines: list[dict] = []
    for row in lines:
        if row.get("id") != item_id:
            new_lines.append(row)
            continue
        if qty < 1:
            continue
        new_lines.append({"id": item_id, "qty": qty})
    _save_lines(new_lines)
    menu = _menu()
    return jsonify(_build_cart_payload(menu))


@cart_api_bp.delete("/items/<item_id>")
def remove_line(item_id: str):
    lines = [row for row in _get_lines() if row.get("id") != item_id]
    _save_lines(lines)
    menu = _menu()
    return jsonify(_build_cart_payload(menu))


@cart_api_bp.post("/clear")
def clear_cart():
    _save_lines([])
    menu = _menu()
    return jsonify(_build_cart_payload(menu))
