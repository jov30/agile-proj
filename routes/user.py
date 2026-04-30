from __future__ import annotations

from flask import Blueprint, jsonify, request, session

from extensions import db
from models import FavoriteMeal, SharedMeal, User
from routes.helpers import render_feature_page


user_bp = Blueprint("user", __name__)
SESSION_USER_ID_KEY = "user_id"


def _current_user() -> User | None:
    user_id = session.get(SESSION_USER_ID_KEY)
    if not isinstance(user_id, int):
        return None
    return User.query.get(user_id)


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


@user_bp.get("/api/user/profile")
def profile_api():
    user = _current_user()
    if not user:
        return jsonify({"error": "authentication required"}), 401
    return jsonify({"id": user.id, "username": user.username, "email": user.email})


@user_bp.patch("/api/user/profile")
def profile_update_api():
    user = _current_user()
    if not user:
        return jsonify({"error": "authentication required"}), 401
    body = request.get_json(silent=True) or {}
    username = str(body.get("username", user.username)).strip()
    email = str(body.get("email", user.email)).strip().lower()
    if not username or not email:
        return jsonify({"error": "username and email are required"}), 400

    existing = User.query.filter(User.id != user.id, (User.username == username) | (User.email == email)).first()
    if existing:
        return jsonify({"error": "username or email already in use"}), 409

    user.username = username
    user.email = email
    db.session.commit()
    return jsonify({"id": user.id, "username": user.username, "email": user.email})


@user_bp.get("/api/user/favorites")
def favorites_api():
    user = _current_user()
    if not user:
        return jsonify({"error": "authentication required"}), 401
    rows = FavoriteMeal.query.filter_by(user_id=user.id).order_by(FavoriteMeal.created_at.desc()).all()
    return jsonify(
        {
            "favorites": [
                {"id": row.id, "item_id": row.item_id, "created_at": row.created_at.isoformat()} for row in rows
            ]
        }
    )


@user_bp.post("/api/user/favorites")
def favorite_add_api():
    user = _current_user()
    if not user:
        return jsonify({"error": "authentication required"}), 401
    body = request.get_json(silent=True) or {}
    item_id = str(body.get("item_id", "")).strip()
    if not item_id:
        return jsonify({"error": "item_id is required"}), 400
    existing = FavoriteMeal.query.filter_by(user_id=user.id, item_id=item_id).first()
    if existing:
        return jsonify({"id": existing.id, "item_id": existing.item_id}), 200
    row = FavoriteMeal(user_id=user.id, item_id=item_id)
    db.session.add(row)
    db.session.commit()
    return jsonify({"id": row.id, "item_id": row.item_id}), 201


@user_bp.delete("/api/user/favorites/<item_id>")
def favorite_remove_api(item_id: str):
    user = _current_user()
    if not user:
        return jsonify({"error": "authentication required"}), 401
    row = FavoriteMeal.query.filter_by(user_id=user.id, item_id=item_id).first()
    if not row:
        return jsonify({"ok": True})
    db.session.delete(row)
    db.session.commit()
    return jsonify({"ok": True})


@user_bp.get("/api/user/shared-meals")
def shared_meals_api():
    rows = (
        db.session.query(SharedMeal, User.username)
        .join(User, SharedMeal.user_id == User.id)
        .order_by(SharedMeal.created_at.desc())
        .limit(100)
        .all()
    )
    return jsonify(
        {
            "shared_meals": [
                {
                    "id": meal.id,
                    "item_id": meal.item_id,
                    "caption": meal.caption,
                    "author": username,
                    "created_at": meal.created_at.isoformat(),
                }
                for meal, username in rows
            ]
        }
    )


@user_bp.post("/api/user/shared-meals")
def shared_meal_add_api():
    user = _current_user()
    if not user:
        return jsonify({"error": "authentication required"}), 401
    body = request.get_json(silent=True) or {}
    item_id = str(body.get("item_id", "")).strip()
    caption = str(body.get("caption", "")).strip()
    if not item_id:
        return jsonify({"error": "item_id is required"}), 400
    row = SharedMeal(user_id=user.id, item_id=item_id, caption=caption[:280])
    db.session.add(row)
    db.session.commit()
    return jsonify({"id": row.id, "item_id": row.item_id, "caption": row.caption}), 201
