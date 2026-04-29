from datetime import datetime
import os

from flask import Flask

from config import Config
from extensions import db
from routes import register_blueprints


def create_app() -> Flask:
    app = Flask(__name__)
    app.config.from_object(Config)
    os.makedirs(app.instance_path, exist_ok=True)
    db.init_app(app)

    with app.app_context():
        # Import models so SQLAlchemy knows all table metadata.
        import models  # noqa: F401

    @app.context_processor
    def inject_globals() -> dict[str, int]:
        return {"current_year": datetime.now().year}

    @app.cli.command("init-db")
    def init_db_command() -> None:
        db.create_all()
        print("Database initialized.")

    register_blueprints(app)
    return app


app = create_app()
