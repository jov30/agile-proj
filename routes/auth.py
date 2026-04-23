from __future__ import annotations

from functools import wraps

from flask import Blueprint, current_app, jsonify, redirect, render_template, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from models import User, db


auth_bp = Blueprint("auth", __name__)
SESSION_USER_KEY = "auth_user"


def current_user() -> dict | None:
    payload = session.get(SESSION_USER_KEY)
    if not isinstance(payload, dict):
        return None
    name = payload.get("name")
    email = payload.get("email")
    role = payload.get("role")
    if not isinstance(name, str) or not isinstance(email, str) or role not in {"customer", "admin"}:
        return None
    return {"name": name, "email": email, "role": role}


def is_admin_user(user: dict | None = None) -> bool:
    active_user = user or current_user()
    return bool(active_user and active_user.get("role") == "admin")


def admin_required(view_func):
    @wraps(view_func)
    def wrapped(*args, **kwargs):
        if is_admin_user():
            return view_func(*args, **kwargs)
        next_url = request.full_path.rstrip("?")
        login_url = url_for("auth.login", next=next_url)
        if request.path.startswith("/api/"):
            return jsonify({"error": "admin access required", "login_url": login_url}), 403
        return redirect(login_url)

    return wrapped


def _safe_next_url(value: str | None) -> str | None:
    if not value or not value.startswith("/") or value.startswith("//"):
        return None
    return value


def _auth_context(
    *,
    title: str,
    eyebrow: str,
    intro: str,
    submit_label: str,
    alternate_label: str,
    alternate_href: str,
    form_data: dict[str, str] | None = None,
    errors: list[str] | None = None,
    next_url: str | None = None,
):
    return {
        "title": title,
        "eyebrow": eyebrow,
        "intro": intro,
        "submit_label": submit_label,
        "alternate_label": alternate_label,
        "alternate_href": alternate_href,
        "form_data": form_data or {"email": "", "password": ""},
        "errors": errors or [],
        "next_url": next_url or "",
        "admin_demo": {
            "name": current_app.config["ADMIN_NAME"],
            "email": current_app.config["ADMIN_EMAIL"],
            "password": current_app.config["ADMIN_PASSWORD"],
        },
    }


@auth_bp.route("/login", methods=["GET", "POST"])
def login() -> str:
    next_url = _safe_next_url(request.values.get("next"))
    if request.method == "POST":
        form_data = {
            "email": request.form.get("email", "").strip().lower(),
            "password": request.form.get("password", "").strip(),
        }
        errors: list[str] = []

        if "@" not in form_data["email"]:
            errors.append("Enter a valid email address.")
        if len(form_data["password"]) < 6:
            errors.append("Password must be at least 6 characters.")

        if not errors:
            # ── Admin check (config-based, no DB) ──────────────────────────
            if (
                form_data["email"] == current_app.config["ADMIN_EMAIL"].lower()
                and form_data["password"] == current_app.config["ADMIN_PASSWORD"]
            ):
                session[SESSION_USER_KEY] = {
                    "name": current_app.config["ADMIN_NAME"],
                    "email": current_app.config["ADMIN_EMAIL"],
                    "role": "admin",
                }
                session.modified = True
                return redirect(next_url or url_for("admin.admin_queue"))

            # ── Customer check (DB lookup) ──────────────────────────────────
            user = User.query.filter_by(email=form_data["email"]).first()
            if user is None or not check_password_hash(user.password_hash, form_data["password"]):
                errors.append("Invalid email or password.")

        if errors:
            context = _auth_context(
                title="Login",
                eyebrow="Customer access",
                intro="Sign in with the email and password you used when you registered. No account yet?",
                submit_label="Sign in",
                alternate_label="Create account",
                alternate_href=url_for("auth.register"),
                form_data=form_data,
                errors=errors,
                next_url=next_url,
            )
            return render_template("auth/login.html", **context), 400

        session[SESSION_USER_KEY] = {
            "name": user.name,
            "email": user.email,
            "role": user.role,
        }
        session.modified = True
        return redirect(next_url or url_for("public.menu"))

    context = _auth_context(
        title="Login",
        eyebrow="Customer access",
        intro="Sign in with the email and password you used when you registered. No account yet?",
        submit_label="Sign in",
        alternate_label="Create account",
        alternate_href=url_for("auth.register"),
        next_url=next_url,
    )
    return render_template("auth/login.html", **context)


@auth_bp.route("/register", methods=["GET", "POST"])
def register() -> str:
    next_url = _safe_next_url(request.values.get("next"))
    if request.method == "POST":
        form_data = {
            "name": request.form.get("name", "").strip(),
            "email": request.form.get("email", "").strip().lower(),
            "password": request.form.get("password", "").strip(),
        }
        errors: list[str] = []

        if len(form_data["name"]) < 2:
            errors.append("Enter your full name.")
        if "@" not in form_data["email"]:
            errors.append("Enter a valid email address.")
        if len(form_data["password"]) < 6:
            errors.append("Password must be at least 6 characters.")

        # Block registration with the admin email
        if (
            not errors
            and form_data["email"] == current_app.config["ADMIN_EMAIL"].lower()
        ):
            errors.append("That email address is not available.")

        # Check for duplicate email
        if not errors and User.query.filter_by(email=form_data["email"]).first():
            errors.append("An account with that email already exists. Try logging in.")

        if errors:
            context = _auth_context(
                title="Register",
                eyebrow="New customer onboarding",
                intro="Create an account for faster checkout, order tracking, and in-site notifications.",
                submit_label="Create account",
                alternate_label="Already have an account?",
                alternate_href=url_for("auth.login"),
                form_data=form_data,
                errors=errors,
                next_url=next_url,
            )
            return render_template("auth/register.html", **context), 400

        # ── Persist to DB ───────────────────────────────────────────────────
        new_user = User(
            name=form_data["name"],
            email=form_data["email"],
            password_hash=generate_password_hash(form_data["password"]),
            role="customer",
        )
        db.session.add(new_user)
        db.session.commit()

        session[SESSION_USER_KEY] = {
            "name": new_user.name,
            "email": new_user.email,
            "role": new_user.role,
        }
        session.modified = True
        return redirect(next_url or url_for("public.menu"))

    context = _auth_context(
        title="Register",
        eyebrow="New customer onboarding",
        intro="Create an account for faster checkout, order tracking, and in-site notifications.",
        submit_label="Create account",
        alternate_label="Already have an account?",
        alternate_href=url_for("auth.login"),
        next_url=next_url,
    )
    return render_template("auth/register.html", **context)


@auth_bp.post("/logout")
def logout():
    session.pop(SESSION_USER_KEY, None)
    session.modified = True
    return redirect(url_for("public.home"))