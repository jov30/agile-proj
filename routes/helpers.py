from flask import render_template

from feature_pages import get_feature_page_context


def render_feature_page(feature_key: str) -> str:
    return render_template("feature-page.html", **get_feature_page_context(feature_key))
