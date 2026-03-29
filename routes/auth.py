from flask import Blueprint

from routes.helpers import render_feature_page


auth_bp = Blueprint("auth", __name__)


@auth_bp.get("/login")
def login() -> str:
    return render_feature_page("login")


@auth_bp.get("/register")
def register() -> str:
    return render_feature_page("register")
