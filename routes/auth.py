from __future__ import annotations

from flask import Blueprint, jsonify, request, session

from extensions import db
from models import User
from routes.helpers import render_feature_page
from werkzeug.security import check_password_hash, generate_password_hash


auth_bp = Blueprint("auth", __name__)
SESSION_USER_ID_KEY = "user_id"


def _json_body() -> dict:
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


@auth_bp.get("/login")
def login() -> str:
    return render_feature_page("login")


@auth_bp.get("/register")
def register() -> str:
    return render_feature_page("register")


@auth_bp.post("/api/auth/register")
def register_user():
    body = _json_body()
    username = str(body.get("username", "")).strip()
    email = str(body.get("email", "")).strip().lower()
    password = str(body.get("password", ""))

    if not username or not email or not password:
        return jsonify({"error": "username, email and password are required"}), 400
    if len(password) < 8:
        return jsonify({"error": "password must be at least 8 characters"}), 400
    if User.query.filter((User.username == username) | (User.email == email)).first():
        return jsonify({"error": "username or email already in use"}), 409

    user = User(username=username, email=email, password_hash=generate_password_hash(password))
    db.session.add(user)
    db.session.commit()
    session[SESSION_USER_ID_KEY] = user.id
    session.modified = True
    return jsonify({"id": user.id, "username": user.username, "email": user.email}), 201


@auth_bp.post("/api/auth/login")
def login_user():
    body = _json_body()
    email = str(body.get("email", "")).strip().lower()
    password = str(body.get("password", ""))
    if not email or not password:
        return jsonify({"error": "email and password are required"}), 400

    user = User.query.filter_by(email=email).first()
    if not user or not check_password_hash(user.password_hash, password):
        return jsonify({"error": "invalid credentials"}), 401

    session[SESSION_USER_ID_KEY] = user.id
    session.modified = True
    return jsonify({"id": user.id, "username": user.username, "email": user.email})


@auth_bp.post("/api/auth/logout")
def logout_user():
    session.pop(SESSION_USER_ID_KEY, None)
    session.modified = True
    return jsonify({"ok": True})


@auth_bp.get("/api/auth/me")
def current_user():
    user_id = session.get(SESSION_USER_ID_KEY)
    if not isinstance(user_id, int):
        return jsonify({"authenticated": False}), 401
    user = User.query.get(user_id)
    if not user:
        session.pop(SESSION_USER_ID_KEY, None)
        session.modified = True
        return jsonify({"authenticated": False}), 401
    return jsonify(
        {
            "authenticated": True,
            "user": {"id": user.id, "username": user.username, "email": user.email},
        }
    )
