from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

from app import create_app
from models import User, db


class TestPointsAndCommunityStats(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmpdir.name) / "points-test.sqlite"
        self.app = create_app(
            {
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
                "PICKUP_OPEN_HOUR": 0,
                "PICKUP_OPEN_MINUTE": 0,
                "PICKUP_CLOSE_HOUR": 23,
                "PICKUP_CLOSE_MINUTE": 59,
            }
        )
        self.client = self.app.test_client()
        self.base_now = datetime.now(
            ZoneInfo(self.app.config["APP_TIMEZONE"])
        ).replace(hour=12, minute=0, second=0, microsecond=0)
        self._now_patch = patch("routes.orders._now_local", return_value=self.base_now)
        self._now_patch.start()

        with self.app.app_context():
            db.drop_all()
            db.create_all()
            # Register a customer directly in the DB
            db.session.add(User(
                name="Test Customer",
                email="customer@test.com",
                password_hash="x",
                role="customer",
            ))
            db.session.commit()

        # Log in as the test customer via session
        with self.client.session_transaction() as sess:
            sess["auth_user"] = {
                "name": "Test Customer",
                "email": "customer@test.com",
                "role": "customer",
            }

    def tearDown(self) -> None:
        self._now_patch.stop()
        self.tmpdir.cleanup()

    def _first_menu_item(self) -> dict:
        return self.client.get("/api/menu").get_json()["categories"][0]["items"][0]

    def _seed_cart(self, quantity: int = 2) -> None:
        item = self._first_menu_item()
        with self.client.session_transaction() as sess:
            sess["cart_lines"] = [{"id": item["id"], "qty": quantity}]

    def _checkout_form(self, days_ahead: int = 1) -> dict:
        pickup = (self.base_now + timedelta(days=days_ahead)).replace(
            hour=12, minute=30, second=0, microsecond=0
        )
        return {
            "customer_name": "Test Customer",
            "customer_email": "customer@test.com",
            "customer_phone": "0412 345 678",
            "fulfillment_type": "scheduled",
            "pickup_date": pickup.strftime("%Y-%m-%d"),
            "pickup_time": pickup.strftime("%H:%M"),
            "payment_method": "card",
            "card_name": "Test Customer",
            "card_number": "4242 4242 4242 4242",
            "card_expiry": "12/30",
            "card_cvv": "123",
            "special_instructions": "",
        }

    def _place_order(self, days_ahead: int = 1) -> str:
        self._seed_cart()
        response = self.client.post(
            "/checkout",
            data=self._checkout_form(days_ahead=days_ahead),
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)
        location = response.headers["Location"]
        return parse_qs(urlparse(location).query)["order"][0]

    # ── Points tests ──────────────────────────────────────────────────────

    def test_points_balance_starts_at_zero_for_new_user(self):
        with self.app.app_context():
            user = User.query.filter_by(email="customer@test.com").first()
            self.assertEqual(user.points_balance, 0)

    def test_placing_order_increments_points_balance(self):
        self._place_order()
        with self.app.app_context():
            user = User.query.filter_by(email="customer@test.com").first()
            self.assertGreater(user.points_balance, 0)

    def test_points_earned_equals_total_cents_divided_by_100(self):
        self._place_order()
        with self.app.app_context():
            from models import Order
            order = Order.query.filter_by(customer_email="customer@test.com").first()
            user = User.query.filter_by(email="customer@test.com").first()
            expected = order.total_cents // 100
            self.assertEqual(user.points_balance, expected)

    def test_multiple_orders_accumulate_points(self):
        self._place_order(days_ahead=1)
        self._place_order(days_ahead=2)
        with self.app.app_context():
            from models import Order
            orders = Order.query.filter_by(customer_email="customer@test.com").all()
            expected = sum(o.total_cents // 100 for o in orders)
            user = User.query.filter_by(email="customer@test.com").first()
            self.assertEqual(user.points_balance, expected)

    def test_order_increments_total_orders_and_spend(self):
        self._place_order()
        with self.app.app_context():
            from models import Order
            order = Order.query.filter_by(customer_email="customer@test.com").first()
            user = User.query.filter_by(email="customer@test.com").first()
            self.assertEqual(user.total_orders, 1)
            self.assertEqual(user.total_spend_cents, order.total_cents)

    def test_scheduled_order_increments_scheduled_counter(self):
        self._place_order()
        with self.app.app_context():
            user = User.query.filter_by(email="customer@test.com").first()
            self.assertEqual(user.scheduled_orders, 1)
            self.assertEqual(user.instant_orders, 0)

    def test_instant_order_increments_instant_counter(self):
        self._seed_cart()
        form = self._checkout_form()
        form["fulfillment_type"] = "instant"
        form["pickup_date"] = ""
        form["pickup_time"] = ""
        response = self.client.post("/checkout", data=form, follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        with self.app.app_context():
            user = User.query.filter_by(email="customer@test.com").first()
            self.assertEqual(user.instant_orders, 1)
            self.assertEqual(user.scheduled_orders, 0)

    def test_failed_payment_does_not_update_points(self):
        self._seed_cart()
        form = self._checkout_form()
        form["card_number"] = "4000 0000 0000 0002"
        response = self.client.post("/checkout", data=form)
        self.assertEqual(response.status_code, 402)
        with self.app.app_context():
            user = User.query.filter_by(email="customer@test.com").first()
            self.assertEqual(user.points_balance, 0)
            self.assertEqual(user.total_orders, 0)

    def test_profile_page_shows_stored_points_not_derived(self):
        # Set points directly — should show on profile even with no orders
        with self.app.app_context():
            user = User.query.filter_by(email="customer@test.com").first()
            user.points_balance = 270
            db.session.commit()

        response = self.client.get("/membership")
        self.assertEqual(response.status_code, 200)
        self.assertIn("270", response.get_data(as_text=True))

    def test_tier_reflects_stored_points(self):
        with self.app.app_context():
            user = User.query.filter_by(email="customer@test.com").first()
            user.points_balance = 270
            db.session.commit()

        response = self.client.get("/membership")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Market Regular", response.get_data(as_text=True))

    # ── Community stats tests ─────────────────────────────────────────────

    def test_posts_shared_increments_when_post_created(self):
        with self.client.session_transaction() as sess:
            sess["auth_user"] = {
                "name": "Test Customer",
                "email": "customer@test.com",
                "role": "customer",
            }
        self.client.post(
            "/community/posts",
            data={
                "author_name": "Test Customer",
                "post_type": "meal_review",
                "meal_name": "Pho Bo",
                "caption": "Really good broth.",
                "order_number": "",
            },
            follow_redirects=False,
        )
        with self.app.app_context():
            user = User.query.filter_by(email="customer@test.com").first()
            self.assertEqual(user.posts_shared, 1)

    def test_second_post_increments_posts_shared_to_two(self):
        for caption in ("First post", "Second post"):
            self.client.post(
                "/community/posts",
                data={
                    "author_name": "Test Customer",
                    "post_type": "meal_review",
                    "meal_name": "Banh Mi",
                    "caption": caption,
                    "order_number": "",
                },
                follow_redirects=False,
            )
        with self.app.app_context():
            user = User.query.filter_by(email="customer@test.com").first()
            self.assertEqual(user.posts_shared, 2)

    def test_most_shared_dish_updates_to_most_frequent(self):
        for meal in ("Pho Bo", "Pho Bo", "Banh Mi"):
            self.client.post(
                "/community/posts",
                data={
                    "author_name": "Test Customer",
                    "post_type": "meal_review",
                    "meal_name": meal,
                    "caption": "Good meal.",
                    "order_number": "",
                },
                follow_redirects=False,
            )
        with self.app.app_context():
            user = User.query.filter_by(email="customer@test.com").first()
            self.assertEqual(user.most_shared_dish, "Pho Bo")

    def test_likes_received_increments_when_post_gets_reaction(self):
        # Post as the test customer
        self.client.post(
            "/community/posts",
            data={
                "author_name": "Test Customer",
                "post_type": "meal_review",
                "meal_name": "Pho Bo",
                "caption": "Great!",
                "order_number": "",
            },
            follow_redirects=False,
        )
        with self.app.app_context():
            from models import CommunityPost
            post = CommunityPost.query.first()
            post_id = post.id

        # React as a different identity (clear session)
        with self.client.session_transaction() as sess:
            sess.pop("auth_user", None)

        self.client.post(
            f"/community/posts/{post_id}/react",
            data={"reaction_type": "love"},
            follow_redirects=False,
        )

        with self.app.app_context():
            user = User.query.filter_by(email="customer@test.com").first()
            self.assertEqual(user.likes_received, 1)

    def test_community_stats_shown_on_profile_page(self):
        with self.app.app_context():
            user = User.query.filter_by(email="customer@test.com").first()
            user.posts_shared = 4
            user.likes_received = 11
            user.most_shared_dish = "Pho Bo Dac Biet"
            user.favorite_combo = "Pho Bo + Goi Cuon"
            db.session.commit()

        response = self.client.get("/membership")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn("4", html)
        self.assertIn("11", html)
        self.assertIn("Pho Bo Dac Biet", html)


if __name__ == "__main__":
    unittest.main()