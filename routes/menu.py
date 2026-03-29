from flask import Blueprint, render_template


public_bp = Blueprint("public", __name__)


@public_bp.get("/")
def home() -> str:
    return render_template("index.html")


@public_bp.get("/menu")
def menu() -> str:
    return render_template("menu/menu.html")
