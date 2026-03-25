from flask import Flask

from routes.auth import auth_bp
from routes.menu import public_bp
from routes.orders import orders_bp
from routes.user import user_bp


def register_blueprints(app: Flask) -> None:
    for blueprint in (public_bp, auth_bp, orders_bp, user_bp):
        app.register_blueprint(blueprint)
