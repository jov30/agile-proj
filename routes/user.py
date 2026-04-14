from __future__ import annotations

import logging

import requests
from flask import Blueprint, current_app, jsonify, request, session

from routes.auth import current_user
from routes.helpers import render_feature_page


user_bp = Blueprint("user", __name__)
SUPPORT_CHAT_HISTORY_KEY = "support_chat_history"
LOGGER = logging.getLogger(__name__)


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
    return render_feature_page("profile")


@user_bp.get("/favorites")
def favorites() -> str:
    return render_feature_page("favorites")


@user_bp.get("/shared-meals")
def shared_meals() -> str:
    return render_feature_page("shared_meals")


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
