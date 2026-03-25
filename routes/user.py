from flask import Blueprint

from routes.helpers import render_feature_page


user_bp = Blueprint("user", __name__)


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
