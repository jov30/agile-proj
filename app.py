from datetime import datetime

from flask import Flask

from config import Config
from routes import register_blueprints


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)

    @app.context_processor
    def inject_globals() -> dict[str, int]:
        return {"current_year": datetime.now().year}

    register_blueprints(app)
    return app


app = create_app()
