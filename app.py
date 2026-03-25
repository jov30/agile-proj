from datetime import datetime

from flask import Flask, render_template


FEATURE_PAGES = {
    "login": {
        "title": "Login",
        "eyebrow": "Customer access",
        "message": "Returning customers will sign in here to revisit order history, check pickup timing, and jump back into their saved favourites.",
        "image": "images/inspiration/streetfood-1.jpg",
        "image_alt": "Vietnamese street food tray",
        "pills": [
            {"strong": "Fast return", "text": "pick up where previous orders left off"},
            {"strong": "Saved dishes", "text": "bring favourites and shared meals back into view"},
            {"strong": "Pickup ready", "text": "surface scheduled collection details quickly"},
        ],
        "facts": [
            {
                "title": "Why it matters",
                "body": "Login is the gateway to personalised ordering, history, favourites, and meal sharing for repeat customers.",
            },
            {
                "title": "Feature link",
                "body": "It connects directly to cart, checkout, payment, receipt access, and support flows.",
            },
        ],
        "actions": [
            {"label": "Create Account", "href": "/register", "variant": "primary"},
            {"label": "Browse Menu", "href": "/menu", "variant": "secondary"},
            {"label": "Customer Support", "href": "/support", "variant": "secondary"},
        ],
    },
    "register": {
        "title": "Register",
        "eyebrow": "New customer onboarding",
        "message": "New accounts will let customers save profile details, keep favourite dishes, place scheduled pickup orders, and join the meal-sharing side of the platform.",
        "image": "images/inspiration/streetfood-5.jpg",
        "image_alt": "Vietnamese produce market baskets",
        "pills": [
            {"strong": "Account setup", "text": "unlock saved details and easier repeat ordering"},
            {"strong": "Community ready", "text": "join favourites and shared meal features later"},
            {"strong": "Pickup flow", "text": "support checkout, payment, and confirmation"},
        ],
        "facts": [
            {
                "title": "What this page should do",
                "body": "Collect customer account details cleanly while keeping the visual tone aligned with the storefront-inspired branding.",
            },
            {
                "title": "Project fit",
                "body": "Registration is explicitly required in the README and is part of the main user workflow.",
            },
        ],
        "actions": [
            {"label": "Login", "href": "/login", "variant": "primary"},
            {"label": "Browse Menu", "href": "/menu", "variant": "secondary"},
            {"label": "View Support", "href": "/support", "variant": "secondary"},
        ],
    },
    "profile": {
        "title": "Profile",
        "eyebrow": "Customer account",
        "message": "The profile area will eventually hold customer details, saved preferences, and the account settings that support a smoother ordering and pickup experience.",
        "image": "images/brand/benthanh.jpg",
        "image_alt": "Ben Thanh Market illustration",
        "pills": [
            {"strong": "Personal details", "text": "store customer profile information"},
            {"strong": "Pickup habits", "text": "make scheduled collection easier to manage"},
            {"strong": "Brand aligned", "text": "keep even utilitarian pages inside the same MCQ mood"},
        ],
        "facts": [
            {
                "title": "Future content",
                "body": "Profile information, password management, favourite dish history, and pickup preferences can all live here.",
            },
            {
                "title": "Visual direction",
                "body": "Using Ben Thanh here keeps the page tied to the storefront identity instead of feeling like a generic account screen.",
            },
        ],
        "actions": [
            {"label": "Login", "href": "/login", "variant": "primary"},
            {"label": "Order History", "href": "/orders", "variant": "secondary"},
            {"label": "Favourites", "href": "/favorites", "variant": "secondary"},
        ],
    },
    "cart": {
        "title": "Cart",
        "eyebrow": "Basket preview",
        "message": "The cart will collect dishes, quantities, and notes before customers move into checkout, payment, pickup scheduling, and final confirmation.",
        "image": "images/inspiration/streetfood-9.jpg",
        "image_alt": "Vietnamese street food skewers in sauce trays",
        "pills": [
            {"strong": "Order summary", "text": "show quantities, prices, and selected dishes clearly"},
            {"strong": "Next step", "text": "move naturally into checkout and payment"},
            {"strong": "Practical flow", "text": "keep the experience useful as well as attractive"},
        ],
        "facts": [
            {
                "title": "Why this matters",
                "body": "A clear basket view is central to preventing mistakes before the customer commits to payment and pickup.",
            },
            {
                "title": "README alignment",
                "body": "The project brief explicitly calls for viewing cart contents and total price before checkout.",
            },
        ],
        "actions": [
            {"label": "Checkout", "href": "/checkout", "variant": "primary"},
            {"label": "Payment", "href": "/payment", "variant": "secondary"},
            {"label": "Browse Menu", "href": "/menu", "variant": "secondary"},
        ],
    },
    "checkout": {
        "title": "Checkout",
        "eyebrow": "Scheduled pickup flow",
        "message": "Checkout should combine order review, payment method choice, pickup date and time, and final confirmation in one clear customer journey.",
        "image": "images/inspiration/street-food-life.jpg",
        "image_alt": "Vietnam street food life inspiration",
        "pills": [
            {"strong": "Core workflow", "text": "convert browsing into a confirmed scheduled pickup order"},
            {"strong": "Payment ready", "text": "connect to the simulated payment step"},
            {"strong": "Confirmation", "text": "lead toward receipt and order history after submission"},
        ],
        "facts": [
            {
                "title": "Business need",
                "body": "This is the most important practical page in the project because it turns the menu into a working online ordering system.",
            },
            {
                "title": "What follows",
                "body": "Customers should move from checkout into payment, pickup planning, and a receipt or confirmation screen.",
            },
        ],
        "actions": [
            {"label": "Payment", "href": "/payment", "variant": "primary"},
            {"label": "Pickup Planner", "href": "/pickup-planner", "variant": "secondary"},
            {"label": "Cart", "href": "/cart", "variant": "secondary"},
        ],
    },
    "payment": {
        "title": "Payment",
        "eyebrow": "Simulated payment step",
        "message": "The platform brief includes payment through the system, so this page is now represented as its own user-side feature instead of being hidden inside a generic placeholder.",
        "image": "images/inspiration/streetfood-7.jpg",
        "image_alt": "Vietnamese fresh shrimp rice paper rolls",
        "pills": [
            {"strong": "Required feature", "text": "payment is part of the documented customer workflow"},
            {"strong": "Checkout follow-up", "text": "sit directly after order review"},
            {"strong": "Confidence point", "text": "help customers understand the order is progressing"},
        ],
        "facts": [
            {
                "title": "Why add this now",
                "body": "It was one of the most obvious missing user-side buttons compared with the README feature list.",
            },
            {
                "title": "Design role",
                "body": "This page can eventually host payment method selection, validation messaging, and a final order amount.",
            },
        ],
        "actions": [
            {"label": "Pickup Planner", "href": "/pickup-planner", "variant": "primary"},
            {"label": "Checkout", "href": "/checkout", "variant": "secondary"},
            {"label": "Receipt", "href": "/receipt", "variant": "secondary"},
        ],
    },
    "pickup_planner": {
        "title": "Pickup Planner",
        "eyebrow": "Scheduled collection",
        "message": "Scheduled pickup is central to the whole application, so this page now exists as a visible customer destination for choosing a date and time before final confirmation.",
        "image": "images/inspiration/streetfood-1.jpg",
        "image_alt": "Vietnamese street food tray with herbs",
        "pills": [
            {"strong": "Core requirement", "text": "choose pickup date and time before confirming the order"},
            {"strong": "Operational value", "text": "helps the kitchen and customer stay in sync"},
            {"strong": "Natural next step", "text": "belongs between payment and receipt"},
        ],
        "facts": [
            {
                "title": "Project role",
                "body": "The README describes scheduled pickup as the main business problem the application is solving.",
            },
            {
                "title": "Customer expectation",
                "body": "Users need a clear scheduling surface, not just a hidden input somewhere inside checkout.",
            },
        ],
        "actions": [
            {"label": "Receipt", "href": "/receipt", "variant": "primary"},
            {"label": "Order History", "href": "/orders", "variant": "secondary"},
            {"label": "Customer Support", "href": "/support", "variant": "secondary"},
        ],
    },
    "receipt": {
        "title": "Receipt",
        "eyebrow": "Confirmation and proof",
        "message": "After payment and pickup scheduling, customers should land on a confirmation page with receipt details, order summary, and a clear route into order history.",
        "image": "images/inspiration/streetfood-8.jpg",
        "image_alt": "Vietnamese banh xeo cooking and plating collage",
        "pills": [
            {"strong": "After checkout", "text": "confirm that the order has been placed successfully"},
            {"strong": "Receipt ready", "text": "prepare for PDF export and order proof"},
            {"strong": "History link", "text": "push the order into the customer's previous orders"},
        ],
        "facts": [
            {
                "title": "Why this was added",
                "body": "The receipt and confirmation stage was also named in the README but had no visible placeholder before now.",
            },
            {
                "title": "Future use",
                "body": "This page can eventually show receipt download, pickup instructions, and order status details.",
            },
        ],
        "actions": [
            {"label": "Order History", "href": "/orders", "variant": "primary"},
            {"label": "Shared Meals", "href": "/shared-meals", "variant": "secondary"},
            {"label": "Browse Menu", "href": "/menu", "variant": "secondary"},
        ],
    },
    "orders": {
        "title": "Orders",
        "eyebrow": "Pickup status and history",
        "message": "Order history should let customers revisit previous purchases, track pickup-related progress, and quickly re-order dishes they already know they like.",
        "image": "images/inspiration/streetfood-10.jpg",
        "image_alt": "Vietnamese market skewer spread",
        "pills": [
            {"strong": "History view", "text": "surface previous orders in one place"},
            {"strong": "Status tracking", "text": "show whether an order is pending, preparing, or ready"},
            {"strong": "Repeat value", "text": "make re-ordering favourite dishes faster"},
        ],
        "facts": [
            {
                "title": "Workflow role",
                "body": "Order history closes the loop after checkout, payment, pickup planning, and receipt generation.",
            },
            {
                "title": "Admin connection",
                "body": "This page will eventually reflect status updates made from the admin side of the platform.",
            },
        ],
        "actions": [
            {"label": "Receipt", "href": "/receipt", "variant": "primary"},
            {"label": "Browse Menu", "href": "/menu", "variant": "secondary"},
            {"label": "Profile", "href": "/profile", "variant": "secondary"},
        ],
    },
    "favorites": {
        "title": "Favourites",
        "eyebrow": "Saved dishes",
        "message": "Favourites help customers keep track of their go-to meals, build repeat habits, and choose what to share with other users later.",
        "image": "images/inspiration/noodle-bowl-unsplash.jpg",
        "image_alt": "Vietnamese noodle bowl close-up",
        "pills": [
            {"strong": "Personal curation", "text": "collect reliable favourite dishes in one place"},
            {"strong": "Community tie-in", "text": "connect naturally to meal sharing"},
            {"strong": "Repeat orders", "text": "make it easier to add known dishes back into cart"},
        ],
        "facts": [
            {
                "title": "Project fit",
                "body": "Saved favourite meals are part of the documented user-side requirements, not just an optional extra.",
            },
            {
                "title": "Future state",
                "body": "This screen can eventually hold private favourites, public shares, and quick add-to-cart actions.",
            },
        ],
        "actions": [
            {"label": "Shared Meals", "href": "/shared-meals", "variant": "primary"},
            {"label": "Browse Menu", "href": "/menu", "variant": "secondary"},
            {"label": "Cart", "href": "/cart", "variant": "secondary"},
        ],
    },
    "shared_meals": {
        "title": "Shared Meals",
        "eyebrow": "Community picks",
        "message": "Meal sharing gives the project its social layer, letting customers browse dishes other users recommend and making the platform feel more interactive than a plain ordering form.",
        "image": "images/inspiration/streetfood-8.jpg",
        "image_alt": "Vietnamese banh xeo street-food platter",
        "pills": [
            {"strong": "Community layer", "text": "support the requirement that users can view data from others"},
            {"strong": "Discovery", "text": "turn popular favourites into social recommendations"},
            {"strong": "Platform identity", "text": "differentiate MCQ from a generic takeaway site"},
        ],
        "facts": [
            {
                "title": "Why it matters",
                "body": "Shared meals are central to the community requirement in the brief and deserve visible placement in the interface.",
            },
            {
                "title": "Future content",
                "body": "This could hold shared meal cards, customer notes, and quick links back into the menu or favourites.",
            },
        ],
        "actions": [
            {"label": "Favourites", "href": "/favorites", "variant": "primary"},
            {"label": "Browse Menu", "href": "/menu", "variant": "secondary"},
            {"label": "Profile", "href": "/profile", "variant": "secondary"},
        ],
    },
    "support": {
        "title": "Customer Support",
        "eyebrow": "Help and assistance",
        "message": "Support should answer questions about menu items, payment, scheduled pickup, account access, and order confirmation while keeping the phone contact visible for customers who want a direct path.",
        "image": "images/inspiration/streetfood-4.jpg",
        "image_alt": "Vietnamese floating market boats",
        "pills": [
            {"strong": "Always visible", "text": "the floating chatbox stays pinned at the bottom of the website"},
            {"strong": "Direct contact", "text": "customers can call 08 9248 5623 when they need help"},
            {"strong": "Online assistance", "text": "future support can cover menu, payment, and pickup questions"},
        ],
        "facts": [
            {
                "title": "MCQ Supermarket",
                "body": "Need Help? Visit our Customer Support for assistance or call us at 08 9248 5623.",
            },
            {
                "title": "Why this page matters",
                "body": "It backs up the fixed chatbox with a dedicated support destination instead of relying on one floating widget alone.",
            },
        ],
        "actions": [
            {"label": "Call 08 9248 5623", "href": "tel:+61892485623", "variant": "primary"},
            {"label": "Pickup Planner", "href": "/pickup-planner", "variant": "secondary"},
            {"label": "Payment", "href": "/payment", "variant": "secondary"},
        ],
    },
}


def render_feature_page(feature_key: str) -> str:
    return render_template("feature-page.html", **FEATURE_PAGES[feature_key])


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

    @app.get("/login")
    def login():
        return render_feature_page("login")

    @app.get("/register")
    def register():
        return render_feature_page("register")

    @app.get("/profile")
    def profile():
        return render_feature_page("profile")

    @app.get("/cart")
    def cart():
        return render_feature_page("cart")

    @app.get("/checkout")
    def checkout():
        return render_feature_page("checkout")

    @app.get("/payment")
    def payment():
        return render_feature_page("payment")

    @app.get("/pickup-planner")
    def pickup_planner():
        return render_feature_page("pickup_planner")

    @app.get("/receipt")
    def receipt():
        return render_feature_page("receipt")

    @app.get("/orders")
    def orders():
        return render_feature_page("orders")

    @app.get("/favorites")
    def favorites():
        return render_feature_page("favorites")

    @app.get("/shared-meals")
    def shared_meals():
        return render_feature_page("shared_meals")

    @app.get("/support")
    def support():
        return render_feature_page("support")

    return app


app = create_app()
