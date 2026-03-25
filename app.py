from datetime import datetime

from flask import Flask, render_template, render_template_string


def create_app() -> Flask:
    app = Flask(__name__)

    @app.context_processor
    def inject_globals():
        return {"current_year": datetime.now().year}

    @app.get("/")
    def home():
        return render_template("index.html")

    @app.get("/menu")
    def menu():
        return render_template("menu/menu.html")

    @app.get("/orders")
    def orders():
        return render_template_string(
            """
            {% extends "base.html" %}
            {% block title %}Orders | MCQ{% endblock %}
            {% block content %}
            <section style="background:#fff;border:1px solid rgba(15,23,42,.08);border-radius:1rem;padding:2rem;">
              <h1 style="margin-top:0;">Orders</h1>
              <p>This preview branch is focused on menu browsing. Order management is not wired yet.</p>
            </section>
            {% endblock %}
            """
        )

    @app.get("/profile")
    def profile():
        return render_template_string(
            """
            {% extends "base.html" %}
            {% block title %}Profile | MCQ{% endblock %}
            {% block content %}
            <section style="background:#fff;border:1px solid rgba(15,23,42,.08);border-radius:1rem;padding:2rem;">
              <h1 style="margin-top:0;">Profile</h1>
              <p>This preview branch is focused on menu browsing. Profile screens are placeholders for now.</p>
            </section>
            {% endblock %}
            """
        )

    @app.get("/shared-meals")
    def shared_meals():
        return render_template_string(
            """
            {% extends "base.html" %}
            {% block title %}Shared Meals | MCQ{% endblock %}
            {% block content %}
            <section style="background:#fff;border:1px solid rgba(15,23,42,.08);border-radius:1rem;padding:2rem;">
              <h1 style="margin-top:0;">Shared Meals</h1>
              <p>This preview branch is focused on menu browsing. Shared meal content is not connected yet.</p>
            </section>
            {% endblock %}
            """
        )

    return app


app = create_app()
