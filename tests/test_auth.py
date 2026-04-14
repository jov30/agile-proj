import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app import create_app
from models import db


class TestAuthAndAdminAccess(unittest.TestCase):
    def setUp(self) -> None:
        self.tmpdir = tempfile.TemporaryDirectory()
        db_path = Path(self.tmpdir.name) / "auth-test.sqlite"
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

        with self.app.app_context():
            db.drop_all()
            db.create_all()

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def _first_menu_item(self) -> dict:
        menu = self.client.get("/api/menu").get_json()
        return menu["categories"][0]["items"][0]

    def _seed_cart(self) -> None:
        item = self._first_menu_item()
        with self.client.session_transaction() as session:
            session["cart_lines"] = [{"id": item["id"], "qty": 1}]

    def _valid_checkout_form(self) -> dict[str, str]:
        now = datetime.now(ZoneInfo(self.app.config["APP_TIMEZONE"]))
        pickup = (now + timedelta(days=1)).replace(hour=12, minute=30, second=0, microsecond=0)
        return {
            "customer_name": "Auth Tester",
            "customer_email": "authtester@example.com",
            "customer_phone": "0412 345 678",
            "fulfillment_type": "scheduled",
            "pickup_date": pickup.strftime("%Y-%m-%d"),
            "pickup_time": pickup.strftime("%H:%M"),
            "payment_method": "card",
            "card_name": "Auth Tester",
            "card_number": "4242 4242 4242 4242",
            "card_expiry": "12/30",
            "card_cvv": "123",
            "special_instructions": "",
        }

    def _place_order(self) -> str:
        self._seed_cart()
        response = self.client.post("/checkout", data=self._valid_checkout_form(), follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        return response.headers["Location"].split("order=")[-1]

    def test_admin_page_redirects_anonymous_users_to_login(self):
        response = self.client.get("/admin/orders/queue", follow_redirects=False)
        self.assertEqual(response.status_code, 302)
        self.assertIn("/login?next=/admin/orders/queue", response.headers["Location"])

    def test_customer_session_cannot_call_admin_status_api(self):
        order_number = self._place_order()
        login = self.client.post(
            "/login",
            data={"email": "customer@example.com", "password": "customer-123"},
            follow_redirects=False,
        )
        self.assertEqual(login.status_code, 302)

        response = self.client.patch(
            f"/api/orders/{order_number}/status",
            json={"status": "Preparing"},
        )
        self.assertEqual(response.status_code, 403)
        payload = response.get_json()
        self.assertEqual(payload["error"], "admin access required")


if __name__ == "__main__":
    unittest.main()
