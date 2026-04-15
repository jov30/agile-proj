# MCQ Vietnamese Street Food Ordering Platform

![MCQ Vietnamese Street Food Logo](static/images/mcq-logo.jpg)

## Overview

MCQ is a Flask-based client-server web application for Vietnamese street-food ordering, pickup coordination, and customer account features.  
The final project scope covers customer authentication, profile and favourite-meal features, menu and cart management, checkout and receipt workflows, and restaurant-side admin operations.

In addition to the core assignment requirements, the current branch also includes richer delivery of those flows through **instant counter pickup**, **scheduled pickup**, **QR-coded receipts**, **PDF receipts**, **live order tracking**, **admin queue operations**, and a **support chat experience with AI fallback handling**.

## Team Members

| UWA ID | Name | GitHub Username |
|--------|------|-----------------|
| 24307608 | Tony Le | utle23 |
| 23957425 | Jovan Pui | jov30 |
| 24220908 | Samuel Ou | slimoftheshady |
| 24181084 | Thomas Zeng | zxx457 |

## Final Project Feature Scope

The project is designed around four main functional areas.

### 1. Authentication, Profile, and Favourite Meals

- user registration
- user login and logout
- profile view and update
- save favourite meals
- share favourite meals with other users
- view favourite meals shared by other users
- authentication and profile forms with validation
- user-related backend routes
- user and favourite-meal data handling in the database
- connection of login, register, profile, and shared-favourite pages to backend logic
- basic tests for authentication, profile, and favourite-meal flows

### 2. Menu and Cart

- menu browsing with category-based navigation
- filter menu bar and keyword search support
- menu item detail flow
- add items to cart
- update cart quantities
- view cart summary and total price
- cart-related backend routes
- menu and cart data handling
- connection of menu and cart pages to backend logic
- basic tests for menu and cart features

### 3. Checkout, Orders, and Receipts

- checkout flow
- simulated payment flow
- scheduled pickup date and time selection
- order confirmation
- store order records in the database
- PDF receipt generation
- order history
- order-related backend routes
- order model and database setup
- connection of checkout, payment, receipt, and order pages to backend logic
- basic tests for checkout and order features

### 4. Admin and Reporting

- admin login and access flow
- view and manage customer accounts
- view customer profiles
- add, edit, and remove menu items
- update prices, descriptions, ingredients, categories, and availability
- view customer orders
- track pickup times
- update order status
- view sales and income records
- monthly income chart and reporting
- admin-related backend routes
- basic tests for admin features

## Current Branch Enhancements

Beyond the base project scope above, the current branch includes several upgraded flows and presentation features:

- **Instant counter pickup** with live queue numbering and quoted wait time
- **Scheduled pickup slot capacity handling** and validation
- **branded HTML and PDF receipts**
- **QR codes** on receipts that open live order tracking
- **order history, order detail, and reorder flow**
- **admin queue operations** for active pickup management
- **live order-status presentation** and ready notifications inside the website
- **support chatbox** with OpenAI integration and automatic fallback mode
- **enhanced landing, menu, cart, checkout, and receipt design**

## System Roles

- **Customer Side** for ordering, account access, favourites, and order tracking
- **Admin Side** for restaurant operations, queue handling, order updates, and reporting

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
2. Open the admin ordering and queue management area.
3. Review active instant and scheduled orders.
4. Move orders through the allowed status sequence.
5. Monitor pickup timing, order progress, and customer-side updates.

## User Features

The customer-facing side of the project includes:

- registration, login, and logout
- profile-related account access
- favourite meal saving and sharing
- viewing favourite meals shared by other users
- menu browsing and item detail views
- keyword and category-based discovery
- cart add, update, and summary flow
- instant and scheduled pickup selection
- simulated checkout and payment confirmation
- PDF receipt generation
- QR-based receipt tracking
- order history and order detail pages

## Admin Features

The admin-facing side of the project includes:

- admin login and protected access
- viewing customer orders
- monitoring pickup timing
- updating order status
- queue operations for pickup handling
- menu-management scope for adding, editing, and removing items
- customer-account and profile management scope
- reporting scope for sales and monthly income

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

## Core Data and Backend Scope

The application is structured around the following backend responsibilities:

- user-related routes and session handling
- menu and cart APIs
- order creation, payment simulation, receipt generation, and order history
- admin queue and status management
- database-backed order, line-item, payment-attempt, notification, and queue-counter records

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
- The current branch persists order-related records, line items, payment attempts, notifications, and queue counters.

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

The current test suite includes automated coverage for:

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
- Some project areas are broader in final scope than in the currently polished branch implementation, especially around extended profile, favourites, and reporting workflows.

## Future Extensions

Possible future improvements include:

- real email or SMS notifications
- richer customer accounts and profile editing
- favourites persistence and real shared-meal data
- menu management from the admin side
- stronger analytics and reporting
- real payment gateway integration
