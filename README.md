# MCQ Restaurant Scheduled Pickup Ordering and Meal Sharing Platform
## Description

The **MCQ Restaurant Scheduled Pickup Ordering and Meal Sharing Platform** is a web application designed for a Vietnamese restaurant. It allows users to create accounts, browse the menu, place food orders for **scheduled pickup**, and share their favourite meals with other users.

This project is based on a realistic restaurant scenario where customers want a more convenient way to order food online before arriving at the restaurant. The platform is designed as a **client-server web application** and focuses on providing a user-friendly ordering experience while also supporting social interaction through meal sharing.

## Team Members

| UWA ID | Name | GitHub Username |
|--------|------|-----------------|
| 24307608 | Tony Le | utle23 |
| 23957425 | Jovan Pui | jov30 |
| 24220908 | Samuel Ou | slimoftheshady |
| 24181084 | Thomas Zeng | zxx457 |

The application is intended to satisfy the project requirements by including:

- a client-server architecture
- user registration, login, and logout
- persistent user data stored in a database
- the ability for users to view data shared by other users

## Purpose of the Application

The purpose of this application is to solve a real business need by providing an online scheduled pickup ordering system for a restaurant that currently does not have one. It also adds a community element by allowing users to share favourite meals, which makes the platform more interactive and helps satisfy the requirement that users can view data from other users.

The application is designed to be:

- **Engaging** through a clean and appealing restaurant-style interface
- **Effective** by making food ordering more convenient for users
- **Intuitive** through a simple workflow for browsing, ordering, and sharing meals

## System Roles

The platform contains two main sides:

- **User Side** for customers
- **Admin Side** for restaurant administrators

## User Side Features

### User Account Features
Users are able to:
- register a new account
- log in and log out
- view and update profile information

### Ordering Features
Users are able to:
- browse the restaurant menu
- view meal details, including description, price, and ingredients
- add meals to cart
- update meal quantities in cart
- view cart contents and order summary information
- view the total price of their order before checkout
- proceed to checkout
- make a payment through the system
- place an online order
- choose a scheduled pickup date and time
- receive an online receipt and order confirmation after successful checkout
- view previous orders in order history


### Meal Sharing Features
Users are able to:
- save favourite meals
- share favourite meals with other users
- view favourite meals shared by other users

## Admin Side Features

Administrators are able to:
- view registered customer accounts
- manage customer account records
- view customer profile information
- monitor newly registered users
- add new menu items
- edit existing menu items
- remove menu items
- update prices, descriptions, ingredients, categories, and availability status
- view customer orders
- track scheduled pickup times
- monitor order history
- update order status such as Pending, Confirmed, Preparing, Ready for Pickup, and Completed
- view sales and income records
- display monthly income using simple charts for business monitoring

## Example User Workflow

A typical user workflow is as follows:

1. Register an account or log in
2. Browse the menu
3. View meal details
4. Add items to cart
5. Review cart contents, order summary, and total price
6. Proceed to checkout
7. Select a payment method and complete the simulated payment process
8. Choose a scheduled pickup date and time
9. Confirm the order
10. Receive an online receipt and order confirmation
11. View the order in order history
12. Save and share favourite meals
13. Browse favourite meals shared by other users

## Example Admin Workflow

A typical admin workflow is as follows:

1. Log in as an administrator
2. View newly registered users
3. Manage customer account records
4. Update menu items and availability
5. View incoming customer orders
6. Track scheduled pickup times
7. Update order status
8. Review monthly income using charts

## Example Menu Categories

The menu is based on a Vietnamese restaurant and may include items such as:

- **Banh Mi**
- **Bun Bo Hue**
- **Pho**
- **Rice Paper Rolls**
- **Rice Dishes**
- **Drinks**

Each menu item may contain:
- item name
- category
- price
- ingredients
- short description
- availability status

## Application Design

The application follows a traditional web architecture using technologies approved for the unit.

### Client Side
The client side is responsible for displaying web pages, handling user interactions, and sending requests to the server.

### Server Side
The server side handles authentication, ordering logic, profile management, meal sharing, admin management, and sales tracking.

### Database
The database stores persistent data such as:

- user accounts
- login details
- profile information
- menu items
- orders
- favourite meals
- shared meal posts
- sales records

## Technologies Used

This project uses only technologies allowed in the unit specification.

### Frontend
- HTML
- CSS
- JavaScript
- Tailwind CSS

### Backend
- Flask

### Database
- SQLite
- SQLAlchemy

### Additional Tools
- Jinja templates
- Flask plugins introduced in the unit
- AJAX where needed
- a chart library for income visualisation

### Version Control
- Git
- GitHub



## Running the Application

### 1. Clone the repository

```bash
git clone https://github.com/jov30/agile-proj.git
cd your-private-repository
