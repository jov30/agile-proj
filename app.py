from datetime import datetime

from flask import Flask, render_template, render_template_string


def render_placeholder_page(title: str, eyebrow: str, message: str) -> str:
    return render_template_string(
        """
        {% extends "base.html" %}
        {% block title %}{{ title }} | MCQ{% endblock %}
        {% block content %}
        <section class="section-panel" style="padding:clamp(1.4rem,3vw,2.2rem);">
          <p class="eyebrow">{{ eyebrow }}</p>
          <h1 class="section-title" style="font-size:clamp(1.8rem,3vw,3rem);">{{ title }}</h1>
          <p class="section-copy">{{ message }}</p>
          <div class="pill-row">
            <span class="pill"><strong>Brand aligned</strong> page shell already updated</span>
            <span class="pill"><strong>Next step</strong> wire the real feature content</span>
          </div>
        </section>
        {% endblock %}
        """,
        title=title,
        eyebrow=eyebrow,
        message=message,
    )


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
        return render_placeholder_page(
            "Orders",
            "Pickup status",
            "This page is ready to adopt the new storefront-inspired visual system. The actual order management flow still needs to be wired in.",
        )

    @app.get("/profile")
    def profile():
        return render_placeholder_page(
            "Profile",
            "Customer account",
            "Profile screens are still placeholders, but they now sit inside the same upgraded visual language as the rest of the public site.",
        )

    @app.get("/shared-meals")
    def shared_meals():
        return render_placeholder_page(
            "Shared Meals",
            "Community picks",
            "Shared meal content is not connected yet, but the page now matches the new MCQ moodboard and layout direction.",
        )

    return app


app = create_app()
