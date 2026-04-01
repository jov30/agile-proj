from __future__ import annotations

from pathlib import Path

from flask import Blueprint, abort, jsonify, render_template

from menu_catalog import find_item, load_enriched_menu

public_bp = Blueprint("public", __name__)

_ROOT_DIR = Path(__file__).resolve().parent.parent


def _menu_path() -> Path:
    return _ROOT_DIR / "static" / "data" / "menu.json"


@public_bp.get("/")
def home() -> str:
    return render_template("index.html")


@public_bp.get("/menu")
def menu() -> str:
    return render_template("menu/menu.html")


@public_bp.get("/api/menu")
def api_menu():
    data = load_enriched_menu(_menu_path())
    return jsonify(data)


@public_bp.get("/menu/item/<item_id>")
def menu_item_detail(item_id: str) -> str:
    data = load_enriched_menu(_menu_path())
    found = find_item(data, item_id)
    if not found:
        abort(404)
    category, item = found
    return render_template("menu/item_detail.html", item=item, category=category)
