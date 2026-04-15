# MCQ Vietnamese Street Food Ordering Platform

![MCQ Vietnamese Street Food Logo](static/images/mcq-logo.jpg)

## Overview

MCQ is a Flask-based client-server web application for Vietnamese street-food pickup ordering.  
The current build focuses on a complete customer ordering journey, from menu browsing to receipt download, with both **scheduled pickup** and **instant counter pickup** supported.

This branch also includes restaurant-side queue operations, order tracking, branded receipts, and a support chat experience with AI fallback handling.

## Team Members

| UWA ID | Name | GitHub Username |
|--------|------|-----------------|
| 24307608 | Tony Le | utle23 |
| 23957425 | Jovan Pui | jov30 |
| 24220908 | Samuel Ou | slimoftheshady |
| 24181084 | Thomas Zeng | zxx457 |

## Guaranteed Features In This Build

These are the features the current project build is designed to include.

### Customer Ordering

- register, log in, and log out
- browse the full menu and view item detail pages
- add items to cart and update quantities
- see cart totals, service fee, and fulfillment-aware checkout hints
- choose between:
  - **Instant counter pickup** with queue number and quoted wait time
  - **Scheduled pickup** with date and time slot selection
- complete a **simulated payment** flow
- create persistent orders in SQLite
- receive a branded HTML receipt and downloadable PDF receipt
- scan a QR code that opens live order tracking
- view order history and order detail pages
- reorder a previous order back into the cart
- receive in-site ready notifications for pickup updates

### Order Tracking and Operations

- live order detail view with current status
- sequential status updates:
  - `Confirmed`
  - `Preparing`
  - `Ready for Pickup`
  - `Completed`
- admin-only queue management screen for pickup operations
- instant queue numbering with safer database-backed assignment
- receipt and order pages showing notification timeline information

### Support and UX

- branded landing page and menu experience
- improved cart, checkout, receipt, and order page layouts
- support chatbox with:
  - OpenAI-backed replies when an API key is configured and available
  - automatic fallback assistant replies when AI is unavailable

## Supporting Scope

The project also keeps lightweight supporting pages for:

- profile
- favourites
- shared meals
- support information

These pages help cover broader project scope and future extension points, but the most complete and production-ready flows in this build are the **menu, cart, checkout, order, receipt, and admin queue** journeys.

## Example User Flow

1. Open the landing page and choose `Order Now` or `Schedule Pickup`.
2. Browse the menu and add dishes to the cart.
3. Review the cart summary.
4. Go to checkout.
5. Choose instant pickup or scheduled pickup.
6. Complete the simulated payment.
7. Receive an order confirmation and receipt.
8. Track the order from the receipt, QR code, or order history.
9. Reorder later if needed.

## Example Admin Flow

1. Log in with the admin demo account.
2. Open `/admin/orders/queue`.
3. Review active instant and scheduled orders.
4. Move orders through the allowed status sequence.
5. Trigger ready-for-pickup notifications shown on the customer side.

## Tech Stack

### Backend

- Flask
- Flask-SQLAlchemy
- SQLite

### Frontend

- Jinja templates
- HTML
- CSS
- Vanilla JavaScript

### Supporting Libraries

- `requests` for AI chat API calls
- `Pillow` for receipt/QR image handling
- `qrcode` for receipt QR generation

## Project Structure

```text
project-root/
│
├── app.py
├── config.py
├── feature_pages.py
├── menu_catalog.py
├── models.py
├── receipt_pdf.py
├── requirements.txt
├── README.md
├── data/
│   ├── menu-image-sources.json
│   ├── menu-prices.json
│   ├── menu-source.txt
│   └── visual-inspiration-sources.json
├── routes/
│   ├── __init__.py
│   ├── admin.py
│   ├── auth.py
│   ├── cart_api.py
│   ├── helpers.py
│   ├── menu.py
│   ├── orders.py
│   └── user.py
├── scripts/
│   ├── build_menu_json.py
│   └── download_menu_images.py
├── static/
│   ├── css/
│   │   └── main.css
│   ├── data/
│   │   └── menu.json
│   ├── images/
│   │   ├── brand/
│   │   ├── inspiration/
│   │   ├── menu/
│   │   ├── mcq-logo.jpg
│   │   └── .gitkeep
│   └── js/
│       ├── admin.js
│       ├── cart.js
│       └── checkout.js
├── templates/
│   ├── admin/
│   │   └── orders.html
│   ├── auth/
│   │   ├── login.html
│   │   └── register.html
│   ├── menu/
│   │   ├── cart.html
│   │   ├── checkout.html
│   │   ├── item_detail.html
│   │   ├── menu.html
│   │   └── receipt.html
│   ├── user/
│   │   ├── order_detail.html
│   │   └── orders.html
│   ├── base.html
│   ├── feature-page.html
│   └── index.html
├── instance/
│   └── app.db
└── tests/
    ├── test_admin.py
    ├── test_auth.py
    ├── test_menu.py
    ├── test_orders.py
    └── test_user.py
```

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/jov30/agile-proj.git
cd agile-proj
git checkout feature/Checkout-Orders-Receipts
```

### 2. Create and activate a virtual environment

macOS / Linux:

```bash
python3 -m venv venv
source venv/bin/activate
python3 -m pip install -r requirements.txt
```

Windows:

```powershell
py -m venv venv
venv\Scripts\activate
py -m pip install -r requirements.txt
```

### 3. Run the application

macOS / Linux:

```bash
python3 -m flask --app app run --host 127.0.0.1 --port 5000
```

Windows:

```powershell
py -m flask --app app run --host 127.0.0.1 --port 5000
```

Then open:

```text
http://127.0.0.1:5000
```

## Configuration

The app works with defaults, but these environment variables are supported:

- `FLASK_SECRET_KEY`
- `DATABASE_URL`
- `APP_ENV`
- `APP_TIMEZONE`
- `PUBLIC_BASE_URL`
- `OPENAI_API_KEY`
- `OPENAI_API_BASE`
- `OPENAI_CHAT_MODEL`
- `ADMIN_NAME`
- `ADMIN_EMAIL`
- `ADMIN_PASSWORD`
- `ENABLE_INSTANT_ORDERING`
- `DEMO_ALLOW_AFTER_HOURS_INSTANT_ORDERING`

Pickup scheduling and instant queue timing can also be tuned through config values in `config.py`.

## Database

- SQLite is used by default.
- The database file is created under `instance/app.db`.
- Tables are initialized automatically when the app starts.

## Demo Admin Account

Default admin credentials:

- Email: `admin@mcq.local`
- Password: `Admin@123`

These can be overridden with environment variables.

## Running Tests

Run the full test suite with:

```bash
venv/bin/python -m unittest tests.test_auth tests.test_admin tests.test_menu tests.test_orders tests.test_user
```

The current branch includes automated coverage for:

- authentication
- admin queue access and updates
- menu and cart behavior
- checkout, payment retries, and order creation
- receipts, QR links, and order tracking
- support chat and user-facing flows

## Menu Data and Assets

- `data/menu-source.txt` is the plain-text menu source used to regenerate structured menu data.
- `data/menu-prices.json` stores price information used by the app.
- `scripts/build_menu_json.py` regenerates `static/data/menu.json`.
- branded and inspiration imagery lives under `static/images/`.

If the menu source changes, regenerate the JSON feed before committing:

```bash
python3 scripts/build_menu_json.py
```

## Notes and Limitations

- Payments are **simulated** for demo and assessment purposes.
- The AI chatbox depends on a valid OpenAI API key and available quota; otherwise it falls back automatically.
- Profile, favourites, and shared-meal areas are supporting scope pages rather than fully developed data-management modules in this build.

## Future Extensions

Possible future improvements include:

- real email or SMS notifications
- richer customer accounts and profile editing
- favourites persistence and real shared-meal data
- menu management from the admin side
- stronger analytics and reporting
- real payment gateway integration

