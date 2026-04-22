## Project Structure

```text
project-root/
│
├── app.py
├── requirements.txt
├── README.md
├── config.py
├── models.py
├── routes/
│   ├── auth.py
│   ├── user.py
│   ├── menu.py
│   ├── orders.py
│   └── admin.py
├── templates/
│   ├── base.html
│   ├── index.html
│   ├── auth/
│   │   ├── login.html
│   │   └── register.html
│   ├── user/
│   │   ├── orders.html
│   │   └── order_detail.html
│   ├── menu/
│   │   ├── menu.html
│   │   ├── cart.html
│   │   └── checkout.html
│   └── admin/
│       └── orders.html
├── static/
│   ├── css/
│   │   └── main.css
│   ├── js/
│   │   ├── cart.js
│   │   ├── checkout.js
│   │   └── admin.js
│   └── images/
├── instance/
│   └── app.db
└── tests/
    ├── test_auth.py
    ├── test_orders.py
    ├── test_menu.py
    └── test_admin.py
```

```text
The project is divided into four main roles, with each person responsible for a clear set of features and tasks. Core and shared team tasks are also outlined.

Person 1 (Samuel) — Authentication, Profile, and Favourite Meals

Role Assignment: Samuel Ou

This role focuses on authentication and user account features, including profile management and favourite meal sharing.

Main files:
- templates/base.html
- templates/index.html
- templates/menu/menu.html
- templates/menu/cart.html
- templates/menu/checkout.html
- static/css/main.css
- static/js/cart.js
- static/js/checkout.js
- routes/menu.py

Main responsibilities:
- user registration
- user login and logout
- profile view and update
- save favourite meals
- share favourite meals with other users
- view favourite meals shared by other users
- auth/profile forms and validation
- user-related backend routes
- user model and database setup
- favourite meal model and database setup
- connect login, register, profile, and shared favourite meal pages to backend logic
- basic tests for auth/profile/favourite meal features

Person 2 (Zeng) — Menu and Cart

Role Assignment: Thomas Zeng

This role focuses on menu browsing and cart experience.

Main files:
- templates/auth/login.html
- templates/auth/register.html
- routes/auth.py

Main responsibilities:
- filter menu bar, looking menu food by keyword
- menu item detail flow if needed
- add items to cart
- update cart quantities
- view cart summary and total price
- cart-related backend routes
- menu/cart data handling
- connect menu and cart pages to backend logic
- basic tests for menu/cart features

Person 3 (Tony) — Checkout, Scheduled + Instant Online Orders, and Receipts + Membership + Chatbox

Role Assignment: Tony Le

This role focuses on checkout, order processing, receipt generation, membership, and chat features.

Main files:
- templates/user/orders.html
- templates/user/order_detail.html
- templates/feature-page.html
- feature_pages.py
- routes/user.py
- routes/orders.py

Main responsibilities:
- checkout flow
- simulated payment flow
- scheduled pickup date and time selection
- order confirmation
- store order records in the database
- PDF receipt generation
- order history
- order-related backend routes
- order model and database setup
- connect checkout, payment, receipt, and order pages to backend logic
- creating membership online card for customer
- Dong chatbox integrated with AI
- basic tests for checkout/order features

Person 4 (Jovan) — Admin and Reporting

This role focuses on the restaurant management side of the system, along with testing and project documentation.

Main files:
- templates/admin/orders.html
- routes/admin.py
- README.md
- tests/

Main responsibilities:
- admin login/access flow
- view and manage customer accounts
- view customer profiles
- add, edit, and remove menu items
- update prices, descriptions, ingredients, categories, and availability
- view customer orders
- track pickup times
- update order status
- view sales/income records
- monthly income chart/reporting
- admin-related backend routes
- basic tests for admin features

Shared team tasks:
- connect everything to SQLite + SQLAlchemy
- agree on common models, field names, and routes
- use separate branches and merge after each feature is stable

Shared Backend Files

Some files affect multiple parts of the system, so they should be treated as shared files and edited carefully.

Shared files:
- app.py
- models.py
- requirements.txt
- config.py

How to handle them:
- the person responsible for the relevant feature should take the lead when editing the related section
- shared files should only be edited when necessary
- team members should communicate before making major changes
- we should avoid editing the same parts at the same time to reduce merge conflicts

Examples:
- Role 2 would mainly handle the authentication-related parts of the User model
- Role 3 would mainly handle user feature models such as favourites, shared meals, and order history records
- Role 1 and Role 3 may coordinate on checkout and order-related logic
- Role 4 would mainly handle admin-related logic, admin data views, and tests

Suggested Route Structure

To make collaboration easier, I think we should split the routes/ folder into separate files:
- routes/auth.py
- routes/user.py
- routes/menu.py
- routes/orders.py
- routes/admin.py

This should reduce Git conflicts and make responsibilities clearer.

If we do that, then:
- Role 1 mainly handles routes/menu.py
- Role 2 mainly handles routes/auth.py
- Role 3 mainly handles routes/user.py and routes/orders.py
- Role 4 mainly handles routes/admin.py

Working Rule

To reduce merge conflicts, each person should mainly work on their assigned files. However, this should not be treated as a completely fixed rule where nobody can ever touch another file. If editing a shared file or another related file is necessary for integration or bug fixing, we should communicate first before making major changes.

This way, responsibilities stay clear, but we still keep enough flexibility for integration and teamwork.
```
