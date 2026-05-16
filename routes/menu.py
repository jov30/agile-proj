from __future__ import annotations

from pathlib import Path

from flask import Blueprint, abort, jsonify, redirect, render_template, request, session, url_for

from menu_catalog import filter_menu_by_query, find_item, load_enriched_menu
from models import CommunityPost, FULFILLMENT_TYPES, Order

public_bp = Blueprint("public", __name__)

_ROOT_DIR = Path(__file__).resolve().parent.parent


def _menu_path() -> Path:
    return _ROOT_DIR / "static" / "data" / "menu.json"


MENU_SEARCH_QUERY_MAX_LEN = 200

def _preferred_fulfillment(default: str = FULFILLMENT_TYPES[0]) -> str:
    raw_value = request.args.get("fulfillment", "").strip().lower()
    if raw_value in FULFILLMENT_TYPES:
        session["preferred_fulfillment"] = raw_value
        session.modified = True
        return raw_value

    session_value = session.get("preferred_fulfillment")
    if session_value in FULFILLMENT_TYPES:
        return session_value
    return default


def _home_context(*, track_error: str | None = None, track_value: str = "") -> dict:
    from routes.orders import public_ordering_snapshot

    return {
        "ordering_snapshot": public_ordering_snapshot(),
        "track_error": track_error,
        "track_value": track_value,
    }


def _community_menu_badges() -> dict[str, list[str]]:
    badges: dict[str, list[str]] = {}
    posts = CommunityPost.query.order_by(CommunityPost.created_at.desc()).limit(100).all()
    for post in posts:
        key = post.meal_name.lower()
        labels = badges.setdefault(key, [])
        if len(post.reactions) >= 3 and "Loved by members" not in labels:
            labels.append("Loved by members")
        if post.order_number and "Pickup combo" not in labels:
            labels.append("Pickup combo")
        if post.spice_level and "Spice tip" not in labels:
            labels.append("Spice tip")
        if post.drink_pairing and "Drink pairing" not in labels:
            labels.append("Drink pairing")
        if len(labels) >= 3:
            badges[key] = labels[:3]
    return badges


def _apply_community_badges(data: dict) -> dict:
    badge_lookup = _community_menu_badges()
    if not badge_lookup:
        return data
    for category in data.get("categories", []):
        for item in category.get("items", []):
            item_name = item.get("name", "")
            matched: list[str] = []
            for shared_name, labels in badge_lookup.items():
                if shared_name in item_name.lower() or item_name.lower() in shared_name:
                    matched.extend(labels)
            if matched:
                item["community_badges"] = list(dict.fromkeys(matched))[:3]
    return data


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
    preferred_fulfillment = _preferred_fulfillment()
    return render_template("menu/menu.html", preferred_fulfillment=preferred_fulfillment)


@public_bp.get("/api/menu")
def api_menu():
    data = load_enriched_menu(_menu_path())
    raw_q = request.args.get("q", "", type=str) or ""
    q = raw_q.strip()
    if q:
        if len(q) > MENU_SEARCH_QUERY_MAX_LEN:
            q = q[:MENU_SEARCH_QUERY_MAX_LEN]
        data = filter_menu_by_query(data, q)
    return jsonify(_apply_community_badges(data))


@public_bp.get("/menu/item/<item_id>")
def menu_item_detail(item_id: str) -> str:
    data = load_enriched_menu(_menu_path())
    data = _apply_community_badges(data)
    found = find_item(data, item_id)
    if not found:
        abort(404)
    category, item = found
    preferred_fulfillment = _preferred_fulfillment()
    return render_template(
        "menu/item_detail.html",
        item=item,
        category=category,
        preferred_fulfillment=preferred_fulfillment,
    )
