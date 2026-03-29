from flask import Blueprint

from routes.helpers import render_feature_page


orders_bp = Blueprint("orders", __name__)


@orders_bp.get("/cart")
def cart() -> str:
    return render_feature_page("cart")


@orders_bp.get("/checkout")
def checkout() -> str:
    return render_feature_page("checkout")


@orders_bp.get("/payment")
def payment() -> str:
    return render_feature_page("payment")


@orders_bp.get("/pickup-planner")
def pickup_planner() -> str:
    return render_feature_page("pickup_planner")


@orders_bp.get("/receipt")
def receipt() -> str:
    return render_feature_page("receipt")


@orders_bp.get("/orders")
def orders() -> str:
    return render_feature_page("orders")
