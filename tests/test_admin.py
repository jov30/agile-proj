import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

from app import create_app
from models import Order, OrderNotification, db


class TestAdminQueueOperations(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmpdir.name) / "admin-test.sqlite"
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
        self.base_now = datetime.now(ZoneInfo(self.app.config["APP_TIMEZONE"])).replace(
            hour=12,
            minute=0,
            second=0,
            microsecond=0,
        )
        self._now_patch = patch("routes.orders._now_local", return_value=self.base_now)
        self._now_patch.start()

        with self.app.app_context():
            db.drop_all()
            db.create_all()

    def tearDown(self) -> None:
        self._now_patch.stop()
        self.tmpdir.cleanup()

    def _first_menu_item(self) -> dict:
        menu = self.client.get("/api/menu").get_json()
        return menu["categories"][0]["items"][0]

    def _seed_cart(self) -> None:
        item = self._first_menu_item()
        with self.client.session_transaction() as session:
            session["cart_lines"] = [{"id": item["id"], "qty": 1}]

    def _instant_form(self) -> dict[str, str]:
        return {
            "customer_name": "Queue Admin Test",
            "customer_email": "queueadmin@example.com",
            "customer_phone": "0412 345 678",
            "fulfillment_type": "instant",
            "pickup_date": "",
            "pickup_time": "",
            "payment_method": "card",
            "card_name": "Queue Admin Test",
            "card_number": "4242 4242 4242 4242",
            "card_expiry": "12/30",
            "card_cvv": "123",
            "special_instructions": "Queue test",
        }

    def _scheduled_form(self) -> dict[str, str]:
        pickup = (self.base_now + timedelta(days=1)).replace(hour=12, minute=30, second=0, microsecond=0)
        return {
            "customer_name": "Queue Admin Test",
            "customer_email": "queueadmin@example.com",
            "customer_phone": "0412 345 678",
            "fulfillment_type": "scheduled",
            "pickup_date": pickup.strftime("%Y-%m-%d"),
            "pickup_time": pickup.strftime("%H:%M"),
            "payment_method": "card",
            "card_name": "Queue Admin Test",
            "card_number": "4242 4242 4242 4242",
            "card_expiry": "12/30",
            "card_cvv": "123",
            "special_instructions": "Queue test",
        }

    def _place_order(self, form_data: dict[str, str]) -> str:
        self._seed_cart()
        response = self.client.post("/checkout", data=form_data, follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        return response.headers["Location"].split("order=")[-1]

    def _login_admin(self) -> None:
        response = self.client.post(
            "/login",
            data={
                "email": self.app.config["ADMIN_EMAIL"],
                "password": self.app.config["ADMIN_PASSWORD"],
            },
            follow_redirects=False,
        )
        self.assertEqual(response.status_code, 302)

    def test_admin_queue_page_only_offers_next_status(self):
        instant_order = self._place_order(self._instant_form())
        self._place_order(self._scheduled_form())
        self._login_admin()

        response = self.client.get("/admin/orders/queue")
        self.assertEqual(response.status_code, 200)
        html = response.get_data(as_text=True)
        self.assertIn(instant_order, html)
        self.assertIn("Mark Preparing", html)
        self.assertNotIn("Mark Ready for Pickup", html)

    def test_admin_can_progress_order_to_ready_and_create_notifications(self):
        order_number = self._place_order(self._instant_form())
        self._login_admin()

        preparing = self.client.patch(
            f"/api/orders/{order_number}/status",
            json={"status": "Preparing", "kitchen_notes": "Kitchen has started."},
        )
        self.assertEqual(preparing.status_code, 200)

        ready = self.client.patch(
            f"/api/orders/{order_number}/status",
            json={"status": "Ready for Pickup"},
        )
        self.assertEqual(ready.status_code, 200)
        payload = ready.get_json()
        self.assertEqual(payload["order_status"], "Ready for Pickup")
        self.assertEqual(payload["ready_notification_count"], 2)

        with self.app.app_context():
            order = Order.query.filter_by(order_number=order_number).first()
            self.assertIsNotNone(order)
            notifications = OrderNotification.query.filter_by(order_id=order.id).all()
            self.assertEqual(len(notifications), 2)


if __name__ == "__main__":
    unittest.main()
