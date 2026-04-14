from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from flask import Flask, has_request_context, session, url_for

from config import Config
from models import Order, init_db
from routes.auth import current_user, is_admin_user
from routes import register_blueprints


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    init_db(app)

    @app.context_processor
    def inject_globals() -> dict[str, object]:
        site_notifications: list[dict] = []
        if has_request_context():
            history = session.get("order_history_numbers")
            if isinstance(history, list):
                order_numbers = [number for number in history if isinstance(number, str)][:10]
                if order_numbers:
                    orders = Order.query.filter(Order.order_number.in_(order_numbers)).all()
                    lookup = {order.order_number: order for order in orders}
                    for order_number in order_numbers:
                        order = lookup.get(order_number)
                        if order is None or order.order_status not in {"Ready for Pickup", "Completed"}:
                            continue
                        latest_ready = next(
                            (
                                note
                                for note in order.notifications
                                if note.event_type == "ready_for_pickup" and note.delivery_status == "Sent"
                            ),
                            None,
                        )
                        if latest_ready is None:
                            continue
                        site_notifications.append(
                            {
                                "order_number": order.order_number,
                                "message": latest_ready.message,
                                "channel": latest_ready.channel.upper(),
                                "created_at": latest_ready.created_at.replace(tzinfo=ZoneInfo("UTC"))
                                .astimezone(ZoneInfo(app.config["APP_TIMEZONE"]))
                                .strftime("%A, %d %b %Y at %I:%M %p")
                                .lstrip("0"),
                                "href": url_for("orders.order_detail", order_number=order.order_number),
                            }
                        )
                        if len(site_notifications) >= 3:
                            break
        user = current_user()
        return {
            "current_year": datetime.now().year,
            "restaurant_phone": app.config.get("RESTAURANT_PHONE", "08 9248 5623"),
            "current_user": user,
            "is_admin": is_admin_user(user),
            "site_notifications": site_notifications,
        }

    register_blueprints(app)
    return app


app = create_app()
