from __future__ import annotations

import hashlib
import logging
from collections import Counter
from pathlib import Path

import requests
from flask import Blueprint, current_app, jsonify, render_template, request, session

from menu_catalog import format_aud, load_enriched_menu
from models import Order
from routes.auth import current_user
from routes.helpers import render_feature_page


user_bp = Blueprint("user", __name__)
SUPPORT_CHAT_HISTORY_KEY = "support_chat_history"
LOGGER = logging.getLogger(__name__)
_ROOT_DIR = Path(__file__).resolve().parent.parent

_MEMBERSHIP_TIERS = (
    {"name": "Lantern Starter", "min_points": 0, "accent": "amber"},
    {"name": "Market Regular", "min_points": 120, "accent": "teal"},
    {"name": "Golden Chopsticks", "min_points": 260, "accent": "gold"},
    {"name": "Chef's Circle", "min_points": 480, "accent": "plum"},
)


def _support_history() -> list[dict[str, str]]:
    raw_history = session.get(SUPPORT_CHAT_HISTORY_KEY)
    if not isinstance(raw_history, list):
        return []
    history: list[dict[str, str]] = []
    for entry in raw_history:
        if not isinstance(entry, dict):
            continue
        role = entry.get("role")
        content = entry.get("content")
        if role not in {"user", "assistant"} or not isinstance(content, str) or not content.strip():
            continue
        history.append({"role": role, "content": content.strip()})
    return history


def _menu_data() -> dict:
    return load_enriched_menu(_ROOT_DIR / "static" / "data" / "menu.json")


def _menu_item_lookup() -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    menu = _menu_data()
    for category in menu.get("categories", []):
        for item in category.get("items", []):
            lookup[item["id"]] = {
                "id": item["id"],
                "name": item["name"],
                "description": item.get("description", ""),
                "price": item.get("price", ""),
                "image": item.get("image", category.get("image")),
                "category": category["title"],
                "href": f"/menu/item/{item['id']}",
            }
    return lookup


def _active_customer_orders() -> list[Order]:
    user = current_user()
    if user and user.get("email"):
        return (
            Order.query.filter_by(customer_email=user["email"])
            .order_by(Order.created_at.desc())
            .all()
        )

    history = session.get("order_history_numbers", [])
    if isinstance(history, list):
        order_numbers = [value for value in history if isinstance(value, str)][:12]
        if order_numbers:
            orders = Order.query.filter(Order.order_number.in_(order_numbers)).all()
            lookup = {order.order_number: order for order in orders}
            return [lookup[number] for number in order_numbers if number in lookup]
    return []


def _member_code(seed_text: str) -> str:
    digest = hashlib.sha1(seed_text.encode("utf-8")).hexdigest().upper()[:8]
    return f"MCQ-{digest[:4]}-{digest[4:]}"


def _membership_summary(orders: list[Order]) -> dict:
    user = current_user()
    seed_source = user["email"] if user else "guest-member-preview"
    total_spend_cents = sum(order.total_cents for order in orders)
    points_balance = total_spend_cents // 100
    total_orders = len(orders)
    instant_orders = sum(1 for order in orders if order.fulfillment_type == "instant")
    scheduled_orders = max(0, total_orders - instant_orders)
    current_tier = _MEMBERSHIP_TIERS[0]
    next_tier = None
    for index, tier in enumerate(_MEMBERSHIP_TIERS):
        if points_balance >= tier["min_points"]:
            current_tier = tier
            next_tier = _MEMBERSHIP_TIERS[index + 1] if index + 1 < len(_MEMBERSHIP_TIERS) else None
    progress_base = current_tier["min_points"]
    progress_target = next_tier["min_points"] if next_tier else current_tier["min_points"] + 1
    progress_span = max(1, progress_target - progress_base)
    progress_value = min(progress_span, max(0, points_balance - progress_base))
    progress_percent = 100 if not next_tier else round((progress_value / progress_span) * 100)
    return {
        "member_name": user["name"] if user else "Guest preview member",
        "member_email": user["email"] if user else "Join to save your points ledger",
        "member_code": _member_code(seed_source),
        "points_balance": points_balance,
        "points_display": f"{points_balance:,}",
        "total_spend_display": format_aud(total_spend_cents),
        "total_orders": total_orders,
        "instant_orders": instant_orders,
        "scheduled_orders": scheduled_orders,
        "current_tier": current_tier,
        "next_tier": next_tier,
        "progress_percent": progress_percent,
        "points_to_next": 0 if not next_tier else max(0, next_tier["min_points"] - points_balance),
        "preview_note": (
            "This loyalty card is a polished UI scaffold. A future membership service can plug a real points ledger into the same layout."
        ),
        "benefits": [
            {"title": "Member-only point wallet", "text": "Track dine-and-pickup spend in one place and convert every dollar into rewards-ready points."},
            {"title": "Priority reorder tray", "text": "Bring favourite meals and past combos back into the cart faster for repeat visits."},
            {"title": "Community identity", "text": "Use the same member profile to share meal boards, street-food stories, and seasonal picks with other customers."},
        ],
    }


def _saved_meals_context() -> dict:
    menu_lookup = _menu_item_lookup()
    orders = _active_customer_orders()
    counts: Counter[str] = Counter()
    for order in orders:
        for line in order.line_items:
            counts[line.item_id] += line.quantity

    saved_items = []
    for item_id, quantity in counts.most_common(6):
        item = menu_lookup.get(item_id)
        if not item:
            continue
        saved_items.append(
            {
                **item,
                "reason": f"Ordered {quantity} time{'s' if quantity != 1 else ''} across your recent pickup history.",
                "badge": "Member favourite",
            }
        )

    if not saved_items:
        fallback_ids = list(menu_lookup.keys())[:6]
        for index, item_id in enumerate(fallback_ids, start=1):
            item = menu_lookup[item_id]
            saved_items.append(
                {
                    **item,
                    "reason": "Starter collection card ready for a real favourites service.",
                    "badge": f"Starter pick {index}",
                }
            )

    collections = [
        {"title": "Late-lunch repeat tray", "text": "A neat cluster for people who rotate between pho, rice, and fast pickup drinks.", "accent": "amber"},
        {"title": "Shareable meal board", "text": "Prepared as a future bridge into community sharing and collaborative meal picks.", "accent": "teal"},
        {"title": "Weekend comfort stack", "text": "A saved lane for rich bowls, hot plates, and dessert add-ons.", "accent": "plum"},
    ]
    return {
        "saved_items": saved_items[:6],
        "collections": collections,
    }


def _community_context() -> dict:
    user = current_user()
    menu_lookup = _menu_item_lookup()
    featured_items = list(menu_lookup.values())[:4]
    member_name = user["name"] if user else "Lantern Guest"
    stories = [
        {
            "author": member_name,
            "handle": "@mcq.member",
            "lane": "Tonight's pickup story",
            "title": "Building a comfort tray for the late shift",
            "body": "A shareable meal note, favourite pairings, and a quick pickup story can all live here once the social backend is connected.",
            "meal": featured_items[0]["name"],
            "image": featured_items[0]["image"],
            "badge": "Member voice",
        },
        {
            "author": "Saigon Supper Club",
            "handle": "@supperclub",
            "lane": "Street-food board",
            "title": "Three dishes we would post to the MCQ community this week",
            "body": "The layout is prepared for meal photos, tasting notes, short captions, and future likes or comments.",
            "meal": featured_items[1]["name"],
            "image": featured_items[1]["image"],
            "badge": "Meal board",
        },
        {
            "author": "Pickup Regulars",
            "handle": "@pickupregulars",
            "lane": "Weekend story",
            "title": "Best combinations for a shared Friday pickup",
            "body": "This feed card is a connector for future shared favourites, story posts, and community challenges.",
            "meal": featured_items[2]["name"],
            "image": featured_items[2]["image"],
            "badge": "Shared tray",
        },
    ]
    return {
        "member_name": member_name,
        "stories": stories,
        "community_cards": [
            {"title": "Share meals", "text": "Prepared for future posting, tagging, and shared favourite collections."},
            {"title": "Share stories", "text": "Ready for food journals, pickup reflections, and short customer stories."},
            {"title": "Challenge boards", "text": "Supports future seasonal prompts such as staff picks or community tray themes."},
        ],
    }


def _save_support_history(history: list[dict[str, str]]) -> None:
    max_messages = max(2, int(current_app.config["SUPPORT_CHAT_MAX_HISTORY_MESSAGES"]))
    session[SUPPORT_CHAT_HISTORY_KEY] = history[-max_messages:]
    session.modified = True


def _support_snapshot() -> dict:
    from routes.orders import public_ordering_snapshot

    return public_ordering_snapshot()


def _support_fallback_reply(message: str) -> str:
    lowered = message.lower()
    snapshot = _support_snapshot()
    next_slot = snapshot.get("next_available_pickup")
    instant_queue = snapshot.get("instant_queue") or {}
    phone = current_app.config["RESTAURANT_PHONE"]

    if any(keyword in lowered for keyword in ("pickup", "schedule", "slot", "time")):
        if next_slot:
            return (
                f"The next scheduled pickup slot is {next_slot['date_label']} at {next_slot['time_label']}. "
                "Add dishes to the cart first, then continue to scheduled checkout to reserve that slot."
            )
        return "Scheduled pickup slots are not open right now. You can still browse the menu and try instant queue ordering instead."

    if any(keyword in lowered for keyword in ("instant", "queue", "ready", "wait")):
        return (
            f"Instant queue is currently showing {instant_queue.get('active_count', 0)} active order(s) "
            f"with an estimated wait of about {instant_queue.get('quoted_wait_minutes', 0)} minutes. "
            "Start from the menu, add dishes, then continue to instant checkout to receive a queue number."
        )

    if any(keyword in lowered for keyword in ("payment", "card", "apple pay", "paypal")):
        return (
            "Checkout supports simulated card, Apple Pay, and PayPal flows. "
            "A successful checkout stores the payment reference with the order and shows it again on the receipt."
        )

    if any(keyword in lowered for keyword in ("receipt", "pdf", "order history", "track", "order")):
        return (
            "You can track an order from the homepage using the order number, or open Orders to review history, live status, and PDF receipts."
        )

    if any(keyword in lowered for keyword in ("menu", "dish", "food", "cart", "add")):
        return (
            "Browse the menu first, choose either Instant Queue or Scheduled Pickup mode, and add dishes directly from the menu cards. "
            "The cart shows item counts, pickup fee, and the next checkout step."
        )

    if any(keyword in lowered for keyword in ("account", "login", "register")):
        user = current_user()
        if user:
            return f"You are currently signed in as {user['name']}. You can keep ordering, track receipts, or log out from the top-right header."
        return "You can use Login or Register from the header before ordering, but ordering and tracking also work without creating a full account."

    return (
        "I can help with menu browsing, cart updates, instant queue timing, scheduled pickup slots, checkout, receipts, and order tracking. "
        f"If you need staff help, call {phone}."
    )


def _extract_output_text(payload: dict) -> str:
    output_text = payload.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text.strip()

    fragments: list[str] = []
    for item in payload.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            text_value = content.get("text")
            if isinstance(text_value, str) and text_value.strip():
                fragments.append(text_value.strip())
    return "\n".join(fragment for fragment in fragments if fragment).strip()


def _support_system_prompt() -> str:
    snapshot = _support_snapshot()
    next_slot = snapshot.get("next_available_pickup")
    instant_queue = snapshot.get("instant_queue") or {}
    next_slot_text = (
        f"{next_slot['date_label']} at {next_slot['time_label']}"
        if next_slot
        else "unavailable right now"
    )
    return (
        "You are the MCQ Vietnamese Street Food website assistant. "
        "Answer concisely and practically, focusing only on this restaurant website and its supported flows. "
        "Help with menu browsing, cart updates, instant queue ordering, scheduled pickup, checkout, payment simulation, receipts, order tracking, and login/register basics. "
        "Do not invent policies or features that are not visible on the site. "
        "If the user needs staff help, advise calling the restaurant phone number. "
        f"Restaurant phone: {current_app.config['RESTAURANT_PHONE']}. "
        f"Instant queue snapshot: {instant_queue.get('active_count', 0)} active orders, "
        f"about {instant_queue.get('quoted_wait_minutes', 0)} minutes estimated wait, "
        f"counter label {instant_queue.get('counter_label', current_app.config['INSTANT_ORDERING_COUNTER_LABEL'])}. "
        f"Next scheduled pickup slot: {next_slot_text}."
    )


def _support_ai_reply(message: str, history: list[dict[str, str]]) -> tuple[str | None, str | None]:
    api_key = current_app.config.get("OPENAI_API_KEY", "").strip()
    if not api_key:
        return None, "missing_api_key"

    endpoint = current_app.config["OPENAI_API_BASE"].rstrip("/") + "/responses"
    max_messages = max(2, int(current_app.config["SUPPORT_CHAT_MAX_HISTORY_MESSAGES"]))
    recent_history = history[-max_messages:]
    input_items = [
        {
            "role": "system",
            "content": [{"type": "input_text", "text": _support_system_prompt()}],
        }
    ]
    for entry in recent_history:
        input_items.append(
            {
                "role": entry["role"],
                "content": [{"type": "input_text", "text": entry["content"]}],
            }
        )
    input_items.append(
        {
            "role": "user",
            "content": [{"type": "input_text", "text": message}],
        }
    )

    try:
        response = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": current_app.config["OPENAI_CHAT_MODEL"],
                "input": input_items,
                "max_output_tokens": 220,
            },
            timeout=float(current_app.config["SUPPORT_CHAT_TIMEOUT_SECONDS"]),
        )
        response.raise_for_status()
        payload = response.json()
        reply = _extract_output_text(payload)
        if not reply:
            return None, "empty_response"
        return reply, None
    except requests.RequestException as exc:
        LOGGER.warning("Support chat AI request failed: %s", exc)
        return None, "request_failed"


@user_bp.get("/profile")
def profile() -> str:
    orders = _active_customer_orders()
    membership = _membership_summary(orders)
    recent_orders = []
    for order in orders[:3]:
        recent_orders.append(
            {
                "order_number": order.order_number,
                "status": order.order_status,
                "fulfillment_label": "Instant counter pickup" if order.fulfillment_type == "instant" else "Scheduled pickup",
                "total_display": format_aud(order.total_cents),
                "href": f"/orders/{order.order_number}",
            }
        )
    return render_template(
        "user/profile.html",
        membership=membership,
        recent_orders=recent_orders,
        is_member=bool(current_user()),
    )


@user_bp.get("/favorites")
def favorites() -> str:
    return render_template(
        "user/favorites.html",
        membership=_membership_summary(_active_customer_orders()),
        **_saved_meals_context(),
    )


@user_bp.get("/community")
@user_bp.get("/shared-meals")
def shared_meals() -> str:
    return render_template(
        "user/community.html",
        membership=_membership_summary(_active_customer_orders()),
        **_community_context(),
    )


@user_bp.get("/support")
def support() -> str:
    return render_feature_page("support")


@user_bp.post("/api/support-chat")
def support_chat():
    body = request.get_json(silent=True) or {}
    message = body.get("message", "")
    if not isinstance(message, str) or not message.strip():
        return jsonify({"error": "message is required"}), 400

    cleaned_message = " ".join(message.strip().split())
    history = _support_history()
    ai_reply, ai_error = _support_ai_reply(cleaned_message, history)
    if ai_reply:
        reply = ai_reply
        mode = "ai"
    else:
        reply = _support_fallback_reply(cleaned_message)
        mode = "fallback"

    history.extend(
        [
            {"role": "user", "content": cleaned_message},
            {"role": "assistant", "content": reply},
        ]
    )
    _save_support_history(history)

    return jsonify(
        {
            "reply": reply,
            "mode": mode,
            "ai_enabled": bool(current_app.config.get("OPENAI_API_KEY")),
            "fallback_reason": ai_error,
            "history_count": len(_support_history()),
        }
    )
