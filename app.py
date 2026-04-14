from datetime import datetime
from pathlib import Path

from flask import Flask

from config import Config
from models import init_db
from routes import register_blueprints


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    Path(app.instance_path).mkdir(parents=True, exist_ok=True)
    init_db(app)

    @app.context_processor
    def inject_globals() -> dict[str, int]:
        return {
            "current_year": datetime.now().year,
            "restaurant_phone": app.config.get("RESTAURANT_PHONE", "08 9248 5623"),
        }

    register_blueprints(app)
    return app


app = create_app()
