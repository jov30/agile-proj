import os
from datetime import datetime, timedelta

import click
from flask import Flask

from config import Config
from database import init_database, seed_database
from extensions import db
from routes import register_blueprints


def create_app() -> Flask:
    app = Flask(__name__, instance_relative_config=True)
    app.config.from_object(Config)
    app.config.setdefault("PERMANENT_SESSION_LIFETIME", timedelta(days=180))

    os.makedirs(app.instance_path, exist_ok=True)
    app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get(
        "DATABASE_URL",
        "sqlite:///" + os.path.join(app.instance_path, "app.sqlite"),
    )

    db.init_app(app)

    import models  # noqa: F401 — register metadata before init_database

    _register_cli(app)

    with app.app_context():
        init_database(app)
        seed_database(app)

    @app.context_processor
    def inject_globals() -> dict[str, int]:
        return {"current_year": datetime.now().year}

    register_blueprints(app)
    return app


def _register_cli(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db_command() -> None:
        """Create SQLite tables (and run seed hook). Safe to run multiple times."""
        with app.app_context():
            init_database(app)
            seed_database(app)
        click.echo(f"Database initialized at {app.config['SQLALCHEMY_DATABASE_URI']}")


app = create_app()
