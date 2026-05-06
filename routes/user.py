from __future__ import annotations

import hashlib
import logging
import secrets
from collections import Counter
from pathlib import Path

import requests
from flask import Blueprint, Response, current_app, jsonify, redirect, render_template, request, session, url_for

from menu_catalog import format_aud, load_enriched_menu
from models import CommunityComment, CommunityCommentVote, CommunityPost, CommunityReaction, CommunitySave, Order, User, db
from routes.api_errors import api_error_response
from routes.auth import current_user
from routes.helpers import render_feature_page
from datetime import date as date_type
from routes.auth import SESSION_USER_KEY


user_bp = Blueprint("user", __name__)
SUPPORT_CHAT_HISTORY_KEY = "support_chat_history"
COMMUNITY_IDENTITY_KEY = "community_identity_key"
LOGGER = logging.getLogger(__name__)
_ROOT_DIR = Path(__file__).resolve().parent.parent
_REACTION_TYPES = ("love", "want_to_try", "saved_for_later")
_COMMENT_FOCUS = ("taste", "portion_size", "spice_level", "drink_pairing", "pickup_timing")
_POST_TYPES = ("meal_review", "usual_combo", "pickup_tip")
_COMMENT_VOTE_TYPES = ("helpful", "tried_this", "good_tip")

_MEMBERSHIP_TIERS = (
    {"name": "Lantern Starter", "min_points": 0, "accent": "amber"},
    {"name": "Market Regular", "min_points": 250, "accent": "teal"},
    {"name": "Golden Chopsticks", "min_points": 600, "accent": "gold"},
    {"name": "Distinction Member", "min_points": 1000, "accent": "plum"},
)
_VOUCHER_REDEEM_POINTS = 1000
_VOUCHER_REDEEM_VALUE_CENTS = 1000
_CODE39_MAP = {
    "0": "nnnwwnwnn",
    "1": "wnnwnnnnw",
    "2": "nnwwnnnnw",
    "3": "wnwwnnnnn",
    "4": "nnnwwnnnw",
    "5": "wnnwwnnnn",
    "6": "nnwwwnnnn",
    "7": "nnnwnnwnw",
    "8": "wnnwnnwnn",
    "9": "nnwwnnwnn",
    "A": "wnnnnwnnw",
    "B": "nnwnnwnnw",
    "C": "wnwnnwnnn",
    "D": "nnnnwwnnw",
    "E": "wnnnwwnnn",
    "F": "nnwnwwnnn",
    "G": "nnnnnwwnw",
    "H": "wnnnnwwnn",
    "I": "nnwnnwwnn",
    "J": "nnnnwwwnn",
    "K": "wnnnnnnww",
    "L": "nnwnnnnww",
    "M": "wnwnnnnwn",
    "N": "nnnnwnnww",
    "O": "wnnnwnnwn",
    "P": "nnwnwnnwn",
    "Q": "nnnnnnwww",
    "R": "wnnnnnwwn",
    "S": "nnwnnnwwn",
    "T": "nnnnwnwwn",
    "U": "wwnnnnnnw",
    "V": "nwwnnnnnw",
    "W": "wwwnnnnnn",
    "X": "nwnnwnnnw",
    "Y": "wwnnwnnnn",
    "Z": "nwwnwnnnn",
    "-": "nwnnnnwnw",
    ".": "wwnnnnwnn",
    " ": "nwwnnnwnn",
    "$": "nwnwnwnnn",
    "/": "nwnwnnnwn",
    "+": "nwnnnwnwn",
    "%": "nnnwnwnwn",
    "*": "nwnnwnwnn",
}

def _sync_user_community_stats(email: str) -> None:
    """Recount and persist community stats for a logged-in user."""
    db_user = User.query.filter_by(email=email).first()
    if not db_user:
        return
    identity_key = f"user:{email.lower()}"
    posts = CommunityPost.query.filter_by(identity_key=identity_key).all()
    db_user.posts_shared = len(posts)
    db_user.likes_received = sum(len(post.reactions) for post in posts)
    dish_counts: Counter[str] = Counter(post.meal_name for post in posts)
    if dish_counts:
        db_user.most_shared_dish = dish_counts.most_common(1)[0][0]
    db.session.commit()

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


def _community_identity() -> tuple[str, str, str | None]:
    user = current_user()
    if user:
        return f"user:{user['email'].lower()}", user["name"], user["email"].lower()
    identity = session.get(COMMUNITY_IDENTITY_KEY)
    if not isinstance(identity, str) or not identity:
        identity = f"guest:{secrets.token_hex(12)}"
        session[COMMUNITY_IDENTITY_KEY] = identity
        session.modified = True
    return identity, "Guest member", None


def _clean_text(value: str | None, *, limit: int, default: str = "") -> str:
    if not isinstance(value, str):
        return default
    return " ".join(value.strip().split())[:limit]


def _community_post_image(post: CommunityPost, menu_lookup: dict[str, dict]) -> str:
    if post.photo_url:
        return post.photo_url
    if post.order and post.order.line_items:
        first_item = menu_lookup.get(post.order.line_items[0].item_id)
        if first_item:
            return first_item["image"]
    lowered = post.meal_name.lower()
    for item in menu_lookup.values():
        if item["name"].lower() in lowered or lowered in item["name"].lower():
            return item["image"]
    return "images/inspiration/street-food-life.jpg"


def _share_order_context(order_number: str | None, menu_lookup: dict[str, dict]) -> dict | None:
    if not order_number:
        return None
    order = Order.query.filter_by(order_number=order_number.strip()).first()
    if not order:
        return None
    meal_items = [f"{line.quantity}x {line.item_name}" for line in order.line_items]
    image = None
    if order.line_items:
        image = menu_lookup.get(order.line_items[0].item_id, {}).get("image")
    return {
        "order_number": order.order_number,
        "meal_name": order.line_items[0].item_name if order.line_items else f"Order {order.order_number}",
        "meal_items": ", ".join(meal_items),
        "total_display": format_aud(order.total_cents),
        "pickup_type": "Instant counter pickup" if order.fulfillment_type == "instant" else "Scheduled pickup",
        "caption": _share_prompt_caption(request.args.get("prompt"), order, meal_items),
        "image": image or "images/inspiration/street-food-life.jpg",
    }


def _share_prompt_caption(prompt: str | None, order: Order, meal_items: list[str]) -> str:
    meal_text = ", ".join(meal_items[:3])
    prompt_key = (prompt or "").strip().lower()
    if prompt_key == "best_part":
        return f"The best part of my {order.order_number} pickup was {meal_text}."
    if prompt_key == "tip":
        return f"Tip for the next customer ordering {meal_text}: "
    if prompt_key == "pairing":
        return f"I would pair {meal_text} with "
    return f"Sharing my {order.order_number} pickup: {meal_text}."


def _remix_context(post_id: str | None) -> dict | None:
    if not post_id:
        return None
    try:
        post = CommunityPost.query.get(int(post_id))
    except (TypeError, ValueError):
        return None
    if not post:
        return None
    return {
        "post_id": post.id,
        "meal_name": post.meal_name,
        "meal_items": post.meal_items or post.meal_name,
        "caption": f"Remixing {post.author_name}'s combo: {post.meal_items or post.meal_name}. I would change ",
        "tip": post.tip or "",
        "spice_level": post.spice_level or "",
        "portion_note": post.portion_note or "",
        "drink_pairing": post.drink_pairing or "",
        "pickup_timing_note": post.pickup_timing_note or "",
    }


def _serialize_community_post(post: CommunityPost, menu_lookup: dict[str, dict], identity_key: str) -> dict:
    reaction_counts: Counter[str] = Counter(reaction.reaction_type for reaction in post.reactions)
    viewer_reactions = {
        reaction.reaction_type
        for reaction in post.reactions
        if reaction.identity_key == identity_key
    }
    viewer_saved = any(save.identity_key == identity_key for save in post.saves)
    helpful_notes = [
        {
            "id": comment.id,
            "focus": comment.focus.replace("_", " ").title(),
            "body": comment.body,
            "author": comment.author_name,
            "helpful_count": sum(1 for vote in comment.votes if vote.vote_type == "helpful"),
            "tried_count": sum(1 for vote in comment.votes if vote.vote_type == "tried_this"),
            "good_tip_count": sum(1 for vote in comment.votes if vote.vote_type == "good_tip"),
        }
        for comment in post.comments[-3:]
    ]
    return {
        "id": post.id,
        "author": post.author_name,
        "type_label": post.post_type.replace("_", " ").title(),
        "meal": post.meal_name,
        "meal_items": post.meal_items,
        "caption": post.caption,
        "tip": post.tip,
        "image": _community_post_image(post, menu_lookup),
        "order_number": post.order_number,
        "order_total_display": format_aud(post.order_total_cents) if post.order_total_cents else None,
        "pickup_type": post.pickup_type,
        "spice_level": post.spice_level,
        "portion_note": post.portion_note,
        "drink_pairing": post.drink_pairing,
        "pickup_timing_note": post.pickup_timing_note,
        "created_label": post.created_at.strftime("%d %b %Y"),
        "love_count": reaction_counts["love"],
        "want_count": reaction_counts["want_to_try"],
        "saved_reaction_count": reaction_counts["saved_for_later"],
        "like_count": len(post.reactions),
        "comment_count": len(post.comments),
        "save_count": len(post.saves),
        "viewer_reactions": viewer_reactions,
        "viewer_saved": viewer_saved,
        "comments": helpful_notes,
    }


def _community_stats(identity_key: str, posts: list[CommunityPost], orders: list[Order]) -> dict:
    user = current_user()

    if user:
        db_user = User.query.filter_by(email=user["email"].lower()).first()
        if db_user:
            badges = ["Lantern Member"]
            if db_user.posts_shared >= 3:
                badges.append("Top Sharer")
            if db_user.most_shared_dish and "pho" in db_user.most_shared_dish.lower():
                badges.append("Pho Lover")
            if db_user.likes_received >= 5:
                badges.append("Community Pick")
            return {
                "posts_shared": db_user.posts_shared,
                "likes_received": db_user.likes_received,
                "most_shared_dish": db_user.most_shared_dish or "No shared dishes yet",
                "favorite_combo": db_user.favorite_combo or "Place an order to build a combo",
                "badges": badges,
            }

    # Guest fallback — derive from live data
    own_posts = [post for post in posts if post.identity_key == identity_key]
    likes_received = sum(len(post.reactions) for post in own_posts)
    shared_dishes: Counter[str] = Counter(post.meal_name for post in own_posts)
    ordered_combos: Counter[str] = Counter()
    for order in orders:
        combo = " + ".join(line.item_name for line in order.line_items[:2])
        if combo:
            ordered_combos[combo] += 1
    badges = ["Lantern Member"]
    if len(own_posts) >= 3:
        badges.append("Top Sharer")
    if any("pho" in dish.lower() for dish in shared_dishes):
        badges.append("Pho Lover")
    if likes_received >= 5:
        badges.append("Community Pick")
    return {
        "posts_shared": len(own_posts),
        "likes_received": likes_received,
        "most_shared_dish": shared_dishes.most_common(1)[0][0] if shared_dishes else "No shared dishes yet",
        "favorite_combo": ordered_combos.most_common(1)[0][0] if ordered_combos else "Place an order to build a combo",
        "badges": badges,
    }


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


def _code39_payload(value: str) -> str:
    cleaned = "".join(char for char in value.upper() if char in _CODE39_MAP and char != "*")
    return f"*{cleaned or 'MCQ-MEMBER'}*"


def _membership_barcode_svg(value: str) -> str:
    payload = _code39_payload(value)
    narrow = 3
    wide = 7
    quiet = 24
    bar_height = 88
    text_y = bar_height + 24
    x = quiet
    bars: list[str] = []

    for index, char in enumerate(payload):
        pattern = _CODE39_MAP[char]
        is_bar = True
        for token in pattern:
            width = wide if token == "w" else narrow
            if is_bar:
                bars.append(
                    f'<rect x="{x}" y="10" width="{width}" height="{bar_height}" rx="1" fill="#1a120e" />'
                )
            x += width
            is_bar = not is_bar
        if index < len(payload) - 1:
            x += narrow

    total_width = x + quiet
    label = value.upper()
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{total_width}" height="{bar_height + 34}" '
        f'viewBox="0 0 {total_width} {bar_height + 34}" role="img" aria-label="Membership barcode for {label}">'
        f'<rect width="{total_width}" height="{bar_height + 34}" rx="16" fill="#fffaf5"/>'
        + "".join(bars)
        + f'<text x="{total_width / 2}" y="{text_y}" text-anchor="middle" '
        f'font-family="Menlo, Monaco, monospace" font-size="16" letter-spacing="3" fill="#1a120e">{label}</text>'
        + "</svg>"
    )


def _membership_summary(orders: list[Order]) -> dict:
    user = current_user()
    seed_source = user["email"] if user else "guest-member-preview"

    # Points: stored on User for logged-in accounts, derived from orders for guests
    if user:
        db_user = User.query.filter_by(email=user["email"]).first()
        points_balance = db_user.points_balance if db_user else 0
    else:
        total_spend_cents = sum(order.total_cents for order in orders)
        points_balance = total_spend_cents // 100

    total_spend_cents = sum(order.total_cents for order in orders)
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
    available_vouchers = points_balance // _VOUCHER_REDEEM_POINTS
    voucher_redeem_value_cents = available_vouchers * _VOUCHER_REDEEM_VALUE_CENTS
    voucher_cycle_points = points_balance % _VOUCHER_REDEEM_POINTS
    voucher_progress_percent = round((voucher_cycle_points / _VOUCHER_REDEEM_POINTS) * 100) if points_balance else 0
    if available_vouchers and voucher_cycle_points == 0:
        voucher_progress_percent = 100
    return {
        "member_name": user["name"] if user else "Guest preview member",
        "member_email": user["email"] if user else "Join to save your points ledger",
        "member_code": _member_code(seed_source),
        "points_balance": points_balance,
        "points_display": f"{points_balance:,}",
        "points_rule_display": "$1 spent = 1 point",
        "total_spend_display": format_aud(total_spend_cents),
        "total_orders": total_orders,
        "instant_orders": instant_orders,
        "scheduled_orders": scheduled_orders,
        "current_tier": current_tier,
        "next_tier": next_tier,
        "progress_percent": progress_percent,
        "points_to_next": 0 if not next_tier else max(0, next_tier["min_points"] - points_balance),
        "voucher_rule_points": _VOUCHER_REDEEM_POINTS,
        "voucher_rule_display": f"{_VOUCHER_REDEEM_POINTS} points = {format_aud(_VOUCHER_REDEEM_VALUE_CENTS)} voucher",
        "available_vouchers": available_vouchers,
        "voucher_value_display": format_aud(voucher_redeem_value_cents),
        "voucher_unit_display": format_aud(_VOUCHER_REDEEM_VALUE_CENTS),
        "points_to_next_voucher": (
            _VOUCHER_REDEEM_POINTS if available_vouchers and voucher_cycle_points == 0
            else max(0, _VOUCHER_REDEEM_POINTS - voucher_cycle_points)
        ),
        "voucher_progress_percent": voucher_progress_percent,
        "preview_note": (
            "This loyalty card is a polished UI scaffold. A future membership service can plug a real points ledger into the same layout."
        ),
        "benefits": [
            {"title": "Member-only point wallet", "text": "Track dine-and-pickup spend in one place and convert every dollar into rewards-ready points."},
            {"title": "Voucher redemption ladder", "text": "Every 1000 points unlocks a $10 redeemable voucher inside the digital membership wallet."},
            {"title": "Community identity", "text": "Use the same member profile to share meal boards, street-food stories, and seasonal picks with other customers."},
        ],
    }


def _mission_progress(identity_key: str, posts: list[CommunityPost], orders: list[Order]) -> list[dict]:
    own_posts = [post for post in posts if post.identity_key == identity_key]
    own_comments = CommunityComment.query.filter_by(identity_key=identity_key).count()
    own_saves = CommunitySave.query.filter_by(identity_key=identity_key).count()
    pho_posts = sum(1 for post in own_posts if "pho" in post.meal_name.lower() or "pho" in (post.meal_items or "").lower())
    tip_posts = sum(1 for post in own_posts if post.tip or post.spice_level or post.pickup_timing_note)
    return [
        {"title": "Share a pho combo", "progress": min(pho_posts, 1), "target": 1},
        {"title": "Post a useful food tip", "progress": min(tip_posts, 1), "target": 1},
        {"title": "Save 3 customer meal ideas", "progress": min(own_saves, 3), "target": 3},
        {"title": "Comment on 2 pickup or taste tips", "progress": min(own_comments, 2), "target": 2},
        {"title": "Share from an order receipt", "progress": min(sum(1 for post in own_posts if post.order_number), 1), "target": 1},
    ]


def _featured_tip(posts: list[CommunityPost]) -> dict | None:
    comments = [comment for post in posts for comment in post.comments]
    if not comments:
        return None
    best = max(comments, key=lambda comment: (len(comment.votes), comment.created_at))
    if not best.votes:
        return None
    return {
        "focus": best.focus.replace("_", " ").title(),
        "body": best.body,
        "author": best.author_name,
        "votes": len(best.votes),
        "post_id": best.post_id,
    }


def _all_community_posts() -> list[CommunityPost]:
    return (
        CommunityPost.query.order_by(CommunityPost.created_at.desc(), CommunityPost.id.desc())
        .limit(60)
        .all()
    )


def _saved_meals_context() -> dict:
    identity_key, _name, _email = _community_identity()
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
        {"title": "Shareable meal board", "text": "Saved community posts and pickup ideas collected from other customers.", "accent": "teal"},
        {"title": "Weekend comfort stack", "text": "A saved lane for rich bowls, hot plates, and dessert add-ons.", "accent": "plum"},
    ]
    saved_posts = (
        CommunityPost.query.join(CommunitySave)
        .filter(CommunitySave.identity_key == identity_key)
        .order_by(CommunitySave.created_at.desc())
        .limit(6)
        .all()
    )
    return {
        "saved_items": saved_items[:6],
        "saved_community_posts": [
            _serialize_community_post(post, menu_lookup, identity_key)
            for post in saved_posts
        ],
        "collections": collections,
    }


def _community_context() -> dict:
    identity_key, member_name, _email = _community_identity()
    menu_lookup = _menu_item_lookup()
    raw_posts = _all_community_posts()
    posts = [_serialize_community_post(post, menu_lookup, identity_key) for post in raw_posts]
    orders = _active_customer_orders()
    shared_order = _share_order_context(request.args.get("order"), menu_lookup)
    remix_post = _remix_context(request.args.get("remix"))
    today = raw_posts[0].created_at.date() if raw_posts else None
    today_posts = [post for post in posts if today and post["created_label"] == today.strftime("%d %b %Y")][:4]
    most_liked = sorted(posts, key=lambda post: (post["like_count"], post["comment_count"]), reverse=True)[:4]
    quick_lunch = [
        post for post in posts
        if any(keyword in f"{post['meal']} {post['caption']}".lower() for keyword in ("banh mi", "rice", "roll", "quick", "lunch"))
    ][:4]
    pickup_combos = [post for post in posts if post["order_number"] or "combo" in post["caption"].lower()][:4]
    return {
        "member_name": member_name,
        "posts": posts,
        "shared_order": shared_order,
        "remix_post": remix_post,
        "recent_orders": [
            {
                "order_number": order.order_number,
                "label": f"{order.order_number} · {format_aud(order.total_cents)}",
                "href": url_for("user.shared_meals", order=order.order_number),
            }
            for order in orders[:5]
        ],
        "community_stats": _community_stats(identity_key, raw_posts, orders),
        "missions": _mission_progress(identity_key, raw_posts, orders),
        "featured_tip": _featured_tip(raw_posts),
        "boards": [
            {"title": "Today's shared meals", "items": today_posts},
            {"title": "Most liked this week", "items": most_liked},
            {"title": "Quick lunch ideas", "items": quick_lunch},
            {"title": "Best pickup combos", "items": pickup_combos},
        ],
        "challenges": [
            "Share your best pho combo this week",
            "Most liked meal post gets featured",
            "Late-night pickup favorites",
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


@user_bp.get("/membership")
@user_bp.get("/profile")
def profile() -> str:
    orders = _active_customer_orders()
    membership = _membership_summary(orders)
    identity_key, _name, _email = _community_identity()
    community_posts = _all_community_posts()
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
        community_stats=_community_stats(identity_key, community_posts, orders),
        recent_orders=recent_orders,
        is_member=bool(current_user()),
    )

_DIETARY_OPTIONS = (
    "No restrictions",
    "Vegetarian",
    "Vegan",
    "Gluten-free",
    "Dairy-free",
    "Halal",
    "No pork",
    "No shellfish",
)
_MIN_AGE_YEARS = 13
_MAX_AGE_YEARS = 120
def _validate_settings_form(form: dict) -> list[str]:
    errors: list[str] = []

    name = form.get("name", "").strip()
    if len(name) < 2:
        errors.append("Full name must be at least 2 characters.")

    username = form.get("username", "").strip()
    if username:
        if len(username) < 3:
            errors.append("Username must be at least 3 characters.")
        elif not username.replace("_", "").replace(".", "").replace("-", "").isalnum():
            errors.append("Username may only contain letters, numbers, dots, hyphens, and underscores.")

    phone = form.get("phone", "").strip()
    if phone:
        digits = [c for c in phone if c.isdigit()]
        if len(digits) < 8:
            errors.append("Enter a valid phone number.")

    dob_raw = form.get("date_of_birth", "").strip()
    if dob_raw:
        try:
            dob = date_type.fromisoformat(dob_raw)
            today = date_type.today()
            age = today.year - dob.year - ((today.month, today.day) < (dob.month, dob.day))
            if age < _MIN_AGE_YEARS:
                errors.append(f"You must be at least {_MIN_AGE_YEARS} years old.")
            elif age > _MAX_AGE_YEARS:
                errors.append("Enter a valid date of birth.")
        except ValueError:
            errors.append("Enter a valid date of birth (YYYY-MM-DD).")

    pickup_mode = form.get("default_pickup_mode", "scheduled")
    if pickup_mode not in ("instant", "scheduled"):
        errors.append("Choose a valid default pickup mode.")

    return errors


@user_bp.get("/profile/settings")
def profile_settings() -> str:
    user = current_user()
    if not user:
        return redirect(url_for("auth.login", next="/profile/settings"))

    db_user = User.query.filter_by(email=user["email"].lower()).first_or_404()
    form_data = {
        "name": db_user.name,
        "username": db_user.username or "",
        "phone": db_user.phone or "",
        "date_of_birth": db_user.date_of_birth.isoformat() if db_user.date_of_birth else "",
        "dietary_preferences": db_user.dietary_preferences or "",
        "default_pickup_mode": db_user.default_pickup_mode or "scheduled",
        "notification_email": db_user.notification_email,
        "notification_sms": db_user.notification_sms,
        "marketing_opt_in": db_user.marketing_opt_in,
    }
    return render_template(
        "user/settings.html",
        form_data=form_data,
        errors=[],
        saved=False,
        dietary_options=_DIETARY_OPTIONS,
        membership=_membership_summary(_active_customer_orders()),
    )


@user_bp.post("/profile/settings")
def save_profile_settings() -> str:
    user = current_user()
    if not user:
        return redirect(url_for("auth.login", next="/profile/settings"))

    db_user = User.query.filter_by(email=user["email"].lower()).first_or_404()

    form = {
        "name": request.form.get("name", "").strip(),
        "username": request.form.get("username", "").strip().lower(),
        "phone": request.form.get("phone", "").strip(),
        "date_of_birth": request.form.get("date_of_birth", "").strip(),
        "dietary_preferences": request.form.get("dietary_preferences", "").strip(),
        "default_pickup_mode": request.form.get("default_pickup_mode", "scheduled"),
        "notification_email": request.form.get("notification_email") == "on",
        "notification_sms": request.form.get("notification_sms") == "on",
        "marketing_opt_in": request.form.get("marketing_opt_in") == "on",
    }

    errors = _validate_settings_form(form)

    # Username uniqueness check (skip if unchanged)
    if not errors and form["username"] and form["username"] != (db_user.username or ""):
        clash = User.query.filter_by(username=form["username"]).first()
        if clash and clash.id != db_user.id:
            errors.append("That username is already taken.")

    if errors:
        return render_template(
            "user/settings.html",
            form_data=form,
            errors=errors,
            saved=False,
            dietary_options=_DIETARY_OPTIONS,
            membership=_membership_summary(_active_customer_orders()),
        ), 400

    # Persist
    db_user.name = form["name"]
    db_user.username = form["username"] or None
    db_user.phone = form["phone"] or None
    db_user.date_of_birth = (
        date_type.fromisoformat(form["date_of_birth"]) if form["date_of_birth"] else None
    )
    db_user.dietary_preferences = form["dietary_preferences"] or None
    db_user.default_pickup_mode = form["default_pickup_mode"]
    db_user.notification_email = form["notification_email"]
    db_user.notification_sms = form["notification_sms"]
    db_user.marketing_opt_in = form["marketing_opt_in"]
    db.session.commit()

    # Refresh session name if it changed
    if form["name"] != user["name"]:
        session[SESSION_USER_KEY] = {**session[SESSION_USER_KEY], "name": form["name"]}
        session.modified = True

    return render_template(
        "user/settings.html",
        form_data={**form, "date_of_birth": db_user.date_of_birth.isoformat() if db_user.date_of_birth else ""},
        errors=[],
        saved=True,
        dietary_options=_DIETARY_OPTIONS,
        membership=_membership_summary(_active_customer_orders()),
    )

@user_bp.get("/membership/barcode.svg")
def membership_barcode() -> Response:
    membership = _membership_summary(_active_customer_orders())
    return Response(
        _membership_barcode_svg(membership["member_code"]),
        mimetype="image/svg+xml",
        headers={"Cache-Control": "no-store"},
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


@user_bp.post("/community/posts")
def create_community_post():
    identity_key, default_name, email = _community_identity()
    order_number = _clean_text(request.form.get("order_number"), limit=32)
    order = Order.query.filter_by(order_number=order_number).first() if order_number else None
    post_type = request.form.get("post_type", "meal_review")
    if post_type not in _POST_TYPES:
        post_type = "meal_review"

    author_name = _clean_text(request.form.get("author_name"), limit=120, default=default_name)
    meal_name = _clean_text(request.form.get("meal_name"), limit=255)
    caption = _clean_text(request.form.get("caption"), limit=900)
    if order:
        meal_items = ", ".join(f"{line.quantity}x {line.item_name}" for line in order.line_items)
        meal_name = meal_name or (order.line_items[0].item_name if order.line_items else f"Order {order.order_number}")
    else:
        meal_items = _clean_text(request.form.get("meal_items"), limit=500)

    if not meal_name or not caption:
        session["community_error"] = "Add a meal name and a short caption before sharing."
        session.modified = True
        return redirect(url_for("user.shared_meals", order=order_number) if order_number else url_for("user.shared_meals"))

    post = CommunityPost(
        author_name=author_name,
        author_email=email,
        identity_key=identity_key,
        post_type=post_type,
        meal_name=meal_name,
        meal_items=meal_items,
        caption=caption,
        tip=_clean_text(request.form.get("tip"), limit=255),
        photo_url=_clean_text(request.form.get("photo_url"), limit=500),
        order_number=order.order_number if order else None,
        order_total_cents=order.total_cents if order else None,
        pickup_type=(
            "Instant counter pickup" if order and order.fulfillment_type == "instant"
            else "Scheduled pickup" if order
            else _clean_text(request.form.get("pickup_type"), limit=40)
        ),
        spice_level=_clean_text(request.form.get("spice_level"), limit=40),
        portion_note=_clean_text(request.form.get("portion_note"), limit=120),
        drink_pairing=_clean_text(request.form.get("drink_pairing"), limit=120),
        pickup_timing_note=_clean_text(request.form.get("pickup_timing_note"), limit=160),
    )
    db.session.add(post)
    db.session.commit()
    _identity, _name, email = _community_identity()
    if email:
        _sync_user_community_stats(email)
    session["community_notice"] = "Your meal post is now live in the community feed."
    session.modified = True
    return redirect(url_for("user.shared_meals", _anchor=f"post-{post.id}"))


@user_bp.post("/community/posts/<int:post_id>/react")
def react_to_community_post(post_id: int):
    post = CommunityPost.query.get_or_404(post_id)
    reaction_type = request.form.get("reaction_type", "love")
    if reaction_type not in _REACTION_TYPES:
        reaction_type = "love"
    identity_key, author_name, _email = _community_identity()
    existing = CommunityReaction.query.filter_by(
        post_id=post.id,
        identity_key=identity_key,
        reaction_type=reaction_type,
    ).first()
    if existing:
        db.session.delete(existing)
    else:
        db.session.add(
            CommunityReaction(
                post_id=post.id,
                identity_key=identity_key,
                author_name=author_name,
                reaction_type=reaction_type,
            )
        )
    db.session.commit()
    if post.author_email:
        _sync_user_community_stats(post.author_email)
    return redirect(url_for("user.shared_meals", _anchor=f"post-{post.id}"))


@user_bp.post("/community/posts/<int:post_id>/comments")
def comment_on_community_post(post_id: int):
    post = CommunityPost.query.get_or_404(post_id)
    identity_key, author_name, _email = _community_identity()
    focus = request.form.get("focus", "taste")
    if focus not in _COMMENT_FOCUS:
        focus = "taste"
    body = _clean_text(request.form.get("body"), limit=500)
    if body:
        db.session.add(
            CommunityComment(
                post_id=post.id,
                identity_key=identity_key,
                author_name=author_name,
                focus=focus,
                body=body,
            )
        )
        db.session.commit()
    return redirect(url_for("user.shared_meals", _anchor=f"post-{post.id}"))


@user_bp.post("/community/posts/<int:post_id>/save")
def save_community_post(post_id: int):
    post = CommunityPost.query.get_or_404(post_id)
    identity_key, author_name, _email = _community_identity()
    existing = CommunitySave.query.filter_by(post_id=post.id, identity_key=identity_key).first()
    if existing:
        db.session.delete(existing)
    else:
        db.session.add(
            CommunitySave(
                post_id=post.id,
                identity_key=identity_key,
                author_name=author_name,
                save_type="favorite_board",
            )
        )
    db.session.commit()
    return redirect(url_for("user.shared_meals", _anchor=f"post-{post.id}"))


@user_bp.post("/community/comments/<int:comment_id>/vote")
def vote_community_comment(comment_id: int):
    comment = CommunityComment.query.get_or_404(comment_id)
    vote_type = request.form.get("vote_type", "helpful")
    if vote_type not in _COMMENT_VOTE_TYPES:
        vote_type = "helpful"
    identity_key, author_name, _email = _community_identity()
    existing = CommunityCommentVote.query.filter_by(
        comment_id=comment.id,
        identity_key=identity_key,
        vote_type=vote_type,
    ).first()
    if existing:
        db.session.delete(existing)
    else:
        db.session.add(
            CommunityCommentVote(
                comment_id=comment.id,
                identity_key=identity_key,
                author_name=author_name,
                vote_type=vote_type,
            )
        )
    db.session.commit()
    return redirect(url_for("user.shared_meals", _anchor=f"post-{comment.post_id}"))


@user_bp.get("/support")
def support() -> str:
    return render_feature_page("support")


@user_bp.post("/api/support-chat")
def support_chat():
    body = request.get_json(silent=True) or {}
    message = body.get("message", "")
    if not isinstance(message, str) or not message.strip():
        return api_error_response("message is required", status=400, code="missing_message")

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
